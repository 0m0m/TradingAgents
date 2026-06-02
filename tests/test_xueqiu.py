import pandas as pd
import pytest


class FakeAkshare:
    def stock_hot_follow_xq(self, symbol="最热门"):
        assert symbol == "最热门"
        return pd.DataFrame(
            [
                {"股票代码": "000100", "股票简称": "TCL科技", "排名": 3, "关注": 1888},
                {"股票代码": "000001", "股票简称": "平安银行", "排名": 4, "关注": 900},
            ]
        )

    def stock_hot_tweet_xq(self, symbol="最热门"):
        assert symbol == "最热门"
        return pd.DataFrame(
            [
                {"股票代码": "000100", "股票简称": "TCL科技", "排名": 7, "讨论": 321},
                {"股票代码": "000001", "股票简称": "平安银行", "排名": 8, "讨论": 100},
            ]
        )

    def stock_hot_deal_xq(self, symbol="最热门"):
        assert symbol == "最热门"
        return pd.DataFrame(
            [
                {"股票代码": "000100", "股票简称": "TCL科技", "排名": 9, "交易": 654},
                {"股票代码": "000001", "股票简称": "平安银行", "排名": 10, "交易": 200},
            ]
        )


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_formats_a_share_matches_by_code(monkeypatch):
    import tradingagents.dataflows.xueqiu as xueqiu

    monkeypatch.setattr(xueqiu, "_require_akshare", lambda: FakeAkshare())
    monkeypatch.setattr(xueqiu, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = xueqiu.fetch_xueqiu_hot_signals("000100.SZ")

    assert "雪球热度信号" in result
    assert "000100.SZ（TCL科技）" in result
    assert "关注榜" in result
    assert "讨论榜" in result
    assert "交易榜" in result
    assert "1888" in result
    assert "321" in result
    assert "654" in result


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_accepts_chinese_stock_name(monkeypatch):
    import tradingagents.dataflows.xueqiu as xueqiu

    monkeypatch.setattr(xueqiu, "_require_akshare", lambda: FakeAkshare())
    monkeypatch.setattr(xueqiu, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = xueqiu.fetch_xueqiu_hot_signals("TCL科技")

    assert "000100.SZ（TCL科技）" in result
    assert "关注榜" in result


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_returns_no_signal_placeholder(monkeypatch):
    import tradingagents.dataflows.xueqiu as xueqiu

    class NoMatchAkshare(FakeAkshare):
        def stock_hot_follow_xq(self, symbol="沪深股市"):
            return pd.DataFrame([{"股票代码": "000001", "股票简称": "平安银行", "排名": 1}])

        def stock_hot_tweet_xq(self, symbol="沪深股市"):
            return pd.DataFrame([{"股票代码": "000001", "股票简称": "平安银行", "排名": 2}])

        def stock_hot_deal_xq(self, symbol="沪深股市"):
            return pd.DataFrame([{"股票代码": "000001", "股票简称": "平安银行", "排名": 3}])

    monkeypatch.setattr(xueqiu, "_require_akshare", lambda: NoMatchAkshare())
    monkeypatch.setattr(xueqiu, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = xueqiu.fetch_xueqiu_hot_signals("000100.SZ")

    assert result == "<no Xueqiu hot ranking signal found for 000100.SZ（TCL科技）>"


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_returns_unavailable_placeholder_on_error(monkeypatch):
    import tradingagents.dataflows.xueqiu as xueqiu

    class BrokenAkshare(FakeAkshare):
        def stock_hot_follow_xq(self, symbol="沪深股市"):
            raise RuntimeError("xueqiu down")

    monkeypatch.setattr(xueqiu, "_require_akshare", lambda: BrokenAkshare())
    monkeypatch.setattr(xueqiu, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = xueqiu.fetch_xueqiu_hot_signals("000100.SZ")

    assert result == "<xueqiu hot signals unavailable: RuntimeError>"


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_suppresses_provider_progress_output(monkeypatch, capsys):
    import tradingagents.dataflows.xueqiu as xueqiu

    class NoisyAkshare(FakeAkshare):
        def stock_hot_follow_xq(self, symbol="最热门"):
            print("provider progress")
            return super().stock_hot_follow_xq(symbol)

    monkeypatch.setattr(xueqiu, "_require_akshare", lambda: NoisyAkshare())
    monkeypatch.setattr(xueqiu, "_stock_name_by_code", lambda: {"000100": "TCL科技"})

    result = xueqiu.fetch_xueqiu_hot_signals("000100.SZ")
    captured = capsys.readouterr()

    assert "雪球热度信号" in result
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.unit
def test_fetch_xueqiu_hot_signals_rejects_overseas_ticker():
    import tradingagents.dataflows.xueqiu as xueqiu

    result = xueqiu.fetch_xueqiu_hot_signals("AAPL")

    assert "xueqiu hot signals supports mainland A-share tickers or Chinese stock names only" in result
