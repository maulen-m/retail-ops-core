from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import scripts.classify_webui_promotion_deltas as delta_mod
from scripts.classify_webui_promotion_deltas import (
    classify_delta_reference,
    classify_webui_promotion_deltas,
    summarize_classification_rows,
)


def test_classify_delta_reference_crm_date_mismatch_planned_courier_match() -> None:
    bucket = classify_delta_reference(
        {
            "surface": "CRM",
            "surface_classifier": "DATE_MISMATCH",
            "planned_courier_at": "2026-01-05",
            "created_at": "2026-01-04",
            "delivered_at": "2026-01-07",
            "crm_sale_date": "2026-01-05",
            "status_set": "DELIVERED",
        }
    )
    assert bucket["root_bucket"] == "CRM_EVENT_BASIS_PLANNED_COURIER_MATCH"


def test_classify_delta_reference_crm_only_missing_in_db() -> None:
    bucket = classify_delta_reference(
        {
            "surface": "CRM",
            "surface_classifier": "IN_CRM_ONLY",
            "status_set": "DELIVERED",
            "missing_in_db_flag": True,
            "delivered_at": "2026-01-28",
        }
    )
    assert bucket["root_bucket"] == "CRM_ONLY_DB_ABSENT_DELIVERED"


def test_classify_delta_reference_db_webui_only_is_prewindow_db_drift() -> None:
    bucket = classify_delta_reference(
        {
            "surface": "DB",
            "surface_classifier": "IN_WEBUI_ONLY",
            "db_sale_date_min": "2025-12-28",
            "webui_sale_date": "2026-01-03",
            "status_set": "DELIVERED",
        }
    )
    assert bucket["root_bucket"] == "DB_WINDOW_DRIFT_PREWINDOW"


def test_classify_delta_reference_db_only_returned_in_webui() -> None:
    bucket = classify_delta_reference(
        {
            "surface": "DB",
            "surface_classifier": "IN_DB_ONLY",
            "status_set": "RETURNED",
            "returned_at": "2026-03-02",
        }
    )
    assert bucket["root_bucket"] == "DB_ONLY_RETURNED_IN_WEBUI"


def test_summarize_classification_rows_reconciles_surface_counts() -> None:
    rows = pd.DataFrame(
        [
            {"surface": "CRM", "surface_classifier": "DATE_MISMATCH", "root_bucket": "A"},
            {"surface": "CRM", "surface_classifier": "DATE_MISMATCH", "root_bucket": "A"},
            {"surface": "CRM", "surface_classifier": "IN_CRM_ONLY", "root_bucket": "B"},
            {"surface": "DB", "surface_classifier": "MISSING_IN_DB", "root_bucket": "C"},
        ]
    )
    summary = summarize_classification_rows(rows)
    assert int(summary["delta_reference_count"].sum()) == 4
    assert (
        summary.groupby(["surface", "surface_classifier"], as_index=False)["delta_reference_count"].sum()
        .sort_values(["surface", "surface_classifier"])
        .to_dict("records")
        == [
            {"surface": "CRM", "surface_classifier": "DATE_MISMATCH", "delta_reference_count": 2},
            {"surface": "CRM", "surface_classifier": "IN_CRM_ONLY", "delta_reference_count": 1},
            {"surface": "DB", "surface_classifier": "MISSING_IN_DB", "delta_reference_count": 1},
        ]
    )


def test_classify_webui_promotion_deltas_strict_outputs_reconciled_counts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ledger_root = tmp_path / "ledger"
    pack_root = tmp_path / "pack"
    output_dir = tmp_path / "out"
    ledger_root.mkdir()
    pack_root.mkdir()

    pd.DataFrame(
        [
            {
                "store_code": "ACMEWEAR",
                "order_id": "1001",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-01-05",
                "created_at": "2026-01-03",
                "delivered_at": "2026-01-05",
                "returned_at": "",
                "source_pack_id": "pack_a",
                "source_file": "f.xlsx",
                "first_seen_pack": "pack_a",
                "last_seen_pack": "pack_a",
                "lineage_source_count": 1,
                "row_fingerprint": "fp1",
            }
        ]
    ).to_csv(ledger_root / "webui_status_ledger.csv", index=False, encoding="utf-8")
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps({"run_id": "ledger_a", "pack_roots": [str(pack_root)]}),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "pack_id": "pack_a",
                "store_code": "ACMEWEAR",
                "source_file": "f.xlsx",
                "source_file_sha256": "sha",
                "source_file_format": "xlsx",
                "source_row_number": 2,
                "order_id": "1001",
                "created_at": "2026-01-03",
                "status_change_at": "2026-01-05",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "quantity": 1.0,
                "net_rev_kzt": 1000.0,
                "warehouse_code": "ACMEWEAR",
                "article": "SKU-1",
                "kaspi_offer_name": "Offer",
                "seller_system_name": "Offer",
                "category": "",
                "pickup_or_delivery_address": "",
                "cancel_reason": "",
                "payment_mode": "",
                "delivery_mode": "",
                "courier_service": "",
                "planned_courier_at": "2026-01-04",
                "delivery_fee_buyer_kzt": 0.0,
                "delivery_fee_seller_kzt": 0.0,
                "transaction_signature_required": "",
                "status_change_required": True,
                "status_change_missing": False,
                "row_fingerprint": "fp1",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
            }
        ]
    ).to_csv(pack_root / "normalized_rows.csv", index=False, encoding="utf-8")
    (pack_root / "source_manifest.json").write_text(json.dumps({"pack_id": "pack_a"}), encoding="utf-8")

    crm_gap = tmp_path / "crm_gap.csv"
    pd.DataFrame(
        [
            {
                "order_id": "1001",
                "sale_date_webui": "2026-01-05",
                "store_code_webui": "ACMEWEAR",
                "sale_date_crm": "2026-01-04",
                "store_code_crm": "ACMEWEAR",
                "classifier": "DATE_MISMATCH",
            }
        ]
    ).to_csv(crm_gap, index=False, encoding="utf-8")
    db_gap = tmp_path / "db_gap.csv"
    pd.DataFrame(columns=["order_id", "sale_date_webui", "store_code_webui", "sale_date_db", "store_code_db", "classifier"]).to_csv(
        db_gap, index=False, encoding="utf-8"
    )

    monkeypatch.setattr(
        delta_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(columns=["order_id", "sale_date", "db_match_status", "webui_delivered_at"]),
            {"missing_in_db_orders": 0},
        ),
    )
    monkeypatch.setattr(
        delta_mod,
        "_load_db_sale_dates",
        lambda _db_path, _order_ids: pd.DataFrame(columns=["order_id", "db_sale_date_min", "db_sale_date_max", "db_store_codes"]),
    )

    report = classify_webui_promotion_deltas(
        start="2026-01-01",
        end="2026-01-31",
        ledger_root=ledger_root,
        pack_root=pack_root,
        db_path=tmp_path / "app.db",
        crm_gap_csv=crm_gap,
        db_compare_csv=db_gap,
        output_dir=output_dir,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert (output_dir / "promotion_delta_orders.csv").exists()
