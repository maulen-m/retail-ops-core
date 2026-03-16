from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import scripts.validate_cogs_completeness_by_month as cogs_mod
from scripts.validate_cogs_completeness_by_month import (
    CogsCompletenessError,
    validate_cogs_completeness_by_month,
)


def _seed_db(db_path: Path, *, unresolved: bool) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                order_id TEXT,
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                units REAL,
                net_rev_kzt REAL,
                cogs_kzt REAL,
                cogs_source TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                model TEXT,
                base_cost_cny REAL,
                weight_kg REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO dim_sku (sku_key, model, base_cost_cny, weight_kg) VALUES ('SKU_A','M',10,1.5)"
        )
        if unresolved:
            conn.execute(
                """
                INSERT INTO view_sales_line_truth
                (order_id, sale_date, store_code, sku_key, units, net_rev_kzt, cogs_kzt, cogs_source)
                VALUES ('1','2026-01-10','UNIVERSAL','SKU_A',1,1000,NULL,'unresolved')
                """
            )
        else:
            conn.execute(
                """
                INSERT INTO view_sales_line_truth
                (order_id, sale_date, store_code, sku_key, units, net_rev_kzt, cogs_kzt, cogs_source)
                VALUES ('1','2026-01-10','UNIVERSAL','SKU_A',1,1000,500,'formula_full')
                """
            )
        conn.commit()
    finally:
        conn.close()


def test_validate_cogs_completeness_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, unresolved=False)
    payload = validate_cogs_completeness_by_month(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_cogs_completeness_strict_fail(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db, unresolved=True)
    with pytest.raises(CogsCompletenessError):
        validate_cogs_completeness_by_month(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            output_dir=tmp_path / "out",
        )


def test_validate_cogs_completeness_webui_coerces_numeric_units(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load_lines(**_kwargs):
        lines = pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-10",
                    "sale_month": "2026-01",
                    "store_code": "ACMEWEAR",
                    "sku_key": "SKU_A",
                    "units": "2",
                    "net_rev_kzt": "1000",
                    "cogs_kzt": None,
                    "cogs_source": "unresolved",
                    "model": "M",
                    "base_cost_cny": "10",
                    "weight_kg": "0",
                }
            ]
        )
        return lines, {"projected_rows": 1, "missing_in_db_orders": 0}, []

    monkeypatch.setattr(cogs_mod, "_load_lines", fake_load_lines)

    payload = validate_cogs_completeness_by_month(
        start="2026-01-01",
        end="2026-01-31",
        strict=False,
        db_path=tmp_path / "app.db",
        truth_source="webui_archive",
        ledger_root=tmp_path / "ledger",
        as_of="2026-03-06",
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "FAIL"
    assert payload["weight_drift_rows"] == 1


def test_validate_cogs_completeness_webui_honors_effective_db_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                model TEXT,
                base_cost_cny REAL,
                weight_kg REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO dim_sku (sku_key, model, base_cost_cny, weight_kg) VALUES ('SKU_A','M',10,1.5)"
        )
        conn.commit()
    finally:
        conn.close()

    ledger = tmp_path / "ledger"
    out_dir = tmp_path / "out"
    ledger.mkdir()
    out_dir.mkdir()

    monkeypatch.setattr(
        cogs_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-10",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "cogs_kzt": 500.0,
                        "cogs_source": "formula_full",
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 1},
        ),
    )

    (out_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ledger_root": str(ledger.resolve()),
                "period": {"start": "2026-01-01", "end": "2026-01-31"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 1,
            }
        ),
        encoding="utf-8",
    )

    payload = validate_cogs_completeness_by_month(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        truth_source="webui_archive",
        ledger_root=ledger,
        as_of="2026-03-07",
        output_dir=out_dir,
    )
    assert payload["status"] == "PASS"
    assert payload["truth_errors"] == []
