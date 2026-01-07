import os
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.requests import Request

from ..utils import site_label
from .helpers import _load_state_any, _safe_env, _state_sources, _state_version, _to_ord
from .renderers import _card_grid, _row_list

router = APIRouter()


def _header_controls_html(user: Optional[dict[str, Any]]) -> str:
    if user:
        # Authenticated: show Settings, Notifications, and Logout
        return """
        <div class="flex items-center gap-2">
          <button
            class="btn-primary"
            hx-get="/api/config"
            hx-target="#modal-body"
            hx-swap="innerHTML"
            hx-trigger="click"
            onclick="document.getElementById('modal').classList.remove('hidden')">
            Settings
          </button>

          <button
            class="btn-primary"
            hx-get="/admin/listeners"
            hx-target="#modal-body"
            hx-swap="innerHTML"
            hx-trigger="click"
            onclick="document.getElementById('modal').classList.remove('hidden')">
            Notifications
          </button>

          <form method="post" action="/logout" class="inline">
            <button class="btn-primary" type="submit">Logout</button>
          </form>
        </div>
        """
    else:
        # Not authenticated: show the Google-branded button
        # We render Google's button and make it navigate to /login on click
        return """
        <div id="g-btn-wrap" class="flex items-center">
          <div id="g_id_signin"></div>
        </div>
        <script src="https://accounts.google.com/gsi/client" async defer></script>
        <script>
          // Render Google's pre-styled button, but route to /login to use your OAuth flow.
          window.addEventListener('DOMContentLoaded', function () {
            if (window.google && google.accounts && google.accounts.id) {
              // The client_id here is ONLY used by the button library for theming; your real OAuth happens at /login.
              // You can safely leave it blank or duplicate your env value if you want; we’ll just use a click handler.
              google.accounts.id.initialize({ client_id: "", callback: function(){} });
              google.accounts.id.renderButton(
                document.getElementById('g_id_signin'),
                {
                  type: 'standard',
                  theme: 'filled_blue',   // options: outline, filled_black, filled_blue
                  size: 'large',          // large for visibility
                  text: 'signin_with',    // "Sign in with Google"
                  logo_alignment: 'left',
                  shape: 'pill'
                }
              );
              // Hijack click to go through your /login route (Authlib/Google OAuth)
              const btn = document.getElementById('g_id_signin');
              btn.addEventListener('click', function (e) {
                e.preventDefault();
                window.location.href = '/login';
              }, { capture: true });
            }
          });
        </script>
        """


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    user = request.session.get("user")
    header_controls = _header_controls_html(user)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Store Watcher</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://unpkg.com/dayjs@1.11.10/dayjs.min.js"></script>
  <script src="https://unpkg.com/dayjs@1.11.10/plugin/relativeTime.js"></script>
  <script src="https://accounts.google.com/gsi/client" async></script>
  <script>dayjs.extend(window.dayjs_plugin_relativeTime)</script>
  <script>document.documentElement.classList.add('dark')</script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    /* ---- synthwave portfolio vibes ---- */
    :root {{
      --cy: rgba(56, 189, 248, 0.22);
      --fu: rgba(217, 70, 239, 0.20);
      --pu: rgba(139, 92, 246, 0.20);
    }}
    @keyframes gradient-x {{
      0%, 100% {{ background-position: 0% 50%; }}
      50%      {{ background-position: 100% 50%; }}
    }}
    .bg-animate {{
      background-image: linear-gradient(90deg, rgba(56,189,248,0.15), rgba(217,70,239,0.12), rgba(139,92,246,0.12));
      background-size: 200% 200%;
      animation: gradient-x 20s ease infinite;
    }}
    .glow-edge {{
      background: linear-gradient(to bottom right, rgba(56,189,248,0.45), rgba(139,92,246,0.45));
      box-shadow: 0 0 35px rgba(99,102,241,0.15);
    }}
    .card-hover {{
      transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
    }}
    .card-hover:hover {{
      transform: translateY(-2px);
      box-shadow: 0 0 25px rgba(168,85,247,0.35);
      border-color: rgba(168,85,247,0.5);
    }}
    .link-neon {{
      color: rgb(165 243 252 / 0.9);
      text-decoration: none;
      transition: color .15s ease, text-shadow .15s ease;
      text-shadow: 0 0 6px rgba(56,189,248,0.25);
    }}
    .link-neon:hover {{
      color: rgb(224 231 255);
      text-shadow: 0 0 10px rgba(168,85,247,0.35);
      text-decoration: underline;
      text-decoration-color: rgba(56,189,248,0.7);
      text-underline-offset: 3px;
    }}
    .sticky-controls {{
      position: sticky; top: 0; z-index: 20;
      backdrop-filter: blur(14px);
      background: rgba(2,6,23,0.72);
      border-bottom: 1px solid rgba(30,41,59,0.6);
      box-shadow: 0 10px 25px rgba(2,6,23,0.4);
    }}
    .chip {{
      border: 1px solid rgba(148,163,184,0.3);
      background: rgba(2,6,23,0.6);
    }}
    .btn-primary {{
      display: inline-flex; align-items: center; justify-content: center;
      background-image: linear-gradient(90deg, rgba(34,211,238,0.9), rgba(168,85,247,0.9));
      color: #0b1324; font-weight: 600;
      border-radius: 0.75rem;
      padding: 0.5rem 0.75rem;
      box-shadow: 0 0 20px rgba(56,189,248,0.25);
      transition: filter .2s ease, transform .2s ease, box-shadow .2s ease;
    }}
    .btn-primary:hover {{
      filter: brightness(1.05);
      transform: translateY(-1px);
      box-shadow: 0 0 26px rgba(168,85,247,0.35);
    }}
  </style>
</head>
<body class="min-h-screen text-slate-200 bg-slate-950 bg-animate
             bg-[radial-gradient(1200px_600px_at_20%_-10%,rgba(59,130,246,0.15),transparent)]
             bg-[radial-gradient(1000px_600px_at_100%_20%,rgba(168,85,247,0.12),transparent)]">
  <div class="max-w-6xl mx-auto pb-10">
    <header class="px-6 pt-8 pb-4 flex items-end justify-between gap-4">
      <div>
        <h1 class="text-4xl md:text-5xl font-semibold tracking-tight">
          <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-fuchsia-400 to-purple-400
                      drop-shadow-[0_0_10px_rgba(56,189,248,0.35)]">
            Store Watcher
          </span>
        </h1>
        <div class="mt-2 text-slate-400">Track new and restocked items across Disney Store regions.</div>
      </div>

      {header_controls}
    </header>

    <!-- Sticky Controls -->
    <div class="sticky-controls">
      <div class="max-w-6xl mx-auto px-6 py-3">
        <form id="filters"
            hx-get="/api/state"
            hx-target="#items"
            hx-swap="innerHTML"
            hx-push-url="true"
            hx-trigger="submit, keyup changed delay:300ms from:input, change from:select, change from:input[name='view']">
            <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
              <div class="md:col-span-2">
                <label class="block text-xs text-slate-400">Region</label>
                <select name="region"
                      class="w-full bg-slate-900/70 backdrop-blur chip rounded px-2 py-1
                             focus:outline-none focus:ring-2 focus:ring-cyan-500/40">
                <option value="all">All</option>
                <option>US</option><option>EU</option><option>UK</option>
                <option>ASIA</option><option>AU</option>
              </select>
            </div>
            <div class="md:col-span-6">
              <label class="block text-xs text-slate-400">Search</label>
              <input name="q" placeholder="Name or code…"
                     class="w-full bg-slate-900/70 backdrop-blur chip rounded px-2 py-1
                            focus:outline-none focus:ring-2 focus:ring-cyan-500/40" />
            </div>
            <div class="md:col-span-3">
              <label class="block text-xs text-slate-400">View</label>
              <div class="flex rounded-lg overflow-hidden chip">
                <label class="flex-1 text-center text-sm py-1 cursor-pointer hover:bg-slate-900/50">
                  <input type="radio" name="view" value="grid" class="hidden" checked>
                  <span>Grid</span>
                </label>
                <label class="flex-1 text-center text-sm py-1 cursor-pointer hover:bg-slate-900/50 border-l border-slate-800/60">
                  <input type="radio" name="view" value="list" class="hidden">
                  <span>List</span>
                </label>
              </div>
            </div>
            <div class="md:col-span-3">
              <label class="block text-xs text-slate-400">Stock</label>
              <select name="stock"
                      class="w-full bg-slate-900/70 backdrop-blur chip rounded px-2 py-1
                             focus:outline-none focus:ring-2 focus:ring-cyan-500/40">
                <option value="all">All</option>
                <option value="in">In stock</option>
                <option value="out">Out of stock</option>
              </select>
            </div>
            <div class="md:col-span-3">
              <label class="block text-xs text-slate-400">Sort</label>
              <select name="sort"
                      class="w-full bg-slate-900/70 backdrop-blur chip rounded px-2 py-1
                             focus:outline-none focus:ring-2 focus:ring-cyan-500/40">
                <option value="newest">Newest</option>
                <option value="restocked">Recently restocked</option>
                <option value="price_asc">Price (low to high)</option>
                <option value="price_desc">Price (high to low)</option>
              </select>
            </div>
            <div class="md:col-span-1">
              <button class="w-full btn-primary">Filter</button>
            </div>
          </div>
        </form>

        <!-- Auto-refresh bubble -->
        <div class="mt-2 flex items-center justify-end">
          <div class="text-xs text-slate-400 flex items-center gap-2">
            <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full chip">
              <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]"></span>
              Auto-refresh in <span id="refreshCountdown">5:00</span>
            </span>
            <button id="refreshNow" class="text-[11px] px-2 py-1 rounded chip hover:bg-slate-900/60 transition">Refresh now</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Summary -->
    <section class="px-6 mt-6">
      <div id="summary"
           hx-get="/api/summary"
           hx-trigger="load, every 60s"
           class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      </div>
    </section>

    <!-- Items -->
    <section class="px-6 mt-4">
      <div id="items" class="grid items-stretch grid-cols-1 md:grid-cols-2 gap-3" hx-swap-oob="true"></div>
    </section>

    <!-- Modal -->
    <div id="modal" class="hidden fixed inset-0 z-40">
      <!-- backdrop -->
      <div class="absolute inset-0 bg-black/60" onclick="document.getElementById('modal').classList.add('hidden')"></div>
      <!-- dialog -->
      <div class="relative mx-auto mt-24 w-[min(92%,900px)] rounded-2xl p-[1px] glow-edge z-50">
        <div class="rounded-2xl bg-slate-900/80 backdrop-blur border border-slate-800/60 p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Settings</h2>
            <button class="text-slate-400 hover:text-slate-200" onclick="document.getElementById('modal').classList.add('hidden')">✕</button>
          </div>
          <div id="modal-body" class="mt-4 text-sm text-slate-200">
            <!-- /api/config JSON will render here; we’ll prettify below -->
          </div>
        </div>
      </div>
    </div>

    <!-- Prefill from URL & trigger initial submit + countdown/refresh -->
    <script>
      (function () {{
        const AUTORELOAD_MS = 5 * 60 * 1000; // 5 min
        let remaining = AUTORELOAD_MS;

        function applyURLFilters() {{
          const params = new URLSearchParams(window.location.search);
          const q = params.get('q') || '';
          const region = params.get('region') || 'all';
          const view = params.get('view') || 'grid';
          const stock = params.get('stock') || 'all';
          const sort = params.get('sort') || 'newest';
          document.querySelector('input[name="q"]').value = q;
          document.querySelector('select[name="region"]').value = region;
          document.querySelector('select[name="stock"]').value = stock;
          document.querySelector('select[name="sort"]').value = sort;
          document.querySelectorAll('input[name="view"]').forEach((r) => {{
            r.checked = (r.value === view);
          }});
        }}

        function submitFilters() {{
          const form = document.getElementById('filters');
          form.dispatchEvent(new Event('submit', {{ bubbles: true, cancelable: true }}));
        }}

        function updateCountdown(ms) {{
          const el = document.getElementById('refreshCountdown');
          const totalSec = Math.max(0, Math.floor(ms / 1000));
          const m = Math.floor(totalSec / 60);
          const s = (totalSec % 60).toString().padStart(2, '0');
          el.textContent = m + ':' + s;
        }}

        function startTimer() {{
          remaining = AUTORELOAD_MS;
          updateCountdown(remaining);
          if (window.__refreshTimer) clearInterval(window.__refreshTimer);
          window.__refreshTimer = setInterval(() => {{
            remaining -= 1000;
            if (remaining <= 0) {{
              submitFilters();
              remaining = AUTORELOAD_MS;
            }}
            updateCountdown(remaining);
          }}, 1000);
        }}

        window.addEventListener('DOMContentLoaded', () => {{
          applyURLFilters();
          submitFilters();
          startTimer();

          // Keep "/" URL when HTMX navigates (avoid showing /api/state in bar)
          document.body.addEventListener('htmx:afterOnLoad', (ev) => {{
            if (ev.detail && ev.detail.requestConfig && ev.detail.requestConfig.path && ev.detail.requestConfig.path.startsWith('/api/')) {{
              const form = document.getElementById('filters');
              const params = new URLSearchParams(new FormData(form));
              history.replaceState({{}}, '', '/?' + params.toString());
            }}
          }});

          // Reset countdown when user manually refreshes
          document.getElementById('refreshNow').addEventListener('click', (e) => {{
            e.preventDefault();
            submitFilters();
            startTimer();
          }});

          // Also reset countdown whenever the items area finishes an HTMX load
          document.getElementById('items').addEventListener('htmx:afterOnLoad', () => {{
            startTimer();
          }});
        }});
      }})();

      // Pretty-print JSON returned by /api/config
      document.body.addEventListener('htmx:afterOnLoad', (ev) => {{
        if (ev.detail && ev.detail.requestConfig && ev.detail.requestConfig.path === '/api/config') {{
          try {{
            const el = document.getElementById('modal-body');
            const data = JSON.parse(el.textContent);
            el.innerHTML = `
              <div class="grid gap-3 sm:grid-cols-2">
                <div>
                  <div class="text-slate-400 text-xs">Backend</div>
                  <div class="font-mono">${{data.backend}}</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">State path</div>
                  <div class="font-mono break-all">${{data.state_path}}</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">Interval</div>
                  <div class="font-mono">${{data.check_every}}s</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">Restock window</div>
                  <div class="font-mono">${{data.restock_window_hours}}h</div>
                </div>
                <div class="sm:col-span-2">
                  <div class="text-slate-400 text-xs">Target URL</div>
                  <div class="font-mono break-all">${{data.target_url || '—'}}</div>
                <div>
                  <div class="text-slate-400 text-xs">Include RE</div>
                  <div class="font-mono">${{data.include_re || '—'}}</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">Exclude RE</div>
                  <div class="font-mono">${{data.exclude_re || '—'}}</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">Email notifier</div>
                  <div>${{data.notifiers.email ? 'Enabled' : 'Disabled'}}</div>
                </div>
                <div>
                  <div class="text-slate-400 text-xs">Discord notifier</div>
                  <div>${{data.notifiers.discord ? 'Enabled' : 'Disabled'}}</div>
                </div>
              </div>
            `;
          }} catch (e) {{
            // leave raw
          }}
        }}
      }});
    </script>
  </div>
</body>
</html>"""
    return HTMLResponse(html)


@router.get("/api/version", response_class=PlainTextResponse)
async def version() -> PlainTextResponse:
    return PlainTextResponse(_state_version())


@router.get("/api/summary", response_class=HTMLResponse)
async def summary() -> HTMLResponse:
    state = _load_state_any()
    totals: Dict[str, int] = {}
    for _key, v in state.items():
        if int(v.get("status", 0)) != 1:
            continue
        host = v.get("host") or ""
        label = site_label(host or v.get("url", ""))
        totals[label] = totals.get(label, 0) + 1

    labels = ["US", "EU", "UK", "ASIA", "AU"]
    items: List[str] = []
    for lab in labels:
        n = totals.get(lab, 0)
        items.append(
            f"""
            <div class="rounded-2xl p-[1px] glow-edge">
                <div class="rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-3">
                <div class="text-slate-400 text-xs">{lab}</div>
                <div class="text-2xl font-semibold text-slate-100">{n}</div>
                </div>
            </div>
            """
        )
    return HTMLResponse("".join(items))


@router.get("/api/state", response_class=HTMLResponse)
async def state_endpoint(
    region: str = Query("all"),
    q: str = Query("", max_length=100),
    view: str = Query("grid"),  # "grid" | "list"
    stock: str = Query("all"),  # "all" | "in" | "out"
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
) -> HTMLResponse:
    state = _load_state_any()

    region_order: Dict[str, int] = {"US": 0, "EU": 1, "UK": 2, "ASIA": 3, "AU": 4}

    stock = stock if stock in {"all", "in", "out"} else "all"
    sort = sort if sort in {"newest", "restocked", "price_asc", "price_desc"} else "newest"

    def _availability_state(v: Dict[str, Any]) -> Optional[str]:
        status = int(v.get("status", 0))
        available_raw = v.get("available")
        if isinstance(available_raw, bool):
            available: Optional[bool] = available_raw
        elif available_raw is None:
            available = None
        else:
            try:
                available = bool(int(available_raw))
            except Exception:
                available = None

        if status == 0:
            return "out"
        if available is True:
            return "in"
        if available is False:
            return "out"
        return None

    def _price_value(price: Any) -> Optional[float]:
        if not price:
            return None
        text = str(price)
        match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", text.replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group(1))
        except Exception:
            return None

    def sort_key(item: Tuple[str, Dict[str, Any]]) -> Tuple[Any, ...]:
        _key, v = item
        lab = site_label((v.get("host") or v.get("url", "")))
        availability = _availability_state(v)
        availability_rank = {"in": 0, "out": 1, None: 2}[availability]
        first_seen_ord = _to_ord(v.get("first_seen") or v.get("status_since"))
        status_since_ord = _to_ord(v.get("status_since") or v.get("first_seen"))
        price_val = _price_value(v.get("price"))

        if sort == "price_asc":
            return (
                availability_rank,
                price_val if price_val is not None else float("inf"),
                -status_since_ord,
                region_order.get(lab, 99),
                -first_seen_ord,
            )
        if sort == "price_desc":
            return (
                availability_rank,
                -price_val if price_val is not None else float("inf"),
                -status_since_ord,
                region_order.get(lab, 99),
                -first_seen_ord,
            )
        if sort == "restocked":
            return (
                availability_rank,
                -status_since_ord,
                region_order.get(lab, 99),
                -first_seen_ord,
            )
        return (
            availability_rank,
            -first_seen_ord,
            region_order.get(lab, 99),
            -status_since_ord,
        )

    # filter & sort
    ql = q.strip().lower()
    items_filtered: List[Tuple[str, Dict[str, Any]]] = []
    for kv in state.items():
        key, v = kv
        lab = site_label((v.get("host") or v.get("url", "")))
        if region.lower() != "all" and lab != region:
            continue
        code = key.split(":", 1)[-1]
        name = v.get("name") or ""
        url = v.get("url") or ""
        if ql and (ql not in name.lower() and ql not in code and ql not in url.lower()):
            continue
        availability = _availability_state(v)
        if stock == "in" and availability != "in":
            continue
        if stock == "out" and availability != "out":
            continue
        items_filtered.append(kv)

    items_sorted = sorted(items_filtered, key=sort_key)

    total = len(items_sorted)
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    page_items = items_sorted[start:end]

    # choose renderer based on view
    rows: List[str] = []
    if view == "list":
        for k, v in page_items:
            rows.append(_row_list(k, v))
        rows_html = "".join(f'<div class="col-span-full">{r}</div>' for r in rows) if rows else ""
    else:
        for k, v in page_items:
            rows.append(_card_grid(k, v))
        rows_html = "".join(rows)

    if not rows and page == 1:
        rows_html = '<div class="text-slate-400">No items match your filters.</div>'

    # HTMX infinite scroll "load more"
    more = ""
    if end < total:
        from urllib.parse import urlencode

        params = dict(
            region=region, q=q, view=view, stock=stock, sort=sort, page=page + 1, page_size=page_size
        )
        url_more = "/api/state?" + urlencode(params)
        more = f'<div class="col-span-full h-0 p-0 m-0" hx-get="{url_more}" hx-trigger="revealed" hx-swap="outerHTML"></div>'

    return HTMLResponse(rows_html + more)


@router.get("/api/raw", response_class=JSONResponse)
async def raw() -> JSONResponse:
    return JSONResponse(_load_state_any())


@router.get("/api/config", response_class=JSONResponse)
async def config() -> JSONResponse:
    backend, path = _state_sources()
    data = {
        "backend": backend,
        "state_path": str(path),
        "check_every": int(os.getenv("CHECK_EVERY", "300") or 300),
        "restock_window_hours": int(os.getenv("RESTOCK_WINDOW_HOURS", "24") or 24),
        "include_re": os.getenv("INCLUDE_RE", ""),
        "exclude_re": os.getenv("EXCLUDE_RE", ""),
        "target_url": os.getenv("TARGET_URL", ""),
        # masked secrets
        "smtp_host": _safe_env("SMTP_HOST"),
        "smtp_user": _safe_env("SMTP_USER"),
    }
    return JSONResponse(data)
