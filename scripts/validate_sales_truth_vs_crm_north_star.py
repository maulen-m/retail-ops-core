#!/usr/bin/env python3
"""Fail-closed validator: DB sales truth must stay inside CRM/reconciled band."""

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


class SalesTruthVsCRMError(RuntimeError):
    """Raised when strict North Star ceiling validation fails."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate DB sales truth vs CRM/reconciled North Star band."
    )
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--crm-workbook",
        default="~/Downloads/SALES_KSP_CRM_GPT_Sales_archive.xlsx",
    )
    parser.add_argument(
        "--reconciled-workbook",
        default="~/Downloads/Claude_Reconciled_plus_crm_corrected.xlsx",
    )
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--net-rev-tolerance-kzt", type=float, default=1.0)
    parser.add_argument("--units-tolerance", type=float, default=0.0)
    parser.add_argument("--min-verified-date-ratio", type=float, default=0.95)
    parser.add_argument(
        "--output-dir",
        default="exports/validation/crm_north_star_rebuild/2026-03-05",
    )
    return parser


def _agg_day_store(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = (
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
    return out


def _fetch_db_orders_outside_window(
    db_path: Path,
    order_ids: list[str],
    start: str,
    end: str,
) -> set[str]:
    if not order_ids:
        return set()
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        out: set[str] = set()
        chunk_size = 900
        for offset in range(0, len(order_ids), chunk_size):
            chunk = order_ids[offset : offset + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"""
                SELECT DISTINCT CAST(order_id AS TEXT) AS order_id
                FROM view_sales_line_truth
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
                  AND (date(sale_date) < date(?) OR date(sale_date) > date(?))
            """
            rows = conn.execute(query, [*chunk, start, end]).fetchall()
            out.update({str(row[0]) for row in rows if row and row[0]})
    finally:
        conn.close()
    return out


def _agg_sku(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    out = (
        df.groupby(["store_code", "sku_key"], as_index=False)
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
    return out


def validate_sales_truth_vs_crm_north_star(
    *,
    start: str,
    end: str,
    strict: bool,
    crm_workbook: Path,
    reconciled_workbook: Path,
    db_path: Path,
    net_rev_tolerance_kzt: float,
    units_tolerance: float,
    min_verified_date_ratio: float,
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    crm_df = load_crm_workbook(crm_workbook)
    rec_df = load_reconciled_workbook(reconciled_workbook)
    crm_bridged = apply_status_bridge(crm_df, rec_df)
    crm_included = crm_bridged[~crm_bridged["bridge_excluded"]].copy()
    crm_included["sale_date"] = crm_included["bridge_status_date"]
    crm_included = crm_included[
        (crm_included["sale_date"] >= start) & (crm_included["sale_date"] <= end)
    ].copy()

    db_df = load_db_truth(db_path=db_path, start=start, end=end)
    outside_window_ids = _fetch_db_orders_outside_window(
        db_path=db_path,
        order_ids=crm_included["order_id"].dropna().astype(str).unique().tolist(),
        start=start,
        end=end,
    )
    crm_included["bridge_unverified_db_outside_window"] = (
        ~crm_included["bridge_date_verified"]
        & crm_included["order_id"].astype(str).isin(outside_window_ids)
    )
    crm_strict = crm_included[~crm_included["bridge_unverified_db_outside_window"]].copy()

    day_store = _agg_day_store(db_df, "db").merge(
        _agg_day_store(crm_strict, "crm"), on=["sale_date", "store_code"], how="outer"
    )
    for col in [
        "db_orders",
        "db_units",
        "db_net_rev_kzt",
        "crm_orders",
        "crm_units",
        "crm_net_rev_kzt",
    ]:
        day_store[col] = day_store[col].fillna(0.0)
    day_store["over_ceiling_orders"] = (
        day_store["db_orders"] - day_store["crm_orders"]
    ).clip(lower=0)
    day_store["over_ceiling_units"] = (
        day_store["db_units"] - day_store["crm_units"]
    ).clip(lower=0)
    day_store["floor_gap_orders"] = (
        day_store["crm_orders"] - day_store["db_orders"]
    ).clip(lower=0)
    day_store["floor_gap_units"] = (
        day_store["crm_units"] - day_store["db_units"]
    ).clip(lower=0)
    day_store["over_ceiling_net_rev_kzt"] = (
        day_store["db_net_rev_kzt"] - day_store["crm_net_rev_kzt"]
    ).clip(lower=0)
    day_store["floor_gap_net_rev_kzt"] = (
        day_store["crm_net_rev_kzt"] - day_store["db_net_rev_kzt"]
    ).clip(lower=0)
    day_store["ceiling_breach"] = (
        (day_store["over_ceiling_orders"] > 0)
        | (day_store["over_ceiling_units"] > units_tolerance)
        | (day_store["over_ceiling_net_rev_kzt"] > net_rev_tolerance_kzt)
    )
    day_store["floor_breach"] = (
        (day_store["floor_gap_orders"] > 0)
        | (day_store["floor_gap_units"] > units_tolerance)
        | (day_store["floor_gap_net_rev_kzt"] > net_rev_tolerance_kzt)
    )
    day_store = day_store.sort_values(["sale_date", "store_code"])

    by_sku = _agg_sku(db_df, "db").merge(
        _agg_sku(crm_strict, "crm"), on=["store_code", "sku_key"], how="outer"
    )
    for col in [
        "db_orders",
        "db_units",
        "db_net_rev_kzt",
        "crm_orders",
        "crm_units",
        "crm_net_rev_kzt",
    ]:
        by_sku[col] = by_sku[col].fillna(0.0)
    by_sku["over_ceiling_units"] = (by_sku["db_units"] - by_sku["crm_units"]).clip(lower=0)
    by_sku["floor_gap_units"] = (by_sku["crm_units"] - by_sku["db_units"]).clip(lower=0)
    by_sku["over_ceiling_net_rev_kzt"] = (
        by_sku["db_net_rev_kzt"] - by_sku["crm_net_rev_kzt"]
    ).clip(lower=0)
    by_sku["floor_gap_net_rev_kzt"] = (
        by_sku["crm_net_rev_kzt"] - by_sku["db_net_rev_kzt"]
    ).clip(lower=0)
    by_sku["ceiling_breach"] = (by_sku["over_ceiling_units"] > units_tolerance) | (
        by_sku["over_ceiling_net_rev_kzt"] > net_rev_tolerance_kzt
    )
    by_sku["floor_breach"] = (by_sku["floor_gap_units"] > units_tolerance) | (
        by_sku["floor_gap_net_rev_kzt"] > net_rev_tolerance_kzt
    )
    by_sku = by_sku.sort_values(["store_code", "sku_key"])

    db_orders = db_df[["order_id", "sale_date", "store_code"]].drop_duplicates()
    crm_orders = crm_strict[
        [
            "order_id",
            "sale_date",
            "store_code",
            "bridge_status",
            "bridge_status_date",
            "bridge_date_verified",
            "bridge_unverified_db_outside_window",
        ]
    ].drop_duplicates()
    gap = db_orders.merge(
        crm_orders,
        on=["order_id"],
        how="outer",
        suffixes=("_db", "_crm"),
        indicator=True,
    )
    gap["classifier"] = gap["_merge"].map(
        {"left_only": "IN_DB_ONLY", "right_only": "IN_CRM_ONLY", "both": "BOTH"}
    )
    gap["classifier"] = gap["classifier"].astype(str)
    both_mask = gap["classifier"] == "BOTH"
    mismatch_mask = both_mask & (gap["sale_date_db"] != gap["sale_date_crm"])
    verified_mask = mismatch_mask & gap["bridge_date_verified"].fillna(False)
    unverified_mask = mismatch_mask & ~gap["bridge_date_verified"].fillna(False)
    gap.loc[verified_mask, "classifier"] = "DATE_MISMATCH_VERIFIED"
    gap.loc[unverified_mask, "classifier"] = "DATE_MISMATCH_UNVERIFIED"
    gap = gap.drop(columns=["_merge"]).sort_values(["classifier", "order_id"])

    floor_day_store = day_store[day_store["floor_breach"]].copy()

    day_store_csv = output_dir / "sales_truth_vs_crm_by_day_store.csv"
    by_sku_csv = output_dir / "sales_truth_vs_crm_by_sku.csv"
    gap_csv = output_dir / "sales_truth_vs_crm_gap_classifier.csv"
    floor_csv = output_dir / "sales_truth_vs_crm_floor_gaps.csv"
    report_md = output_dir / "sales_truth_vs_crm_report.md"
    report_json = output_dir / "sales_truth_vs_crm_report.json"
    root_causes_md = output_dir / "sales_truth_vs_crm_root_causes.md"

    day_store.to_csv(day_store_csv, index=False)
    by_sku.to_csv(by_sku_csv, index=False)
    gap.to_csv(gap_csv, index=False)
    floor_day_store.to_csv(floor_csv, index=False)

    breach_days = int(day_store["ceiling_breach"].sum())
    floor_days = int(day_store["floor_breach"].sum())
    breach_skus = int(by_sku["ceiling_breach"].sum())
    floor_skus = int(by_sku["floor_breach"].sum())
    db_only_orders = int((gap["classifier"] == "IN_DB_ONLY").sum())
    crm_only_orders = int((gap["classifier"] == "IN_CRM_ONLY").sum())
    chronology_mismatch_orders = int((gap["classifier"] == "DATE_MISMATCH_VERIFIED").sum())
    chronology_unverified_orders = int((gap["classifier"] == "DATE_MISMATCH_UNVERIFIED").sum())
    bridge_verified_rows = int(crm_included["bridge_date_verified"].sum())
    bridge_unverified_rows = int((~crm_included["bridge_date_verified"]).sum())
    bridge_verified_ratio = float(
        bridge_verified_rows / max(1, bridge_verified_rows + bridge_unverified_rows)
    )
    status = (
        "PASS"
        if breach_days == 0
        and breach_skus == 0
        and floor_days == 0
        and floor_skus == 0
        and chronology_mismatch_orders == 0
        else "FAIL"
    )

    payload: dict[str, object] = {
        "status": status,
        "strict": strict,
        "period": {"start": start, "end": end},
        "breach_days": breach_days,
        "floor_days": floor_days,
        "breach_skus": breach_skus,
        "floor_skus": floor_skus,
        "db_only_orders": db_only_orders,
        "crm_only_orders": crm_only_orders,
        "chronology_mismatch_orders": chronology_mismatch_orders,
        "chronology_unverified_orders": chronology_unverified_orders,
        "bridge_unverified_db_outside_window_excluded": int(
            crm_included["bridge_unverified_db_outside_window"].sum()
        ),
        "bridge_date_verified_rows": bridge_verified_rows,
        "bridge_date_unverified_rows": bridge_unverified_rows,
        "bridge_date_verified_ratio": round(bridge_verified_ratio, 6),
        "tolerances": {
            "net_rev_tolerance_kzt": float(net_rev_tolerance_kzt),
            "units_tolerance": float(units_tolerance),
            "min_verified_date_ratio": float(min_verified_date_ratio),
        },
        "rows": {
            "crm_included": len(crm_included),
            "crm_strict_rows": len(crm_strict),
            "db_truth": len(db_df),
        },
        "outputs": {
            "sales_truth_vs_crm_by_day_store_csv": str(day_store_csv.resolve()),
            "sales_truth_vs_crm_by_sku_csv": str(by_sku_csv.resolve()),
            "sales_truth_vs_crm_gap_classifier_csv": str(gap_csv.resolve()),
            "sales_truth_vs_crm_floor_gaps_csv": str(floor_csv.resolve()),
            "sales_truth_vs_crm_report_md": str(report_md.resolve()),
            "sales_truth_vs_crm_root_causes_md": str(root_causes_md.resolve()),
            "sales_truth_vs_crm_report_json": str(report_json.resolve()),
        },
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md.write_text(
        "\n".join(
            [
                "# Sales Truth vs CRM North Star",
                "",
                f"- period: `{start}`..`{end}`",
                f"- status: `{status}`",
                f"- breach_days: `{breach_days}`",
                f"- floor_days: `{floor_days}`",
                f"- breach_skus: `{breach_skus}`",
                f"- floor_skus: `{floor_skus}`",
                f"- db_only_orders: `{db_only_orders}`",
                f"- crm_only_orders: `{crm_only_orders}`",
                f"- chronology_mismatch_orders: `{chronology_mismatch_orders}`",
                f"- chronology_unverified_orders: `{chronology_unverified_orders}`",
                f"- bridge_unverified_db_outside_window_excluded: `{int(crm_included['bridge_unverified_db_outside_window'].sum())}`",
                f"- bridge_date_verified_rows: `{bridge_verified_rows}`",
                f"- bridge_date_unverified_rows: `{bridge_unverified_rows}`",
                f"- bridge_date_verified_ratio: `{bridge_verified_ratio:.4f}`",
                "",
                (
                    "Fail-closed rule: DB truth must stay within CRM/reconciled band "
                    "(no over-ceiling, no floor gaps, no chronology mismatches)."
                ),
            ]
        ),
        encoding="utf-8",
    )
    classifier_counts = gap["classifier"].value_counts(dropna=False).to_dict()
    root_causes_md.write_text(
        "\n".join(
            [
                "# Sales Truth vs CRM Root Causes",
                "",
                "## Classifier Counts",
                "",
                *[
                    f"- `{key}`: `{int(value)}`"
                    for key, value in sorted(classifier_counts.items(), key=lambda kv: kv[0])
                ],
                "",
                "## Day/Store Breach Counts",
                "",
                f"- ceiling_breach_days: `{breach_days}`",
                f"- floor_breach_days: `{floor_days}`",
                f"- chronology_mismatch_orders: `{chronology_mismatch_orders}`",
                f"- chronology_unverified_orders: `{chronology_unverified_orders}`",
            ]
        ),
        encoding="utf-8",
    )

    if strict and bridge_verified_ratio < float(min_verified_date_ratio):
        raise SalesTruthVsCRMError(
            (
                "CRM status-date bridge coverage below strict threshold: "
                f"verified_ratio={bridge_verified_ratio:.4f} "
                f"< min_verified_date_ratio={float(min_verified_date_ratio):.4f}"
            )
        )

    if strict and status != "PASS":
        raise SalesTruthVsCRMError(
            (
                "CRM North Star band breaches detected: "
                f"breach_days={breach_days}, floor_days={floor_days}, "
                f"breach_skus={breach_skus}, floor_skus={floor_skus}, "
                f"chronology_mismatch_orders={chronology_mismatch_orders}"
            )
        )
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = validate_sales_truth_vs_crm_north_star(
            start=args.start,
            end=args.end,
            strict=args.strict,
            crm_workbook=Path(args.crm_workbook),
            reconciled_workbook=Path(args.reconciled_workbook),
            db_path=Path(args.db_path),
            net_rev_tolerance_kzt=float(args.net_rev_tolerance_kzt),
            units_tolerance=float(args.units_tolerance),
            min_verified_date_ratio=float(args.min_verified_date_ratio),
            output_dir=Path(args.output_dir),
        )
    except SalesTruthVsCRMError as exc:
        print(str(exc))
        return 1
    print(
        f"sales_truth_vs_crm_report_json={payload['outputs']['sales_truth_vs_crm_report_json']}"
    )
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
