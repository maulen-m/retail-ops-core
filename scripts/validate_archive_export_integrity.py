#!/usr/bin/env python3
"""
Validate Kaspi archive export integrity for period coverage and status-date completeness.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_kaspi_archive_history import WINDOW_DAYS, date_windows  # noqa: E402

COMPLETED_EXPORT_STATUSES = {"Завершен", "Выдан"}


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _artifact_dir(until: str, output_root: Path | None = None) -> Path:
    if output_root:
        return output_root
    return PROJECT_ROOT / "exports" / "validation" / "archive_integrity" / until


def validate_archive_export_integrity(
    *,
    export_root: Path,
    since: str,
    until: str,
    strict: bool = True,
    require_status_change_date_for_completed: bool = True,
    output_root: Path | None = None,
) -> Dict[str, Any]:
    export_root = export_root.expanduser().resolve()
    since_d = _parse_date(since)
    until_d = _parse_date(until)
    expected_windows = date_windows(since_d, until_d, WINDOW_DAYS)

    errors: List[str] = []
    stores: List[Dict[str, Any]] = []
    missing_rows: List[Dict[str, Any]] = []
    manifest_by_store: Dict[str, Dict[str, Any]] = {}

    manifest_path = export_root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            for row in manifest_payload.get("results") or []:
                store_code = str(row.get("store_code") or "").strip().upper()
                if store_code:
                    manifest_by_store[store_code] = row
        except Exception as exc:  # noqa: BLE001
            errors.append(f"failed to parse manifest.json: {exc}")

    store_dirs = sorted([p for p in export_root.glob("store_*") if p.is_dir()])
    if not store_dirs:
        errors.append(f"no store_* directories found under {export_root}")

    for store_dir in store_dirs:
        store_code = store_dir.name.replace("store_", "")
        store_report: Dict[str, Any] = {
            "store_code": store_code,
            "coverage_ok": True,
            "completed_missing_status_change_date": 0,
            "rows_total": 0,
            "manifest_orders_dedup": 0,
            "manifest_orders_selected": 0,
            "errors": [],
        }

        manifest_row = manifest_by_store.get(store_code.upper(), {})
        store_report["manifest_orders_dedup"] = int(manifest_row.get("orders_dedup") or 0)
        store_report["manifest_orders_selected"] = int(manifest_row.get("orders_selected") or 0)
        date_mode = str(manifest_row.get("date_mode") or "").strip()
        if (
            require_status_change_date_for_completed
            and date_mode == "statusChangeDate"
            and store_report["manifest_orders_dedup"] > 0
            and store_report["manifest_orders_selected"] == 0
        ):
            store_report["errors"].append(
                "statusChangeDate mode produced zero selected orders while dedup orders exist (likely missing statusChangeDate coverage)"
            )

        windows_path = store_dir / "windows.csv"
        if not windows_path.exists():
            store_report["coverage_ok"] = False
            store_report["errors"].append("missing windows.csv")
        else:
            with windows_path.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            if len(rows) != len(expected_windows):
                store_report["coverage_ok"] = False
                store_report["errors"].append(
                    f"window count mismatch expected={len(expected_windows)} got={len(rows)}"
                )
            for idx, expected in enumerate(expected_windows):
                if idx >= len(rows):
                    break
                row = rows[idx]
                exp_since, exp_until = expected
                if row.get("since") != exp_since.isoformat() or row.get("until") != exp_until.isoformat():
                    store_report["coverage_ok"] = False
                    store_report["errors"].append(
                        f"window {idx+1} bounds mismatch expected={exp_since}..{exp_until} got={row.get('since')}..{row.get('until')}"
                    )
                if str(row.get("status") or "").strip().lower() != "ok":
                    store_report["coverage_ok"] = False
                    store_report["errors"].append(
                        f"window {idx+1} status not ok ({row.get('status')})"
                    )

        csv_path = store_dir / f"ArchiveOrders_{store_code}.csv"
        if not csv_path.exists():
            store_report["errors"].append(f"missing {csv_path.name}")
        else:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
            store_report["rows_total"] = int(len(df))
            if require_status_change_date_for_completed:
                if "Статус" not in df.columns or "Дата изменения статуса" not in df.columns:
                    store_report["errors"].append("required columns missing in export CSV")
                else:
                    completed = df["Статус"].astype(str).str.strip().isin(COMPLETED_EXPORT_STATUSES)
                    missing = completed & df["Дата изменения статуса"].astype(str).str.strip().eq("")
                    missing_count = int(missing.sum())
                    store_report["completed_missing_status_change_date"] = missing_count
                    if missing_count > 0:
                        sample = df.loc[missing, ["№ заказа", "Дата поступления заказа", "Дата изменения статуса", "Статус"]].copy()
                        sample["store_code"] = store_code
                        missing_rows.extend(sample.to_dict("records"))
                        store_report["errors"].append(
                            f"completed rows missing status-change date: {missing_count}"
                        )

        if store_report["errors"]:
            errors.extend([f"{store_code}: {e}" for e in store_report["errors"]])
        stores.append(store_report)

    status = "PASS" if not errors else "FAIL"
    out_dir = _artifact_dir(until, output_root=output_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    missing_csv = out_dir / "missing_status_change_rows.csv"
    if missing_rows:
        pd.DataFrame(missing_rows).to_csv(missing_csv, index=False, encoding="utf-8")
    elif missing_csv.exists():
        missing_csv.unlink()

    report = {
        "status": status,
        "since": since,
        "until": until,
        "export_root": str(export_root),
        "stores_checked": len(stores),
        "errors": errors,
        "stores": stores,
        "artifacts": {
            "json": str(out_dir / "integrity_report.json"),
            "md": str(out_dir / "integrity_report.md"),
            "missing_status_change_rows_csv": str(missing_csv),
        },
    }

    (out_dir / "integrity_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Archive Export Integrity Report",
        "",
        f"- Status: `{status}`",
        f"- Range: `{since}` -> `{until}`",
        f"- Export root: `{export_root}`",
        f"- Stores checked: `{len(stores)}`",
        f"- Errors: `{len(errors)}`",
        "",
        "## Store Summary",
        "",
        "| Store | Coverage OK | Dedup (manifest) | Selected (manifest) | Rows | Missing completed status-change-date |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for store in stores:
        lines.append(
            f"| {store['store_code']} | {'YES' if store['coverage_ok'] else 'NO'} | "
            f"{store['manifest_orders_dedup']} | {store['manifest_orders_selected']} | "
            f"{store['rows_total']} | {store['completed_missing_status_change_date']} |"
        )

    if errors:
        lines.extend(["", "## Errors"])
        for err in errors[:200]:
            lines.append(f"- {err}")
    (out_dir / "integrity_report.md").write_text("\n".join(lines), encoding="utf-8")

    if strict and errors:
        raise RuntimeError("archive export integrity validation failed: " + "; ".join(errors))

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Kaspi archive export integrity")
    parser.add_argument("--export-root", type=Path, required=True, help="Root folder produced by export_kaspi_archive_history.py")
    parser.add_argument("--since", required=True, help="Expected range start YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="Expected range end YYYY-MM-DD")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--require-status-change-date-for-completed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail if completed rows are missing status-change date",
    )
    parser.add_argument("--output-root", type=Path, default=None, help="Optional output artifact directory")
    args = parser.parse_args()

    report = validate_archive_export_integrity(
        export_root=args.export_root,
        since=args.since,
        until=args.until,
        strict=args.strict,
        require_status_change_date_for_completed=args.require_status_change_date_for_completed,
        output_root=args.output_root,
    )
    status = report.get("status", "FAIL")
    if status == "PASS":
        print("PASS: archive export integrity validation")
        return 0
    print(
        "FAIL: archive export integrity validation"
        + (" (non-strict mode)" if not args.strict else "")
    )
    if not args.strict:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
