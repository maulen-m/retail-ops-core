#!/usr/bin/env python3
"""Validate monthly economics reconciliation against cashflow events."""

from __future__ import annotations

import argparse
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import calc_net_rev  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "cash_reconciliation"
DEFAULT_STATUSDATE_CUTOVER = date(2026, 2, 27)
DEFAULT_TOLERANCE_FRACTION = 0.01
FORMULA_AMOUNT_TOLERANCE_KZT = Decimal("0.01")
SOURCE_UNITS_TOLERANCE = Decimal("0.0001")


class CashReconciliationError(RuntimeError):
    """Raised when strict cash reconciliation fails."""


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _object_exists(conn: sqlite3.Connection, object_type: str, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
            (object_type, name),
        ).fetchone()
        is not None
    )


def _paths_collide(left: Path, right: Path) -> bool:
    left_resolved = left.expanduser().resolve()
    right_resolved = right.expanduser().resolve()
    if left_resolved == right_resolved:
        return True
    try:
        return left_resolved.exists() and right_resolved.exists() and left_resolved.samefile(right_resolved)
    except OSError:
        return False


def _month_end(month_key: str) -> date:
    y, m = month_key.split("-")
    yy, mm = int(y), int(m)
    return date(yy, mm, monthrange(yy, mm)[1])


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _decimal_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _absolute_decimal_difference(left: Any, right: Any) -> Decimal | None:
    left_decimal = _decimal_value(left)
    right_decimal = _decimal_value(right)
    if left_decimal is None or right_decimal is None:
        return None
    return abs(left_decimal - right_decimal)


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _neutralized_unmapped_order_entry_events(
    cash_events: pd.DataFrame,
) -> tuple[set[int], list[dict[str, Any]]]:
    """Return only exact append-only neutralization pairs for missing recovered refs."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for raw in cash_events.to_dict(orient="records"):
        if _safe_text(raw.get("ref_type")).upper() != "ORDER_ENTRY":
            continue
        if _safe_text(raw.get("order_id")):
            continue
        ref_id = _safe_text(raw.get("ref_id"))
        if not ref_id.startswith(("RECOV-CURRENT_CRM-", "RECOV-WORKBOOK-")):
            continue
        groups.setdefault(ref_id, []).append(raw)

    neutralized_ids: set[int] = set()
    evidence: list[dict[str, Any]] = []
    hash_pattern = re.compile(r"^[0-9a-f]{64}$")
    order_pattern = re.compile(r"(?:^|[;\s])order_id=(\d+)(?:$|[;\s])")
    supersedes_pattern = re.compile(r"(?:^|[;\s])supersedes_cash_id=(\d+)(?:$|[;\s])")

    for ref_id, rows in sorted(groups.items()):
        if len(rows) != 2:
            continue
        positive = [row for row in rows if _safe_float(row.get("amount_kzt")) > 0]
        negative = [row for row in rows if _safe_float(row.get("amount_kzt")) < 0]
        if len(positive) != 1 or len(negative) != 1:
            continue
        positive_row = positive[0]
        negative_row = negative[0]
        positive_id = int(positive_row["event_id"])
        negative_id = int(negative_row["event_id"])
        if abs(_safe_float(positive_row["amount_kzt"]) + _safe_float(negative_row["amount_kzt"])) > 0.01:
            continue
        identity_fields = (
            "raw_event_date",
            "event_store_code",
            "ref_id",
            "sku_key",
            "sku_id",
        )
        if any(
            _safe_text(positive_row.get(field)) != _safe_text(negative_row.get(field))
            for field in identity_fields
        ):
            continue
        if _safe_text(positive_row.get("source")).upper() != "ORDER_MODELLED":
            continue
        if _safe_text(negative_row.get("source")).upper() != "ORDER_IDENTITY_REPAIR":
            continue
        positive_run = _safe_text(positive_row.get("run_id"))
        negative_run = _safe_text(negative_row.get("run_id"))
        hashes = {
            _safe_text(positive_row.get("event_hash")).lower(),
            _safe_text(negative_row.get("event_hash")).lower(),
        }
        if not positive_run or not negative_run or len(hashes) != 2 or not all(
            hash_pattern.fullmatch(value) for value in hashes
        ):
            continue
        positive_notes = _safe_text(positive_row.get("notes"))
        negative_notes = _safe_text(negative_row.get("notes"))
        positive_order = order_pattern.search(positive_notes)
        negative_order = order_pattern.search(negative_notes)
        supersedes = supersedes_pattern.search(negative_notes)
        if (
            not positive_order
            or not negative_order
            or positive_order.group(1) != negative_order.group(1)
            or not supersedes
            or int(supersedes.group(1)) != positive_id
            or not negative_notes.startswith("exact recovered-entry reversal;")
        ):
            continue
        neutralized_ids.update((positive_id, negative_id))
        evidence.append(
            {
                "ref_id": ref_id,
                "order_id": positive_order.group(1),
                "positive_event_id": positive_id,
                "reversal_event_id": negative_id,
                "event_date": _safe_text(positive_row.get("event_date")),
                "store_code": _safe_text(positive_row.get("event_store_code")),
                "net_amount_kzt": round(
                    _safe_float(positive_row["amount_kzt"])
                    + _safe_float(negative_row["amount_kzt"]),
                    2,
                ),
            }
        )
    return neutralized_ids, evidence


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _sales_amount_formula_proof(
    conn: sqlite3.Connection,
    *,
    since: date,
    until: date,
) -> tuple[bool, dict[tuple[str, str], dict[str, Any]]]:
    if not _object_exists(conn, "view", "view_sales_line_truth"):
        return False, {}
    view_required = {
        "order_id",
        "sale_date",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "units",
        "net_rev_kzt",
        "source_table",
        "source_sku_key",
        "source_sku_id",
        "source_units",
        "source_net_rev_kzt",
    }
    view_columns = _table_columns(conn, "view_sales_line_truth")
    if not view_required.issubset(view_columns):
        return False, {}

    selected_source_date_expr = (
        "date(source_sale_date)" if "source_sale_date" in view_columns else "date(sale_date)"
    )
    selected_source_row_id_expr = (
        "CAST(COALESCE(source_row_id, '') AS TEXT)"
        if "source_row_id" in view_columns
        else "''"
    )
    selected_binding_status_expr = (
        "CAST(COALESCE(publication_binding_status, 'UNBOUND') AS TEXT)"
        if "publication_binding_status" in view_columns
        else "'LEGACY_VIEW'"
    )
    selected_provisional_expr = (
        "CAST(COALESCE(publication_provisional_flag, 0) AS INTEGER)"
        if "publication_provisional_flag" in view_columns
        else "0"
    )

    selected_rows = conn.execute(
        """
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            date(sale_date) AS sale_date,
            UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
            LOWER(TRIM(COALESCE(source_table, ''))) AS source_table,
            CAST(COALESCE(source_sku_key, '') AS TEXT) AS source_sku_key,
            CAST(COALESCE(source_sku_id, '') AS TEXT) AS source_sku_id,
            CAST(COALESCE(my_size, '') AS TEXT) AS my_size,
            {selected_source_date_expr} AS source_sale_date,
            {selected_source_row_id_expr} AS source_row_id,
            {selected_binding_status_expr} AS publication_binding_status,
            {selected_provisional_expr} AS publication_provisional_flag,
            source_units,
            source_net_rev_kzt,
            units AS published_units,
            net_rev_kzt AS published_net_rev_kzt
        FROM view_sales_line_truth
        WHERE date(sale_date) BETWEEN ? AND ?
        ORDER BY
            CAST(order_id AS TEXT),
            UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))),
            LOWER(TRIM(COALESCE(source_table, ''))),
            date(sale_date),
            CAST(COALESCE(source_sku_key, '') AS TEXT),
            CAST(COALESCE(source_sku_id, '') AS TEXT),
            CAST(COALESCE(my_size, '') AS TEXT),
            source_units,
            source_net_rev_kzt,
            units,
            net_rev_kzt
        """.format(
            selected_source_date_expr=selected_source_date_expr,
            selected_source_row_id_expr=selected_source_row_id_expr,
            selected_binding_status_expr=selected_binding_status_expr,
            selected_provisional_expr=selected_provisional_expr,
        ),
        (since.isoformat(), until.isoformat()),
    ).fetchall()
    selected_sources = {_safe_text(row["source_table"]).lower() for row in selected_rows}
    supported_sources = {"sales_fact_v2", "fact_sales"}
    if selected_sources - supported_sources:
        return False, {}

    v2_required = {
        "order_id",
        "order_date",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "sell_price_kzt",
        "delivery_fee",
        "net_rev",
        "status",
        "return_flag",
    }
    fact_required = {
        "order_id",
        "order_date",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "sell_price_kzt",
        "delivery_fee",
        "line_net_rev",
    }
    if "sales_fact_v2" in selected_sources and (
        not _object_exists(conn, "table", "sales_fact_v2")
        or not v2_required.issubset(_table_columns(conn, "sales_fact_v2"))
    ):
        return False, {}
    if "fact_sales" in selected_sources and (
        not _object_exists(conn, "table", "fact_sales")
        or not fact_required.issubset(_table_columns(conn, "fact_sales"))
    ):
        return False, {}

    rows: list[sqlite3.Row] = []
    if "sales_fact_v2" in selected_sources:
        v2_source_row_id_expr = (
            "CAST(sales.sale_id AS TEXT)"
            if "sale_id" in _table_columns(conn, "sales_fact_v2")
            else "CAST(sales.rowid AS TEXT)"
        )
        rows.extend(
            conn.execute(
                f"""
                WITH selected AS (
                    SELECT DISTINCT
                        CAST(order_id AS TEXT) AS order_id,
                        UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code
                    FROM view_sales_line_truth
                    WHERE date(sale_date) BETWEEN ? AND ?
                      AND LOWER(TRIM(COALESCE(source_table, ''))) = 'sales_fact_v2'
                )
                SELECT
                    sales.order_id,
                    sales.order_date,
                    {v2_source_row_id_expr} AS source_row_id,
                    UPPER(TRIM(COALESCE(sales.store_code, 'UNIVERSAL'))) AS store_code,
                    CAST(COALESCE(sales.sku_key, '') AS TEXT) AS source_sku_key,
                    CAST(COALESCE(sales.sku_id, '') AS TEXT) AS source_sku_id,
                    CAST(COALESCE(sales.my_size, '') AS TEXT) AS my_size,
                    sales.quantity,
                    sales.sell_price_kzt,
                    sales.delivery_fee,
                    sales.net_rev,
                    0 AS delivery_fee_is_unit,
                    'sales_fact_v2' AS source_table
                FROM sales_fact_v2 AS sales
                JOIN selected
                  ON selected.order_id = CAST(sales.order_id AS TEXT)
                 AND selected.store_code = UPPER(TRIM(COALESCE(sales.store_code, 'UNIVERSAL')))
                WHERE UPPER(COALESCE(sales.status, 'DELIVERED')) = 'DELIVERED'
                  AND COALESCE(sales.return_flag, 0) = 0
                """,
                (
                    since.isoformat(),
                    until.isoformat(),
                ),
            ).fetchall()
        )
    if "fact_sales" in selected_sources:
        fact_source_row_id_expr = (
            "CAST(sales.id AS TEXT)"
            if "id" in _table_columns(conn, "fact_sales")
            else "CAST(sales.rowid AS TEXT)"
        )
        rows.extend(
            conn.execute(
                f"""
                WITH selected AS (
                    SELECT DISTINCT
                        CAST(order_id AS TEXT) AS order_id,
                        UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code
                    FROM view_sales_line_truth
                    WHERE date(sale_date) BETWEEN ? AND ?
                      AND LOWER(TRIM(COALESCE(source_table, ''))) = 'fact_sales'
                )
                SELECT
                    sales.order_id,
                    sales.order_date,
                    {fact_source_row_id_expr} AS source_row_id,
                    UPPER(TRIM(COALESCE(sales.store_code, 'UNIVERSAL'))) AS store_code,
                    CAST(COALESCE(sales.sku_key, '') AS TEXT) AS source_sku_key,
                    CAST(COALESCE(sales.sku_id, '') AS TEXT) AS source_sku_id,
                    CAST(COALESCE(sales.my_size, '') AS TEXT) AS my_size,
                    sales.quantity,
                    sales.sell_price_kzt,
                    sales.delivery_fee,
                    sales.line_net_rev AS net_rev,
                    1 AS delivery_fee_is_unit,
                    'fact_sales' AS source_table
                FROM fact_sales AS sales
                JOIN selected
                  ON selected.order_id = CAST(sales.order_id AS TEXT)
                 AND selected.store_code = UPPER(TRIM(COALESCE(sales.store_code, 'UNIVERSAL')))
                """,
                (
                    since.isoformat(),
                    until.isoformat(),
                ),
            ).fetchall()
        )

    def line_key(
        *,
        order_id: str,
        store_code: str,
        source_table: str,
        source_date: str,
        source_sku_key: str,
        source_sku_id: str,
        my_size: str,
        source_units: float | None,
        source_net_rev_kzt: float | None,
    ) -> tuple[Any, ...] | None:
        if (
            not order_id
            or not store_code
            or not source_table
            or not source_date
            or source_units is None
            or source_net_rev_kzt is None
        ):
            return None
        return (
            order_id,
            store_code,
            source_table,
            source_date,
            source_sku_key,
            source_sku_id,
            my_size,
            _decimal_value(source_units),
            _decimal_value(source_net_rev_kzt),
        )

    binding_formula_dates: dict[tuple[str, str], str] = {}
    binding_formula_date_conflicts: set[tuple[str, str]] = set()
    for row in selected_rows:
        status = _safe_text(row["publication_binding_status"]).upper()
        provisional = int(row["publication_provisional_flag"] or 0)
        source_row_id = _safe_text(row["source_row_id"])
        source_table = _safe_text(row["source_table"]).lower()
        effective_date = _safe_text(row["sale_date"])[:10]
        if status != "VALID_ACTIVE" or provisional != 0 or not source_row_id or not effective_date:
            continue
        source_identity = (source_table, source_row_id)
        prior = binding_formula_dates.get(source_identity)
        if prior is not None and prior != effective_date:
            binding_formula_date_conflicts.add(source_identity)
        binding_formula_dates[source_identity] = effective_date

    source_rows_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    source_counts_by_order_store: dict[tuple[str, str], Counter[tuple[Any, ...]]] = {}
    invalid_source_line_count_by_order_store: Counter[tuple[str, str]] = Counter()
    for row in rows:
        order_id = _safe_text(row["order_id"])
        store_code = (_safe_text(row["store_code"]) or "UNKNOWN").upper()
        source_table = _safe_text(row["source_table"]).lower()
        source_row_id = _safe_text(row["source_row_id"])
        source_units = _optional_float(row["quantity"])
        source_net_rev = _optional_float(row["net_rev"])
        raw_source_date = _safe_text(row["order_date"])[:10]
        key = line_key(
            order_id=order_id,
            store_code=store_code,
            source_table=source_table,
            source_date=raw_source_date,
            source_sku_key=_safe_text(row["source_sku_key"]),
            source_sku_id=_safe_text(row["source_sku_id"]),
            my_size=_safe_text(row["my_size"]),
            source_units=source_units,
            source_net_rev_kzt=source_net_rev,
        )
        quantity = _optional_float(row["quantity"])
        sell_price = _optional_float(row["sell_price_kzt"])
        stored_net = _optional_float(row["net_rev"])
        delivery_total = _optional_float(row["delivery_fee"])
        source_identity = (source_table, source_row_id)
        formula_date_text = binding_formula_dates.get(source_identity, raw_source_date)
        try:
            order_date = date.fromisoformat(formula_date_text)
        except ValueError:
            order_date = None
        formula_proven = False
        abs_diff = 0.0
        if (
            order_id
            and quantity is not None
            and quantity > 0
            and sell_price is not None
            and order_date is not None
            and stored_net is not None
        ):
            delivery_unit = (
                delivery_total
                if delivery_total is not None and bool(row["delivery_fee_is_unit"])
                else delivery_total / quantity
                if delivery_total is not None
                else None
            )
            canonical_net = round(
                calc_net_rev(
                    sell_price,
                    delivery_fee=delivery_unit,
                    as_of_date=order_date,
                )
                * quantity,
                2,
            )
            raw_abs_diff = _absolute_decimal_difference(stored_net, canonical_net)
            abs_diff = float(raw_abs_diff) if raw_abs_diff is not None else 0.0
            formula_proven = bool(
                raw_abs_diff is not None
                and raw_abs_diff <= FORMULA_AMOUNT_TOLERANCE_KZT
                and source_identity not in binding_formula_date_conflicts
            )
        order_store = (order_id, store_code)
        if key is not None:
            source_rows_by_key.setdefault(key, []).append(
                {"formula_proven": formula_proven, "abs_diff_kzt": abs_diff}
            )
            source_counts_by_order_store.setdefault(
                order_store, Counter()
            )[key] += 1
        else:
            invalid_source_line_count_by_order_store[order_store] += 1

    proof: dict[tuple[str, str], dict[str, Any]] = {}
    selected_counts_by_order_store: dict[
        tuple[str, str], Counter[tuple[Any, ...]]
    ] = {}
    for row in selected_rows:
        order_id = _safe_text(row["order_id"])
        store_code = (_safe_text(row["store_code"]) or "UNKNOWN").upper()
        order_store = (order_id, store_code)
        state = proof.setdefault(
            order_store,
            {
                "line_count": 0,
                "unproven_line_count": 0,
                "max_abs_diff_kzt": 0.0,
                "published_source_mismatch_line_count": 0,
                "max_published_source_abs_diff_kzt": 0.0,
                "source_multiset_mismatch_line_count": 0,
            },
        )
        state["line_count"] += 1
        source_units = _optional_float(row["source_units"])
        published_units = _optional_float(row["published_units"])
        source_net_rev = _optional_float(row["source_net_rev_kzt"])
        published_net_rev = _optional_float(row["published_net_rev_kzt"])
        published_sale_date = _safe_text(row["sale_date"])[:10]
        source_sale_date = _safe_text(row["source_sale_date"])[:10]
        publication_binding_status = _safe_text(
            row["publication_binding_status"]
        ).upper()
        publication_provisional = int(row["publication_provisional_flag"] or 0)
        published_source_raw_abs_diff = _absolute_decimal_difference(
            published_net_rev,
            source_net_rev,
        )
        published_source_abs_diff = (
            float(published_source_raw_abs_diff)
            if published_source_raw_abs_diff is not None
            else 0.0
        )
        published_source_units_abs_diff = _absolute_decimal_difference(
            published_units,
            source_units,
        )
        state["max_published_source_abs_diff_kzt"] = max(
            float(state["max_published_source_abs_diff_kzt"]),
            published_source_abs_diff,
        )
        published_source_mismatch = bool(
            source_units is None
            or published_units is None
            or source_net_rev is None
            or published_net_rev is None
            or published_source_units_abs_diff is None
            or published_source_units_abs_diff > SOURCE_UNITS_TOLERANCE
            or published_source_raw_abs_diff is None
            or published_source_raw_abs_diff > FORMULA_AMOUNT_TOLERANCE_KZT
            or publication_provisional != 0
            or publication_binding_status.startswith("INVALID_ACTIVE")
        )
        if published_source_mismatch:
            state["published_source_mismatch_line_count"] += 1
        key = line_key(
            order_id=order_id,
            store_code=store_code,
            source_table=_safe_text(row["source_table"]).lower(),
            source_date=(
                source_sale_date
                if publication_binding_status == "VALID_ACTIVE"
                and publication_provisional == 0
                else published_sale_date
            ),
            source_sku_key=_safe_text(row["source_sku_key"]),
            source_sku_id=_safe_text(row["source_sku_id"]),
            my_size=_safe_text(row["my_size"]),
            source_units=source_units,
            source_net_rev_kzt=source_net_rev,
        )
        if key is not None:
            selected_counts_by_order_store.setdefault(order_store, Counter())[key] += 1
        else:
            state["source_multiset_mismatch_line_count"] += 1

    for order_store, state in proof.items():
        selected_counts = selected_counts_by_order_store.get(order_store, Counter())
        source_counts = source_counts_by_order_store.get(order_store, Counter())
        all_keys = set(selected_counts) | set(source_counts)
        invalid_source_line_count = int(
            invalid_source_line_count_by_order_store.get(order_store, 0)
        )
        multiset_mismatch_count = (
            int(state["source_multiset_mismatch_line_count"])
            + invalid_source_line_count
        )
        formula_unproven_line_count = 0
        max_formula_abs_diff = 0.0
        for key in all_keys:
            selected_count = int(selected_counts.get(key, 0))
            source_count = int(source_counts.get(key, 0))
            if selected_count != source_count:
                multiset_mismatch_count += abs(selected_count - source_count)
            source_evidence = source_rows_by_key.get(key, [])
            max_formula_abs_diff = max(
                max_formula_abs_diff,
                max(
                    (float(item["abs_diff_kzt"]) for item in source_evidence),
                    default=0.0,
                ),
            )
            formula_unproven_line_count += sum(
                not bool(item["formula_proven"])
                for item in source_evidence[: min(selected_count, source_count)]
            )
        state["source_multiset_mismatch_line_count"] = multiset_mismatch_count
        state["max_abs_diff_kzt"] = max_formula_abs_diff
        source_formula_evidence = [
            item
            for key in source_counts
            for item in source_rows_by_key.get(key, [])
        ]
        state["source_formula_line_count"] = (
            len(source_formula_evidence) + invalid_source_line_count
        )
        state["source_formula_invalid_line_count"] = invalid_source_line_count
        state["source_formula_unproven_line_count"] = sum(
            not bool(item["formula_proven"])
            for item in source_formula_evidence
        ) + invalid_source_line_count
        state["source_formula_proven"] = bool(
            source_formula_evidence
            and state["source_formula_unproven_line_count"] == 0
        )
        state["publication_binding_unproven_line_count"] = (
            int(state["published_source_mismatch_line_count"])
            + multiset_mismatch_count
        )
        state["publication_binding_proven"] = bool(
            state["line_count"] > 0
            and state["publication_binding_unproven_line_count"] == 0
        )
        state["unproven_line_count"] = (
            int(state["published_source_mismatch_line_count"])
            + formula_unproven_line_count
            + multiset_mismatch_count
        )
        state["source_multiset_matches"] = multiset_mismatch_count == 0
        state["proven"] = bool(
            state["line_count"] > 0 and state["unproven_line_count"] == 0
        )
    return True, proof


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Monthly Cash Reconciliation",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- range: `{report['since']} -> {report['until']}`",
        f"- status: `{report['status']}`",
        f"- error_code: `{report.get('error_code') or 'none'}`",
        f"- tolerance_pct: `{report['tolerance_pct']}`",
        f"- statusdate_cutover: `{report['statusdate_cutover']}`",
        f"- decision_grade_pairs: `{report['decision_grade_pairs']}`",
        f"- covered_pairs: `{report['covered_pairs']}`",
        f"- uncovered_decision_grade_pairs: `{report['uncovered_decision_grade_pairs']}`",
        f"- sales_orders: `{report['sales_order_count']}`",
        f"- cash_resolution_all_scope: `ORDER_ENTRY={report['order_entry_resolution_count']}, ORDER={report['order_fallback_resolution_count']}, AMBIGUOUS_ENTRY={report['ambiguous_entry_resolution_count']}, MISSING={report['missing_cash_order_count']}`",
        f"- decision_grade_missing_cash_orders: `{report['decision_grade_missing_cash_order_count']}`",
        f"- decision_grade_ambiguous_entry_orders: `{report['decision_grade_ambiguous_entry_order_count']}`",
        f"- duplicate_chosen_cash_orders: `{report['duplicate_chosen_cash_order_count']}`",
        f"- sales_amount_formula_unproven_orders: `{report['sales_amount_formula_unproven_order_count']}`",
        f"- source_formula_proven_orders: `{report['sales_amount_source_formula_proven_order_count']}`",
        f"- source_formula_unproven_orders: `{report['sales_amount_source_formula_unproven_order_count']}`",
        f"- publication_binding_proven_orders: `{report['sales_amount_publication_binding_proven_order_count']}`",
        f"- publication_binding_unproven_orders: `{report['sales_amount_publication_binding_unproven_order_count']}`",
        f"- selected_amount_source_mismatch_orders: `{report['sales_amount_published_source_mismatch_order_count']}`",
        f"- selected_source_multiset_mismatch_orders: `{report['sales_amount_source_multiset_mismatch_order_count']}`",
        f"- entry_ambiguity_reasons_all_scope: `reference_incomplete={report['entry_reference_incomplete_order_count']}, quantity_mismatch={report['entry_quantity_mismatch_order_count']}, store_mismatch={report['entry_store_mismatch_order_count']}`",
        f"- provisional_missing_cash_orders: `{report['provisional_missing_cash_order_count']}`",
        f"- exact_neutralized_unmapped_entry_history: `groups={report['neutralized_unmapped_order_entry_group_count']}, events={report['neutralized_unmapped_order_entry_cash_event_count']}, net_kzt={report['neutralized_unmapped_order_entry_net_amount_kzt']:.2f}`",
        "",
        "| month | store | decision_grade | scope_complete | covered | sales_orders | missing_cash | entry_ambiguity | store_mismatch | db_net_rev | cash_net_rev | rel_diff_pct |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['sale_month']}` | `{row['store_code']}` | `{str(row['decision_grade']).lower()}` | "
            f"`{str(row['scope_complete']).lower()}` | `{str(row['covered']).lower()}` | "
            f"{row['sales_order_count']} | {row['missing_cash_order_count']} | "
            f"{row['entry_identity_ambiguous_order_count']} | "
            f"{row['event_store_mismatch_order_count']} | {row['db_net_rev_kzt']:.2f} | "
            f"{row['cash_net_rev_kzt']:.2f} | {row['rel_diff_pct']:.2f} |"
        )

    if report["mismatches"]:
        lines.extend(["", "## Mismatches", ""])
        for msg in report["mismatches"]:
            lines.append(f"- {msg}")

    if report["notes"]:
        lines.extend(["", "## Notes", ""])
        for note in report["notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def validate_monthly_cash_reconciliation(
    *,
    db_path: Path,
    since: date,
    until: date,
    output_root: Path,
    tolerance_pct: float,
    statusdate_cutover: date,
    require_covered_pairs: bool,
    strict: bool,
) -> dict[str, Any]:
    if until < since:
        raise CashReconciliationError("until must be >= since")
    if tolerance_pct < 0:
        raise CashReconciliationError("tolerance_pct must be >= 0")
    if not db_path.exists():
        raise CashReconciliationError(f"db not found: {db_path}")

    db_path = db_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if _paths_collide(output_root, db_path):
        raise CashReconciliationError("output_root must not resolve to the DB path or a hardlink to it")
    if db_path != DEFAULT_DB.expanduser().resolve() and output_root == DEFAULT_OUTPUT_ROOT.expanduser().resolve():
        raise CashReconciliationError(
            "non-production DB requires an explicit noncanonical output_root"
        )

    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _object_exists(conn, "view", "view_sales_line_truth"):
            raise CashReconciliationError(
                "required view missing: view_sales_line_truth; prepare schema in a separately write-gated lane"
            )
        if not _object_exists(conn, "table", "fact_cashflow_events"):
            raise CashReconciliationError("required table missing: fact_cashflow_events")
        if not _object_exists(conn, "table", "fact_order_entries_kaspi"):
            raise CashReconciliationError("required table missing: fact_order_entries_kaspi")
        cash_event_columns = _table_columns(conn, "fact_cashflow_events")
        optional_cash_select = {
            column: (
                f"COALESCE(c.{column}, '') AS {column}"
                if column in cash_event_columns
                else f"'' AS {column}"
            )
            for column in ("notes", "run_id", "event_hash")
        }
        cash_select_notes = optional_cash_select["notes"]
        cash_select_run_id = optional_cash_select["run_id"]
        cash_select_event_hash = optional_cash_select["event_hash"]
        sales_orders = pd.read_sql_query(
            """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                MIN(substr(date(sale_date), 1, 7)) AS sale_month,
                MIN(UPPER(COALESCE(store_code, 'UNKNOWN'))) AS store_code,
                COUNT(DISTINCT substr(date(sale_date), 1, 7)) AS sale_month_count,
                COUNT(DISTINCT UPPER(COALESCE(store_code, 'UNKNOWN'))) AS sale_store_count,
                COUNT(*) AS sales_line_count,
                SUM(COALESCE(units, 0)) AS sales_units,
                SUM(COALESCE(net_rev_kzt, 0)) AS db_net_rev_kzt
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            GROUP BY CAST(order_id AS TEXT)
            """,
            conn,
            params=(since.isoformat(), until.isoformat()),
        )

        order_entries = pd.read_sql_query(
            """
            SELECT
                CAST(order_id AS TEXT) AS order_id,
                CAST(entry_id AS TEXT) AS entry_id,
                UPPER(COALESCE(store_code, 'UNKNOWN')) AS entry_store_code,
                COALESCE(quantity, 0) AS quantity,
                COALESCE(offer_id, '') AS offer_id
            FROM fact_order_entries_kaspi
            WHERE COALESCE(TRIM(CAST(order_id AS TEXT)), '') <> ''
              AND COALESCE(TRIM(CAST(entry_id AS TEXT)), '') <> ''
            """,
            conn,
        )

        cash_events = pd.read_sql_query(
            f"""
            SELECT
                c.id AS event_id,
                date(c.event_date) AS event_date,
                c.event_date AS raw_event_date,
                COALESCE(c.amount_kzt, 0) AS amount_kzt,
                UPPER(COALESCE(c.store_code, 'UNKNOWN')) AS event_store_code,
                UPPER(COALESCE(c.ref_type, '')) AS ref_type,
                CAST(c.ref_id AS TEXT) AS ref_id,
                COALESCE(c.source, '') AS source,
                COALESCE(c.sku_key, '') AS sku_key,
                COALESCE(c.sku_id, '') AS sku_id,
                {cash_select_notes},
                {cash_select_run_id},
                {cash_select_event_hash},
                CASE
                    WHEN UPPER(COALESCE(c.ref_type, '')) = 'ORDER_ENTRY'
                        THEN CAST(entries.order_id AS TEXT)
                    WHEN UPPER(COALESCE(c.ref_type, '')) = 'ORDER'
                        THEN CAST(c.ref_id AS TEXT)
                    ELSE NULL
                END AS order_id
            FROM fact_cashflow_events AS c
            LEFT JOIN fact_order_entries_kaspi AS entries
              ON UPPER(COALESCE(c.ref_type, '')) = 'ORDER_ENTRY'
             AND entries.entry_id = c.ref_id
            WHERE UPPER(COALESCE(c.event_type, '')) = 'CASH_IN'
              AND (date(c.event_date) <= ? OR date(c.event_date) IS NULL)
            """,
            conn,
            params=(until.isoformat(),),
        )
        sales_amount_formula_proof_available, sales_amount_formula_by_order_store = (
            _sales_amount_formula_proof(conn, since=since, until=until)
        )
    finally:
        conn.close()

    cash_by_order: dict[str, list[dict[str, Any]]] = {}
    selected_order_ids = {
        _safe_text(value)
        for value in sales_orders.get("order_id", pd.Series(dtype="object")).tolist()
        if _safe_text(value)
    }
    entries_by_order: dict[str, list[dict[str, Any]]] = {}
    for raw in order_entries.to_dict(orient="records"):
        order_id = _safe_text(raw.get("order_id"))
        if order_id:
            entries_by_order.setdefault(order_id, []).append(raw)

    unsupported_cash_event_count = 0
    unsupported_cash_event_count_asof_all = 0
    unmapped_order_entry_cash_event_count = 0
    unmapped_order_entry_cash_event_count_asof_all = 0
    neutralized_unmapped_event_ids, neutralized_unmapped_groups = (
        _neutralized_unmapped_order_entry_events(cash_events)
    )
    neutralized_unmapped_order_entry_cash_event_count = 0
    neutralized_unmapped_order_entry_cash_event_count_asof_all = 0
    invalid_selected_cash_event_date_count = 0
    out_of_cohort_mapped_cash_event_count = 0
    for raw in cash_events.to_dict(orient="records"):
        ref_type = _safe_text(raw.get("ref_type")).upper()
        order_id = _safe_text(raw.get("order_id"))
        event_date_text = _safe_text(raw.get("event_date"))
        in_reporting_event_window = bool(
            event_date_text and since.isoformat() <= event_date_text <= until.isoformat()
        )
        if ref_type not in {"ORDER", "ORDER_ENTRY"}:
            unsupported_cash_event_count_asof_all += 1
            unsupported_cash_event_count += int(in_reporting_event_window)
            continue
        if ref_type == "ORDER_ENTRY" and not order_id:
            event_id = int(raw["event_id"])
            if event_id in neutralized_unmapped_event_ids:
                neutralized_unmapped_order_entry_cash_event_count_asof_all += 1
                neutralized_unmapped_order_entry_cash_event_count += int(
                    in_reporting_event_window
                )
                continue
            unmapped_order_entry_cash_event_count_asof_all += 1
            unmapped_order_entry_cash_event_count += int(in_reporting_event_window)
            continue
        if not order_id or order_id not in selected_order_ids:
            out_of_cohort_mapped_cash_event_count += 1
            continue
        if not event_date_text:
            invalid_selected_cash_event_date_count += 1
            continue
        cash_by_order.setdefault(order_id, []).append(raw)

    order_rows: list[dict[str, Any]] = []
    pair_accumulators: dict[tuple[str, str], dict[str, Any]] = {}

    for raw in sales_orders.to_dict(orient="records"):
        order_id = _safe_text(raw.get("order_id"))
        month = _safe_text(raw.get("sale_month"))
        store = (_safe_text(raw.get("store_code")) or "UNKNOWN").upper()
        sale_month_count = int(round(_safe_float(raw.get("sale_month_count"))))
        sale_store_count = int(round(_safe_float(raw.get("sale_store_count"))))
        sales_line_count = int(round(_safe_float(raw.get("sales_line_count"))))
        sales_units = _safe_float(raw.get("sales_units"))
        identity_ambiguous = bool(
            not order_id
            or not month
            or sale_month_count != 1
            or sale_store_count != 1
        )
        db_net = _safe_float(raw.get("db_net_rev_kzt"))
        sales_amount_formula_state = sales_amount_formula_by_order_store.get(
            (order_id, store), {}
        )
        sales_amount_formula_unproven = bool(
            not sales_amount_formula_proof_available
            or not bool(sales_amount_formula_state.get("proven"))
        )
        all_events = cash_by_order.get(order_id, [])
        entry_events = [row for row in all_events if _safe_text(row.get("ref_type")).upper() == "ORDER_ENTRY"]
        order_events = [row for row in all_events if _safe_text(row.get("ref_type")).upper() == "ORDER"]
        expected_entries = entries_by_order.get(order_id, [])
        expected_entry_ids = {
            _safe_text(row.get("entry_id"))
            for row in expected_entries
            if _safe_text(row.get("entry_id"))
        }
        entry_cash_ref_ids = {
            _safe_text(row.get("ref_id"))
            for row in entry_events
            if _safe_text(row.get("ref_id"))
        }
        expected_entry_stores = {
            (_safe_text(row.get("entry_store_code")) or "UNKNOWN").upper()
            for row in expected_entries
        }
        expected_entry_quantity = sum(_safe_float(row.get("quantity")) for row in expected_entries)
        entry_reference_complete = bool(
            entry_events
            and expected_entry_ids
            and entry_cash_ref_ids == expected_entry_ids
        )
        entry_store_matches_sales = bool(
            expected_entry_ids and expected_entry_stores == {store}
        )
        entry_quantity_matches_sales = bool(
            expected_entry_ids and abs(expected_entry_quantity - sales_units) <= 0.0001
        )
        entry_identity_ambiguous = bool(
            entry_events
            and not (
                entry_reference_complete
                and entry_store_matches_sales
                and entry_quantity_matches_sales
            )
        )
        if entry_events:
            chosen_events = entry_events
            resolution = "AMBIGUOUS_ENTRY" if entry_identity_ambiguous else "ORDER_ENTRY"
        elif order_events:
            chosen_events = order_events
            resolution = "ORDER"
        else:
            chosen_events = []
            resolution = "MISSING"

        chosen_stores = {
            (_safe_text(row.get("event_store_code")) or "UNKNOWN").upper()
            for row in chosen_events
        }
        chosen_event_signatures = Counter(
            (
                _safe_text(row.get("event_date")),
                round(_safe_float(row.get("amount_kzt")), 2),
                (_safe_text(row.get("event_store_code")) or "UNKNOWN").upper(),
                _safe_text(row.get("ref_type")).upper(),
                _safe_text(row.get("ref_id")),
                _safe_text(row.get("sku_key")),
                _safe_text(row.get("sku_id")),
            )
            for row in chosen_events
        )
        duplicate_chosen_cash = any(count > 1 for count in chosen_event_signatures.values())
        duplicate_chosen_cash_group_count = sum(
            count - 1 for count in chosen_event_signatures.values() if count > 1
        )
        if duplicate_chosen_cash and not entry_identity_ambiguous:
            resolution = "AMBIGUOUS_DUPLICATE_CASH"
        event_store_mismatch = bool(chosen_events and chosen_stores != {store})
        chosen_cash = sum(_safe_float(row.get("amount_kzt")) for row in chosen_events)
        chosen_event_dates = {
            _safe_text(row.get("event_date"))
            for row in chosen_events
            if _safe_text(row.get("event_date"))
        }
        cash_covered = bool(
            not identity_ambiguous
            and chosen_events
            and not entry_identity_ambiguous
            and not duplicate_chosen_cash
            and not sales_amount_formula_unproven
            and not event_store_mismatch
        )
        dual_ref_type = bool(entry_events and order_events)

        order_row = {
            "order_id": order_id,
            "sale_month": month,
            "store_code": store,
            "db_net_rev_kzt": round(db_net, 2),
            "cash_net_rev_kzt": round(chosen_cash, 2),
            "cash_resolution": resolution,
            "sales_line_count": sales_line_count,
            "sales_units": round(sales_units, 4),
            "chosen_cash_event_count": len(chosen_events),
            "chosen_cash_event_days": len(chosen_event_dates),
            "order_entry_cash_event_count": len(entry_events),
            "order_cash_event_count": len(order_events),
            "dual_ref_type": dual_ref_type,
            "expected_entry_count": len(expected_entry_ids),
            "entry_cash_reference_count": len(entry_cash_ref_ids),
            "expected_entry_quantity": round(expected_entry_quantity, 4),
            "entry_reference_complete": entry_reference_complete,
            "entry_store_matches_sales": entry_store_matches_sales,
            "entry_quantity_matches_sales": entry_quantity_matches_sales,
            "entry_identity_ambiguous": entry_identity_ambiguous,
            "duplicate_chosen_cash": duplicate_chosen_cash,
            "duplicate_chosen_cash_group_count": duplicate_chosen_cash_group_count,
            "sales_amount_formula_proof_available": sales_amount_formula_proof_available,
            "sales_amount_formula_proven": (
                bool(sales_amount_formula_state.get("proven"))
                if sales_amount_formula_proof_available
                else False
            ),
            "sales_amount_formula_unproven_line_count": int(
                sales_amount_formula_state.get("unproven_line_count", 0)
            ),
            "sales_amount_source_formula_line_count": int(
                sales_amount_formula_state.get("source_formula_line_count", 0)
            ),
            "sales_amount_source_formula_unproven_line_count": int(
                sales_amount_formula_state.get(
                    "source_formula_unproven_line_count", 0
                )
            ),
            "sales_amount_source_formula_invalid_line_count": int(
                sales_amount_formula_state.get(
                    "source_formula_invalid_line_count", 0
                )
            ),
            "sales_amount_source_formula_proven": bool(
                sales_amount_formula_state.get("source_formula_proven", False)
            ),
            "sales_amount_publication_binding_unproven_line_count": int(
                sales_amount_formula_state.get(
                    "publication_binding_unproven_line_count", 0
                )
            ),
            "sales_amount_publication_binding_proven": bool(
                sales_amount_formula_state.get(
                    "publication_binding_proven", False
                )
            ),
            "sales_amount_formula_max_abs_diff_kzt": round(
                _safe_float(sales_amount_formula_state.get("max_abs_diff_kzt")), 2
            ),
            "sales_amount_published_source_mismatch_line_count": int(
                sales_amount_formula_state.get(
                    "published_source_mismatch_line_count", 0
                )
            ),
            "sales_amount_published_source_max_abs_diff_kzt": round(
                _safe_float(
                    sales_amount_formula_state.get(
                        "max_published_source_abs_diff_kzt"
                    )
                ),
                2,
            ),
            "sales_amount_source_multiset_mismatch_line_count": int(
                sales_amount_formula_state.get(
                    "source_multiset_mismatch_line_count", 0
                )
            ),
            "sale_month_count": sale_month_count,
            "sale_store_count": sale_store_count,
            "identity_ambiguous": identity_ambiguous,
            "chosen_event_store_codes": ",".join(sorted(chosen_stores)),
            "event_store_mismatch": event_store_mismatch,
            "cash_covered": cash_covered,
        }
        order_rows.append(order_row)

        pair = pair_accumulators.setdefault(
            (month, store),
            {
                "db_net_rev_kzt": 0.0,
                "cash_net_rev_kzt": 0.0,
                "sales_order_count": 0,
                "cash_covered_order_count": 0,
                "missing_cash_order_count": 0,
                "identity_ambiguous_order_count": 0,
                "entry_identity_ambiguous_order_count": 0,
                "duplicate_chosen_cash_order_count": 0,
                "sales_amount_formula_unproven_order_count": 0,
                "event_store_mismatch_order_count": 0,
                "order_entry_resolution_count": 0,
                "order_fallback_resolution_count": 0,
                "dual_ref_type_order_count": 0,
                "event_dates": set(),
            },
        )
        pair["db_net_rev_kzt"] += db_net
        pair["cash_net_rev_kzt"] += chosen_cash
        pair["sales_order_count"] += 1
        pair["cash_covered_order_count"] += int(cash_covered)
        pair["missing_cash_order_count"] += int(resolution == "MISSING")
        pair["identity_ambiguous_order_count"] += int(identity_ambiguous)
        pair["entry_identity_ambiguous_order_count"] += int(entry_identity_ambiguous)
        pair["duplicate_chosen_cash_order_count"] += int(duplicate_chosen_cash)
        pair["sales_amount_formula_unproven_order_count"] += int(
            sales_amount_formula_unproven
        )
        pair["event_store_mismatch_order_count"] += int(event_store_mismatch)
        pair["order_entry_resolution_count"] += int(resolution == "ORDER_ENTRY")
        pair["order_fallback_resolution_count"] += int(resolution == "ORDER")
        pair["dual_ref_type_order_count"] += int(dual_ref_type)
        pair["event_dates"].update(chosen_event_dates)

    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    notes: list[str] = []
    covered_pairs = 0
    decision_grade_pairs = 0
    uncovered_decision_grade_pairs = 0

    for (month, store), raw in sorted(pair_accumulators.items()):
        if not month:
            continue
        db_net = _safe_float(raw.get("db_net_rev_kzt"))
        cash_net = _safe_float(raw.get("cash_net_rev_kzt"))
        sales_order_count = int(raw["sales_order_count"])
        cash_covered_order_count = int(raw["cash_covered_order_count"])
        missing_cash_order_count = int(raw["missing_cash_order_count"])
        identity_ambiguous_order_count = int(raw["identity_ambiguous_order_count"])
        entry_identity_ambiguous_order_count = int(raw["entry_identity_ambiguous_order_count"])
        duplicate_chosen_cash_order_count = int(raw["duplicate_chosen_cash_order_count"])
        sales_amount_formula_unproven_order_count = int(
            raw["sales_amount_formula_unproven_order_count"]
        )
        event_store_mismatch_order_count = int(raw["event_store_mismatch_order_count"])
        event_days = len(raw["event_dates"])

        month_end = _month_end(month)
        closed_month = month_end < until
        decision_grade = bool(closed_month and month_end >= statusdate_cutover)
        scope_complete = bool(
            sales_order_count > 0
            and cash_covered_order_count == sales_order_count
            and missing_cash_order_count == 0
            and identity_ambiguous_order_count == 0
            and entry_identity_ambiguous_order_count == 0
            and duplicate_chosen_cash_order_count == 0
            and sales_amount_formula_unproven_order_count == 0
            and event_store_mismatch_order_count == 0
        )
        covered = bool(decision_grade and scope_complete)
        if decision_grade:
            decision_grade_pairs += 1
        if covered:
            covered_pairs += 1
        elif decision_grade:
            uncovered_decision_grade_pairs += 1

        denom = max(abs(db_net), 1.0)
        rel_diff = abs(db_net - cash_net) / denom
        rel_diff_pct = round(rel_diff * 100.0, 4)
        exceeds = bool(covered and rel_diff > tolerance_pct)
        if exceeds:
            mismatches.append(
                f"{month} {store}: db_net={db_net:.2f} cash_net={cash_net:.2f} rel_diff_pct={rel_diff_pct:.2f}"
            )

        rows.append(
            {
                "sale_month": month,
                "store_code": store,
                "db_net_rev_kzt": round(db_net, 2),
                "cash_net_rev_kzt": round(cash_net, 2),
                "event_days": event_days,
                "sales_order_count": sales_order_count,
                "cash_covered_order_count": cash_covered_order_count,
                "missing_cash_order_count": missing_cash_order_count,
                "identity_ambiguous_order_count": identity_ambiguous_order_count,
                "entry_identity_ambiguous_order_count": entry_identity_ambiguous_order_count,
                "duplicate_chosen_cash_order_count": duplicate_chosen_cash_order_count,
                "sales_amount_formula_unproven_order_count": sales_amount_formula_unproven_order_count,
                "event_store_mismatch_order_count": event_store_mismatch_order_count,
                "order_entry_resolution_count": int(raw["order_entry_resolution_count"]),
                "order_fallback_resolution_count": int(raw["order_fallback_resolution_count"]),
                "dual_ref_type_order_count": int(raw["dual_ref_type_order_count"]),
                "closed_month": closed_month,
                "decision_grade": decision_grade,
                "scope_complete": scope_complete,
                "covered": covered,
                "rel_diff_pct": rel_diff_pct,
                "exceeds_tolerance": exceeds,
            }
        )

    if covered_pairs == 0:
        notes.append(
            "No covered decision-grade month/store pairs available for strict cash reconciliation in this window."
        )
    if neutralized_unmapped_order_entry_cash_event_count:
        notes.append(
            f"{len(neutralized_unmapped_groups)} exact recovered-entry neutralization group(s) / "
            f"{neutralized_unmapped_order_entry_cash_event_count} event(s) net to 0 KZT and are disclosed outside active unmapped obligations."
        )

    errors: list[str] = []
    error_codes: list[str] = []
    if unsupported_cash_event_count:
        error_codes.append("CASH_RECON_UNSUPPORTED_REF_TYPE")
        errors.append(f"{unsupported_cash_event_count} CASH_IN event(s) use an unsupported ref_type")
    if unmapped_order_entry_cash_event_count:
        error_codes.append("CASH_RECON_UNMAPPED_ORDER_ENTRY")
        errors.append(
            f"{unmapped_order_entry_cash_event_count} ORDER_ENTRY CASH_IN event(s) do not resolve to an order"
        )
    if invalid_selected_cash_event_date_count:
        error_codes.append("CASH_RECON_INVALID_EVENT_DATE")
        errors.append(
            f"{invalid_selected_cash_event_date_count} selected-cohort CASH_IN event(s) have an invalid event_date"
        )
    if uncovered_decision_grade_pairs:
        error_codes.append("CASH_RECON_INCOMPLETE_COVERAGE")
        errors.append(
            f"{uncovered_decision_grade_pairs} decision-grade month/store pair(s) have incomplete order coverage"
        )
    if mismatches:
        error_codes.append("CASH_RECON_MISMATCH")
        errors.append(f"{len(mismatches)} covered pair(s) exceed tolerance")
    if (require_covered_pairs or strict) and covered_pairs == 0:
        error_codes.append("CASH_RECON_NO_COVERAGE")
        errors.append("no covered decision-grade month/store pairs available")

    out_dir = output_root.resolve() / until.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_csv = out_dir / "cash_reconciliation_rows.csv"
    pd.DataFrame(rows).to_csv(rows_csv, index=False, encoding="utf-8")
    order_rows_csv = out_dir / "cash_reconciliation_order_rows.csv"
    pd.DataFrame(order_rows).to_csv(order_rows_csv, index=False, encoding="utf-8")

    order_entry_resolution_count = sum(row["cash_resolution"] == "ORDER_ENTRY" for row in order_rows)
    order_fallback_resolution_count = sum(row["cash_resolution"] == "ORDER" for row in order_rows)
    ambiguous_entry_resolution_count = sum(
        row["cash_resolution"] == "AMBIGUOUS_ENTRY" for row in order_rows
    )
    entry_reference_incomplete_order_count = sum(
        row["cash_resolution"] == "AMBIGUOUS_ENTRY" and not row["entry_reference_complete"]
        for row in order_rows
    )
    entry_quantity_mismatch_order_count = sum(
        row["cash_resolution"] == "AMBIGUOUS_ENTRY" and not row["entry_quantity_matches_sales"]
        for row in order_rows
    )
    entry_store_mismatch_order_count = sum(
        row["cash_resolution"] == "AMBIGUOUS_ENTRY" and not row["entry_store_matches_sales"]
        for row in order_rows
    )
    missing_cash_order_count = sum(row["cash_resolution"] == "MISSING" for row in order_rows)
    identity_ambiguous_order_count = sum(bool(row["identity_ambiguous"]) for row in order_rows)
    event_store_mismatch_order_count = sum(bool(row["event_store_mismatch"]) for row in order_rows)
    duplicate_chosen_cash_order_count = sum(
        bool(row["duplicate_chosen_cash"]) for row in order_rows
    )
    sales_amount_formula_unproven_order_count = sum(
        row["sales_amount_formula_proven"] is False for row in order_rows
    )
    sales_amount_source_formula_proven_order_count = sum(
        bool(row["sales_amount_source_formula_proven"])
        for row in order_rows
    )
    sales_amount_source_formula_unproven_order_count = (
        len(order_rows) - sales_amount_source_formula_proven_order_count
    )
    sales_amount_publication_binding_proven_order_count = sum(
        bool(row["sales_amount_publication_binding_proven"])
        for row in order_rows
    )
    sales_amount_publication_binding_unproven_order_count = (
        len(order_rows) - sales_amount_publication_binding_proven_order_count
    )
    sales_amount_published_source_mismatch_order_count = sum(
        int(row["sales_amount_published_source_mismatch_line_count"]) > 0
        for row in order_rows
    )
    sales_amount_source_multiset_mismatch_order_count = sum(
        int(row["sales_amount_source_multiset_mismatch_line_count"]) > 0
        for row in order_rows
    )
    dual_ref_type_order_count = sum(bool(row["dual_ref_type"]) for row in order_rows)
    decision_grade_order_rows = [
        row
        for row in order_rows
        if row["sale_month"]
        and _month_end(str(row["sale_month"])) < until
        and _month_end(str(row["sale_month"])) >= statusdate_cutover
    ]
    decision_grade_missing_cash_order_count = sum(
        row["cash_resolution"] == "MISSING" for row in decision_grade_order_rows
    )
    decision_grade_ambiguous_entry_order_count = sum(
        row["cash_resolution"] == "AMBIGUOUS_ENTRY" for row in decision_grade_order_rows
    )
    provisional_missing_cash_order_count = missing_cash_order_count - decision_grade_missing_cash_order_count

    if duplicate_chosen_cash_order_count:
        error_codes.append("CASH_RECON_DUPLICATE_CHOSEN_CASH")
        errors.append(
            f"{duplicate_chosen_cash_order_count} selected order(s) have duplicate chosen CASH_IN evidence"
        )
    if sales_amount_formula_unproven_order_count:
        error_codes.append("CASH_RECON_SALES_AMOUNT_UNPROVEN")
        errors.append(
            f"{sales_amount_formula_unproven_order_count} selected order(s) do not bind and reproduce the exact effective-dated canonical source-line amount"
        )
    if sales_amount_published_source_mismatch_order_count:
        error_codes.append("CASH_RECON_SELECTED_AMOUNT_SOURCE_MISMATCH")
        errors.append(
            f"{sales_amount_published_source_mismatch_order_count} selected order(s) publish an amount or quantity that differs from the exact declared source line"
        )
    if sales_amount_source_multiset_mismatch_order_count:
        error_codes.append("CASH_RECON_SELECTED_SOURCE_MULTISET_MISMATCH")
        errors.append(
            f"{sales_amount_source_multiset_mismatch_order_count} selected order(s) do not bind an exact order/store/source-line multiset"
        )

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "ok": len(errors) == 0,
        "error_code": error_codes[0] if error_codes else None,
        "error_codes": error_codes,
        "errors": errors,
        "mismatches": mismatches,
        "notes": notes,
        "rows": rows,
        "sales_order_count": len(order_rows),
        "order_entry_resolution_count": order_entry_resolution_count,
        "order_fallback_resolution_count": order_fallback_resolution_count,
        "ambiguous_entry_resolution_count": ambiguous_entry_resolution_count,
        "entry_reference_incomplete_order_count": entry_reference_incomplete_order_count,
        "entry_quantity_mismatch_order_count": entry_quantity_mismatch_order_count,
        "entry_store_mismatch_order_count": entry_store_mismatch_order_count,
        "missing_cash_order_count": missing_cash_order_count,
        "decision_grade_order_count": len(decision_grade_order_rows),
        "decision_grade_missing_cash_order_count": decision_grade_missing_cash_order_count,
        "decision_grade_ambiguous_entry_order_count": decision_grade_ambiguous_entry_order_count,
        "provisional_missing_cash_order_count": provisional_missing_cash_order_count,
        "identity_ambiguous_order_count": identity_ambiguous_order_count,
        "event_store_mismatch_order_count": event_store_mismatch_order_count,
        "duplicate_chosen_cash_order_count": duplicate_chosen_cash_order_count,
        "sales_amount_formula_proof_available": sales_amount_formula_proof_available,
        "sales_amount_formula_unproven_order_count": sales_amount_formula_unproven_order_count,
        "sales_amount_source_formula_proven_order_count": sales_amount_source_formula_proven_order_count,
        "sales_amount_source_formula_unproven_order_count": sales_amount_source_formula_unproven_order_count,
        "sales_amount_publication_binding_proven_order_count": sales_amount_publication_binding_proven_order_count,
        "sales_amount_publication_binding_unproven_order_count": sales_amount_publication_binding_unproven_order_count,
        "sales_amount_published_source_mismatch_order_count": sales_amount_published_source_mismatch_order_count,
        "sales_amount_source_multiset_mismatch_order_count": sales_amount_source_multiset_mismatch_order_count,
        "dual_ref_type_order_count": dual_ref_type_order_count,
        "unsupported_cash_event_count": unsupported_cash_event_count,
        "unsupported_cash_event_count_asof_all": unsupported_cash_event_count_asof_all,
        "unmapped_order_entry_cash_event_count": unmapped_order_entry_cash_event_count,
        "unmapped_order_entry_cash_event_count_asof_all": unmapped_order_entry_cash_event_count_asof_all,
        "neutralized_unmapped_order_entry_cash_event_count": neutralized_unmapped_order_entry_cash_event_count,
        "neutralized_unmapped_order_entry_cash_event_count_asof_all": neutralized_unmapped_order_entry_cash_event_count_asof_all,
        "neutralized_unmapped_order_entry_group_count": len(neutralized_unmapped_groups),
        "neutralized_unmapped_order_entry_net_amount_kzt": round(
            sum(_safe_float(row["net_amount_kzt"]) for row in neutralized_unmapped_groups),
            2,
        ),
        "invalid_selected_cash_event_date_count": invalid_selected_cash_event_date_count,
        "out_of_cohort_mapped_cash_event_count": out_of_cohort_mapped_cash_event_count,
        "decision_grade_pairs": decision_grade_pairs,
        "covered_pairs": covered_pairs,
        "uncovered_decision_grade_pairs": uncovered_decision_grade_pairs,
        "tolerance_pct": float(tolerance_pct),
        "statusdate_cutover": statusdate_cutover.isoformat(),
        "db_path": str(db_path.resolve()),
        "db_open_mode": "read_only",
        "rows_csv": str(rows_csv),
        "order_rows_csv": str(order_rows_csv),
    }

    json_path = out_dir / "cash_reconciliation_report.json"
    md_path = out_dir / "cash_reconciliation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and errors:
        raise CashReconciliationError("cash reconciliation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate monthly economics against cashflow events")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default="2025-06-06")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=DEFAULT_TOLERANCE_FRACTION,
        help="Relative tolerance as a fraction (0.01 means 1%%)",
    )
    parser.add_argument("--statusdate-cutover", default=DEFAULT_STATUSDATE_CUTOVER.isoformat())
    parser.add_argument("--require-covered-pairs", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_monthly_cash_reconciliation(
            db_path=args.db,
            since=date.fromisoformat(str(args.since)),
            until=date.fromisoformat(str(args.as_of)),
            output_root=args.output_root,
            tolerance_pct=float(args.tolerance_pct),
            statusdate_cutover=date.fromisoformat(str(args.statusdate_cutover)),
            require_covered_pairs=bool(args.require_covered_pairs),
            strict=bool(args.strict),
        )
    except CashReconciliationError as exc:
        print("status=FAIL")
        print("error_code=CASH_RECON_FAIL")
        print(f"message={exc}")
        return 1

    print(f"cash_reconciliation_json={report['json_path']}")
    print(f"cash_reconciliation_md={report['md_path']}")
    print(f"status={report['status']}")
    if report.get("error_code"):
        print(f"error_code={report['error_code']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
