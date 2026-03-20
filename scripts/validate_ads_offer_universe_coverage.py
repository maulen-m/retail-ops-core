#!/usr/bin/env python3
"""Validate sold-offer coverage against ads mapped universe."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ads.active_scope import DEFAULT_ADS_ACTIVE_SCOPE_CONFIG, is_store_active_on
from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)
from scripts.webui_db_gate_utils import resolve_effective_missing_in_db_orders


class AdsOfferCoverageError(RuntimeError):
    """Raised when strict ads offer-universe coverage fails."""


DEFAULT_ADS_SOURCE_GAP_QUARANTINE_CONFIG = PROJECT_ROOT / "config" / "ads_source_gap_quarantine.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ads offer-universe coverage.")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--min-coverage", type=float, default=1.0)
    parser.add_argument("--max-ads-to-net-rev-ratio", type=float, default=0.8)
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-03-06")
    parser.add_argument("--stores-config", default="config/kaspi_stores.yaml")
    parser.add_argument("--ads-scope-config", type=Path, default=DEFAULT_ADS_ACTIVE_SCOPE_CONFIG)
    parser.add_argument("--gap-quarantine-config", type=Path, default=DEFAULT_ADS_SOURCE_GAP_QUARANTINE_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _merchant_to_store_map(stores_config: Path) -> dict[str, str]:
    payload = yaml.safe_load(stores_config.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores", {})
    out: dict[str, str] = {}
    for store_code, meta in stores.items():
        merchant_uid = str(meta.get("merchant_uid", "")).strip()
        if merchant_uid:
            out[merchant_uid] = store_code
    return out


def _resolve_output_dir(output_dir: Path | None, *, truth_source: str, as_of: str) -> Path:
    if output_dir is not None:
        return output_dir
    if truth_source == "webui_archive":
        return PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of
    return PROJECT_ROOT / "exports" / "validation" / "crm_north_star_rebuild" / "2026-03-05"


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


def _load_sold_truth(
    *,
    db_path: Path,
    truth_source: str,
    ledger_root: Path | None,
    start: str,
    end: str,
    output_dir: Path,
    truth_output_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object] | None, list[str]]:
    if truth_source == "webui_archive":
        resolved_ledger_root = _resolve_ledger_root(ledger_root)
        rows, projection_meta = build_webui_truth_projection(
            db_path=db_path.resolve(),
            ledger_run_root=resolved_ledger_root,
            start=start,
            end=end,
        )
        match_status = (
            rows["db_match_status"]
            if "db_match_status" in rows.columns
            else pd.Series(["MATCHED"] * len(rows), index=rows.index)
        )
        rows = rows[match_status == "MATCHED"].copy()
        rows["sale_date"] = rows["sale_date"].astype(str)
        rows["sale_month"] = rows["sale_date"].astype(str).str.slice(0, 7)
        rows["store_code"] = rows["store_code"].astype(str).str.upper()
        rows["sku_key"] = rows["sku_key"].fillna("").astype(str).replace({"": "__UNMAPPED__"})
        truth_errors: list[str] = []
        if int((projection_meta or {}).get("projected_rows", 0)) == 0:
            truth_errors.append("webui truth projection contains 0 rows")
        effective_missing_in_db_orders, _ = resolve_effective_missing_in_db_orders(
            output_dir=truth_output_dir,
            ledger_root=resolved_ledger_root,
            start=start,
            end=end,
            projection_meta=projection_meta,
        )
        if effective_missing_in_db_orders > 0:
            truth_errors.append(
                f"webui truth projection has missing_in_db_orders={effective_missing_in_db_orders}"
            )
        return rows[["order_id", "sale_date", "sale_month", "store_code", "sku_key", "net_rev_kzt"]], projection_meta, truth_errors

    conn = sqlite3.connect(str(db_path))
    try:
        sold = pd.read_sql_query(
            """
            SELECT
                order_id,
                date(sale_date) AS sale_date,
                substr(sale_date, 1, 7) AS sale_month,
                UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                COALESCE(net_rev_kzt, 0) AS net_rev_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN date(?) AND date(?)
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()
    return sold, None, []


def _load_gap_quarantine_rules(config_path: Path | None) -> pd.DataFrame:
    if config_path is None:
        return pd.DataFrame(columns=["order_id", "sale_date", "store_code", "sku_key", "reason"])
    candidate = Path(config_path).expanduser()
    if not candidate.exists():
        return pd.DataFrame(columns=["order_id", "sale_date", "store_code", "sku_key", "reason"])
    payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    rows = payload.get("quarantines") or []
    if not rows:
        return pd.DataFrame(columns=["order_id", "sale_date", "store_code", "sku_key", "reason"])
    rules = pd.DataFrame(rows).copy()
    for column in ["order_id", "sale_date", "store_code", "sku_key"]:
        if column not in rules.columns:
            rules[column] = ""
        rules[column] = rules[column].fillna("").astype(str)
    rules["store_code"] = rules["store_code"].str.upper()
    if "reason" not in rules.columns:
        rules["reason"] = "unspecified"
    rules["reason"] = rules["reason"].fillna("unspecified").astype(str)
    return rules[["order_id", "sale_date", "store_code", "sku_key", "reason"]].drop_duplicates()


def _apply_gap_quarantine(
    sold: pd.DataFrame,
    *,
    config_path: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if sold.empty:
        return sold.copy(), sold.iloc[0:0].copy()
    rules = _load_gap_quarantine_rules(config_path)
    if rules.empty:
        return sold.copy(), sold.iloc[0:0].copy()
    merged = sold.merge(
        rules,
        on=["order_id", "sale_date", "store_code", "sku_key"],
        how="left",
    )
    quarantined = merged[merged["reason"].notna()].copy()
    filtered = merged[merged["reason"].isna()].copy()
    return filtered[sold.columns].copy(), quarantined.copy()


def validate_ads_offer_universe_coverage(
    *,
    start: str,
    end: str,
    strict: bool,
    min_coverage: float,
    max_ads_to_net_rev_ratio: float,
    db_path: Path,
    truth_source: str = "db",
    ledger_root: Path | None = None,
    as_of: str = "2026-03-06",
    stores_config: Path,
    ads_scope_config: Path = DEFAULT_ADS_ACTIVE_SCOPE_CONFIG,
    gap_quarantine_config: Path | None = DEFAULT_ADS_SOURCE_GAP_QUARANTINE_CONFIG,
    output_dir: Path | None = None,
    truth_output_dir: Path | None = None,
) -> dict[str, object]:
    output_dir = _resolve_output_dir(output_dir, truth_source=truth_source, as_of=as_of)
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_truth_output_dir = (
        truth_output_dir.resolve() if truth_output_dir is not None else output_dir.resolve()
    )

    sold, projection_meta, truth_errors = _load_sold_truth(
        db_path=db_path,
        truth_source=truth_source,
        ledger_root=ledger_root,
        start=start,
        end=end,
        output_dir=output_dir,
        truth_output_dir=resolved_truth_output_dir,
    )
    sold["ads_scope_active"] = (
        sold.apply(
            lambda row: is_store_active_on(
                str(row["store_code"]),
                str(row["sale_date"]),
                config_path=ads_scope_config,
            ),
            axis=1,
        )
        if not sold.empty
        else pd.Series(dtype=bool, index=sold.index)
    )
    sold = sold[sold["ads_scope_active"]].copy()
    sold, quarantined = _apply_gap_quarantine(sold, config_path=gap_quarantine_config)
    sold = (
        sold.groupby(["sale_month", "store_code", "sku_key"], as_index=False)
        .agg(
            sold_lines=("order_id", "size"),
            net_rev_kzt=("net_rev_kzt", "sum"),
        )
        .sort_values(["sale_month", "store_code", "sku_key"])
    )

    conn = sqlite3.connect(str(db_path))
    try:
        ads_raw = pd.read_sql_query(
            """
            SELECT
                date(date) AS ads_date,
                substr(date, 1, 7) AS sale_month,
                CAST(store_code AS TEXT) AS store_code_raw,
                COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                CAST(COALESCE(mapped, 0) AS INTEGER) AS mapped,
                SUM(COALESCE(ads_cost_kzt, 0)) AS ads_kzt
            FROM ads_spend_sidecar_daily_sku
            WHERE date(date) BETWEEN date(?) AND date(?)
            GROUP BY 1,2,3,4,5
            """,
            conn,
            params=[start, end],
        )
    finally:
        conn.close()

    merchant_map = _merchant_to_store_map(stores_config)
    ads_raw["store_code"] = ads_raw["store_code_raw"].map(
        lambda value: merchant_map.get(str(value), str(value).upper())
    )
    ads_raw["ads_scope_active"] = (
        ads_raw.apply(
            lambda row: is_store_active_on(
                str(row["store_code"]),
                str(row["ads_date"]),
                config_path=ads_scope_config,
            ),
            axis=1,
        )
        if not ads_raw.empty
        else pd.Series(dtype=bool, index=ads_raw.index)
    )
    ads_raw = ads_raw[ads_raw["ads_scope_active"]].copy()
    ads_presence = (
        ads_raw.groupby(["sale_month", "store_code"], as_index=False)
        .agg(ads_rows=("sku_key", "size"), ads_total_kzt=("ads_kzt", "sum"))
        .assign(ads_tracking_enabled=lambda d: d["ads_rows"] > 0)
    )
    ads = ads_raw.groupby(["sale_month", "store_code", "sku_key"], as_index=False).agg(
        mapped=("mapped", "max"),
        ads_kzt=("ads_kzt", "sum"),
    )
    ads = ads[ads["mapped"] == 1].copy()

    merged = sold.merge(
        ads[["sale_month", "store_code", "sku_key"]],
        on=["sale_month", "store_code", "sku_key"],
        how="left",
        indicator=True,
    )
    merged["is_covered"] = merged["_merge"] == "both"
    merged = merged.drop(columns=["_merge"])

    by_month_store = (
        merged.groupby(["sale_month", "store_code"], as_index=False)
        .agg(
            sold_skus=("sku_key", "nunique"),
            covered_skus=("is_covered", "sum"),
        )
        .assign(ads_scope_expected=True)
        .sort_values(["sale_month", "store_code"])
    )
    by_month_store = by_month_store.merge(
        ads_presence[["sale_month", "store_code", "ads_tracking_enabled"]],
        on=["sale_month", "store_code"],
        how="left",
    )
    by_month_store["ads_tracking_enabled"] = (
        by_month_store["ads_scope_expected"]
        | by_month_store["ads_tracking_enabled"].map(
            lambda value: bool(value) if pd.notna(value) else False
        )
    )
    by_month_store["coverage_pct"] = (
        by_month_store["covered_skus"] / by_month_store["sold_skus"].replace({0: 1})
    ).round(6)
    by_month_store["coverage_ok"] = (
        ~by_month_store["ads_tracking_enabled"]
        | (by_month_store["coverage_pct"] >= float(min_coverage))
    )

    missing = merged[~merged["is_covered"]].copy().sort_values(["sale_month", "store_code", "sku_key"])

    sold_month_store = sold.groupby(["sale_month", "store_code"], as_index=False).agg(
        sold_lines=("sold_lines", "sum"),
        sold_skus=("sku_key", "nunique"),
        net_rev_kzt=("net_rev_kzt", "sum"),
    )
    ads_month_store = ads_raw.groupby(["sale_month", "store_code"], as_index=False).agg(
        ads_kzt=("ads_kzt", "sum")
    )
    spend_reality = sold_month_store.merge(
        ads_month_store, on=["sale_month", "store_code"], how="left"
    )
    spend_reality = spend_reality.merge(
        ads_presence[["sale_month", "store_code", "ads_tracking_enabled"]],
        on=["sale_month", "store_code"],
        how="left",
    )
    expected_pairs = by_month_store[["sale_month", "store_code", "ads_scope_expected"]].copy()
    spend_reality = spend_reality.merge(
        expected_pairs,
        on=["sale_month", "store_code"],
        how="left",
    )
    spend_reality["ads_tracking_enabled"] = (
        spend_reality["ads_scope_expected"].fillna(False).astype(bool)
        | spend_reality["ads_tracking_enabled"].map(
            lambda value: bool(value) if pd.notna(value) else False
        )
    )
    spend_reality["ads_kzt"] = pd.to_numeric(spend_reality["ads_kzt"], errors="coerce").fillna(0.0)
    spend_reality["ads_to_net_rev_ratio"] = (
        spend_reality["ads_kzt"] / spend_reality["net_rev_kzt"].replace({0: pd.NA})
    ).fillna(0.0)
    spend_reality["missing_ads_spend"] = (
        spend_reality["ads_tracking_enabled"]
        & (spend_reality["sold_lines"] > 0)
        & (spend_reality["ads_kzt"] <= 0)
    )
    spend_reality["ratio_out_of_band"] = (
        spend_reality["ads_tracking_enabled"]
        & (spend_reality["ads_to_net_rev_ratio"] > float(max_ads_to_net_rev_ratio))
    )
    spend_reality["spend_reality_ok"] = (
        ~spend_reality["missing_ads_spend"] & ~spend_reality["ratio_out_of_band"]
    )
    spend_reality = spend_reality.sort_values(["sale_month", "store_code"])

    coverage_csv = output_dir / "ads_offer_universe_coverage.csv"
    missing_csv = output_dir / "ads_missing_sold_offers.csv"
    quarantined_csv = output_dir / "ads_quarantined_sold_offers.csv"
    month_store_csv = output_dir / "ads_coverage_by_month_store.csv"
    spend_reality_csv = output_dir / "ads_spend_reality_by_month_store.csv"
    report_md = output_dir / "ads_offer_universe_report.md"
    report_json = output_dir / "ads_offer_universe_report.json"

    merged.to_csv(coverage_csv, index=False, encoding="utf-8")
    missing.to_csv(missing_csv, index=False, encoding="utf-8")
    quarantined.to_csv(quarantined_csv, index=False, encoding="utf-8")
    by_month_store.to_csv(month_store_csv, index=False, encoding="utf-8")
    spend_reality.to_csv(spend_reality_csv, index=False, encoding="utf-8")

    failing_pairs = int((~by_month_store["coverage_ok"]).sum())
    spend_reality_fail_pairs = int((~spend_reality["spend_reality_ok"]).sum())
    status = (
        "PASS"
        if failing_pairs == 0 and spend_reality_fail_pairs == 0 and not truth_errors
        else "FAIL"
    )
    payload: dict[str, object] = {
        "status": status,
        "strict": strict,
        "truth_source": truth_source,
        "as_of": as_of,
        "ads_scope_config": str(Path(ads_scope_config).expanduser().resolve()),
        "gap_quarantine_config": (
            str(Path(gap_quarantine_config).expanduser().resolve())
            if gap_quarantine_config is not None and Path(gap_quarantine_config).expanduser().exists()
            else None
        ),
        "period": {"start": start, "end": end},
        "min_coverage": min_coverage,
        "max_ads_to_net_rev_ratio": float(max_ads_to_net_rev_ratio),
        "failing_month_store_pairs": failing_pairs,
        "spend_reality_fail_pairs": spend_reality_fail_pairs,
        "missing_sold_offers": len(missing),
        "quarantined_sold_offers": len(quarantined),
        "truth_errors": truth_errors,
        "truth_projection": projection_meta,
        "outputs": {
            "ads_offer_universe_coverage_csv": str(coverage_csv.resolve()),
            "ads_missing_sold_offers_csv": str(missing_csv.resolve()),
            "ads_quarantined_sold_offers_csv": str(quarantined_csv.resolve()),
            "ads_coverage_by_month_store_csv": str(month_store_csv.resolve()),
            "ads_spend_reality_by_month_store_csv": str(spend_reality_csv.resolve()),
            "ads_offer_universe_report_md": str(report_md.resolve()),
            "ads_offer_universe_report_json": str(report_json.resolve()),
        },
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# Ads Offer-Universe Coverage",
                "",
                f"- period: `{start}`..`{end}`",
                f"- status: `{status}`",
                f"- truth_source: `{truth_source}`",
                f"- min_coverage: `{min_coverage}`",
                f"- failing_month_store_pairs: `{failing_pairs}`",
                f"- spend_reality_fail_pairs: `{spend_reality_fail_pairs}`",
                f"- missing_sold_offers: `{len(missing)}`",
                f"- quarantined_sold_offers: `{len(quarantined)}`",
                f"- truth_errors: `{len(truth_errors)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and status != "PASS":
        raise AdsOfferCoverageError(
            (
                "Ads offer-universe/spend-reality failed: "
                f"failing_month_store_pairs={failing_pairs}, "
                f"spend_reality_fail_pairs={spend_reality_fail_pairs}, "
                f"truth_errors={len(truth_errors)}"
            )
        )
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = validate_ads_offer_universe_coverage(
            start=args.start,
            end=args.end,
            strict=args.strict,
            min_coverage=args.min_coverage,
            max_ads_to_net_rev_ratio=float(args.max_ads_to_net_rev_ratio),
            db_path=Path(args.db_path),
            truth_source=str(args.truth_source),
            ledger_root=args.ledger_root,
            as_of=str(args.as_of),
            stores_config=Path(args.stores_config),
            ads_scope_config=Path(args.ads_scope_config),
            gap_quarantine_config=Path(args.gap_quarantine_config) if args.gap_quarantine_config else None,
            output_dir=args.output_dir,
        )
    except AdsOfferCoverageError as exc:
        print(str(exc))
        return 1

    print(f"ads_offer_universe_report_json={payload['outputs']['ads_offer_universe_report_json']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
