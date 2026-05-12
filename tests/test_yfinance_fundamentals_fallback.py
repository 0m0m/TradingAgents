import pytest


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
