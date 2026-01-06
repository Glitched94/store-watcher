import json
from pathlib import Path

from store_watcher.adapters.sfcc import _parse_variation_payload


def test_parse_variation_payload_sample() -> None:
    payload_path = Path(__file__).resolve().parent.parent / "Product-Variation.json"
    raw = payload_path.read_text()
    payload = json.loads(raw)

    details = _parse_variation_payload(payload)

    assert details["available"] is True
    assert details["availability_message"] == "In Stock"
    assert details["price"] == "$19.99"

    image = details["image"]
    assert isinstance(image, str)
    assert image.startswith("https://cdn-ssl.s7.shopdisney.com/is/image/DisneyShopping/3803059860920")

    product_url = details["url"]
    assert isinstance(product_url, str)
    assert product_url.endswith("438030107121.html?quantity=1")