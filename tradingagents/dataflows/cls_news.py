"""Direct CLS/Cailian Press news access."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

_CLS_API_BASE = "https://api3.cls.cn"
_CLS_APP = "CailianpressWeb"
_CLS_OS = "web"
_CLS_SV = "8.4.6"


class ClsNewsError(RuntimeError):
    pass


def get_cls_kuaixun_records(limit: int = 20, last_time: int | None = None, timeout: int = 10) -> list[dict[str, Any]]:
    payload = _fetch_cls_roll_list(limit=limit, last_time=last_time, timeout=timeout)
    return [_normalize_cls_roll_record(item) for item in payload if isinstance(item, dict)]


def _fetch_cls_roll_list(limit: int = 20, last_time: int | None = None, timeout: int = 10) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 50))
    params: dict[str, Any] = {
        "app": _CLS_APP,
        "category": "telegraph",
        "last_time": int(last_time if last_time is not None else time.time()),
        "os": _CLS_OS,
        "refresh_type": 1,
        "rn": safe_limit,
        "sv": _CLS_SV,
    }
    params["sign"] = _cls_sign(params)
    url = f"{_CLS_API_BASE}/v1/roll/get_roll_list?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "TradingAgents/1.0"})

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except OSError as exc:
        raise ClsNewsError(f"CLS request failed: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ClsNewsError("CLS returned invalid JSON") from exc

    if str(data.get("errno")) != "0":
        raise ClsNewsError(f"CLS API error: {data.get('msg') or data.get('errno')}")

    roll_data = data.get("data", {}).get("roll_data", [])
    if not isinstance(roll_data, list):
        return []
    return roll_data


def _normalize_cls_roll_record(raw: dict[str, Any]) -> dict[str, Any]:
    content = str(raw.get("content") or raw.get("brief") or "").strip()
    title = str(raw.get("title") or raw.get("brief") or content or "No title").strip()
    record_id = raw.get("id")

    return {
        "title": title,
        "summary": content if content != title else "",
        "time": _format_cls_time(raw.get("ctime")),
        "source": "cls_kuaixun",
        "url": f"https://www.cls.cn/detail/{record_id}" if record_id else None,
        "stocks": _extract_cls_stocks(raw),
    }


def _format_cls_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return (datetime.fromtimestamp(int(value), tz=timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return str(value).strip() or None


def _extract_cls_stocks(raw: dict[str, Any]) -> list[str]:
    stocks = []
    for key in ("stocks", "stock", "symbols", "secu_codes"):
        value = raw.get(key)
        if isinstance(value, str):
            stocks.extend(item.strip() for item in value.replace("，", ",").split(",") if item.strip())
        elif isinstance(value, list):
            stocks.extend(_stock_value(item) for item in value)
    return [stock for stock in stocks if stock]


def _stock_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("secu_code", "symbol", "code", "stock_code", "name"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value).strip()


def _cls_sign(params: dict[str, Any]) -> str:
    sha1_hex = hashlib.sha1(_cls_canonical_query(params).encode("utf-8")).hexdigest()
    return hashlib.md5(sha1_hex.encode("utf-8")).hexdigest()


def _cls_canonical_query(params: dict[str, Any]) -> str:
    return "&".join(
        part
        for key in sorted(params)
        for part in [_cls_canonical_part(key, params[key])]
        if part
    )


def _cls_canonical_part(key: str, value: Any) -> str:
    encoded_key = quote(str(key), safe="")
    if value is None:
        return f"{encoded_key}=None"
    if isinstance(value, bool):
        return f"{encoded_key}={str(value).lower()}"
    if isinstance(value, (str, int, float)):
        return f"{encoded_key}={quote(str(value), safe='')}"
    if isinstance(value, list):
        if not value:
            return quote(f"{key}[]", safe="")
        return "&".join(_cls_canonical_part(f"{key}[{index}]", item) for index, item in enumerate(value))
    if isinstance(value, dict):
        return "&".join(_cls_canonical_part(f"{key}[{child_key}]", value[child_key]) for child_key in sorted(value))
    return f"{encoded_key}={quote(str(value), safe='')}"
