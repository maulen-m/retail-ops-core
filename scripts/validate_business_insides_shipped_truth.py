#!/usr/bin/env python3
"""Validate BUSINESS_INSIDES shipped totals against shipped-truth validator outputs."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import csv
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUSINESS_DIR = PROJECT_ROOT / "config" / "business_insides"
DEFAULT_SHIPPED_ROOT = PROJECT_ROOT / "exports" / "validation" / "shipped_truth_crm_waybill"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "business_insides_shipped_truth"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_bi_snapshot(business_dir: Path, day: str) -> Path | None:
    direct = business_dir / f"BUSINESS_INSIDES_{day}.json"
    if direct.exists():
        return direct
    snap = business_dir / "snapshots" / f"BUSINESS_INSIDES_{day}.json"
    if snap.exists():
        return snap
    return None


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# BUSINESS_INSIDES Shipped Truth Validation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- since: `{report['since']}`",
        f"- until: `{report['until']}`",
        f"- status: `{report['status']}`",
        f"- shipped_summary: `{report['shipped_summary']}`",
        "",
        "| day | api_primary_orders | bi_waybill_orders | status | details |",
        "|---|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['day']} | {row['api_primary_orders']} | {row.get('bi_waybill_orders', 'N/A')} | "
            f"{'PASS' if row['ok'] else 'FAIL'} | {row.get('details', '')} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_business_insides_shipped_truth(
    *,
    since: str,
    until: str,
    business_dir: Path,
    shipped_summary: Path,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    summary = _load_json(shipped_summary)
    rows = summary.get("rows") if isinstance(summary.get("rows"), list) else []

    per_day_api: dict[str, int] = {}
    for row in rows:
        day = str(row.get("day") or "").strip()
        if not day:
            continue
        if str(row.get("provisional", False)).lower() == "true" or bool(row.get("provisional", False)):
            continue
        per_day_api[day] = per_day_api.get(day, 0) + int(row.get("api_primary") or 0)

    report_rows: list[dict[str, Any]] = []
    mismatch_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for day in sorted(per_day_api.keys()):
        expected = int(per_day_api[day])
        snapshot_path = _resolve_bi_snapshot(business_dir, day)
        if snapshot_path is None:
            errors.append(f"{day}: missing BUSINESS_INSIDES snapshot")
            row = {
                "day": day,
                "api_primary_orders": expected,
                "bi_waybill_orders": None,
                "ok": False,
                "details": "missing_snapshot",
                "snapshot_path": "",
            }
            report_rows.append(row)
            mismatch_rows.append(row)
            continue

        payload = _load_json(snapshot_path)
        waybill = payload.get("waybill_snapshot") if isinstance(payload, dict) else {}
        totals = waybill.get("totals") if isinstance(waybill, dict) else {}
        bi_orders_raw = totals.get("orders") if isinstance(totals, dict) else None
        try:
            bi_orders = int(bi_orders_raw)
        except Exception:
            bi_orders = None

        ok = bi_orders is not None and bi_orders == expected
        if not ok:
            errors.append(
                f"{day}: shipped orders mismatch api_primary={expected} bi_waybill={bi_orders if bi_orders is not None else '<missing>'}"
            )
        row = {
            "day": day,
            "api_primary_orders": expected,
            "bi_waybill_orders": bi_orders,
            "ok": ok,
            "details": "ok" if ok else "mismatch",
            "snapshot_path": str(snapshot_path),
        }
        report_rows.append(row)
        if not ok:
            mismatch_rows.append(row)

    status = "PASS" if not errors else "FAIL"
    out_dir = output_root / f"{since}_to_{until}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since,
        "until": until,
        "status": status,
        "ok": status == "PASS",
        "business_dir": str(business_dir.resolve()),
        "shipped_summary": str(shipped_summary.resolve()),
        "rows": report_rows,
        "errors": errors,
    }

    json_path = out_dir / "summary.json"
    md_path = out_dir / "report.md"
    mismatch_csv_path = out_dir / "mismatch_days.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    with mismatch_csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "day",
                "api_primary_orders",
                "bi_waybill_orders",
                "details",
                "snapshot_path",
            ],
        )
        writer.writeheader()
        for row in mismatch_rows:
            writer.writerow(
                {
                    "day": row["day"],
                    "api_primary_orders": row["api_primary_orders"],
                    "bi_waybill_orders": row.get("bi_waybill_orders"),
                    "details": row["details"],
                    "snapshot_path": row.get("snapshot_path") or "",
                }
            )

    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    report["mismatch_csv_path"] = str(mismatch_csv_path)

    if strict and errors:
        raise RuntimeError("business insides shipped truth validation failed")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BUSINESS_INSIDES shipped totals against shipped truth")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--business-dir", type=Path, default=DEFAULT_BUSINESS_DIR)
    parser.add_argument("--shipped-root", type=Path, default=DEFAULT_SHIPPED_ROOT)
    parser.add_argument("--shipped-summary", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    since = str(args.since)
    until = str(args.until)
    shipped_summary = args.shipped_summary
    if shipped_summary is None:
        shipped_summary = args.shipped_root / f"{since}_to_{until}" / "summary.json"
    if not shipped_summary.exists():
        raise SystemExit(f"missing shipped summary: {shipped_summary}")

    report = validate_business_insides_shipped_truth(
        since=since,
        until=until,
        business_dir=args.business_dir,
        shipped_summary=shipped_summary,
        output_root=args.output_root,
        strict=False,
    )
    print(f"business_insides_shipped_truth_json={report['json_path']}")
    print(f"business_insides_shipped_truth_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
