from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.validate_ads_spend_reality import (
    AdsSpendRealityError,
    validate_ads_spend_reality,
)
import scripts.validate_ads_spend_reality as spend_mod


def _write_stores_yaml(path: Path) -> None:
    payload = {
        "stores": {
            "ACMEWEAR": {"merchant_uid": "30137883"},
        }
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _seed_db(db_path: Path, *, ads_cost: float | None, mapped: int = 1) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                net_rev_kzt REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ads_spend_sidecar_daily_sku (
                date TEXT,
                store_code TEXT,
                sku_key TEXT,
                mapped INTEGER,
                ads_cost_kzt REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO view_sales_line_truth VALUES ('1','2026-01-05','ACMEWEAR','SKU_A',1000.0)"
        )
        if ads_cost is not None:
            conn.execute(
                "INSERT INTO ads_spend_sidecar_daily_sku VALUES ('2026-01-05','30137883','SKU_A',?,?)",
                (mapped, ads_cost),
            )
        conn.commit()
    finally:
        conn.close()


def _write_gap_quarantine_yaml(path: Path) -> None:
    payload = {
        "version": 1,
        "quarantines": [
            {
                "order_id": "1",
                "sale_date": "2026-01-05",
                "store_code": "ACMEWEAR",
                "sku_key": "SKU_A",
                "reason": "missing_source_evidence",
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_validate_ads_spend_reality_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=100.0)
    payload = validate_ads_spend_reality(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        max_ads_to_net_rev_ratio=0.8,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
    assert "_ads_spend_reality_offer_input" in str(
        payload["source_offer_coverage_report_json"]
    )


def test_validate_ads_spend_reality_strict_fail_missing_ads(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=0.0)
    with pytest.raises(AdsSpendRealityError):
        validate_ads_spend_reality(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            stores_config=stores,
            max_ads_to_net_rev_ratio=0.8,
            output_dir=tmp_path / "out",
        )


def test_validate_ads_spend_reality_passes_through_gap_quarantine(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    quarantine = tmp_path / "ads_source_gap_quarantine.yaml"
    _write_stores_yaml(stores)
    _write_gap_quarantine_yaml(quarantine)
    _seed_db(db, ads_cost=0.0)
    payload = validate_ads_spend_reality(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        stores_config=stores,
        max_ads_to_net_rev_ratio=0.8,
        gap_quarantine_config=quarantine,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_ads_spend_reality_passes_parent_truth_dir_to_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_validate_ads_offer_universe_coverage(**kwargs):
        captured.update(kwargs)
        coverage_dir = Path(kwargs["output_dir"])
        coverage_dir.mkdir(parents=True, exist_ok=True)
        report_json = coverage_dir / "ads_offer_universe_report.json"
        report_json.write_text("{}", encoding="utf-8")
        month_store_csv = coverage_dir / "ads_spend_reality_by_month_store.csv"
        month_store_csv.write_text("sale_month,store_code,ads_kzt\n", encoding="utf-8")
        return {
            "spend_reality_fail_pairs": 0,
            "truth_errors": [],
            "outputs": {
                "ads_offer_universe_report_json": str(report_json),
                "ads_spend_reality_by_month_store_csv": str(month_store_csv),
            },
        }

    monkeypatch.setattr(spend_mod, "validate_ads_offer_universe_coverage", _fake_validate_ads_offer_universe_coverage)
    db = tmp_path / "app.db"
    stores = tmp_path / "stores.yaml"
    _write_stores_yaml(stores)
    _seed_db(db, ads_cost=100.0)
    out_dir = tmp_path / "out"

    payload = validate_ads_spend_reality(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        truth_source="webui_archive",
        stores_config=stores,
        ledger_root=tmp_path / "ledger",
        output_dir=out_dir,
        max_ads_to_net_rev_ratio=0.8,
    )

    assert payload["status"] == "PASS"
    assert captured["truth_output_dir"] == out_dir
