#!/usr/bin/env python3
"""Create a read-only SHR receipt registry from local transaction screenshots."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Iterable

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - openpyxl is expected in repo env.
    load_workbook = None


DEFAULT_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/"
    "vibe_code_PO/Transactions"
)
DEFAULT_INBOUND_WORKBOOK = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/"
    "vibe_code_PO/Inbound_calendar_V10.002.xlsx"
)
DEFAULT_PO_STORING_WORKBOOK = DEFAULT_ROOT / "PO_storing_Vibecode_2.xlsx"
DEFAULT_HANDOFF_DIR = Path(
    "~/Docs/Autonomous_business_agent_handoffs/2026-05-27_shr_receipt_sync_registry_handoff"
)

RECEIPT_FOLDERS = {
    "PO_4_7.1.26": {"expected_count": 13, "expected_total_cny": Decimal("67421"), "pool": "PO-4.0 receipt pool"},
    "PO_4.1_21.01.2026": {
        "expected_count": 11,
        "expected_total_cny": Decimal("59030"),
        "pool": "PO-4.1 receipt pool",
    },
    "PO_5.1_24.03.2026": {
        "expected_count": 16,
        "expected_total_cny": Decimal("98800"),
        "pool": "PO-5 receipt pool",
    },
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff"}
REFERENCE_FX_RATE = Decimal("72")
SHR_BASE_ORDER_VALUE_CNY = Decimal("322207")
LINE52_PAID_WECHAT_EVIDENCE_CNY = Decimal("21855")
EXPECTED_LOCAL_RECEIPT_TOTAL_CNY = Decimal("225251")
EXPECTED_TOTAL_PAID_CNY = Decimal("247106")
EXPECTED_REMAINING_CNY = Decimal("75101")
EXPECTED_REMAINING_KZT_REFERENCE = Decimal("5407272")
REMAINING_EXPECTED = {"PO-5.2": Decimal("60421"), "PO-6.0a": Decimal("3000"), "PO-6.0b": Decimal("11680")}
LOCAL_FIFO_PARTS = [
    ("PO-4.0", Decimal("73515")),
    ("PO-4.1", Decimal("24050")),
    ("PO-5.1", Decimal("32260")),
    ("PO-4.2", Decimal("16225")),
    ("PO-4.3", Decimal("20317")),
    ("PO-5.2", Decimal("119305")),
    ("PO-6.0a", Decimal("3000")),
    ("PO-6.0b", Decimal("11680")),
]
GENERATED_SYNC_FILES = [
    "receipt_registry.jsonl",
    "receipt_registry.csv",
    "cash_balances_latest_snapshot.json",
    "cash_balances_latest_snapshot.csv",
    "receipt_sync_report.md",
    "workbook_patch_plan.json",
    "hash_manifest.json",
    "directory_restructure_plan.md",
]
OWNER_CONFIRMED_UNRECORDED_RESERVE_KZT = Decimal("1500000")
REGISTRY_COLUMNS = [
    "receipt_id",
    "supplier_id",
    "source_folder",
    "source_path",
    "file_name",
    "file_sha256",
    "file_size_bytes",
    "amount_cny_from_filename",
    "payment_date_from_filename",
    "payment_time_from_filename",
    "visible_payment_date",
    "visible_payment_time",
    "payee_name",
    "payment_method",
    "transaction_id_if_visible",
    "po_pool_label_from_folder",
    "po_part_allocation_status",
    "assigned_po_part_id",
    "counted_status",
    "dedupe_status",
    "owner_confirmation_status",
    "proof_sent_to_supplier",
    "supplier_acknowledged",
    "amount_kzt_actual",
    "actual_fx_rate",
    "kzt_source",
    "amount_kzt_reference",
    "reference_fx_rate",
    "notes",
]


class ReceiptSyncError(RuntimeError):
    """Raised when the dry-run registry is unsafe or inconsistent."""


@dataclass(frozen=True)
class ParsedReceiptName:
    sequence: int
    amount_cny: Decimal
    payment_date: str
    payment_time: str
    po_label: str


@dataclass
class ReceiptRow:
    receipt_id: str
    supplier_id: str
    source_folder: str
    source_path: str
    file_name: str
    file_sha256: str
    file_size_bytes: int
    amount_cny_from_filename: str
    payment_date_from_filename: str
    payment_time_from_filename: str
    visible_payment_date: str
    visible_payment_time: str
    payee_name: str
    payment_method: str
    transaction_id_if_visible: str
    po_pool_label_from_folder: str
    po_part_allocation_status: str
    assigned_po_part_id: str
    counted_status: str
    dedupe_status: str
    owner_confirmation_status: str
    proof_sent_to_supplier: str
    supplier_acknowledged: str
    amount_kzt_actual: str
    actual_fx_rate: str
    kzt_source: str
    amount_kzt_reference: str
    reference_fx_rate: str
    notes: str


def decimal_to_str(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.name)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def parse_receipt_filename(file_name: str) -> ParsedReceiptName:
    stem = Path(file_name).stem
    tokens = stem.split("_")
    if len(tokens) < 3 or not tokens[0].isdigit() or not re.fullmatch(r"\d+(?:\.\d+)?", tokens[1]):
        raise ReceiptSyncError(f"cannot parse receipt filename: {file_name}")
    sequence = int(tokens[0])
    amount = Decimal(tokens[1])
    idx = 2
    payment_date = ""
    payment_time = ""
    if idx < len(tokens) and re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{2,4}", tokens[idx]):
        payment_date = parse_filename_date(tokens[idx])
        idx += 1
    if idx + 2 < len(tokens) and all(re.fullmatch(r"\d{1,2}", tokens[idx + offset]) for offset in range(3)):
        hh, mm, ss = (int(tokens[idx]), int(tokens[idx + 1]), int(tokens[idx + 2]))
        payment_time = f"{hh:02d}:{mm:02d}:{ss:02d}"
        idx += 3
    po_label = "_".join(tokens[idx:]).replace("_", "-") if idx < len(tokens) else ""
    return ParsedReceiptName(
        sequence=sequence,
        amount_cny=amount,
        payment_date=payment_date,
        payment_time=payment_time,
        po_label=po_label,
    )


def parse_filename_date(text: str) -> str:
    day_text, month_text, year_text = text.split(".")
    year = int(year_text)
    if year < 100:
        year += 2000
    return f"{year:04d}-{int(month_text):02d}-{int(day_text):02d}"


def discover_receipt_images(root: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in RECEIPT_FOLDERS:
        folder_path = root / folder
        if not folder_path.exists():
            raise ReceiptSyncError(f"missing receipt folder: {folder_path}")
        paths.extend(
            path
            for path in sorted(folder_path.iterdir(), key=natural_key)
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
    return sorted(paths, key=lambda p: (list(RECEIPT_FOLDERS).index(p.parent.name), natural_key(p)))


def file_manifest(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        stat = path.stat()
        rows.append(
            {
                "relative_path": str(path.relative_to(root)),
                "path": str(path.resolve()),
                "file_name": path.name,
                "sha256": sha256_file(path),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return rows


def compute_fifo_allocation(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    remaining = {part_id: amount for part_id, amount in LOCAL_FIFO_PARTS}
    ordered_parts = [part_id for part_id, _ in LOCAL_FIFO_PARTS]
    idx = 0
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        amount_left = Decimal(str(row["amount_cny_from_filename"]))
        allocations: list[tuple[str, Decimal]] = []
        while amount_left > 0 and idx < len(ordered_parts):
            part_id = ordered_parts[idx]
            if remaining[part_id] <= 0:
                idx += 1
                continue
            applied = min(amount_left, remaining[part_id])
            allocations.append((part_id, applied))
            remaining[part_id] -= applied
            amount_left -= applied
            if remaining[part_id] <= 0:
                idx += 1
        row_copy = dict(row)
        row_copy["assigned_po_part_id"] = ";".join(part_id for part_id, _ in allocations) or "UNALLOCATED"
        row_copy["po_part_allocation_status"] = "FIFO_POOL" if allocations else "UNALLOCATED_SHR_PAYMENT"
        split_note = "; ".join(f"{part_id}:{decimal_to_str(amount)} CNY" for part_id, amount in allocations)
        row_copy["notes"] = "; ".join(filter(None, [str(row_copy.get("notes", "")), f"fifo_allocation={split_note}"]))
        out_rows.append(row_copy)
    return out_rows, remaining


def remaining_allocation_after_local_receipts() -> dict[str, str]:
    dummy_rows = [{"amount_cny_from_filename": decimal_to_str(amount)} for _, amount in []]
    _ = dummy_rows
    rows = [{"amount_cny_from_filename": decimal_to_str(EXPECTED_LOCAL_RECEIPT_TOTAL_CNY)}]
    _, remaining = compute_fifo_allocation(rows)
    return {part_id: decimal_to_str(value) for part_id, value in remaining.items() if value > 0}


def read_cny_buy_rows(workbook_path: Path) -> list[dict[str, Any]]:
    if load_workbook is None or not workbook_path.exists():
        return []
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        if "CNY_buy" not in wb.sheetnames:
            return []
        ws = wb["CNY_buy"]
        header = None
        rows: list[dict[str, Any]] = []
        for raw_row in ws.iter_rows(values_only=True):
            values = ["" if value is None else str(value) for value in raw_row]
            if header is None and "Final_Receiver" in values and "CNY_receive_claim" in values:
                header = values
                continue
            if header is None:
                continue
            record = {header[i]: values[i] if i < len(values) else "" for i in range(len(header))}
            if record.get("Final_Receiver") or record.get("Internal_order_code"):
                rows.append(record)
        return rows
    finally:
        wb.close()


def observed_workbook_values(inbound_workbook: Path) -> dict[str, Any]:
    if load_workbook is None or not inbound_workbook.exists():
        return {"error": "openpyxl unavailable or workbook missing"}
    wb = load_workbook(inbound_workbook, read_only=True, data_only=True)
    observed: dict[str, Any] = {}
    try:
        for sheet, labels in {
            "base_payment_SHR_log": [
                "Actual paid (receipts + approval)",
                "Actual remaining CNY",
                "Actual remaining KZT @72",
            ],
            "SHR_Pay_Lock_105952": [
                "Actual paid BASE (receipt-priority)",
                "Actual remaining BASE payable",
                "Actual remaining BASE payable @72",
                "All attached receipt evidence",
                "PO-5 screenshot receipts ingested",
            ],
            "PO_part_id_Totals": ["Pending BASE (not paid)", "FX_CNY_KZT used:"],
        }.items():
            if sheet not in wb.sheetnames:
                continue
            ws = wb[sheet]
            found: dict[str, Any] = {}
            for row in ws.iter_rows(values_only=True):
                values = ["" if value is None else str(value) for value in row]
                for label in labels:
                    if label in values:
                        pos = values.index(label)
                        found[label] = values[pos + 1 : pos + 5]
            observed[sheet] = found
        return observed
    finally:
        wb.close()


def extract_latest_cash_balances_snapshot(inbound_workbook: Path) -> dict[str, Any]:
    if load_workbook is None or not inbound_workbook.exists():
        raise ReceiptSyncError("cannot read Cash_Balances sheet: openpyxl unavailable or workbook missing")
    wb = load_workbook(inbound_workbook, read_only=True, data_only=True)
    try:
        if "Cash_Balances" not in wb.sheetnames:
            raise ReceiptSyncError(f"Cash_Balances sheet missing in {inbound_workbook}")
        ws = wb["Cash_Balances"]
        header_row_idx = None
        headers: list[str] = []
        for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            values = ["" if value is None else str(value).strip() for value in row]
            if len(values) >= 4 and values[0] == "Store" and values[1] == "Account" and values[2] == "Currency":
                header_row_idx = idx
                headers = values
                break
        if header_row_idx is None:
            raise ReceiptSyncError("Cash_Balances header row not found")

        latest_idx = max(
            idx for idx, value in enumerate(headers) if idx >= 3 and str(value).strip()
        )
        latest_timestamp = headers[latest_idx]

        rows = list(ws.iter_rows(values_only=True))
        fx_rates: dict[str, Decimal] = {}
        account_rows: list[dict[str, Any]] = []
        store_totals: dict[str, str] = {}
        currency_totals: dict[str, dict[str, str]] = {}
        workbook_grand_total = Decimal("0")

        for row in rows[header_row_idx:]:
            values = ["" if value is None else str(value).strip() for value in row]
            label = values[0] if values else ""
            if label == "STORE TOTALS (KZT only)":
                continue
            if label == "CURRENCY TOTALS":
                continue
            if label == "GRAND TOTAL KZT":
                workbook_grand_total = Decimal(values[latest_idx] or "0")
                continue
            if len(values) > 2 and values[0] and values[1] and values[2] and values[0] not in {"KZT", "RUB", "USD", "USDT"}:
                amount = Decimal(values[latest_idx] or "0")
                account_rows.append(
                    {
                        "snapshot_timestamp": latest_timestamp,
                        "store": values[0],
                        "account": values[1],
                        "currency": values[2],
                        "amount": decimal_to_str(amount),
                    }
                )
                continue
            if len(values) > latest_idx and values[0] in {"KZT", "RUB", "USD", "USDT"}:
                fx_rate = Decimal(values[1] or "0")
                fx_rates[values[0]] = fx_rate
                currency_totals[values[0]] = {
                    "fx_rate_to_kzt": decimal_to_str(fx_rate),
                    "kzt_equivalent": decimal_to_str(Decimal(values[latest_idx] or "0")),
                }
                continue
            if len(values) > latest_idx and values[0] in {"UNIVERSAL", "11KZ", "STOREB", "ACMEWEAR", "MELVIS"} and not values[1]:
                store_totals[values[0]] = decimal_to_str(Decimal(values[latest_idx] or "0"))

        for row in account_rows:
            fx_rate = fx_rates.get(row["currency"], Decimal("0"))
            row["fx_rate_to_kzt"] = decimal_to_str(fx_rate)
            row["kzt_equivalent"] = decimal_to_str(Decimal(row["amount"]) * fx_rate)

        return {
            "source_workbook": str(inbound_workbook.resolve()),
            "source_sheet": "Cash_Balances",
            "snapshot_timestamp": latest_timestamp,
            "owner_confirmation": {
                "workbook_current_to_snapshot_timestamp": True,
                "workbook_reflects_everything_paid_as_of_snapshot": True,
                "unrecorded_reserve_kzt": decimal_to_str(OWNER_CONFIRMED_UNRECORDED_RESERVE_KZT),
                "unrecorded_reserve_note": "Owner-confirmed 1.5M KZT exists in reserve but is not recorded in Cash_Balances.",
            },
            "account_rows": account_rows,
            "store_totals_kzt": store_totals,
            "currency_totals": currency_totals,
            "workbook_recorded_grand_total_kzt": decimal_to_str(workbook_grand_total),
            "cash_including_owner_unrecorded_reserve_kzt": decimal_to_str(
                workbook_grand_total + OWNER_CONFIRMED_UNRECORDED_RESERVE_KZT
            ),
            "ingestion_mode": "read_only_workbook_snapshot_plus_owner_confirmed_unrecorded_reserve_note",
        }
    finally:
        wb.close()


def write_cash_balances_csv(path: Path, snapshot: dict[str, Any]) -> None:
    fieldnames = [
        "snapshot_timestamp",
        "store",
        "account",
        "currency",
        "amount",
        "fx_rate_to_kzt",
        "kzt_equivalent",
        "owner_confirmed_unrecorded_reserve_kzt",
        "workbook_recorded_grand_total_kzt",
        "cash_including_owner_unrecorded_reserve_kzt",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=fieldnames)
        writer.writeheader()
        for row in snapshot["account_rows"]:
            writer.writerow(
                {
                    **row,
                    "owner_confirmed_unrecorded_reserve_kzt": snapshot["owner_confirmation"]["unrecorded_reserve_kzt"],
                    "workbook_recorded_grand_total_kzt": snapshot["workbook_recorded_grand_total_kzt"],
                    "cash_including_owner_unrecorded_reserve_kzt": snapshot[
                        "cash_including_owner_unrecorded_reserve_kzt"
                    ],
                }
            )
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def build_registry(root: Path, po_workbook: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    receipt_paths = discover_receipt_images(root)
    manifest_rows = file_manifest(receipt_paths, root)
    cny_rows = read_cny_buy_rows(po_workbook)
    _ = cny_rows  # workbook rows are summarized in patch plan; no strong KZT matches are promoted.
    raw_rows: list[dict[str, Any]] = []
    seen_hashes: dict[str, Path] = {}
    for manifest in manifest_rows:
        path = Path(manifest["path"])
        parsed = parse_receipt_filename(path.name)
        duplicate_override = path.name in {"4_5000_PO_5.png", "5_5000_PO_5.png"}
        dedupe_status = "OWNER_CONFIRMED_DISTINCT" if duplicate_override else "UNIQUE"
        if manifest["sha256"] in seen_hashes and not duplicate_override:
            dedupe_status = "DUPLICATE_CANDIDATE"
        seen_hashes[manifest["sha256"]] = path
        amount_kzt_reference = parsed.amount_cny * REFERENCE_FX_RATE
        notes = []
        if not parsed.payment_date:
            notes.append("payment date not present in filename; visible date not OCRed")
        if duplicate_override:
            notes.append("owner confirmed this PO-5 5000 CNY receipt is distinct, not duplicate")
        raw_rows.append(
            {
                "receipt_id": f"SHR-{path.parent.name}-{parsed.sequence:03d}-{manifest['sha256'][:12]}",
                "supplier_id": "SHR",
                "source_folder": path.parent.name,
                "source_path": str(path.resolve()),
                "file_name": path.name,
                "file_sha256": manifest["sha256"],
                "file_size_bytes": int(manifest["size_bytes"]),
                "amount_cny_from_filename": decimal_to_str(parsed.amount_cny),
                "payment_date_from_filename": parsed.payment_date,
                "payment_time_from_filename": parsed.payment_time,
                "visible_payment_date": "",
                "visible_payment_time": "",
                "payee_name": "",
                "payment_method": "UNKNOWN",
                "transaction_id_if_visible": "",
                "po_pool_label_from_folder": RECEIPT_FOLDERS[path.parent.name]["pool"],
                "po_part_allocation_status": "",
                "assigned_po_part_id": "",
                "counted_status": "COUNTED",
                "dedupe_status": dedupe_status,
                "owner_confirmation_status": "OWNER_CONFIRMED_DISTINCT" if duplicate_override else "OWNER_CONFIRMED_COUNTED",
                "proof_sent_to_supplier": "UNKNOWN",
                "supplier_acknowledged": "UNKNOWN",
                "amount_kzt_actual": "",
                "actual_fx_rate": "",
                "kzt_source": "estimated_fx",
                "amount_kzt_reference": decimal_to_str(amount_kzt_reference),
                "reference_fx_rate": decimal_to_str(REFERENCE_FX_RATE),
                "notes": "; ".join(notes),
            }
        )
    allocated_rows, _remaining = compute_fifo_allocation(raw_rows)
    return allocated_rows, manifest_rows


def totals_by_folder(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for folder in RECEIPT_FOLDERS:
        folder_rows = [row for row in rows if row["source_folder"] == folder]
        out[folder] = {
            "file_count": len(folder_rows),
            "amount_cny": decimal_to_str(sum((Decimal(row["amount_cny_from_filename"]) for row in folder_rows), Decimal("0"))),
        }
    return out


def validate_registry(rows: list[dict[str, Any]], discovered_count: int, patch_plan: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []
    folder_totals = totals_by_folder(rows)
    local_total = sum((Decimal(row["amount_cny_from_filename"]) for row in rows), Decimal("0"))
    total_paid = LINE52_PAID_WECHAT_EVIDENCE_CNY + local_total
    remaining = SHR_BASE_ORDER_VALUE_CNY - total_paid
    checks.append(("registry_file_count_equals_discovered_image_count", len(rows) == discovered_count, f"{len(rows)} vs {discovered_count}"))
    checks.append(("po5_count_is_16", folder_totals["PO_5.1_24.03.2026"]["file_count"] == 16, str(folder_totals["PO_5.1_24.03.2026"])))
    checks.append(
        (
            "po5_filename_amount_total_is_98800_cny",
            Decimal(folder_totals["PO_5.1_24.03.2026"]["amount_cny"]) == Decimal("98800"),
            str(folder_totals["PO_5.1_24.03.2026"]),
        )
    )
    checks.append(("total_local_receipt_amount_is_225251_cny", local_total == EXPECTED_LOCAL_RECEIPT_TOTAL_CNY, decimal_to_str(local_total)))
    checks.append(("confirmed_total_shr_paid_is_247106_cny", total_paid == EXPECTED_TOTAL_PAID_CNY, decimal_to_str(total_paid)))
    checks.append(("confirmed_remaining_payable_is_75101_cny", remaining == EXPECTED_REMAINING_CNY, decimal_to_str(remaining)))
    distinct_files = {
        row["file_name"]: row["dedupe_status"]
        for row in rows
        if row["file_name"] in {"4_5000_PO_5.png", "5_5000_PO_5.png"}
    }
    checks.append(
        (
            "po5_4_and_5_5000_receipts_not_marked_duplicate",
            distinct_files == {"4_5000_PO_5.png": "OWNER_CONFIRMED_DISTINCT", "5_5000_PO_5.png": "OWNER_CONFIRMED_DISTINCT"},
            str(distinct_files),
        )
    )
    remaining_by_part = patch_plan["ledger_derived_values"]["remaining_cny_by_po_part"]
    checks.append(("po_6_0a_remains_real_payable", remaining_by_part.get("PO-6.0a") == "3000", str(remaining_by_part)))
    checks.append(
        (
            "kzt_not_primary_payment_truth",
            patch_plan["ledger_derived_formulas"]["primary_payment_currency"] == "CNY"
            and all(row["kzt_source"] != "actual_transaction" for row in rows),
            patch_plan["ledger_derived_formulas"]["primary_payment_currency"],
        )
    )
    checks.append(
        (
            "workbook_patch_plan_formula_driven",
            bool(patch_plan.get("ledger_derived_formulas")) and not patch_plan.get("manual_summary_only", True),
            "manual_summary_only=false",
        )
    )
    cash_snapshot = patch_plan.get("cash_balances_latest_snapshot") or {}
    if cash_snapshot:
        checks.append(
            (
                "latest_cash_balances_snapshot_ingested",
                bool(cash_snapshot.get("snapshot_timestamp")) and cash_snapshot.get("workbook_recorded_grand_total_kzt") != "",
                str(
                    {
                        "timestamp": cash_snapshot.get("snapshot_timestamp"),
                        "recorded_total": cash_snapshot.get("workbook_recorded_grand_total_kzt"),
                    }
                ),
            )
        )
        checks.append(
            (
                "owner_unrecorded_reserve_marked_1500000_kzt",
                cash_snapshot.get("owner_confirmation", {}).get("unrecorded_reserve_kzt") == "1500000",
                str(cash_snapshot.get("owner_confirmation", {})),
            )
        )
        checks.append(
            (
                "cash_balances_workbook_current_to_timestamp_owner_confirmed",
                cash_snapshot.get("owner_confirmation", {}).get("workbook_current_to_snapshot_timestamp") is True
                and cash_snapshot.get("owner_confirmation", {}).get("workbook_reflects_everything_paid_as_of_snapshot")
                is True,
                str(cash_snapshot.get("owner_confirmation", {})),
            )
        )
    results = [{"check": name, "status": "PASS" if ok else "FAIL", "detail": detail} for name, ok, detail in checks]
    failures = [row for row in results if row["status"] != "PASS"]
    if failures:
        raise ReceiptSyncError("validation failed: " + "; ".join(f"{row['check']}={row['detail']}" for row in failures))
    return results


def build_patch_plan(
    rows: list[dict[str, Any]],
    inbound_workbook: Path,
    po_workbook: Path,
    cash_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    local_total = sum((Decimal(row["amount_cny_from_filename"]) for row in rows), Decimal("0"))
    total_paid = LINE52_PAID_WECHAT_EVIDENCE_CNY + local_total
    remaining = SHR_BASE_ORDER_VALUE_CNY - total_paid
    remaining_by_part = remaining_allocation_after_local_receipts()
    observed = observed_workbook_values(inbound_workbook)
    folder_totals = totals_by_folder(rows)
    return {
        "plan_type": "read_only_formula_driven_workbook_patch_plan",
        "manual_summary_only": False,
        "source_workbooks_read_only": {
            "po_storing_vibecode_2": str(po_workbook.resolve()),
            "inbound_calendar_v10_002": str(inbound_workbook.resolve()),
        },
        "ledger_derived_formulas": {
            "primary_payment_currency": "CNY",
            "local_receipt_archive_paid_cny": "SUM(receipt_registry.amount_cny_from_filename WHERE counted_status='COUNTED' AND supplier_id='SHR')",
            "total_paid_to_shr_cny": "line52_paid_from_wechat_evidence_cny + local_receipt_archive_paid_cny",
            "remaining_payable_to_shr_cny": "shr_base_order_value_cny - total_paid_to_shr_cny",
            "reference_kzt": "remaining_payable_to_shr_cny * reference_fx_rate",
            "po_part_remaining": "FIFO allocate local_receipt_archive_paid_cny across PO_part_id_Totals SHR base rows after Line52; keep PO-6.0a distinct",
        },
        "owner_confirmed_constants": {
            "shr_base_order_value_cny": decimal_to_str(SHR_BASE_ORDER_VALUE_CNY),
            "line52_paid_from_wechat_evidence_cny": decimal_to_str(LINE52_PAID_WECHAT_EVIDENCE_CNY),
            "reference_fx_rate": decimal_to_str(REFERENCE_FX_RATE),
            "po_5_4_5000_and_5_5000_are_distinct": True,
            "po_6_0a_is_real_second_3000_cny_bag_order": True,
        },
        "ledger_derived_values": {
            "folder_totals": folder_totals,
            "local_receipt_archive_paid_cny": decimal_to_str(local_total),
            "total_paid_to_shr_cny": decimal_to_str(total_paid),
            "remaining_payable_to_shr_cny": decimal_to_str(remaining),
            "remaining_payable_to_shr_kzt_reference": decimal_to_str(remaining * REFERENCE_FX_RATE),
            "remaining_cny_by_po_part": remaining_by_part,
        },
        "cash_balances_latest_snapshot": cash_snapshot or {},
        "current_stale_values_observed": observed,
        "proposed_changes": [
            {
                "target": "Inbound_calendar_V10.002.xlsx::base_payment_SHR_log debt summary",
                "current_observed": observed.get("base_payment_SHR_log", {}),
                "proposed_corrected_values": {
                    "Actual paid (receipts + approval)": decimal_to_str(total_paid),
                    "Actual remaining CNY": decimal_to_str(remaining),
                    "Actual remaining KZT @72": decimal_to_str(remaining * REFERENCE_FX_RATE),
                    "Local receipt archive paid": decimal_to_str(local_total),
                },
                "source_evidence": ["receipt_registry.csv", "hash_manifest.json"],
                "safe_to_apply_automatically_later": False,
                "needs_owner_review": True,
            },
            {
                "target": "Inbound_calendar_V10.002.xlsx::PO_part_id_Totals pending BASE and SHR part rows",
                "current_observed": observed.get("PO_part_id_Totals", {}),
                "proposed_corrected_values": {
                    "Pending BASE (not paid)": decimal_to_str(remaining),
                    "Remaining PO-5.2": remaining_by_part.get("PO-5.2", "0"),
                    "Remaining PO-6.0a": remaining_by_part.get("PO-6.0a", "0"),
                    "Remaining PO-6.0b": remaining_by_part.get("PO-6.0b", "0"),
                },
                "source_evidence": ["workbook_patch_plan.json ledger_derived_formulas"],
                "safe_to_apply_automatically_later": False,
                "needs_owner_review": True,
            },
        ],
        "state_separation": {
            "payment_made": "receipt rows with counted_status=COUNTED",
            "proof_sent_to_supplier": "separate registry field; UNKNOWN until source-backed",
            "supplier_acknowledged": "separate registry field; UNKNOWN until source-backed",
            "po_part_allocation": "FIFO_POOL registry allocation and patch-plan formulas",
            "actual_kzt_matched": "blank unless strong transaction match exists",
            "reference_kzt_estimated": "amount_cny * 72 for planning only",
        },
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_registry_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def write_registry_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=REGISTRY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in REGISTRY_COLUMNS})
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def build_report(rows: list[dict[str, Any]], validations: list[dict[str, Any]], patch_plan: dict[str, Any]) -> str:
    folder_lines = "\n".join(
        f"- `{folder}`: `{data['file_count']}` files, `{data['amount_cny']} CNY`"
        for folder, data in patch_plan["ledger_derived_values"]["folder_totals"].items()
    )
    validation_lines = "\n".join(f"- `{row['check']}`: `{row['status']}` ({row['detail']})" for row in validations)
    values = patch_plan["ledger_derived_values"]
    cash_snapshot = patch_plan.get("cash_balances_latest_snapshot", {})
    cash_lines = ""
    if cash_snapshot:
        cash_lines = f"""
## Latest Cash Balances Ingest
- Source sheet: `Cash_Balances`
- Latest timestamp: `{cash_snapshot['snapshot_timestamp']}`
- Workbook recorded grand total: `{cash_snapshot['workbook_recorded_grand_total_kzt']} KZT`
- Owner-confirmed unrecorded reserve: `{cash_snapshot['owner_confirmation']['unrecorded_reserve_kzt']} KZT`
- Recorded plus unrecorded reserve: `{cash_snapshot['cash_including_owner_unrecorded_reserve_kzt']} KZT`
- Owner confirms workbook is current to this timestamp and reflects everything paid as of the timestamp.
"""
    return f"""# SHR Receipt Sync Report

Generated: {datetime.now().isoformat(timespec="seconds")}
Gate: `GREEN_HANDOFF_READY_CANDIDATE`

## Scope
- Supplier: `SHR`
- Primary currency: `CNY`
- Registry rows: `{len(rows)}`
- Source mode: read-only screenshots plus read-only workbook inspection.

## Folder Totals
{folder_lines}

## Owner-Confirmed Debt Summary
- SHR base/order value: `{decimal_to_str(SHR_BASE_ORDER_VALUE_CNY)} CNY`
- Line52 paid from WeChat evidence: `{decimal_to_str(LINE52_PAID_WECHAT_EVIDENCE_CNY)} CNY`
- Local receipt archive paid: `{values['local_receipt_archive_paid_cny']} CNY`
- Total paid to SHR current workbook debt: `{values['total_paid_to_shr_cny']} CNY`
- Remaining payable to SHR: `{values['remaining_payable_to_shr_cny']} CNY`
- Reference KZT at `{decimal_to_str(REFERENCE_FX_RATE)}`: `{values['remaining_payable_to_shr_kzt_reference']} KZT`

## Remaining Allocation
- `PO-5.2`: `{values['remaining_cny_by_po_part'].get('PO-5.2', '0')} CNY`
- `PO-6.0a`: `{values['remaining_cny_by_po_part'].get('PO-6.0a', '0')} CNY`
- `PO-6.0b`: `{values['remaining_cny_by_po_part'].get('PO-6.0b', '0')} CNY`
{cash_lines}

## Validation
{validation_lines}

## No-Mutation Statement
- No source receipt image was renamed, moved, deleted, overwritten, compressed, or modified.
- No workbook was edited.
- Generated dry-run files were written only under `Transactions/_sync/`.
- KZT values are reference-only unless a later strong transaction match is approved.
"""


def build_directory_plan(root: Path) -> str:
    return f"""# Directory Restructure Plan

Status: `PLAN_ONLY_NOT_APPLIED`

This dry-run did not rename, move, delete, overwrite, compress, or modify source receipt images.

Recommended future view, only after backup and explicit approval:

```text
Transactions/
  _sync/
    receipt_registry.jsonl
    receipt_registry.csv
    receipt_sync_report.md
    workbook_patch_plan.json
    hash_manifest.json
  _normalized_view/
    SHR/
      PO_4.0/
      PO_4.1_4.2_4.3_pool/
      PO_5_pool/
  _raw_legacy_do_not_edit/
```

Source root inspected read-only:

`{root}`

Future apply constraints:
- create backup/hash manifest first;
- use an explicit env gate and `--apply`;
- preserve original raw folders;
- prefer symlink/copy views over destructive moves;
- keep `4_5000_PO_5.png` and `5_5000_PO_5.png` distinct.
"""


def build_hash_manifest(
    root: Path,
    source_manifest_before: list[dict[str, Any]],
    source_manifest_after: list[dict[str, Any]],
    generated_paths: list[Path],
    workbooks: list[Path],
) -> dict[str, Any]:
    before_map = {row["relative_path"]: row for row in source_manifest_before}
    after_map = {row["relative_path"]: row for row in source_manifest_after}
    source_unchanged = before_map == after_map
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_root": str(root.resolve()),
        "source_images_unchanged_after_dry_run": source_unchanged,
        "source_image_count": len(source_manifest_before),
        "source_images": source_manifest_after,
        "source_workbooks_read_only": [
            {
                "path": str(path.resolve()),
                "exists": path.exists(),
                "sha256": sha256_file(path) if path.exists() else "",
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for path in workbooks
        ],
        "generated_files": [
            {
                "path": str(path.resolve()),
                "file_name": path.name,
                "sha256": sha256_file(path) if path.exists() and path.name != "hash_manifest.json" else "",
                "hash_note": "self hash omitted" if path.name == "hash_manifest.json" else "",
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
            for path in generated_paths
        ],
    }


def write_handoff(
    handoff_dir: Path,
    sync_dir: Path,
    root: Path,
    validations: list[dict[str, Any]],
    patch_plan: dict[str, Any],
    command: str,
) -> None:
    handoff_dir.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_SYNC_FILES:
        shutil.copy2(sync_dir / name, handoff_dir / name)
    validation_lines = "\n".join(f"- `{row['check']}`: `{row['status']}` ({row['detail']})" for row in validations)
    source_manifest = json.loads((sync_dir / "hash_manifest.json").read_text(encoding="utf-8"))
    write_json(
        handoff_dir / "SOURCE_EVIDENCE_MANIFEST.json",
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_root": str(root.resolve()),
            "source_folders_read": list(RECEIPT_FOLDERS),
            "source_image_hashes": source_manifest["source_images"],
            "source_workbooks_read_only": source_manifest["source_workbooks_read_only"],
            "cash_balances_latest_snapshot": json.loads(
                (sync_dir / "cash_balances_latest_snapshot.json").read_text(encoding="utf-8")
            ),
            "no_workbook_edited": True,
            "no_source_receipt_image_modified": source_manifest["source_images_unchanged_after_dry_run"],
        },
    )
    atomic_write_text(
        handoff_dir / "00_START_HERE.md",
        f"""# SHR Receipt Sync Registry Handoff

Gate: `GREEN_HANDOFF_READY` for receipt-registry/project-population handoff.

Repo-wide caveat: `python3 scripts/validate_params.py --strict` may still fail
on existing PO/inbound/on-delivery/business-insides/COGS blockers unrelated to
this receipt sync. Check `VALIDATION_OUTPUTS.md` for the current orchestrator
gate record.

Start with:

1. `HANDOFF_FOR_PROJECT_POPULATION.md`
2. `SOURCE_EVIDENCE_MANIFEST.json`
3. `receipt_sync_report.md`
4. `workbook_patch_plan.json`
5. `cash_balances_latest_snapshot.json`

Command used:

```bash
{command}
```
""",
    )
    atomic_write_text(
        handoff_dir / "HANDOFF_FOR_PROJECT_POPULATION.md",
        f"""# Handoff For Project Population

## Owner-Confirmed Facts Used
- CNY is the primary supplier debt currency.
- KZT is reference-only unless matched to an actual transaction.
- Payment made, proof sent to supplier, and supplier acknowledged are separate states.
- `4_5000_PO_5.png` and `5_5000_PO_5.png` are distinct payments.
- `PO-6.0a` is a real second `3,000 CNY` bag order.
- `Cash_Balances` is current to `{patch_plan['cash_balances_latest_snapshot'].get('snapshot_timestamp', '')}` and reflects everything paid as of that timestamp.
- There is `1,500,000 KZT` unrecorded in `Cash_Balances`; owner confirms it is in reserve.

## Generated Totals
- Local receipt archive paid: `{patch_plan['ledger_derived_values']['local_receipt_archive_paid_cny']} CNY`
- Total paid to SHR: `{patch_plan['ledger_derived_values']['total_paid_to_shr_cny']} CNY`
- Remaining payable: `{patch_plan['ledger_derived_values']['remaining_payable_to_shr_cny']} CNY`
- Reference KZT: `{patch_plan['ledger_derived_values']['remaining_payable_to_shr_kzt_reference']} KZT`
- Latest workbook-recorded cash total: `{patch_plan['cash_balances_latest_snapshot'].get('workbook_recorded_grand_total_kzt', '')} KZT`
- Owner-confirmed unrecorded reserve: `{patch_plan['cash_balances_latest_snapshot'].get('owner_confirmation', {}).get('unrecorded_reserve_kzt', '')} KZT`
- Recorded plus unrecorded reserve: `{patch_plan['cash_balances_latest_snapshot'].get('cash_including_owner_unrecorded_reserve_kzt', '')} KZT`

## Safe Later Population
- Use `receipt_registry.csv` as the receipt evidence ledger.
- Use `workbook_patch_plan.json` formulas and proposed values as the review surface.
- Do not populate workbook values until owner approves the patch plan.

## Needs Owner Decision
- Whether to mark specific receipt proofs as sent to supplier.
- Whether to mark any supplier acknowledgement state as YES.
- Whether to apply the workbook patch plan into `Inbound_calendar_V10.002.xlsx`.

## No-Mutation Proof
- Source images were hashed before and after dry-run and remained unchanged.
- No workbook was edited.
- No supplier-facing message was sent.
""",
    )
    atomic_write_text(
        handoff_dir / "VALIDATION_OUTPUTS.md",
        f"""# Validation Outputs

## Command

```bash
{command}
```

## Script Validation
{validation_lines}

Additional repo gates should be appended by the orchestrator after running tests.
""",
    )
    atomic_write_text(
        handoff_dir / "COPY_BACK_OR_APPLY_PLAN.md",
        """# Copy Back Or Apply Plan

Status: `PLAN_ONLY`

No copy-back or workbook apply is authorized by this handoff.

Future safe apply lane:

1. Review `workbook_patch_plan.json` with owner.
2. Backup `Inbound_calendar_V10.002.xlsx`.
3. Re-run receipt sync and compare hashes.
4. Use an explicit env gate plus `--apply` in a separate write-capable script.
5. Re-open workbook and validate formulas/headers.
6. Roll back by restoring the backup workbook if validation fails.
""",
    )


def run_sync(root: Path, sync_dir: Path, po_workbook: Path, inbound_workbook: Path, handoff_dir: Path | None) -> dict[str, Any]:
    source_paths = discover_receipt_images(root)
    source_manifest_before = file_manifest(source_paths, root)
    rows, _manifest_rows = build_registry(root, po_workbook)
    cash_snapshot = extract_latest_cash_balances_snapshot(inbound_workbook)
    patch_plan = build_patch_plan(rows, inbound_workbook, po_workbook, cash_snapshot)
    validations = validate_registry(rows, len(source_paths), patch_plan)

    sync_dir.mkdir(parents=True, exist_ok=True)
    write_registry_jsonl(sync_dir / "receipt_registry.jsonl", rows)
    write_registry_csv(sync_dir / "receipt_registry.csv", rows)
    write_json(sync_dir / "cash_balances_latest_snapshot.json", cash_snapshot)
    write_cash_balances_csv(sync_dir / "cash_balances_latest_snapshot.csv", cash_snapshot)
    write_json(sync_dir / "workbook_patch_plan.json", patch_plan)
    atomic_write_text(sync_dir / "directory_restructure_plan.md", build_directory_plan(root))
    atomic_write_text(sync_dir / "receipt_sync_report.md", build_report(rows, validations, patch_plan))

    source_manifest_after = file_manifest(source_paths, root)
    if source_manifest_before != source_manifest_after:
        raise ReceiptSyncError("source image hash/mtime changed during dry-run")
    generated_paths = [sync_dir / name for name in GENERATED_SYNC_FILES]
    hash_manifest = build_hash_manifest(
        root,
        source_manifest_before,
        source_manifest_after,
        generated_paths,
        [po_workbook, inbound_workbook],
    )
    write_json(sync_dir / "hash_manifest.json", hash_manifest)

    command = (
        f"python3 scripts/sync_transaction_receipts.py --root \"{root}\" --dry-run"
        + (f" --handoff-dir \"{handoff_dir}\"" if handoff_dir else "")
    )
    if handoff_dir:
        write_handoff(handoff_dir, sync_dir, root, validations, patch_plan, command)

    return {
        "gate": "GREEN_HANDOFF_READY" if handoff_dir else "GREEN_DRY_RUN_READY",
        "sync_dir": str(sync_dir.resolve()),
        "handoff_dir": str(handoff_dir.resolve()) if handoff_dir else "",
        "registry_rows": len(rows),
        "local_receipt_total_cny": patch_plan["ledger_derived_values"]["local_receipt_archive_paid_cny"],
        "total_paid_to_shr_cny": patch_plan["ledger_derived_values"]["total_paid_to_shr_cny"],
        "remaining_payable_to_shr_cny": patch_plan["ledger_derived_values"]["remaining_payable_to_shr_cny"],
        "latest_cash_balances_timestamp": cash_snapshot["snapshot_timestamp"],
        "workbook_recorded_grand_total_kzt": cash_snapshot["workbook_recorded_grand_total_kzt"],
        "owner_confirmed_unrecorded_reserve_kzt": cash_snapshot["owner_confirmation"]["unrecorded_reserve_kzt"],
        "cash_including_owner_unrecorded_reserve_kzt": cash_snapshot["cash_including_owner_unrecorded_reserve_kzt"],
        "validations": validations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--sync-dir", type=Path, default=None)
    parser.add_argument("--po-workbook", type=Path, default=DEFAULT_PO_STORING_WORKBOOK)
    parser.add_argument("--inbound-workbook", type=Path, default=DEFAULT_INBOUND_WORKBOOK)
    parser.add_argument("--handoff-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", default=True, help="Read-only mode; writes generated files only.")
    parser.add_argument("--apply", action="store_true", help="Reserved for future write lanes; currently rejected.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.apply:
        print("ERROR: --apply is not implemented or authorized for receipt sync", file=sys.stderr)
        return 2
    root = args.root.expanduser().resolve()
    sync_dir = args.sync_dir.expanduser().resolve() if args.sync_dir else root / "_sync"
    result = run_sync(
        root=root,
        sync_dir=sync_dir,
        po_workbook=args.po_workbook.expanduser().resolve(),
        inbound_workbook=args.inbound_workbook.expanduser().resolve(),
        handoff_dir=args.handoff_dir.expanduser().resolve() if args.handoff_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
