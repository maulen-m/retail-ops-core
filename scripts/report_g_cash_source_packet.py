#!/usr/bin/env python3
"""Build a no-write cash/PO source packet from owner-provided files."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sync_cash_balances_from_inbound_calendar import SHEET_NAME, _load_history, _read_snapshot

ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_INBOUND_WORKBOOK = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/"
    "vibe_code_PO/Inbound_calendar_V10.002.xlsx"
)
DEFAULT_PO51_RECEIPTS = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/"
    "vibe_code_PO/Transactions/PO_5.1_24.03.2026"
)
DEFAULT_ARC_RECEIPTS = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/"
    "vibe_code_PO/Transactions/ARC"
)
DEFAULT_HISTORY = PROJECT_ROOT / "config" / "bank_accounts_history.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_cash_source_packet"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff"}
AMOUNT_RE = re.compile(r"^\d+(?:\.\d+)?$")

RECEIPT_MANIFEST_COLUMNS = [
    "group",
    "relative_path",
    "file_name",
    "size_bytes",
    "sha256",
    "amount_cny_from_filename",
    "amount_parse_status",
]

CASH_BALANCE_COLUMNS = ["store", "account", "currency", "amount"]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _run_id(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _decimal_to_str(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", str(path))
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def _parse_amount_from_filename(path: Path) -> tuple[str, str]:
    parts = path.stem.split("_")
    if len(parts) >= 2 and parts[0].isdigit() and AMOUNT_RE.fullmatch(parts[1]):
        try:
            return _decimal_to_str(Decimal(parts[1])), "PARSED_LEADING_SEQUENCE_AMOUNT"
        except InvalidOperation:
            pass
    return "", "UNPARSED_NO_LEADING_SEQUENCE_AMOUNT"


def _discover_receipts(group: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    if not root.exists():
        blockers.append(f"receipt_folder_missing:{group}:{root}")
        summary = {
            "group": group,
            "path": str(root),
            "exists": False,
            "image_file_count": 0,
            "parsed_amount_file_count": 0,
            "unparsed_amount_file_count": 0,
            "parsed_amount_total_cny": "0",
        }
        return rows, summary, blockers

    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=_natural_key,
    )
    total = Decimal("0")
    parsed_count = 0
    unparsed_count = 0
    for path in paths:
        amount_text, parse_status = _parse_amount_from_filename(path)
        if amount_text:
            total += Decimal(amount_text)
            parsed_count += 1
        else:
            unparsed_count += 1
        rows.append(
            {
                "group": group,
                "relative_path": str(path.relative_to(root)),
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "amount_cny_from_filename": amount_text,
                "amount_parse_status": parse_status,
            }
        )

    if not rows:
        blockers.append(f"receipt_folder_empty:{group}:{root}")
    summary = {
        "group": group,
        "path": str(root),
        "exists": True,
        "image_file_count": len(rows),
        "parsed_amount_file_count": parsed_count,
        "unparsed_amount_file_count": unparsed_count,
        "parsed_amount_total_cny": _decimal_to_str(total),
    }
    return rows, summary, blockers


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _parse_cash_as_of(value: str) -> datetime | None:
    raw = value.replace(" GMT+5", "").strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _latest_history_as_of(history_path: Path) -> str:
    entries = _load_history(history_path)
    values = sorted(str(row.get("as_of") or "") for row in entries if row.get("as_of"))
    return values[-1] if values else ""


def _workbook_holder_count(path: Path) -> tuple[int | None, str]:
    try:
        result = subprocess.run(
            ["lsof", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "UNKNOWN"
    if result.returncode not in {0, 1}:
        return None, "UNKNOWN"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return 0, "CHECKED"
    return max(0, len(lines) - 1), "CHECKED"


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-CASH Source Packet",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated: {report['generated_at']}",
        "",
        "## Cash Snapshot",
        "",
        f"- workbook: `{report['cash_snapshot']['workbook_path']}`",
        f"- as_of: {report['cash_snapshot']['as_of']}",
        f"- selected_label: {report['cash_snapshot']['selected_label']}",
        f"- account_rows: {report['cash_snapshot']['account_rows']}",
        f"- latest_config_history_as_of: {report['cash_snapshot']['latest_config_history_as_of']}",
        f"- workbook_holder_count: {report['cash_snapshot']['workbook_holder_count']}",
        "",
        "## Receipt Groups",
        "",
    ]
    for group in report["receipt_groups"]:
        lines.append(
            "- "
            f"{group['group']}: files={group['image_file_count']}, "
            f"parsed={group['parsed_amount_file_count']}, "
            f"unparsed={group['unparsed_amount_file_count']}, "
            f"parsed_total_cny={group['parsed_amount_total_cny']}"
        )
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- receipt_manifest_csv: `{report['receipt_manifest_csv']}`")
    lines.append(f"- cash_balance_rows_csv: `{report['cash_balance_rows_csv']}`")
    lines.append("")
    lines.append("No workbook/config/DB/external write was performed by this packet.")
    return "\n".join(lines) + "\n"


def build_cash_source_packet(
    *,
    inbound_workbook: Path,
    po51_receipts: Path,
    arc_receipts: Path,
    history_path: Path,
    output_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or _now_almaty()
    out_dir = output_root / _run_id(generated_at)
    out_dir.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    checks: list[dict[str, Any]] = [
        {"check": "inbound_workbook_present", "ok": inbound_workbook.exists(), "path": str(inbound_workbook)},
        {"check": "history_path_present", "ok": history_path.exists(), "path": str(history_path)},
    ]
    if not inbound_workbook.exists():
        blockers.append(f"inbound_workbook_missing:{inbound_workbook}")

    as_of = ""
    selected_label = ""
    selected_column: int | None = None
    balances: list[dict[str, Any]] = []
    workbook_date_matches_generated_date = False
    account_rows = 0
    if inbound_workbook.exists():
        try:
            as_of, balances, metadata = _read_snapshot(
                xlsx_path=inbound_workbook,
                sheet_name=SHEET_NAME,
                snapshot_ts=None,
            )
            selected_label = str(metadata.get("selected_label") or "")
            selected_column = int(metadata.get("selected_column") or 0)
            account_rows = int(metadata.get("account_rows") or len(balances))
            as_of_dt = _parse_cash_as_of(as_of)
            generated_dt = datetime.fromisoformat(generated_at)
            workbook_date_matches_generated_date = bool(as_of_dt and as_of_dt.date() == generated_dt.date())
            if not workbook_date_matches_generated_date:
                blockers.append(f"cash_snapshot_not_today:{as_of}")
        except Exception as exc:
            blockers.append(f"cash_snapshot_read_failed:{exc}")

    receipt_rows: list[dict[str, Any]] = []
    receipt_groups: list[dict[str, Any]] = []
    for group, root in (("PO_5.1", po51_receipts), ("ARC", arc_receipts)):
        rows, summary, group_blockers = _discover_receipts(group, root)
        receipt_rows.extend(rows)
        receipt_groups.append(summary)
        blockers.extend(group_blockers)
        checks.append({"check": f"{group}_receipt_folder_present", "ok": summary["exists"], "path": summary["path"]})

    holder_count, holder_status = _workbook_holder_count(inbound_workbook) if inbound_workbook.exists() else (None, "NOT_CHECKED")
    balance_rows = [
        {
            "store": row.get("store", ""),
            "account": row.get("account", ""),
            "currency": row.get("currency", ""),
            "amount": row.get("amount", ""),
        }
        for row in balances
    ]

    receipt_manifest_csv = out_dir / "receipt_manifest.csv"
    cash_balance_rows_csv = out_dir / "cash_balance_rows.csv"
    _write_csv(receipt_manifest_csv, receipt_rows, RECEIPT_MANIFEST_COLUMNS)
    _write_csv(cash_balance_rows_csv, balance_rows, CASH_BALANCE_COLUMNS)

    gate = "RED" if blockers else "ARMED"
    status = "SOURCE_PACKET_BLOCKED" if blockers else "SOURCE_PACKET_READY_NO_WRITE"
    report: dict[str, Any] = {
        "gate_id": "G-SCHED-02",
        "gate": gate,
        "status": status,
        "generated_at": generated_at,
        "cash_snapshot": {
            "workbook_path": str(inbound_workbook),
            "workbook_exists": inbound_workbook.exists(),
            "as_of": as_of,
            "selected_label": selected_label,
            "selected_column": selected_column,
            "account_rows": account_rows,
            "latest_config_history_as_of": _latest_history_as_of(history_path) if history_path.exists() else "",
            "workbook_date_matches_generated_date": workbook_date_matches_generated_date,
            "workbook_holder_count": holder_count,
            "workbook_holder_check_status": holder_status,
        },
        "receipt_groups": receipt_groups,
        "receipt_manifest_csv": str(receipt_manifest_csv),
        "cash_balance_rows_csv": str(cash_balance_rows_csv),
        "blockers": blockers,
        "checks": checks,
        "production_db_written": False,
        "cash_config_written": False,
        "workbook_written": False,
        "external_writes_performed": False,
        "apply_performed": False,
        "notes": [
            "This packet validates owner-provided source artifacts only.",
            "It does not sync config/bank account history, move cash, update PO ledgers, or mutate the workbook.",
        ],
    }
    json_path = out_dir / "cash_source_packet_report.json"
    md_path = out_dir / "cash_source_packet_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbound-workbook", type=Path, default=DEFAULT_INBOUND_WORKBOOK)
    parser.add_argument("--po51-receipts", type=Path, default=DEFAULT_PO51_RECEIPTS)
    parser.add_argument("--arc-receipts", type=Path, default=DEFAULT_ARC_RECEIPTS)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_cash_source_packet(
        inbound_workbook=_resolve_path(args.inbound_workbook),
        po51_receipts=_resolve_path(args.po51_receipts),
        arc_receipts=_resolve_path(args.arc_receipts),
        history_path=_resolve_path(args.history),
        output_root=_resolve_path(args.output_root),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Status: {report['status']}")
        print(f"Report: {report['json_path']}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
