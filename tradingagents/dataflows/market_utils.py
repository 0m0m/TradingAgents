import re

_A_SHARE_SUFFIXES = {"SS", "SH", "SZ", "BJ"}
_A_SHARE_RE = re.compile(r"^(?P<digits>\d{6})(?:\.(?P<suffix>[A-Za-z]{2}))?$")
_CHINESE_RE = re.compile(r"[一-鿿]")


def has_chinese_characters(value: str | None) -> bool:
    if not value:
        return False
    return _CHINESE_RE.search(str(value)) is not None


def is_mainland_a_share_ticker(ticker: str | None) -> bool:
    if not ticker:
        return False

    normalized = str(ticker).strip().upper()
    match = _A_SHARE_RE.match(normalized)
    if not match:
        return False

    suffix = match.group("suffix")
    return suffix is None or suffix in _A_SHARE_SUFFIXES


def normalize_a_share_ticker(ticker: str) -> str:
    if not is_mainland_a_share_ticker(ticker):
        raise ValueError("mainland A-share data sources support mainland A-share tickers only")

    normalized = str(ticker).strip().upper()
    digits = normalized.split(".", 1)[0]
    suffix = normalized.split(".", 1)[1] if "." in normalized else _infer_exchange_suffix(digits)

    if suffix == "SS":
        suffix = "SH"

    return f"{digits}.{suffix}"


def _infer_exchange_suffix(digits: str) -> str:
    if digits.startswith(("6", "9")):
        return "SH"
    if digits.startswith(("4", "8")):
        return "BJ"
    return "SZ"
