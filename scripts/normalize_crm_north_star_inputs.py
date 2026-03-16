#!/usr/bin/env python3
"""Normalize CRM/reconciled workbook and DB truth to comparable grain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Ensure repo root is importable when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.north_star_workbook_utils import (
    apply_status_bridge,
    load_crm_workbook,
    load_db_truth,
    load_reconciled_workbook,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize North Star inputs.")
    parser.add_argument("--as-of", default="2026-03-05")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument(
        "--crm-workbook",
        default="~/Downloads/SALES_KSP_CRM_GPT_Sales_archive.xlsx",
    )
    parser.add_argument(
        "--reconciled-workbook",
        default="~/Downloads/Claude_Reconciled_plus_crm_corrected.xlsx",
    )
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument(
        "--output-dir",
        default="exports/validation/crm_north_star_rebuild/2026-03-05",
    )
    return parser


def normalize_inputs(
    *,
    crm_workbook: Path,
    reconciled_workbook: Path,
    db_path: Path,
    start: str,
    end: str,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    crm_df = load_crm_workbook(crm_workbook)
    rec_df = load_reconciled_workbook(reconciled_workbook)
    crm_bridged = apply_status_bridge(crm_df, rec_df)
    crm_norm = crm_bridged[~crm_bridged["bridge_excluded"]].copy()
    crm_norm["sale_date"] = crm_norm["bridge_status_date"]
    crm_norm = crm_norm[
        (crm_norm["sale_date"] >= start) & (crm_norm["sale_date"] <= end)
    ].copy()

    rec_norm = rec_df.copy()
    rec_norm = rec_norm[
        (rec_norm["status_change_date"].fillna("9999-12-31") >= start)
        & (rec_norm["status_change_date"].fillna("0000-01-01") <= end)
    ].copy()

    db_norm = load_db_truth(db_path=db_path, start=start, end=end)

    crm_csv = output_dir / "crm_workbook_normalized.csv"
    rec_csv = output_dir / "reconciled_workbook_normalized.csv"
    db_csv = output_dir / "db_truth_normalized.csv"
    schema_json = output_dir / "normalization_schema.json"
    report_md = output_dir / "normalization_report.md"

    crm_norm.to_csv(crm_csv, index=False)
    rec_norm.to_csv(rec_csv, index=False)
    db_norm.to_csv(db_csv, index=False)

    schema_payload = {
        "crm_columns": list(crm_norm.columns),
        "reconciled_columns": list(rec_norm.columns),
        "db_columns": list(db_norm.columns),
        "period": {"start": start, "end": end},
    }
    schema_json.write_text(json.dumps(schema_payload, indent=2, ensure_ascii=False))

    report_md.write_text(
        "\n".join(
            [
                "# Normalization Report",
                "",
                f"- start: `{start}`",
                f"- end: `{end}`",
                f"- crm_rows_included: `{len(crm_norm)}`",
                f"- reconciled_rows_included: `{len(rec_norm)}`",
                f"- db_rows_included: `{len(db_norm)}`",
                f"- crm_bridge_excluded_rows: `{int(crm_bridged['bridge_excluded'].sum())}`",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "crm_workbook_normalized_csv": str(crm_csv.resolve()),
        "reconciled_workbook_normalized_csv": str(rec_csv.resolve()),
        "db_truth_normalized_csv": str(db_csv.resolve()),
        "normalization_schema_json": str(schema_json.resolve()),
        "normalization_report_md": str(report_md.resolve()),
    }


def main() -> int:
    args = _build_parser().parse_args()
    outputs = normalize_inputs(
        crm_workbook=Path(args.crm_workbook),
        reconciled_workbook=Path(args.reconciled_workbook),
        db_path=Path(args.db_path),
        start=args.start,
        end=args.end,
        output_dir=Path(args.output_dir),
    )
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
