from __future__ import annotations

from functools import lru_cache


TICKER_NAME_OVERRIDES = {
    "000913.SZ": "钱江摩托",
    "002179.SZ": "中航光电",
    "002332.SZ": "仙琚制药",
    "300315.SZ": "掌趣科技",
    "300318.SZ": "博晖创新",
    "302132.SZ": "中航成飞",
    "600104.SS": "上汽集团",
    "600900.SS": "长江电力",
    "601611.SS": "中国核建",
    "601698.SS": "中国卫通",
    "601857.SS": "中国石油",
    "601899.SS": "紫金矿业",
    "603281.SS": "江瀚新材",
}

@lru_cache(maxsize=1)
def _stock_name_by_ticker() -> dict[str, str]:
    try:
        import akshare as ak
    except Exception:
        return {}

    try:
        rows = ak.stock_info_a_code_name()
    except Exception:
        return {}

    names: dict[str, str] = {}
    for row in rows.to_dict("records"):
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        if not code or not name:
            continue
        if code.startswith(("6", "9")):
            names[f"{code}.SS"] = name
        elif code.startswith(("0", "2", "3")):
            names[f"{code}.SZ"] = name
        names[code] = name
    return names


def pinyin_initials(name: str) -> str:
    try:
        from pypinyin import Style, lazy_pinyin
    except Exception:
        return ""

    return "".join(
        part.upper()
        for part in lazy_pinyin(name, style=Style.FIRST_LETTER)
        if part
    )


def ticker_name(ticker: str) -> str:
    normalized = ticker.strip().upper()
    return TICKER_NAME_OVERRIDES.get(normalized, _stock_name_by_ticker().get(normalized, ""))


def ticker_display(row: dict[str, str]) -> str:
    ticker = row.get("ticker", "")
    name = row.get("ticker_name", "") or row.get("stock_name", "") or ticker_name(ticker)
    abbreviation = row.get("ticker_pinyin_abbr", "") or pinyin_initials(name)
    if not ticker:
        return ""
    if name and abbreviation:
        return f"{ticker}（{name} / {abbreviation}）"
    if name:
        return f"{ticker}（{name}）"
    if abbreviation:
        return f"{ticker}（{abbreviation}）"
    return ticker
