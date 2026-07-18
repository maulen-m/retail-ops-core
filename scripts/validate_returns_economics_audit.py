#!/usr/bin/env python3
"""Validate that returned orders do not leak into delivered economics beyond volatility window."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views
from core.db.validation_copy import validation_db_copy

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "returns_economics"


class ReturnsEconomicsError(RuntimeError):
    """Raised when strict returns economics validation fails."""


def _relation_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _column_exists(conn: sqlite3.Connection, relation: str, column: str) -> bool:
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({relation})").fetchall())


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Returns Economics Audit",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- since: `{report['since']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- volatility_days: `{report['volatility_days']}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            f"| `{check['check']}` | {'PASS' if check['ok'] else 'FAIL'} | {check['details']} |"
        )

    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")

    if report.get("stale_leak_orders_csv"):
        lines.extend([
            "",
            "## Artifacts",
            "",
            f"- stale_leak_orders_csv: `{report['stale_leak_orders_csv']}`",
            f"- return_cash_reversal_rows_csv: `{report['return_cash_reversal_rows_csv']}`",
            f"- monthly_returns_csv: `{report['monthly_returns_csv']}`",
        ])
    return "\n".join(lines) + "\n"


def _load_leaked_sales_for_returned_orders(
    conn: sqlite3.Connection,
    *,
    returned: pd.DataFrame,
    as_of: date,
) -> pd.DataFrame:
    """Load delivered sales only for returned orders within the requested window."""
    if returned.empty:
        return pd.DataFrame(columns=["order_id", "store_code", "sale_date", "return_date"])

    scoped = returned.copy()
    scoped["order_id"] = scoped["order_id"].astype(str)
    scoped = scoped[scoped["order_id"].str.len() > 0].copy()
    scoped["return_date"] = pd.to_datetime(scoped["return_date"], errors="coerce").dt.date
    scoped = scoped[scoped["return_date"].notna()].copy()
    if scoped.empty:
        return pd.DataFrame(columns=["order_id", "store_code", "sale_date", "return_date"])

    order_ids = sorted(scoped["order_id"].drop_duplicates().tolist())
    sales_frames: list[pd.DataFrame] = []
    chunk_size = 500
    for start in range(0, len(order_ids), chunk_size):
        chunk = order_ids[start : start + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        params = [*chunk, as_of.isoformat()]
        if _relation_exists(conn, "view_sales_line_truth"):
            sales_frames.append(
                pd.read_sql_query(
                    f"""
                    SELECT
                        CAST(order_id AS TEXT) AS order_id,
                        UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                        date(sale_date) AS sale_date,
                        'view_sales_line_truth' AS source_table
                    FROM view_sales_line_truth
                    WHERE CAST(order_id AS TEXT) IN ({placeholders})
                      AND date(sale_date) <= ?
                    """,
                    conn,
                    params=params,
                )
            )
        elif _relation_exists(conn, "sales_fact_v2"):
            sale_date_col = "order_date" if _column_exists(conn, "sales_fact_v2", "order_date") else "sale_date"
            if _column_exists(conn, "sales_fact_v2", sale_date_col):
                store_expr = "store_code" if _column_exists(conn, "sales_fact_v2", "store_code") else "'UNKNOWN'"
                status_expr = "status" if _column_exists(conn, "sales_fact_v2", "status") else "'DELIVERED'"
                return_expr = "return_flag" if _column_exists(conn, "sales_fact_v2", "return_flag") else "0"
                sales_frames.append(
                    pd.read_sql_query(
                        f"""
                        SELECT
                            CAST(order_id AS TEXT) AS order_id,
                            UPPER(COALESCE({store_expr}, 'UNKNOWN')) AS store_code,
                            date({sale_date_col}) AS sale_date,
                            'sales_fact_v2' AS source_table
                        FROM sales_fact_v2
                        WHERE CAST(order_id AS TEXT) IN ({placeholders})
                          AND date({sale_date_col}) <= ?
                          AND UPPER(COALESCE({status_expr}, 'DELIVERED')) IN ('DELIVERED', 'COMPLETED', 'ВЫДАН')
                          AND COALESCE({return_expr}, 0) = 0
                        """,
                        conn,
                        params=params,
                    )
                )

    sales = (
        pd.concat(sales_frames, ignore_index=True)
        if sales_frames
        else pd.DataFrame(columns=["order_id", "store_code", "sale_date"])
    )
    if sales.empty:
        return pd.DataFrame(columns=["order_id", "store_code", "sale_date", "return_date", "source_table"])
    scoped = scoped[["order_id", "store_code", "return_date"]].drop_duplicates()
    return sales.merge(scoped, on=["order_id", "store_code"], how="inner")


def _load_cash_events(conn: sqlite3.Connection, *, as_of: date) -> pd.DataFrame:
    """Load cash events with a stable schema without assuming optional columns exist."""
    columns = [
        "event_date",
        "event_type",
        "amount_kzt",
        "store_code",
        "ref_type",
        "ref_id",
        "source",
        "notes",
    ]
    if not _relation_exists(conn, "fact_cashflow_events"):
        return pd.DataFrame(columns=columns)

    available = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(fact_cashflow_events)").fetchall()
    }
    required = {"event_date", "event_type", "amount_kzt", "store_code"}
    if not required.issubset(available):
        return pd.DataFrame(columns=columns)

    optional_expr = {
        "ref_type": "CAST(ref_type AS TEXT)" if "ref_type" in available else "NULL",
        "ref_id": "CAST(ref_id AS TEXT)" if "ref_id" in available else "NULL",
        "source": "CAST(source AS TEXT)" if "source" in available else "NULL",
        "notes": "CAST(notes AS TEXT)" if "notes" in available else "NULL",
    }
    return pd.read_sql_query(
        f"""
        SELECT
            date(event_date) AS event_date,
            UPPER(COALESCE(event_type, '')) AS event_type,
            COALESCE(amount_kzt, 0) AS amount_kzt,
            UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
            {optional_expr['ref_type']} AS ref_type,
            {optional_expr['ref_id']} AS ref_id,
            {optional_expr['source']} AS source,
            {optional_expr['notes']} AS notes
        FROM fact_cashflow_events
        WHERE date(event_date) <= ?
        """,
        conn,
        params=(as_of.isoformat(),),
    )


def _load_entry_scope(conn: sqlite3.Connection) -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Return unique current entry scopes and entry IDs whose identity is ambiguous."""
    required = {"entry_id", "order_id", "store_code"}
    if not _relation_exists(conn, "fact_order_entries_kaspi"):
        return {}, set()
    available = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(fact_order_entries_kaspi)").fetchall()
    }
    if not required.issubset(available):
        return {}, set()

    rows = pd.read_sql_query(
        """
        SELECT
            TRIM(CAST(entry_id AS TEXT)) AS entry_id,
            TRIM(CAST(order_id AS TEXT)) AS order_id,
            UPPER(TRIM(COALESCE(store_code, 'UNKNOWN'))) AS store_code
        FROM fact_order_entries_kaspi
        WHERE entry_id IS NOT NULL
          AND TRIM(CAST(entry_id AS TEXT)) <> ''
          AND order_id IS NOT NULL
          AND TRIM(CAST(order_id AS TEXT)) <> ''
        """,
        conn,
    )
    if rows.empty:
        return {}, set()

    scope: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for entry_id, group in rows.groupby("entry_id", sort=False):
        pairs = {
            (str(row.order_id).strip(), str(row.store_code).strip().upper())
            for row in group.itertuples(index=False)
        }
        if len(pairs) == 1:
            scope[str(entry_id)] = next(iter(pairs))
        else:
            ambiguous.add(str(entry_id))
    return scope, ambiguous


def _build_cash_reversal_evidence(
    *,
    returned: pd.DataFrame,
    cash_events: pd.DataFrame,
    entry_scope: dict[str, tuple[str, str]],
    ambiguous_entry_ids: set[str],
    cutoff: date,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Classify exact mature returned-order cash recognition and reversal evidence."""
    columns = [
        "order_id",
        "store_code",
        "return_date",
        "classification",
        "positive_cash_events",
        "positive_cash_kzt",
        "cash_reversal_events",
        "cash_reversal_kzt",
    ]
    if returned.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(), {
            "unscoped_reversal_events": 0,
            "scope_mismatch_events": 0,
            "ambiguous_entry_reference_events": 0,
        }

    scoped_returns = returned.copy()
    scoped_returns["order_id"] = scoped_returns["order_id"].astype(str).str.strip()
    scoped_returns["store_code"] = scoped_returns["store_code"].astype(str).str.strip().str.upper()
    scoped_returns["return_date"] = pd.to_datetime(
        scoped_returns["return_date"], errors="coerce"
    ).dt.date
    # A duplicated order row can carry several source timestamps. The latest
    # return observation is the conservative maturity boundary for that exact
    # order/store identity.
    scoped_returns = scoped_returns[
        scoped_returns["order_id"].ne("") & scoped_returns["return_date"].notna()
    ].copy()
    scoped_returns = (
        scoped_returns.groupby(["order_id", "store_code"], as_index=False)
        .agg(return_date=("return_date", "max"))
        .sort_values(["return_date", "store_code", "order_id"])
    )
    scoped_returns = scoped_returns[scoped_returns["return_date"] <= cutoff].copy()
    if scoped_returns.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(), {
            "unscoped_reversal_events": 0,
            "scope_mismatch_events": 0,
            "ambiguous_entry_reference_events": 0,
        }

    metrics: dict[tuple[str, str], dict[str, float | int]] = {}
    diagnostics = {
        "unscoped_reversal_events": 0,
        "scope_mismatch_events": 0,
        "ambiguous_entry_reference_events": 0,
    }
    cash = cash_events.copy()
    if not cash.empty:
        cash["event_date"] = pd.to_datetime(cash["event_date"], errors="coerce").dt.date
        cash["event_type"] = cash["event_type"].fillna("").astype(str).str.strip().str.upper()
        cash["amount_kzt"] = pd.to_numeric(cash["amount_kzt"], errors="coerce").fillna(0.0)
        cash["store_code"] = cash["store_code"].fillna("UNKNOWN").astype(str).str.strip().str.upper()
        cash["ref_type"] = cash["ref_type"].fillna("").astype(str).str.strip().str.upper()
        cash["ref_id"] = cash["ref_id"].fillna("").astype(str).str.strip()
        cash["source"] = cash["source"].fillna("").astype(str).str.strip().str.upper()
        cash["notes"] = cash["notes"].fillna("").astype(str)

        for event in cash.itertuples(index=False):
            amount = float(event.amount_kzt)
            positive_cash = event.event_type == "CASH_IN" and amount > 0
            repair_correction = (
                event.event_type == "CASH_IN"
                and amount < 0
                and event.source == "ORDER_CASH_REPAIR"
                and "supersedes_cash_id=" in event.notes.lower()
            )
            cash_reversal = (
                event.event_type == "REFUND"
                or (event.event_type == "CASH_IN" and amount < 0 and not repair_correction)
            )
            if not positive_cash and not cash_reversal:
                continue

            key: tuple[str, str] | None = None
            if event.ref_type == "ORDER" and event.ref_id:
                key = (event.ref_id, event.store_code)
            elif event.ref_type == "ORDER_ENTRY" and event.ref_id:
                if event.ref_id in ambiguous_entry_ids:
                    diagnostics["ambiguous_entry_reference_events"] += 1
                elif event.ref_id in entry_scope:
                    mapped_order, mapped_store = entry_scope[event.ref_id]
                    if event.store_code == mapped_store:
                        key = (mapped_order, mapped_store)
                    else:
                        diagnostics["scope_mismatch_events"] += 1

            if key is None:
                if cash_reversal:
                    diagnostics["unscoped_reversal_events"] += 1
                continue

            bucket = metrics.setdefault(
                key,
                {
                    "positive_cash_events": 0,
                    "positive_cash_kzt": 0.0,
                    "cash_reversal_events": 0,
                    "cash_reversal_kzt": 0.0,
                },
            )
            if positive_cash:
                bucket["positive_cash_events"] = int(bucket["positive_cash_events"]) + 1
                bucket["positive_cash_kzt"] = float(bucket["positive_cash_kzt"]) + amount
            if cash_reversal:
                bucket["cash_reversal_events"] = int(bucket["cash_reversal_events"]) + 1
                bucket["cash_reversal_kzt"] = float(bucket["cash_reversal_kzt"]) + amount

    evidence_rows: list[dict[str, Any]] = []
    for row in scoped_returns.itertuples(index=False):
        key = (str(row.order_id), str(row.store_code))
        values = metrics.get(
            key,
            {
                "positive_cash_events": 0,
                "positive_cash_kzt": 0.0,
                "cash_reversal_events": 0,
                "cash_reversal_kzt": 0.0,
            },
        )
        positive_count = int(values["positive_cash_events"])
        reversal_count = int(values["cash_reversal_events"])
        if positive_count == 0:
            classification = "NO_RECOGNIZED_CASH_TO_REVERSE"
        elif reversal_count > 0:
            classification = "CASH_REVERSAL_COVERED"
        else:
            classification = "MISSING_CASH_REVERSAL"
        evidence_rows.append(
            {
                "order_id": key[0],
                "store_code": key[1],
                "return_date": row.return_date.isoformat(),
                "classification": classification,
                "positive_cash_events": positive_count,
                "positive_cash_kzt": round(float(values["positive_cash_kzt"]), 2),
                "cash_reversal_events": reversal_count,
                "cash_reversal_kzt": round(float(values["cash_reversal_kzt"]), 2),
            }
        )

    evidence = pd.DataFrame(evidence_rows, columns=columns)
    reversal_events = cash.copy()
    if not reversal_events.empty:
        repair_mask = (
            reversal_events["event_type"].eq("CASH_IN")
            & reversal_events["amount_kzt"].lt(0)
            & reversal_events["source"].eq("ORDER_CASH_REPAIR")
            & reversal_events["notes"].str.lower().str.contains(
                "supersedes_cash_id=", regex=False, na=False
            )
        )
        reversal_events = reversal_events[
            reversal_events["event_type"].eq("REFUND")
            | (
                reversal_events["event_type"].eq("CASH_IN")
                & reversal_events["amount_kzt"].lt(0)
                & ~repair_mask
            )
        ].copy()
    return evidence, reversal_events, diagnostics


def validate_returns_economics_audit(
    *,
    db_path: Path,
    as_of: date,
    since: date,
    output_root: Path,
    volatility_days: int,
    strict: bool,
) -> dict[str, Any]:
    if since > as_of:
        raise ReturnsEconomicsError("since must be <= as_of")
    if volatility_days < 0:
        raise ReturnsEconomicsError("volatility_days must be >= 0")
    if not db_path.exists():
        raise ReturnsEconomicsError(f"db not found: {db_path}")

    with validation_db_copy(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_sales_truth_views(conn)
        returned = pd.read_sql_query(
            """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS store_code,
                date(COALESCE(status_updated_at, updated_at, created_at)) AS return_date,
                UPPER(COALESCE(internal_status, '')) AS internal_status
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, updated_at, created_at)) BETWEEN ? AND ?
              AND UPPER(COALESCE(internal_status, '')) = 'RETURNED'
            """,
            conn,
            params=(since.isoformat(), as_of.isoformat()),
        )

        leaked = _load_leaked_sales_for_returned_orders(conn, returned=returned, as_of=as_of)

        cash_events = _load_cash_events(conn, as_of=as_of)
        entry_scope, ambiguous_entry_ids = _load_entry_scope(conn)

    now_cutoff = as_of - timedelta(days=int(volatility_days))

    reversal_evidence, reversal_events, cash_diagnostics = _build_cash_reversal_evidence(
        returned=returned,
        cash_events=cash_events,
        entry_scope=entry_scope,
        ambiguous_entry_ids=ambiguous_entry_ids,
        cutoff=now_cutoff,
    )

    if leaked.empty:
        leaked = pd.DataFrame(columns=["order_id", "store_code", "sale_date", "return_date", "source_table"])
    leaked["return_date"] = pd.to_datetime(leaked["return_date"], errors="coerce").dt.date
    leaked["sale_date"] = pd.to_datetime(leaked["sale_date"], errors="coerce").dt.date
    stale_leaks = leaked[leaked["return_date"].notna() & (leaked["return_date"] <= now_cutoff)].copy()

    returned_monthly = pd.DataFrame()
    if not returned.empty:
        returned["return_date"] = pd.to_datetime(returned["return_date"], errors="coerce").dt.date
        returned = returned[returned["return_date"].notna()].copy()
        returned["sale_month"] = pd.to_datetime(returned["return_date"]).dt.to_period("M").astype(str)
        returned_monthly = (
            returned.groupby("sale_month", dropna=False)
            .agg(returned_orders=("order_id", "nunique"))
            .reset_index()
            .sort_values("sale_month")
        )
    else:
        returned_monthly = pd.DataFrame(columns=["sale_month", "returned_orders"])

    refunds = pd.DataFrame(columns=["sale_month", "refund_events", "refund_amount_kzt"])
    if not reversal_events.empty:
        reversal_events = reversal_events[
            reversal_events["event_date"].notna()
            & (reversal_events["event_date"] >= since)
            & (reversal_events["event_date"] <= as_of)
        ].copy()
        if not reversal_events.empty:
            reversal_events["sale_month"] = pd.to_datetime(
                reversal_events["event_date"]
            ).dt.to_period("M").astype(str)
            refunds = (
                reversal_events.groupby("sale_month", dropna=False)
                .agg(
                    refund_events=("event_type", "size"),
                    refund_amount_kzt=("amount_kzt", "sum"),
                )
                .reset_index()
                .sort_values("sale_month")
            )
            refunds["refund_amount_kzt"] = refunds["refund_amount_kzt"].round(2)

    monthly = returned_monthly.merge(refunds, on="sale_month", how="left")
    if "refund_events" not in monthly.columns:
        monthly["refund_events"] = 0
    monthly["refund_events"] = pd.to_numeric(monthly["refund_events"], errors="coerce").fillna(0).astype(int)
    if "refund_amount_kzt" not in monthly.columns:
        monthly["refund_amount_kzt"] = 0.0
    monthly["refund_amount_kzt"] = (
        pd.to_numeric(monthly["refund_amount_kzt"], errors="coerce").fillna(0.0).round(2)
    )

    months_missing_refunds: list[str] = []
    for _, row in monthly.iterrows():
        month = str(row.get("sale_month") or "")
        if not month:
            continue
        year, mon = month.split("-")
        month_end = date(int(year), int(mon), 1)
        if mon == "12":
            month_end = date(int(year) + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(int(year), int(mon) + 1, 1) - timedelta(days=1)
        if month_end > now_cutoff:
            continue
        if int(row.get("returned_orders") or 0) > 0 and int(row.get("refund_events") or 0) == 0:
            months_missing_refunds.append(month)

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    error_codes: list[str] = []

    checks.append(
        {
            "check": "returned_orders_present",
            "ok": True,
            "details": f"returned_orders={int(returned['order_id'].nunique()) if not returned.empty else 0}",
        }
    )

    stale_leak_count = int(stale_leaks["order_id"].nunique()) if not stale_leaks.empty else 0
    stale_ok = stale_leak_count == 0
    checks.append(
        {
            "check": "stale_return_leak",
            "ok": stale_ok,
            "details": f"stale_leaked_orders={stale_leak_count} cutoff={now_cutoff.isoformat()}",
        }
    )
    if not stale_ok:
        error_codes.append("RETURNS_LEAK_STALE")
        errors.append(
            f"{stale_leak_count} returned order(s) still present in delivered sales beyond {volatility_days}d window"
        )

    cash_reversal_required = int(
        reversal_evidence["classification"].isin(
            ["CASH_REVERSAL_COVERED", "MISSING_CASH_REVERSAL"]
        ).sum()
    ) if not reversal_evidence.empty else 0
    cash_reversal_covered = int(
        reversal_evidence["classification"].eq("CASH_REVERSAL_COVERED").sum()
    ) if not reversal_evidence.empty else 0
    missing_cash_reversal = int(
        reversal_evidence["classification"].eq("MISSING_CASH_REVERSAL").sum()
    ) if not reversal_evidence.empty else 0
    no_cash_to_reverse = int(
        reversal_evidence["classification"].eq("NO_RECOGNIZED_CASH_TO_REVERSE").sum()
    ) if not reversal_evidence.empty else 0
    cash_reversal_ok = missing_cash_reversal == 0
    checks.append(
        {
            "check": "order_cash_reversal_presence",
            "ok": cash_reversal_ok,
            "details": (
                f"required={cash_reversal_required} covered={cash_reversal_covered} "
                f"no_recognized_cash={no_cash_to_reverse} missing={missing_cash_reversal}"
            ),
        }
    )
    if not cash_reversal_ok:
        error_codes.append("RETURNS_CASH_REVERSAL_GAP")
        errors.append(
            f"{missing_cash_reversal} mature returned order(s) have positive recognized cash "
            "without an exact linked cash reversal"
        )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    stale_leaks_csv = out_dir / "stale_leak_orders.csv"
    reversal_rows_csv = out_dir / "return_cash_reversal_rows.csv"
    monthly_csv = out_dir / "monthly_returns.csv"
    stale_leaks.to_csv(stale_leaks_csv, index=False, encoding="utf-8")
    reversal_evidence.to_csv(reversal_rows_csv, index=False, encoding="utf-8")
    monthly.to_csv(monthly_csv, index=False, encoding="utf-8")

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "since": since.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "checks": checks,
        "volatility_days": int(volatility_days),
        "db_path": str(db_path.resolve()),
        "returned_orders": int(returned["order_id"].nunique()) if not returned.empty else 0,
        "mature_returned_orders": int(len(reversal_evidence)),
        "stale_leaked_orders": stale_leak_count,
        "cash_reversal_required_orders": cash_reversal_required,
        "cash_reversal_covered_orders": cash_reversal_covered,
        "missing_cash_reversal_orders": missing_cash_reversal,
        "no_recognized_cash_to_reverse_orders": no_cash_to_reverse,
        "unscoped_reversal_events": cash_diagnostics["unscoped_reversal_events"],
        "cash_scope_mismatch_events": cash_diagnostics["scope_mismatch_events"],
        "ambiguous_order_entry_reference_events": cash_diagnostics[
            "ambiguous_entry_reference_events"
        ],
        "months_missing_refunds": months_missing_refunds,
        "stale_leak_orders_csv": str(stale_leaks_csv),
        "return_cash_reversal_rows_csv": str(reversal_rows_csv),
        "monthly_returns_csv": str(monthly_csv),
    }

    json_path = out_dir / "returns_economics_report.json"
    md_path = out_dir / "returns_economics_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise ReturnsEconomicsError("returns economics audit failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate returned-order economics drift")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--volatility-days", type=int, default=14)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    since = date.fromisoformat(str(args.since)) if args.since else (as_of - timedelta(days=90))
    try:
        report = validate_returns_economics_audit(
            db_path=args.db,
            as_of=as_of,
            since=since,
            output_root=args.output_root,
            volatility_days=int(args.volatility_days),
            strict=bool(args.strict),
        )
    except ReturnsEconomicsError as exc:
        print("status=FAIL")
        print("error_code=RETURNS_ECONOMICS_FAIL")
        print(f"message={exc}")
        return 1

    print(f"returns_economics_json={report['json_path']}")
    print(f"returns_economics_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
