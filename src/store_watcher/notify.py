from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any, List, Tuple

import requests

from .db.config import list_listeners
from .utils import pretty_name_from_url, short_product_url_from_state, site_label

# ---------- Notifier base ----------


class Notifier:
    """Abstract notifier. Implement send()."""

    def send(self, subject: str, html_body: str, text_body: str) -> None:
        raise NotImplementedError


# ---------- Email ----------


class EmailNotifier(Notifier):
    """Uses SMTP_* and EMAIL_FROM from env; recipient comes from listener config."""

    def __init__(self, to_addr: str) -> None:
        self.to_addr = to_addr

    @staticmethod
    def _smtp_settings() -> Tuple[str, int, str, str, str]:
        host = os.getenv("SMTP_HOST", "")
        port = int(os.getenv("SMTP_PORT", "587") or "587")
        user = os.getenv("SMTP_USER", "")
        pwd = os.getenv("SMTP_PASS", "")
        from_addr = os.getenv("EMAIL_FROM", user or "")
        if not (host and user and pwd and from_addr):
            raise RuntimeError(
                "SMTP not configured (need SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM)."
            )
        return host, port, user, pwd, from_addr

    def send(self, subject: str, html_body: str, text_body: str) -> None:
        host, port, user, pwd, from_addr = self._smtp_settings()
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = self.to_addr
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ctx)
            s.login(user, pwd)
            s.send_message(msg)


# ---------- Discord Webhook ----------

DISCORD_EMBEDS_SUPPRESSED = 4


class DiscordNotifier(Notifier):
    """
    Sends Discord messages with masked links and *suppressed embeds*,
    automatically chunking into multiple messages under ~2000 chars.
    """

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def _post(self, content: str) -> None:
        payload: dict[str, Any] = {
            "content": content,
            "flags": DISCORD_EMBEDS_SUPPRESSED,
        }

        r = requests.post(
            self.webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code >= 300:
            # Surface the error text so test UI can show why it failed
            raise RuntimeError(f"Discord webhook {r.status_code}: {r.text[:300]}")

    def send(self, title: str, html_body: str, text_body: str | None = None) -> None:
        if not self.webhook_url:
            # Soft-fail to avoid crashing watcher if a row is misconfigured
            print("[warn] DiscordNotifier missing webhook_url; skipping")
            return

        # Prefer the plaintext digest (already masked links). Fallback to title.
        content = (text_body or title or "").strip()
        if not content:
            return

        # Discord hard limit is 2000; stay a bit under to be safe
        limit = 1900

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


# ---------- Factories ----------


def build_notifiers_from_db(state_db_path: str, watcher_label: str) -> List[Notifier]:
    """Create notifiers scoped to the watcher's region (including ALL)."""

    region = (watcher_label or "").strip().upper() or None

    notifiers: List[Notifier] = []
    for listener in list_listeners(Path(state_db_path), region=region):
        if not listener.enabled:
            continue
        if listener.kind == "discord":
            url = str(listener.config.get("webhook_url") or "").strip()
            if url:
                notifiers.append(DiscordNotifier(url))
        elif listener.kind == "email":
            to_addr = str(listener.config.get("to") or "").strip()
            if to_addr:
                notifiers.append(EmailNotifier(to_addr))
    return notifiers
