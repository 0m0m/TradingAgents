import io
from datetime import datetime
from dateutil.relativedelta import relativedelta

import pandas as pd

from stockstats import wrap

from .market_utils import has_chinese_characters, normalize_a_share_ticker
from .stockstats_utils import _clean_dataframe


def _require_akshare():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("akshare is not installed") from exc
    return ak


def _ak_symbol(ticker: str) -> str:
    return normalize_a_share_ticker(ticker).split(".", 1)[0]


def _format_dataframe(data: pd.DataFrame, title: str) -> str:
    if data.empty:
        raise RuntimeError(f"No data returned for {title}")
    return f"# {title}\n# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{data.to_csv(index=False)}"


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    ak = _require_akshare()
    data = ak.stock_zh_a_hist(
        symbol=_ak_symbol(symbol),
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq",
    )
    return _format_dataframe(data, f"AKShare stock data for {symbol.upper()} from {start_date} to {end_date}")


def get_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    stock_data = get_stock_data(symbol, _lookback_start(curr_date, look_back_days), curr_date)
    data = pd.read_csv(io.StringIO(stock_data), comment="#")
    data = data.rename(
        columns={
            "日期": "Date",
            "开盘": "Open",
            "收盘": "Close",
            "最高": "High",
            "最低": "Low",
            "成交量": "Volume",
        }
    )
    data = data[["Date", "Open", "High", "Low", "Close", "Volume"]]
    data = _clean_dataframe(data)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)
    indicator_data = _indicator_values_by_date(df, indicator)

    ind_string = ""
    current_dt = curr_date_dt
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = indicator_data.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        ind_string += f"{date_str}: {value}\n"
        current_dt = current_dt - relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + _indicator_description(indicator)
    )


def _indicator_values_by_date(df: pd.DataFrame, indicator: str) -> dict:
    result = {}
    for _, row in df.iterrows():
        value = row[indicator]
        result[row["Date"]] = "N/A" if pd.isna(value) else str(value)
    return result


def _indicator_description(indicator: str) -> str:
    if "sma" in indicator.lower():
        return "SMA: Simple moving average. Usage: Identify trend direction and dynamic support/resistance."
    return "No description available."


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    ak = _require_akshare()
    symbol = _ak_symbol(ticker)
    try:
        data = ak.stock_individual_info_em(symbol=symbol)
        return _format_dataframe(data, f"AKShare fundamentals for {ticker.upper()}")
    except Exception:
        data = ak.stock_financial_abstract_new_ths(symbol=symbol)
        data = _recent_financial_abstract(data, curr_date)
        return _format_dataframe(data, f"AKShare financial abstract for {ticker.upper()}")


def _recent_financial_abstract(data: pd.DataFrame, curr_date: str | None) -> pd.DataFrame:
    if data.empty or "report_date" not in data.columns:
        return data

    filtered = data.copy()
    report_dates = pd.to_datetime(filtered["report_date"], errors="coerce")
    if curr_date:
        cutoff = pd.to_datetime(curr_date, errors="coerce")
        if not pd.isna(cutoff):
            filtered = filtered[report_dates <= cutoff].copy()
            report_dates = pd.to_datetime(filtered["report_date"], errors="coerce")

    latest_dates = sorted(report_dates.dropna().unique(), reverse=True)[:4]
    if not latest_dates:
        return filtered

    filtered = filtered[report_dates.isin(latest_dates)].copy()
    filtered["report_date"] = pd.to_datetime(filtered["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return filtered


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    ak = _require_akshare()
    query = ticker if has_chinese_characters(ticker) else _ak_symbol(ticker)
    data = ak.stock_news_em(symbol=query)
    data = _filter_news_by_date(data, start_date, end_date)
    return _format_dataframe(data, f"AKShare news for {ticker}")


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    raise RuntimeError("AKShare balance sheet is not available in this provider")


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    raise RuntimeError("AKShare cash flow is not available in this provider")


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    raise RuntimeError("AKShare income statement is not available in this provider")


def _filter_news_by_date(data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if data.empty:
        return data

    date_column = next((column for column in ("发布时间", "时间", "日期", "datetime", "time", "date") if column in data.columns), None)
    if date_column is None:
        return data

    dates = pd.to_datetime(data[date_column], errors="coerce")
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
    return data[(dates >= start) & (dates < end)]


def _lookback_start(curr_date: str, look_back_days: int) -> str:
    days = max(look_back_days * 2, 260)
    return (pd.Timestamp(curr_date) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
