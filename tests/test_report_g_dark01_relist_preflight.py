from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from scripts.report_g_dark01_relist_preflight import build_relist_preflight


HEADERS = ["SKU", "model", "brand", "price", "PP1", "PP2", "PP3", "PP4", "PP5", "preorder"]


def _write_pricelist(path: Path, rows: list[dict[str, str]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Лист1"
    ws.append(HEADERS)
    for row in rows:
        ws.append([row.get(header, "") for header in HEADERS])
    wb.save(path)


def _write_offer_state(path: Path) -> None:
    fieldnames = [
        "family_id",
        "sku_key",
        "size",
        "current_stock",
        "excluded_by_decision",
        "should_be_buyable",
        "active_available_offer_count",
        "store_ids",
        "merchant_skus",
        "links",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "family_id": "RUSH_WHITE",
                "sku_key": "SKU_KEY",
                "size": "S",
                "current_stock": "14",
                "status": "MISSING_BUYABLE",
            }
        )
        writer.writerow(
            {
                "family_id": "RUSH_WHITE",
                "sku_key": "SKU_KEY",
                "size": "L",
                "current_stock": "0",
                "status": "EXCLUDED_OR_ZERO_STOCK_BUYABLE",
            }
        )


def test_relist_preflight_blocks_missing_positive_rows_and_builds_off_update(tmp_path: Path) -> None:
    offer_state = tmp_path / "offer_state.csv"
    _write_offer_state(offer_state)
    active = tmp_path / "active.xlsx"
    archive = tmp_path / "archive.xlsx"
    _write_pricelist(
        active,
        [
            {
                "SKU": "SKU_KEY_L_1",
                "price": "14990",
                "PP1": "500",
                "PP2": "no",
                "PP3": "no",
                "PP4": "no",
                "PP5": "no",
                "preorder": "0",
            }
        ],
    )
    _write_pricelist(archive, [])

    report = build_relist_preflight(
        offer_state_csv=offer_state,
        store_files={
            "UNIVERSAL": {"ACTIVE": active, "ARCHIVE": archive},
            "STORE-B": {"ACTIVE": active, "ARCHIVE": archive},
        },
        output_root=tmp_path / "out",
        generated_at="2026-06-18T20:50:00+05:00",
    )

    assert report["status"] == "BLOCKED_NO_WRITE"
    assert report["missing_platform_rows"] == ["SKU_KEY:S"]
    assert report["active_off_candidate_skus"] == ["SKU_KEY_L_1"]
    assert report["safe_full_action_apply_allowed"] is False
    assert Path(report["off_updates_csv_by_store"]["UNIVERSAL"]).exists()


def test_relist_preflight_allows_review_when_archive_row_exists(tmp_path: Path) -> None:
    offer_state = tmp_path / "offer_state.csv"
    _write_offer_state(offer_state)
    active = tmp_path / "active.xlsx"
    archive = tmp_path / "archive.xlsx"
    _write_pricelist(active, [{"SKU": "SKU_KEY_L_1", "price": "14990", "PP1": "500"}])
    _write_pricelist(archive, [{"SKU": "SKU_KEY_S_1", "price": "14990", "PP1": "no"}])

    report = build_relist_preflight(
        offer_state_csv=offer_state,
        store_files={
            "UNIVERSAL": {"ACTIVE": active, "ARCHIVE": archive},
            "STORE-B": {"ACTIVE": active, "ARCHIVE": archive},
        },
        output_root=tmp_path / "out",
        generated_at="2026-06-18T20:51:00+05:00",
    )

    assert report["status"] == "READY_FOR_REVIEW"
    assert report["missing_platform_rows"] == []
    assert report["archive_activation_candidate_skus"] == ["SKU_KEY_S_1"]
