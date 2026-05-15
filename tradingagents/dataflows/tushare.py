import os
from datetime import datetime

import pandas as pd

from .market_utils import normalize_a_share_ticker


def _require_tushare():
    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("tushare is not installed") from exc

    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set")

    ts.set_token(token)
    return ts.pro_api()


def _ts_code(ticker: str) -> str:
    normalized = normalize_a_share_ticker(ticker)
    digits, suffix = normalized.split(".", 1)
    return f"{digits}.{suffix}"


def _format_dataframe(data: pd.DataFrame, title: str) -> str:
    if data.empty:
        raise RuntimeError(f"No data returned for {title}")
    return f"# {title}\n# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{data.to_csv(index=False)}"


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    pro = _require_tushare()
    data = pro.daily(
        ts_code=_ts_code(symbol),
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
    )
    return _format_dataframe(data, f"Tushare stock data for {symbol.upper()} from {start_date} to {end_date}")


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    pro = _require_tushare()
    ts_code = _ts_code(ticker)
    stock_basic = pro.stock_basic(ts_code=ts_code, fields="ts_code,symbol,name,area,industry,market,list_date")
    daily_basic = pro.daily_basic(ts_code=ts_code, trade_date=curr_date.replace("-", "") if curr_date else None)

    sections = [f"# Tushare fundamentals for {ticker.upper()}"]
    if not stock_basic.empty:
        sections.append("## Stock Basic\n" + stock_basic.to_csv(index=False))
    if not daily_basic.empty:
        sections.append("## Daily Basic\n" + daily_basic.to_csv(index=False))
    if len(sections) == 1:
        raise RuntimeError(f"No fundamentals data returned for {ticker}")
    return "\n\n".join(sections)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    pro = _require_tushare()
    data = pro.balancesheet(ts_code=_ts_code(ticker), **_statement_date_range(curr_date))
    return _format_dataframe(data, f"Tushare balance sheet for {ticker.upper()} ({freq})")


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    pro = _require_tushare()
    data = pro.cashflow(ts_code=_ts_code(ticker), **_statement_date_range(curr_date))
    return _format_dataframe(data, f"Tushare cash flow for {ticker.upper()} ({freq})")


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    pro = _require_tushare()
    data = pro.income(ts_code=_ts_code(ticker), **_statement_date_range(curr_date))
    return _format_dataframe(data, f"Tushare income statement for {ticker.upper()} ({freq})")


def _statement_date_range(curr_date: str | None) -> dict:
    if not curr_date:
        return {}
    end_date = pd.Timestamp(curr_date)
    start_date = end_date - pd.DateOffset(years=1)
    return {
        "start_date": start_date.strftime("%Y%m%d"),
        "end_date": end_date.strftime("%Y%m%d"),
    }
