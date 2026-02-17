#!/usr/bin/env python3
"""Build a daily single-truth drift monitoring artifact (read-only)."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.paid_capital_truth import compute_paid_capital_truth
from scripts.validate_cogs_integrity import validate_cogs_integrity
from scripts.validate_dim_sku_light_alignment import (
    DEFAULT_SHEET as DEFAULT_DIM_SKU_SHEET,
    DEFAULT_WORKBOOK as DEFAULT_DIM_SKU_WORKBOOK,
    validate_dim_sku_light_alignment,
)
from scripts.validate_on_delivery_freeze import validate_on_delivery_freeze
from scripts.validate_sales_vs_workbook_anchor import (
    DEFAULT_SHEET as DEFAULT_SALES_SHEET,
    validate_sales_vs_workbook_anchor,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_BANK = PROJECT_ROOT / "config" / "bank_accounts.yaml"


def collect_workbook_overage(
    *,
    db_path: Path,
    as_of: str,
    workbook_path: Path | None,
    workbook_sheet: str = DEFAULT_SALES_SHEET,
    max_lag_days: int = 1,
) -> dict[str, Any]:
    if workbook_path is None:
        return {"status": "skipped", "reason": "workbook path not provided"}
    workbook = Path(workbook_path).expanduser()
    if not workbook.exists():
        return {"status": "skipped", "reason": f"workbook not found: {workbook}"}

    report = validate_sales_vs_workbook_anchor(
        db_path=db_path,
        workbook_path=workbook,
        sheet_name=workbook_sheet,
        days=14,
        tol_pct=5.0,
        as_of=as_of,
        min_overlap_days=7,
        max_lag_days=max_lag_days,
    )

    overage_days: list[dict[str, Any]] = []
    for day in report.get("daily", []):
        wb_units = float(day.get("workbook_units") or 0.0)
        db_units = float(day.get("published_units") or 0.0)
        wb_net = float(day.get("workbook_net_rev_kzt") or 0.0)
        db_net = float(day.get("published_net_rev_kzt") or 0.0)
        if (wb_units > 0 and db_units > wb_units * 1.05) or (wb_net > 0 and db_net > wb_net * 1.05):
            overage_days.append(day)

    return {
        "status": "ok" if report.get("ok") else "fail",
        "ok": bool(report.get("ok")),
        "window_start": report.get("window_start"),
        "window_end": report.get("window_end"),
        "workbook_max_date": report.get("workbook_max_date"),
        "db_max_date": report.get("db_max_date"),
        "overlap_days": int(report.get("overlap_days") or 0),
        "max_lag_days": int(report.get("max_lag_days") or max_lag_days),
        "overage_count": len(overage_days),
        "overage_days": overage_days[:20],
        "errors": report.get("errors", []),
    }


def collect_cogs_summary(
    *,
    db_path: Path,
    as_of: str,
    days: int = 30,
) -> dict[str, Any]:
    report = validate_cogs_integrity(
        db_path=db_path,
        as_of=as_of,
        days=days,
        max_unresolved_rows=10**9,
        max_unresolved_skus=10**9,
    )

    top_unresolved_skus: list[dict[str, Any]] = []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT sku_key, COUNT(*) AS unresolved_rows
            FROM view_sales_line_truth
            WHERE cogs_source = 'unresolved'
              AND date(sale_date) BETWEEN ? AND ?
            GROUP BY sku_key
            ORDER BY unresolved_rows DESC, sku_key
            LIMIT 10
            """,
            (report["window_start"], report["window_end"]),
        ).fetchall()
        top_unresolved_skus = [
            {"sku_key": str(row["sku_key"]), "unresolved_rows": int(row["unresolved_rows"] or 0)}
            for row in rows
        ]
    except Exception as exc:
        top_unresolved_skus = [{"error": str(exc)}]
    finally:
        conn.close()

    return {
        "window_start": report["window_start"],
        "window_end": report["window_end"],
        "total_rows": report["total_rows"],
        "formula_rows": report["formula_rows"],
        "unresolved_rows": report["unresolved_rows"],
        "unresolved_skus": report["unresolved_skus"],
        "top_unresolved_skus": top_unresolved_skus,
    }


def collect_on_delivery_residuals(
    *,
    db_path: Path,
    as_of: str,
) -> dict[str, Any]:
    errors = validate_on_delivery_freeze(
        db_path=db_path,
        until=date.fromisoformat(as_of),
        lookback_days=30,
    )
    return {
        "residual_count": len(errors),
        "sample": errors[:20],
    }


def collect_dim_sku_alignment(
    *,
    db_path: Path,
    workbook_path: Path = DEFAULT_DIM_SKU_WORKBOOK,
    sheet_name: str = DEFAULT_DIM_SKU_SHEET,
) -> dict[str, Any]:
    try:
        report = validate_dim_sku_light_alignment(
            db_path=db_path,
            workbook_path=workbook_path,
            sheet_name=sheet_name,
            weight_tol_kg=0.01,
            base_tol_cny=0.01,
            enforce_base_cost=False,
        )
        return {
            "status": "ok" if report.get("ok") else "fail",
            "compared_count": report.get("compared_count"),
            "weight_mismatch_count": report.get("weight_mismatch_count"),
            "base_mismatch_count": report.get("base_mismatch_count"),
            "warnings": report.get("warnings", []),
            "errors": report.get("errors", []),
        }
    except Exception as exc:
        return {
            "status": "error",
            "errors": [str(exc)],
        }


def collect_paid_capital_snapshot(
    *,
    db_path: Path,
    as_of: str,
    bank_accounts_path: Path = DEFAULT_BANK,
) -> dict[str, Any]:
    snapshot = compute_paid_capital_truth(
        db_path=db_path,
        bank_accounts_path=bank_accounts_path,
        as_of=as_of,
    )
    return {
        "snapshot_date": snapshot.get("snapshot_date"),
        "bank_as_of_date": snapshot.get("bank_as_of_date"),
        "cash_actual_kzt": snapshot.get("cash_actual_kzt"),
        "inventory_on_hand_paid_kzt": snapshot.get("inventory_on_hand_paid_kzt"),
        "inventory_inbound_paid_kzt": snapshot.get("inventory_inbound_paid_kzt"),
        "inventory_on_delivery_paid_kzt": snapshot.get("inventory_on_delivery_paid_kzt"),
        "total_capital_paid_kzt": snapshot.get("total_capital_paid_kzt"),
        "inbound_unpaid_obligations_kzt": snapshot.get("inbound_unpaid_obligations_kzt"),
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    def _json_block(obj: Any) -> str:
        return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"

    return "\n".join(
        [
            "# Single Truth Drift Pack",
            "",
            f"- Generated at: `{payload['generated_at']}`",
            f"- As of: `{payload['as_of']}`",
            "",
            "## Workbook Overage",
            "",
            _json_block(payload["workbook_overage"]),
            "",
            "## COGS Integrity",
            "",
            _json_block(payload["cogs_integrity"]),
            "",
            "## On-Delivery Residuals",
            "",
            _json_block(payload["on_delivery_residuals"]),
            "",
            "## Dim SKU Alignment",
            "",
            _json_block(payload["dim_sku_alignment"]),
            "",
            "## Paid Capital Snapshot",
            "",
            _json_block(payload["paid_capital_snapshot"]),
            "",
        ]
    )


def build_single_truth_drift_pack(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    workbook_path: Path | None = None,
    workbook_sheet: str = DEFAULT_SALES_SHEET,
    max_lag_days: int = 1,
) -> dict[str, str]:
    as_of_iso = as_of or date.today().isoformat()
    workbook = workbook_path
    if workbook is None:
        raw = str(os.environ.get("AB_CRM_WORKBOOK_PATH", "")).strip()
        if raw:
            workbook = Path(raw)

    payload = {
        "generated_at": date.today().isoformat(),
        "as_of": as_of_iso,
        "workbook_overage": collect_workbook_overage(
            db_path=db_path,
            as_of=as_of_iso,
            workbook_path=workbook,
            workbook_sheet=workbook_sheet,
            max_lag_days=max_lag_days,
        ),
        "cogs_integrity": collect_cogs_summary(db_path=db_path, as_of=as_of_iso),
        "on_delivery_residuals": collect_on_delivery_residuals(db_path=db_path, as_of=as_of_iso),
        "dim_sku_alignment": collect_dim_sku_alignment(db_path=db_path),
        "paid_capital_snapshot": collect_paid_capital_snapshot(db_path=db_path, as_of=as_of_iso),
    }

    out_dir = output_root / as_of_iso
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "single_truth_drift_pack.json"
    markdown_path = out_dir / "single_truth_drift_pack.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build single-truth daily drift pack")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--workbook-sheet", type=str, default=DEFAULT_SALES_SHEET)
    parser.add_argument("--max-lag-days", type=int, default=1)
    args = parser.parse_args()

    result = build_single_truth_drift_pack(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        workbook_path=args.workbook,
        workbook_sheet=args.workbook_sheet,
        max_lag_days=args.max_lag_days,
    )
    print(f"json_path={result['json_path']}")
    print(f"markdown_path={result['markdown_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
