#!/usr/bin/env python3
"""Build owner review surface with fail-closed publication locks."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
import sys

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)
from scripts.webui_chronology_contract_utils import load_webui_chronology_gates


class NorthStarOwnerReviewError(RuntimeError):
    """Raised when strict mode is requested and publication is not ready."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build North Star owner review surface.")
    parser.add_argument("--as-of", default="2026-03-06")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--stores-config", default="config/kaspi_stores.yaml")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument(
        "--validation-dir",
        default=None,
    )
    parser.add_argument(
        "--owner-pnl-json",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        default=None,
    )
    return parser


def _load_gate_status(validation_dir: Path, file_name: str, fallback_status: str = "FAIL") -> dict[str, object]:
    path = validation_dir / file_name
    if not path.exists():
        return {"status": fallback_status, "reason": f"missing:{file_name}", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"status": payload.get("status", fallback_status), "path": str(path), "payload": payload}


def _resolve_validation_dir(validation_dir: Path | None, *, truth_source: str, as_of: str) -> Path:
    if validation_dir is not None:
        return validation_dir
    if truth_source == "webui_archive":
        return PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of
    return PROJECT_ROOT / "exports" / "validation" / "crm_north_star_restate" / as_of


def _resolve_owner_pnl_json(owner_pnl_json: Path | None, *, as_of: str) -> Path:
    if owner_pnl_json is not None:
        return owner_pnl_json
    return PROJECT_ROOT / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json"


def _resolve_output_dir(output_dir: Path | None, *, as_of: str) -> Path:
    if output_dir is not None:
        return output_dir
    return PROJECT_ROOT / "exports" / "north_star_owner_review" / as_of


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


def _load_publication_gates(validation_dir: Path, truth_source: str) -> dict[str, dict[str, object]]:
    if truth_source == "webui_archive":
        chronology_gates, _chronology_ok, _chronology_meta = load_webui_chronology_gates(validation_dir)
        return {
            **chronology_gates,
            "webui_db_projection": _load_gate_status(validation_dir, "webui_vs_db_report.json"),
            "cogs_completeness": _load_gate_status(validation_dir, "cogs_completeness_report.json"),
            "cogs_realism": _load_gate_status(validation_dir, "cogs_realism_report.json"),
            "ads_offer_universe": _load_gate_status(validation_dir, "ads_offer_universe_report.json"),
            "ads_spend_reality": _load_gate_status(validation_dir, "ads_spend_reality_report.json"),
            "order_status_audit": _load_gate_status(validation_dir, "order_status_audit_report.json"),
        }
    return {
        "crm_ceiling": _load_gate_status(validation_dir, "sales_truth_vs_crm_report.json"),
        "cogs_completeness": _load_gate_status(validation_dir, "cogs_completeness_report.json"),
        "cogs_realism": _load_gate_status(validation_dir, "cogs_realism_report.json"),
        "ads_offer_universe": _load_gate_status(validation_dir, "ads_offer_universe_report.json"),
        "ads_spend_reality": _load_gate_status(validation_dir, "ads_spend_reality_report.json"),
    }


def _load_truth_lines(
    *,
    db_path: Path,
    truth_source: str,
    ledger_root: Path | None,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    if truth_source == "webui_archive":
        resolved_ledger_root = _resolve_ledger_root(ledger_root)
        projection, projection_meta = build_webui_truth_projection(
            db_path=db_path.resolve(),
            ledger_run_root=resolved_ledger_root,
            start=start,
            end=end,
        )
        if projection.empty:
            lines = pd.DataFrame(
                columns=[
                    "sale_date",
                    "sale_month",
                    "store_code",
                    "order_id",
                    "sku_key",
                    "units",
                    "net_rev_kzt",
                    "cogs_kzt",
                ]
            )
        else:
            match_status = (
                projection["db_match_status"]
                if "db_match_status" in projection.columns
                else pd.Series(["MATCHED"] * len(projection), index=projection.index)
            )
            lines = projection[match_status == "MATCHED"].copy()
            lines["sale_month"] = lines["sale_date"].astype(str).str.slice(0, 7)
            lines["store_code"] = lines["store_code"].fillna("UNIVERSAL").astype(str).str.upper()
            lines["sku_key"] = lines["sku_key"].fillna("__UNMAPPED__").astype(str)
            lines["units"] = pd.to_numeric(lines["units"], errors="coerce").fillna(0.0)
            lines["net_rev_kzt"] = pd.to_numeric(lines["net_rev_kzt"], errors="coerce").fillna(0.0)
            lines["cogs_kzt"] = pd.to_numeric(lines["cogs_kzt"], errors="coerce").fillna(0.0)
            lines = lines[
                [
                    "sale_date",
                    "sale_month",
                    "store_code",
                    "order_id",
                    "sku_key",
                    "units",
                    "net_rev_kzt",
                    "cogs_kzt",
                ]
            ].copy()
        return lines, projection_meta

    conn = sqlite3.connect(str(db_path))
    try:
        lines = pd.read_sql_query(
            """
            SELECT
                date(sale_date) AS sale_date,
                substr(sale_date, 1, 7) AS sale_month,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                CAST(order_id AS TEXT) AS order_id,
                COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                COALESCE(units, 0) AS units,
                COALESCE(net_rev_kzt, 0) AS net_rev_kzt,
                COALESCE(cogs_kzt, 0) AS cogs_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN date(?) AND date(?)
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()
    return lines, None


def _merchant_to_store_map(stores_config: Path) -> dict[str, str]:
    payload = yaml.safe_load(stores_config.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores", {})
    out: dict[str, str] = {}
    for store_code, meta in stores.items():
        merchant_uid = str(meta.get("merchant_uid", "")).strip()
        if merchant_uid:
            out[merchant_uid] = store_code
    return out


def build_north_star_owner_review(
    *,
    as_of: str,
    start: str,
    end: str,
    strict: bool,
    db_path: Path,
    stores_config: Path,
    truth_source: str,
    ledger_root: Path | None,
    validation_dir: Path | None,
    owner_pnl_json: Path | None,
    output_dir: Path | None,
) -> dict[str, object]:
    validation_dir = _resolve_validation_dir(validation_dir, truth_source=truth_source, as_of=as_of)
    owner_pnl_json = _resolve_owner_pnl_json(owner_pnl_json, as_of=as_of)
    output_dir = _resolve_output_dir(output_dir, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)

    gates = _load_publication_gates(validation_dir, truth_source)
    publication_ready = all(str(item.get("status")).upper() == "PASS" for item in gates.values())

    owner_flags: dict[tuple[str, str], dict[str, object]] = {}
    owner_flags_month: dict[str, dict[str, object]] = {}
    if owner_pnl_json.exists():
        payload = json.loads(owner_pnl_json.read_text(encoding="utf-8"))
        owner_flags = {
            (row.get("sale_month"), row.get("store_code")): row
            for row in payload.get("monthly_by_store", [])
        }
        owner_flags_month = {
            row.get("sale_month"): row for row in payload.get("monthly_totals", [])
        }

    lines, projection_meta = _load_truth_lines(
        db_path=db_path,
        truth_source=truth_source,
        ledger_root=ledger_root,
        start=start,
        end=end,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        opex = pd.read_sql_query(
            """
            SELECT substr(commit_date,1,7) AS sale_month, SUM(amount_kzt) AS opex_kzt
            FROM fact_cashflow_commitments
            WHERE commit_type='OPEX' AND date(commit_date) BETWEEN date(?) AND date(?)
            GROUP BY 1
            """,
            conn,
            params=[start, end],
        )
        ads_raw = pd.read_sql_query(
            """
            SELECT
                substr(date,1,7) AS sale_month,
                CAST(store_code AS TEXT) AS store_code_raw,
                COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                SUM(COALESCE(ads_cost_kzt,0)) AS ads_kzt
            FROM ads_spend_sidecar_daily_sku
            WHERE date(date) BETWEEN date(?) AND date(?)
            GROUP BY 1,2,3
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()

    merchant_map = _merchant_to_store_map(stores_config)
    ads_raw["store_code"] = ads_raw["store_code_raw"].map(
        lambda v: merchant_map.get(str(v), str(v).upper())
    )
    ads = ads_raw.groupby(["sale_month", "store_code", "sku_key"], as_index=False)["ads_kzt"].sum()

    sales_sku = lines.groupby(["sale_month", "store_code", "sku_key"], as_index=False).agg(
        orders=("order_id", "nunique"),
        units=("units", "sum"),
        net_rev_kzt=("net_rev_kzt", "sum"),
        cogs_kzt=("cogs_kzt", "sum"),
    )
    sku = sales_sku.merge(ads, on=["sale_month", "store_code", "sku_key"], how="left")
    sku["ads_kzt"] = sku["ads_kzt"].fillna(0.0)
    sku["profit_after_ads_kzt_raw"] = sku["net_rev_kzt"] - sku["cogs_kzt"] - sku["ads_kzt"]

    # Decision-grade flags from owner pnl if available.
    sku["decision_grade"] = sku.apply(
        lambda row: bool(owner_flags.get((row["sale_month"], row["store_code"]), {}).get("decision_grade", False)),
        axis=1,
    )
    sku["decision_grade"] = sku["decision_grade"].fillna(False).astype(bool)
    sku["statusdate_coverage_pct"] = sku.apply(
        lambda row: owner_flags.get((row["sale_month"], row["store_code"]), {}).get("statusdate_coverage_pct", 0.0),
        axis=1,
    )
    sku["profit_locked"] = (~sku["decision_grade"]) | bool(not publication_ready)
    sku["profit_after_ads_kzt"] = sku["profit_after_ads_kzt_raw"].where(~sku["profit_locked"])

    # Build true daily-by-store surface and allocate month+store ads over daily sales.
    daily_sales = lines.groupby(["sale_date", "sale_month", "store_code"], as_index=False).agg(
        orders=("order_id", "nunique"),
        units=("units", "sum"),
        net_rev_kzt=("net_rev_kzt", "sum"),
        cogs_kzt=("cogs_kzt", "sum"),
    )
    ads_month_store = ads_raw.groupby(["sale_month", "store_code"], as_index=False).agg(
        ads_kzt=("ads_kzt", "sum")
    )
    daily = daily_sales.merge(ads_month_store, on=["sale_month", "store_code"], how="left")
    daily["ads_kzt"] = daily["ads_kzt"].fillna(0.0)
    daily["ads_alloc_method"] = "none"
    daily["ads_kzt_alloc"] = 0.0
    for (sale_month, store_code), group in daily.groupby(["sale_month", "store_code"]):
        total_ads = float(group["ads_kzt"].iloc[0])
        if total_ads <= 0:
            continue
        net_sum = float(group["net_rev_kzt"].sum())
        if net_sum > 0:
            weights = group["net_rev_kzt"] / net_sum
            method = "month_store_pro_rata_net_rev"
        else:
            units_sum = float(group["units"].sum())
            if units_sum > 0:
                weights = group["units"] / units_sum
                method = "month_store_pro_rata_units"
            else:
                weights = pd.Series([1.0 / len(group)] * len(group), index=group.index)
                method = "month_store_equal_split"
        alloc = (weights * total_ads).round(2)
        diff = round(total_ads - float(alloc.sum()), 2)
        if abs(diff) > 0:
            alloc.iloc[-1] = round(float(alloc.iloc[-1]) + diff, 2)
        daily.loc[group.index, "ads_kzt_alloc"] = alloc
        daily.loc[group.index, "ads_alloc_method"] = method

    daily["decision_grade"] = daily.apply(
        lambda row: bool(owner_flags.get((row["sale_month"], row["store_code"]), {}).get("decision_grade", False)),
        axis=1,
    )
    daily["decision_grade"] = daily["decision_grade"].fillna(False).astype(bool)
    daily["statusdate_coverage_pct"] = daily.apply(
        lambda row: owner_flags.get((row["sale_month"], row["store_code"]), {}).get("statusdate_coverage_pct", 0.0),
        axis=1,
    )
    daily["profit_after_ads_kzt_raw"] = daily["net_rev_kzt"] - daily["cogs_kzt"] - daily["ads_kzt_alloc"]
    daily["profit_locked"] = (~daily["decision_grade"]) | bool(not publication_ready)
    daily["profit_after_ads_kzt"] = daily["profit_after_ads_kzt_raw"].where(~daily["profit_locked"])
    daily["provisional"] = ~daily["decision_grade"].fillna(False)

    monthly = daily.groupby("sale_month", as_index=False).agg(
        orders=("orders", "sum"),
        units=("units", "sum"),
        net_rev_kzt=("net_rev_kzt", "sum"),
        cogs_kzt=("cogs_kzt", "sum"),
        ads_kzt=("ads_kzt_alloc", "sum"),
        profit_after_ads_kzt=("profit_after_ads_kzt", "sum"),
        decision_grade=("decision_grade", "max"),
        statusdate_coverage_pct=("statusdate_coverage_pct", "max"),
        profit_locked=("profit_locked", "max"),
    )
    monthly = monthly.merge(opex, on="sale_month", how="left")
    monthly["opex_kzt"] = monthly["opex_kzt"].fillna(0.0)
    monthly["profit_after_ads_and_opex_kzt"] = (
        monthly["profit_after_ads_kzt"] - monthly["opex_kzt"]
    )
    monthly["decision_grade"] = monthly.apply(
        lambda row: bool(owner_flags_month.get(row["sale_month"], {}).get("decision_grade", row["decision_grade"])),
        axis=1,
    )
    monthly["decision_grade"] = monthly["decision_grade"].fillna(False).astype(bool)
    monthly["statusdate_coverage_pct"] = monthly.apply(
        lambda row: owner_flags_month.get(row["sale_month"], {}).get("statusdate_coverage_pct", row["statusdate_coverage_pct"]),
        axis=1,
    )
    monthly.loc[monthly["profit_locked"], ["profit_after_ads_kzt", "profit_after_ads_and_opex_kzt"]] = pd.NA
    monthly["provisional"] = ~monthly["decision_grade"].fillna(False)

    sku_table = sku[
        [
            "sale_month",
            "store_code",
            "sku_key",
            "orders",
            "units",
            "net_rev_kzt",
            "cogs_kzt",
            "ads_kzt",
            "profit_after_ads_kzt",
            "decision_grade",
            "statusdate_coverage_pct",
            "profit_locked",
        ]
    ].copy()
    sku_agg = sku_table.groupby("sku_key", as_index=False).agg(
        orders=("orders", "sum"),
        units=("units", "sum"),
        net_rev_kzt=("net_rev_kzt", "sum"),
        cogs_kzt=("cogs_kzt", "sum"),
        ads_allocation_kzt=("ads_kzt", "sum"),
        profit_after_ads_kzt=("profit_after_ads_kzt", "sum"),
    )
    top_gainers = sku_agg.sort_values("profit_after_ads_kzt", ascending=False).head(30)
    top_losers = sku_agg.sort_values("profit_after_ads_kzt", ascending=True).head(30)

    # Locked flags
    locked_monthly = monthly[
        ["sale_month", "decision_grade", "statusdate_coverage_pct", "profit_locked", "provisional"]
    ].copy()
    locked_store = daily[
        ["sale_month", "store_code", "decision_grade", "statusdate_coverage_pct", "profit_locked", "provisional"]
    ].copy()

    # Persist
    monthly_csv = output_dir / "monthly_totals_review.csv"
    daily_csv = output_dir / "daily_profit_by_day_store.csv"
    sku_csv = output_dir / "sku_profit_table.csv"
    gain_csv = output_dir / "top_gainers_by_sku.csv"
    lose_csv = output_dir / "top_losers_by_sku.csv"
    lock_month_csv = output_dir / "locked_flags_monthly.csv"
    lock_store_csv = output_dir / "locked_flags_monthly_by_store.csv"
    ready_json = output_dir / "publication_readiness.json"
    out_json = output_dir / "NORTH_STAR_OWNER_REVIEW.json"
    out_md = output_dir / "NORTH_STAR_OWNER_REVIEW.md"

    monthly.to_csv(monthly_csv, index=False)
    daily[
        [
            "sale_date",
            "store_code",
            "orders",
            "units",
            "net_rev_kzt",
            "cogs_kzt",
            "ads_kzt_alloc",
            "profit_after_ads_kzt",
            "decision_grade",
            "statusdate_coverage_pct",
            "profit_locked",
            "provisional",
            "ads_alloc_method",
        ]
    ].rename(columns={"ads_kzt_alloc": "ads_kzt"}).to_csv(daily_csv, index=False)
    sku_agg.to_csv(sku_csv, index=False)
    top_gainers.to_csv(gain_csv, index=False)
    top_losers.to_csv(lose_csv, index=False)
    locked_monthly.to_csv(lock_month_csv, index=False)
    locked_store.to_csv(lock_store_csv, index=False)

    readiness = {
        "status": "PASS" if publication_ready else "FAIL",
        "truth_source": truth_source,
        "gates": gates,
        "profit_locked": not publication_ready,
    }
    ready_json.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    payload: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": as_of,
        "period": {"start": start, "end": end},
        "truth_source": truth_source,
        "truth_projection": projection_meta,
        "status": "PASS" if publication_ready else "FAIL",
        "profit_locked": not publication_ready,
        "publication_readiness_json": str(ready_json.resolve()),
        "monthly_totals_review_csv": str(monthly_csv.resolve()),
        "daily_profit_by_day_store_csv": str(daily_csv.resolve()),
        "sku_profit_table_csv": str(sku_csv.resolve()),
        "top_gainers_by_sku_csv": str(gain_csv.resolve()),
        "top_losers_by_sku_csv": str(lose_csv.resolve()),
        "locked_flags_monthly_csv": str(lock_month_csv.resolve()),
        "locked_flags_monthly_by_store_csv": str(lock_store_csv.resolve()),
        "north_star_owner_review_json": str(out_json.resolve()),
        "north_star_owner_review_md": str(out_md.resolve()),
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md.write_text(
        "\n".join(
            [
                "# North Star Owner Review",
                "",
                f"- as_of: `{as_of}`",
                f"- period: `{start}`..`{end}`",
                f"- truth_source: `{truth_source}`",
                f"- status: `{payload['status']}`",
                f"- profit_locked: `{payload['profit_locked']}`",
                "",
                "## Gate Status",
                *[f"- {gate_name}: `{gate_payload['status']}`" for gate_name, gate_payload in gates.items()],
            ]
        ),
        encoding="utf-8",
    )

    if strict and not publication_ready:
        raise NorthStarOwnerReviewError("Owner review publication blocked: one or more gates are RED")
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = build_north_star_owner_review(
            as_of=args.as_of,
            start=args.start,
            end=args.end,
            strict=args.strict,
            db_path=Path(args.db_path),
            stores_config=Path(args.stores_config),
            truth_source=str(args.truth_source),
            ledger_root=args.ledger_root,
            validation_dir=Path(args.validation_dir) if args.validation_dir is not None else None,
            owner_pnl_json=Path(args.owner_pnl_json) if args.owner_pnl_json is not None else None,
            output_dir=Path(args.output_dir) if args.output_dir is not None else None,
        )
    except NorthStarOwnerReviewError as exc:
        print(str(exc))
        return 1
    print(f"NORTH_STAR_OWNER_REVIEW_json={payload['north_star_owner_review_json']}")
    print(f"NORTH_STAR_OWNER_REVIEW_md={payload['north_star_owner_review_md']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
