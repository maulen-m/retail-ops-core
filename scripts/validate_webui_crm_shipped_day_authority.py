#!/usr/bin/env python3
"""Decide whether a deterministic WebUI->CRM shipped-day rule is authority-backed."""

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

DEFAULT_GAP_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "webui_promotion_delta_recon"
    / "2026-03-07"
    / "webui_vs_crm_gap_classifier_reprojected.csv"
)
DEFAULT_PROMOTION_DELTA_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "webui_promotion_delta_recon"
    / "2026-03-07"
    / "promotion_delta_orders.csv"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_shipped_authority_recon" / "2026-03-07"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_SHIPPED_VALIDATION_ROOT = (
    PROJECT_ROOT / "exports" / "validation" / "shipped_vs_waybill_crm"
)


class WebuiCRMShippedAuthorityError(RuntimeError):
    """Raised when shipped-day authority cannot be decided fail-closed."""


def _normalize_order_id(value: Any) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") else text


def _normalize_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def _plus_days(value: pd.Series, days: int) -> pd.Series:
    parsed = pd.to_datetime(value.replace({"": pd.NA}), errors="coerce")
    shifted = parsed + pd.to_timedelta(days, unit="D")
    return shifted.dt.date.astype("string").fillna("")


def _load_authority_inputs(*, gap_csv: Path, promotion_delta_csv: Path) -> pd.DataFrame:
    if not gap_csv.exists():
        raise FileNotFoundError(f"gap csv not found: {gap_csv}")
    if not promotion_delta_csv.exists():
        raise FileNotFoundError(f"promotion delta csv not found: {promotion_delta_csv}")

    gap = pd.read_csv(gap_csv, dtype=object, keep_default_na=False)
    gap = gap[gap["classifier"].astype(str) == "DATE_MISMATCH"].copy()
    if gap.empty:
        raise WebuiCRMShippedAuthorityError("webui_vs_crm gap classifier contains 0 DATE_MISMATCH rows")
    gap["order_id"] = gap["order_id"].map(_normalize_order_id)
    gap = gap.drop_duplicates(subset=["order_id"], keep="first")

    delta = pd.read_csv(promotion_delta_csv, dtype=object, keep_default_na=False)
    delta = delta[
        (delta["surface"].astype(str) == "CRM")
        & (delta["surface_classifier"].astype(str) == "DATE_MISMATCH")
    ].copy()
    if delta.empty:
        raise WebuiCRMShippedAuthorityError("promotion_delta_orders contains 0 CRM DATE_MISMATCH rows")

    delta["order_id"] = delta["order_id"].map(_normalize_order_id)
    delta = delta.drop_duplicates(subset=["order_id"], keep="first")

    merged = gap.merge(
        delta[
            [
                "order_id",
                "store_code",
                "created_at",
                "planned_courier_at",
                "delivered_at",
                "crm_sale_date",
                "webui_sale_date",
                "root_bucket",
            ]
        ],
        on="order_id",
        how="left",
        suffixes=("", "_delta"),
    )
    merged["store_code"] = merged["store_code"].where(
        merged["store_code"].astype(str).str.strip() != "",
        merged["store_code_webui"],
    )
    merged["root_bucket"] = merged["root_bucket"].fillna("").where(
        merged["root_bucket"].fillna("").astype(str).str.strip() != "",
        "UNMAPPED_REPROJECTED_ONLY",
    )
    for col in (
        "sale_date_webui",
        "sale_date_crm",
        "created_at",
        "planned_courier_at",
        "delivered_at",
        "crm_sale_date",
        "webui_sale_date",
    ):
        if col in merged.columns:
            merged[col] = merged[col].map(_normalize_date)
    return merged


def _load_latest_fact_orders(db_path: Path, order_ids: list[str]) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")
    if not order_ids:
        return pd.DataFrame(
            columns=[
                "order_id",
                "store_code_db",
                "db_created_at",
                "planned_shipment_date",
                "actual_shipment_date",
                "courier_transmission_date",
                "internal_status",
                "kaspi_status",
                "waybill_number",
                "waybill_url",
            ]
        )

    conn = sqlite3.connect(str(db_path))
    try:
        frames: list[pd.DataFrame] = []
        for offset in range(0, len(order_ids), 900):
            chunk = order_ids[offset : offset + 900]
            placeholders = ",".join(["?"] * len(chunk))
            query = f"""
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    UPPER(COALESCE(store_code, '')) AS store_code_db,
                    created_at AS db_created_at,
                    planned_shipment_date,
                    actual_shipment_date,
                    courier_transmission_date,
                    internal_status,
                    kaspi_status,
                    waybill_number,
                    waybill_url,
                    updated_at,
                    imported_at,
                    id
                FROM fact_orders_kaspi
                WHERE CAST(order_id AS TEXT) IN ({placeholders})
                ORDER BY
                    CAST(order_id AS TEXT) ASC,
                    datetime(COALESCE(updated_at, imported_at, '1970-01-01')) DESC,
                    id DESC
            """
            frames.append(pd.read_sql_query(query, conn, params=chunk))
    finally:
        conn.close()
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return df
    df["order_id"] = df["order_id"].map(_normalize_order_id)
    df = df.drop_duplicates(subset=["order_id"], keep="first").copy()
    for col in ("db_created_at", "planned_shipment_date", "actual_shipment_date", "courier_transmission_date"):
        df[col] = df[col].map(_normalize_date)
    return df[
        [
            "order_id",
            "store_code_db",
            "db_created_at",
            "planned_shipment_date",
            "actual_shipment_date",
            "courier_transmission_date",
            "internal_status",
            "kaspi_status",
            "waybill_number",
            "waybill_url",
        ]
    ]


def _load_shipped_validation_summary(shipped_validation_root: Path) -> dict[str, Any] | None:
    if not shipped_validation_root.exists():
        return None
    candidates = sorted(
        path for path in shipped_validation_root.rglob("summary.json") if path.is_file()
    )
    if not candidates:
        return None
    payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    payload["summary_path"] = str(candidates[-1])
    return payload


def build_shipped_day_rule_candidates(enriched: pd.DataFrame) -> pd.DataFrame:
    sample = enriched.copy()
    sample["crm_sale_date"] = sample["sale_date_crm"]
    sample["webui_planned_plus_1"] = _plus_days(sample["planned_courier_at"], 1)
    sample["webui_created_plus_1"] = _plus_days(sample["created_at"], 1)
    sample["webui_delivered_minus_1"] = _plus_days(sample["delivered_at"], -1)

    candidate_specs = [
        ("WEBUI_PLANNED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM", "webui_planned_plus_1", "planned_shipment_date"),
        ("WEBUI_CREATED_PLUS_ONE__API_PLANNED_SHIPMENT_EQ_CRM", "webui_created_plus_1", "planned_shipment_date"),
        ("WEBUI_PLANNED__API_PLANNED_SHIPMENT_EQ_CRM", "planned_courier_at", "planned_shipment_date"),
        ("WEBUI_CREATED__API_PLANNED_SHIPMENT_EQ_CRM", "created_at", "planned_shipment_date"),
        ("WEBUI_DELIVERED_MINUS_ONE__API_ACTUAL_SHIPMENT_EQ_CRM", "webui_delivered_minus_1", "actual_shipment_date"),
    ]
    rows: list[dict[str, Any]] = []
    total_orders = int(sample["order_id"].nunique())
    for rule_code, webui_col, authority_col in candidate_specs:
        webui_match = sample[webui_col].astype(str) == sample["crm_sale_date"].astype(str)
        authority_match = sample[authority_col].astype(str) == sample["crm_sale_date"].astype(str)
        combined_match = webui_match & authority_match
        matched_orders = int(sample.loc[combined_match, "order_id"].nunique())
        authority_supported = int(sample.loc[authority_match, "order_id"].nunique())
        mismatched_orders = total_orders - matched_orders
        rows.append(
            {
                "rule_code": rule_code,
                "webui_rule_field": webui_col,
                "authority_field": authority_col,
                "total_orders": total_orders,
                "matched_orders": matched_orders,
                "mismatched_orders": mismatched_orders,
                "authority_supported_orders": authority_supported,
                "coverage_ratio": round(matched_orders / float(max(1, total_orders)), 6),
                "authority_support_ratio": round(authority_supported / float(max(1, total_orders)), 6),
                "is_deterministic": bool(matched_orders == total_orders and authority_supported == total_orders),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["is_deterministic", "matched_orders", "authority_supported_orders", "rule_code"],
        ascending=[False, False, False, True],
    )


def decide_shipped_day_authority(
    enriched: pd.DataFrame,
    candidates: pd.DataFrame,
) -> dict[str, Any]:
    total_orders = int(enriched["order_id"].nunique())
    deterministic = candidates[candidates["is_deterministic"] == True].copy()  # noqa: E712
    if not deterministic.empty:
        winner = deterministic.iloc[0]
        return {
            "decision": "RULE_PROVEN",
            "rule_code": str(winner["rule_code"]),
            "matched_orders": int(winner["matched_orders"]),
            "total_orders": total_orders,
            "reason": "single WebUI transformation is fully supported by API shipment authority for all mismatch orders",
        }
    return {
        "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY",
        "rule_code": "",
        "matched_orders": int(candidates["matched_orders"].max()) if not candidates.empty else 0,
        "total_orders": total_orders,
        "reason": "no single WebUI transformation is authority-backed across the full mismatch population",
    }


def _render_report(
    *,
    decision: dict[str, Any],
    candidates: pd.DataFrame,
    sample: pd.DataFrame,
    shipped_summary: dict[str, Any] | None,
) -> str:
    lines = [
        "# Shipped-Day Authority Report",
        "",
        f"- decision: `{decision['decision']}`",
        f"- rule_code: `{decision['rule_code']}`",
        f"- total_mismatch_orders: `{decision['total_orders']}`",
        f"- matched_orders_top_rule: `{decision['matched_orders']}`",
        f"- reason: {decision['reason']}",
        "",
        "## Candidate Rules",
        "",
        "| rule_code | matched_orders | total_orders | authority_supported_orders | coverage_ratio | deterministic |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in candidates.to_dict("records"):
        lines.append(
            f"| `{row['rule_code']}` | {row['matched_orders']} | {row['total_orders']} | "
            f"{row['authority_supported_orders']} | {row['coverage_ratio']:.6f} | "
            f"{'true' if row['is_deterministic'] else 'false'} |"
        )

    root_counts = sample["root_bucket"].astype(str).value_counts()
    lines.extend(["", "## Root Buckets", ""])
    for bucket, count in root_counts.items():
        lines.append(f"- `{bucket}`: `{int(count)}`")

    if shipped_summary:
        lines.extend(
            [
                "",
                "## Existing Shipped/Waybill Authority Snapshot",
                "",
                f"- summary_path: `{shipped_summary.get('summary_path')}`",
                f"- target_date: `{shipped_summary.get('target_date')}`",
                f"- crm_day_orders: `{shipped_summary.get('crm_day_orders')}`",
                f"- crm_day_with_api_shipped: `{shipped_summary.get('crm_day_with_api_shipped')}`",
                f"- crm_day_with_waybill_pdf: `{shipped_summary.get('crm_day_with_waybill_pdf')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def validate_webui_crm_shipped_day_authority(
    *,
    start: str,
    end: str,
    db_path: Path,
    gap_csv: Path,
    promotion_delta_csv: Path,
    output_dir: Path,
    shipped_validation_root: Path,
    strict: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sample = _load_authority_inputs(gap_csv=gap_csv, promotion_delta_csv=promotion_delta_csv)
    sample = sample[
        (sample["sale_date_crm"].astype(str) >= str(start))
        & (sample["sale_date_crm"].astype(str) <= str(end))
    ].copy()
    if sample.empty:
        raise WebuiCRMShippedAuthorityError("no DATE_MISMATCH rows remain inside requested window")

    db_authority = _load_latest_fact_orders(
        db_path=db_path,
        order_ids=sorted(sample["order_id"].dropna().astype(str).unique().tolist()),
    )
    enriched = sample.merge(db_authority, on="order_id", how="left")
    enriched["crm_equals_api_planned_shipment"] = (
        enriched["sale_date_crm"].astype(str) == enriched["planned_shipment_date"].astype(str)
    )
    enriched["crm_equals_api_actual_shipment"] = (
        enriched["sale_date_crm"].astype(str) == enriched["actual_shipment_date"].astype(str)
    )
    enriched["crm_equals_api_courier_transmission"] = (
        enriched["sale_date_crm"].astype(str) == enriched["courier_transmission_date"].astype(str)
    )
    enriched["crm_equals_webui_planned_plus_1"] = (
        _plus_days(enriched["planned_courier_at"], 1) == enriched["sale_date_crm"].astype(str)
    )
    enriched["crm_equals_webui_created_plus_1"] = (
        _plus_days(enriched["created_at"], 1) == enriched["sale_date_crm"].astype(str)
    )

    candidates = build_shipped_day_rule_candidates(enriched)
    decision = decide_shipped_day_authority(enriched, candidates)
    shipped_summary = _load_shipped_validation_summary(shipped_validation_root)

    sample_csv = output_dir / "shipped_day_authority_sample.csv"
    candidates_csv = output_dir / "shipped_day_rule_candidates.csv"
    report_md = output_dir / "shipped_day_authority_report.md"
    decision_json = output_dir / "shipped_day_authority_decision.json"
    enriched.sort_values(["sale_date_crm", "store_code", "order_id"]).to_csv(
        sample_csv,
        index=False,
        encoding="utf-8",
    )
    candidates.to_csv(candidates_csv, index=False, encoding="utf-8")

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS",
        "ok": True,
        "period": {"start": start, "end": end},
        "decision": decision["decision"],
        "rule_code": decision["rule_code"],
        "matched_orders": decision["matched_orders"],
        "total_orders": decision["total_orders"],
        "reason": decision["reason"],
        "crm_matches_api_planned_shipment_orders": int(
            enriched.loc[enriched["crm_equals_api_planned_shipment"], "order_id"].nunique()
        ),
        "crm_matches_api_actual_shipment_orders": int(
            enriched.loc[enriched["crm_equals_api_actual_shipment"], "order_id"].nunique()
        ),
        "crm_matches_api_courier_transmission_orders": int(
            enriched.loc[enriched["crm_equals_api_courier_transmission"], "order_id"].nunique()
        ),
        "crm_matches_webui_planned_plus_1_orders": int(
            enriched.loc[enriched["crm_equals_webui_planned_plus_1"], "order_id"].nunique()
        ),
        "crm_matches_webui_created_plus_1_orders": int(
            enriched.loc[enriched["crm_equals_webui_created_plus_1"], "order_id"].nunique()
        ),
        "shipped_validation_summary": shipped_summary,
        "outputs": {
            "shipped_day_authority_sample_csv": str(sample_csv),
            "shipped_day_rule_candidates_csv": str(candidates_csv),
            "shipped_day_authority_report_md": str(report_md),
            "shipped_day_authority_decision_json": str(decision_json),
        },
    }
    decision_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        _render_report(
            decision=decision,
            candidates=candidates,
            sample=enriched,
            shipped_summary=shipped_summary,
        ),
        encoding="utf-8",
    )
    if strict and payload["decision"] not in {"RULE_PROVEN", "CRM_REMAINS_CHRONOLOGY_AUTHORITY"}:
        raise WebuiCRMShippedAuthorityError("authority decision is ambiguous")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decide WebUI->CRM shipped-day authority")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--gap-csv", type=Path, default=DEFAULT_GAP_CSV)
    parser.add_argument("--promotion-delta-csv", type=Path, default=DEFAULT_PROMOTION_DELTA_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--shipped-validation-root", type=Path, default=DEFAULT_SHIPPED_VALIDATION_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_webui_crm_shipped_day_authority(
            start=str(args.start),
            end=str(args.end),
            db_path=args.db_path,
            gap_csv=args.gap_csv,
            promotion_delta_csv=args.promotion_delta_csv,
            output_dir=args.output_dir,
            shipped_validation_root=args.shipped_validation_root,
            strict=bool(args.strict),
        )
    except WebuiCRMShippedAuthorityError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_CRM_SHIPPED_AUTHORITY_FAIL")
        print(f"message={exc}")
        return 1

    print(f"shipped_day_authority_decision_json={report['outputs']['shipped_day_authority_decision_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
