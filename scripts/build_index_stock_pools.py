from __future__ import annotations

import argparse
import contextlib
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import pandas as pd


DEFAULT_EXCLUDED_INDUSTRIES = {"银行", "房地产"}
DEFAULT_BATCH_SIZE = 21
INDEX_CONFIGS = [
    {
        "symbol": "000300",
        "name": "hs300",
        "display_name": "沪深300",
        "csv_name": "hs300_ex_fin_realestate.csv",
        "unmatched_name": "hs300_ex_fin_realestate_unmatched.csv",
    },
    {
        "symbol": "000905",
        "name": "csi500",
        "display_name": "中证500",
        "csv_name": "csi500_ex_fin_realestate.csv",
        "unmatched_name": "csi500_ex_fin_realestate_unmatched.csv",
    },
]


def first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for name in candidates:
        if name in df.columns:
            return name
    raise RuntimeError(f"missing expected columns {candidates}; got {list(df.columns)}")


def normalize_code(value: object) -> str:
    code = re.sub(r"\D", "", str(value))
    if len(code) != 6:
        raise RuntimeError(f"invalid A-share code: {value!r}")
    return code


def to_ticker(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"{code}.SS"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    raise RuntimeError(f"unsupported exchange prefix for code: {code}")


@contextlib.contextmanager
def sws_tls_bypass(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return

    import requests
    import urllib3

    original_get = requests.get

    def get_with_limited_bypass(url: object, *args: object, **kwargs: object):
        host = urlparse(str(url)).hostname or ""
        if host == "www.swsresearch.com" or host.endswith(".swsresearch.com"):
            kwargs.setdefault("verify", False)
        return original_get(url, *args, **kwargs)

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    requests.get = get_with_limited_bypass
    try:
        yield
    finally:
        requests.get = original_get


def load_primary_industry(allow_sws_tls_bypass: bool = False) -> pd.DataFrame:
    import akshare as ak

    with sws_tls_bypass(allow_sws_tls_bypass):
        first_info = ak.sw_index_first_info()
    industry_code_col = first_existing_column(first_info, ["行业代码"])
    industry_name_col = first_existing_column(first_info, ["行业名称"])

    frames: list[pd.DataFrame] = []
    for row in first_info.to_dict("records"):
        industry_symbol = str(row[industry_code_col]).split(".", 1)[0]
        industry_name = str(row[industry_name_col]).strip()
        with sws_tls_bypass(allow_sws_tls_bypass):
            components = ak.index_component_sw(symbol=industry_symbol)
        code_col = first_existing_column(components, ["证券代码", "股票代码", "代码"])
        frame = components[[code_col]].copy()
        frame["code"] = frame[code_col].map(normalize_code)
        frame["industry_level1"] = industry_name
        frame["industry_level2"] = ""
        frame["industry_source"] = "akshare.sw_index_first_info+index_component_sw"
        frames.append(frame[["code", "industry_level1", "industry_level2", "industry_source"]])

    industry = pd.concat(frames, ignore_index=True)
    duplicates = industry[industry["code"].duplicated(keep=False)].sort_values("code")
    if not duplicates.empty:
        duplicate_codes = sorted(duplicates["code"].unique().tolist())[:20]
        raise RuntimeError(
            f"[blocked] duplicate stock codes across Shenwan first-level industries: {duplicate_codes}"
        )
    return industry


def fallback_industry(code: str) -> dict[str, str] | None:
    import akshare as ak

    history = ak.stock_industry_change_cninfo(
        symbol=code,
        start_date="19900101",
        end_date="20260601",
    )
    if history.empty:
        return None
    history = history.copy()
    history["分类标准"] = history["分类标准"].astype(str)
    candidates = history[
        history["分类标准"].str.contains("申银万国行业分类标准", na=False)
        & ~history["分类标准"].str.contains("旧", na=False)
    ]
    if candidates.empty:
        return None
    row = candidates.sort_values("变更日期").iloc[-1]
    level1 = str(row.get("行业门类", "")).strip()
    level2 = str(row.get("行业大类", "")).strip()
    if not level1 or level1.lower() == "nan":
        return None
    return {
        "code": code,
        "industry_level1": level1,
        "industry_level2": "" if level2.lower() == "nan" else level2,
        "industry_source": "akshare.stock_industry_change_cninfo",
    }


def load_constituents(symbol: str) -> pd.DataFrame:
    import akshare as ak

    constituents = ak.index_stock_cons_csindex(symbol=symbol)
    code_col = first_existing_column(
        constituents,
        ["成分券代码", "品种代码", "证券代码", "代码", "con_code"],
    )
    name_col = first_existing_column(
        constituents,
        ["成分券名称", "品种名称", "证券简称", "名称", "name"],
    )
    constituents = constituents[[code_col, name_col]].copy()
    constituents["code"] = constituents[code_col].map(normalize_code)
    constituents["name"] = constituents[name_col].astype(str).str.strip()
    return constituents[["code", "name"]].drop_duplicates("code")


def attach_industry(
    constituents: pd.DataFrame,
    industry: pd.DataFrame,
    index_name: str,
    unmatched_path: Path | None = None,
) -> pd.DataFrame:
    merged = constituents.merge(industry, on="code", how="left")
    missing_mask = merged["industry_level1"].isna() | (
        merged["industry_level1"].astype(str).str.strip() == ""
    )
    missing_codes = merged.loc[missing_mask, "code"].tolist()
    if not missing_codes:
        return merged

    fallback_rows: list[dict[str, str]] = []
    unresolved: list[str] = []
    for code in missing_codes:
        fallback = fallback_industry(code)
        if fallback is None:
            unresolved.append(code)
        else:
            fallback_rows.append(fallback)

    if unresolved:
        unresolved_rows = merged[merged["code"].isin(unresolved)]
        if unmatched_path is not None:
            unmatched_path.parent.mkdir(parents=True, exist_ok=True)
            unresolved_rows.to_csv(unmatched_path, index=False, encoding="utf-8-sig")
        raise RuntimeError(
            f"[blocked] {len(unresolved)} {index_name} constituents have no industry mapping"
        )

    fallback_df = pd.DataFrame(fallback_rows)
    return constituents.merge(
        pd.concat([industry, fallback_df], ignore_index=True),
        on="code",
        how="left",
    )


def build_stock_pool(
    constituents: pd.DataFrame,
    industry: pd.DataFrame,
    index_symbol: str,
    index_name: str,
    analysis_date: str,
    generated_at: str,
    excluded_industries: set[str] | None = None,
    unmatched_path: Path | None = None,
) -> pd.DataFrame:
    excluded = excluded_industries or DEFAULT_EXCLUDED_INDUSTRIES
    merged = constituents.merge(industry, on="code", how="left")
    missing = merged[
        merged["industry_level1"].isna()
        | (merged["industry_level1"].astype(str).str.strip() == "")
    ]
    if not missing.empty:
        if unmatched_path is not None:
            unmatched_path.parent.mkdir(parents=True, exist_ok=True)
            missing.to_csv(unmatched_path, index=False, encoding="utf-8-sig")
        raise RuntimeError(
            f"[blocked] {len(missing)} {index_name} constituents have no industry mapping"
        )

    filtered = merged[~merged["industry_level1"].isin(excluded)].copy()
    filtered["ticker"] = filtered["code"].map(to_ticker)
    filtered["index_symbol"] = index_symbol
    filtered["index_name"] = index_name
    filtered["analysis_date"] = analysis_date
    filtered["generated_at"] = generated_at
    filtered = filtered[
        [
            "ticker",
            "code",
            "name",
            "industry_level1",
            "industry_level2",
            "industry_source",
            "index_symbol",
            "index_name",
            "analysis_date",
            "generated_at",
        ]
    ].sort_values("ticker")

    if filtered.empty:
        raise RuntimeError(f"[blocked] filtered {index_name} universe is empty")
    if filtered["ticker"].duplicated().any():
        dupes = filtered.loc[filtered["ticker"].duplicated(), "ticker"].tolist()
        raise RuntimeError(f"[blocked] duplicated tickers after filtering {index_name}: {dupes}")
    if filtered["industry_level1"].isin(excluded).any():
        raise RuntimeError(f"[blocked] excluded industries remain in {index_name} filtered universe")
    return filtered.reset_index(drop=True)


def build_index_pool(
    index_config: dict[str, str],
    industry: pd.DataFrame,
    output_dir: Path,
    analysis_date: str,
    generated_at: str,
) -> dict[str, object]:
    constituents = load_constituents(index_config["symbol"])
    unmatched_path = output_dir / index_config["unmatched_name"]
    merged = attach_industry(
        constituents=constituents,
        industry=industry,
        index_name=index_config["display_name"],
        unmatched_path=unmatched_path,
    )
    stock_pool = build_stock_pool(
        constituents=merged[["code", "name"]],
        industry=merged[["code", "industry_level1", "industry_level2", "industry_source"]],
        index_symbol=index_config["symbol"],
        index_name=index_config["display_name"],
        analysis_date=analysis_date,
        generated_at=generated_at,
        unmatched_path=unmatched_path,
    )
    output_path = output_dir / index_config["csv_name"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stock_pool.to_csv(output_path, index=False, encoding="utf-8-sig")
    return {
        "index_name": index_config["display_name"],
        "csv_path": str(output_path),
        "constituents": int(len(constituents)),
        "filtered": int(len(stock_pool)),
        "excluded": int(len(constituents) - len(stock_pool)),
    }


def existing_analysis_tickers(csv_path: Path, analysis_date: str) -> set[str]:
    if not csv_path.exists():
        return set()
    tickers: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("analysis_date") == analysis_date and row.get("ticker"):
                tickers.add(str(row["ticker"]))
    return tickers


def pool_tickers(csv_path: Path) -> list[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row["ticker"] for row in csv.DictReader(handle) if row.get("ticker")]


def write_batch_files(
    tickers: list[str],
    batch_dir: Path,
    batch_size: int,
) -> list[dict[str, object]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    batch_dir.mkdir(parents=True, exist_ok=True)
    for existing in batch_dir.glob("batch_*.txt"):
        existing.unlink()

    manifest: list[dict[str, object]] = []
    for index, start in enumerate(range(0, len(tickers), batch_size), start=1):
        batch_tickers = tickers[start : start + batch_size]
        batch_path = batch_dir / f"batch_{index:03d}.txt"
        batch_path.write_text("\n".join(batch_tickers) + "\n", encoding="utf-8")
        manifest.append(
            {
                "batch": index,
                "path": str(batch_path),
                "ticker_count": len(batch_tickers),
                "first_ticker": batch_tickers[0],
                "last_ticker": batch_tickers[-1],
            }
        )
    return manifest


def build_batches_from_pool_csv(
    stock_pool_csv: Path,
    existing_report_csv: Path,
    batch_dir: Path,
    analysis_date: str,
    batch_size: int,
) -> dict[str, object]:
    source_tickers = pool_tickers(stock_pool_csv)
    existing_tickers = existing_analysis_tickers(existing_report_csv, analysis_date)
    queued_tickers = [ticker for ticker in source_tickers if ticker not in existing_tickers]
    manifest = write_batch_files(queued_tickers, batch_dir=batch_dir, batch_size=batch_size)
    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "source_ticker_count": len(source_tickers),
        "skipped_existing_count": len(source_tickers) - len(queued_tickers),
        "queued_ticker_count": len(queued_tickers),
        "batch_count": len(manifest),
        "manifest_path": str(manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--output-dir")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--existing-report-csv")
    parser.add_argument("--batch-dir")
    parser.add_argument("--no-batches", action="store_true")
    parser.add_argument("--allow-sws-tls-bypass", action="store_true")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir) if args.output_dir else Path("reports") / args.analysis_date
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    industry = load_primary_industry(allow_sws_tls_bypass=args.allow_sws_tls_bypass)
    pools = [
        build_index_pool(
            index_config=index_config,
            industry=industry,
            output_dir=output_dir,
            analysis_date=args.analysis_date,
            generated_at=generated_at,
        )
        for index_config in INDEX_CONFIGS
    ]

    batches: dict[str, object] = {}
    if not args.no_batches:
        existing_report_csv = (
            Path(args.existing_report_csv)
            if args.existing_report_csv
            else output_dir / "daily_ticker_analysis.csv"
        )
        batch_dir = Path(args.batch_dir) if args.batch_dir else output_dir / "hs300_batches"
        batches = build_batches_from_pool_csv(
            stock_pool_csv=output_dir / "hs300_ex_fin_realestate.csv",
            existing_report_csv=existing_report_csv,
            batch_dir=batch_dir,
            analysis_date=args.analysis_date,
            batch_size=args.batch_size,
        )

    print(json.dumps({"pools": pools, "batches": batches}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
