#!/usr/bin/env python3
"""Prepare deterministic workbook anchors for headless validation runs."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from openpyxl import Workbook


def _write_sales_workbook(path: Path, *, as_of: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Date", "Quantity", "Total_price", "Total_net_rev", "Sell_price_kzt"])
    ws.append([as_of.isoformat(), 1, 10000.0, 9500.0, 10000.0])
    wb.save(path)


def _write_inbound_workbook(path: Path, *, as_of: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "PO_part_id_Totals"
    ws.append(["po_part_id", "status", "Actual_Arrival_date", "is_paid_BASE", "is_paid_DLV"])
    ws.append(["FIX-1.0", "Transit", as_of.isoformat(), "NO", "NO"])
    wb.save(path)


def _replace_with_symlink(link_path: Path, target_path: Path) -> None:
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_dir() and not link_path.is_symlink():
            raise RuntimeError(f"refusing to replace directory with symlink: {link_path}")
        link_path.unlink()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target_path)


def prepare_ci_headless_fixture(*, project_root: Path, as_of: date) -> dict[str, str]:
    root = project_root.resolve()
    sales_target = root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    inbound_target = root / "excel_ui" / "INBOUND_CALENDAR_V10.002.xlsx"
    crm_anchor = root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    inbound_anchor = root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"

    _write_sales_workbook(sales_target, as_of=as_of)
    _write_inbound_workbook(inbound_target, as_of=as_of)
    _replace_with_symlink(crm_anchor, sales_target)
    _replace_with_symlink(inbound_anchor, inbound_target)

    return {
        "project_root": str(root),
        "sales_target": str(sales_target),
        "inbound_target": str(inbound_target),
        "crm_anchor": str(crm_anchor),
        "inbound_anchor": str(inbound_anchor),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare headless workbook fixtures and anchor symlinks")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--as-of", type=str, default=date.today().isoformat())
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    result = prepare_ci_headless_fixture(project_root=args.project_root, as_of=as_of)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
