import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import get_config


_CACHE_VERSION = "v2"


def _normalize_for_key(value: Any) -> Any:
    """Convert values into a deterministic, JSON-serializable structure."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_for_key(v) for v in value]
    if isinstance(value, dict):
        return {
            str(k): _normalize_for_key(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    return repr(value)


def _cache_root() -> Path:
    cfg = get_config()
    data_cache_dir = cfg.get("data_cache_dir")
    root = Path(data_cache_dir) / "vendor_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_cache_key(
    method: str, vendor: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    payload = {
        "version": _CACHE_VERSION,
        "method": method,
        "vendor": vendor,
        "args": _normalize_for_key(args),
        "kwargs": _normalize_for_key(kwargs),
    }
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_date_value(args: tuple[Any, ...], kwargs: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = kwargs.get(name)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]

    # Best-effort positional fallback for common signatures:
    # get_stock_data(symbol, start_date, end_date)
    if "end_date" in names and len(args) >= 3 and isinstance(args[2], str):
        return args[2][:10]
    # get_indicators(symbol, indicator, curr_date, look_back_days)
    if "curr_date" in names and len(args) >= 3 and isinstance(args[2], str):
        return args[2][:10]

    return None


def _is_recent_date(date_str: str) -> bool:
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return False
    today = datetime.now().date()
    # 当请求包含今天/昨天的数据时，优先刷新避免缓存不完整
    return (today - day).days <= 1


def _should_bypass_cache(method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    # 对“会持续更新”的近实时请求，如果日期非常新，强制走新请求并覆盖缓存
    dynamic_methods = {"get_stock_data", "get_indicators", "get_news", "get_global_news"}
    if method not in dynamic_methods:
        return False

    date_hint = _find_date_value(args, kwargs, ("end_date", "curr_date", "start_date"))
    if not date_hint:
        return False
    return _is_recent_date(date_hint)


def load_cached_vendor_result(
    method: str, vendor: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any | None:
    """Load cached vendor result if present; return None when cache miss or bypass is required."""
    if _should_bypass_cache(method, args, kwargs):
        return None

    key = _build_cache_key(method, vendor, args, kwargs)
    file_path = _cache_root() / f"{key}.json"
    if not file_path.exists():
        return None

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return payload.get("result")
    except Exception:
        return None


def save_cached_vendor_result(
    method: str,
    vendor: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: Any,
) -> None:
    """Persist vendor result to cache; silently skip if result is not JSON-serializable."""
    key = _build_cache_key(method, vendor, args, kwargs)
    file_path = _cache_root() / f"{key}.json"

    payload = {
        "method": method,
        "vendor": vendor,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }

    try:
        encoded = json.dumps(payload, ensure_ascii=False)
    except TypeError:
        return

    file_path.write_text(encoded, encoding="utf-8")
