import pytest

from tradingagents.dataflows.market_utils import (
    has_chinese_characters,
    is_mainland_a_share_ticker,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "ticker",
    [
        "600118.SS",
        "600118.SH",
        "000001.SZ",
        "300750",
        "430047.BJ",
    ],
)
def test_identifies_mainland_a_share_tickers(ticker):
    assert is_mainland_a_share_ticker(ticker) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "ticker",
    [
        "AAPL",
        "BRK.B",
        "0700.HK",
        "7203.T",
        "SPY",
    ],
)
def test_rejects_overseas_tickers_as_mainland_a_share(ticker):
    assert is_mainland_a_share_ticker(ticker) is False


@pytest.mark.unit
def test_identifies_chinese_names_without_treating_them_as_a_share_tickers():
    assert has_chinese_characters("贵州茅台") is True
    assert is_mainland_a_share_ticker("贵州茅台") is False
