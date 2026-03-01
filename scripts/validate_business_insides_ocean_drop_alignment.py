#!/usr/bin/env python3
"""Validate BUSINESS_INSIDES alignment against locked ocean-drop anchor (fail-closed)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.ocean_drop_anchor import DEFAULT_REGISTRY, load_ocean_drop_anchor
from scripts.build_ocean_drop_reference_snapshot import build_ocean_drop_snapshot_dataframe
from scripts.generate_business_insides import generate_business_insides
from scripts.validate_sales_truth_ocean_drop_parity import validate_sales_truth_ocean_drop_parity

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "business_insides"
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "exports" / "validation" / "business_insides_ocean_drop_alignment"


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# BUSINESS_INSIDES Ocean Drop Alignment",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- parity_status: `{report['parity_status']}`",
        f"- volatility_days: `{report['volatility_days']}`",
        f"- snapshot_json: `{report['snapshot_json_path']}`",
        f"- anchor_path: `{report['anchor_path']}`",
        f"- anchor_sha256: `{report['anchor_sha256']}`",
        f"- nonvolatile_mismatch_count: `{report['nonvolatile_mismatch_count']}`",
        f"- volatile_mismatch_count: `{report['volatile_mismatch_count']}`",
        "",
        "| date | bi_units_delivered | ref_units_delivered | bi_net_rev_kzt | ref_net_rev_kzt | volatile | match |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["daily_rows"]:
        lines.append(
            f"| `{row['date']}` | {row['bi_units']:.2f} | {row['ref_units']:.2f} | "
            f"{row['bi_net_rev_kzt']:.2f} | {row['ref_net_rev_kzt']:.2f} | {str(row['is_volatile']).lower()} | {str(row['match']).lower()} |"
        )
    if report["nonvolatile_mismatches"]:
        lines.extend(["", "## Non-Volatile Mismatches", ""])
        for item in report["nonvolatile_mismatches"][:200]:
            lines.append(f"- {item}")
    if report["volatile_mismatches"]:
        lines.extend(["", "## Volatile Mismatches", ""])
        for item in report["volatile_mismatches"][:200]:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def validate_business_insides_ocean_drop_alignment(
    *,
    db_path: Path,
    as_of: date,
    output_dir: Path,
    anchor_registry: Path,
    report_root: Path,
    strict: bool,
    window_days: int,
    volatility_days: int,
) -> dict[str, Any]:
    if window_days <= 0:
        raise RuntimeError("window_days must be > 0")
    if volatility_days < 0:
        raise RuntimeError("volatility_days must be >= 0")

    anchor = load_ocean_drop_anchor(anchor_registry)
    generate_result = generate_business_insides(
        db_path=db_path.resolve(),
        as_of=as_of,
        output_dir=output_dir.resolve(),
        strict=True,
        ocean_drop_anchor_registry=anchor_registry.resolve(),
        bi_alignment_output_root=report_root.resolve(),
        bi_alignment_window_days=window_days,
        archive_orders_globs=[],
    )

    snapshot_json = Path(generate_result["latest_json_path"]).resolve()
    payload = json.loads(snapshot_json.read_text(encoding="utf-8"))
    external_check = payload.get("external_check") or {}
    parity_status = str(external_check.get("status") or "").upper()
    if parity_status != "PASS":
        raise RuntimeError(f"BUSINESS_INSIDES external check is not PASS: {external_check}")

    parity = validate_sales_truth_ocean_drop_parity(
        db_path=db_path.resolve(),
        as_of=as_of,
        ocean_drop_path=Path(anchor["ocean_drop_path_resolved"]).resolve(),
        output_root=report_root.resolve(),
        volatility_days=14,
        strict=False,
        crm_archive_lookup_path=None,
        window_days=window_days,
    )

    start_day = as_of - timedelta(days=window_days - 1)
    ref_df, _meta = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=Path(anchor["ocean_drop_path_resolved"]).resolve(),
        as_of=as_of,
        crm_archive_lookup_path=None,
        include_as_of_day=True,
        strict=True,
    )
    ref_df = ref_df[
        (ref_df["status_internal"] == "DELIVERED")
        & (ref_df["return_flag"] == 0)
        & (ref_df["sale_date"] >= start_day.isoformat())
        & (ref_df["sale_date"] <= as_of.isoformat())
    ].copy()

    ref_daily = (
        ref_df.groupby("sale_date", dropna=False)
        .agg(ref_units=("quantity", "sum"), ref_net_rev_kzt=("net_rev_kzt", "sum"))
        .reset_index()
    )
    ref_map = {
        str(row["sale_date"]): (_safe_float(row["ref_units"]), _safe_float(row["ref_net_rev_kzt"]))
        for _, row in ref_daily.iterrows()
    }

    bi_rows = payload.get("last_7_days") or []
    bi_map: dict[str, tuple[float, float]] = {}
    for row in bi_rows:
        day = str(row.get("date") or "")
        if not day:
            continue
        units = row.get("units_delivered")
        net = row.get("net_rev_kzt")
        bi_map[day] = (
            _safe_float(units) if units is not None else 0.0,
            _safe_float(net) if net is not None else 0.0,
        )

    all_days = sorted(set(ref_map.keys()) | set(bi_map.keys()))
    daily_rows: list[dict[str, Any]] = []
    nonvolatile_mismatches: list[str] = []
    volatile_mismatches: list[str] = []
    diff_rows: list[dict[str, Any]] = []
    volatile_start = (
        as_of - timedelta(days=max(0, volatility_days - 1))
        if volatility_days > 0
        else date.max
    )
    for day in all_days:
        ref_units, ref_rev = ref_map.get(day, (0.0, 0.0))
        bi_units, bi_rev = bi_map.get(day, (0.0, 0.0))
        match = abs(ref_units - bi_units) < 1e-9 and abs(ref_rev - bi_rev) <= 1.0
        day_date = date.fromisoformat(day)
        is_volatile = bool(day_date >= volatile_start)
        daily_rows.append(
            {
                "date": day,
                "bi_units": bi_units,
                "ref_units": ref_units,
                "bi_net_rev_kzt": bi_rev,
                "ref_net_rev_kzt": ref_rev,
                "is_volatile": is_volatile,
                "match": match,
            }
        )
        if not match:
            message = (
                f"{day}: bi_units={bi_units:.2f} ref_units={ref_units:.2f} "
                f"bi_net_rev={bi_rev:.2f} ref_net_rev={ref_rev:.2f}"
            )
            if is_volatile:
                volatile_mismatches.append(message)
            else:
                nonvolatile_mismatches.append(message)
            diff_rows.append(
                {
                    "date": day,
                    "bi_units": bi_units,
                    "ref_units": ref_units,
                    "bi_net_rev_kzt": bi_rev,
                    "ref_net_rev_kzt": ref_rev,
                    "is_volatile": is_volatile,
                }
            )

    out_dir = report_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_csv = out_dir / "alignment_diff_daily.csv"
    pd.DataFrame(diff_rows).to_csv(diff_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "status": "PASS"
        if not nonvolatile_mismatches and parity.get("status") == "PASS"
        else "FAIL",
        "parity_status": str(parity.get("status") or "FAIL"),
        "volatility_days": int(volatility_days),
        "snapshot_json_path": str(snapshot_json),
        "snapshot_markdown_path": str(generate_result["latest_path"]),
        "anchor_path": str(anchor["ocean_drop_path_resolved"]),
        "anchor_sha256": str(anchor["sha256"]),
        "nonvolatile_mismatch_count": len(nonvolatile_mismatches),
        "volatile_mismatch_count": len(volatile_mismatches),
        "nonvolatile_mismatches": nonvolatile_mismatches,
        "volatile_mismatches": volatile_mismatches,
        "daily_rows": daily_rows,
        "alignment_diff_csv": str(diff_csv),
        "parity_report_json": str(out_dir / "parity_report.json"),
    }
    report_json = out_dir / "alignment_report.json"
    report_md = out_dir / "alignment_report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")
    report["report_json"] = str(report_json)
    report["report_md"] = str(report_md)

    if strict and report["status"] != "PASS":
        raise RuntimeError("BUSINESS_INSIDES ocean-drop alignment failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BUSINESS_INSIDES alignment against ocean-drop anchor")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--anchor-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--volatility-days", type=int, default=14)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_business_insides_ocean_drop_alignment(
        db_path=args.db,
        as_of=date.fromisoformat(str(args.as_of)),
        output_dir=args.output_dir,
        anchor_registry=args.anchor_registry,
        report_root=args.output_root,
        strict=bool(args.strict),
        window_days=int(args.window_days),
        volatility_days=int(args.volatility_days),
    )
    print(f"business_insides_alignment_json={report['report_json']}")
    print(f"business_insides_alignment_md={report['report_md']}")
    print(f"status={report['status']}")
    return 0 if (report["status"] == "PASS" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
