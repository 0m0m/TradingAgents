import pandas as pd
import pytest


@pytest.mark.unit
def test_akshare_fundamentals_falls_back_to_recent_financial_abstract(monkeypatch):
    import tradingagents.dataflows.akshare as akshare_provider

    class FakeAkshare:
        def stock_individual_info_em(self, symbol):
            raise RuntimeError("Eastmoney 502 Bad Gateway")

        def stock_financial_abstract_new_ths(self, symbol):
            return pd.DataFrame(
                [
                    {"report_date": "2026-06-30", "metric_name": "future_metric", "value": 999},
                    {"report_date": "2026-03-31", "metric_name": "revenue", "value": 100},
                    {"report_date": "2025-12-31", "metric_name": "net_profit", "value": 90},
                    {"report_date": "2025-09-30", "metric_name": "gross_margin", "value": 80},
                    {"report_date": "2025-06-30", "metric_name": "cash_flow", "value": 70},
                    {"report_date": "2025-03-31", "metric_name": "old_metric", "value": 60},
                ]
            )

    monkeypatch.setattr(akshare_provider, "_require_akshare", lambda: FakeAkshare())

    result = akshare_provider.get_fundamentals("000100.SZ", curr_date="2026-05-30")

    assert "AKShare financial abstract for 000100.SZ" in result
    assert "revenue" in result
    assert "2026-06-30" not in result
    assert "2025-03-31" not in result


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "property_name", "fallback_result"),
    [
        ("get_balance_sheet", "quarterly_balance_sheet", "alpha balance sheet"),
        ("get_cashflow", "quarterly_cashflow", "alpha cashflow"),
        ("get_income_statement", "quarterly_income_stmt", "alpha income statement"),
    ],
)
def test_route_to_vendor_falls_back_when_yfinance_financial_statement_fails(
    monkeypatch, method, property_name, fallback_result
):
    import tradingagents.dataflows.interface as interface
    import tradingagents.dataflows.y_finance as y_finance

    class BrokenTicker:
        def __getattribute__(self, name):
            if name == property_name:
                raise RuntimeError("upstream TLS failed")
            return super().__getattribute__(name)

    monkeypatch.setattr(y_finance.yf, "Ticker", lambda ticker: BrokenTicker())
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setattr(
        interface,
        "load_cached_vendor_result",
        lambda method, vendor, args, kwargs: None,
    )
    saved = []

    def fake_save(method, vendor, args, kwargs, result):
        saved.append((vendor, result))

    monkeypatch.setattr(interface, "save_cached_vendor_result", fake_save)
    monkeypatch.setitem(
        interface.VENDOR_METHODS[method],
        "alpha_vantage",
        lambda *args, **kwargs: fallback_result,
    )

    result = interface.route_to_vendor(method, "AAPL", curr_date="2026-05-12")

    assert result == fallback_result
    assert saved == [("alpha_vantage", fallback_result)]


def test_route_to_vendor_falls_back_when_yfinance_insider_transactions_fails(monkeypatch):
    import tradingagents.dataflows.interface as interface
    import tradingagents.dataflows.y_finance as y_finance

    class BrokenTicker:
        @property
        def insider_transactions(self):
            raise RuntimeError("upstream TLS failed")

    monkeypatch.setattr(y_finance.yf, "Ticker", lambda ticker: BrokenTicker())
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setattr(
        interface,
        "load_cached_vendor_result",
        lambda method, vendor, args, kwargs: None,
    )
    saved = []

    def fake_save(method, vendor, args, kwargs, result):
        saved.append((vendor, result))

    monkeypatch.setattr(interface, "save_cached_vendor_result", fake_save)
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_insider_transactions"],
        "alpha_vantage",
        lambda *args, **kwargs: "alpha insider transactions",
    )

    result = interface.route_to_vendor("get_insider_transactions", "AAPL")

    assert result == "alpha insider transactions"
    assert saved == [("alpha_vantage", "alpha insider transactions")]
