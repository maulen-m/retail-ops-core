#!/usr/bin/env python3
"""Build fail-closed sales truth drift report from Ocean Drop parity output."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_sales_truth_ocean_drop_parity import validate_sales_truth_ocean_drop_parity

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"
DEFAULT_PARITY_ROOT = PROJECT_ROOT / "exports" / "validation" / "sales_ocean_drop_parity"


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Sales Truth Drift Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- lookback_days: `{payload['lookback_days']}`",
        f"- status: `{payload['status']}`",
        f"- mismatch_count: `{payload['mismatch_count']}`",
        f"- parity_report: `{payload['parity_report_json']}`",
        "",
        "| sale_date | store_code | ref_units | db_units | ref_rev | db_rev | match |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| `{row['sale_date']}` | `{row['store_code']}` | {row['ref_units']:.2f} | {row['db_units']:.2f} | "
            f"{row['ref_rev_kzt']:.2f} | {row['db_rev_kzt']:.2f} | {str(row['match']).lower()} |"
        )
    if payload["mismatch_rows"]:
        lines.extend(["", "## Mismatches", ""])
        for row in payload["mismatch_rows"][:200]:
            lines.append(
                f"- {row['sale_date']} {row['store_code']}: ref_units={row['ref_units']:.2f} db_units={row['db_units']:.2f} "
                f"ref_rev={row['ref_rev_kzt']:.2f} db_rev={row['db_rev_kzt']:.2f}"
            )
    return "\n".join(lines) + "\n"


def build_sales_truth_drift_report(
    *,
    as_of: str,
    output_root: Path,
    parity_root: Path,
    lookback_days: int,
    strict: bool,
    ocean_drop_path: Path | None,
    crm_archive_lookup: Path | None,
) -> dict[str, Any]:
    if lookback_days <= 0:
        raise RuntimeError("lookback_days must be > 0")
    as_of_day = date.fromisoformat(as_of)

    parity_json = parity_root.resolve() / as_of_day.isoformat() / "parity_report.json"
    if not parity_json.exists():
        if ocean_drop_path is None:
            raise RuntimeError(f"parity report missing and no ocean drop path provided: {parity_json}")
        validate_sales_truth_ocean_drop_parity(
            db_path=PROJECT_ROOT / "db" / "app.db",
            as_of=as_of_day,
            ocean_drop_path=ocean_drop_path,
            output_root=parity_root,
            volatility_days=0,
            strict=True,
            crm_archive_lookup_path=crm_archive_lookup,
            window_days=lookback_days,
        )
    parity = json.loads(parity_json.read_text(encoding="utf-8"))

    rows = []
    start_day = as_of_day - timedelta(days=lookback_days - 1)
    for row in parity.get("daily_rows", []):
        sale_date = str(row.get("sale_date") or "")
        if not sale_date:
            continue
        if sale_date < start_day.isoformat() or sale_date > as_of_day.isoformat():
            continue
        rows.append(
            {
                "sale_date": sale_date,
                "store_code": str(row.get("store_code") or "").upper(),
                "ref_units": float(row.get("ref_units") or 0.0),
                "db_units": float(row.get("db_units") or 0.0),
                "ref_rev_kzt": float(row.get("ref_rev_kzt") or 0.0),
                "db_rev_kzt": float(row.get("db_rev_kzt") or 0.0),
                "match": bool(row.get("match", False)),
            }
        )
    rows.sort(key=lambda r: (r["sale_date"], r["store_code"]))
    mismatch_rows = [r for r in rows if not r["match"]]

    status = "PASS" if not mismatch_rows else "FAIL"
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "as_of": as_of_day.isoformat(),
        "lookback_days": lookback_days,
        "status": status,
        "mismatch_count": len(mismatch_rows),
        "rows": rows,
        "mismatch_rows": mismatch_rows,
        "parity_report_json": str(parity_json),
    }

    out_dir = output_root.resolve() / as_of_day.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "sales_truth_drift_report.json"
    out_md = out_dir / "sales_truth_drift_report.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(_render_md(payload), encoding="utf-8")

    if strict and mismatch_rows:
        raise RuntimeError("sales truth drift detected in strict mode")

    return {
        "status": status,
        "json_path": str(out_json),
        "md_path": str(out_md),
        "mismatch_count": len(mismatch_rows),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build sales truth drift report")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--parity-root", type=Path, default=DEFAULT_PARITY_ROOT)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--ocean-drop", type=Path, default=None)
    parser.add_argument("--crm-archive-lookup", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ocean_drop = args.ocean_drop
    if ocean_drop is None:
        env_path = str(os.environ.get("AB_OCEAN_DROP_SALES_PATH") or "").strip()
        if env_path:
            ocean_drop = Path(env_path)

    report = build_sales_truth_drift_report(
        as_of=str(args.as_of),
        output_root=args.output_root,
        parity_root=args.parity_root,
        lookback_days=int(args.lookback_days),
        strict=bool(args.strict),
        ocean_drop_path=ocean_drop,
        crm_archive_lookup=args.crm_archive_lookup,
    )
    print(f"sales_truth_drift_report_json={report['json_path']}")
    print(f"sales_truth_drift_report_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if (report["status"] == "PASS" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
