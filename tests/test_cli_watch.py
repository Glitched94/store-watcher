import pytest
from typer.testing import CliRunner

from store_watcher import cli
from store_watcher.core import MULTIPLE_URLS_ERROR, _resolve_target_url, normalize_single_url

runner = CliRunner()


def test_normalize_single_url_happy_path() -> None:
    url = " https://example.com/page "
    assert normalize_single_url(url) == "https://example.com/page"


@pytest.mark.parametrize(
    "raw",
    [
        "https://a.com,https://b.com",
        "https://a.com\nhttps://b.com",
    ],
)
def test_normalize_single_url_rejects_multiple(raw: str) -> None:
    with pytest.raises(ValueError) as exc:
        normalize_single_url(raw)
    assert str(exc.value) == MULTIPLE_URLS_ERROR


def test_watch_cli_rejects_multiple_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_run_watcher(**kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(cli, "run_watcher", fake_run_watcher)

    result = runner.invoke(cli.app, ["watch", "--url", "https://a.com,https://b.com"])

    assert result.exit_code != 0
    assert "Only a single URL is supported" in result.output
    assert calls == {}


def test_resolve_target_url_builds_from_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_URL", raising=False)
    monkeypatch.delenv("TARGET_SCHEME", raising=False)
    monkeypatch.setenv("TARGET_HOST", "www.disneystore.asia")
    monkeypatch.setenv("TARGET_REGION_SLUG", "Sites-shopDisneyAP-Site")
    monkeypatch.setenv("TARGET_LOCALE", "en_SG")
    monkeypatch.setenv("TARGET_CATEGORY_SLUG", "L3_Collectibles_Category_Pin")
    monkeypatch.setenv("TARGET_START", "0")
    monkeypatch.setenv("TARGET_PAGE_SIZE", "200")

    url = _resolve_target_url(None)

    assert (
        url == "https://www.disneystore.asia/on/demandware.store/"
        "Sites-shopDisneyAP-Site/en_SG/Search-UpdateGrid"
        "?cgid=L3_Collectibles_Category_Pin&start=0&sz=200"
    )
