from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path


DEFAULT_SHALLOW_THINKER = "MiniMax-M2.7"
DEFAULT_DEEP_THINKER = "gpt-5.5"


_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")
_ANALYSIS_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRADINGAGENTS_REPO_ROOT = Path(__file__).resolve().parents[1]


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"ticker must be a non-empty string, got {value!r}")
    if len(value) > max_len:
        raise ValueError(f"ticker exceeds {max_len} chars: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"ticker contains characters not allowed in a filesystem path: {value!r}"
        )
    if set(value) == {"."}:
        raise ValueError(f"ticker cannot consist solely of dots: {value!r}")
    return value


def safe_analysis_date(value: str) -> str:
    if not isinstance(value, str) or not _ANALYSIS_DATE_RE.fullmatch(value):
        raise ValueError(f"analysis_date must match YYYY-MM-DD, got {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"analysis_date must be a valid calendar date, got {value!r}"
        ) from exc
    return value


def build_run_context(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str = "Chinese",
    timestamp: str = "20260509_000000",
) -> dict[str, object]:
    safe_ticker = safe_ticker_component(ticker)
    validated_analysis_date = safe_analysis_date(analysis_date)
    report_dir = (
        TRADINGAGENTS_REPO_ROOT
        / "reports"
        / validated_analysis_date
        / f"{safe_ticker}_{timestamp}"
    )
    command = [
        "uv",
        "run",
        "tradingagents",
        "--shallow-thinker",
        shallow_model,
        "--deep-thinker",
        deep_model,
        "--ticker",
        safe_ticker,
        "--analysis-date",
        validated_analysis_date,
        "--output-language",
        output_language,
    ]
    stdin_text = f"Y\n{report_dir}\nN\n"
    return {
        "command": command,
        "stdin_text": stdin_text,
        "report_dir": report_dir,
        "tradingagents_root": TRADINGAGENTS_REPO_ROOT,
    }


def run_tradingagents_daily(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str = "Chinese",
) -> dict[str, object]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    context = build_run_context(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
        shallow_model=shallow_model,
        deep_model=deep_model,
        output_language=output_language,
        timestamp=timestamp,
    )
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    completed = subprocess.run(
        context["command"],
        input=context["stdin_text"],
        cwd=context["tradingagents_root"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=env,
    )
    return {
        **context,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(TRADINGAGENTS_REPO_ROOT))
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument(
        "--shallow-thinker",
        dest="shallow_model",
        default=DEFAULT_SHALLOW_THINKER,
    )
    parser.add_argument(
        "--deep-thinker",
        dest="deep_model",
        default=DEFAULT_DEEP_THINKER,
    )
    parser.add_argument("--output-language", default="Chinese")
    args = parser.parse_args(argv)

    result = run_tradingagents_daily(
        repo_root=Path(args.repo_root),
        ticker=args.ticker,
        analysis_date=args.analysis_date,
        shallow_model=args.shallow_model,
        deep_model=args.deep_model,
        output_language=args.output_language,
    )
    payload = {
        key: (str(value) if isinstance(value, Path) else value)
        for key, value in result.items()
    }
    payload.update(
        {
            "report_dir": str(result["report_dir"]),
            "ticker": args.ticker,
            "analysis_date": args.analysis_date,
            "shallow_model": args.shallow_model,
            "deep_model": args.deep_model,
        }
    )
    print(json.dumps(payload, ensure_ascii=False))
    return int(result["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
