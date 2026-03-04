#!/usr/bin/env python3
"""Strict validator for status-date mapped sales archive dataset."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DATA_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "economics_parity"
DEFAULT_REQUIRED_STORES = {"UNIVERSAL", "ACMEWEAR", "STOREB", "MELVIS", "11KZ"}
DEFAULT_STRICT_STATUSDATE_REQUIRED_SINCE = "2026-02-27"

REQUIRED_COLUMNS = {
    "line_id",
    "order_id",
    "transaction_date",
    "transaction_month",
    "transaction_date_source",
    "store_code",
    "status_internal",
    "return_flag",
    "quantity",
    "gross_rev_kzt",
    "net_rev_kzt",
    "mapped_sku_key",
    "mapped_size",
}


class ValidationError(RuntimeError):
    """Raised when mapped archive validation fails."""


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales Archive Status-Date Mapped Validation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- range: `{report['since']} -> {report['until']}`",
        f"- status: `{report['status']}`",
        f"- strict: `{str(report['strict']).lower()}`",
        f"- csv_path: `{report['csv_path']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(
            f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_sales_archive_statusdate_mapped(
    *,
    since: date,
    until: date,
    data_root: Path,
    output_root: Path,
    strict: bool,
    strict_statusdate_required_since: date,
    min_delivered_mapping_coverage: float,
) -> dict[str, Any]:
    if until < since:
        raise ValidationError("until must be >= since")
    if not (0.0 <= min_delivered_mapping_coverage <= 1.0):
        raise ValidationError("min_delivered_mapping_coverage must be within [0,1]")

    range_dir = data_root.resolve() / f"{since.isoformat()}_to_{until.isoformat()}"
    csv_path = range_dir / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    schema_path = range_dir / "schema.json"
    manifest_path = range_dir / "source_manifest.json"

    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    for path in (csv_path, schema_path, manifest_path):
        ok = path.exists()
        checks.append({"check": f"artifact_exists:{path.name}", "ok": ok, "details": str(path)})
        if not ok:
            errors.append(f"missing required artifact: {path}")

    if errors:
        raise ValidationError("; ".join(errors))

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    missing_cols = sorted(REQUIRED_COLUMNS - set(df.columns))
    checks.append(
        {
            "check": "required_columns",
            "ok": not missing_cols,
            "details": "none" if not missing_cols else ", ".join(missing_cols),
        }
    )
    if missing_cols:
        errors.append(f"csv missing required columns: {', '.join(missing_cols)}")

    schema_cols = set((schema.get("columns") or {}).keys())
    schema_missing = sorted(REQUIRED_COLUMNS - schema_cols)
    checks.append(
        {
            "check": "schema_required_columns",
            "ok": not schema_missing,
            "details": "none" if not schema_missing else ", ".join(schema_missing),
        }
    )
    if schema_missing:
        errors.append(f"schema missing required columns: {', '.join(schema_missing)}")

    if df.empty:
        errors.append("mapped archive csv contains 0 rows")

    tx_dates = pd.to_datetime(df.get("transaction_date"), errors="coerce")
    invalid_date_rows = int(tx_dates.isna().sum())
    checks.append(
        {
            "check": "transaction_date_parseable",
            "ok": invalid_date_rows == 0,
            "details": f"invalid_rows={invalid_date_rows}",
        }
    )
    if invalid_date_rows > 0:
        errors.append(f"transaction_date parse failures: {invalid_date_rows}")

    in_range = (tx_dates.dt.date >= since) & (tx_dates.dt.date <= until)
    out_of_range = int((~in_range).sum())
    checks.append(
        {
            "check": "transaction_date_within_requested_range",
            "ok": out_of_range == 0,
            "details": f"out_of_range_rows={out_of_range}",
        }
    )
    if out_of_range > 0:
        errors.append(f"rows outside requested range: {out_of_range}")

    duplicate_line_ids = int(df["line_id"].astype(str).duplicated().sum()) if "line_id" in df.columns else 0
    checks.append(
        {
            "check": "line_id_unique",
            "ok": duplicate_line_ids == 0,
            "details": f"duplicate_rows={duplicate_line_ids}",
        }
    )
    if duplicate_line_ids > 0:
        errors.append(f"duplicate line_id rows: {duplicate_line_ids}")

    stores = {str(v).strip().upper() for v in df.get("store_code", pd.Series(dtype=str)).tolist() if str(v).strip()}
    missing_stores = sorted(DEFAULT_REQUIRED_STORES - stores)
    checks.append(
        {
            "check": "required_store_coverage",
            "ok": not missing_stores,
            "details": "none" if not missing_stores else ", ".join(missing_stores),
        }
    )
    if missing_stores:
        errors.append(f"missing stores in mapped archive: {', '.join(missing_stores)}")

    delivered_mask = (
        df.get("status_internal", pd.Series(dtype=str)).astype(str).str.upper().eq("DELIVERED")
        & pd.to_numeric(df.get("return_flag", 0), errors="coerce").fillna(0).astype(int).eq(0)
    )

    delivered_rows = int(delivered_mask.sum())
    missing_mapping = int(
        (
            delivered_mask
            & (
                df.get("mapped_sku_key", pd.Series(dtype=str)).astype(str).str.strip().eq("")
                | df.get("mapped_size", pd.Series(dtype=str)).astype(str).str.strip().eq("")
            )
        ).sum()
    )
    delivered_mapping_coverage = 1.0
    if delivered_rows > 0:
        delivered_mapping_coverage = 1.0 - (missing_mapping / delivered_rows)
    checks.append(
        {
            "check": "delivered_mapping_coverage",
            "ok": delivered_mapping_coverage >= min_delivered_mapping_coverage,
            "details": f"coverage={delivered_mapping_coverage:.4f} threshold={min_delivered_mapping_coverage:.4f}",
        }
    )
    if delivered_mapping_coverage < min_delivered_mapping_coverage:
        errors.append(
            f"delivered mapping coverage below threshold: {delivered_mapping_coverage:.4f} < {min_delivered_mapping_coverage:.4f}"
        )

    source_series = df.get("transaction_date_source", pd.Series(dtype=str)).astype(str)
    disallowed_fallback = int(
        (
            delivered_mask
            & tx_dates.dt.date.ge(strict_statusdate_required_since)
            & source_series.eq("creation_date_fallback")
        ).sum()
    )
    checks.append(
        {
            "check": "post_cutover_delivered_requires_status_date",
            "ok": disallowed_fallback == 0,
            "details": (
                f"cutover={strict_statusdate_required_since.isoformat()} fallback_rows={disallowed_fallback}"
            ),
        }
    )
    if disallowed_fallback > 0:
        errors.append(
            f"post-cutover delivered rows still use creation_date_fallback: {disallowed_fallback}"
        )

    manifest_rows = int((manifest.get("output") or {}).get("rows") or 0)
    manifest_ok = manifest_rows == int(len(df))
    checks.append(
        {
            "check": "manifest_row_count_matches_csv",
            "ok": manifest_ok,
            "details": f"manifest_rows={manifest_rows} csv_rows={len(df)}",
        }
    )
    if not manifest_ok:
        errors.append("source_manifest output.rows does not match csv row count")

    status = "PASS" if not errors else "FAIL"

    report_dir = output_root.resolve() / f"{since.isoformat()}_to_{until.isoformat()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = report_dir / "sales_archive_statusdate_mapped_validation.json"
    report_md = report_dir / "sales_archive_statusdate_mapped_validation.md"

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "strict": bool(strict),
        "status": status,
        "csv_path": str(csv_path.resolve()),
        "schema_path": str(schema_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "rows": int(len(df)),
        "delivered_rows": delivered_rows,
        "delivered_mapping_coverage": delivered_mapping_coverage,
        "checks": checks,
        "errors": errors,
        "json_path": str(report_json.resolve()),
        "md_path": str(report_md.resolve()),
    }

    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")

    if strict and errors:
        raise ValidationError("sales archive statusdate mapped validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate status-date mapped sales archive dataset")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--strict-statusdate-required-since",
        default=DEFAULT_STRICT_STATUSDATE_REQUIRED_SINCE,
    )
    parser.add_argument("--min-delivered-mapping-coverage", type=float, default=0.995)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_sales_archive_statusdate_mapped(
        since=date.fromisoformat(args.since),
        until=date.fromisoformat(args.until),
        data_root=args.data_root,
        output_root=args.output_root,
        strict=bool(args.strict),
        strict_statusdate_required_since=date.fromisoformat(args.strict_statusdate_required_since),
        min_delivered_mapping_coverage=float(args.min_delivered_mapping_coverage),
    )
    print(f"sales_archive_statusdate_validation_json={report['json_path']}")
    print(f"sales_archive_statusdate_validation_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["status"] == "PASS" else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
