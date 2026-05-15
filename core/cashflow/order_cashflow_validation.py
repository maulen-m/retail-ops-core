"""Read-only D1 order cashflow validation helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DELIVERED_STAGE_CODES = {"COMPLETED", "DELIVERED", "ISSUED_COMPLETED"}
UNKNOWN_STORE_CODES = {"", "UNKNOWN"}
LEGACY_RECEIVABLE_EVENT_TYPES = {
    "SALE_ACCRUED",
    "PAYOUT_EXPECTED",
    "DELIVERY_FEES",
    "REFUND",
    "OPENING_BALANCE",
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _date_part(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()[:10]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_unknown_store(value: Any) -> bool:
    return _upper(value) in UNKNOWN_STORE_CODES


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_weak_sku_identity(sku_key: str, sku_id: str) -> bool:
    return sku_key.strip().upper() == "CL" and sku_id.strip().upper().startswith("CL_")


def _is_recovered_blank_order_entry(candidate: dict[str, Any]) -> bool:
    return (
        _upper(candidate.get("ref_type")) == "ORDER_ENTRY"
        and str(candidate.get("ref_id") or "").startswith("RECOV-CURRENT_CRM-")
        and not str(candidate.get("sku_key") or "").strip()
        and not str(candidate.get("sku_id") or "").strip()
    )


def _event_is_balance_anchor_cash_in(row: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        _upper(row["event_type"]) == "CASH_IN"
        and (
            _upper(row["source"]) == "BALANCE_ANCHOR"
            or _upper(row["ref_type"]) == "BALANCE_ANCHOR"
        )
    )


def _is_legacy_receivable_diagnostic(row: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        _upper(row["source"]) == "ORDER_MODELLED"
        and _upper(row["account"]) == "RECEIVABLES"
        and _upper(row["event_type"]) in LEGACY_RECEIVABLE_EVENT_TYPES
    )


def _is_receivable_leak(row: sqlite3.Row | dict[str, Any]) -> bool:
    if _as_float(row["amount_kzt"]) <= 0:
        return False
    if _is_legacy_receivable_diagnostic(row):
        return False
    account = _upper(row["account"])
    event_type = _upper(row["event_type"])
    return "RECEIVABLE" in account or "RECEIVABLE" in event_type


def _load_sales_lines(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not _table_exists(conn, "sales_fact_v2"):
        return {}
    cols = _columns(conn, "sales_fact_v2")
    wanted = ["order_id", "store_code", "sku_key", "sku_id", "quantity", "sell_price_kzt"]
    select_cols = [col for col in wanted if col in cols]
    if not {"order_id", "store_code"}.issubset(select_cols):
        return {}
    rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM sales_fact_v2").fetchall()
    by_order: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        order_id = str(item.get("order_id") or "").strip()
        store_code = _upper(item.get("store_code") or "UNIVERSAL")
        if not order_id:
            continue
        by_order.setdefault((order_id, store_code), []).append(
            {
                "ref_type": "ORDER",
                "ref_id": order_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key": str(item.get("sku_key") or "").strip(),
                "sku_id": str(item.get("sku_id") or "").strip(),
                "quantity": _as_float(item.get("quantity")),
                "amount_basis_kzt": _as_float(item.get("sell_price_kzt")),
                "source": "sales_fact_v2",
            }
        )
    return by_order


def _offer_candidates(offer_id: Any) -> list[str]:
    raw = str(offer_id or "").strip()
    if not raw:
        return []
    candidates = [raw]
    for separator in ("\t", " "):
        if separator in raw:
            candidates.extend(part.strip() for part in raw.split(separator) if part.strip())
    for marker in ("CL_", "ELS_"):
        idx = raw.find(marker)
        if idx > 0:
            candidates.append(raw[idx:].strip())
    out = []
    seen = set()
    for item in candidates:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _load_article_map(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    rows = conn.execute(
        """
        SELECT store_code, kaspi_article, sku_key, sku_id
        FROM dim_kaspi_article_map
        WHERE sku_key IS NOT NULL
          AND trim(sku_key) <> ''
          AND sku_id IS NOT NULL
          AND trim(sku_id) <> ''
        """
    ).fetchall()
    out: dict[tuple[str, str], tuple[str, str]] = {}
    ambiguous: set[tuple[str, str]] = set()
    for row in rows:
        key = (_upper(row["store_code"]), str(row["kaspi_article"] or "").strip())
        value = (str(row["sku_key"] or "").strip(), str(row["sku_id"] or "").strip())
        if not key[0] or not key[1] or not value[0] or not value[1]:
            continue
        if key in ambiguous:
            continue
        if key in out and out[key] != value:
            ambiguous.add(key)
            out.pop(key, None)
            continue
        out[key] = value
    return out


def _load_entry_lines(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not _table_exists(conn, "fact_order_entries_kaspi"):
        return {}
    cols = _columns(conn, "fact_order_entries_kaspi")
    article_map = _load_article_map(conn)
    wanted = ["entry_id", "order_id", "store_code", "offer_id", "quantity", "unit_price_kzt", "total_price_kzt"]
    select_cols = [col for col in wanted if col in cols]
    if not {"order_id", "store_code"}.issubset(select_cols):
        return {}
    rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM fact_order_entries_kaspi").fetchall()
    sales = _load_sales_lines(conn)
    by_order: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        order_id = str(item.get("order_id") or "").strip()
        store_code = _upper(item.get("store_code") or "UNIVERSAL")
        if not order_id:
            continue
        entry_id = str(item.get("entry_id") or "").strip()
        sku_key = ""
        sku_id = ""
        for candidate in _offer_candidates(item.get("offer_id")):
            mapped = article_map.get((store_code, candidate))
            if mapped:
                sku_key, sku_id = mapped
                break
        qty = _as_float(item.get("quantity"))
        unit = _as_float(item.get("unit_price_kzt"))
        total = _as_float(item.get("total_price_kzt"))
        amount_basis = total if total > 0 else unit * qty
        by_order.setdefault((order_id, store_code), []).append(
            {
                "ref_type": "ORDER_ENTRY" if entry_id else "ORDER",
                "ref_id": entry_id or order_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "quantity": qty,
                "amount_basis_kzt": amount_basis,
                "source": "fact_order_entries_kaspi",
            }
        )

    for key, lines in by_order.items():
        sales_lines = sales.get(key, [])
        if len(lines) == len(sales_lines):
            for line, sale_line in zip(lines, sales_lines):
                if not line.get("sku_key") or not line.get("sku_id"):
                    line["sku_key"] = sale_line.get("sku_key", "")
                    line["sku_id"] = sale_line.get("sku_id", "")
    return by_order


def _load_fact_order_lines(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not _table_exists(conn, "fact_orders_kaspi"):
        return {}
    cols = _columns(conn, "fact_orders_kaspi")
    wanted = ["order_id", "store_code", "sku_key", "sku_id", "quantity", "unit_price_kzt"]
    select_cols = [col for col in wanted if col in cols]
    if not {"order_id", "store_code", "sku_key", "sku_id"}.issubset(select_cols):
        return {}
    rows = conn.execute(
        f"""
        SELECT {', '.join(select_cols)}
        FROM fact_orders_kaspi
        WHERE order_id IS NOT NULL
          AND trim(order_id) <> ''
          AND store_code IS NOT NULL
          AND trim(store_code) <> ''
          AND sku_key IS NOT NULL
          AND trim(sku_key) <> ''
          AND sku_id IS NOT NULL
          AND trim(sku_id) <> ''
        """
    ).fetchall()
    by_order: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        item = dict(row)
        order_id = str(item.get("order_id") or "").strip()
        store_code = _upper(item.get("store_code") or "UNIVERSAL")
        sku_id = str(item.get("sku_id") or "").strip()
        key = (order_id, store_code, sku_id)
        if not order_id or not sku_id or key in seen:
            continue
        seen.add(key)
        qty = _as_float(item.get("quantity"))
        unit = _as_float(item.get("unit_price_kzt"))
        by_order.setdefault((order_id, store_code), []).append(
            {
                "ref_type": "ORDER",
                "ref_id": order_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key": str(item.get("sku_key") or "").strip(),
                "sku_id": sku_id,
                "quantity": qty,
                "amount_basis_kzt": unit * qty,
                "source": "fact_orders_kaspi",
            }
        )
    return by_order


def _load_fact_order_header_lines(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not _table_exists(conn, "fact_orders_kaspi"):
        return {}
    cols = _columns(conn, "fact_orders_kaspi")
    wanted = [
        "order_id",
        "store_code",
        "quantity",
        "unit_price_kzt",
        "delivery_cost_for_seller",
        "delivery_cost",
        "sku_key",
        "sku_id",
    ]
    select_cols = [col for col in wanted if col in cols]
    if not {"order_id", "store_code", "quantity", "unit_price_kzt"}.issubset(select_cols):
        return {}
    rows = conn.execute(
        f"""
        SELECT {', '.join(select_cols)}
        FROM fact_orders_kaspi
        WHERE order_id IS NOT NULL
          AND trim(order_id) <> ''
          AND store_code IS NOT NULL
          AND trim(store_code) <> ''
          AND COALESCE(quantity, 0) > 0
          AND COALESCE(unit_price_kzt, 0) > 0
        """
    ).fetchall()
    by_order: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, float, float]] = set()
    for row in rows:
        item = dict(row)
        if str(item.get("sku_key") or "").strip() and str(item.get("sku_id") or "").strip():
            continue
        order_id = str(item.get("order_id") or "").strip()
        store_code = _upper(item.get("store_code") or "UNIVERSAL")
        qty = _as_float(item.get("quantity"))
        unit = _as_float(item.get("unit_price_kzt"))
        key = (order_id, store_code, qty, unit)
        if not order_id or key in seen:
            continue
        seen.add(key)
        delivery_cost = item.get("delivery_cost_for_seller")
        if delivery_cost is None:
            delivery_cost = item.get("delivery_cost")
        by_order.setdefault((order_id, store_code), []).append(
            {
                "ref_type": "ORDER",
                "ref_id": order_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key": "",
                "sku_id": "",
                "quantity": qty,
                "amount_basis_kzt": unit * qty,
                "delivery_cost_kzt": _as_float(delivery_cost),
                "source": "fact_orders_kaspi_header",
                "classification": "deterministic_exception",
                "classification_reason": "ORDER_HEADER_AMOUNT_WITHOUT_LINE_IDENTITY",
            }
        )
    return by_order


def _load_delivered_orders(conn: sqlite3.Connection, *, as_of: str | None) -> list[dict[str, Any]]:
    delivered_sql = ",".join("?" * len(DELIVERED_STAGE_CODES))
    params: list[Any] = list(sorted(DELIVERED_STAGE_CODES))
    as_of_clause = ""
    if as_of:
        as_of_clause = "AND date(event_ts) <= date(?)"
        params.append(as_of)
    rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
                   order_id,
                   MIN(event_ts) AS delivered_ts
            FROM order_status_event
            WHERE UPPER(COALESCE(stage_code, '')) IN ({delivered_sql})
              {as_of_clause}
            GROUP BY UPPER(COALESCE(store_code, 'UNIVERSAL')), order_id
            """,
            params,
        ).fetchall()
    ]
    non_unknown_orders = {
        str(row.get("order_id") or "").strip()
        for row in rows
        if str(row.get("order_id") or "").strip() and not _is_unknown_store(row.get("store_code"))
    }
    return [
        row
        for row in rows
        if not (
            str(row.get("order_id") or "").strip() in non_unknown_orders
            and _is_unknown_store(row.get("store_code"))
        )
    ]


def _build_d1_candidates(conn: sqlite3.Connection, *, as_of: str | None) -> list[dict[str, Any]]:
    entry_lines = _load_entry_lines(conn)
    sales_lines = _load_sales_lines(conn)
    fact_order_lines = _load_fact_order_lines(conn)
    fact_order_header_lines = _load_fact_order_header_lines(conn)
    candidates: list[dict[str, Any]] = []
    for delivered in _load_delivered_orders(conn, as_of=as_of):
        order_id = str(delivered.get("order_id") or "").strip()
        store_code = _upper(delivered.get("store_code") or "UNIVERSAL")
        delivered_date = _date_part(delivered.get("delivered_ts"))
        if not order_id or not delivered_date:
            continue
        lines = (
            entry_lines.get((order_id, store_code))
            or sales_lines.get((order_id, store_code))
            or fact_order_lines.get((order_id, store_code))
            or fact_order_header_lines.get((order_id, store_code))
        )
        if not lines:
            lines = [
                {
                    "ref_type": "ORDER",
                    "ref_id": order_id,
                    "order_id": order_id,
                    "store_code": store_code,
                    "sku_key": "",
                    "sku_id": "",
                    "quantity": 0.0,
                    "amount_basis_kzt": 0.0,
                    "source": "missing_line_evidence",
                }
            ]
        for line in lines:
            candidates.append({**line, "delivered_date": delivered_date})
    return candidates


def _cash_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return []
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                   ref_type, ref_id, source
            FROM fact_cashflow_events
            WHERE UPPER(COALESCE(event_type, '')) = 'CASH_IN'
            """
        ).fetchall()
    ]


def _positive_cash_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if _as_float(row.get("amount_kzt")) <= 0:
            continue
        if "RECEIVABLE" in _upper(row.get("account")):
            continue
        if _event_is_balance_anchor_cash_in(row):
            continue
        key = (
            _date_part(row.get("event_date")),
            _upper(row.get("ref_type") or "ORDER"),
            str(row.get("ref_id") or "").strip(),
        )
        index.setdefault(key, []).append(row)
    return index


def _candidate_cash_rows(
    candidate: dict[str, Any],
    index: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    delivered_date = candidate["delivered_date"]
    rows: list[dict[str, Any]] = []
    if candidate["ref_type"] == "ORDER_ENTRY":
        rows.extend(index.get((delivered_date, "ORDER_ENTRY", candidate["ref_id"]), []))
    rows.extend(index.get((delivered_date, "ORDER", candidate["order_id"]), []))
    return rows


def _matching_positive_cash(candidate: dict[str, Any], rows: list[dict[str, Any]], line_count: int) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    sku_fallback: list[dict[str, Any]] = []
    general_fallback: list[dict[str, Any]] = []
    for row in rows:
        if _as_float(row.get("amount_kzt")) <= 0:
            continue
        if "RECEIVABLE" in _upper(row.get("account")):
            continue
        if _event_is_balance_anchor_cash_in(row):
            continue
        if _date_part(row.get("event_date")) != candidate["delivered_date"]:
            continue
        row_ref_type = _upper(row.get("ref_type") or "ORDER")
        row_ref_id = str(row.get("ref_id") or "").strip()
        row_sku_key = str(row.get("sku_key") or "").strip()
        row_sku_id = str(row.get("sku_id") or "").strip()
        candidate_sku_key = str(candidate.get("sku_key") or "").strip()
        candidate_sku_id = str(candidate.get("sku_id") or "").strip()
        candidate_specific = bool(candidate_sku_id or candidate_sku_key) and not _is_weak_sku_identity(
            candidate_sku_key, candidate_sku_id
        )
        if candidate["ref_type"] == "ORDER_ENTRY" and row_ref_type == "ORDER_ENTRY" and row_ref_id == candidate["ref_id"]:
            exact.append(row)
        elif row_ref_type == "ORDER" and row_ref_id == candidate["order_id"]:
            if candidate_specific and (row_sku_id or row_sku_key):
                if (
                    (candidate_sku_id and row_sku_id == candidate_sku_id)
                    or (candidate_sku_key and row_sku_key == candidate_sku_key)
                    or (candidate_sku_key and row_sku_id == candidate_sku_key)
                ):
                    sku_fallback.append(row)
            elif line_count == 1:
                general_fallback.append(row)
            elif _is_recovered_blank_order_entry(candidate):
                general_fallback.append(row)
    if exact:
        return exact
    if sku_fallback:
        return sku_fallback[:1]
    return general_fallback[:1]


def evaluate_order_cashflow_coverage_conn(
    conn: sqlite3.Connection,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    required = {"order_status_event", "fact_cashflow_events"}
    missing_tables = sorted(table for table in required if not _table_exists(conn, table))
    if missing_tables:
        return {
            "status": "FAIL",
            "missing_tables": missing_tables,
            "candidate_line_count": 0,
            "cash_in_missing_count": 0,
            "modeled_receivables_count": 0,
            "balance_anchor_fake_cash_in_count": 0,
            "duplicate_cash_in_count": 0,
            "missing_line_evidence_count": 0,
            "deterministic_exception_count": 0,
            "still_blocked_source_missing_count": 0,
            "samples": {},
        }

    candidates = _build_d1_candidates(conn, as_of=as_of)
    cash = _cash_rows(conn)
    positive_cash = _positive_cash_index(cash)
    line_counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        key = (candidate["order_id"], candidate["store_code"])
        line_counts[key] = line_counts.get(key, 0) + 1

    missing_cash: list[dict[str, Any]] = []
    duplicate_cash: list[dict[str, Any]] = []
    missing_line_evidence = [c for c in candidates if c.get("source") == "missing_line_evidence"]
    deterministic_exceptions = [
        c for c in candidates if c.get("classification") == "deterministic_exception"
    ]
    still_blocked_source_missing = missing_line_evidence
    for candidate in candidates:
        key = (candidate["order_id"], candidate["store_code"])
        matches = _matching_positive_cash(
            candidate,
            _candidate_cash_rows(candidate, positive_cash),
            line_counts.get(key, 1),
        )
        if not matches:
            missing_cash.append(candidate)
        elif len(matches) > 1:
            duplicate_cash.append(candidate)

    receivable_rows = []
    if _table_exists(conn, "fact_cashflow_events"):
        receivable_rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT event_date, event_type, account, amount_kzt, ref_type, ref_id, source
                FROM fact_cashflow_events
                WHERE COALESCE(amount_kzt, 0) > 0
                  AND (
                        UPPER(COALESCE(account, '')) LIKE '%RECEIVABLE%'
                     OR UPPER(COALESCE(event_type, '')) LIKE '%RECEIVABLE%'
                  )
                """
            ).fetchall()
            if _is_receivable_leak(row)
        ]

    fake_anchor_rows = [row for row in cash if _event_is_balance_anchor_cash_in(row)]
    status = (
        "PASS"
        if not missing_cash and not duplicate_cash and not receivable_rows and not fake_anchor_rows and not missing_line_evidence
        else "FAIL"
    )
    return {
        "status": status,
        "missing_tables": [],
        "candidate_line_count": len(candidates),
        "cash_in_missing_count": len(missing_cash),
        "modeled_receivables_count": len(receivable_rows),
        "balance_anchor_fake_cash_in_count": len(fake_anchor_rows),
        "duplicate_cash_in_count": len(duplicate_cash),
        "missing_line_evidence_count": len(missing_line_evidence),
        "deterministic_exception_count": len(deterministic_exceptions),
        "still_blocked_source_missing_count": len(still_blocked_source_missing),
        "samples": {
            "cash_in_missing": missing_cash[:10],
            "duplicate_cash_in": duplicate_cash[:10],
            "modeled_receivables": receivable_rows[:10],
            "balance_anchor_fake_cash_in": fake_anchor_rows[:10],
            "missing_line_evidence": missing_line_evidence[:10],
            "deterministic_exception": deterministic_exceptions[:10],
            "still_blocked_source_missing": still_blocked_source_missing[:10],
        },
    }


def evaluate_order_cashflow_coverage(db_path: Path, *, as_of: str | None = None) -> dict[str, Any]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return evaluate_order_cashflow_coverage_conn(conn, as_of=as_of)


def evaluate_actual_model_separation_conn(
    conn: sqlite3.Connection,
    *,
    anchor_date: str,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    missing_tables = sorted(
        table for table in ("fact_cashflow_events", "fact_cashflow_daily") if not _table_exists(conn, table)
    )
    if missing_tables:
        return {
            "status": "FAIL",
            "missing_tables": missing_tables,
            "modeled_receivables_count": 0,
            "legacy_modeled_receivables_diagnostic_count": 0,
            "paid_truth_receivables_daily_count": 0,
            "balance_anchor_fake_cash_in_count": 0,
            "actual_model_cash_overlap_count": 0,
            "samples": {},
        }

    event_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT event_date, event_type, account, amount_kzt, store_code, ref_type, ref_id, source
            FROM fact_cashflow_events
            WHERE date(event_date) <= date(?)
            """,
            (anchor_date,),
        ).fetchall()
    ]
    legacy = [row for row in event_rows if _is_legacy_receivable_diagnostic(row)]
    leaks = [row for row in event_rows if _is_receivable_leak(row)]
    fake_anchor = [row for row in event_rows if _event_is_balance_anchor_cash_in(row)]
    paid_truth_daily = [
        dict(row)
        for row in conn.execute(
            """
            SELECT date, receivables_open, receivables_close, receivables_flow_kzt
            FROM fact_cashflow_daily
            WHERE date(date) <= date(?)
              AND (
                    ABS(COALESCE(receivables_open, 0)) > 0.01
                 OR ABS(COALESCE(receivables_close, 0)) > 0.01
                 OR ABS(COALESCE(receivables_flow_kzt, 0)) > 0.01
              )
            """,
            (anchor_date,),
        ).fetchall()
    ]

    actual_cash_keys = {
        (
            _date_part(row.get("event_date")),
            _upper(row.get("store_code")),
            str(row.get("ref_type") or "").strip(),
            str(row.get("ref_id") or "").strip(),
        )
        for row in event_rows
        if _upper(row.get("event_type")) == "CASH_IN"
        and _upper(row.get("source")) == "STATEMENT_ACTUAL"
        and _as_float(row.get("amount_kzt")) > 0
    }
    model_cash_overlap = [
        row
        for row in event_rows
        if _upper(row.get("event_type")) == "CASH_IN"
        and _upper(row.get("source")) == "ORDER_MODELLED"
        and _as_float(row.get("amount_kzt")) > 0
        and (
            _date_part(row.get("event_date")),
            _upper(row.get("store_code")),
            str(row.get("ref_type") or "").strip(),
            str(row.get("ref_id") or "").strip(),
        )
        in actual_cash_keys
    ]

    status = (
        "PASS"
        if not leaks and not paid_truth_daily and not fake_anchor and not model_cash_overlap
        else "FAIL"
    )
    return {
        "status": status,
        "missing_tables": [],
        "modeled_receivables_count": len(leaks),
        "legacy_modeled_receivables_diagnostic_count": len(legacy),
        "paid_truth_receivables_daily_count": len(paid_truth_daily),
        "balance_anchor_fake_cash_in_count": len(fake_anchor),
        "actual_model_cash_overlap_count": len(model_cash_overlap),
        "samples": {
            "modeled_receivables": leaks[:10],
            "legacy_modeled_receivables_diagnostic": legacy[:10],
            "paid_truth_receivables_daily": paid_truth_daily[:10],
            "balance_anchor_fake_cash_in": fake_anchor[:10],
            "actual_model_cash_overlap": model_cash_overlap[:10],
        },
    }


def evaluate_actual_model_separation(db_path: Path, *, anchor_date: str) -> dict[str, Any]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return evaluate_actual_model_separation_conn(conn, anchor_date=anchor_date)


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
