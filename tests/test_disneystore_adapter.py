import re
from types import SimpleNamespace
from store_watcher.adapters.disneystore import DisneyStoreAdapter

HTML = """
<html><body>
  <a class="card" href="/animal-pin-the-muppets-438039197642.html" title="Animal Pin – The Muppets">Animal Pin</a>
  <a class="card" href="/ariel-and-sebastian-pin-the-little-mermaid-438039196577.html?searchType=redirect">Ariel</a>
  <a class="card" href="/not-a-product">Ignore</a>
</body></html>
"""

class DummyResp:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass

class DummySession:
    def __init__(self, html): self._html = html
    def get(self, url, timeout=25): return DummyResp(self._html)

def test_adapter_parses_codes_and_titles():
    adapter = DisneyStoreAdapter()
    session = DummySession(HTML)
    items = list(adapter.fetch(session, "https://www.disneystore.com/grid", include_rx=None, exclude_rx=None))
    codes = {i.code for i in items}
    assert "438039197642" in codes
    assert "438039196577" in codes
    # title is best-effort (may be None); check we pass something if present
    muppets = [i for i in items if i.code == "438039197642"][0]
    assert muppets.url.endswith("/animal-pin-the-muppets-438039197642.html")
    assert muppets.title is None or "Animal" in (muppets.title or "")
