from __future__ import annotations

import contextlib
import io
import re
from functools import lru_cache
from typing import Any

from .market_utils import has_chinese_characters, is_mainland_a_share_ticker, normalize_a_share_ticker

_MARKET = "最热门"
_RANKINGS = (
    ("关注榜", "stock_hot_follow_xq"),
    ("讨论榜", "stock_hot_tweet_xq"),
    ("交易榜", "stock_hot_deal_xq"),
)
_CODE_KEYS = ("股票代码", "代码", "证券代码", "symbol", "code")
_NAME_KEYS = ("股票简称", "名称", "证券简称", "name")


def fetch_xueqiu_hot_signals(symbol: str) -> str:
    identity = _resolve_a_share_identity(symbol)
    if not identity["supported"]:
        return "<xueqiu hot signals supports mainland A-share tickers or Chinese stock names only>"

    try:
        ak = _require_akshare()
        sections = []
        for title, method_name in _RANKINGS:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                frame = getattr(ak, method_name)(_MARKET)
            rows = _filter_target_rows(frame, identity)
            if rows:
                sections.append((title, rows))
    except Exception as exc:
        return f"<xueqiu hot signals unavailable: {type(exc).__name__}>"

    if not sections:
        return f"<no Xueqiu hot ranking signal found for {_identity_label(identity)}>"
    return _format_xueqiu_signals(identity, sections)


def _require_akshare():
    import akshare as ak

    return ak


def _resolve_a_share_identity(symbol: str) -> dict[str, Any]:
    raw = str(symbol).strip()

    if is_mainland_a_share_ticker(raw):
        normalized = normalize_a_share_ticker(raw)
        code, suffix = normalized.split(".", 1)
        name = _stock_name_by_code().get(code, "")
        return {
            "supported": True,
            "raw": raw,
            "code": code,
            "ticker": _display_ticker(code, suffix),
            "name": name,
        }

    if has_chinese_characters(raw):
        for code, name in _stock_name_by_code().items():
            if name == raw:
                suffix = _infer_exchange_suffix(code)
                return {
                    "supported": True,
                    "raw": raw,
                    "code": code,
                    "ticker": _display_ticker(code, suffix),
                    "name": name,
                }

    return {"supported": False, "raw": raw}


@lru_cache(maxsize=1)
def _stock_name_by_code() -> dict[str, str]:
    try:
        ak = _require_akshare()
    except Exception:
        return {}

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rows = ak.stock_info_a_code_name()
    except Exception:
        return {}

    names: dict[str, str] = {}
    for row in rows.to_dict("records"):
        code = str(row.get("code", row.get("证券代码", row.get("股票代码", "")))).strip()
        name = str(row.get("name", row.get("证券简称", row.get("股票简称", "")))).strip()
        if len(code) == 6 and name:
            names[code] = name
    return names


def _filter_target_rows(frame, identity: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dict("records"):
        if _matches_identity(row, identity):
            rows.append(row)
    return rows


def _matches_identity(row: dict[str, Any], identity: dict[str, Any]) -> bool:
    code = str(identity.get("code") or "")
    name = str(identity.get("name") or identity.get("raw") or "")

    for key in _CODE_KEYS:
        if _extract_code(row.get(key)) == code:
            return True

    for key in _NAME_KEYS:
        if str(row.get(key) or "").strip() == name:
            return True

    return False


def _extract_code(value: object) -> str:
    match = re.search(r"\d{6}", str(value or ""))
    return match.group(0) if match else ""


def _format_xueqiu_signals(identity: dict[str, Any], sections: list[tuple[str, list[dict[str, Any]]]]) -> str:
    lines = [
        f"## 雪球热度信号 — {_identity_label(identity)}",
        "",
        "These are Xueqiu hot-ranking and attention proxy signals, not full community post text.",
    ]
    for title, rows in sections:
        lines.extend(["", f"### {title}"])
        for row in rows:
            fields = _format_row_fields(row)
            if fields:
                lines.append(f"- {' · '.join(fields)}")
    return "\n".join(lines)


def _format_row_fields(row: dict[str, Any]) -> list[str]:
    fields = []
    for key, value in row.items():
        if key in _CODE_KEYS or key in _NAME_KEYS or _blank(value):
            continue
        fields.append(f"{key} {value}")
    return fields


def _blank(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip() in {"", "nan", "NaN", "None"}


def _identity_label(identity: dict[str, Any]) -> str:
    ticker = str(identity.get("ticker") or identity.get("raw") or "")
    name = str(identity.get("name") or "")
    return f"{ticker}（{name}）" if name else ticker


def _display_ticker(code: str, suffix: str) -> str:
    return f"{code}.SS" if suffix == "SH" else f"{code}.{suffix}"


def _infer_exchange_suffix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"
