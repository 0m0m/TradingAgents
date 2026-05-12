"""
复现并验证 fundamentals 在 yfinance TLS 失败场景下的 fallback 行为（可稳定复现）。

运行方式（PowerShell）：
python scripts/repro_fundamentals_tls_fallback.py
"""


def yfinance_fundamentals(_ticker: str, _curr_date: str) -> str:
    # 模拟你遇到的 TLS/OpenSSL 异常
    raise RuntimeError(
        "Failed to perform, curl: (35) TLS connect error: "
        "error:00000000:invalid library (0):OPENSSL_internal:invalid library (0)"
    )


def alpha_vantage_fundamentals(ticker: str, _curr_date: str) -> str:
    return f"fallback success from alpha_vantage for {ticker}"


def route_to_vendor_before_fix(method: str, *args):
    """模拟修复前：只在限流错误时 fallback，其它异常直接失败。"""
    if method != "get_fundamentals":
        raise ValueError("unsupported method")

    vendors = [yfinance_fundamentals, alpha_vantage_fundamentals]
    for impl in vendors:
        try:
            return impl(*args)
        except Exception as e:
            # 修复前行为：非限流异常不降级，直接抛出
            raise RuntimeError(f"before-fix failed fast: {e}") from e


def route_to_vendor_after_fix(method: str, *args):
    """模拟修复后：任意供应商异常都继续 fallback。"""
    if method != "get_fundamentals":
        raise ValueError("unsupported method")

    vendors = [yfinance_fundamentals, alpha_vantage_fundamentals]
    last_error = None
    for impl in vendors:
        try:
            return impl(*args)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"after-fix all vendors failed: {last_error}") from last_error


def main() -> None:
    ticker = "600118.SS"
    curr_date = "2026-05-08"

    print("=== 1) 先复现（修复前行为）===")
    try:
        result_before = route_to_vendor_before_fix("get_fundamentals", ticker, curr_date)
        print("UNEXPECTED SUCCESS:", result_before)
    except Exception as e:
        print("EXPECTED FAILURE:")
        print(e)

    print("\n=== 2) 再验证修复后行为 ===")
    result_after = route_to_vendor_after_fix("get_fundamentals", ticker, curr_date)
    print("EXPECTED SUCCESS:")
    print(result_after)


if __name__ == "__main__":
    main()
