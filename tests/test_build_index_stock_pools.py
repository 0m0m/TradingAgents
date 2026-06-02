from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_script(module_name: str):
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_stock_pool_excludes_banks_and_real_estate_but_keeps_nonbank_finance():
    module = _load_script("build_index_stock_pools")
    constituents = pd.DataFrame(
        [
            {"code": "000001", "name": "平安银行"},
            {"code": "000002", "name": "万科A"},
            {"code": "000063", "name": "中兴通讯"},
            {"code": "600030", "name": "中信证券"},
        ]
    )
    industry = pd.DataFrame(
        [
            {
                "code": "000001",
                "industry_level1": "银行",
                "industry_level2": "股份制银行",
                "industry_source": "test",
            },
            {
                "code": "000002",
                "industry_level1": "房地产",
                "industry_level2": "房地产开发",
                "industry_source": "test",
            },
            {
                "code": "000063",
                "industry_level1": "通信",
                "industry_level2": "通信设备",
                "industry_source": "test",
            },
            {
                "code": "600030",
                "industry_level1": "非银金融",
                "industry_level2": "证券",
                "industry_source": "test",
            },
        ]
    )

    result = module.build_stock_pool(
        constituents=constituents,
        industry=industry,
        index_symbol="000300",
        index_name="沪深300",
        analysis_date="2026-05-30",
        generated_at="2026-06-01T00:00:00+00:00",
    )

    assert result["ticker"].tolist() == ["000063.SZ", "600030.SS"]
    assert result["industry_level1"].tolist() == ["通信", "非银金融"]
    assert set(result["index_name"]) == {"沪深300"}


def test_build_stock_pool_blocks_when_industry_mapping_is_missing(tmp_path: Path):
    module = _load_script("build_index_stock_pools")
    constituents = pd.DataFrame([{"code": "000063", "name": "中兴通讯"}])
    industry = pd.DataFrame(
        columns=["code", "industry_level1", "industry_level2", "industry_source"]
    )
    unmatched_path = tmp_path / "unmatched.csv"

    try:
        module.build_stock_pool(
            constituents=constituents,
            industry=industry,
            index_symbol="000300",
            index_name="沪深300",
            analysis_date="2026-05-30",
            generated_at="2026-06-01T00:00:00+00:00",
            unmatched_path=unmatched_path,
        )
    except RuntimeError as exc:
        assert "[blocked]" in str(exc)
        assert "no industry mapping" in str(exc)
    else:
        raise AssertionError("missing industry mapping should block stock-pool generation")

    assert unmatched_path.exists()
    with unmatched_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["code"] == "000063"


def test_build_batches_skips_existing_analysis_report_tickers(tmp_path: Path):
    module = _load_script("build_index_stock_pools")
    stock_pool_csv = tmp_path / "hs300_ex_fin_realestate.csv"
    report_csv = tmp_path / "daily_ticker_analysis.csv"
    batch_dir = tmp_path / "hs300_batches"

    with stock_pool_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker"])
        writer.writeheader()
        writer.writerows(
            [
                {"ticker": "000063.SZ"},
                {"ticker": "000100.SZ"},
                {"ticker": "000157.SZ"},
            ]
        )

    with report_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["analysis_date", "ticker", "status"])
        writer.writeheader()
        writer.writerows(
            [
                {
                    "analysis_date": "2026-05-30",
                    "ticker": "000063.SZ",
                    "status": "completed",
                },
                {
                    "analysis_date": "2026-05-29",
                    "ticker": "000100.SZ",
                    "status": "completed",
                },
            ]
        )

    payload = module.build_batches_from_pool_csv(
        stock_pool_csv=stock_pool_csv,
        existing_report_csv=report_csv,
        batch_dir=batch_dir,
        analysis_date="2026-05-30",
        batch_size=3,
    )

    assert payload["source_ticker_count"] == 3
    assert payload["skipped_existing_count"] == 1
    assert payload["queued_ticker_count"] == 2
    assert payload["batch_count"] == 1
    assert (batch_dir / "batch_001.txt").read_text(encoding="utf-8").splitlines() == [
        "000100.SZ",
        "000157.SZ",
    ]


def test_main_uses_batch_size_21_by_default():
    module = _load_script("build_index_stock_pools")

    assert module.DEFAULT_BATCH_SIZE == 21
