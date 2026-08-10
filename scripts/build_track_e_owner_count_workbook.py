#!/usr/bin/env python3
"""Build the read-only Track E owner count evidence workbook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from copy import copy
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation


AUTHORIZED_LANES = (
    "T-SHIRT/BERSERK mixed",
    "NIKE-SHIRT",
    "slow LINE51",
)

EVIDENCE_COLUMNS = [
    "candidate_lane", "lot_id", "family", "color", "size", "owner_label",
    "candidate_sku_id", "stock_pool_id", "alias_group", "count_location",
    "count_timestamp_+05", "counter", "photo_ref", "photo_hash",
    "source_anchor_ref", "last_replay_event", "estimate_low", "estimate_high",
    "physical_count", "sellable_count", "reserved_count", "quarantine_count",
    "damaged_count", "mismatch_count", "blank_semantic", "count_low", "count_high",
    "verified_receipts", "verified_departures", "accepted_return_restock",
    "approved_adjustments", "replay_low", "replay_high", "known_open_commitments",
    "marketplace_reserve", "owner_approved_qty", "approved_lot_qty", "supplier_base",
    "fx", "cargo", "import", "packaging", "qc", "other", "frozen_landed_cogs",
    "cogs_source", "cogs_status", "rendered_price", "rendered_price_source_time",
    "commission", "delivery", "vat", "allocated_ads", "return_reserve", "kaspi_net",
    "wholesale_handling", "minimum_cash_margin", "opportunity_cost", "opening_price",
    "target_price", "owner_hard_floor", "hard_floor", "prepaid_confirmed",
    "non_consignment_confirmed", "owner_approval", "outreach_status",
]

OWNER_EDITABLE = {
    "owner_label", "candidate_sku_id", "stock_pool_id", "alias_group", "count_location",
    "count_timestamp_+05", "counter", "photo_ref", "photo_hash", "physical_count",
    "sellable_count", "reserved_count", "quarantine_count", "damaged_count",
    "mismatch_count", "count_low", "count_high", "verified_receipts",
    "verified_departures", "accepted_return_restock", "approved_adjustments",
    "marketplace_reserve", "owner_approved_qty", "supplier_base", "fx", "cargo",
    "import", "packaging", "qc", "other", "cogs_source", "rendered_price",
    "rendered_price_source_time", "allocated_ads", "return_reserve",
    "wholesale_handling", "minimum_cash_margin", "opening_price", "target_price",
    "owner_hard_floor", "prepaid_confirmed", "non_consignment_confirmed", "owner_approval",
}

SOURCE_REF = "agent_f_report.md"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
ENTRY_FILL = PatternFill("solid", fgColor="FFF2CC")
FORMULA_FILL = PatternFill("solid", fgColor="D9EAD3")
STOP_FILL = PatternFill("solid", fgColor="F4CCCC")


def resolve_estimate(low: int, high: int, correction: object) -> tuple[int, int]:
    """Apply an explicit correction while preserving blank and range semantics."""
    if correction is None or correction == "":
        return low, high
    value = int(correction)
    return value, value


def _row(lane: str, lot_id: str, family: str, color: str, size: str,
         low: int | str, high: int | str, note: str, commitment: int = 0) -> dict:
    row = {column: "" for column in EVIDENCE_COLUMNS}
    row.update({
        "candidate_lane": lane,
        "lot_id": lot_id,
        "family": family,
        "color": color,
        "size": size,
        "source_anchor_ref": SOURCE_REF,
        "last_replay_event": note,
        "estimate_low": low,
        "estimate_high": high,
        "known_open_commitments": commitment,
        "blank_semantic": "EXPLICIT_ZERO_ESTIMATE" if low == high == 0 else "BLANK=UNKNOWN/NOT_ENTERED",
        "cogs_status": "UNKNOWN/STOP",
        "approved_lot_qty": "",
        "frozen_landed_cogs": "",
        "opportunity_cost": "",
        "outreach_status": "UNKNOWN/STOP",
    })
    return row


def build_rows(as_of: str) -> list[dict]:
    rows = [
        _row(AUTHORIZED_LANES[0], "TE-TS-CAN-WHT", "T-SHIRT", "White", "UNRESOLVED",
             522, 522, "2026-07-17 canonical pool estimate; color-by-size count required"),
        _row(AUTHORIZED_LANES[0], "TE-TS-MIX-WHT", "T-SHIRT", "White (mixed-case)", "UNRESOLVED",
             194, 194, "Possible duplicate pool; exclude until identity bridge is owner-approved"),
        _row(AUTHORIZED_LANES[0], "TE-BS-CAN-MIX", "BERSERK-SHIRT", "Black/White/GREY-BLK", "UNRESOLVED",
             923, 923, "Replay estimate conflicts with prior approximately 594 count"),
        _row(AUTHORIZED_LANES[0], "TE-BS-MIX-BLK", "BERSERK-SHIRT", "Black (mixed-case)", "UNRESOLVED",
             190, 190, "Excluded unresolved pool; duplication status UNKNOWN/STOP"),
        _row(AUTHORIZED_LANES[1], "TE-NIKE-ALL", "NIKE-SHIRT", "UNRESOLVED", "UNRESOLVED",
             947, 947, "54 confirmed shipments through 2026-08-09; full current-day coverage missing", 1),
    ]
    beli = {"S": 81, "M": 105, "L": 186, "XL": 191, "2XL": 99, "3XL": 50, "4XL": 0}
    for size, estimate in beli.items():
        rows.append(_row(
            AUTHORIZED_LANES[2], f"TE-LINE51-{size}", "LINE51", "UNRESOLVED", size,
            estimate, estimate, "Owner slow-size eligibility and protected reserve not attested",
            1 if size == "XL" else 0,
        ))
    for row in rows:
        row["as_of_+05"] = as_of
    return rows


def _style_header(sheet) -> None:
    for cell in sheet[1]:
        cell.fill = copy(HEADER_FILL)
        cell.font = copy(HEADER_FONT)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def _set_widths(sheet, maximum: int = 32) -> None:
    for column_cells in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, maximum)
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = max(width, 11)


def _add_validation(sheet, column: int, validation: DataValidation, last_row: int) -> None:
    sheet.add_data_validation(validation)
    validation.add(f"{get_column_letter(column)}2:{get_column_letter(column)}{last_row}")


def _formula_refs(headers: dict[str, int], row: int) -> dict[str, str]:
    return {name: f"{get_column_letter(column)}{row}" for name, column in headers.items()}


def _build_count_entry(workbook: Workbook, rows: list[dict]) -> None:
    sheet = workbook.create_sheet("COUNT_ENTRY")
    sheet.append(EVIDENCE_COLUMNS)
    headers = {name: index + 1 for index, name in enumerate(EVIDENCE_COLUMNS)}
    for row_number, source in enumerate(rows, start=2):
        sheet.append([source.get(column, "") for column in EVIDENCE_COLUMNS])
        refs = _formula_refs(headers, row_number)
        sheet[refs["replay_low"]] = (
            f'=IF(OR({refs["count_low"]}="",{refs["verified_receipts"]}="",'
            f'{refs["verified_departures"]}="",{refs["accepted_return_restock"]}="",'
            f'{refs["approved_adjustments"]}=""),"",{refs["count_low"]}+'
            f'{refs["verified_receipts"]}-{refs["verified_departures"]}+'
            f'{refs["accepted_return_restock"]}+{refs["approved_adjustments"]})'
        )
        sheet[refs["replay_high"]] = sheet[refs["replay_low"]].value.replace(
            refs["count_low"], refs["count_high"]
        )
        sheet[refs["frozen_landed_cogs"]] = (
            f'=IF(COUNT({refs["supplier_base"]},{refs["fx"]},{refs["cargo"]},{refs["import"]},'
            f'{refs["packaging"]},{refs["qc"]},{refs["other"]})<7,"",SUM('
            f'{refs["supplier_base"]},{refs["cargo"]},{refs["import"]},'
            f'{refs["packaging"]},{refs["qc"]},{refs["other"]}))'
        )
        sheet[refs["hard_floor"]] = (
            f'=IF(OR({refs["owner_hard_floor"]}="",{refs["frozen_landed_cogs"]}="",'
            f'{refs["wholesale_handling"]}="",{refs["minimum_cash_margin"]}=""),"",MAX('
            f'{refs["owner_hard_floor"]},{refs["frozen_landed_cogs"]}+'
            f'{refs["wholesale_handling"]}+{refs["minimum_cash_margin"]}))'
        )
        sheet[refs["kaspi_net"]] = (
            f'=IF({refs["rendered_price"]}="","",(({refs["rendered_price"]}*0.875)-1249.14)*0.96)'
        )
        blockers = [
            "candidate_sku_id", "stock_pool_id", "count_location", "count_timestamp_+05",
            "counter", "photo_ref", "photo_hash", "physical_count", "count_low", "count_high",
            "replay_low", "marketplace_reserve", "owner_approved_qty", "fx", "cogs_source",
            "frozen_landed_cogs", "opening_price", "target_price", "hard_floor",
        ]
        blank_gate = ",".join(f'{refs[name]}=""' for name in blockers)
        sheet[refs["approved_lot_qty"]] = (
            f'=IF(OR({blank_gate},{refs["count_low"]}<>{refs["count_high"]},'
            f'{refs["physical_count"]}<>{refs["count_low"]},'
            f'{refs["opening_price"]}<{refs["target_price"]},'
            f'{refs["target_price"]}<{refs["hard_floor"]},'
            f'{refs["prepaid_confirmed"]}<>"YES",'
            f'{refs["non_consignment_confirmed"]}<>"YES",{refs["owner_approval"]}<>"YES"),"",'
            f'MAX(0,MIN({refs["owner_approved_qty"]},{refs["replay_low"]}-'
            f'{refs["known_open_commitments"]}-{refs["marketplace_reserve"]})))'
        )
        sheet[refs["outreach_status"]] = '="UNKNOWN/STOP"'
        sheet[refs["opportunity_cost"]] = (
            f'=IF(OR({refs["approved_lot_qty"]}="",{refs["frozen_landed_cogs"]}="",'
            f'{refs["target_price"]}="",{refs["kaspi_net"]}=""),"",MAX(0,'
            f'({refs["kaspi_net"]}-{refs["frozen_landed_cogs"]}-{refs["allocated_ads"]}-'
            f'{refs["return_reserve"]})-({refs["target_price"]}-{refs["frozen_landed_cogs"]}-'
            f'{refs["wholesale_handling"]})))'
        )

    for column_name, column in headers.items():
        for row_number in range(2, sheet.max_row + 1):
            cell = sheet.cell(row_number, column)
            editable = column_name in OWNER_EDITABLE
            cell.protection = Protection(locked=not editable)
            cell.fill = copy(ENTRY_FILL if editable else FORMULA_FILL)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _style_header(sheet)
    sheet.protection.sheet = True
    sheet.protection.selectUnlockedCells = False
    last_row = sheet.max_row
    yes_no = DataValidation(type="list", formula1='"YES,NO"', allow_blank=True)
    for name in ("prepaid_confirmed", "non_consignment_confirmed", "owner_approval"):
        _add_validation(sheet, headers[name], copy(yes_no), last_row)
    nonnegative = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    for name in ("physical_count", "count_low", "count_high", "marketplace_reserve", "owner_approved_qty"):
        _add_validation(sheet, headers[name], copy(nonnegative), last_row)
    price_validation = DataValidation(
        type="custom", formula1=f'=OR(${get_column_letter(headers["opening_price"])}2="",'
        f'${get_column_letter(headers["target_price"])}2="",'
        f'${get_column_letter(headers["hard_floor"])}2="",AND('
        f'${get_column_letter(headers["opening_price"])}2>='
        f'${get_column_letter(headers["target_price"])}2,'
        f'${get_column_letter(headers["target_price"])}2>='
        f'${get_column_letter(headers["hard_floor"])}2))', allow_blank=True,
    )
    for name in ("opening_price", "target_price", "owner_hard_floor"):
        _add_validation(sheet, headers[name], copy(price_validation), last_row)
    sheet.conditional_formatting.add(
        f"A2:{get_column_letter(sheet.max_column)}{last_row}",
        FormulaRule(formula=[f'${get_column_letter(headers["outreach_status"])}2="UNKNOWN/STOP"'], fill=STOP_FILL),
    )
    _set_widths(sheet)


def _simple_sheet(workbook: Workbook, title: str, headers: list[str], rows: list[list]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    _style_header(sheet)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _set_widths(sheet, 45)


def _normalize_xlsx(path: Path) -> None:
    fixed = (2026, 8, 10, 0, 0, 0)
    with NamedTemporaryFile(suffix=".xlsx", delete=False, dir=path.parent) as handle:
        temp = Path(handle.name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as target:
            for name in sorted(source.namelist()):
                info = zipfile.ZipInfo(name, fixed)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                target.writestr(info, source.read(name))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _build_workbook(path: Path, rows: list[dict], as_of: str) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Autonomous_business Track E builder"
    workbook.properties.created = datetime.fromisoformat(as_of)
    workbook.properties.modified = datetime.fromisoformat(as_of)
    _simple_sheet(workbook, "README", ["field", "value"], [
        ["gate", "YELLOW_PREPARATION_ONLY / UNKNOWN/STOP"],
        ["as_of_Asia_Almaty", as_of],
        ["scope", "; ".join(AUTHORIZED_LANES)],
        ["authority", "Owner-entry evidence only; no outreach, reservation, approval, or release authority"],
        ["blank_semantic", "Blank means UNKNOWN/not entered; explicit numeric zero is valid"],
        ["price_rule", "OpeningPrice >= TargetPrice >= HardFloor"],
        ["external_writes", 0],
    ])
    _build_count_entry(workbook, rows)
    _simple_sheet(workbook, "REPLAY_AND_GAPS", ["candidate_lane", "lot_id", "gap", "status"], [
        [row["candidate_lane"], row["lot_id"], row["last_replay_event"], "UNKNOWN/STOP"] for row in rows
    ])
    _simple_sheet(workbook, "COGS_AND_FLOORS", ["family", "current_cost_evidence", "status"], [
        ["T-SHIRT", "780 vs 1,950 KZT proxies conflict", "UNKNOWN/STOP"],
        ["BERSERK-SHIRT", "780 KZT proxy is not landed COGS", "UNKNOWN/STOP"],
        ["NIKE-SHIRT", "858 KZT proxy; one-order 992.746846 override not family-wide", "UNKNOWN/STOP"],
        ["LINE51", "4,680 base; 6,020 historical; 6,395 fallback", "UNKNOWN/STOP"],
    ])
    _simple_sheet(workbook, "LOT_PREVIEW", ["candidate_lane", "approved_qty", "hard_floor", "target_price", "opening_price", "cash_objective", "approved_unit_price", "cash_hard_floor", "cash_target", "cash_opening", "units_needed_for_band", "outreach_status"], [
        [lane, "", "", "", "", "", "", f'=IF(OR(B{index}="",C{index}=""),"",B{index}*C{index})',
         f'=IF(OR(B{index}="",D{index}=""),"",B{index}*D{index})',
         f'=IF(OR(B{index}="",E{index}=""),"",B{index}*E{index})',
         f'=IF(OR(F{index}="",G{index}=""),"",CEILING(F{index}/G{index},1))', "UNKNOWN/STOP"]
        for index, lane in enumerate(AUTHORIZED_LANES, start=2)
    ])
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.save(path)
    _normalize_xlsx(path)


def _validate_as_of(as_of: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:00", as_of):
        raise ValueError("--as-of must be ISO8601 with explicit +05:00 offset")
    datetime.fromisoformat(as_of)


def generate_bundle(output_dir: Path | str, as_of: str, strict: bool = False) -> dict[str, str]:
    _validate_as_of(as_of)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    rows = build_rows(as_of)
    if strict and ({row["candidate_lane"] for row in rows} != set(AUTHORIZED_LANES)):
        raise ValueError("unauthorized or missing candidate lane")

    paths = {
        "workbook": output / "track_e_owner_count_workbook.xlsx",
        "csv": output / "track_e_owner_count_rows.csv",
        "json": output / "track_e_owner_count_rows.json",
        "manifest": output / "SHA256_MANIFEST.json",
    }
    _build_workbook(paths["workbook"], rows, as_of)
    with paths["csv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_COLUMNS + ["as_of_+05"])
        writer.writeheader()
        writer.writerows(rows)
    paths["json"].write_text(
        json.dumps({"as_of": as_of, "rows": rows}, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifacts = []
    for key in ("workbook", "csv", "json"):
        artifact = paths[key]
        artifacts.append({"name": artifact.name, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "bytes": artifact.stat().st_size})
    paths["manifest"].write_text(
        json.dumps({"as_of": as_of, "row_count": len(rows), "candidate_lane_count": len(AUTHORIZED_LANES),
                    "external_writes": 0, "artifacts": artifacts}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_workbook(paths["workbook"], data_only=False).close()
    json.loads(paths["json"].read_text(encoding="utf-8"))
    with paths["csv"].open(newline="", encoding="utf-8") as handle:
        list(csv.DictReader(handle))
    return {key: str(value) for key, value in paths.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    paths = generate_bundle(args.output_dir, args.as_of, strict=args.strict)
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
