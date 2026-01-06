from __future__ import annotations

from typing import Any, Dict

from ..utils import site_label
from .helpers import _h_since


def _availability_badge(v: Dict[str, Any]) -> tuple[str, str]:
    status = int(v.get("status", 0))
    if status == 0:
        return (
            "bg-amber-500/15 text-amber-300 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.15)]",
            "Absent",
        )

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

    if available is False:
        return (
            "bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]",
            availability_message or "Out of Stock",
        )

    if availability_message:
        lowered = availability_message.lower()
        if "low" in lowered:
            cls = "bg-amber-500/15 text-amber-300 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.15)]"
        else:
            cls = "bg-sky-500/15 text-sky-200 border-sky-500/30 shadow-[0_0_20px_rgba(56,189,248,0.15)]"
        return (cls, availability_message)

    if available is True:
        return (
            "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.15)]",
            "In Stock",
        )

    return (
        "bg-slate-500/20 text-slate-200 border-slate-500/30 shadow-[0_0_20px_rgba(148,163,184,0.12)]",
        "Unknown",
    )


def _card_grid(key: str, v: Dict[str, Any]) -> str:
    """Grid card with SQUARE image (only used in Grid view)."""
    lab = site_label((v.get("host") or v.get("url", "")))
    code = key.split(":", 1)[-1]
    name = v.get("name") or ""
    url = v.get("url") or ""
    since = v.get("status_since") or v.get("first_seen")
    h = _h_since(since) or 0.0
    chip_cls, chip_txt = _availability_badge(v)

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
          <span class="text-[11px] px-2 py-0.5 rounded-full border {chip_cls}">{chip_txt}</span>
        </div>
        <a class="mt-2 text-base font-medium link-neon break-words" href="{url}">
          {name or url}
        </a>
        <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-200">
          {f'<span class="font-semibold">{v.get("price")}</span>' if v.get("price") else ""}
          {f'<span class="text-xs text-slate-400">{v.get("availability_message")}</span>' if v.get("availability_message") else ""}
        </div>
        <div class="mt-auto pt-3 text-xs text-slate-400">
          since {since or "?"} <span class="ml-1 text-slate-500">(~{h:.1f}h)</span>
        </div>
      </div>
    </div>
    """


def _row_list(key: str, v: Dict[str, Any]) -> str:
    """List row WITHOUT image (only used in List view)."""
    lab = site_label((v.get("host") or v.get("url", "")))
    code = key.split(":", 1)[-1]
    name = v.get("name") or ""
    url = v.get("url") or ""
    since = v.get("status_since") or v.get("first_seen")
    h = _h_since(since) or 0.0
    chip_cls, chip_txt = _availability_badge(v)
    price_html = (
        f'<div class="text-sm font-semibold text-slate-100">{v.get("price")}</div>'
        if v.get("price")
        else ""
    )
    availability_line = (
        f'<div class="mt-1 text-xs text-slate-400">{v.get("availability_message")}</div>'
        if v.get("availability_message")
        else ""
    )

    return f"""
    <div class="rounded-2xl p-[1px] glow-edge">
      <div class="rounded-2xl bg-slate-900/70 backdrop-blur border border-slate-800/60 p-4 card-hover">
        <div class="flex items-start md:items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="text-xs text-slate-400">[{lab}] {code}</div>
            <a class="mt-1 block text-base font-medium link-neon break-words" href="{url}">
              {name or url}
            </a>
            {availability_line}
            <div class="mt-1 text-xs text-slate-400">
              since {since or "?"} <span class="ml-1 text-slate-500">(~{h:.1f}h)</span>
            </div>
          </div>
          <div class="flex flex-col items-end gap-2">
            {price_html}
            <span class="text-[11px] px-2 py-0.5 rounded-full border {chip_cls} whitespace-nowrap">{chip_txt}</span>
          </div>
        </div>
      </div>
    </div>
    """
