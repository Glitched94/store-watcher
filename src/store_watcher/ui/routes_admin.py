import os
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Form, Query
from fastapi.responses import HTMLResponse

from ..config_sqlite import (
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


@router.get("/listeners", response_class=HTMLResponse)
async def admin_listeners(user: UserDep) -> HTMLResponse:
    ensure_listener_schema(Path(os.getenv("STATE_DB", "/app/data/state.db")))
    listeners = list_listeners(Path(os.getenv("STATE_DB", "/app/data/state.db")), region=None)
    rows: list[str] = []

    for listener in listeners:
        cfg = listener.config
        if listener.kind == "discord":
            display = f"Webhook: {(cfg.get('webhook_url') or '')[:48]}..."
        else:
            display = f"SMTP: {cfg.get('smtp_host')} → {cfg.get('to')}"

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
                </td>
            </tr>
            """
        )

    table = f"""
    <div class="space-y-4">
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
        <form hx-post="/admin/listeners" hx-target="closest div" hx-swap="outerHTML" class="grid md:grid-cols-2 gap-3">
        <div>
            <label class="block text-xs text-slate-400">Region</label>
            <select name="region" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1">
            <option>ALL</option><option>US</option><option>EU</option><option>UK</option><option>ASIA</option><option>AU</option>
            </select>
        </div>
        <div>
            <label class="block text-xs text-slate-400">Kind</label>
            <select name="kind" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1">
            <option value="discord">Discord</option>
            <option value="email">Email (SMTP)</option>
            </select>
        </div>
        <div class="md:col-span-2">
            <label class="block text-xs text-slate-400">Name</label>
            <input name="name" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" placeholder="Team alerts / Personal inbox" />
        </div>

        <!-- Discord -->
        <div class="md:col-span-2">
            <label class="block text-xs text-slate-400">Discord Webhook URL</label>
            <input name="discord_webhook_url" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">Discord Username (optional)</label>
            <input name="discord_username" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">Discord Avatar URL (optional)</label>
            <input name="discord_avatar" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>

        <!-- Email -->
        <div>
            <label class="block text-xs text-slate-400">SMTP Host</label>
            <input name="smtp_host" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">SMTP Port</label>
            <input name="smtp_port" value="587" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">SMTP User</label>
            <input name="smtp_user" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">SMTP Pass</label>
            <input name="smtp_pass" type="password" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">From</label>
            <input name="smtp_from" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>
        <div>
            <label class="block text-xs text-slate-400">To</label>
            <input name="smtp_to" class="w-full bg-slate-900/70 border border-slate-800/60 rounded px-2 py-1" />
        </div>

        <div class="md:col-span-2">
            <button class="px-3 py-1 rounded bg-gradient-to-r from-cyan-600 to-purple-600">Add listener</button>
        </div>
        </form>
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

    # Tell mypy that `k` is exactly one of the two literals
    kind_lit = cast(Literal["discord", "email"], k)

    cfg: dict[str, Any]
    if kind_lit == "discord":
        if not discord_webhook_url.strip():
            return HTMLResponse(
                "<div class='text-rose-400'>Webhook URL required for Discord.</div>",
                status_code=400,
            )
        cfg = {
            "webhook_url": discord_webhook_url.strip(),
            "username": discord_username.strip() or None,
            "avatar_url": discord_avatar.strip() or None,
        }
    else:  # "email"
        if not (smtp_host.strip() and smtp_user.strip() and smtp_pass.strip() and smtp_to.strip()):
            return HTMLResponse(
                "<div class='text-rose-400'>SMTP host/user/pass and To are required.</div>",
                status_code=400,
            )
        cfg = {
            "smtp_host": smtp_host.strip(),
            "smtp_port": int(smtp_port or "587"),
            "smtp_user": smtp_user.strip(),
            "smtp_pass": smtp_pass.strip(),
            "from": (smtp_from.strip() or smtp_user.strip()),
            "to": smtp_to.strip(),
        }

    add_listener(
        dbp,
        Listener(
            id=None,
            region=region.upper(),
            kind=kind_lit,  # <- now a Literal
            enabled=True,
            name=name or f"{kind_lit}@{region}",
            config=cfg,
        ),
    )
    # re-render list
    return await admin_listeners(user)


@router.post("/listeners/toggle", response_class=HTMLResponse)
async def admin_listeners_toggle(user: UserDep, id: int = Query(...)) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)
    # read current state
    ls = list_listeners(dbp)
    m = next((x for x in ls if x.id == id), None)
    if not m:
        return HTMLResponse("<span class='text-rose-400'>Not found</span>", status_code=404)
    set_listener_enabled(dbp, id, not m.enabled)
    return HTMLResponse(
        f"""<button hx-post="/admin/listeners/toggle?id={id}" hx-swap="outerHTML"
        class="px-2 py-0.5 rounded text-xs {'bg-emerald-600' if not m.enabled else 'bg-slate-700'}">
        {"Enabled" if not m.enabled else "Disabled"}</button>"""
    )


@router.delete("/listeners", response_class=HTMLResponse)
async def admin_listeners_delete(user: UserDep, id: int = Query(...)) -> HTMLResponse:
    dbp = Path(os.getenv("STATE_DB", "/app/data/state.db"))
    ensure_listener_schema(dbp)
    delete_listener(dbp, id)
    return HTMLResponse("")  # HTMX will remove the row
