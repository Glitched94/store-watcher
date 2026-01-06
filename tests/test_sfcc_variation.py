import json
from pathlib import Path

import pytest

from store_watcher.adapters.sfcc import (
    _build_variation_url,
    _extract_region_slug_and_locale,
    _parse_variation_payload,
    build_grid_url,
)


def test_parse_variation_payload_sample() -> None:
    payload_path = Path(__file__).resolve().parent.parent / "Product-Variation.json"
    raw = payload_path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    details = _parse_variation_payload(payload)

    assert details["available"] is True
    assert details["availability_message"] == "In Stock"
    assert details["price"] == "$19.99"

    image = details["image"]
    assert isinstance(image, str)
    assert image.startswith(
        "https://cdn-ssl.s7.shopdisney.com/is/image/DisneyShopping/3803059860920"
    )

    product_url = details["url"]
    assert isinstance(product_url, str)
    assert product_url.endswith("438030107121.html?quantity=1")


def test_extract_region_slug_and_locale() -> None:
    url = (
        "https://www.disneystore.asia/on/demandware.store/"
        "Sites-shopDisneyAP-Site/en_SG/Search-UpdateGrid?cgid=xyz"
    )

    slug, locale = _extract_region_slug_and_locale(url)

    assert slug == "Sites-shopDisneyAP-Site"
    assert locale == "en_SG"


def test_build_variation_url_uses_slug_and_locale() -> None:
    base_url = (
        "https://www.disneystore.asia/on/demandware.store/"
        "Sites-shopDisneyAP-Site/en_SG/Search-UpdateGrid?cgid=xyz"
    )

    variation_url = _build_variation_url(base_url, "12345")

    assert variation_url == (
        "https://www.disneystore.asia/on/demandware.store/"
        "Sites-shopDisneyAP-Site/en_SG/Product-Variation?pid=12345&quantity=1"
    )


def test_build_variation_url_falls_back_to_default() -> None:
    base_url = "https://example.com/products"

    variation_url = _build_variation_url(base_url, "ABC")

    assert variation_url == (
        "https://example.com/on/demandware.store/Sites-shopDisney-Site/default/"
        "Product-Variation?pid=ABC&quantity=1"
    )


def test_build_variation_url_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    base_url = (
        "https://www.disneystore.com/on/demandware.store/"
        "Sites-shopDisney-Site/default/Search-UpdateGrid?cgid=xyz"
    )
    monkeypatch.setenv("TARGET_REGION_SLUG", "Sites-DisneyStoreAUNZ-Site")
    monkeypatch.setenv("TARGET_LOCALE", "en_AU")

    variation_url = _build_variation_url(base_url, "777")

    assert variation_url == (
        "https://www.disneystore.com/on/demandware.store/"
        "Sites-DisneyStoreAUNZ-Site/en_AU/Product-Variation?pid=777&quantity=1"
    )


def test_build_grid_url_from_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure env noise does not leak
    monkeypatch.delenv("TARGET_SCHEME", raising=False)
    monkeypatch.delenv("TARGET_START", raising=False)
    monkeypatch.delenv("TARGET_PAGE_SIZE", raising=False)

    url = build_grid_url(
        host="www.disneystore.asia",
        region_slug="Sites-shopDisneyAP-Site",
        locale="en_SG",
        category_slug="L3_Collectibles_Category_Pin",
        start=0,
        size=200,
    )

    assert url == (
        "https://www.disneystore.asia/on/demandware.store/"
        "Sites-shopDisneyAP-Site/en_SG/Search-UpdateGrid"
        "?cgid=L3_Collectibles_Category_Pin&start=0&sz=200"
    )
