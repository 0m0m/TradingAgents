from urllib.error import URLError

import pytest


class FakeResponse:
    def __init__(self, text: str, encoding: str = "utf-8"):
        self.text = text
        self.encoding = encoding

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.text.encode(self.encoding)


GUBA_HTML = """
<html>
  <body>
    <div id="articlelistnew">
      <div class="articleh normal_post">
        <span class="l1">1234</span>
        <span class="l2">56</span>
        <span class="l3"><a href="/news,000100,123456.html" title="TCL科技面板价格继续回暖">TCL科技面板价格继续回暖</a></span>
        <span class="l4"><a>股友123</a></span>
        <span class="l5">06-01 10:30</span>
      </div>
      <div class="articleh normal_post">
        <span class="l1">88</span>
        <span class="l2">3</span>
        <span class="l3"><a href="/news,000100,123457.html">北向资金怎么看</a></span>
        <span class="l4"><a>价值投资者</a></span>
        <span class="l5">05-31 21:05</span>
      </div>
    </div>
  </body>
</html>
"""


@pytest.mark.unit
def test_fetch_eastmoney_guba_posts_formats_a_share_posts_with_stock_name(monkeypatch):
    import tradingagents.dataflows.eastmoney_guba as guba

    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(GUBA_HTML)

    monkeypatch.setattr(guba, "urlopen", fake_urlopen)
    monkeypatch.setattr(guba, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = guba.fetch_eastmoney_guba_posts("000100.SZ", limit=2, timeout=7.5)

    assert "东方财富股吧" in result
    assert "000100.SZ" in result
    assert "TCL科技" in result
    assert "TCL科技面板价格继续回暖" in result
    assert "阅读 1234" in result
    assert "评论 56" in result
    assert "股友123" in result
    assert "https://guba.eastmoney.com/news,000100,123456.html" in result
    assert requests[0][0].full_url == "https://guba.eastmoney.com/list,000100.html"
    assert requests[0][1] == 7.5


@pytest.mark.unit
def test_fetch_eastmoney_guba_posts_decodes_gb18030_html(monkeypatch):
    import tradingagents.dataflows.eastmoney_guba as guba

    monkeypatch.setattr(guba, "urlopen", lambda request, timeout: FakeResponse(GUBA_HTML, encoding="gb18030"))
    monkeypatch.setattr(guba, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = guba.fetch_eastmoney_guba_posts("000100.SZ", limit=1)

    assert "TCL科技面板价格继续回暖" in result


@pytest.mark.unit
def test_resolve_a_share_identity_accepts_chinese_stock_name(monkeypatch):
    import tradingagents.dataflows.eastmoney_guba as guba

    monkeypatch.setattr(guba, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    identity = guba._resolve_a_share_identity("TCL科技")

    assert identity["supported"] is True
    assert identity["code"] == "000100"
    assert identity["ticker"] == "000100.SZ"
    assert identity["name"] == "TCL科技"
    assert "TCL科技" in identity["aliases"]


@pytest.mark.unit
def test_fetch_eastmoney_guba_posts_rejects_overseas_ticker():
    import tradingagents.dataflows.eastmoney_guba as guba

    result = guba.fetch_eastmoney_guba_posts("AAPL")

    assert "eastmoney guba supports mainland A-share tickers or Chinese stock names only" in result


@pytest.mark.unit
def test_fetch_eastmoney_guba_posts_returns_unavailable_placeholder_on_network_error(monkeypatch):
    import tradingagents.dataflows.eastmoney_guba as guba

    def broken_urlopen(request, timeout):
        raise URLError("network down")

    monkeypatch.setattr(guba, "urlopen", broken_urlopen)
    monkeypatch.setattr(guba, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = guba.fetch_eastmoney_guba_posts("000100.SZ")

    assert result == "<eastmoney guba unavailable: URLError>"


@pytest.mark.unit
def test_fetch_eastmoney_guba_posts_returns_no_posts_placeholder(monkeypatch):
    import tradingagents.dataflows.eastmoney_guba as guba

    monkeypatch.setattr(guba, "urlopen", lambda request, timeout: FakeResponse("<html></html>"))
    monkeypatch.setattr(guba, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = guba.fetch_eastmoney_guba_posts("000100.SZ")

    assert result == "<no Eastmoney Guba posts found for 000100.SZ（TCL科技）>"
