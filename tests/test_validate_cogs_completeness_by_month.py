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


def _seed_unit_cogs_gap_db(db_path: Path) -> None:
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
            "INSERT INTO dim_sku (sku_key, model, base_cost_cny, weight_kg) "
            "VALUES ('SUIT-31-TS','SUIT-31-TS',0,0)"
        )
        conn.execute(
            """
            INSERT INTO view_sales_line_truth
            (order_id, sale_date, store_code, sku_key, units, net_rev_kzt, cogs_kzt, cogs_source)
            VALUES ('909054064','2026-05-04','ACMEWEAR','SUIT-31-TS',1,7563,NULL,'unresolved')
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_unit_cogs_evidence(path: Path, *, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_childsum_cogs_evidence(path: Path, *, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_validate_cogs_completeness_accepts_copied_temp_unit_cogs_evidence(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "compact_sku_cogs_decisions.csv"
    _seed_unit_cogs_gap_db(db)
    _write_unit_cogs_evidence(
        evidence,
        rows=[
            {
                "sku_key": "SUIT-31-TS",
                "approved_unit_cogs_kzt": 5567.22,
                "source_parent_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "owner-approved 2026-04-28 parent landed COGS carry-forward for copied-temp proof only",
                "copied_temp_only": True,
                "production_write_authorized": False,
            }
        ],
    )

    payload = validate_cogs_completeness_by_month(
        start="2026-05-01",
        end="2026-05-17",
        strict=True,
        db_path=db,
        output_dir=tmp_path / "out",
        unit_cogs_evidence_csv=evidence,
    )

    assert payload["status"] == "PASS"
    assert payload["unresolved_lines"] == 0
    assert payload["unit_cogs_evidence_applied_lines"] == 1
    applied = pd.read_csv(payload["outputs"]["cogs_unit_evidence_applied_lines_csv"])
    assert applied.loc[0, "order_id"] == 909054064
    assert applied.loc[0, "sku_key"] == "SUIT-31-TS"
    assert applied.loc[0, "resolved_cogs_kzt"] == pytest.approx(5567.22)


def test_validate_cogs_completeness_missing_unit_cogs_evidence_still_fails(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "compact_sku_cogs_decisions.csv"
    _seed_unit_cogs_gap_db(db)
    _write_unit_cogs_evidence(
        evidence,
        rows=[
            {
                "sku_key": "LINE-31-TS",
                "approved_unit_cogs_kzt": 6006.76,
                "source_parent_sku": "CL_OC_MEN_LINE51_WHITE",
                "decision_basis": "owner-approved 2026-04-28 parent landed COGS carry-forward for copied-temp proof only",
                "copied_temp_only": True,
                "production_write_authorized": False,
            }
        ],
    )

    with pytest.raises(CogsCompletenessError, match="unresolved_lines=1"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=True,
            db_path=db,
            output_dir=tmp_path / "out",
            unit_cogs_evidence_csv=evidence,
        )


def test_validate_cogs_completeness_rejects_unsafe_unit_cogs_evidence(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "compact_sku_cogs_decisions.csv"
    _seed_unit_cogs_gap_db(db)
    _write_unit_cogs_evidence(
        evidence,
        rows=[
            {
                "sku_key": "SUIT-31-TS",
                "approved_unit_cogs_kzt": 5567.22,
                "source_parent_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "owner-approved 2026-04-28 parent landed COGS carry-forward for copied-temp proof only",
                "copied_temp_only": True,
                "production_write_authorized": True,
            }
        ],
    )

    with pytest.raises(CogsCompletenessError, match="production_write_authorized=false"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=False,
            db_path=db,
            output_dir=tmp_path / "out",
            unit_cogs_evidence_csv=evidence,
        )


def test_validate_cogs_completeness_rejects_ambiguous_unit_cogs_evidence(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "compact_sku_cogs_decisions.csv"
    _seed_unit_cogs_gap_db(db)
    _write_unit_cogs_evidence(
        evidence,
        rows=[
            {
                "sku_key": "SUIT-31-TS",
                "approved_unit_cogs_kzt": 5567.22,
                "source_parent_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "owner-approved 2026-04-28 parent landed COGS carry-forward for copied-temp proof only",
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
            {
                "sku_key": "SUIT-31-TS",
                "approved_unit_cogs_kzt": 6006.76,
                "source_parent_sku": "CL_OC_MEN_LINE51_WHITE",
                "decision_basis": "conflicting copied-temp evidence should not pass",
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
        ],
    )

    with pytest.raises(CogsCompletenessError, match="ambiguous duplicate"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=False,
            db_path=db,
            output_dir=tmp_path / "out",
            unit_cogs_evidence_csv=evidence,
        )


def test_validate_cogs_completeness_accepts_childsum_component_cogs_evidence(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "childsum_cogs_components.csv"
    _seed_unit_cogs_gap_db(db)
    _write_childsum_cogs_evidence(
        evidence,
        rows=[
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "line61_tshirt_top",
                "component_base_cost_cny": 12,
                "component_weight_kg": 0.2,
                "component_source_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "component-level copied-temp proof",
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "shared_leggings_pool",
                "component_base_cost_cny": 21,
                "component_weight_kg": 0.5,
                "component_source_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "component-level copied-temp proof",
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "shared_shorts_pool",
                "component_base_cost_cny": 8,
                "component_weight_kg": 0.3,
                "component_source_sku": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "decision_basis": "component-level copied-temp proof",
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
        ],
    )

    payload = validate_cogs_completeness_by_month(
        start="2026-05-01",
        end="2026-05-17",
        strict=True,
        db_path=db,
        output_dir=tmp_path / "out",
        childsum_cogs_evidence_csv=evidence,
    )

    expected_unit_cogs = round(
        (41 * cogs_mod.CHILDSUM_CNY_KZT) + (1.0 * cogs_mod.USD_KZT * cogs_mod.DLV),
        2,
    )
    assert payload["status"] == "PASS"
    assert payload["unresolved_lines"] == 0
    assert payload["childsum_cogs_evidence_applied_lines"] == 1
    applied = pd.read_csv(payload["outputs"]["cogs_childsum_evidence_applied_lines_csv"])
    assert applied.loc[0, "order_id"] == 909054064
    assert applied.loc[0, "sku_key"] == "SUIT-31-TS"
    assert applied.loc[0, "component_count"] == 3
    assert applied.loc[0, "cogs_source"] == cogs_mod.CHILDSUM_COGS_COPIED_TEMP_SOURCE
    assert applied.loc[0, "resolved_cogs_kzt"] == pytest.approx(expected_unit_cogs)


def test_validate_cogs_completeness_missing_childsum_component_truth_still_fails(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "childsum_cogs_components.csv"
    _seed_unit_cogs_gap_db(db)
    _write_childsum_cogs_evidence(
        evidence,
        rows=[
            {
                "child_sku_key": "LINE-31-TS",
                "component_key": "line51_tshirt_top",
                "component_base_cost_cny": 12,
                "component_weight_kg": 0.2,
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
            {
                "child_sku_key": "LINE-31-TS",
                "component_key": "shared_shorts_pool",
                "component_base_cost_cny": 8,
                "component_weight_kg": 0.3,
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
        ],
    )

    with pytest.raises(CogsCompletenessError, match="unresolved_lines=1"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=True,
            db_path=db,
            output_dir=tmp_path / "out",
            childsum_cogs_evidence_csv=evidence,
        )


def test_validate_cogs_completeness_rejects_unsafe_childsum_component_evidence(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "childsum_cogs_components.csv"
    _seed_unit_cogs_gap_db(db)
    _write_childsum_cogs_evidence(
        evidence,
        rows=[
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "line61_tshirt_top",
                "component_base_cost_cny": 12,
                "component_weight_kg": 0.2,
                "copied_temp_only": True,
                "production_write_authorized": True,
            },
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "shared_shorts_pool",
                "component_base_cost_cny": 8,
                "component_weight_kg": 0.3,
                "copied_temp_only": True,
                "production_write_authorized": False,
            },
        ],
    )

    with pytest.raises(CogsCompletenessError, match="production_write_authorized=false"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=False,
            db_path=db,
            output_dir=tmp_path / "out",
            childsum_cogs_evidence_csv=evidence,
        )


def test_validate_cogs_completeness_rejects_incomplete_childsum_component_set(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    evidence = tmp_path / "childsum_cogs_components.csv"
    _seed_unit_cogs_gap_db(db)
    _write_childsum_cogs_evidence(
        evidence,
        rows=[
            {
                "child_sku_key": "SUIT-31-TS",
                "component_key": "line61_tshirt_top",
                "component_base_cost_cny": 12,
                "component_weight_kg": 0.2,
                "copied_temp_only": True,
                "production_write_authorized": False,
            }
        ],
    )

    with pytest.raises(CogsCompletenessError, match="at least two components"):
        validate_cogs_completeness_by_month(
            start="2026-05-01",
            end="2026-05-17",
            strict=False,
            db_path=db,
            output_dir=tmp_path / "out",
            childsum_cogs_evidence_csv=evidence,
        )
