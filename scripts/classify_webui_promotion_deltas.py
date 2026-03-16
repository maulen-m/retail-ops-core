#!/usr/bin/env python3
"""Classify current WebUI promotion deltas into deterministic root-cause buckets."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import build_webui_truth_projection, load_pack_rows, load_status_ledger

DEFAULT_LEDGER_ROOT = PROJECT_ROOT / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
DEFAULT_PACK_ROOT = (
    PROJECT_ROOT
    / "exports"
    / "webui_archive_full_parse_runs"
    / "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211"
    / "pack_outputs"
    / "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "exports" / "validation" / "webui_promotion_delta_recon" / "2026-03-07"
DEFAULT_CRM_GAP_CSV = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06" / "webui_vs_crm_gap_classifier_full_parse.csv"
)
DEFAULT_DB_COMPARE_CSV = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06" / "webui_vs_db_order_compare_full_parse.csv"
)


class PromotionDeltaClassificationError(RuntimeError):
    """Raised when promotion delta classification is incomplete or inconsistent."""


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _to_date(value: Any) -> pd.Timestamp | None:
    text = _to_text(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def _last_nonblank(series: pd.Series) -> str:
    values = [_to_text(value) for value in series.tolist() if _to_text(value)]
    return values[-1] if values else ""


def _date_in_window(value: Any, *, start: str, end: str) -> bool:
    text = _to_text(value)
    return bool(text) and str(start) <= text <= str(end)


def _add_days(value: Any, days: int) -> str:
    parsed = _to_date(value)
    if parsed is None:
        return ""
    return (parsed + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def classify_delta_reference(row: Mapping[str, Any], *, start: str = "2026-01-01", end: str = "2026-02-29") -> dict[str, str]:
    surface = _to_text(row.get("surface")).upper()
    classifier = _to_text(row.get("surface_classifier")).upper()
    planned_courier_at = _to_text(row.get("planned_courier_at"))
    created_at = _to_text(row.get("created_at"))
    delivered_at = _to_text(row.get("delivered_at"))
    returned_at = _to_text(row.get("returned_at"))
    crm_sale_date = _to_text(row.get("crm_sale_date"))
    webui_sale_date = _to_text(row.get("webui_sale_date"))
    db_sale_date_min = _to_text(row.get("db_sale_date_min"))
    status_set = _to_text(row.get("status_set"))
    order_found = str(row.get("order_found", "")).strip().lower() not in {"", "0", "false", "none", "nan"}
    missing_in_db_flag = str(row.get("missing_in_db_flag", "")).strip().lower() in {"1", "true", "yes"}

    root_bucket = "UNRESOLVED_MANUAL_REVIEW"
    detail = "no deterministic bucket matched"

    if surface == "CRM" and classifier == "DATE_MISMATCH":
        if planned_courier_at and planned_courier_at == crm_sale_date:
            root_bucket = "CRM_EVENT_BASIS_PLANNED_COURIER_MATCH"
            detail = "crm sale_date matches planned_courier_at"
        elif created_at and created_at == crm_sale_date:
            root_bucket = "CRM_EVENT_BASIS_CREATED_AT_MATCH"
            detail = "crm sale_date matches created_at fallback"
        elif created_at and _add_days(created_at, 1) == crm_sale_date:
            root_bucket = "CRM_EVENT_BASIS_CREATED_PLUS_ONE_MATCH"
            detail = "crm sale_date is created_at + 1 day"
        elif planned_courier_at and _add_days(planned_courier_at, 1) == crm_sale_date:
            root_bucket = "CRM_EVENT_BASIS_PLANNED_PLUS_ONE_MATCH"
            detail = "crm sale_date is planned_courier_at + 1 day"
        elif delivered_at:
            root_bucket = "CRM_EVENT_BASIS_OTHER_DELIVERY_LAG"
            detail = "crm mismatch remains a lifecycle-date divergence against delivered lineage"
    elif surface == "CRM" and classifier == "IN_CRM_ONLY":
        if missing_in_db_flag and "DELIVERED" in status_set:
            root_bucket = "CRM_ONLY_DB_ABSENT_DELIVERED"
            detail = "webui delivered order is absent from DB-backed projection"
        elif returned_at and not delivered_at:
            root_bucket = "CRM_ONLY_RETURNED_IN_WEBUI"
            detail = "crm order maps to returned-only webui lineage"
        elif "CANCELLED" in status_set:
            root_bucket = "CRM_ONLY_CANCELLED_IN_WEBUI"
            detail = "crm order maps to cancelled webui lineage"
        elif _date_in_window(planned_courier_at, start=start, end=end) and not _date_in_window(delivered_at, start=start, end=end):
            root_bucket = "CRM_ONLY_SHIPPED_IN_WINDOW_DELIVERED_LATER"
            detail = "planned_courier_at is in-window but delivered_at lands after the window"
        elif delivered_at and delivered_at > end:
            root_bucket = "CRM_ONLY_DELIVERED_AFTER_WINDOW_MISSING_EVENT_DATE"
            detail = "delivered after window and no promotable shipped event date is available"
        elif not order_found:
            root_bucket = "CRM_ONLY_NO_WEBUI_LINEAGE"
            detail = "crm order id was not found in the frozen webui lineage"
        else:
            root_bucket = "CRM_ONLY_OTHER"
            detail = "crm-only order requires downstream reconciliation but is not unresolved"
    elif surface == "CRM" and classifier == "IN_WEBUI_ONLY":
        if db_sale_date_min and db_sale_date_min < start and webui_sale_date >= start:
            root_bucket = "CRM_WEBUI_ONLY_PREWINDOW_DB_DRIFT"
            detail = "order exists in DB before the window but is counted in-webui inside the window"
        elif planned_courier_at and planned_courier_at < start and webui_sale_date >= start:
            root_bucket = "CRM_WEBUI_ONLY_PREWINDOW_SHIPPED"
            detail = "planned_courier_at falls before the comparison window"
        else:
            root_bucket = "CRM_WEBUI_ONLY_OTHER"
            detail = "webui-only order requires CRM-side follow-up but is not unresolved"
    elif surface == "DB" and classifier == "MISSING_IN_DB":
        if "DELIVERED" in status_set or delivered_at:
            root_bucket = "DB_MISSING_IN_DB_ABSENT"
            detail = "webui delivered order has no DB lineage at any sale_date"
        else:
            root_bucket = "DB_MISSING_IN_DB_OTHER"
            detail = "db absence does not have delivered lineage context"
    elif surface == "DB" and classifier == "IN_WEBUI_ONLY":
        if db_sale_date_min and db_sale_date_min < start and webui_sale_date >= start:
            root_bucket = "DB_WINDOW_DRIFT_PREWINDOW"
            detail = "db sale_date exists before the active window"
        else:
            root_bucket = "DB_IN_WEBUI_ONLY_OTHER"
            detail = "db compare sees a webui-only order outside the standard prewindow drift pattern"
    elif surface == "DB" and classifier == "IN_DB_ONLY":
        if "RETURNED" in status_set or returned_at:
            root_bucket = "DB_ONLY_RETURNED_IN_WEBUI"
            detail = "db-only order is present in returned-only webui lineage"
        elif not order_found:
            root_bucket = "DB_ONLY_NO_WEBUI_LINEAGE"
            detail = "db-only order id is absent from the frozen webui pack"
        else:
            root_bucket = "DB_IN_DB_ONLY_OTHER"
            detail = "db-only order has webui lineage but is not returned-only"

    return {
        "root_bucket": root_bucket,
        "resolution_detail": detail,
        "resolved": "false" if root_bucket == "UNRESOLVED_MANUAL_REVIEW" else "true",
    }


def summarize_classification_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["surface", "surface_classifier", "root_bucket", "delta_reference_count"])
    return (
        rows.groupby(["surface", "surface_classifier", "root_bucket"], as_index=False)
        .size()
        .rename(columns={"size": "delta_reference_count"})
        .sort_values(["surface", "surface_classifier", "root_bucket"])
        .reset_index(drop=True)
    )


def _load_db_sale_dates(db_path: Path, order_ids: list[str]) -> pd.DataFrame:
    if not order_ids:
        return pd.DataFrame(columns=["order_id", "db_sale_date_min", "db_sale_date_max", "db_store_codes"])
    conn = sqlite3.connect(str(db_path))
    try:
        frames: list[pd.DataFrame] = []
        for offset in range(0, len(order_ids), 900):
            chunk = order_ids[offset : offset + 900]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"""
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    date(sale_date) AS sale_date,
                    UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code
                FROM view_sales_line_truth
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
            """
            frames.append(pd.read_sql_query(query, conn, params=chunk))
    finally:
        conn.close()
    if not frames:
        return pd.DataFrame(columns=["order_id", "db_sale_date_min", "db_sale_date_max", "db_store_codes"])
    rows = pd.concat(frames, ignore_index=True)
    return (
        rows.groupby("order_id", as_index=False)
        .agg(
            db_sale_date_min=("sale_date", "min"),
            db_sale_date_max=("sale_date", "max"),
            db_store_codes=("store_code", lambda s: "|".join(sorted(set(str(v) for v in s if str(v).strip())))),
        )
    )


def _build_order_features(ledger_root: Path, pack_root: Path) -> pd.DataFrame:
    ledger, _ = load_status_ledger(ledger_root)
    pack = load_pack_rows(pack_root)
    pack_features = (
        pack.groupby(["store_code", "order_id"], as_index=False)
        .agg(
            planned_courier_at=("planned_courier_at", _last_nonblank),
            created_at_pack=("created_at", "min"),
            status_set=("status_internal", lambda s: "|".join(sorted(set(_to_text(v) for v in s if _to_text(v))))),
        )
    )
    order_features = (
        ledger[["store_code", "order_id", "created_at", "delivered_at", "returned_at"]]
        .drop_duplicates()
        .merge(pack_features, on=["store_code", "order_id"], how="outer")
    )
    order_features["created_at"] = order_features["created_at"].where(
        order_features["created_at"].astype(str).str.strip() != "",
        order_features["created_at_pack"],
    )
    order_features["order_found"] = order_features["store_code"].notna()
    return order_features.drop(columns=["created_at_pack"])


def classify_webui_promotion_deltas(
    *,
    start: str,
    end: str,
    ledger_root: Path,
    pack_root: Path,
    db_path: Path,
    crm_gap_csv: Path,
    db_compare_csv: Path,
    output_dir: Path,
    strict: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    order_features = _build_order_features(ledger_root, pack_root)
    projection, projection_meta = build_webui_truth_projection(
        db_path=db_path.resolve(),
        ledger_run_root=ledger_root.resolve(),
        start=start,
        end=end,
    )
    missing_projection = projection.reindex(
        columns=["store_code", "order_id", "sale_date", "webui_delivered_at", "db_match_status"],
        fill_value="",
    )
    missing_rows = (
        missing_projection.loc[missing_projection["db_match_status"] == "MISSING_IN_DB", ["store_code", "order_id", "sale_date", "webui_delivered_at"]]
        .drop_duplicates()
        .rename(columns={"sale_date": "webui_sale_date", "webui_delivered_at": "delivered_at"})
    )
    missing_rows["surface"] = "DB"
    missing_rows["surface_classifier"] = "MISSING_IN_DB"
    missing_rows["missing_in_db_flag"] = True
    missing_rows["crm_sale_date"] = ""

    crm_gap = pd.read_csv(crm_gap_csv, dtype=object, keep_default_na=False)
    crm_gap = crm_gap[crm_gap["classifier"].astype(str) != "BOTH"].copy()
    crm_gap["surface"] = "CRM"
    crm_gap["surface_classifier"] = crm_gap["classifier"]
    crm_gap["webui_sale_date"] = crm_gap["sale_date_webui"]
    crm_gap["crm_sale_date"] = crm_gap["sale_date_crm"]
    crm_gap["missing_in_db_flag"] = crm_gap["order_id"].astype(str).isin(set(missing_rows["order_id"].astype(str)))

    db_compare = pd.read_csv(db_compare_csv, dtype=object, keep_default_na=False)
    db_compare = db_compare[db_compare["classifier"].astype(str) != "BOTH"].copy()
    db_compare["surface"] = "DB"
    db_compare["surface_classifier"] = db_compare["classifier"]
    db_compare["webui_sale_date"] = db_compare["sale_date_webui"]
    db_compare["crm_sale_date"] = ""
    db_compare["missing_in_db_flag"] = False

    combined = pd.concat(
        [
            crm_gap[["surface", "surface_classifier", "order_id", "webui_sale_date", "crm_sale_date", "missing_in_db_flag"]],
            db_compare[["surface", "surface_classifier", "order_id", "webui_sale_date", "crm_sale_date", "missing_in_db_flag"]],
            missing_rows[["surface", "surface_classifier", "order_id", "webui_sale_date", "crm_sale_date", "missing_in_db_flag"]],
        ],
        ignore_index=True,
    )
    db_dates = _load_db_sale_dates(db_path, sorted(combined["order_id"].dropna().astype(str).unique().tolist()))
    rows = combined.merge(order_features, on="order_id", how="left").merge(db_dates, on="order_id", how="left")
    for col in ["planned_courier_at", "created_at", "delivered_at", "returned_at", "status_set", "db_sale_date_min", "db_sale_date_max"]:
        if col in rows.columns:
            rows[col] = rows[col].fillna("")
    rows["order_found"] = rows["order_found"].fillna(False)

    classified = rows.copy()
    bucket_rows = [classify_delta_reference(record, start=start, end=end) for record in classified.to_dict("records")]
    bucket_df = pd.DataFrame(bucket_rows)
    classified = pd.concat([classified.reset_index(drop=True), bucket_df.reset_index(drop=True)], axis=1)
    classified = classified.sort_values(["surface", "surface_classifier", "order_id"]).reset_index(drop=True)

    buckets = summarize_classification_rows(classified)
    unresolved = classified[classified["resolved"] != "true"].copy()

    orders_csv = output_dir / "promotion_delta_orders.csv"
    buckets_csv = output_dir / "promotion_delta_buckets.csv"
    unresolved_csv = output_dir / "promotion_delta_unresolved.csv"
    root_causes_md = output_dir / "promotion_root_causes.md"
    classified.to_csv(orders_csv, index=False, encoding="utf-8")
    buckets.to_csv(buckets_csv, index=False, encoding="utf-8")
    unresolved.to_csv(unresolved_csv, index=False, encoding="utf-8")

    expected_counts = {
        ("CRM", "DATE_MISMATCH"): int((crm_gap["surface_classifier"] == "DATE_MISMATCH").sum()),
        ("CRM", "IN_CRM_ONLY"): int((crm_gap["surface_classifier"] == "IN_CRM_ONLY").sum()),
        ("CRM", "IN_WEBUI_ONLY"): int((crm_gap["surface_classifier"] == "IN_WEBUI_ONLY").sum()),
        ("DB", "MISSING_IN_DB"): int(len(missing_rows)),
        ("DB", "IN_WEBUI_ONLY"): int((db_compare["surface_classifier"] == "IN_WEBUI_ONLY").sum()),
        ("DB", "IN_DB_ONLY"): int((db_compare["surface_classifier"] == "IN_DB_ONLY").sum()),
    }
    observed_counts = {
        tuple(key): int(value)
        for key, value in (
            classified.groupby(["surface", "surface_classifier"]).size().rename("count").to_dict().items()
        )
    }
    actual_counts = {key: int(observed_counts.get(key, 0)) for key in expected_counts}
    unresolved_ratio = float(len(unresolved) / max(1, len(classified)))

    root_causes_md.write_text(
        "\n".join(
            [
                "# Promotion Root Causes",
                "",
                f"- generated_at: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
                f"- start: `{start}`",
                f"- end: `{end}`",
                f"- delta_reference_count: `{len(classified)}`",
                f"- unresolved_references: `{len(unresolved)}`",
                f"- unresolved_ratio: `{unresolved_ratio:.4f}`",
                f"- projection_missing_in_db_orders: `{projection_meta.get('missing_in_db_orders', 0)}`",
                "",
                "## Bucket Totals",
                "",
            ]
            + [
                f"- `{row.surface} / {row.surface_classifier} / {row.root_bucket}`: `{int(row.delta_reference_count)}`"
                for row in buckets.itertuples(index=False)
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS" if unresolved_ratio <= 0.05 and expected_counts == actual_counts else "FAIL",
        "strict": bool(strict),
        "period": {"start": start, "end": end},
        "delta_reference_count": int(len(classified)),
        "unresolved_reference_count": int(len(unresolved)),
        "unresolved_ratio": unresolved_ratio,
        "expected_counts": {f"{k[0]}::{k[1]}": v for k, v in expected_counts.items()},
        "actual_counts": {f"{k[0]}::{k[1]}": v for k, v in actual_counts.items()},
        "outputs": {
            "promotion_delta_orders_csv": str(orders_csv),
            "promotion_delta_buckets_csv": str(buckets_csv),
            "promotion_delta_unresolved_csv": str(unresolved_csv),
            "promotion_root_causes_md": str(root_causes_md),
        },
    }
    if strict and expected_counts != actual_counts:
        raise PromotionDeltaClassificationError(
            f"bucket totals do not reconcile: expected={expected_counts} actual={actual_counts}"
        )
    if strict and unresolved_ratio > 0.05:
        raise PromotionDeltaClassificationError(
            f"unresolved ratio {unresolved_ratio:.4f} exceeds max 0.05"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify WebUI promotion deltas into root-cause buckets")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--ledger-root", type=Path, default=DEFAULT_LEDGER_ROOT)
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    parser.add_argument("--db-path", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--crm-gap-csv", type=Path, default=DEFAULT_CRM_GAP_CSV)
    parser.add_argument("--db-compare-csv", type=Path, default=DEFAULT_DB_COMPARE_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = classify_webui_promotion_deltas(
            start=str(args.start),
            end=str(args.end),
            ledger_root=args.ledger_root,
            pack_root=args.pack_root,
            db_path=args.db_path,
            crm_gap_csv=args.crm_gap_csv,
            db_compare_csv=args.db_compare_csv,
            output_dir=args.output_dir,
            strict=bool(args.strict),
        )
    except PromotionDeltaClassificationError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_PROMOTION_DELTA_CLASSIFICATION_FAIL")
        print(f"message={exc}")
        return 1

    print(f"promotion_delta_orders_csv={report['outputs']['promotion_delta_orders_csv']}")
    print(f"promotion_delta_buckets_csv={report['outputs']['promotion_delta_buckets_csv']}")
    print(f"promotion_delta_unresolved_csv={report['outputs']['promotion_delta_unresolved_csv']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
