#!/usr/bin/env python3
"""Build owner-facing monthly PnL surface with fail-closed decision-grade flags."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_ads_sidecar_readiness import validate_ads_sidecar_readiness
from scripts.validate_monthly_economics_parity import (
    validate_monthly_economics_parity,
)
from scripts.validate_opex_readiness import validate_opex_readiness
from scripts.webui_chronology_contract_utils import load_webui_chronology_gates
from scripts.webui_db_gate_utils import resolve_effective_missing_in_db_orders
from scripts.webui_archive_truth_utils import (
    DEFAULT_LEDGER_ROOT,
    build_webui_truth_projection,
    resolve_latest_dir,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_MAPPED_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "owner_pnl"
DEFAULT_PARITY_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "economics_parity"
DEFAULT_OPEX_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "opex_readiness"
DEFAULT_STATUSDATE_CUTOVER = date(2026, 2, 27)


class OwnerPnlError(RuntimeError):
    """Raised when strict owner PnL build fails."""


def _cap_pct(value: Any) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(100.0, numeric)), 2)


def _resolve_mapped_csv(*, mapped_root: Path, since: date, until: date, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
    else:
        path = (
            mapped_root.resolve()
            / f"{since.isoformat()}_to_{until.isoformat()}"
            / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
        )
    if not path.exists():
        raise OwnerPnlError(
            f"mapped archive csv missing: {path} (run export_sales_archive_statusdate_mapped.py first)"
        )
    return path


def _query_ads_monthly(*, db_path: Path, since: date, until: date) -> tuple[dict[tuple[str, str], float], bool]:
    if not db_path.exists():
        return {}, False
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ads_spend_sidecar_daily'"
        ).fetchone()
        if row is None:
            return {}, False
        rows = conn.execute(
            """
            SELECT
                substr(date(date), 1, 7) AS sale_month,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                SUM(COALESCE(total_cost_kzt, 0)) AS total_cost_kzt
            FROM ads_spend_sidecar_daily
            WHERE date(date) BETWEEN ? AND ?
            GROUP BY substr(date(date), 1, 7), UPPER(COALESCE(store_code, 'UNKNOWN'))
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    out: dict[tuple[str, str], float] = {}
    for r in rows:
        month = str(r["sale_month"] or "")
        store = str(r["store_code"] or "UNKNOWN")
        out[(month, store)] = round(float(r["total_cost_kzt"] or 0.0), 2)

    for month in sorted({k[0] for k in out}):
        month_sum = round(sum(v for (m, _), v in out.items() if m == month), 2)
        out[(month, "TOTAL")] = month_sum
    return out, True


def _fmt_kzt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f}"


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# OWNER PnL",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- since: `{report['since']}`",
        f"- status: `{report['status']}`",
        f"- ads_ready: `{str(bool(report['ads_readiness']['ok'])).lower()}`",
        f"- opex_ready: `{str(bool(report['opex_readiness']['ok'])).lower()}`",
        f"- parity_status: `{report['economics_parity_status']}`",
        "",
        "## Monthly Totals",
        "",
        "| Month | Decision Grade | StatusDate Coverage | Net Rev KZT | COGS KZT | Ads KZT | OPEX KZT | Profit After Ads KZT | Profit After Ads+OPEX KZT |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["monthly_totals"]:
        lines.append(
            f"| `{row['sale_month']}` | `{str(bool(row['decision_grade'])).lower()}` | "
            f"{row['statusdate_coverage_pct']:.2f}% | {_fmt_kzt(row['net_rev_kzt'])} | "
            f"{_fmt_kzt(row['cogs_kzt'])} | {_fmt_kzt(row['ads_kzt'])} | {_fmt_kzt(row['opex_kzt'])} | "
            f"{_fmt_kzt(row['profit_after_ads_kzt'])} | {_fmt_kzt(row['profit_after_ads_and_opex_kzt'])} |"
        )

    if report.get("monthly_by_store"):
        lines.extend(
            [
                "",
                "## Monthly By Store",
                "",
                "| Month | Store | Decision Grade | StatusDate Coverage | Net Rev KZT | COGS KZT | Ads KZT | Profit After Ads KZT |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in report["monthly_by_store"]:
            lines.append(
                f"| `{row['sale_month']}` | `{row['store_code']}` | "
                f"`{str(bool(row['decision_grade'])).lower()}` | {row['statusdate_coverage_pct']:.2f}% | "
                f"{_fmt_kzt(row['net_rev_kzt'])} | {_fmt_kzt(row['cogs_kzt'])} | {_fmt_kzt(row['ads_kzt'])} | "
                f"{_fmt_kzt(row['profit_after_ads_kzt'])} |"
            )

    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def _render_ascii(report: dict[str, Any]) -> str:
    headers = [
        "Month",
        "Decision",
        "Coverage%",
        "Net Rev",
        "COGS",
        "Ads",
        "OPEX",
        "Profit-Ads",
        "Profit-Ads-OPEX",
    ]
    rows: list[list[str]] = []
    for row in report["monthly_totals"]:
        rows.append(
            [
                str(row["sale_month"]),
                "YES" if bool(row["decision_grade"]) else "NO",
                f"{row['statusdate_coverage_pct']:.2f}",
                _fmt_kzt(row["net_rev_kzt"]),
                _fmt_kzt(row["cogs_kzt"]),
                _fmt_kzt(row["ads_kzt"]),
                _fmt_kzt(row["opex_kzt"]),
                _fmt_kzt(row["profit_after_ads_kzt"]),
                _fmt_kzt(row["profit_after_ads_and_opex_kzt"]),
            ]
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _line(ch: str = "-") -> str:
        return "+" + "+".join(ch * (w + 2) for w in widths) + "+"

    out = [_line("-")]
    out.append(
        "| "
        + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        + " |"
    )
    out.append(_line("="))
    for row in rows:
        out.append(
            "| "
            + " | ".join(row[i].ljust(widths[i]) for i in range(len(headers)))
            + " |"
        )
    out.append(_line("-"))
    return "\n".join(out) + "\n"


def _query_opex_monthly(*, db_path: Path, since: date, until: date) -> tuple[dict[str, float], bool]:
    if not db_path.exists():
        return {}, False
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_cashflow_commitments'"
        ).fetchone()
        if row is None:
            return {}, False
        rows = conn.execute(
            """
            SELECT
                substr(date(commit_date), 1, 7) AS commit_month,
                SUM(COALESCE(amount_kzt, 0)) AS total_opex_kzt
            FROM fact_cashflow_commitments
            WHERE UPPER(COALESCE(commit_type, '')) = 'OPEX'
              AND date(commit_date) BETWEEN ? AND ?
            GROUP BY substr(date(commit_date), 1, 7)
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    out: dict[str, float] = {}
    for row in rows:
        month = str(row["commit_month"] or "")
        if not month:
            continue
        out[month] = round(float(row["total_opex_kzt"] or 0.0), 2)
    return out, True


def _load_gate_status(validation_dir: Path, file_name: str, fallback_status: str = "FAIL") -> dict[str, Any]:
    path = validation_dir / file_name
    if not path.exists():
        return {"status": fallback_status, "ok": False, "reason": f"missing:{file_name}", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status") or fallback_status).upper()
    return {"status": status, "ok": status == "PASS", "path": str(path), "payload": payload}


def _resolve_validation_dir(validation_dir: Path | None, *, truth_source: str, as_of: date) -> Path:
    if validation_dir is not None:
        return validation_dir.resolve()
    if truth_source == "webui_archive":
        return PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of.isoformat()
    return PROJECT_ROOT / "exports" / "validation" / "crm_north_star_restate" / as_of.isoformat()


def _resolve_opex_schedule_yaml(root: Path, explicit: Path | None = None) -> Path:
    candidate = explicit
    if candidate is None:
        raw = os.environ.get("AB_OPEX_SCHEDULE_YAML", "").strip()
        if raw:
            candidate = Path(raw)
    if candidate is None:
        return (root / "config" / "opex" / "opex_schedule.yaml").resolve()
    resolved = candidate.expanduser()
    if not resolved.is_absolute():
        resolved = (root / resolved).resolve()
    if not resolved.exists():
        raise OwnerPnlError(f"AB_OPEX_SCHEDULE_YAML does not exist: {resolved}")
    return resolved.resolve()


def _resolve_ledger_root(ledger_root: Path | None) -> Path:
    if ledger_root is None:
        return resolve_latest_dir(DEFAULT_LEDGER_ROOT)
    candidate = ledger_root.expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = DEFAULT_LEDGER_ROOT / candidate
    if alt.exists():
        return alt.resolve()
    raise OwnerPnlError(f"ledger root not found: {ledger_root}")


def _load_webui_truth_gates(validation_dir: Path) -> tuple[dict[str, dict[str, Any]], bool]:
    chronology_gates, chronology_ok, _chronology_meta = load_webui_chronology_gates(validation_dir)
    gates = {
        **chronology_gates,
        "webui_vs_current_db": _load_gate_status(validation_dir, "webui_vs_db_report.json"),
        "ads_offer_universe": _load_gate_status(validation_dir, "ads_offer_universe_report.json"),
        "ads_spend_reality": _load_gate_status(validation_dir, "ads_spend_reality_report.json"),
        "cogs_completeness": _load_gate_status(validation_dir, "cogs_completeness_report.json"),
        "cogs_realism": _load_gate_status(validation_dir, "cogs_realism_report.json"),
        "order_status_audit": _load_gate_status(validation_dir, "order_status_audit_report.json"),
    }
    return gates, bool(chronology_ok and all(bool(item.get("ok")) for item in gates.values()))


def _query_owner_truth_rows(*, db_path: Path, since: date, until: date) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame(
            columns=["order_id", "sale_date", "sale_month", "store_code", "sku_key", "units", "net_rev_kzt", "cogs_kzt"]
        )
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            rows = pd.read_sql_query(
                """
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    date(sale_date) AS sale_date,
                    substr(date(sale_date), 1, 7) AS sale_month,
                    UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                    COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                    CAST(COALESCE(units, 0) AS REAL) AS units,
                    CAST(COALESCE(net_rev_kzt, 0) AS REAL) AS net_rev_kzt,
                    CAST(COALESCE(cogs_kzt, 0) AS REAL) AS cogs_kzt
                FROM view_sales_line_truth
                WHERE date(sale_date) BETWEEN date(?) AND date(?)
                """,
                conn,
                params=[since.isoformat(), until.isoformat()],
            )
        except Exception:
            rows = pd.read_sql_query(
                """
                SELECT
                    CAST(order_id AS TEXT) AS order_id,
                    date(order_date) AS sale_date,
                    substr(date(order_date), 1, 7) AS sale_month,
                    UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
                    COALESCE(NULLIF(sku_key, ''), '__UNMAPPED__') AS sku_key,
                    CAST(COALESCE(quantity, 0) AS REAL) AS units,
                    CAST(COALESCE(net_rev, 0) AS REAL) AS net_rev_kzt,
                    CAST(COALESCE(cogs, 0) AS REAL) AS cogs_kzt
                FROM sales_fact_v2
                WHERE date(order_date) BETWEEN date(?) AND date(?)
                  AND UPPER(COALESCE(status, '')) = 'DELIVERED'
                  AND CAST(COALESCE(return_flag, 0) AS INTEGER) = 0
                """,
                conn,
                params=[since.isoformat(), until.isoformat()],
            )
    finally:
        conn.close()
    return rows


def build_owner_pnl_report(
    *,
    db_path: Path,
    as_of: date,
    since: date,
    mapped_root: Path,
    mapped_csv: Path | None,
    output_root: Path,
    parity_output_root: Path,
    include_store_breakdown: bool,
    strict: bool,
    truth_source: str = "db",
    validation_dir: Path | None = None,
    ledger_root: Path | None = None,
    tolerance_pct: float = 0.005,
    statusdate_cutover: date = DEFAULT_STATUSDATE_CUTOVER,
    ads_max_age_hours: float = 36.0,
    ads_min_mapping_coverage_pct: float = 85.0,
    ads_min_total_cost_kzt: float = 1.0,
    opex_output_root: Path = DEFAULT_OPEX_OUTPUT_ROOT,
    opex_schedule_yaml: Path = PROJECT_ROOT / "config" / "opex" / "opex_schedule.yaml",
    opex_max_schedule_age_days: int = 30,
    opex_min_horizon_days: int = 30,
    require_opex_for_net_publication: bool = False,
) -> dict[str, Any]:
    if since > as_of:
        raise OwnerPnlError("since must be <= as_of")

    resolved_mapped_csv = _resolve_mapped_csv(
        mapped_root=mapped_root,
        since=since,
        until=as_of,
        explicit=mapped_csv,
    )

    parity = validate_monthly_economics_parity(
        since=since,
        until=as_of,
        db_path=db_path.resolve(),
        mapped_csv=resolved_mapped_csv,
        output_root=parity_output_root.resolve(),
        strict=False,
        tolerance_pct=float(tolerance_pct),
        statusdate_cutover=statusdate_cutover,
    )
    ads_readiness = validate_ads_sidecar_readiness(
        db_path=db_path.resolve(),
        as_of=as_of,
        output_root=PROJECT_ROOT / "exports" / "validation" / "ads_sidecar_readiness",
        max_age_hours=float(ads_max_age_hours),
        min_mapping_coverage_pct=float(ads_min_mapping_coverage_pct),
        min_total_cost_kzt=float(ads_min_total_cost_kzt),
        readiness_mode="live",
        strict=False,
    )
    opex_readiness = validate_opex_readiness(
        db_path=db_path.resolve(),
        as_of=as_of,
        output_root=opex_output_root.resolve(),
        schedule_yaml=opex_schedule_yaml.resolve(),
        max_schedule_age_days=int(opex_max_schedule_age_days),
        min_horizon_days=int(opex_min_horizon_days),
        strict=False,
    )

    ads_monthly_map, ads_table_exists = _query_ads_monthly(
        db_path=db_path.resolve(),
        since=since,
        until=as_of,
    )
    opex_monthly_map, opex_table_exists = _query_opex_monthly(
        db_path=db_path.resolve(),
        since=since,
        until=as_of,
    )
    resolved_validation_dir = _resolve_validation_dir(
        validation_dir,
        truth_source=truth_source,
        as_of=as_of,
    )
    webui_truth_gates: dict[str, dict[str, Any]] = {}
    webui_truth_ready = True
    projection_meta: dict[str, Any] | None = None

    if truth_source == "webui_archive":
        resolved_ledger_root = _resolve_ledger_root(ledger_root)
        projection, projection_meta = build_webui_truth_projection(
            db_path=db_path.resolve(),
            ledger_run_root=resolved_ledger_root,
            start=since.isoformat(),
            end=as_of.isoformat(),
        )
        effective_missing_in_db_orders, source_meta = resolve_effective_missing_in_db_orders(
            output_dir=resolved_validation_dir,
            ledger_root=resolved_ledger_root,
            start=since.isoformat(),
            end=as_of.isoformat(),
            projection_meta=projection_meta,
        )
        projection_meta["missing_in_db_orders"] = int(effective_missing_in_db_orders)
        if source_meta is not None:
            projection_meta["effective_missing_in_db_orders_source"] = source_meta
        match_status = (
            projection["db_match_status"]
            if "db_match_status" in projection.columns
            else pd.Series(["MATCHED"] * len(projection), index=projection.index)
        )
        truth_rows = projection[match_status == "MATCHED"].copy()
        truth_rows["sale_month"] = truth_rows["sale_date"].astype(str).str.slice(0, 7)
        truth_rows["store_code"] = truth_rows["store_code"].fillna("UNIVERSAL").astype(str).str.upper()
        truth_rows["sku_key"] = truth_rows["sku_key"].fillna("__UNMAPPED__").astype(str)
        truth_rows["units"] = pd.to_numeric(truth_rows["units"], errors="coerce").fillna(0.0)
        truth_rows["net_rev_kzt"] = pd.to_numeric(truth_rows["net_rev_kzt"], errors="coerce").fillna(0.0)
        truth_rows["cogs_kzt"] = pd.to_numeric(truth_rows["cogs_kzt"], errors="coerce").fillna(0.0)

        db_reference = _query_owner_truth_rows(db_path=db_path.resolve(), since=since, until=as_of)
        projected_orders = (
            truth_rows.groupby(["sale_month", "store_code"], as_index=False)
            .agg(projected_orders=("order_id", "nunique"))
            if not truth_rows.empty
            else pd.DataFrame(columns=["sale_month", "store_code", "projected_orders"])
        )
        db_orders = (
            db_reference.groupby(["sale_month", "store_code"], as_index=False)
            .agg(db_orders=("order_id", "nunique"))
            if not db_reference.empty
            else pd.DataFrame(columns=["sale_month", "store_code", "db_orders"])
        )
        coverage_df = projected_orders.merge(db_orders, on=["sale_month", "store_code"], how="outer").fillna(0.0)
        coverage_map: dict[tuple[str, str], float] = {}
        for row in coverage_df.to_dict("records"):
            projected = float(row.get("projected_orders") or 0.0)
            total = float(row.get("db_orders") or 0.0)
            coverage_map[(str(row["sale_month"]), str(row["store_code"]).upper())] = _cap_pct(
                (projected / total) * 100.0 if total > 0 else (100.0 if projected > 0 else 0.0),
            )

        parity_store_map = {
            (str(row["sale_month"]), str(row["store_code"]).upper()): bool(row.get("decision_grade"))
            for row in parity["rows"]
        }
        webui_truth_gates, webui_truth_ready = _load_webui_truth_gates(resolved_validation_dir)

        truth_month_store = (
            truth_rows.groupby(["sale_month", "store_code"], as_index=False)
            .agg(
                net_rev_kzt=("net_rev_kzt", "sum"),
                cogs_kzt=("cogs_kzt", "sum"),
            )
            if not truth_rows.empty
            else pd.DataFrame(columns=["sale_month", "store_code", "net_rev_kzt", "cogs_kzt"])
        )

        by_store_rows = []
        for row in truth_month_store.to_dict("records"):
            month = str(row["sale_month"])
            store = str(row["store_code"]).upper()
            decision_grade = bool(parity_store_map.get((month, store), False) and webui_truth_ready)
            coverage_pct = _cap_pct(coverage_map.get((month, store), 0.0))
            ads_kzt = ads_monthly_map.get((month, store))
            publishable = bool(decision_grade and ads_readiness["ok"])
            net_rev = round(float(row.get("net_rev_kzt") or 0.0), 2) if publishable else None
            cogs = round(float(row.get("cogs_kzt") or 0.0), 2) if publishable else None
            profit_val = (
                round(float(row.get("net_rev_kzt") or 0.0) - float(row.get("cogs_kzt") or 0.0), 2)
                if publishable
                else None
            )
            profit_after_ads = (
                round(float(profit_val) - float(ads_kzt or 0.0), 2)
                if publishable and profit_val is not None and ads_kzt is not None
                else None
            )
            by_store_rows.append(
                {
                    "sale_month": month,
                    "store_code": store,
                    "decision_grade": decision_grade,
                    "statusdate_coverage_pct": coverage_pct,
                    "net_rev_kzt": net_rev,
                    "cogs_kzt": cogs,
                    "ads_kzt": round(float(ads_kzt), 2) if ads_kzt is not None and publishable else None,
                    "profit_after_ads_kzt": profit_after_ads,
                    "locked_reason": None if publishable else "LOCKED_WEBUI_PROMOTION_OR_PARITY_OR_ADS_NOT_READY",
                }
            )

        totals_rows = []
        df = pd.DataFrame(by_store_rows)
        for month in sorted(df["sale_month"].unique().tolist()) if not df.empty else []:
            month_rows = df[df["sale_month"] == month]
            decision_grade = bool((month_rows["decision_grade"] == True).all())  # noqa: E712
            publishable = bool(decision_grade and ads_readiness["ok"])
            coverage_pct = _cap_pct(month_rows["statusdate_coverage_pct"].max() if not month_rows.empty else 0.0)
            net_rev_val = round(sum(float(v or 0.0) for v in month_rows["net_rev_kzt"].tolist()), 2)
            cogs_val = round(sum(float(v or 0.0) for v in month_rows["cogs_kzt"].tolist()), 2)
            profit_val = round(net_rev_val - cogs_val, 2)
            ads_val = ads_monthly_map.get((month, "TOTAL"))
            totals_rows.append(
                {
                    "sale_month": month,
                    "decision_grade": decision_grade,
                    "statusdate_coverage_pct": coverage_pct,
                    "net_rev_kzt": net_rev_val if publishable else None,
                    "cogs_kzt": cogs_val if publishable else None,
                    "ads_kzt": round(float(ads_val), 2) if (publishable and ads_val is not None) else None,
                    "profit_after_ads_kzt": (
                        round(profit_val - float(ads_val or 0.0), 2)
                        if publishable and ads_val is not None
                        else None
                    ),
                    "opex_kzt": (
                        round(float(opex_monthly_map.get(month, 0.0)), 2)
                        if (publishable and opex_readiness.get("ok"))
                        else None
                    ),
                    "profit_after_ads_and_opex_kzt": (
                        round((profit_val - float(ads_val or 0.0)) - float(opex_monthly_map.get(month, 0.0)), 2)
                        if publishable and ads_val is not None and opex_readiness.get("ok")
                        else None
                    ),
                    "locked_reason": None if publishable else "LOCKED_WEBUI_PROMOTION_OR_PARITY_OR_ADS_NOT_READY",
                }
            )
    else:
        by_store_rows = []
        for row in parity["rows"]:
            month = str(row["sale_month"])
            store = str(row["store_code"]).upper()
            decision_grade = bool(row.get("decision_grade"))
            coverage_pct = _cap_pct(float(row.get("status_date_coverage") or 0.0) * 100.0)
            ads_kzt = ads_monthly_map.get((month, store))
            publishable = bool(decision_grade and ads_readiness["ok"])

            net_rev = round(float(row.get("db_net_rev_kzt") or 0.0), 2) if publishable else None
            cogs = round(float(row.get("db_cogs_kzt") or 0.0), 2) if publishable else None
            profit = round(float(row.get("db_profit_kzt") or 0.0), 2) if publishable else None
            profit_after_ads = (
                round(profit - float(ads_kzt or 0.0), 2)
                if publishable and profit is not None and ads_kzt is not None
                else None
            )
            by_store_rows.append(
                {
                    "sale_month": month,
                    "store_code": store,
                    "decision_grade": decision_grade,
                    "statusdate_coverage_pct": coverage_pct,
                    "net_rev_kzt": net_rev,
                    "cogs_kzt": cogs,
                    "ads_kzt": round(float(ads_kzt), 2) if ads_kzt is not None and publishable else None,
                    "profit_after_ads_kzt": profit_after_ads,
                    "locked_reason": None if publishable else "LOCKED_NOT_DECISION_GRADE_OR_ADS_NOT_READY",
                }
            )

        totals_rows = []
        df = pd.DataFrame(by_store_rows)
        for month in sorted(df["sale_month"].unique().tolist()) if not df.empty else []:
            month_rows = df[df["sale_month"] == month]
            decision_grade = bool((month_rows["decision_grade"] == True).all())  # noqa: E712
            publishable = bool(decision_grade and ads_readiness["ok"])
            parity_rows = [r for r in parity["rows"] if str(r["sale_month"]) == month]
            archive_rows = sum(int(float(r.get("archive_rows") or 0.0)) for r in parity_rows)
            if archive_rows > 0:
                coverage_pct = round(
                    (
                        sum(
                            float(r.get("status_date_coverage") or 0.0)
                            * int(float(r.get("archive_rows") or 0.0))
                            for r in parity_rows
                        )
                        / float(archive_rows)
                    )
                    * 100.0,
                )
            else:
                coverage_pct = 0.0
            coverage_pct = _cap_pct(coverage_pct)

            net_rev_val = round(sum(float(r.get("db_net_rev_kzt") or 0.0) for r in parity_rows), 2)
            cogs_val = round(sum(float(r.get("db_cogs_kzt") or 0.0) for r in parity_rows), 2)
            profit_val = round(sum(float(r.get("db_profit_kzt") or 0.0) for r in parity_rows), 2)
            ads_val = ads_monthly_map.get((month, "TOTAL"))

            totals_rows.append(
                {
                    "sale_month": month,
                    "decision_grade": decision_grade,
                    "statusdate_coverage_pct": coverage_pct,
                    "net_rev_kzt": net_rev_val if publishable else None,
                    "cogs_kzt": cogs_val if publishable else None,
                    "ads_kzt": round(float(ads_val), 2) if (publishable and ads_val is not None) else None,
                    "profit_after_ads_kzt": (
                        round(profit_val - float(ads_val or 0.0), 2)
                        if publishable and ads_val is not None
                        else None
                    ),
                    "opex_kzt": (
                        round(float(opex_monthly_map.get(month, 0.0)), 2)
                        if (publishable and opex_readiness.get("ok"))
                        else None
                    ),
                    "profit_after_ads_and_opex_kzt": (
                        round(
                            (profit_val - float(ads_val or 0.0)) - float(opex_monthly_map.get(month, 0.0)),
                            2,
                        )
                        if publishable and ads_val is not None and opex_readiness.get("ok")
                        else None
                    ),
                    "locked_reason": None if publishable else "LOCKED_NOT_DECISION_GRADE_OR_ADS_NOT_READY",
                }
            )

    errors: list[str] = []
    error_codes: list[str] = []
    if parity.get("status") != "PASS":
        error_codes.append("ECONOMICS_PARITY_FAIL")
        errors.append(
            f"economics parity status={parity.get('status')} decision_grade_mismatches={parity.get('decision_grade_mismatch_count')}"
        )
    if not ads_readiness.get("ok", False):
        error_codes.append("ADS_READINESS_FAIL")
        errors.append(
            f"ads readiness status={ads_readiness.get('status')} error_code={ads_readiness.get('error_code')}"
        )
    if not ads_table_exists:
        error_codes.append("ADS_TABLE_MISSING")
        errors.append("ads_spend_sidecar_daily table missing in operational DB")
    if truth_source == "webui_archive" and not webui_truth_ready:
        error_codes.append("WEBUI_PROMOTION_FAIL")
        failing_gates = [name for name, payload in webui_truth_gates.items() if not payload.get("ok")]
        errors.append(
            "webui promotion contract not green: "
            + (", ".join(failing_gates) if failing_gates else "missing promotion artifacts")
        )
    if truth_source == "webui_archive" and projection_meta is not None:
        if int(projection_meta.get("projected_rows", 0)) == 0:
            error_codes.append("WEBUI_PROJECTION_EMPTY")
            errors.append("webui truth projection produced 0 matched rows")
        if int(projection_meta.get("missing_in_db_orders", 0)) > 0:
            error_codes.append("WEBUI_MISSING_DB_ORDERS")
            errors.append(
                f"webui truth projection missing_in_db_orders={projection_meta.get('missing_in_db_orders')}"
            )
    if require_opex_for_net_publication:
        if not opex_table_exists:
            error_codes.append("OPEX_TABLE_MISSING")
            errors.append("fact_cashflow_commitments table missing in operational DB")
        if not opex_readiness.get("ok", False):
            error_codes.append("OPEX_READINESS_FAIL")
            errors.append(
                f"opex readiness status={opex_readiness.get('status')} error_code={opex_readiness.get('error_code')}"
            )

    overall_ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    by_store_csv = out_dir / "owner_pnl_monthly_by_store.csv"
    totals_csv = out_dir / "owner_pnl_monthly_totals.csv"
    if by_store_rows:
        pd.DataFrame(by_store_rows).to_csv(by_store_csv, index=False, encoding="utf-8")
    else:
        by_store_csv.write_text("", encoding="utf-8")
    if totals_rows:
        pd.DataFrame(totals_rows).to_csv(totals_csv, index=False, encoding="utf-8")
    else:
        totals_csv.write_text("", encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "since": since.isoformat(),
        "truth_source": truth_source,
        "status": "PASS" if overall_ok else "FAIL",
        "ok": overall_ok,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "db_path": str(db_path.resolve()),
        "mapped_csv": str(resolved_mapped_csv),
        "economics_parity_status": parity.get("status"),
        "economics_parity_summary_path": parity.get("summary_json"),
        "validation_dir": str(resolved_validation_dir),
        "webui_truth_projection": projection_meta,
        "webui_truth_gates": webui_truth_gates if truth_source == "webui_archive" else {},
        "ads_readiness": {
            "ok": bool(ads_readiness.get("ok")),
            "status": ads_readiness.get("status"),
            "error_code": ads_readiness.get("error_code"),
            "mapping_coverage_pct": (
                (ads_readiness.get("ads_payload") or {}).get("mapping_coverage_pct")
            ),
            "total_cost_kzt": (ads_readiness.get("ads_payload") or {}).get("total_cost_kzt"),
            "json_path": ads_readiness.get("json_path"),
        },
        "opex_readiness": {
            "ok": bool(opex_readiness.get("ok")),
            "status": opex_readiness.get("status"),
            "error_code": opex_readiness.get("error_code"),
            "max_commit_date": opex_readiness.get("max_commit_date"),
            "json_path": opex_readiness.get("json_path"),
        },
        "monthly_totals": totals_rows,
        "monthly_by_store": by_store_rows if include_store_breakdown else [],
    }
    json_path = out_dir / "OWNER_PNL.json"
    md_path = out_dir / "OWNER_PNL.md"
    ascii_path = out_dir / "OWNER_PNL_ASCII.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    ascii_path.write_text(_render_ascii(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    report["ascii_path"] = str(ascii_path)
    report["monthly_by_store_csv"] = str(by_store_csv)
    report["monthly_totals_csv"] = str(totals_csv)

    if strict and not overall_ok:
        raise OwnerPnlError("owner pnl build failed strict checks")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build fail-closed OWNER_PNL report.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--since",
        default=os.environ.get("AB_ECONOMICS_PARITY_SINCE", "2025-06-06"),
    )
    parser.add_argument("--mapped-root", type=Path, default=DEFAULT_MAPPED_ROOT)
    parser.add_argument("--mapped-csv", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--parity-output-root", type=Path, default=DEFAULT_PARITY_OUTPUT_ROOT)
    parser.add_argument("--include-store-breakdown", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--validation-dir", type=Path, default=None)
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--tolerance-pct", type=float, default=0.005)
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER.isoformat())
    parser.add_argument(
        "--ads-max-age-hours",
        type=float,
        default=float(os.environ.get("AB_ADS_DB_MAX_AGE_HOURS", "36")),
    )
    parser.add_argument(
        "--ads-min-mapping-coverage-pct",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_COVERAGE_PCT", "85")),
    )
    parser.add_argument(
        "--ads-min-total-cost-kzt",
        type=float,
        default=float(os.environ.get("AB_ADS_MAPPING_MIN_TOTAL_COST_KZT", "1")),
    )
    parser.add_argument("--opex-output-root", type=Path, default=DEFAULT_OPEX_OUTPUT_ROOT)
    parser.add_argument(
        "--opex-schedule-yaml",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--opex-max-schedule-age-days",
        type=int,
        default=int(os.environ.get("AB_OPEX_SCHEDULE_MAX_AGE_DAYS", "30")),
    )
    parser.add_argument(
        "--opex-min-horizon-days",
        type=int,
        default=int(os.environ.get("AB_OPEX_MIN_HORIZON_DAYS", "30")),
    )
    parser.add_argument(
        "--require-opex-for-net-publication",
        action="store_true",
        default=bool(int(os.environ.get("AB_OWNER_PNL_REQUIRE_OPEX", "0"))),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        resolved_opex_schedule_yaml = _resolve_opex_schedule_yaml(PROJECT_ROOT, args.opex_schedule_yaml)
        report = build_owner_pnl_report(
            db_path=args.db,
            as_of=date.fromisoformat(str(args.as_of)),
            since=date.fromisoformat(str(args.since)),
            mapped_root=args.mapped_root,
            mapped_csv=args.mapped_csv,
            output_root=args.output_root,
            parity_output_root=args.parity_output_root,
            include_store_breakdown=bool(args.include_store_breakdown),
            strict=bool(args.strict),
            truth_source=str(args.truth_source),
            validation_dir=args.validation_dir,
            ledger_root=args.ledger_root,
            tolerance_pct=float(args.tolerance_pct),
            statusdate_cutover=date.fromisoformat(str(args.statusdate_cutover)),
            ads_max_age_hours=float(args.ads_max_age_hours),
            ads_min_mapping_coverage_pct=float(args.ads_min_mapping_coverage_pct),
            ads_min_total_cost_kzt=float(args.ads_min_total_cost_kzt),
            opex_output_root=args.opex_output_root,
            opex_schedule_yaml=resolved_opex_schedule_yaml,
            opex_max_schedule_age_days=int(args.opex_max_schedule_age_days),
            opex_min_horizon_days=int(args.opex_min_horizon_days),
            require_opex_for_net_publication=bool(args.require_opex_for_net_publication),
        )
    except OwnerPnlError as exc:
        print("status=FAIL")
        print("error_code=OWNER_PNL_BUILD_FAIL")
        print(f"message={exc}")
        return 1
    print(f"owner_pnl_json={report['json_path']}")
    print(f"owner_pnl_md={report['md_path']}")
    print(f"owner_pnl_ascii={report['ascii_path']}")
    print(f"owner_pnl_totals_csv={report['monthly_totals_csv']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
