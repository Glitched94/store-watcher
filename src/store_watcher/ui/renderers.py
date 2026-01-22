from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils import site_label
from .helpers import _h_since


def _availability_badge(v: Dict[str, Any]) -> tuple[str, str]:
    availability_message = (v.get("availability_message") or "").strip()
    available_raw = v.get("available")
    available: bool | None
    if isinstance(available_raw, bool):
        available = available_raw
    elif available_raw is None:
        available = None
    else:
        try:
            available = bool(int(available_raw))
        except Exception:
            available = None

    lowered = availability_message.lower()
    if "low" in lowered:
        return (
            "bg-amber-500/15 text-amber-300 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.15)]",
            "Low Stock",
        )

    in_stock_allocation_raw = v.get("in_stock_allocation")
    in_stock_allocation: int | None
    if isinstance(in_stock_allocation_raw, int):
        in_stock_allocation = in_stock_allocation_raw
    elif in_stock_allocation_raw is None:
        in_stock_allocation = None
    else:
        try:
            in_stock_allocation = int(in_stock_allocation_raw)
        except Exception:
            in_stock_allocation = None

    if in_stock_allocation is not None:
        if in_stock_allocation > 0:
            return (
                "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.15)]",
                "In Stock",
            )
        return (
            "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
            "Out of Stock",
        )

    if available is True:
        return (
            "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.15)]",
            "In Stock",
        )

    if available is False:
        return (
            "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
            "Out of Stock",
        )

    if "out" in lowered or "unavailable" in lowered or "sold out" in lowered:
        return (
            "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
            "Out of Stock",
        )

    if "in stock" in lowered or "available" in lowered:
        return (
            "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.15)]",
            "In Stock",
        )

    status = int(v.get("status", 0))
    if status == 0:
        return (
            "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
            "Out of Stock",
        )

    return (
        "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
        "Out of Stock",
    )


def _relative(hours: Optional[float]) -> str:
    if hours is None:
        return ""
    if hours < 24:
        return f"({hours:.1f}h ago)"
    days = hours / 24.0
    if days < 14:
        return f"({days:.1f}d ago)"
    weeks = days / 7.0
    return f"({weeks:.1f}w ago)"


def _pill(cls: str, text: str) -> str:
    return f'<span class="text-[11px] px-2 py-0.5 rounded-full border {cls} whitespace-nowrap">{text}</span>'


def _card_grid(
    key: str,
    v: Dict[str, Any],
    *,
    is_new: bool = False,
    is_restocked: bool = False,
    hours_since_first: Optional[float] = None,
    hours_since_status: Optional[float] = None,
    first_seen: str = "",
    status_since: str = "",
) -> str:
    """Grid card with SQUARE image (only used in Grid view)."""
    lab = site_label((v.get("host") or v.get("url", "")))
    code = key.split(":", 1)[-1]
    name = v.get("name") or ""
    url = v.get("url") or ""
    availability_message = (v.get("availability_message") or "").strip()
    since = status_since or v.get("status_since") or v.get("first_seen")
    h = hours_since_status if hours_since_status is not None else (_h_since(since) or 0.0)
    rel_first = _relative(hours_since_first)
    rel_status = _relative(h)
    first_seen_text = rel_first or (
        f"~{hours_since_first:.1f}h" if hours_since_first is not None else ""
    )
    if not first_seen_text:
        first_seen_text = "—"
    status_since_text = rel_status or f"~{h:.1f}h"
    if not status_since_text:
        status_since_text = "—"
    chip_cls, chip_txt = _availability_badge(v)
    pill_items: list[str] = []
    if is_new:
        pill_items.append(
            _pill(
                "bg-sky-500/15 text-sky-200 border-sky-500/30 shadow-[0_0_18px_rgba(56,189,248,0.15)]",
                "New",
            )
        )
    if is_restocked:
        pill_items.append(
            _pill(
                "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_18px_rgba(16,185,129,0.15)]",
                "Restocked",
            )
        )
    if v.get("price_changed"):
        pill_items.append(
            _pill(
                "bg-amber-500/15 text-amber-200 border-amber-500/30 shadow-[0_0_18px_rgba(245,158,11,0.12)]",
                "Price updated",
            )
        )
    if v.get("availability_changed"):
        pill_items.append(
            _pill(
                "bg-violet-500/15 text-violet-200 border-violet-500/30 shadow-[0_0_18px_rgba(139,92,246,0.12)]",
                "Message updated",
            )
        )

    img = v.get("image") or ""
    if img:
        img_html = (
            f'<div class="w-full aspect-square overflow-hidden rounded-xl mb-3 '
            f'border border-slate-800/60">'
            f'<img src="{img}" alt="" loading="lazy" referrerpolicy="no-referrer" '
            f'class="w-full h-full object-cover" /></div>'
        )
    else:
        img_html = (
            '<div class="w-full aspect-square rounded-xl mb-3 '
            "bg-gradient-to-br from-slate-800/80 to-slate-900/40 "
            'border border-slate-800/60"></div>'
        )

    return f"""
    <div class="h-full rounded-2xl p-[1px] glow-edge">
      <div class="h-full rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-4 flex flex-col card-hover">
        {img_html}
        <div class="flex items-center justify-between gap-2">
          <div class="text-xs text-slate-400">[{lab}] {code}</div>
          <div class="flex flex-wrap items-center gap-2">
            {"".join(pill_items)}
            <span class="text-[11px] px-2 py-0.5 rounded-full border {chip_cls} whitespace-nowrap">{chip_txt}</span>
          </div>
        </div>
        <a class="mt-2 text-base font-medium link-neon break-words" href="{url}">
          {name or url}
        </a>
        <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-200">
          {f'<span class="font-semibold">{v.get("price")}</span>' if v.get("price") else ""}
          {f'<span class="text-xs text-slate-400">{availability_message}</span>' if availability_message else ""}
          {f'<span class="text-xs text-slate-400">Stock: {v.get("in_stock_allocation")}</span>' if v.get("in_stock_allocation") is not None and not (availability_message and str(v.get("in_stock_allocation")) in availability_message) else ""}
        </div>
        <div class="mt-auto pt-3 text-xs text-slate-400 space-y-1">
          <div>First seen {first_seen or "?"} <span class="ml-1 text-slate-500">{first_seen_text}</span></div>
          <div>Status since {since or "?"} <span class="ml-1 text-slate-500">{status_since_text}</span></div>
        </div>
      </div>
    </div>
    """


def _row_list(
    key: str,
    v: Dict[str, Any],
    *,
    is_new: bool = False,
    is_restocked: bool = False,
    hours_since_first: Optional[float] = None,
    hours_since_status: Optional[float] = None,
    first_seen: str = "",
    status_since: str = "",
) -> str:
    """List row WITHOUT image (only used in List view)."""
    lab = site_label((v.get("host") or v.get("url", "")))
    code = key.split(":", 1)[-1]
    name = v.get("name") or ""
    url = v.get("url") or ""
    availability_message = (v.get("availability_message") or "").strip()
    since = status_since or v.get("status_since") or v.get("first_seen")
    h = hours_since_status if hours_since_status is not None else (_h_since(since) or 0.0)
    rel_first = _relative(hours_since_first)
    rel_status = _relative(h)
    first_seen_text = rel_first or (
        f"~{hours_since_first:.1f}h" if hours_since_first is not None else ""
    )
    if not first_seen_text:
        first_seen_text = "—"
    status_since_text = rel_status or f"~{h:.1f}h"
    if not status_since_text:
        status_since_text = "—"
    chip_cls, chip_txt = _availability_badge(v)
    pill_items: list[str] = []
    if is_new:
        pill_items.append(
            _pill(
                "bg-sky-500/15 text-sky-200 border-sky-500/30 shadow-[0_0_18px_rgba(56,189,248,0.15)]",
                "New",
            )
        )
    if is_restocked:
        pill_items.append(
            _pill(
                "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_18px_rgba(16,185,129,0.15)]",
                "Restocked",
            )
        )
    if v.get("price_changed"):
        pill_items.append(
            _pill(
                "bg-amber-500/15 text-amber-200 border-amber-500/30 shadow-[0_0_18px_rgba(245,158,11,0.12)]",
                "Price updated",
            )
        )
    if v.get("availability_changed"):
        pill_items.append(
            _pill(
                "bg-violet-500/15 text-violet-200 border-violet-500/30 shadow-[0_0_18px_rgba(139,92,246,0.12)]",
                "Message updated",
            )
        )
    price_html = (
        f'<div class="text-sm font-semibold text-slate-100">{v.get("price")}</div>'
        if v.get("price")
        else ""
    )
    stock_html = (
        f'<div class="text-xs text-slate-400">Stock: {v.get("in_stock_allocation")}</div>'
        if v.get("in_stock_allocation") is not None
        and not (availability_message and str(v.get("in_stock_allocation")) in availability_message)
        else ""
    )
    availability_line = (
        f'<div class="mt-1 text-xs text-slate-400">{availability_message}</div>'
        if availability_message
        else ""
    )

    return f"""
    <div class="rounded-2xl p-[1px] glow-edge">
      <div class="rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-4 card-hover">
        <div class="flex items-start md:items-center justify-between gap-3">
          <div class="min-w-0 space-y-1">
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span>[{lab}] {code}</span>
              {"".join(pill_items)}
            </div>
            <a class="mt-1 block text-base font-medium link-neon break-words" href="{url}">
              {name or url}
            </a>
            {availability_line}
            <div class="mt-1 text-xs text-slate-400 space-y-1">
              <div>First seen {first_seen or "?"} <span class="ml-1 text-slate-500">{first_seen_text}</span></div>
              <div>Status since {since or "?"} <span class="ml-1 text-slate-500">{status_since_text}</span></div>
            </div>
          </div>
          <div class="flex flex-col items-end gap-2">
            {price_html}
            {stock_html}
            <span class="text-[11px] px-2 py-0.5 rounded-full border {chip_cls} whitespace-nowrap">{chip_txt}</span>
          </div>
        </div>
      </div>
    </div>
    """
