from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
import pytest

from scripts.sync_transaction_receipts import (
    EXPECTED_LOCAL_RECEIPT_TOTAL_CNY,
    OWNER_CONFIRMED_UNRECORDED_RESERVE_KZT,
    RECEIPT_FOLDERS,
    build_patch_plan,
    build_registry,
    extract_latest_cash_balances_snapshot,
    parse_receipt_filename,
    remaining_allocation_after_local_receipts,
    totals_by_folder,
    validate_registry,
)


FILES_BY_FOLDER = {
    "PO_4_7.1.26": [
        "1_5000_PO_4.0.png",
        "2_5000_PO_4.0.png",
        "3_5000_PO_4.0.png",
        "4_5000_PO_4.0.png",
        "5_5100_PO_4.0.png",
        "6_5314_PO_4.0.png",
        "7_5313_PO_4.0.png",
        "8_5694_PO_4.0.png",
        "9_5500_PO_4.0.png",
        "10_5000_PO_4.0.png",
        "11_5500_PO_4.0.png",
        "12_5000_PO_4.0.png",
        "13_5000_PO_4.0.png",
    ],
    "PO_4.1_21.01.2026": [
        "1_5000_PO_4.1.png",
        "2_5000_PO_4.1.png",
        "3_5000_PO_4.1.png",
        "4_5500_PO_4.1.png",
        "5_5500_PO_4.1.png",
        "6_5500_PO_4.1.png",
        "7_5500_PO_4.1.png",
        "8_5500_PO_4.1.png",
        "9_5500_PO_4.1.png",
        "10_5500_PO_4.1.png",
        "11_5530_PO_4.1.png",
    ],
    "PO_5.1_24.03.2026": [
        "1_5000_PO_5.png",
        "2_5000_PO_5.png",
        "3_5000_PO_5.png",
        "4_5000_PO_5.png",
        "5_5000_PO_5.png",
        "6_5000_PO_5.png",
        "7_7000_PO_5.png",
        "8_7000_PO_5.png",
        "9_7000_PO_5.png",
        "10_7000_28.4.26_PO_5.png",
        "11_7000_28.4.26_PO_5.png",
        "12_7000_20.05.2026_23_01_45_PO_5.png",
        "13_7000_24.05.2026_13_45_28_PO_5.png",
        "14_6000_24.05.2026_14_53_00_PO_5.png",
        "15_7000_24.05.2026_20_53_00_PO_5.png",
        "16_6800_25.05.2026_23_03_00_PO_5.png",
    ],
}


def make_receipt_root(tmp_path: Path) -> Path:
    root = tmp_path / "Transactions"
    for folder, files in FILES_BY_FOLDER.items():
        folder_path = root / folder
        folder_path.mkdir(parents=True)
        for file_name in files:
            (folder_path / file_name).write_bytes(f"{folder}/{file_name}".encode())
    return root


def test_filename_amount_and_date_time_parsing() -> None:
    parsed = parse_receipt_filename("12_7000_20.05.2026_23_01_45_PO_5.png")

    assert parsed.sequence == 12
    assert parsed.amount_cny == Decimal("7000")
    assert parsed.payment_date == "2026-05-20"
    assert parsed.payment_time == "23:01:45"
    assert parsed.po_label == "PO-5"


def test_short_filename_date_parsing() -> None:
    parsed = parse_receipt_filename("10_7000_28.4.26_PO_5.png")

    assert parsed.payment_date == "2026-04-28"
    assert parsed.payment_time == ""


def test_folder_amount_totals_and_local_total(tmp_path: Path) -> None:
    root = make_receipt_root(tmp_path)
    rows, _manifest = build_registry(root, tmp_path / "missing.xlsx")
    totals = totals_by_folder(rows)

    for folder, expected in RECEIPT_FOLDERS.items():
        assert totals[folder]["file_count"] == expected["expected_count"]
        assert Decimal(totals[folder]["amount_cny"]) == expected["expected_total_cny"]
    assert sum(Decimal(row["amount_cny_from_filename"]) for row in rows) == EXPECTED_LOCAL_RECEIPT_TOTAL_CNY


def test_owner_confirmed_po5_duplicate_override(tmp_path: Path) -> None:
    root = make_receipt_root(tmp_path)
    rows, _manifest = build_registry(root, tmp_path / "missing.xlsx")
    status_by_file = {row["file_name"]: row["dedupe_status"] for row in rows}

    assert status_by_file["4_5000_PO_5.png"] == "OWNER_CONFIRMED_DISTINCT"
    assert status_by_file["5_5000_PO_5.png"] == "OWNER_CONFIRMED_DISTINCT"


def test_po6_0a_remaining_debt_handling() -> None:
    remaining = remaining_allocation_after_local_receipts()

    assert remaining["PO-5.2"] == "60421"
    assert remaining["PO-6.0a"] == "3000"
    assert remaining["PO-6.0b"] == "11680"


def test_validation_fails_on_bad_total(tmp_path: Path) -> None:
    root = make_receipt_root(tmp_path)
    rows, _manifest = build_registry(root, tmp_path / "missing.xlsx")
    rows[0]["amount_cny_from_filename"] = "1"
    patch_plan = build_patch_plan(rows, tmp_path / "missing_inbound.xlsx", tmp_path / "missing_po.xlsx")

    with pytest.raises(Exception, match="validation failed"):
        validate_registry(rows, len(rows), patch_plan)


def test_kzt_is_not_primary_payment_truth(tmp_path: Path) -> None:
    root = make_receipt_root(tmp_path)
    rows, _manifest = build_registry(root, tmp_path / "missing.xlsx")
    patch_plan = build_patch_plan(rows, tmp_path / "missing_inbound.xlsx", tmp_path / "missing_po.xlsx")
    results = validate_registry(rows, len(rows), patch_plan)

    assert patch_plan["ledger_derived_formulas"]["primary_payment_currency"] == "CNY"
    assert all(row["kzt_source"] == "estimated_fx" for row in rows)
    assert {row["status"] for row in results} == {"PASS"}


def test_latest_cash_balances_snapshot_ingests_unrecorded_reserve(tmp_path: Path) -> None:
    workbook_path = tmp_path / "Inbound_calendar_V10.002.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Cash_Balances"
    ws.append(["CASH BALANCES — MANUAL SNAPSHOT LOG"])
    ws.append([])
    ws.append(["", "", "", "", ""])
    ws.append(["Store", "Account", "Currency", "26.05.2026_11_44_41", "27.05.2026_17_03_55"])
    ws.append(["UNIVERSAL", "kaspi_gold", "KZT", 2019000, 1937000])
    ws.append(["UNIVERSAL", "cash_usd", "USD", 548, 548])
    ws.append([])
    ws.append(["STORE TOTALS (KZT only)", "", "", "", ""])
    ws.append(["UNIVERSAL", "", "", 2284780, 2202780])
    ws.append([])
    ws.append(["CURRENCY TOTALS", "FX Rate", "Amount", "KZT Equiv", "KZT Equiv"])
    ws.append(["KZT", 1, 2019000, 2019000, 1937000])
    ws.append(["USD", 485, 548, 265780, 265780])
    ws.append([])
    ws.append(["GRAND TOTAL KZT", "", "", 2284780, 2202780])
    wb.save(workbook_path)

    snapshot = extract_latest_cash_balances_snapshot(workbook_path)

    assert snapshot["snapshot_timestamp"] == "27.05.2026_17_03_55"
    assert snapshot["workbook_recorded_grand_total_kzt"] == "2202780"
    assert snapshot["owner_confirmation"]["unrecorded_reserve_kzt"] == str(
        int(OWNER_CONFIRMED_UNRECORDED_RESERVE_KZT)
    )
    assert snapshot["cash_including_owner_unrecorded_reserve_kzt"] == "3702780"
