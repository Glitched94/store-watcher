import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..db.config import (
    Listener,
    add_listener,
    delete_listener,
    ensure_listener_schema,
    list_listeners,
    set_listener_enabled,
)
from .helpers import SessionUser, _require_user

router = APIRouter(prefix="/admin")
UserDep = Annotated[SessionUser, Depends(_require_user)]


def _send_test_discord(cfg: dict) -> None:
    url = str(cfg.get("webhook_url") or "").strip()
    if not url:
        raise RuntimeError("Discord webhook_url is empty")

    try:
        r = httpx.post(
            url,
            json={"content": "🔔 Store Watcher test message (Discord)"},
            timeout=10,
        )
    except httpx.RequestError as e:
        # network/DNS/timeout
        raise RuntimeError(f"RequestError: {e.__class__.__name__}: {e}") from e

    # Discord usually returns 204 No Content on success
    if r.status_code not in (200, 204):
        text = (r.text or "").strip()
        # Trim to keep badge readable
        if len(text) > 500:
            text = text[:500] + "…"
        raise RuntimeError(f"HTTP {r.status_code}: {text or 'No response body'}")


def _send_test_email(cfg: dict[str, Any]) -> None:
    """
    Send a test email using server env (SMTP_* and EMAIL_FROM).
    Listener config only needs {"to": "..."}.
    """
    to = str(cfg.get("to") or "").strip()
    if not to:
        raise ValueError("Listener config must include 'to' email address")

    host = (os.getenv("SMTP_HOST") or "").strip()
    port_str = (os.getenv("SMTP_PORT") or "587").strip()
    user = (os.getenv("SMTP_USER") or "").strip()
    pwd = (os.getenv("SMTP_PASS") or "").strip()
    sender = (os.getenv("EMAIL_FROM") or user).strip()

    try:
        port = int(port_str)
    except ValueError:
        raise RuntimeError(f"Invalid SMTP_PORT value: {port_str!r}")

    missing = [
        name
        for name, val in {"SMTP_HOST": host, "SMTP_USER": user, "SMTP_PASS": pwd}.items()
        if not val
    ]
    if missing:
        raise RuntimeError("Missing required SMTP environment variables: " + ", ".join(missing))

    msg = EmailMessage()
    msg["Subject"] = "Store Watcher test"
    msg["From"] = sender or user
    msg["To"] = to
    msg.set_content("This is a Store Watcher test message (text).")
    msg.add_alternative(
        "<p>This is a <b>Store Watcher</b> test message (HTML).</p>", subtype="html"
    )

    context = ssl.create_default_context()

    # Use SMTPS for 465, STARTTLS for 587, plain for others
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            if port == 587:
                s.starttls(context=context)
            s.login(user, pwd)
            s.send_message(msg)


@router.get("/listeners", response_class=HTMLResponse)
async def admin_listeners(user: UserDep) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)
    listeners = list_listeners(dbp, region=None, user_id=user["id"])

    rows: list[str] = []

    for listener in listeners:
        cfg = listener.config
        if listener.kind == "discord":
            display = f"Webhook: {(cfg.get('webhook_url') or '')[:48]}..."
        else:
            display = f"To: {cfg.get('to')}"

        rows.append(
            f"""
            <tr class="border-b border-slate-800/60">
            <td class="px-2 py-1 text-slate-300">{listener.id}</td>
            <td class="px-2 py-1">{listener.region}</td>
            <td class="px-2 py-1">{listener.kind}</td>
            <td class="px-2 py-1">{listener.name}</td>
            <td class="px-2 py-1 text-slate-400 text-sm">{display}</td>
            <td class="px-2 py-1">
                <button hx-post="/admin/listeners/toggle?id={listener.id}" hx-swap="outerHTML"
                        class="px-2 py-0.5 rounded text-xs {'bg-emerald-600' if listener.enabled else 'bg-slate-700'}">
                {"Enabled" if listener.enabled else "Disabled"}
                </button>
                <button hx-delete="/admin/listeners?id={listener.id}" hx-target="closest tr" hx-swap="outerHTML"
                        class="ml-2 px-2 py-0.5 rounded text-xs bg-rose-700/80">Delete</button>
                <button hx-post="/admin/listeners/test?id={listener.id}" 
                        hx-target="this" hx-swap="outerHTML"
                        class="ml-2 px-2 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600">
                Test
                </button>
            </td>
            </tr>
            """
        )

    table = f"""
    <div id="listeners-panel" class="space-y-4">
        <h2 class="text-xl font-semibold">Listeners</h2>
        <table class="w-full text-left text-slate-200">
            <thead class="text-slate-400 text-xs uppercase">
            <tr>
                <th class="px-2 py-1">ID</th>
                <th class="px-2 py-1">Region</th>
                <th class="px-2 py-1">Kind</th>
                <th class="px-2 py-1">Name</th>
                <th class="px-2 py-1">Config</th>
                <th class="px-2 py-1">Actions</th>
            </tr>
            </thead>
            <tbody>
            {"".join(rows) or '<tr><td colspan="6" class="px-2 py-4 text-slate-400">No listeners yet.</td></tr>'}
            </tbody>
        </table>

        <h3 class="text-lg font-semibold">Add listener</h3>
        <form id="listenerForm" hx-post="/admin/listeners" hx-target="closest div" hx-swap="outerHTML" class="grid md:grid-cols-2 gap-3">
        <div>
            <label class="block text-xs text-slate-400">Region</label>
            <select name="region" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1">
            <option>ALL</option><option>US</option><option>EU</option><option>UK</option><option>ASIA</option><option>AU</option>
            </select>
        </div>
        <div>
            <label class="block text-xs text-slate-400">Kind</label>
            <select name="kind" id="kindSelect" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1">
            <option value="discord">Discord</option>
            <option value="email">Email (SMTP)</option>
            </select>
        </div>
        <div class="md:col-span-2">
            <label class="block text-xs text-slate-400">Name</label>
            <input name="name" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" placeholder="Team alerts / Personal inbox" />
        </div>

        <!-- Discord-only -->
        <div data-kind-section="discord" class="md:col-span-2">
            <label class="block text-xs text-slate-400">Discord Webhook URL</label>
            <input name="discord_webhook_url" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>

        <!-- Email-only -->
        <div data-kind-section="email" class="md:col-span-2">
            <label class="block text-xs text-slate-400">Email To</label>
            <input name="smtp_to" type="email" placeholder="recipient@example.com" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
            <div class="mt-1 text-xs text-slate-400">Uses SMTP_* and EMAIL_FROM from server env.</div>
        </div>

        <div class="md:col-span-2">
            <button class="px-3 py-1 rounded bg-gradient-to-r from-cyan-600 to-purple-600">Add listener</button>
        </div>
        </form>

        <script>
        (function () {{
            const select = document.getElementById('kindSelect');
            const sections = document.querySelectorAll('[data-kind-section]');
            function applyKind() {{
                const k = select.value;
                sections.forEach(el => {{
                    const showFor = el.getAttribute('data-kind-section');
                    el.style.display = (showFor === k) ? '' : 'none';
                }});
            }}
            select.addEventListener('change', applyKind);
            applyKind(); // initial
            // Re-apply after HTMX swap (when form re-renders)
            document.body.addEventListener('htmx:afterOnLoad', ev => {{
                if (ev.detail && ev.detail.target && ev.detail.target.id === 'listenerForm') {{
                    const s = document.getElementById('kindSelect');
                    if (s) s.dispatchEvent(new Event('change'));
                }}
            }});
        }})();
        </script>
    </div>
    """
    return HTMLResponse(table)


@router.post("/listeners", response_class=HTMLResponse)
async def admin_listeners_add(
    user: UserDep,
    region: str = Form(...),
    kind: str = Form(...),
    name: str = Form(""),
    discord_webhook_url: str = Form(""),
    discord_username: str = Form(""),
    discord_avatar: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    smtp_from: str = Form(""),
    smtp_to: str = Form(""),
) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)

    k = kind.lower().strip()
    if k not in ("discord", "email"):
        return HTMLResponse("<div class='text-rose-400'>Unknown kind.</div>", status_code=400)
    kind_lit = cast(Literal["discord", "email"], k)

    if kind_lit == "discord":
        if not discord_webhook_url.strip():
            return HTMLResponse(
                "<div class='text-rose-400'>Webhook URL required.</div>", status_code=400
            )
        cfg = {"webhook_url": discord_webhook_url.strip()}
    else:
        if not smtp_to.strip():
            return HTMLResponse(
                "<div class='text-rose-400'>Email To address is required.</div>", status_code=400
            )
        cfg = {"to": smtp_to.strip()}

    add_listener(
        dbp,
        Listener(
            id=None,
            region=region.upper(),
            kind=kind_lit,
            enabled=True,
            name=name or f"{kind_lit}@{region}",
            config=cfg,
            user_id=user["id"],
        ),
    )
    return await admin_listeners(user)


@router.post("/listeners/toggle", response_class=HTMLResponse)
async def admin_listeners_toggle(user: UserDep, id: int = Query(...)) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)
    ls = list_listeners(dbp, user_id=user["id"])
    m = next((x for x in ls if x.id == id), None)
    if not m:
        return HTMLResponse("<span class='text-rose-400'>Not found</span>", status_code=404)
    set_listener_enabled(dbp, id, not m.enabled, user_id=user["id"])
    return HTMLResponse(
        f"""<button hx-post="/admin/listeners/toggle?id={id}" hx-swap="outerHTML"
        class="px-2 py-0.5 rounded text-xs {'bg-emerald-600' if not m.enabled else 'bg-slate-700'}">
        {"Enabled" if not m.enabled else "Disabled"}</button>"""
    )


@router.delete("/listeners", response_class=HTMLResponse)
async def admin_listeners_delete(user: UserDep, id: int = Query(...)) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)
    delete_listener(dbp, id, user_id=user["id"])
    return HTMLResponse("")  # HTMX will remove the row


@router.post("/listeners/test", response_class=HTMLResponse)
async def admin_listeners_test(user: UserDep, id: int = Query(...)) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)

    listeners = list_listeners(dbp, user_id=user["id"])
    lst = next((x for x in listeners if x.id == id), None)
    if not lst:
        raise HTTPException(status_code=404, detail="Listener not found")

    ok = False
    msg = "Test sent!"
    try:
        if lst.kind == "discord":
            _send_test_discord(lst.config)
        else:
            _send_test_email(lst.config)
        ok = True
    except Exception as e:
        # Surface an actionable snippet
        msg = f"Failed: {str(e)}"

    color = "emerald" if ok else "rose"

    # Replace ONLY the clicked button; then refresh the listeners panel after 2s
    return HTMLResponse(
        f"""
        <span class="ml-2 text-xs px-2 py-0.5 rounded border border-{color}-500/40 text-{color}-300 bg-{color}-500/10">{msg}</span>
        <script>
          setTimeout(() => {{
            const panel = document.getElementById('listeners-panel');
            if (panel) {{
              htmx.ajax('GET', '/admin/listeners', {{target: panel, swap: 'outerHTML'}});
            }}
          }}, 2000);
        </script>
        """,
        status_code=200 if ok else 500,
    )
