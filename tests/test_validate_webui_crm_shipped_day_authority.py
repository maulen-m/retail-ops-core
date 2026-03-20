from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from scripts.validate_webui_crm_shipped_day_authority import (
    _load_authority_inputs,
    decide_shipped_day_authority,
    validate_webui_crm_shipped_day_authority,
)


def _seed_fact_orders(db_path: Path, rows: list[dict[str, object]]) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            store_code TEXT,
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,
            courier_transmission_date TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            waybill_number TEXT,
            waybill_url TEXT,
            updated_at TEXT,
            imported_at TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, created_at, planned_shipment_date, actual_shipment_date,
            courier_transmission_date, internal_status, kaspi_status, waybill_number,
            waybill_url, updated_at, imported_at
        ) VALUES (
            :order_id, :store_code, :created_at, :planned_shipment_date, :actual_shipment_date,
            :courier_transmission_date, :internal_status, :kaspi_status, :waybill_number,
            :waybill_url, :updated_at, :imported_at
        )
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_decide_shipped_day_authority_returns_rule_proven_on_single_deterministic_rule() -> None:
    enriched = pd.DataFrame(
        [
            {
                "order_id": "1001",
                "sale_date_crm": "2026-01-03",
                "planned_courier_at": "2026-01-02",
                "created_at": "2026-01-01",
                "delivered_at": "2026-01-05",
                "planned_shipment_date": "2026-01-03",
                "actual_shipment_date": "2026-01-03",
                "courier_transmission_date": "2026-01-03",
            },
            {
                "order_id": "1002",
                "sale_date_crm": "2026-01-05",
                "planned_courier_at": "2026-01-04",
                "created_at": "2026-01-03",
                "delivered_at": "2026-01-07",
                "planned_shipment_date": "2026-01-05",
                "actual_shipment_date": "2026-01-05",
                "courier_transmission_date": "2026-01-05",
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "rule_code": "WEBUI_PLANNED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM",
                "matched_orders": 2,
                "mismatched_orders": 0,
                "coverage_ratio": 1.0,
                "is_deterministic": True,
            },
            {
                "rule_code": "WEBUI_CREATED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM",
                "matched_orders": 1,
                "mismatched_orders": 1,
                "coverage_ratio": 0.5,
                "is_deterministic": False,
            },
        ]
    )

    decision = decide_shipped_day_authority(enriched, candidates)

    assert decision["decision"] == "RULE_PROVEN"
    assert decision["rule_code"] == "WEBUI_PLANNED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM"


def test_decide_shipped_day_authority_returns_crm_authority_on_mixed_population() -> None:
    enriched = pd.DataFrame(
        [
            {
                "order_id": "1001",
                "sale_date_crm": "2026-01-03",
                "planned_courier_at": "2026-01-02",
                "created_at": "2026-01-01",
                "planned_shipment_date": "2026-01-03",
            },
            {
                "order_id": "1002",
                "sale_date_crm": "2026-01-05",
                "planned_courier_at": "",
                "created_at": "2026-01-04",
                "planned_shipment_date": "2026-01-05",
            },
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "rule_code": "WEBUI_PLANNED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM",
                "matched_orders": 1,
                "mismatched_orders": 1,
                "coverage_ratio": 0.5,
                "is_deterministic": False,
            },
            {
                "rule_code": "WEBUI_CREATED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM",
                "matched_orders": 1,
                "mismatched_orders": 1,
                "coverage_ratio": 0.5,
                "is_deterministic": False,
            },
        ]
    )

    decision = decide_shipped_day_authority(enriched, candidates)

    assert decision["decision"] == "CRM_REMAINS_CHRONOLOGY_AUTHORITY"
    assert decision["rule_code"] == ""


def test_validate_webui_crm_shipped_day_authority_writes_outputs_and_decision(
    tmp_path: Path,
) -> None:
    gap_csv = tmp_path / "webui_vs_crm_gap_classifier_reprojected.csv"
    pd.DataFrame(
        [
            {
                "order_id": "1001",
                "sale_date_webui": "2026-01-02",
                "store_code_webui": "ACMEWEAR",
                "sale_date_crm": "2026-01-03",
                "store_code_crm": "ACMEWEAR",
                "classifier": "DATE_MISMATCH",
            },
            {
                "order_id": "1002",
                "sale_date_webui": "2026-01-04",
                "store_code_webui": "ACMEWEAR",
                "sale_date_crm": "2026-01-05",
                "store_code_crm": "ACMEWEAR",
                "classifier": "DATE_MISMATCH",
            },
        ]
    ).to_csv(gap_csv, index=False, encoding="utf-8")

    delta_csv = tmp_path / "promotion_delta_orders.csv"
    pd.DataFrame(
        [
            {
                "surface": "CRM",
                "surface_classifier": "DATE_MISMATCH",
                "order_id": "1001",
                "store_code": "ACMEWEAR",
                "created_at": "2026-01-01",
                "planned_courier_at": "2026-01-02",
                "delivered_at": "2026-01-05",
                "crm_sale_date": "2026-01-03",
                "webui_sale_date": "2026-01-02",
                "root_bucket": "CRM_EVENT_BASIS_PLANNED_PLUS_ONE_MATCH",
            },
            {
                "surface": "CRM",
                "surface_classifier": "DATE_MISMATCH",
                "order_id": "1002",
                "store_code": "ACMEWEAR",
                "created_at": "2026-01-03",
                "planned_courier_at": "2026-01-04",
                "delivered_at": "2026-01-06",
                "crm_sale_date": "2026-01-05",
                "webui_sale_date": "2026-01-04",
                "root_bucket": "CRM_EVENT_BASIS_PLANNED_PLUS_ONE_MATCH",
            },
        ]
    ).to_csv(delta_csv, index=False, encoding="utf-8")

    db_path = tmp_path / "app.db"
    _seed_fact_orders(
        db_path,
        [
            {
                "order_id": "1001",
                "store_code": "ACMEWEAR",
                "created_at": "2026-01-01 08:00:00",
                "planned_shipment_date": "2026-01-03",
                "actual_shipment_date": "2026-01-03 19:00:00",
                "courier_transmission_date": "2026-01-03 19:00:00",
                "internal_status": "COMPLETED",
                "kaspi_status": "ARCHIVE",
                "waybill_number": "WB1",
                "waybill_url": "https://example.test/1.pdf",
                "updated_at": "2026-01-03 20:00:00",
                "imported_at": "2026-01-03 20:00:00",
            },
            {
                "order_id": "1002",
                "store_code": "ACMEWEAR",
                "created_at": "2026-01-03 08:00:00",
                "planned_shipment_date": "2026-01-05",
                "actual_shipment_date": "2026-01-05 19:00:00",
                "courier_transmission_date": "2026-01-05 19:00:00",
                "internal_status": "COMPLETED",
                "kaspi_status": "ARCHIVE",
                "waybill_number": "WB2",
                "waybill_url": "https://example.test/2.pdf",
                "updated_at": "2026-01-05 20:00:00",
                "imported_at": "2026-01-05 20:00:00",
            },
        ],
    )

    shipped_root = tmp_path / "shipped_vs_waybill_crm" / "2026-02-27"
    shipped_root.mkdir(parents=True)
    (shipped_root / "summary.json").write_text(
        '{"target_date":"2026-02-27","crm_day_orders":73,"crm_day_with_api_shipped":70}',
        encoding="utf-8",
    )

    report = validate_webui_crm_shipped_day_authority(
        start="2026-01-01",
        end="2026-02-29",
        db_path=db_path,
        gap_csv=gap_csv,
        promotion_delta_csv=delta_csv,
        output_dir=tmp_path / "out",
        shipped_validation_root=tmp_path / "shipped_vs_waybill_crm",
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["decision"] == "RULE_PROVEN"
    assert (tmp_path / "out" / "shipped_day_authority_decision.json").exists()
    assert (tmp_path / "out" / "shipped_day_rule_candidates.csv").exists()
    assert (tmp_path / "out" / "shipped_day_authority_sample.csv").exists()


def test_load_authority_inputs_dedupes_gap_orders_and_fills_missing_root_bucket(
    tmp_path: Path,
) -> None:
    gap_csv = tmp_path / "gap.csv"
    pd.DataFrame(
        [
            {
                "order_id": "5001",
                "sale_date_webui": "2026-01-02",
                "store_code_webui": "ACMEWEAR",
                "sale_date_crm": "2026-01-03",
                "store_code_crm": "ACMEWEAR",
                "classifier": "DATE_MISMATCH",
            },
            {
                "order_id": "5001",
                "sale_date_webui": "2026-01-02",
                "store_code_webui": "ACMEWEAR",
                "sale_date_crm": "2026-01-03",
                "store_code_crm": "ACMEWEAR",
                "classifier": "DATE_MISMATCH",
            },
        ]
    ).to_csv(gap_csv, index=False, encoding="utf-8")

    delta_csv = tmp_path / "delta.csv"
    pd.DataFrame(
        [
            {
                "surface": "CRM",
                "surface_classifier": "DATE_MISMATCH",
                "order_id": "9999",
                "store_code": "ACMEWEAR",
                "created_at": "2026-01-01",
                "planned_courier_at": "2026-01-02",
                "delivered_at": "2026-01-05",
                "crm_sale_date": "2026-01-03",
                "webui_sale_date": "2026-01-02",
                "root_bucket": "CRM_EVENT_BASIS_PLANNED_PLUS_ONE_MATCH",
            },
        ]
    ).to_csv(delta_csv, index=False, encoding="utf-8")

    loaded = _load_authority_inputs(gap_csv=gap_csv, promotion_delta_csv=delta_csv)

    assert len(loaded) == 1
    assert loaded.iloc[0]["root_bucket"] == "UNMAPPED_REPROJECTED_ONLY"
