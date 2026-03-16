#!/usr/bin/env python3
"""Validate WebUI archive truth projection against the CRM delivered-day band."""

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

from scripts.north_star_workbook_utils import load_crm_workbook
from scripts.build_webui_shipped_projection import build_webui_shipped_projection
from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)

DEFAULT_CRM_WORKBOOK = Path("~/Downloads/SALES_KSP_CRM_GPT_Sales_archive.xlsx")
DEFAULT_BASELINE_REPORT = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "crm_north_star_restate"
    / "2026-03-06"
    / "sales_truth_vs_crm_report.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06"
)


class WebuiArchiveVsCRMError(RuntimeError):
    """Raised when strict WebUI-vs-CRM band validation fails."""


def _resolve_ledger_root(ledger_root: Path | None) -> Path:
    if ledger_root is None:
        return resolve_latest_dir(DEFAULT_LEDGER_ROOT)
    candidate = ledger_root.expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = DEFAULT_LEDGER_ROOT / candidate
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(f"ledger root not found: {ledger_root}")


def _agg_day_store(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["sale_date", "store_code", f"{prefix}_orders", f"{prefix}_units", f"{prefix}_net_rev_kzt"])
    return (
        df.groupby(["sale_date", "store_code"], as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            units=("units", "sum"),
            net_rev_kzt=("net_rev_kzt", "sum"),
        )
        .rename(
            columns={
                "orders": f"{prefix}_orders",
                "units": f"{prefix}_units",
                "net_rev_kzt": f"{prefix}_net_rev_kzt",
            }
        )
    )


def validate_webui_archive_vs_crm_band(
    *,
    start: str,
    end: str,
    crm_workbook: Path,
    db_path: Path,
    ledger_root: Path | None,
    output_dir: Path,
    strict: bool,
    baseline_report_json: Path,
    units_tolerance: float,
    net_rev_tolerance_kzt: float,
    truth_event: str = "delivered_projection",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_ledger_root = _resolve_ledger_root(ledger_root)
    if str(truth_event) == "shipped_projection":
        shipped_report = build_webui_shipped_projection(
            ledger_root=resolved_ledger_root,
            output_root=PROJECT_ROOT / "exports" / "webui_projection",
            run_id=f"webui_shipped_projection_{datetime.now():%Y%m%d}",
            start=start,
            end=end,
        )
        if isinstance(shipped_report, tuple):
            webui_projection, projection_meta = shipped_report
        else:
            webui_projection = shipped_report["projection"]
            projection_meta = shipped_report["projection_manifest"]
    else:
        webui_projection, projection_meta = build_webui_truth_projection(
            db_path=db_path.resolve(),
            ledger_run_root=resolved_ledger_root,
            start=start,
            end=end,
        )
    crm_df = load_crm_workbook(crm_workbook)
    crm_df = crm_df[(crm_df["sale_date"] >= start) & (crm_df["sale_date"] <= end)].copy()
    if str(truth_event) == "shipped_projection":
        webui_orders = webui_projection.copy()
    else:
        match_status = (
            webui_projection["db_match_status"]
            if "db_match_status" in webui_projection.columns
            else pd.Series(["MATCHED"] * len(webui_projection), index=webui_projection.index)
        )
        webui_orders = webui_projection[match_status == "MATCHED"].copy()

    by_day_store = _agg_day_store(webui_orders, "webui").merge(
        _agg_day_store(crm_df, "crm"),
        on=["sale_date", "store_code"],
        how="outer",
    ).fillna(0.0)
    by_day_store["over_ceiling_orders"] = (by_day_store["webui_orders"] - by_day_store["crm_orders"]).clip(lower=0)
    by_day_store["floor_gap_orders"] = (by_day_store["crm_orders"] - by_day_store["webui_orders"]).clip(lower=0)
    by_day_store["over_ceiling_units"] = (by_day_store["webui_units"] - by_day_store["crm_units"]).clip(lower=0)
    by_day_store["floor_gap_units"] = (by_day_store["crm_units"] - by_day_store["webui_units"]).clip(lower=0)
    by_day_store["over_ceiling_net_rev_kzt"] = (
        by_day_store["webui_net_rev_kzt"] - by_day_store["crm_net_rev_kzt"]
    ).clip(lower=0)
    by_day_store["floor_gap_net_rev_kzt"] = (
        by_day_store["crm_net_rev_kzt"] - by_day_store["webui_net_rev_kzt"]
    ).clip(lower=0)
    by_day_store["ceiling_breach"] = (
        (by_day_store["over_ceiling_orders"] > 0)
        | (by_day_store["over_ceiling_units"] > float(units_tolerance))
        | (by_day_store["over_ceiling_net_rev_kzt"] > float(net_rev_tolerance_kzt))
    )
    by_day_store["floor_breach"] = (
        (by_day_store["floor_gap_orders"] > 0)
        | (by_day_store["floor_gap_units"] > float(units_tolerance))
        | (by_day_store["floor_gap_net_rev_kzt"] > float(net_rev_tolerance_kzt))
    )
    by_day_store = by_day_store.sort_values(["sale_date", "store_code"])

    crm_orders = crm_df[["order_id", "sale_date", "store_code"]].drop_duplicates()
    webui_order_dates = webui_orders[["order_id", "sale_date", "store_code"]].drop_duplicates()
    gap = webui_order_dates.merge(
        crm_orders,
        on=["order_id"],
        how="outer",
        suffixes=("_webui", "_crm"),
        indicator=True,
    )
    gap["classifier"] = gap["_merge"].map(
        {"left_only": "IN_WEBUI_ONLY", "right_only": "IN_CRM_ONLY", "both": "BOTH"}
    ).astype(object)
    mismatch_mask = (
        (gap["classifier"] == "BOTH")
        & (
            (gap["sale_date_webui"] != gap["sale_date_crm"])
            | (gap["store_code_webui"] != gap["store_code_crm"])
        )
    )
    gap.loc[mismatch_mask, "classifier"] = "DATE_MISMATCH"
    gap = gap.drop(columns=["_merge"]).sort_values(["classifier", "order_id"])

    baseline_payload = (
        json.loads(baseline_report_json.read_text(encoding="utf-8"))
        if baseline_report_json.exists()
        else None
    )
    baseline_mismatch_orders = (
        int(baseline_payload.get("chronology_mismatch_orders", 0))
        if baseline_payload
        else None
    )
    chronology_mismatch_orders = int((gap["classifier"] == "DATE_MISMATCH").sum())
    chronology_improvement_orders = (
        None if baseline_mismatch_orders is None else baseline_mismatch_orders - chronology_mismatch_orders
    )

    by_day_store_csv = output_dir / "webui_vs_crm_by_day_store.csv"
    gap_csv = output_dir / "webui_vs_crm_gap_classifier.csv"
    report_md = output_dir / "webui_truth_promotion_report.md"
    report_json = output_dir / "webui_truth_promotion_report.json"
    by_day_store.to_csv(by_day_store_csv, index=False, encoding="utf-8")
    gap.to_csv(gap_csv, index=False, encoding="utf-8")

    breach_days = int(by_day_store["ceiling_breach"].sum())
    floor_days = int(by_day_store["floor_breach"].sum())
    status = "PASS" if breach_days == 0 and floor_days == 0 and chronology_mismatch_orders == 0 else "FAIL"
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "ok": status == "PASS",
        "strict": bool(strict),
        "period": {"start": start, "end": end},
        "truth_event": str(truth_event),
        "ledger_root": str(resolved_ledger_root),
        "crm_workbook": str(crm_workbook),
        "projection_meta": projection_meta,
        "breach_days": breach_days,
        "floor_days": floor_days,
        "db_missing_orders": int(projection_meta.get("missing_in_db_orders", 0)),
        "chronology_mismatch_orders": chronology_mismatch_orders,
        "baseline_chronology_mismatch_orders": baseline_mismatch_orders,
        "chronology_improvement_orders": chronology_improvement_orders,
        "outputs": {
            "webui_vs_crm_by_day_store_csv": str(by_day_store_csv),
            "webui_vs_crm_gap_classifier_csv": str(gap_csv),
            "webui_truth_promotion_report_md": str(report_md),
            "webui_truth_promotion_report_json": str(report_json),
        },
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# WebUI Truth Promotion Report",
                "",
                f"- status: `{status}`",
                f"- period: `{start}`..`{end}`",
                f"- truth_event: `{truth_event}`",
                f"- breach_days: `{breach_days}`",
                f"- floor_days: `{floor_days}`",
                f"- chronology_mismatch_orders: `{chronology_mismatch_orders}`",
                f"- baseline_chronology_mismatch_orders: `{baseline_mismatch_orders}`",
                f"- chronology_improvement_orders: `{chronology_improvement_orders}`",
                f"- db_missing_orders: `{projection_meta.get('missing_in_db_orders', 0)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and baseline_mismatch_orders is None:
        raise WebuiArchiveVsCRMError("baseline CRM restate report missing for chronology comparison")
    if strict and chronology_improvement_orders is not None and chronology_improvement_orders <= 0:
        raise WebuiArchiveVsCRMError(
            f"webui chronology did not beat current baseline: improvement={chronology_improvement_orders}"
        )
    if strict and not report["ok"]:
        raise WebuiArchiveVsCRMError(
            f"webui archive vs crm band failed: breach_days={breach_days} floor_days={floor_days} chronology_mismatch_orders={chronology_mismatch_orders}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate WebUI archive truth against CRM band")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--crm-workbook", type=Path, default=DEFAULT_CRM_WORKBOOK)
    parser.add_argument("--db-path", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--baseline-report-json", type=Path, default=DEFAULT_BASELINE_REPORT)
    parser.add_argument("--units-tolerance", type=float, default=0.0)
    parser.add_argument("--net-rev-tolerance-kzt", type=float, default=1.0)
    parser.add_argument("--truth-event", choices=["delivered_projection", "shipped_projection"], default="delivered_projection")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_webui_archive_vs_crm_band(
            start=str(args.start),
            end=str(args.end),
            crm_workbook=args.crm_workbook,
            db_path=args.db_path,
            ledger_root=args.ledger_root,
            output_dir=args.output_dir,
            strict=bool(args.strict),
            baseline_report_json=args.baseline_report_json,
            units_tolerance=float(args.units_tolerance),
            net_rev_tolerance_kzt=float(args.net_rev_tolerance_kzt),
            truth_event=str(args.truth_event),
        )
    except WebuiArchiveVsCRMError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_CRM_BAND_FAIL")
        print(f"message={exc}")
        return 1

    print(f"webui_truth_promotion_report_json={report['outputs']['webui_truth_promotion_report_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
