from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.build_webui_shipped_projection import build_webui_shipped_projection


def _write_pack(pack_root: Path) -> None:
    pack_root.mkdir(parents=True, exist_ok=True)
    rows = pd.DataFrame(
        [
            {
                "pack_id": "pack_a",
                "store_code": "ACMEWEAR",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "source_file_sha256": "sha",
                "source_file_format": "xlsx",
                "source_row_number": 2,
                "order_id": "1001",
                "created_at": "2026-01-01",
                "status_change_at": "2026-01-04",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "quantity": 1.0,
                "net_rev_kzt": 1000.0,
                "warehouse_code": "ACMEWEAR",
                "article": "SKU-1",
                "kaspi_offer_name": "Offer 1",
                "seller_system_name": "Offer 1",
                "category": "",
                "pickup_or_delivery_address": "",
                "cancel_reason": "",
                "payment_mode": "",
                "delivery_mode": "",
                "courier_service": "",
                "planned_courier_at": "2026-01-02",
                "delivery_fee_buyer_kzt": 0.0,
                "delivery_fee_seller_kzt": 0.0,
                "transaction_signature_required": "",
                "status_change_required": True,
                "status_change_missing": False,
                "row_fingerprint": "fp-1",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
            },
            {
                "pack_id": "pack_a",
                "store_code": "ACMEWEAR",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "source_file_sha256": "sha",
                "source_file_format": "xlsx",
                "source_row_number": 3,
                "order_id": "1002",
                "created_at": "2026-01-03",
                "status_change_at": "2026-01-05",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "quantity": 2.0,
                "net_rev_kzt": 2200.0,
                "warehouse_code": "ACMEWEAR",
                "article": "SKU-2",
                "kaspi_offer_name": "Offer 2",
                "seller_system_name": "Offer 2",
                "category": "",
                "pickup_or_delivery_address": "",
                "cancel_reason": "",
                "payment_mode": "",
                "delivery_mode": "",
                "courier_service": "",
                "planned_courier_at": "",
                "delivery_fee_buyer_kzt": 0.0,
                "delivery_fee_seller_kzt": 0.0,
                "transaction_signature_required": "",
                "status_change_required": True,
                "status_change_missing": False,
                "row_fingerprint": "fp-2",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
            },
            {
                "pack_id": "pack_a",
                "store_code": "ACMEWEAR",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "source_file_sha256": "sha",
                "source_file_format": "xlsx",
                "source_row_number": 4,
                "order_id": "1003",
                "created_at": "2026-01-05",
                "status_change_at": "2026-01-07",
                "status_raw": "Выдан",
                "status_internal": "DELIVERED",
                "quantity": 1.0,
                "net_rev_kzt": 1300.0,
                "warehouse_code": "ACMEWEAR",
                "article": "SKU-3",
                "kaspi_offer_name": "Offer 3",
                "seller_system_name": "Offer 3",
                "category": "",
                "pickup_or_delivery_address": "",
                "cancel_reason": "",
                "payment_mode": "",
                "delivery_mode": "",
                "courier_service": "",
                "planned_courier_at": "2026-01-06",
                "delivery_fee_buyer_kzt": 0.0,
                "delivery_fee_seller_kzt": 0.0,
                "transaction_signature_required": "",
                "status_change_required": True,
                "status_change_missing": False,
                "row_fingerprint": "fp-3",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
            },
        ]
    )
    rows.to_csv(pack_root / "normalized_rows.csv", index=False, encoding="utf-8")
    (pack_root / "source_manifest.json").write_text(
        json.dumps(
            {
                "pack_id": "pack_a",
                "pack_root": str(pack_root),
                "files": [
                    {
                        "store_code": "ACMEWEAR",
                        "window_since": "2026-01-01",
                        "window_until": "2026-01-31",
                        "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_ledger(ledger_root: Path, pack_root: Path) -> None:
    ledger_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "store_code": "ACMEWEAR",
                "order_id": "1001",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-01-04",
                "created_at": "2026-01-01",
                "delivered_at": "2026-01-04",
                "returned_at": "",
                "source_pack_id": "pack_a",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "first_seen_pack": "pack_a",
                "last_seen_pack": "pack_a",
                "lineage_source_count": 1,
                "row_fingerprint": "fp-1",
            },
            {
                "store_code": "ACMEWEAR",
                "order_id": "1002",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-01-05",
                "created_at": "2026-01-03",
                "delivered_at": "2026-01-05",
                "returned_at": "",
                "source_pack_id": "pack_a",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "first_seen_pack": "pack_a",
                "last_seen_pack": "pack_a",
                "lineage_source_count": 1,
                "row_fingerprint": "fp-2",
            },
            {
                "store_code": "ACMEWEAR",
                "order_id": "1003",
                "status_internal": "RETURNED",
                "status_change_at": "2026-01-08",
                "created_at": "2026-01-05",
                "delivered_at": "2026-01-07",
                "returned_at": "2026-01-08",
                "source_pack_id": "pack_a",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                "first_seen_pack": "pack_a",
                "last_seen_pack": "pack_a",
                "lineage_source_count": 1,
                "row_fingerprint": "fp-3",
            },
        ]
    ).to_csv(ledger_root / "webui_status_ledger.csv", index=False, encoding="utf-8")
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "ledger_a",
                "pack_roots": [str(pack_root)],
                "pack_ids": ["pack_a"],
                "pack_windows": [
                    {
                        "pack_id": "pack_a",
                        "store_code": "ACMEWEAR",
                        "window_since": "2026-01-01",
                        "window_until": "2026-01-31",
                        "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR.xlsx",
                    }
                ],
                "ledger_row_count": 3,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_webui_shipped_projection_uses_planned_courier_or_created_fallback(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    ledger_root = tmp_path / "ledger"
    output_root = tmp_path / "projection"
    _write_pack(pack_root)
    _write_ledger(ledger_root, pack_root)

    report = build_webui_shipped_projection(
        ledger_root=ledger_root,
        output_root=output_root,
        run_id="webui_shipped_projection_test",
        start="2026-01-01",
        end="2026-01-31",
    )

    projection = pd.read_csv(report["projection_csv"], dtype=object, keep_default_na=False)
    assert projection["order_id"].tolist() == ["1001", "1002"]
    assert projection.loc[projection["order_id"] == "1001", "sale_date"].item() == "2026-01-02"
    assert projection.loc[projection["order_id"] == "1002", "sale_date"].item() == "2026-01-03"
    assert set(projection["event_date_source"]) == {"planned_courier_at", "created_at_fallback"}
    assert report["projection_manifest"]["orders_returned_excluded"] == 1
    assert report["projection_manifest"]["projected_orders"] == 2
