from datetime import datetime

import pandas as pd
import pytest
from stockstats import wrap

from tradingagents.dataflows import akshare, tushare


@pytest.mark.unit
def test_akshare_indicator_fetches_enough_history_for_long_window(monkeypatch):
    captured = {}

    def fake_stock_data(symbol, start_date, end_date):
        captured["symbol"] = symbol
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return "# test\n\nDate,Open,High,Low,Close,Volume\n2026-05-15,1,1,1,1,100\n"

    monkeypatch.setattr(akshare, "get_stock_data", fake_stock_data)

    akshare.get_indicators("600519.SH", "close", "2026-05-15", 30)

    fetched_days = (datetime.strptime(captured["end_date"], "%Y-%m-%d") - datetime.strptime(captured["start_date"], "%Y-%m-%d")).days
    assert fetched_days >= 260


@pytest.mark.unit
def test_akshare_indicator_calculates_from_akshare_dataframe(monkeypatch):
    data = pd.DataFrame(
        {
            "Date": pd.date_range("2026-05-11", periods=5, freq="D").strftime("%Y-%m-%d"),
            "Open": [1, 2, 3, 4, 5],
            "High": [1, 2, 3, 4, 5],
            "Low": [1, 2, 3, 4, 5],
            "Close": [1, 2, 3, 4, 5],
            "Volume": [100, 100, 100, 100, 100],
        }
    )
    csv = "# test\n\n" + data.to_csv(index=False)

    monkeypatch.setattr(akshare, "get_stock_data", lambda *args: csv)

    result = akshare.get_indicators("600519.SH", "close_3_sma", "2026-05-15", 4)

    expected = wrap(data)["close_3_sma"].iloc[-1]
    assert f"2026-05-15: {expected}" in result


@pytest.mark.unit
def test_akshare_indicator_returns_lookback_window_series(monkeypatch):
    data = pd.DataFrame(
        {
            "Date": pd.date_range("2026-05-11", periods=5, freq="D").strftime("%Y-%m-%d"),
            "Open": [1, 2, 3, 4, 5],
            "High": [1, 2, 3, 4, 5],
            "Low": [1, 2, 3, 4, 5],
            "Close": [1, 2, 3, 4, 5],
            "Volume": [100, 100, 100, 100, 100],
        }
    )
    csv = "# test\n\n" + data.to_csv(index=False)

    monkeypatch.setattr(akshare, "get_stock_data", lambda *args: csv)

    result = akshare.get_indicators("600519.SH", "close_3_sma", "2026-05-15", 2)

    assert "## close_3_sma values from 2026-05-13 to 2026-05-15:" in result
    assert "2026-05-15:" in result
    assert "2026-05-14:" in result
    assert "2026-05-13:" in result
    assert "SMA" in result


@pytest.mark.unit
def test_akshare_news_filters_by_requested_date_range(monkeypatch):
    class FakeAk:
        @staticmethod
        def stock_news_em(symbol):
            return pd.DataFrame(
                [
                    {"关键词": symbol, "新闻标题": "old", "发布时间": "2026-05-01 09:00:00"},
                    {"关键词": symbol, "新闻标题": "inside", "发布时间": "2026-05-10 09:00:00"},
                    {"关键词": symbol, "新闻标题": "new", "发布时间": "2026-05-20 09:00:00"},
                ]
            )

    monkeypatch.setattr(akshare, "_require_akshare", lambda: FakeAk)

    result = akshare.get_news("600519.SH", "2026-05-08", "2026-05-12")

    assert "inside" in result
    assert "old," not in result
    assert "new," not in result


@pytest.mark.unit
def test_tushare_financial_statements_use_announcement_date_range_instead_of_trade_date_period(monkeypatch):
    calls = []

    class FakePro:
        def balancesheet(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame([{"ts_code": "600519.SH"}])

    monkeypatch.setattr(tushare, "_require_tushare", lambda: FakePro())

    tushare.get_balance_sheet("600519.SH", curr_date="2026-05-15")

    assert calls == [
        {
            "ts_code": "600519.SH",
            "start_date": "20250515",
            "end_date": "20260515",
        }
    ]
