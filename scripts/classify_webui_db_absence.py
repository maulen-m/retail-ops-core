#!/usr/bin/env python3
"""Classify the remaining WebUI-vs-DB absence set into backfill vs quarantine paths."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MISSING_ORDERS_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "webui_promotion_delta_recon"
    / "2026-03-07"
    / "db_missing_order_candidates.csv"
)
DEFAULT_DB_ONLY_ORDERS_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "webui_promotion_delta_recon"
    / "2026-03-07"
    / "db_only_order_explanations.csv"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_shipped_authority_recon" / "2026-03-07"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


class WebuiDBAbsenceError(RuntimeError):
    """Raised when DB absence rows cannot be fully classified fail-closed."""


def _normalize_order_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def _load_presence(db_path: Path, order_ids: list[str]) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")
    if not order_ids:
        return pd.DataFrame(columns=["order_id"])
    conn = sqlite3.connect(str(db_path))
    try:
        frames: list[pd.DataFrame] = []
        for offset in range(0, len(order_ids), 900):
            chunk = order_ids[offset : offset + 900]
            ids_union = " UNION ALL ".join(["SELECT ? AS order_id"] + ["SELECT ?"] * (len(chunk) - 1))
            query = f"""
                WITH ids AS ({ids_union})
                SELECT
                    ids.order_id,
                    MAX(CASE WHEN fo.order_id IS NOT NULL THEN 1 ELSE 0 END) AS in_fact_orders,
                    MAX(CASE WHEN fe.order_id IS NOT NULL THEN 1 ELSE 0 END) AS in_fact_entries,
                    MAX(CASE WHEN sf.order_id IS NOT NULL THEN 1 ELSE 0 END) AS in_sales_fact_v2,
                    MAX(CASE WHEN fs.order_id IS NOT NULL THEN 1 ELSE 0 END) AS in_fact_sales,
                    MAX(CASE WHEN COALESCE(fo.courier_transmission_date, '') <> '' THEN 1 ELSE 0 END) AS has_courier_transmission,
                    MAX(CASE WHEN COALESCE(fo.actual_shipment_date, '') <> '' THEN 1 ELSE 0 END) AS has_actual_shipment,
                    MAX(CASE WHEN COALESCE(fo.planned_shipment_date, '') <> '' THEN 1 ELSE 0 END) AS has_planned_shipment
                FROM ids
                LEFT JOIN fact_orders_kaspi fo ON CAST(fo.order_id AS TEXT) = ids.order_id
                LEFT JOIN fact_order_entries_kaspi fe ON CAST(fe.order_id AS TEXT) = ids.order_id
                LEFT JOIN sales_fact_v2 sf ON CAST(sf.order_id AS TEXT) = ids.order_id
                LEFT JOIN fact_sales fs ON CAST(fs.order_id AS TEXT) = ids.order_id
                GROUP BY ids.order_id
            """
            frames.append(pd.read_sql_query(query, conn, params=chunk))
    finally:
        conn.close()
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["order_id"])
    if df.empty:
        return df
    df["order_id"] = df["order_id"].map(_normalize_order_id)
    for col in df.columns:
        if col != "order_id":
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


def _classify_missing_row(row: pd.Series) -> tuple[str, str]:
    if int(row.get("in_sales_fact_v2", 0)) > 0:
        return (
            "DB_ALREADY_IN_SALES_FACT_V2",
            "order already exists in sales_fact_v2; validator/input drift needs review",
        )
    if int(row.get("in_fact_entries", 0)) > 0:
        if int(row.get("in_fact_sales", 0)) > 0:
            return (
                "DB_BACKFILL_FROM_FACT_ORDER_ENTRIES",
                "entries exist and legacy fact_sales exists, but sales_fact_v2/view_sales_line_truth is missing the order",
            )
        return (
            "DB_BACKFILL_FROM_FACT_ORDER_ENTRIES",
            "fact_order_entries_kaspi exists and sales_fact_v2 rebuild can backfill the order",
        )
    if int(row.get("in_fact_orders", 0)) > 0:
        return (
            "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
            "fact_orders_kaspi exists but fact_order_entries_kaspi is missing, so a safe sales rebuild cannot materialize the order",
        )
    return (
        "DB_QUARANTINE_NO_FACT_ORDER_HEADER",
        "order is absent from fact_orders_kaspi and cannot be safely backfilled from current DB state",
    )


def classify_webui_db_absence(
    *,
    db_path: Path,
    missing_orders_csv: Path,
    db_only_orders_csv: Path,
    output_dir: Path,
    strict: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not missing_orders_csv.exists():
        raise FileNotFoundError(f"missing orders csv not found: {missing_orders_csv}")
    if not db_only_orders_csv.exists():
        raise FileNotFoundError(f"db-only orders csv not found: {db_only_orders_csv}")

    missing = pd.read_csv(missing_orders_csv, dtype=object, keep_default_na=False)
    missing["order_id"] = missing["order_id"].map(_normalize_order_id)
    db_only = pd.read_csv(db_only_orders_csv, dtype=object, keep_default_na=False)
    db_only["order_id"] = db_only["order_id"].map(_normalize_order_id)

    presence = _load_presence(
        db_path=db_path,
        order_ids=sorted(missing["order_id"].dropna().astype(str).unique().tolist()),
    )
    classified_missing = missing.merge(presence, on="order_id", how="left")
    for col in (
        "in_fact_orders",
        "in_fact_entries",
        "in_sales_fact_v2",
        "in_fact_sales",
        "has_courier_transmission",
        "has_actual_shipment",
        "has_planned_shipment",
    ):
        classified_missing[col] = pd.to_numeric(classified_missing[col], errors="coerce").fillna(0).astype(int)

    root_buckets: list[str] = []
    details: list[str] = []
    for _, row in classified_missing.iterrows():
        root_bucket, detail = _classify_missing_row(row)
        root_buckets.append(root_bucket)
        details.append(detail)
    classified_missing["root_bucket"] = root_buckets
    classified_missing["resolution_detail"] = details

    db_only = db_only.copy()
    db_only["resolution_status"] = db_only["root_bucket"].map(
        lambda bucket: "NON_BLOCKING_EXPLANATION"
        if str(bucket) == "DB_ONLY_RETURNED_IN_WEBUI"
        else "QUARANTINE_REQUIRED"
    )

    root_summary_rows: list[dict[str, Any]] = []
    missing_counts = (
        classified_missing.groupby("root_bucket", as_index=False)
        .agg(delta_reference_count=("order_id", "nunique"))
        .sort_values(["root_bucket"])
    )
    for row in missing_counts.to_dict("records"):
        root_summary_rows.append(
            {
                "surface_classifier": "MISSING_IN_DB",
                "root_bucket": row["root_bucket"],
                "delta_reference_count": int(row["delta_reference_count"]),
            }
        )
    db_only_counts = (
        db_only.groupby("root_bucket", as_index=False)
        .agg(delta_reference_count=("order_id", "nunique"))
        .sort_values(["root_bucket"])
    )
    for row in db_only_counts.to_dict("records"):
        root_summary_rows.append(
            {
                "surface_classifier": "IN_DB_ONLY",
                "root_bucket": row["root_bucket"],
                "delta_reference_count": int(row["delta_reference_count"]),
            }
        )
    root_causes = pd.DataFrame(root_summary_rows).sort_values(
        ["surface_classifier", "root_bucket"]
    )

    backfill_candidates = classified_missing[
        classified_missing["root_bucket"].isin(
            {
                "DB_BACKFILL_FROM_FACT_ORDER_ENTRIES",
            }
        )
    ].copy()
    quarantine_candidates = pd.concat(
        [
            classified_missing[
                classified_missing["root_bucket"].isin(
                    {
                        "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES",
                        "DB_QUARANTINE_NO_FACT_ORDER_HEADER",
                        "DB_ALREADY_IN_SALES_FACT_V2",
                    }
                )
            ][
                [
                    "order_id",
                    "store_code",
                    "webui_sale_date",
                    "root_bucket",
                    "resolution_detail",
                ]
            ],
            db_only[db_only["resolution_status"] == "QUARANTINE_REQUIRED"][
                ["order_id", "store_code", "db_sale_date_min", "root_bucket", "resolution_detail"]
            ].rename(columns={"db_sale_date_min": "webui_sale_date"}),
        ],
        ignore_index=True,
    )

    root_causes_csv = output_dir / "db_absence_root_causes.csv"
    backfill_csv = output_dir / "db_backfill_candidates.csv"
    quarantine_csv = output_dir / "db_quarantine_candidates.csv"
    root_causes.to_csv(root_causes_csv, index=False, encoding="utf-8")
    backfill_candidates.to_csv(backfill_csv, index=False, encoding="utf-8")
    quarantine_candidates.to_csv(quarantine_csv, index=False, encoding="utf-8")

    unresolved = int(root_causes["delta_reference_count"].sum()) - (
        int(classified_missing["order_id"].nunique()) + int(db_only["order_id"].nunique())
    )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS" if unresolved == 0 else "FAIL",
        "ok": unresolved == 0,
        "missing_in_db_orders": int(classified_missing["order_id"].nunique()),
        "db_only_orders": int(db_only["order_id"].nunique()),
        "backfill_candidate_orders": int(backfill_candidates["order_id"].nunique()),
        "quarantine_candidate_orders": int(quarantine_candidates["order_id"].nunique()),
        "unresolved_order_count": int(unresolved),
        "outputs": {
            "db_absence_root_causes_csv": str(root_causes_csv),
            "db_backfill_candidates_csv": str(backfill_csv),
            "db_quarantine_candidates_csv": str(quarantine_csv),
        },
    }
    if strict and not report["ok"]:
        raise WebuiDBAbsenceError(f"db absence classification unresolved_order_count={unresolved}")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify WebUI-vs-DB absence set")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--missing-orders-csv", type=Path, default=DEFAULT_MISSING_ORDERS_CSV)
    parser.add_argument("--db-only-orders-csv", type=Path, default=DEFAULT_DB_ONLY_ORDERS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = classify_webui_db_absence(
            db_path=args.db_path,
            missing_orders_csv=args.missing_orders_csv,
            db_only_orders_csv=args.db_only_orders_csv,
            output_dir=args.output_dir,
            strict=bool(args.strict),
        )
    except WebuiDBAbsenceError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_DB_ABSENCE_CLASSIFICATION_FAIL")
        print(f"message={exc}")
        return 1
    print(f"db_absence_root_causes_csv={report['outputs']['db_absence_root_causes_csv']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
