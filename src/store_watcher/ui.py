from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .state import load_state as load_any_state
from .utils import site_label


def _utcnow() -> datetime:
    return datetime.now(UTC)

def _h_since(iso: str | None) -> float | None:
    if not iso:
        return None
    s = iso.replace("Z", "+00:00")
    try:
        then = datetime.fromisoformat(s)
    except Exception:
        return None
    return max(0.0, (_utcnow() - then).total_seconds() / 3600.0)

def _load_state_current() -> dict[str, dict[str, Any]]:
    return load_any_state()

def _state_version() -> str:
    db = os.getenv("STATE_DB", "").strip()
    try:
        if db:
            return str(int(Path(db).stat().st_mtime))
        else:
            return str(int(Path(os.getenv("STATE_FILE","seen_items.json")).stat().st_mtime))
    except Exception:
        return "0"

def create_app(dotenv_path: str | None = None) -> FastAPI:
    load_dotenv(dotenv_path=dotenv_path)
    app = FastAPI(title="Store Watcher UI")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        # Simple Tailwind + HTMX page; HTMX swaps the two fragments below
        html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Store Watcher</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://unpkg.com/dayjs@1.11.10/dayjs.min.js"></script>
  <script src="https://unpkg.com/dayjs@1.11.10/plugin/relativeTime.js"></script>
  <script>dayjs.extend(window.dayjs_plugin_relativeTime)</script>
  <script>document.documentElement.classList.add('dark')</script>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen text-slate-200 bg-slate-950
             bg-[radial-gradient(1200px_600px_at_20%_-10%,rgba(59,130,246,0.15),transparent)]
             bg-[radial-gradient(1000px_600px_at_100%_20%,rgba(168,85,247,0.12),transparent)]">
  <div class="max-w-6xl mx-auto p-6 space-y-6">
    <h1 class="text-3xl font-semibold tracking-tight">
      <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-400
                   drop-shadow-[0_0_10px_rgba(56,189,248,0.35)]">
        Store Watcher
      </span>
    </h1>

    <!-- Controls -->
    <form id="filters"
          class="flex flex-wrap md:flex-nowrap items-end gap-3"
          hx-get="/api/state"
          hx-target="#items"
          hx-swap="innerHTML"
          hx-trigger="submit, keyup changed delay:300ms from:input, change from:select">

    <div class="w-40">
        <label class="block text-xs text-slate-400">Region</label>
        <select name="region"
                class="w-full bg-slate-900/70 backdrop-blur border border-slate-800/60 rounded px-2 py-1
                    focus:outline-none focus:ring-2 focus:ring-cyan-500/40">
        <option value="all">All</option>
        <option>US</option><option>EU</option><option>UK</option>
        <option>ASIA</option><option>AU</option><option>JP</option>
        </select>
    </div>

    <div class="flex-1 min-w-[220px]">
        <label class="block text-xs text-slate-400">Search</label>
        <input name="q" placeholder="Name or code…"
            class="w-full bg-slate-900/70 backdrop-blur border border-slate-800/60 rounded px-2 py-1
                    focus:outline-none focus:ring-2 focus:ring-cyan-500/40" />
    </div>

    <div>
        <button class="px-3 py-2 rounded bg-gradient-to-r from-cyan-600 to-purple-600
                    hover:from-cyan-500 hover:to-purple-500 transition-colors
                    shadow-[0_0_20px_rgba(56,189,248,0.25)]">
        Filter
        </button>
    </div>
    </form>

    <!-- Summary -->
    <div id="summary"
         hx-get="/api/summary"
         hx-trigger="load, every 10s"
         class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
    </div>

    <!-- Items -->
    <div id="items"
         class="grid items-stretch grid-cols-1 md:grid-cols-2 gap-3"
         hx-swap-oob="true"></div>

    <span id="vwatch"
        hx-get="/api/version"
        hx-trigger="load, every 30s"
        hx-swap="none"
        hx-on::after-on-load="
            const v = event.detail.xhr.responseText;
            if (this.dataset.v !== v) {
            this.dataset.v = v;
            htmx.trigger('#filters', 'submit');
            }
        "></span>

    <!-- Prefill from URL & trigger initial submit -->
    <script>
      window.addEventListener('DOMContentLoaded', () => {
        const params = new URLSearchParams(window.location.search);
        const q = params.get('q') || '';
        const region = params.get('region') || 'all';
        const qInput = document.querySelector('input[name="q"]');
        const regionSel = document.querySelector('select[name="region"]');
        if (qInput) qInput.value = q;
        if (regionSel) regionSel.value = region;
        document.getElementById('filters')
          .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      });

      // Keep the address bar on "/" with current filters (avoid pushing /api/state)
      const form = document.getElementById('filters');
      form.addEventListener('htmx:beforeRequest', (e) => {
        const params = new URLSearchParams(new FormData(form));
        history.replaceState(null, "", "/?" + params.toString());
      });
    </script>
  </div>
</body>
</html>"""
        return HTMLResponse(html)

    @app.get("/api/version", response_class=PlainTextResponse)
    async def version():
        return PlainTextResponse(_state_version())

    @app.get("/api/summary", response_class=HTMLResponse)
    async def summary():
        state = _load_state_current()
        # group by label only for items currently present
        totals: dict[str, int] = {}
        for key, v in state.items():
            if int(v.get("status", 0)) != 1:
                continue
            host = v.get("host") or ""
            label = site_label(host or v.get("url", ""))
            totals[label] = totals.get(label, 0) + 1

        # build cards
        labels = ["US", "EU", "UK", "ASIA", "AU", "JP"]
        items = []
        for lab in labels:
            n = totals.get(lab, 0)
            items.append(
                f'''
                <div class="rounded-2xl p-[1px] bg-gradient-to-br from-cyan-500/40 to-purple-500/40
                            shadow-[0_0_35px_rgba(99,102,241,0.15)]">
                <div class="rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-3">
                    <div class="text-slate-400 text-xs">{lab}</div>
                    <div class="text-2xl font-semibold text-slate-100">{n}</div>
                </div>
                </div>
                '''
            )
        return HTMLResponse("".join(items))

    @app.get("/api/state", response_class=HTMLResponse)
    async def state(
        region: str = Query("all"),
        q: str = Query("", max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=10, le=200),
    ):
        state = _load_state_current()

        region_order = {"US": 0, "EU": 1, "UK": 2, "ASIA": 3, "AU": 4, "JP": 5}

        def to_ord(iso: str | None) -> int:
            if not iso:
                return 0
            s = iso.replace("Z", "+00:00")
            try:
                y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
                hh, mm, ss = int(s[11:13]), int(s[14:16]), int(s[17:19])
                return (((((y * 12 + m) * 31 + d) * 24 + hh) * 60 + mm) * 60 + ss)
            except Exception:
                return 0

        def sort_key(item):
            _key, v = item
            lab = site_label(v.get("host") or v.get("url", ""))
            status = int(v.get("status", 0))
            since = v.get("status_since") or v.get("first_seen")
            return (region_order.get(lab, 99), 0 if status == 1 else 1, -to_ord(since))

        # filter & sort (all), then slice
        ql = q.strip().lower()
        items_sorted = []
        for kv in sorted(state.items(), key=sort_key):
            key, v = kv
            lab = site_label(v.get("host") or v.get("url", ""))
            if region.lower() != "all" and lab != region:
                continue
            code = key.split(":", 1)[-1]
            name = v.get("name") or ""
            url = v.get("url") or ""
            if ql and (ql not in name.lower() and ql not in code and ql not in url.lower()):
                continue
            items_sorted.append(kv)

        total = len(items_sorted)
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        page_items = items_sorted[start:end]

        def card(key, v):
            lab = site_label(v.get("host") or v.get("url", ""))
            code = key.split(":", 1)[-1]
            name = v.get("name") or ""
            url = v.get("url") or ""
            status = int(v.get("status", 0))
            since = v.get("status_since") or v.get("first_seen")
            h = _h_since(since) or 0.0
            chip_cls, chip_txt = (
                ("bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.15)]", "Present")
                if status == 1 else
                ("bg-amber-500/15 text-amber-300 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.15)]", "Absent")
            )
            return f'''
            <div class="h-full rounded-2xl p-[1px] bg-gradient-to-br from-cyan-500/40 to-purple-500/40
                        shadow-[0_0_35px_rgba(99,102,241,0.15)]">
            <div class="h-full rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-4 flex flex-col">
                <div class="flex items-center justify-between gap-2">
                <div class="text-xs text-slate-400">[{lab}] {code}</div>
                <span class="text-[11px] px-2 py-0.5 rounded-full border {chip_cls}">{chip_txt}</span>
                </div>
                <a class="mt-2 text-base font-medium text-cyan-200 hover:text-cyan-100 transition-colors break-words" href="{url}">
                {name or url}
                </a>
                <div class="mt-auto pt-3 text-xs text-slate-400">
                since {since or "?"} <span class="ml-1 text-slate-500">(~{h:.1f}h)</span>
                </div>
            </div>
            </div>'''

        rows = [card(k, v) for k, v in page_items]
        if not rows and page == 1:
            rows.append('<div class="text-slate-400">No items match your filters.</div>')

        # “Load more” sentinel for HTMX infinite scroll
        more = ""
        if end < total:
            # Preserve current filters in next-page URL
            from urllib.parse import urlencode
            params = dict(region=region, q=q, page=page + 1, page_size=page_size)
            url = "/api/state?" + urlencode(params)
            more = f'<div class="col-span-full h-0 p-0 m-0" hx-get="{url}" hx-trigger="revealed" hx-swap="outerHTML"></div>'

        return HTMLResponse("".join(rows) + more)

    @app.get("/api/raw", response_class=JSONResponse)
    async def raw():
        return JSONResponse(_load_state_current())

    return app
