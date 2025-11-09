from __future__ import annotations

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests

from .config_sqlite import list_listeners
from .utils import pretty_name_from_url, short_product_url_from_state, site_label

# ---------- Notifier base ----------


class Notifier:
    """Abstract notifier. Implement send()."""

    def send(self, title: str, html_body: str, text_body: str | None = None) -> None:
        raise NotImplementedError


# ---------- Email ----------


class EmailNotifier(Notifier):
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        email_from: str,
        email_to: str,
        use_starttls: bool = True,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.email_from = email_from or user
        self.email_to = email_to
        self.use_starttls = use_starttls

    def send(self, title: str, html_body: str, text_body: str | None = None) -> None:
        if not (self.host and self.user and self.password and self.email_from and self.email_to):
            print("[warn] EmailNotifier missing configuration; skipping")
            return
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = self.email_from
        msg["To"] = self.email_to
        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(self.host, self.port) as s:
            if self.use_starttls:
                s.starttls()
            s.login(self.user, self.password)
            s.sendmail(self.email_from, [self.email_to], msg.as_string())


# ---------- Discord Webhook ----------


class DiscordWebhookNotifier(Notifier):
    """
    Sends Discord messages with masked links and *suppressed embeds*,
    automatically chunking into multiple messages under ~2000 chars.
    """

    def __init__(
        self, webhook_url: str, username: str | None = None, avatar_url: str | None = None
    ):
        self.webhook_url = webhook_url
        self.username = username
        self.avatar_url = avatar_url

    def _post(self, content: str) -> None:
        payload: dict[str, Any] = {
            "content": content,
            "flags": 4,  # SUPPRESS_EMBEDS
        }
        if self.username:
            payload["username"] = self.username
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        r = requests.post(
            self.webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code >= 300:
            print(f"[warn] Discord webhook returned {r.status_code}: {r.text[:200]}")

    def send(self, title: str, html_body: str, text_body: str | None = None) -> None:
        if not self.webhook_url:
            print("[warn] DiscordWebhookNotifier missing webhook_url; skipping")
            return

        content = (text_body or title).strip()
        limit = 1900  # safety margin
        if len(content) <= limit:
            self._post(content)
            return

        # Chunk by line, preserving whole links and headings
        lines = content.splitlines()
        buf: list[str] = []
        cur = 0
        for line in lines:
            add_len = len(line) + 1  # + newline
            if cur + add_len > limit and buf:
                self._post("\n".join(buf))
                buf = []
                cur = 0
            buf.append(line)
            cur += add_len
        if buf:
            self._post("\n".join(buf))


# ---------- Rendering helpers ----------


def render_change_digest(
    *,
    new_codes: list[str],
    restocked_codes: list[str],
    state: dict[str, dict[str, Any]],
    restock_hours: int,
    target_url: str,
    total_count: int,
) -> tuple[str, str, str]:
    """
    Multi-region aware renderer.

    Accepts code keys in either form:
      - "438039197642"                          (single-site legacy)
      - "disneystore.co.uk:438039197642"        (multi-site composite key)

    Produces:
      - subject: "[Store Watch] X new & Y restocked (now N total)"
      - html_body: lists with region prefix and name-only links
      - text_body: Discord-friendly Markdown with masked links and region prefix
    """

    # ----- helpers -----
    def _md_escape(text: str) -> str:
        return (
            text.replace("\\", r"\\")
            .replace("[", r"\[")
            .replace("]", r"\]")
            .replace("(", r"\(")
            .replace(")", r"\)")
            .replace("*", r"\*")
            .replace("_", r"\_")
            .replace("`", r"\`")
            .replace("|", r"\|")
        )

    def _masked_link(name: str, url: str) -> str:
        return f"[{_md_escape(name)}]({url})"

    def _entry(code_key: str) -> tuple[str, str, str]:
        """
        Returns (display_name, html_li, text_li) for one item.
        Adds region prefix like "[US] " based on host.
        """
        host = ""
        if ":" in code_key:
            host, code = code_key.split(":", 1)
            info = state.get(code_key, {})
        else:
            code = code_key
            info = state.get(code_key, {})
            host = info.get("host") or ""  # prefer stored host

        url = info.get("url", "") or str(code)
        # Derive label from host if we have one; otherwise from URL; final fallback "US"
        label = site_label(host or url) or "US"

        name = info.get("name") or pretty_name_from_url(url) or str(code)
        short_url = short_product_url_from_state(url, code if code.isdigit() else "")

        prefix = f"[{label}] "
        html_li = f'<li>{prefix}<a href="{short_url}">{name}</a></li>'
        text_li = f"- {prefix}[{name}]({short_url})"
        return name, html_li, text_li

    # ----- subject -----
    bits = []
    if new_codes:
        bits.append(f"{len(new_codes)} new")
    if restocked_codes:
        bits.append(f"{len(restocked_codes)} restocked")
    subject = (
        "[Store Watch] "
        + (" & ".join(bits) if bits else "No changes")
        + f" (now {total_count} total)"
    )

    # ----- HTML (email) -----
    html_parts: list[str] = []
    if new_codes:
        html_parts.append(f"<p><strong>New items ({len(new_codes)}):</strong></p><ul>")
        for key in sorted(new_codes):
            _, h, _ = _entry(key)
            html_parts.append(h)
        html_parts.append("</ul>")
    if restocked_codes:
        html_parts.append(
            f"<p><strong>Restocked (≥{restock_hours}h absent) "
            f"({len(restocked_codes)}):</strong></p><ul>"
        )
        for key in sorted(restocked_codes):
            _, h, _ = _entry(key)
            html_parts.append(h)
        html_parts.append("</ul>")
    html_parts.append(f"<p>Total items now: {total_count}</p>")
    html_body = "\n".join(html_parts)

    # ----- TEXT (Discord-friendly) -----
    text_lines: list[str] = []
    if new_codes:
        text_lines.append(f"New items ({len(new_codes)}):")
        for key in sorted(new_codes):
            _, _, t = _entry(key)
            text_lines.append(t)
        text_lines.append("")
    if restocked_codes:
        text_lines.append(f"Restocked (≥{restock_hours}h absent) ({len(restocked_codes)}):")
        for key in sorted(restocked_codes):
            _, _, t = _entry(key)
            text_lines.append(t)
        text_lines.append("")
    text_lines.append(f"Total items now: {total_count}")
    text_body = "\n".join(text_lines).strip()

    return subject, html_body, text_body


# ---------- Factory from env ----------


def build_notifiers_from_env() -> list[Notifier]:
    notifiers: list[Notifier] = []

    # Email (SMTP)
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    email_from = os.getenv("EMAIL_FROM", smtp_user)
    email_to = os.getenv("EMAIL_TO", "")

    if smtp_host and smtp_user and smtp_pass and email_to:
        notifiers.append(
            EmailNotifier(smtp_host, smtp_port, smtp_user, smtp_pass, email_from, email_to)
        )

    # Discord
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    discord_name = os.getenv("DISCORD_USERNAME", "") or None
    discord_avatar = os.getenv("DISCORD_AVATAR_URL", "") or None
    if discord_url:
        notifiers.append(DiscordWebhookNotifier(discord_url, discord_name, discord_avatar))

    return notifiers


# ---------- Factory from db ----------


def build_notifiers_from_db(state_db_path: str, region: str) -> list[Notifier]:
    """Load enabled listeners for this region (plus ALL)."""
    notifiers: list[Notifier] = []
    for listener in list_listeners(Path(state_db_path), region=region):
        if not listener.enabled:
            continue

        if listener.kind == "discord":
            cfg = listener.config
            url = (cfg.get("webhook_url") or "").strip()
            if url:
                notifiers.append(
                    DiscordWebhookNotifier(
                        url,
                        cfg.get("username") or None,
                        cfg.get("avatar_url") or None,
                    )
                )

        elif listener.kind == "email":
            cfg = listener.config
            host = (cfg.get("smtp_host") or "").strip()
            user = (cfg.get("smtp_user") or "").strip()
            pw = (cfg.get("smtp_pass") or "").strip()
            to = (cfg.get("to") or "").strip()
            if host and user and pw and to:
                notifiers.append(
                    EmailNotifier(
                        host,
                        int(cfg.get("smtp_port") or 587),
                        user,
                        pw,
                        (cfg.get("from") or user),
                        to,
                    )
                )
    return notifiers
