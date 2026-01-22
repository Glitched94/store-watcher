from typing import Any, Dict

from store_watcher.notify import render_change_digest


def _state(url: str, name: str | None = None) -> Dict[str, Any]:
    rec = {
        "url": url,
        "first_seen": "2025-01-01T00:00:00Z",
        "status": 1,
        "status_since": "2025-01-01T00:00:00Z",
        "in_stock_allocation": 5,
    }
    if name:
        rec["name"] = name
    return rec


def test_render_change_digest_basic() -> None:
    state = {
        "disneystore.com:438039197642": _state(
            "https://www.disneystore.com/animal-pin-the-muppets-438039197642.html",
            name="Animal Pin – The Muppets",
        ),
        "disneystore.com:438018657693": _state("https://www.disneystore.com/xyz-438018657693.html"),
    }

    subject, html_body, text_body = render_change_digest(
        new_codes=["disneystore.com:438039197642"],
        restocked_codes=["disneystore.com:438018657693"],
        state=state,
        target_url="(multiple)",
        total_count=2,
    )

    # Subject summarizes counts
    subj_low = subject.lower()
    assert "1 new" in subj_low and "1 restocked" in subj_low

    # HTML contains an anchor with a short product URL
    assert (
        'href="https://www.disneystore.com/438039197642.html"' in html_body
        or 'href="https://disneystore.com/438039197642.html"' in html_body
    )
    assert "Stock: 5" in html_body

    # The display name should appear somewhere in HTML
    assert "Muppets" in html_body or "Animal Pin" in html_body

    # Text uses short URL and reasonable formatting (no dev-only header)
    assert (
        "https://www.disneystore.com/438039197642.html" in text_body
        or "https://disneystore.com/438039197642.html" in text_body
    )
    assert "Stock: 5" in text_body
    assert "Changes detected on" not in text_body
