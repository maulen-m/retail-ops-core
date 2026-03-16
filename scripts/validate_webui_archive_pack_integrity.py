#!/usr/bin/env python3
"""Validate normalized Kaspi WebUI archive source packs."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_STORES_CONFIG,
    PACK_NORMALIZED_COLUMNS,
    compute_sha256,
    load_enabled_stores,
    load_pack_manifest,
    load_pack_rows,
)


class WebuiPackIntegrityError(RuntimeError):
    """Raised when WebUI pack integrity fails in strict mode."""


def validate_webui_archive_pack_integrity(
    *,
    pack_root: Path,
    stores_config: Path,
    strict: bool,
) -> dict[str, Any]:
    pack_root = pack_root.expanduser().resolve()
    manifest = load_pack_manifest(pack_root)
    rows = load_pack_rows(pack_root)
    enabled_stores = load_enabled_stores(stores_config)

    errors: list[str] = []
    warnings: list[str] = []
    required_columns_missing = [col for col in PACK_NORMALIZED_COLUMNS if col not in rows.columns]
    if required_columns_missing:
        errors.append(f"normalized_rows missing columns: {', '.join(required_columns_missing)}")

    manifest_missing_store_files = sorted(
        set(str(store).upper() for store in manifest.get("missing_store_files") or [])
    )
    if manifest_missing_store_files:
        errors.append(f"missing store files: {', '.join(manifest_missing_store_files)}")

    stores_present = sorted({str(value).upper() for value in rows.get("store_code", pd.Series(dtype=object)).tolist() if str(value).strip()})
    stores_without_rows = [store for store in enabled_stores if store not in stores_present]
    if stores_without_rows:
        warnings.append(f"enabled stores without normalized rows: {', '.join(stores_without_rows)}")

    delivered_missing_status_change_date = int(
        rows.get("status_change_missing", pd.Series(dtype=bool)).fillna(False).sum()
    ) if not rows.empty else 0
    if delivered_missing_status_change_date > 0:
        errors.append(
            f"delivered rows missing status_change_at: {delivered_missing_status_change_date}"
        )

    duplicate_rows = rows[rows.duplicated(["store_code", "row_fingerprint"], keep=False)].copy()
    duplicate_count = int(len(duplicate_rows))
    if duplicate_count > 0:
        errors.append(f"duplicate normalized rows detected: {duplicate_count}")

    hash_mismatch_files: list[str] = []
    source_files_checked = 0
    for item in manifest.get("files", []):
        source_path = Path(str(item.get("absolute_source_file") or ""))
        expected_sha = str(item.get("source_file_sha256") or "").strip()
        if not source_path.exists():
            errors.append(f"manifest source file missing: {source_path}")
            continue
        source_files_checked += 1
        actual_sha = compute_sha256(source_path)
        if expected_sha and actual_sha != expected_sha:
            hash_mismatch_files.append(str(source_path))
    if hash_mismatch_files:
        errors.append(f"source file hash mismatch: {len(hash_mismatch_files)}")

    per_store = (
        rows.groupby("store_code", as_index=False)
        .agg(
            rows=("order_id", "size"),
            unique_orders=("order_id", "nunique"),
            delivered_rows=("status_internal", lambda s: int((s == "DELIVERED").sum())),
        )
        .sort_values("store_code")
        if not rows.empty
        else pd.DataFrame(columns=["store_code", "rows", "unique_orders", "delivered_rows"])
    )

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pack_root": str(pack_root),
        "pack_id": manifest.get("pack_id"),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "strict": bool(strict),
        "source_file_count": int(manifest.get("source_file_count", 0)),
        "source_files_checked": source_files_checked,
        "enabled_stores": enabled_stores,
        "stores_present": stores_present,
        "manifest_missing_store_files": manifest_missing_store_files,
        "stores_without_rows": stores_without_rows,
        "delivered_missing_status_change_date": delivered_missing_status_change_date,
        "duplicate_rows": duplicate_count,
        "hash_mismatch_files": hash_mismatch_files,
        "errors": errors,
        "warnings": warnings,
    }

    report_json = pack_root / "integrity_report.json"
    report_md = pack_root / "integrity_report.md"
    duplicate_csv = pack_root / "integrity_duplicate_rows.csv"
    duplicate_rows.to_csv(duplicate_csv, index=False, encoding="utf-8")
    report["outputs"] = {
        "integrity_report_json": str(report_json),
        "integrity_report_md": str(report_md),
        "integrity_duplicate_rows_csv": str(duplicate_csv),
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# WebUI Archive Pack Integrity",
        "",
        f"- pack_id: `{manifest.get('pack_id')}`",
        f"- status: `{report['status']}`",
        f"- source_file_count: `{report['source_file_count']}`",
        f"- stores_present: `{', '.join(stores_present)}`",
        f"- delivered_missing_status_change_date: `{delivered_missing_status_change_date}`",
        f"- duplicate_rows: `{duplicate_count}`",
        "",
        "## Per Store",
        "",
        "| store_code | rows | unique_orders | delivered_rows |",
        "|---|---:|---:|---:|",
    ]
    for row in per_store.to_dict("records"):
        lines.append(
            f"| `{row['store_code']}` | {int(row['rows'])} | {int(row['unique_orders'])} | {int(row['delivered_rows'])} |"
        )
    if errors:
        lines.extend(["", "## Errors", ""])
        for error in errors:
            lines.append(f"- {error}")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if strict and not report["ok"]:
        raise WebuiPackIntegrityError("; ".join(errors))
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate normalized WebUI archive pack integrity")
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_webui_archive_pack_integrity(
            pack_root=args.pack_root,
            stores_config=args.stores_config,
            strict=bool(args.strict),
        )
    except WebuiPackIntegrityError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_PACK_INTEGRITY_FAIL")
        print(f"message={exc}")
        return 1

    print(f"integrity_report_json={report['outputs']['integrity_report_json']}")
    print(f"integrity_report_md={report['outputs']['integrity_report_md']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
