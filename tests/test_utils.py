import pytest

from store_watcher.utils import (
    canonicalize,
    extract_product_code,
    pretty_name_from_url,
    short_product_url_from_state,
    slug_to_title,
)


def test_canonicalize_basic():
    u = "https://WWW.disneystore.com//foo//bar.html?searchType=redirect#frag"
    assert canonicalize(u) == "https://disneystore.com/foo/bar.html"


@pytest.mark.parametrize(
    "url,code",
    [
        ("https://disneystore.com/animal-pin-the-muppets-438039197642.html", "438039197642"),
        ("https://www.disneystore.com/x-y-438018657693.html?foo=1", "438018657693"),
        ("https://disneystore.com/123456.html", "123456"),
        ("https://disneystore.com/no-code-here.html", None),
    ],
)
def test_extract_product_code(url, code):
    assert extract_product_code(url) == code


def test_slug_to_title_and_pretty_name():
    slug = "disneyland-70th-anniversary-vault-collection-pin-display-frame-with-three-pins-limited-edition-438018657693"
    titled = slug_to_title(slug)
    assert (
        "Disneyland 70th Anniversary Vault Collection Pin Display Frame with Three Pins Limited Edition"
        in titled
    )
    url = "https://disneystore.com/" + slug + ".html"
    pretty = pretty_name_from_url(url)
    assert pretty.startswith("Disneyland 70th Anniversary")


def test_short_product_url_from_state():
    long = "https://www.disneystore.com/animal-pin-the-muppets-438039197642.html?x=y"
    short = short_product_url_from_state(long, "438039197642")
    assert short == "https://disneystore.com/438039197642.html"

    # Non-Disney host falls back to canonicalized original
    other = "https://example.com/foo-123456.html?x=1"
    assert short_product_url_from_state(other, "123456") == "https://example.com/123456.html"
