#!/usr/bin/env python3
"""Build the G-ADS-02 daily campaign CRR disposition report.

The report is read-only. It evaluates OD-019 against watcher campaign metrics,
then joins AB canonical campaign->SKU rows and sales profit to explain the
contribution side of the rule.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_ADS_DB = Path("~/Docs/Web_automation/data/kaspi_marketing.sqlite")
DEFAULT_OWNER_DECISIONS = PROJECT_ROOT / "docs/plan/green_path_2026-06/OWNER_DECISIONS_RECORDED.yaml"
DEFAULT_SCOPE_CONFIG = PROJECT_ROOT / "config/ads_active_scope.yaml"


@dataclass(frozen=True)
class Od019Rule:
    kill_crr_pct_14d: float
    kill_requires_negative_contribution: bool
    fix_band_min_pct: float
    fix_band_max_pct: float
    decision_id: str = "OD-019"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _today_token() -> str:
    return datetime.now(timezone(timedelta(hours=5))).strftime("%Y%m%d_%H%M%S")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[:10]


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _normalize_store(source_store: Any, merchant_id: Any) -> str:
    store = str(source_store or "").strip().upper().replace(" ", "")
    merchant = str(merchant_id or "").strip()
    if store in {"30137883", "ACMEWEAR"} or merchant == "759051":
        return "ACMEWEAR"
    if store in {"30000002", "STORE-B", "STOREB"} or merchant == "1065684":
        return "STOREB"
    if store in {"UNIVERSAL", "1127778"}:
        return "UNIVERSAL"
    return store


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def load_od019_rule(path: Path = DEFAULT_OWNER_DECISIONS) -> Od019Rule:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        data = {}
    decisions = data.get("owner_decisions") or data.get("decisions") or []
    for item in decisions:
        if str(item.get("id") or "") == "OD-019":
            return _rule_from_params(item.get("params") or {})

    match = re.search(r"(?ms)^\s*-\s+id:\s*OD-019\b(?P<block>.*?)(?=^\s*-\s+id:|\Z)", text)
    if match:
        params_match = re.search(r"params:\s*(\{.*?\})", match.group("block"))
        if params_match:
            params = yaml.safe_load(params_match.group(1)) or {}
            return _rule_from_params(params)
    raise ValueError(f"OD-019 not found in {path}")


def _rule_from_params(params: dict[str, Any]) -> Od019Rule:
    band = params.get("fix_band_crr_pct") or [20, 35]
    return Od019Rule(
        kill_crr_pct_14d=float(params.get("kill_crr_pct_14d", 35)),
        kill_requires_negative_contribution=bool(params.get("kill_requires_negative_contribution", True)),
        fix_band_min_pct=float(band[0]),
        fix_band_max_pct=float(band[1]),
    )


def load_ads_scope(path: Path = DEFAULT_SCOPE_CONFIG) -> dict[str, Any]:
    if not path.exists():
        return {"default_active": True, "stores": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_store_active_on(scope: dict[str, Any], store_code: str, on_date: str) -> bool:
    store = str(store_code or "").strip().upper()
    windows = ((scope.get("stores") or {}).get(store) or {}).get("windows") or []
    target = _parse_date(on_date)
    active: bool | None = None
    for window in windows:
        start = _parse_date(str(window.get("start")))
        end_raw = window.get("end")
        end = _parse_date(str(end_raw)) if end_raw else None
        if target >= start and (end is None or target <= end):
            active = bool(window.get("active"))
    if active is None:
        active = bool(scope.get("default_active", False))
    return active


def resolve_as_of(app_db: Path, ads_db: Path, requested: str | None) -> str:
    if requested:
        return requested
    with _connect(app_db) as app_conn, _connect(ads_db) as ads_conn:
        app_max = _scalar(app_conn, "SELECT max(date) FROM ads_campaign_product_daily")
        source_max = _scalar(ads_conn, "SELECT max(date) FROM campaign_daily_current")
    dates = [_parse_date(_date_key(value)) for value in (app_max, source_max) if _date_key(value)]
    if not dates:
        raise ValueError("Cannot resolve as_of: no ads dates in app/source DB")
    return min(dates).isoformat()


def load_campaign_rows(
    ads_db: Path,
    *,
    start: str,
    end: str,
    scope: dict[str, Any],
) -> list[dict[str, Any]]:
    with _connect(ads_db) as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, merchant_id, store_code, campaign_id, campaign_name, state,
                       daily_budget, views, clicks, gmv, transactions, cost, crr,
                       report_state, record_timestamp, ingested_at
                FROM campaign_daily_current
                WHERE date(date) >= date(?) AND date(date) <= date(?)
                ORDER BY date, campaign_id
                """,
                (start, end),
            )
        ]
    out: list[dict[str, Any]] = []
    for row in rows:
        business_store = _normalize_store(row.get("store_code"), row.get("merchant_id"))
        date_key = _date_key(row.get("date"))
        if not business_store or not date_key or not is_store_active_on(scope, business_store, date_key):
            continue
        row["business_store_code"] = business_store
        row["date"] = date_key
        out.append(row)
    return out


def load_campaign_sku_map(app_db: Path, *, start: str, end: str) -> dict[tuple[str, str], dict[str, Any]]:
    with _connect(app_db) as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT store_code, campaign_id, campaign_name, sku_key,
                       sum(cost_kzt) AS cost_kzt,
                       group_concat(DISTINCT coverage_status) AS coverage_statuses,
                       min(date) AS first_date,
                       max(date) AS last_date
                FROM ads_campaign_product_daily
                WHERE date(date) >= date(?) AND date(date) <= date(?)
                GROUP BY store_code, campaign_id, campaign_name, sku_key
                ORDER BY store_code, campaign_id, sku_key
                """,
                (start, end),
            )
        ]
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["store_code"]), str(row["campaign_id"]))
        item = mapped.setdefault(
            key,
            {
                "sku_keys": [],
                "app_ads_cost_kzt": 0.0,
                "coverage_statuses": set(),
                "first_date": row.get("first_date"),
                "last_date": row.get("last_date"),
            },
        )
        sku_key = str(row.get("sku_key") or "").strip()
        if sku_key and sku_key not in item["sku_keys"]:
            item["sku_keys"].append(sku_key)
        item["app_ads_cost_kzt"] += _to_float(row.get("cost_kzt"))
        for status in str(row.get("coverage_statuses") or "").split(","):
            if status:
                item["coverage_statuses"].add(status)
    for item in mapped.values():
        item["sku_keys"] = sorted(item["sku_keys"])
        item["coverage_statuses"] = sorted(item["coverage_statuses"])
        item["app_ads_cost_kzt"] = round(item["app_ads_cost_kzt"], 2)
    return mapped


def load_sku_profit(app_db: Path, *, start: str, end: str) -> tuple[dict[tuple[str, str], dict[str, Any]], str | None]:
    with _connect(app_db) as conn:
        fact_max = _scalar(conn, "SELECT max(sale_date) FROM fact_sales_daily")
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT store_code, sku_key,
                       sum(units) AS units,
                       sum(revenue) AS revenue_kzt,
                       sum(cogs) AS cogs_kzt,
                       sum(profit) AS profit_kzt
                FROM fact_sales_daily
                WHERE date(sale_date) >= date(?) AND date(sale_date) <= date(?)
                GROUP BY store_code, sku_key
                ORDER BY store_code, sku_key
                """,
                (start, end),
            )
        ]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        out[(str(row["store_code"]), str(row["sku_key"]))] = {
            "units": _to_int(row.get("units")),
            "revenue_kzt": round(_to_float(row.get("revenue_kzt")), 2),
            "cogs_kzt": round(_to_float(row.get("cogs_kzt")), 2),
            "profit_kzt": round(_to_float(row.get("profit_kzt")), 2),
        }
    return out, _date_key(fact_max) or None


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(rows, key=lambda row: (row.get("date") or "", row.get("ingested_at") or ""))[-1]


def aggregate_campaigns(
    campaign_rows: list[dict[str, Any]],
    *,
    sku_map: dict[tuple[str, str], dict[str, Any]],
    sku_profit: dict[tuple[str, str], dict[str, Any]],
    sales_max_date: str | None,
    as_of: str,
    start: str,
    rule: Od019Rule,
    report_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in campaign_rows:
        key = (str(row["business_store_code"]), str(row.get("campaign_id") or ""))
        grouped.setdefault(key, []).append(row)

    report_rows: list[dict[str, Any]] = []
    disposition_rows: list[dict[str, Any]] = []
    sales_lag = bool(sales_max_date and _parse_date(sales_max_date) < _parse_date(as_of))
    for key, rows in sorted(grouped.items(), key=lambda entry: entry[0]):
        store_code, campaign_id = key
        latest = _latest(rows)
        cost = round(sum(_to_float(row.get("cost")) for row in rows), 2)
        gmv = round(sum(_to_float(row.get("gmv")) for row in rows), 2)
        transactions = sum(_to_int(row.get("transactions")) for row in rows)
        views = sum(_to_int(row.get("views")) for row in rows)
        clicks = sum(_to_int(row.get("clicks")) for row in rows)
        zero_gmv_spend_days = sum(
            1 for row in rows if _to_float(row.get("cost")) > 0 and _to_float(row.get("gmv")) <= 0
        )
        spend_days = sum(1 for row in rows if _to_float(row.get("cost")) > 0)
        crr_pct = round(cost * 100.0 / gmv, 2) if gmv > 0 else None
        crr_rule_value = "INF_ZERO_GMV" if gmv <= 0 and cost > 0 else "NO_SPEND" if cost <= 0 else str(crr_pct)

        mapping = sku_map.get(key, {})
        sku_keys: list[str] = list(mapping.get("sku_keys") or [])
        sku_profit_total = 0.0
        sku_units_total = 0
        for sku_key in sku_keys:
            profit_row = sku_profit.get((store_code, sku_key), {})
            sku_profit_total += _to_float(profit_row.get("profit_kzt"))
            sku_units_total += _to_int(profit_row.get("units"))
        contribution_after_ads = round(sku_profit_total - cost, 2) if sku_keys else None
        contribution_negative = contribution_after_ads is not None and contribution_after_ads < 0

        kill_threshold_hit = False
        if cost > 0:
            if gmv <= 0:
                kill_threshold_hit = True
            elif crr_pct is not None and crr_pct > rule.kill_crr_pct_14d:
                kill_threshold_hit = True
        fix_band_hit = crr_pct is not None and rule.fix_band_min_pct <= crr_pct <= rule.fix_band_max_pct

        latest_state = str(latest.get("state") or "").strip() or "UNKNOWN"
        if cost <= 0 and gmv <= 0:
            disposition = "PAUSED_NO_SPEND" if latest_state.lower() == "paused" else "NO_SPEND"
            action = "NONE"
            action_status = "LOGGED"
            reason = "no spend and no GMV in window"
        elif kill_threshold_hit and (
            not rule.kill_requires_negative_contribution or contribution_negative
        ):
            disposition = "KILL_RECOMMENDED_REPORT_ONLY" if report_only else "KILL_RECOMMENDED"
            action = "PAUSE_CAMPAIGN"
            action_status = "REPORT_ONLY_PENDING_EXTERNAL_APPLY" if report_only else "PENDING_APPLY"
            reason = (
                f"14d CRR exceeds {rule.kill_crr_pct_14d}% and contribution_after_ads is negative"
                if gmv > 0
                else "zero-GMV spend with negative contribution_after_ads"
            )
        elif kill_threshold_hit:
            disposition = "ZERO_GMV_OR_HIGH_CRR_REVIEW"
            action = "REVIEW"
            action_status = "LOGGED"
            reason = "CRR/zero-GMV threshold hit but negative-contribution condition is not proven"
        elif fix_band_hit:
            disposition = "FIX_REVIEW"
            action = "BID_TARGETING_REVIEW"
            action_status = "LOGGED"
            reason = f"14d CRR is in OD-019 fix band {rule.fix_band_min_pct:g}-{rule.fix_band_max_pct:g}%"
        else:
            disposition = "KEEP"
            action = "NONE"
            action_status = "LOGGED"
            reason = "campaign is below OD-019 fix/kill thresholds"

        common = {
            "as_of": as_of,
            "window_start": start,
            "window_end": as_of,
            "decision_id": rule.decision_id,
            "store_code": store_code,
            "campaign_id": campaign_id,
            "campaign_name": str(latest.get("campaign_name") or ""),
            "latest_state": latest_state,
            "latest_daily_budget_kzt": round(_to_float(latest.get("daily_budget")), 2),
            "cost_kzt_14d": cost,
            "gmv_kzt_14d": gmv,
            "transactions_14d": transactions,
            "views_14d": views,
            "clicks_14d": clicks,
            "spend_days_14d": spend_days,
            "zero_gmv_spend_days_14d": zero_gmv_spend_days,
            "crr_pct_14d": crr_pct,
            "crr_rule_value": crr_rule_value,
            "mapped_sku_keys": ";".join(sku_keys),
            "mapping_coverage_statuses": ";".join(mapping.get("coverage_statuses") or []),
            "app_ads_cost_kzt_14d": mapping.get("app_ads_cost_kzt", 0.0),
            "mapped_sku_units_14d": sku_units_total,
            "mapped_sku_profit_kzt_14d": round(sku_profit_total, 2),
            "contribution_after_ads_kzt_14d": contribution_after_ads,
            "contribution_basis": "mapped_sku_window_profit_minus_campaign_ad_cost",
            "sales_profit_max_date": sales_max_date or "",
            "sales_profit_lags_as_of": sales_lag,
            "disposition": disposition,
            "recommended_action": action,
            "action_status": action_status,
            "external_write_performed": False,
            "reason": reason,
        }
        report_rows.append(common)
        disposition_rows.append(
            {
                "logged_at": datetime.now(timezone(timedelta(hours=5))).isoformat(timespec="seconds"),
                **common,
            }
        )
    return report_rows, disposition_rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({field for row in rows for field in row.keys()})
    preferred = [
        "as_of",
        "window_start",
        "window_end",
        "decision_id",
        "store_code",
        "campaign_id",
        "campaign_name",
        "latest_state",
        "cost_kzt_14d",
        "gmv_kzt_14d",
        "crr_pct_14d",
        "crr_rule_value",
        "mapped_sku_keys",
        "mapped_sku_profit_kzt_14d",
        "contribution_after_ads_kzt_14d",
        "disposition",
        "recommended_action",
        "action_status",
        "external_write_performed",
        "reason",
    ]
    ordered = [field for field in preferred if field in fields] + [
        field for field in fields if field not in preferred
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Ads Campaign CRR Disposition Report",
        "",
        f"- As of: `{payload['as_of']}`",
        f"- Window: `{payload['window_start']}` to `{payload['window_end']}`",
        f"- Decision: `OD-019`",
        f"- Report-only: `{str(payload['report_only']).lower()}`",
        f"- External actions required: `{payload['summary']['external_actions_required_count']}`",
        "",
        "| Campaign | State | CRR 14d | Cost | GMV | SKU(s) | Contribution After Ads | Disposition | Action Status |",
        "|---|---|---:|---:|---:|---|---:|---|---|",
    ]
    for row in payload["campaigns"]:
        crr = row["crr_pct_14d"] if row["crr_pct_14d"] is not None else row["crr_rule_value"]
        contribution = (
            ""
            if row["contribution_after_ads_kzt_14d"] is None
            else row["contribution_after_ads_kzt_14d"]
        )
        lines.append(
            "| {campaign} | {state} | {crr} | {cost} | {gmv} | {skus} | {contribution} | {disp} | {status} |".format(
                campaign=row["campaign_id"],
                state=row["latest_state"],
                crr=crr,
                cost=row["cost_kzt_14d"],
                gmv=row["gmv_kzt_14d"],
                skus=row["mapped_sku_keys"],
                contribution=contribution,
                disp=row["disposition"],
                status=row["action_status"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    *,
    app_db: Path,
    ads_db: Path,
    as_of: str | None,
    window_days: int,
    output_dir: Path,
    owner_decisions: Path = DEFAULT_OWNER_DECISIONS,
    scope_config: Path = DEFAULT_SCOPE_CONFIG,
    report_only: bool = True,
) -> dict[str, Any]:
    resolved_as_of = resolve_as_of(app_db, ads_db, as_of)
    window_start = (_parse_date(resolved_as_of) - timedelta(days=window_days - 1)).isoformat()
    rule = load_od019_rule(owner_decisions)
    scope = load_ads_scope(scope_config)
    campaign_rows = load_campaign_rows(ads_db, start=window_start, end=resolved_as_of, scope=scope)
    sku_map = load_campaign_sku_map(app_db, start=window_start, end=resolved_as_of)
    sku_profit, sales_max_date = load_sku_profit(app_db, start=window_start, end=resolved_as_of)
    report_rows, disposition_rows = aggregate_campaigns(
        campaign_rows,
        sku_map=sku_map,
        sku_profit=sku_profit,
        sales_max_date=sales_max_date,
        as_of=resolved_as_of,
        start=window_start,
        rule=rule,
        report_only=report_only,
    )
    external_required = [
        row for row in disposition_rows if row["action_status"] == "REPORT_ONLY_PENDING_EXTERNAL_APPLY"
    ]
    fix_required = [row for row in disposition_rows if row["recommended_action"] == "BID_TARGETING_REVIEW"]
    review_required = [row for row in disposition_rows if row["recommended_action"] == "REVIEW"]
    payload = {
        "schema_version": "ads_campaign_crr_disposition_report.v1",
        "generated_at": datetime.now(timezone(timedelta(hours=5))).isoformat(timespec="seconds"),
        "as_of": resolved_as_of,
        "window_start": window_start,
        "window_end": resolved_as_of,
        "window_days": window_days,
        "report_only": report_only,
        "app_db": str(app_db),
        "ads_db": str(ads_db),
        "owner_decisions": str(owner_decisions),
        "scope_config": str(scope_config),
        "summary": {
            "campaign_count": len(report_rows),
            "kill_recommended_count": len(external_required),
            "fix_review_count": len(fix_required),
            "review_count": len(review_required),
            "external_actions_required_count": len(external_required),
            "external_write_performed": False,
            "all_campaigns_dispositioned": all(row.get("disposition") for row in report_rows),
            "sales_profit_max_date": sales_max_date,
        },
        "campaigns": report_rows,
        "dispositions": disposition_rows,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "daily_crr_report.csv", report_rows)
    _write_csv(output_dir / "campaign_disposition_log.csv", disposition_rows)
    _write_csv(output_dir / "campaign_daily_window.csv", campaign_rows)
    (output_dir / "ads_campaign_crr_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_markdown(output_dir / "ads_campaign_crr_report.md", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only G-ADS-02 CRR disposition report")
    parser.add_argument("--app-db", type=Path, default=DEFAULT_APP_DB)
    parser.add_argument("--ads-db", type=Path, default=DEFAULT_ADS_DB)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS)
    parser.add_argument("--scope-config", type=Path, default=DEFAULT_SCOPE_CONFIG)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "exports" / "ads_crr_disposition" / _today_token(),
    )
    parser.add_argument(
        "--allow-external-apply-status",
        action="store_true",
        help="Label kill rows as pending apply instead of report-only. This script still performs no external writes.",
    )
    args = parser.parse_args()

    payload = build_report(
        app_db=args.app_db,
        ads_db=args.ads_db,
        as_of=args.as_of,
        window_days=args.window_days,
        output_dir=args.output_dir,
        owner_decisions=args.owner_decisions,
        scope_config=args.scope_config,
        report_only=not args.allow_external_apply_status,
    )
    print(json.dumps({"ok": True, "output_dir": str(args.output_dir), "summary": payload["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
