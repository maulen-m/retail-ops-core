from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

import scripts.validate_webui_archive_vs_crm_band as crm_band_mod
import scripts.validate_webui_archive_vs_current_db as current_db_mod
from scripts.validate_webui_archive_vs_crm_band import validate_webui_archive_vs_crm_band
from scripts.validate_webui_archive_vs_current_db import (
    WebuiArchiveVsCurrentDBError,
    validate_webui_archive_vs_current_db,
)


def test_validate_webui_archive_vs_crm_band_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"chronology_mismatch_orders": 2}), encoding="utf-8")

    monkeypatch.setattr(
        crm_band_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        crm_band_mod,
        "load_crm_workbook",
        lambda _path: pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-05",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                }
            ]
        ),
    )

    report = validate_webui_archive_vs_crm_band(
        start="2026-01-01",
        end="2026-01-31",
        crm_workbook=tmp_path / "crm.xlsx",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
        baseline_report_json=baseline,
        units_tolerance=0.0,
        net_rev_tolerance_kzt=1.0,
    )
    assert report["status"] == "PASS"
    assert report["chronology_improvement_orders"] == 2


def test_validate_webui_archive_vs_crm_band_shipped_projection_uses_pack_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"chronology_mismatch_orders": 1}), encoding="utf-8")

    monkeypatch.setattr(
        crm_band_mod,
        "build_webui_shipped_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "event_date_source": "planned_courier_at",
                    }
                ]
            ),
            {"projected_orders": 1, "projected_rows": 1},
        ),
    )
    monkeypatch.setattr(
        crm_band_mod,
        "load_crm_workbook",
        lambda _path: pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-05",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                }
            ]
        ),
    )

    report = validate_webui_archive_vs_crm_band(
        start="2026-01-01",
        end="2026-01-31",
        crm_workbook=tmp_path / "crm.xlsx",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
        baseline_report_json=baseline,
        units_tolerance=0.0,
        net_rev_tolerance_kzt=1.0,
        truth_event="shipped_projection",
    )
    assert report["status"] == "PASS"
    assert report["truth_event"] == "shipped_projection"


def test_validate_webui_archive_vs_current_db_strict_fail_on_missing_db_orders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )

    with pytest.raises(WebuiArchiveVsCurrentDBError):
        validate_webui_archive_vs_current_db(
            start="2026-01-01",
            end="2026-01-31",
            db_path=tmp_path / "app.db",
            ledger_root=ledger,
            output_dir=tmp_path / "out",
            strict=True,
        )


def test_validate_webui_archive_vs_current_db_reclassifies_prewindow_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "ledger_manifest.json").write_text(json.dumps({"run_id": "ledger"}), encoding="utf-8")
    pd.DataFrame(columns=["store_code", "order_id", "status_internal", "status_change_at", "created_at", "delivered_at", "returned_at"]).to_csv(
        ledger / "webui_status_ledger.csv",
        index=False,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame([{"order_id": "1", "sale_date": "2025-12-30", "store_code": "ACMEWEAR"}]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["webui_only_orders"] == 0
    assert report["window_drift_orders"] == 1


def test_validate_webui_archive_vs_current_db_reclassifies_db_only_returned_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "ledger_manifest.json").write_text(json.dumps({"run_id": "ledger"}), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "store_code": "ACMEWEAR",
                "order_id": "2",
                "status_internal": "RETURNED",
                "status_change_at": "2026-02-03",
                "created_at": "2026-01-30",
                "delivered_at": "",
                "returned_at": "2026-02-03",
            }
        ]
    ).to_csv(ledger / "webui_status_ledger.csv", index=False, encoding="utf-8")

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt", "db_match_status"]),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "order_id": "2",
                    "sale_date": "2026-01-31",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 900.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["db_only_orders"] == 0
    assert report["db_only_returned_orders"] == 1


def test_validate_webui_archive_vs_current_db_accepts_quarantined_missing_orders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    quarantine_csv = tmp_path / "db_quarantine_candidates.csv"
    pd.DataFrame(
        [
            {
                "order_id": "1",
                "store_code": "ACMEWEAR",
                "webui_sale_date": "2026-01-05",
                "root_bucket": "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
                "resolution_detail": "documented quarantine",
            }
        ]
    ).to_csv(quarantine_csv, index=False, encoding="utf-8")

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
        quarantine_csv=quarantine_csv,
    )

    assert report["status"] == "PASS"


def test_validate_webui_archive_vs_current_db_autoloads_quarantine_from_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    pd.DataFrame(
        [
            {
                "order_id": "1",
                "store_code": "ACMEWEAR",
                "webui_sale_date": "2026-01-05",
                "root_bucket": "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
                "resolution_detail": "documented quarantine",
            }
        ]
    ).to_csv(output_dir / "db_quarantine_candidates.csv", index=False, encoding="utf-8")

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=output_dir,
        strict=True,
    )

    assert report["status"] == "PASS"


def test_validate_webui_archive_vs_current_db_falls_back_to_repo_quarantine_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    repo_quarantine = (
        tmp_path
        / "exports"
        / "validation"
        / "webui_archive_single_truth"
        / "2026-03-07"
        / "db_quarantine_candidates.csv"
    )
    repo_quarantine.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "order_id": "1",
                "store_code": "ACMEWEAR",
                "webui_sale_date": "2026-01-05",
                "root_bucket": "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
                "resolution_detail": "documented quarantine",
            }
        ]
    ).to_csv(repo_quarantine, index=False, encoding="utf-8")
    monkeypatch.setattr(current_db_mod, "PROJECT_ROOT", tmp_path)

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["missing_in_db_orders"] == 0


def test_validate_webui_archive_vs_current_db_normalizes_invalid_month_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt", "db_match_status"]),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "order_id": "2",
                    "sale_date": "2026-03-01",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 900.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-02-29",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["db_only_orders"] == 0
    assert report["missing_in_db_orders"] == 0
    assert report["quarantined_orders"] == 0


def test_validate_webui_archive_vs_current_db_treats_date_mismatch_as_diagnostic_under_crm_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-14",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-07",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=output_dir,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["chronology_delta_orders"] == 1
    assert report["hard_chronology_delta_orders"] == 0


def test_validate_webui_archive_vs_current_db_falls_back_to_repo_authority_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    repo_decision = (
        tmp_path
        / "exports"
        / "validation"
        / "webui_shipped_authority_recon"
        / "2026-03-07"
        / "shipped_day_authority_decision.json"
    )
    repo_decision.parent.mkdir(parents=True)
    repo_decision.write_text(
        json.dumps({"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(current_db_mod, "PROJECT_ROOT", tmp_path)

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-14",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-07",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 1000.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=tmp_path / "out",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["chronology_authority_decision"] == "CRM_REMAINS_CHRONOLOGY_AUTHORITY"
    assert report["hard_chronology_delta_orders"] == 0


def test_validate_webui_archive_vs_current_db_reclassifies_db_only_postwindow_drift_under_crm_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "ledger_manifest.json").write_text(json.dumps({"run_id": "ledger"}), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "store_code": "ACMEWEAR",
                "order_id": "1",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-02-05",
                "created_at": "2026-01-30",
                "delivered_at": "2026-02-05",
                "returned_at": "",
            }
        ]
    ).to_csv(ledger / "webui_status_ledger.csv", index=False, encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt", "db_match_status"]),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "order_id": "1",
                    "sale_date": "2026-01-31",
                    "store_code": "ACMEWEAR",
                    "units": 1.0,
                    "net_rev_kzt": 900.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=tmp_path / "app.db",
        ledger_root=ledger,
        output_dir=output_dir,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["db_only_orders"] == 0
    assert report["postwindow_drift_orders"] == 1


def test_validate_webui_archive_vs_current_db_accepts_workbook_anchor_quarantine_under_crm_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps({"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}),
        encoding="utf-8",
    )

    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_sales_workbook_anchor_quarantine (
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sale_dates TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                quantity REAL NOT NULL,
                net_rev_kzt REAL NOT NULL,
                total_price_kzt REAL NOT NULL,
                reason TEXT NOT NULL,
                source_file TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_sales_workbook_anchor_quarantine (
                order_id, store_code, sale_dates, row_count, quantity, net_rev_kzt, total_price_kzt, reason, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "ACMEWEAR", "2026-01-05|2026-01-06", 2, 1.0, 1000.0, 1200.0, "MULTI_DATE", "seed.xlsx"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    report = validate_webui_archive_vs_current_db(
        start="2026-01-01",
        end="2026-01-31",
        db_path=db_path,
        ledger_root=ledger,
        output_dir=output_dir,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["missing_in_db_orders"] == 0
    assert report["original_missing_in_db_orders"] == 1
    assert report["workbook_anchor_quarantined_orders"] == 1
    assert report["quarantined_orders"] == 1


def test_validate_webui_archive_vs_current_db_keeps_workbook_anchor_quarantine_hard_without_crm_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    monkeypatch.setattr(current_db_mod, "PROJECT_ROOT", tmp_path)
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_sales_workbook_anchor_quarantine (
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sale_dates TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                quantity REAL NOT NULL,
                net_rev_kzt REAL NOT NULL,
                total_price_kzt REAL NOT NULL,
                reason TEXT NOT NULL,
                source_file TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_sales_workbook_anchor_quarantine (
                order_id, store_code, sale_dates, row_count, quantity, net_rev_kzt, total_price_kzt, reason, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("1", "ACMEWEAR", "2026-01-05|2026-01-06", 2, 1.0, 1000.0, 1200.0, "MULTI_DATE", "seed.xlsx"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(
        current_db_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "db_match_status": "MISSING_IN_DB",
                    }
                ]
            ),
            {"missing_in_db_orders": 1},
        ),
    )
    monkeypatch.setattr(
        current_db_mod,
        "load_db_truth",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code", "units", "net_rev_kzt"]),
    )
    monkeypatch.setattr(
        current_db_mod,
        "_fetch_db_rows_for_orders_any_date",
        lambda **_kwargs: pd.DataFrame(columns=["order_id", "sale_date", "store_code"]),
    )

    with pytest.raises(WebuiArchiveVsCurrentDBError):
        validate_webui_archive_vs_current_db(
            start="2026-01-01",
            end="2026-01-31",
            db_path=db_path,
            ledger_root=ledger,
            output_dir=tmp_path / "out",
            strict=True,
        )
