from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.ads.active_scope import (
    ADVERTISED_PRODUCTS_ONLY_MODE,
    is_store_active_on,
    resolve_store_coverage_mode_on,
)
from core.cashflow.order_cashflow_validation import evaluate_order_cashflow_coverage_conn


DELIVERED_STAGES = {"COMPLETED", "DELIVERED"}
DELIVERED_SALES_STATUSES = {"COMPLETED", "DELIVERED", "SOLD"}
RETURN_STAGES = {
    "RETURNED",
    "RETURN",
    "REFUND",
    "CANCELLED_AFTER_DELIVERY",
    "CANCELLED_DELIVERED",
}
RETURN_RESTOCK_TYPES = {"RETURN", "RESTOCK", "INVENTORY_RETURN"}
RECEIVED_PO_STATUSES = {"RECEIVED", "ARRIVED", "CLOSED", "DONE"}
OPEN_PO_STATUSES = {"PENDING", "PARTIAL", "IN_TRANSIT", "CONFIRMED", "SHIPPED", "PAID_NOT_SHIPPED"}
VALID_ADS_REFRESH_STATUSES = {"SUCCESS", "PASS", "OK", "COMPLETE", "COMPLETED"}
VALID_ADS_COVERAGE_STATUSES = {
    "COVERED",
    "COMPLETE",
    "COMPLETED",
    "OK",
    "MAPPED",
    "NO_SPEND_VERIFIED",
}
VALID_INBOUND_REFERENCE_TYPES = {
    "PO_LINE",
    "PO_INBOUND_LINE",
    "PO_PART",
    "PO_INBOUND_PART",
}
PRODUCT_IDENTITY_QUARANTINE_TABLE = "fact_order_entry_product_identity_quarantine"
PRODUCT_IDENTITY_QUARANTINE_REASON = "MISSING_APPROVED_CANONICAL_PRODUCT_IDENTITY"
HEADER_ONLY_SOURCE_GAP_QUARANTINE_TABLE = "fact_order_entry_header_only_source_gap_quarantine"
HEADER_ONLY_SOURCE_GAP_REASON = "HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE"
PRODUCT_CASHFLOW_EVENT_TYPES = {"COGS_RECOGNIZED", "INVENTORY_MOVE"}


def _sql_in_values(values: set[str]) -> str:
    return ", ".join("'" + str(value).replace("'", "''") + "'" for value in sorted(values))


@dataclass(frozen=True)
class GateFinding:
    code: str
    severity: str
    message: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class IntegrationGateReport:
    status: str
    as_of: str | None
    findings: list[GateFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "as_of": self.as_of,
            "finding_count": len(self.findings),
            "findings": [asdict(finding) for finding in self.findings],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def evaluate_operational_stock_integration_gates(
    db_path: Path,
    *,
    as_of: str | None = None,
    tolerance: float = 0.01,
) -> IntegrationGateReport:
    """Evaluate Agent 7 fail-closed gates without mutating the DB."""

    findings: list[GateFinding] = []
    if not Path(db_path).exists():
        findings.append(
            GateFinding(
                code="DB_MISSING",
                severity="ERROR",
                message="Operational DB is missing; cannot make stock-linked decisions green.",
                evidence={"db_path": str(db_path)},
            )
        )
        return IntegrationGateReport(status="RED", as_of=as_of, findings=findings)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        _check_sales_order_lifecycle(conn, findings, as_of=as_of)
        _check_return_qc(conn, findings)
        _check_po_inbound(conn, findings, as_of=as_of, tolerance=tolerance)
        _check_ads_coverage(conn, findings, as_of=as_of)
        _check_cashflow_d1(conn, findings, as_of=as_of)
        _check_cashflow_roll_forward(conn, findings, tolerance=tolerance)

    status = "RED" if any(f.severity == "ERROR" for f in findings) else "GREEN"
    return IntegrationGateReport(status=status, as_of=as_of, findings=findings)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _relation_exists(conn: sqlite3.Connection, relation: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
            (relation,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _missing_tables(conn: sqlite3.Connection, required: tuple[str, ...]) -> list[str]:
    return [table for table in required if not _table_exists(conn, table)]


def _add(
    findings: list[GateFinding],
    *,
    code: str,
    message: str,
    evidence: dict[str, Any],
    severity: str = "ERROR",
) -> None:
    findings.append(
        GateFinding(
            code=code,
            severity=severity,
            message=message,
            evidence={key: value for key, value in evidence.items() if value is not None},
        )
    )


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _date_part(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:10]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _store_clause(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return f"UPPER(COALESCE({prefix}store_code, 'UNIVERSAL'))"


def _sales_where(conn: sqlite3.Connection, *, alias: str = "", as_of: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    cols = _columns(conn, "sales_fact_v2")
    clauses = [
        f"UPPER(COALESCE({prefix}status, '')) IN ({','.join(repr(s) for s in sorted(DELIVERED_SALES_STATUSES))})"
    ]
    if "return_flag" in cols:
        clauses.append(f"COALESCE({prefix}return_flag, 0) = 0")
    if as_of and "order_date" in cols:
        clauses.append(f"date({prefix}order_date) <= date('{as_of}')")
    return " AND ".join(clauses)


def _check_sales_order_lifecycle(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    *,
    as_of: str | None,
) -> None:
    missing = _missing_tables(conn, ("sales_fact_v2", "order_status_event", "fact_order_entries_kaspi"))
    if missing:
        _add(
            findings,
            code="ORDER_SALES_TABLE_MISSING",
            message="Sales/order lifecycle gate cannot run because required tables are missing.",
            evidence={"missing_tables": missing},
        )
        return

    where = _sales_where(conn, as_of=as_of)
    duplicates = conn.execute(
        f"""
        SELECT
            order_id,
            COALESCE(store_code, 'UNIVERSAL') AS store_code,
            COALESCE(sku_id, '') AS sku_id,
            COALESCE(sku_key, '') AS sku_key,
            COALESCE(my_size, '') AS my_size,
            COALESCE(kaspi_offer_name, '') AS kaspi_offer_name,
            COUNT(*) AS row_count,
            SUM(COALESCE(quantity, 0)) AS quantity
        FROM sales_fact_v2
        WHERE {where}
        GROUP BY order_id, COALESCE(store_code, 'UNIVERSAL'), COALESCE(sku_id, ''),
                 COALESCE(sku_key, ''), COALESCE(my_size, ''), COALESCE(kaspi_offer_name, '')
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for row in duplicates:
        _add(
            findings,
            code="SALES_ORDER_DUPLICATE",
            message="Delivered sales projection contains duplicate rows for the same order/SKU grain.",
            evidence=dict(row),
        )

    sales_rows = conn.execute(
        f"""
        SELECT
            rowid AS row_id,
            order_id,
            COALESCE(store_code, 'UNIVERSAL') AS store_code,
            COALESCE(sku_id, '') AS sku_id,
            COALESCE(sku_key, '') AS sku_key,
            COALESCE(my_size, '') AS my_size,
            COALESCE(kaspi_offer_name, '') AS kaspi_offer_name
        FROM sales_fact_v2
        WHERE {where}
        """
    ).fetchall()
    completed_pairs = {
        (_upper(row["store_code"]) or "UNIVERSAL", str(row["order_id"] or "").strip())
        for row in conn.execute(
            f"""
            SELECT store_code, order_id
            FROM order_status_event
            WHERE UPPER(COALESCE(stage_code, '')) IN ({','.join(repr(s) for s in sorted(DELIVERED_STAGES))})
            """
        ).fetchall()
        if str(row["order_id"] or "").strip()
    }
    entry_pairs = {
        (_upper(row["store_code"]) or "UNIVERSAL", str(row["order_id"] or "").strip())
        for row in conn.execute(
            """
            SELECT store_code, order_id
            FROM fact_order_entries_kaspi
            """
        ).fetchall()
        if str(row["order_id"] or "").strip()
    }
    quarantine_rows = _active_product_identity_quarantines(conn)
    _check_product_identity_quarantine_integrity(conn, findings, quarantine_rows)
    header_only_quarantine_rows = _active_header_only_source_gap_quarantines(conn)
    _check_header_only_source_gap_quarantine_integrity(conn, findings, header_only_quarantine_rows)
    for row in sales_rows:
        order_id = str(row["order_id"] or "").strip()
        store_code = str(row["store_code"] or "UNIVERSAL").strip().upper()
        pair = (store_code, order_id)
        if not order_id:
            _add(
                findings,
                code="SALES_ORDER_ID_MISSING",
                message="Delivered sales row has no order_id and cannot bind to lifecycle truth.",
                evidence=dict(row),
            )
            continue

        if (store_code, order_id) not in completed_pairs:
            _add(
                findings,
                code="ORDER_LIFECYCLE_MISSING_COMPLETED",
                message="Delivered sales row lacks a matching completed lifecycle event.",
                evidence={"order_id": order_id, "store_code": store_code, "row_id": row["row_id"]},
            )

        if pair not in entry_pairs:
            quarantine = quarantine_rows.get(pair)
            if quarantine is not None:
                blockers = _product_identity_quarantine_blockers(conn, quarantine)
                if not blockers:
                    _add(
                        findings,
                        code="ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED",
                        severity="WARN",
                        message=(
                            "Delivered order is missing canonical product identity and is "
                            "excluded from product-level stock, COGS, and profit publication."
                        ),
                        evidence={
                            "order_id": order_id,
                            "store_code": store_code,
                            "row_id": row["row_id"],
                            "reason_code": quarantine.get("reason_code"),
                        },
                    )
                    continue
            header_only_quarantine = header_only_quarantine_rows.get(pair)
            if header_only_quarantine is not None:
                header_only_blockers = _header_only_source_gap_quarantine_blockers(
                    conn,
                    header_only_quarantine,
                )
                if not header_only_blockers:
                    _add(
                        findings,
                        code="ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED",
                        severity="WARN",
                        message=(
                            "Delivered order has only header-level source evidence; it remains "
                            "visible as a warning and is excluded from product-level stock, COGS, "
                            "profit, and SKU publication truth."
                        ),
                        evidence={
                            "order_id": order_id,
                            "store_code": store_code,
                            "row_id": row["row_id"],
                            "reason_code": header_only_quarantine.get("reason_code"),
                            "header_source_file": header_only_quarantine.get("header_source_file"),
                        },
                    )
                    continue
            _add(
                findings,
                code="ORDER_ENTRY_MISSING",
                message=(
                    "Delivered sales row lacks a canonical Kaspi order entry row."
                    if quarantine is None and header_only_quarantine_rows.get(pair) is None
                    else "Delivered sales row has a quarantine row but lacks complete publication-exclusion proof."
                ),
                evidence={
                    "order_id": order_id,
                    "store_code": store_code,
                    "row_id": row["row_id"],
                    "quarantine_present": quarantine is not None,
                    "quarantine_blockers": blockers if quarantine is not None else None,
                    "header_only_quarantine_present": header_only_quarantine_rows.get(pair) is not None,
                    "header_only_quarantine_blockers": (
                        header_only_blockers if header_only_quarantine_rows.get(pair) is not None else None
                    ),
                },
            )


def _active_product_identity_quarantines(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not _table_exists(conn, PRODUCT_IDENTITY_QUARANTINE_TABLE):
        return {}
    cols = _columns(conn, PRODUCT_IDENTITY_QUARANTINE_TABLE)
    if not {"store_code", "order_id"}.issubset(cols):
        return {}

    select_cols = [
        "store_code",
        "order_id",
        "sale_id",
        "order_date",
        "reason_code",
        "api_entry_ids",
        "api_offer_codes",
        "api_product_ids",
        "api_entry_count",
        "api_entries_with_complete_sku_id_size",
        "publication_exclusion_required",
        "product_stock_excluded",
        "product_cogs_excluded",
        "product_profit_excluded",
        "sku_publication_excluded",
        "publication_exclusion_proof_json",
        "active_flag",
        "evidence_source",
    ]
    expressions = []
    for col in select_cols:
        if col in cols:
            expressions.append(col)
        elif col in {"api_entry_count", "api_entries_with_complete_sku_id_size"}:
            expressions.append(f"0 AS {col}")
        elif col in {
            "publication_exclusion_required",
            "product_stock_excluded",
            "product_cogs_excluded",
            "product_profit_excluded",
            "sku_publication_excluded",
            "active_flag",
        }:
            default = 1 if col in {"publication_exclusion_required", "active_flag"} else 0
            expressions.append(f"{default} AS {col}")
        else:
            expressions.append(f"'' AS {col}")

    active_where = "COALESCE(active_flag, 1) = 1" if "active_flag" in cols else "1 = 1"
    rows = conn.execute(
        f"""
        SELECT {', '.join(expressions)}
        FROM {PRODUCT_IDENTITY_QUARANTINE_TABLE}
        WHERE {active_where}
        """
    ).fetchall()
    payload: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        store_code = _upper(row["store_code"]) or "UNIVERSAL"
        order_id = str(row["order_id"] or "").strip()
        if order_id:
            payload[(store_code, order_id)] = dict(row)
    return payload


def _quarantine_text_present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _json_object_present(value: Any) -> bool:
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return False
    return isinstance(parsed, dict) and bool(parsed)


def _json_object(value: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    return parsed


def _product_identity_quarantine_blockers(
    conn: sqlite3.Connection,
    quarantine: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    store_code = _upper(quarantine.get("store_code")) or "UNIVERSAL"
    order_id = str(quarantine.get("order_id") or "").strip()
    reason_code = _upper(quarantine.get("reason_code"))
    if reason_code != PRODUCT_IDENTITY_QUARANTINE_REASON:
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_REASON_INVALID",
                "reason_code": quarantine.get("reason_code"),
            }
        )
    for field in ("api_entry_ids", "api_offer_codes", "api_product_ids"):
        if not _quarantine_text_present(quarantine.get(field)):
            blockers.append({"code": "ORDER_ENTRY_QUARANTINE_API_EVIDENCE_MISSING", "field": field})
    if _as_int(quarantine.get("publication_exclusion_required")) != 1:
        blockers.append({"code": "ORDER_ENTRY_QUARANTINE_PUBLICATION_EXCLUSION_NOT_REQUIRED"})
    proof_flags = (
        "product_stock_excluded",
        "product_cogs_excluded",
        "product_profit_excluded",
        "sku_publication_excluded",
    )
    missing_flags = [
        flag for flag in proof_flags if _as_int(quarantine.get(flag)) != 1
    ]
    if missing_flags or not _json_object_present(quarantine.get("publication_exclusion_proof_json")):
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_PUBLICATION_EXCLUSION_MISSING",
                "missing_flags": missing_flags,
            }
        )

    entry_count = _as_int(quarantine.get("api_entry_count"))
    complete_entries = _as_int(quarantine.get("api_entries_with_complete_sku_id_size"))
    canonical_entry_count = 0
    if _table_exists(conn, "fact_order_entries_kaspi"):
        canonical_entry_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_order_entries_kaspi
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    if canonical_entry_count and (entry_count <= 0 or complete_entries < entry_count):
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_PARTIAL_ENTRY_LEAK",
                "fact_order_entries_count": canonical_entry_count,
                "api_entry_count": entry_count,
                "api_entries_with_complete_sku_id_size": complete_entries,
            }
        )

    stock_count = 0
    if _table_exists(conn, "stock_ledger"):
        stock_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM stock_ledger
                WHERE CAST(reference_id AS TEXT) = ?
                """,
                (order_id,),
            ).fetchone()[0]
        )
    if stock_count:
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_PRODUCT_STOCK_LEAK",
                "stock_ledger_reference_count": stock_count,
            }
        )

    product_cashflow_count = 0
    if _table_exists(conn, "fact_cashflow_events"):
        product_cashflow_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_cashflow_events
                WHERE CAST(ref_id AS TEXT) = ?
                  AND (
                    UPPER(COALESCE(event_type, '')) IN ('COGS_RECOGNIZED', 'INVENTORY_MOVE')
                    OR UPPER(COALESCE(event_type, '')) LIKE '%COGS%'
                    OR UPPER(COALESCE(account, '')) LIKE 'INVENTORY_%'
                    OR UPPER(COALESCE(account, '')) = 'COGS'
                  )
                """,
                (order_id,),
            ).fetchone()[0]
        )
    if product_cashflow_count:
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_PRODUCT_COGS_LEAK",
                "product_cashflow_reference_count": product_cashflow_count,
            }
        )

    sales_fact_profit_count = 0
    sales_cols = _columns(conn, "sales_fact_v2")
    if _table_exists(conn, "sales_fact_v2") and {"store_code", "order_id"} <= sales_cols:
        profit_clauses = []
        if "cogs" in sales_cols:
            profit_clauses.append("cogs IS NOT NULL")
        if "profit" in sales_cols:
            profit_clauses.append("profit IS NOT NULL")
        profit_where = " OR ".join(profit_clauses) or "0"
        sales_fact_profit_count = _as_int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM sales_fact_v2
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                  AND ({profit_where})
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    published_profit_count = 0
    if _relation_exists(conn, "view_sales_line_truth"):
        published_profit_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM view_sales_line_truth
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    if sales_fact_profit_count or published_profit_count:
        blockers.append(
            {
                "code": "ORDER_ENTRY_QUARANTINE_PRODUCT_PROFIT_LEAK",
                "sales_fact_cogs_profit_count": sales_fact_profit_count,
                "published_sales_truth_line_count": published_profit_count,
            }
        )
    return blockers


def _active_header_only_source_gap_quarantines(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not _table_exists(conn, HEADER_ONLY_SOURCE_GAP_QUARANTINE_TABLE):
        return {}
    cols = _columns(conn, HEADER_ONLY_SOURCE_GAP_QUARANTINE_TABLE)
    if not {"store_code", "order_id"}.issubset(cols):
        return {}

    select_cols = [
        "store_code",
        "order_id",
        "sale_id",
        "order_date",
        "reason_code",
        "header_sku_key",
        "header_sku_id",
        "header_my_size",
        "header_kaspi_offer_name",
        "header_quantity",
        "header_source_file",
        "source_hierarchy_checked_json",
        "publication_exclusion_required",
        "product_stock_excluded",
        "product_cogs_excluded",
        "product_profit_excluded",
        "sku_publication_excluded",
        "publication_exclusion_proof_json",
        "owner_or_codecaptain_review_status",
        "active_flag",
    ]
    expressions = []
    for col in select_cols:
        if col in cols:
            expressions.append(col)
        elif col in {
            "publication_exclusion_required",
            "product_stock_excluded",
            "product_cogs_excluded",
            "product_profit_excluded",
            "sku_publication_excluded",
            "active_flag",
        }:
            default = 1 if col in {"publication_exclusion_required", "active_flag"} else 0
            expressions.append(f"{default} AS {col}")
        else:
            expressions.append(f"'' AS {col}")

    active_where = "COALESCE(active_flag, 1) = 1" if "active_flag" in cols else "1 = 1"
    rows = conn.execute(
        f"""
        SELECT {', '.join(expressions)}
        FROM {HEADER_ONLY_SOURCE_GAP_QUARANTINE_TABLE}
        WHERE {active_where}
        """
    ).fetchall()
    payload: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        store_code = _upper(row["store_code"]) or "UNIVERSAL"
        order_id = str(row["order_id"] or "").strip()
        if order_id:
            payload[(store_code, order_id)] = dict(row)
    return payload


def _product_leakage_blockers(
    conn: sqlite3.Connection,
    *,
    store_code: str,
    order_id: str,
    code_prefix: str,
    allow_fact_order_entries: bool,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    canonical_entry_count = 0
    if _table_exists(conn, "fact_order_entries_kaspi"):
        canonical_entry_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_order_entries_kaspi
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    if canonical_entry_count and not allow_fact_order_entries:
        blockers.append(
            {
                "code": f"{code_prefix}_ENTRY_LEAK",
                "fact_order_entries_count": canonical_entry_count,
            }
        )

    stock_count = 0
    if _table_exists(conn, "stock_ledger"):
        stock_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM stock_ledger
                WHERE CAST(reference_id AS TEXT) = ?
                """,
                (order_id,),
            ).fetchone()[0]
        )
    if stock_count:
        blockers.append(
            {
                "code": f"{code_prefix}_PRODUCT_STOCK_LEAK",
                "stock_ledger_reference_count": stock_count,
            }
        )

    product_cashflow_count = 0
    if _table_exists(conn, "fact_cashflow_events"):
        product_cashflow_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM fact_cashflow_events
                WHERE CAST(ref_id AS TEXT) = ?
                  AND (
                    UPPER(COALESCE(event_type, '')) IN ('COGS_RECOGNIZED', 'INVENTORY_MOVE')
                    OR UPPER(COALESCE(event_type, '')) LIKE '%COGS%'
                    OR UPPER(COALESCE(account, '')) LIKE 'INVENTORY_%'
                    OR UPPER(COALESCE(account, '')) = 'COGS'
                  )
                """,
                (order_id,),
            ).fetchone()[0]
        )
    if product_cashflow_count:
        blockers.append(
            {
                "code": f"{code_prefix}_PRODUCT_COGS_LEAK",
                "product_cashflow_reference_count": product_cashflow_count,
            }
        )

    sales_fact_profit_count = 0
    sales_cols = _columns(conn, "sales_fact_v2")
    if _table_exists(conn, "sales_fact_v2") and {"store_code", "order_id"} <= sales_cols:
        profit_clauses = []
        if "cogs" in sales_cols:
            profit_clauses.append("cogs IS NOT NULL")
        if "profit" in sales_cols:
            profit_clauses.append("profit IS NOT NULL")
        profit_where = " OR ".join(profit_clauses) or "0"
        sales_fact_profit_count = _as_int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM sales_fact_v2
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                  AND ({profit_where})
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    published_profit_count = 0
    if _relation_exists(conn, "view_sales_line_truth"):
        published_profit_count = _as_int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM view_sales_line_truth
                WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND CAST(order_id AS TEXT) = ?
                """,
                (store_code, order_id),
            ).fetchone()[0]
        )
    if sales_fact_profit_count or published_profit_count:
        blockers.append(
            {
                "code": f"{code_prefix}_PRODUCT_PROFIT_LEAK",
                "sales_fact_cogs_profit_count": sales_fact_profit_count,
                "published_sales_truth_line_count": published_profit_count,
            }
        )
    return blockers


def _header_only_source_gap_quarantine_blockers(
    conn: sqlite3.Connection,
    quarantine: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    store_code = _upper(quarantine.get("store_code")) or "UNIVERSAL"
    order_id = str(quarantine.get("order_id") or "").strip()
    reason_code = _upper(quarantine.get("reason_code"))
    if store_code != "STOREB":
        blockers.append(
            {
                "code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_STORE_INVALID",
                "store_code": quarantine.get("store_code"),
            }
        )
    if reason_code != HEADER_ONLY_SOURCE_GAP_REASON:
        blockers.append(
            {
                "code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_REASON_INVALID",
                "reason_code": quarantine.get("reason_code"),
            }
        )
    if not _quarantine_text_present(quarantine.get("header_source_file")):
        blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_HEADER_SOURCE_MISSING"})
    source_proof = _json_object(quarantine.get("source_hierarchy_checked_json"))
    if source_proof is None:
        blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_SOURCE_PROOF_MISSING"})
    else:
        if source_proof.get("approved_hierarchy_checked") is not True:
            blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_HIERARCHY_NOT_CHECKED"})
        if source_proof.get("real_item_entry_evidence_exists") is not False:
            blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_REAL_ENTRY_EVIDENCE_AMBIGUOUS"})
        if source_proof.get("crm_header_evidence_only") is not True:
            blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_NOT_HEADER_ONLY"})

    if _as_int(quarantine.get("publication_exclusion_required")) != 1:
        blockers.append({"code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PUBLICATION_EXCLUSION_NOT_REQUIRED"})
    proof_flags = (
        "product_stock_excluded",
        "product_cogs_excluded",
        "product_profit_excluded",
        "sku_publication_excluded",
    )
    missing_flags = [
        flag for flag in proof_flags if _as_int(quarantine.get(flag)) != 1
    ]
    if missing_flags or not _json_object_present(quarantine.get("publication_exclusion_proof_json")):
        blockers.append(
            {
                "code": "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PUBLICATION_EXCLUSION_MISSING",
                "missing_flags": missing_flags,
            }
        )

    blockers.extend(
        _product_leakage_blockers(
            conn,
            store_code=store_code,
            order_id=order_id,
            code_prefix="ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP",
            allow_fact_order_entries=False,
        )
    )
    return blockers


def _check_header_only_source_gap_quarantine_integrity(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    quarantine_rows: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for (store_code, order_id), quarantine in sorted(quarantine_rows.items()):
        for blocker in _header_only_source_gap_quarantine_blockers(conn, quarantine):
            code = str(blocker.get("code") or "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_INVALID")
            if code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PUBLICATION_EXCLUSION_MISSING":
                message = "Header-only source-gap quarantine lacks product publication-exclusion proof."
            elif code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_ENTRY_LEAK":
                message = "Header-only source-gap quarantine has canonical order-entry rows."
            elif code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_STOCK_LEAK":
                message = "Header-only source-gap quarantine still feeds product stock."
            elif code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK":
                message = "Header-only source-gap quarantine still feeds product-level COGS or inventory cashflow."
            elif code == "ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_PROFIT_LEAK":
                message = "Header-only source-gap quarantine still feeds product profit publication."
            else:
                message = "Header-only source-gap quarantine does not satisfy its proof contract."
            _add(
                findings,
                code=code,
                message=message,
                evidence={"order_id": order_id, "store_code": store_code, **blocker},
            )


def _check_product_identity_quarantine_integrity(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    quarantine_rows: dict[tuple[str, str], dict[str, Any]],
) -> None:
    for (store_code, order_id), quarantine in sorted(quarantine_rows.items()):
        for blocker in _product_identity_quarantine_blockers(conn, quarantine):
            code = str(blocker.get("code") or "ORDER_ENTRY_QUARANTINE_INVALID")
            if code == "ORDER_ENTRY_QUARANTINE_PUBLICATION_EXCLUSION_MISSING":
                message = "Quarantined order lacks proof that product-level publication surfaces exclude it."
            elif code == "ORDER_ENTRY_QUARANTINE_PARTIAL_ENTRY_LEAK":
                message = "Quarantined order has partial canonical entry rows without every API entry having exact product identity."
            elif code == "ORDER_ENTRY_QUARANTINE_PRODUCT_STOCK_LEAK":
                message = "Quarantined order still feeds product stock."
            elif code == "ORDER_ENTRY_QUARANTINE_PRODUCT_COGS_LEAK":
                message = "Quarantined order still feeds product-level COGS or inventory cashflow."
            elif code == "ORDER_ENTRY_QUARANTINE_PRODUCT_PROFIT_LEAK":
                message = "Quarantined order still feeds product profit publication."
            else:
                message = "Quarantined order does not satisfy the product-identity quarantine contract."
            _add(
                findings,
                code=code,
                message=message,
                evidence={"order_id": order_id, "store_code": store_code, **blocker},
            )


def _check_return_qc(conn: sqlite3.Connection, findings: list[GateFinding]) -> None:
    missing = _missing_tables(conn, ("order_status_event", "return_qc_event", "stock_ledger"))
    if missing:
        _add(
            findings,
            code="RETURN_QC_TABLE_MISSING",
            message="Return/QC gate cannot run because required tables are missing.",
            evidence={"missing_tables": missing},
        )
        return

    qc_rows = conn.execute(
        """
        SELECT qc_event_id, store_code, order_id, sku_id, quantity, qc_status,
               accepted_active_qty, quarantine_qty, rejected_qty, writeoff_qty
        FROM return_qc_event
        """
    ).fetchall()
    for row in qc_rows:
        total = (
            _as_int(row["accepted_active_qty"])
            + _as_int(row["quarantine_qty"])
            + _as_int(row["rejected_qty"])
            + _as_int(row["writeoff_qty"])
        )
        quantity = _as_int(row["quantity"])
        if quantity >= 0 and total != quantity:
            _add(
                findings,
                code="RETURN_QC_QUANTITY_MISMATCH",
                message="Return QC quantities must partition the returned quantity.",
                evidence={
                    "qc_event_id": row["qc_event_id"],
                    "order_id": row["order_id"],
                    "sku_id": row["sku_id"],
                    "quantity": quantity,
                    "partition_total": total,
                },
            )

    returned_orders = {
        (_upper(row["store_code"]) or "UNIVERSAL", str(row["order_id"] or "").strip())
        for row in conn.execute(
            f"""
            SELECT store_code, order_id
            FROM order_status_event
            WHERE UPPER(COALESCE(stage_code, '')) IN ({','.join(repr(s) for s in sorted(RETURN_STAGES))})
            """
        ).fetchall()
    }
    returned_order_ids = {order_id for _, order_id in returned_orders if order_id}

    restock_rows = conn.execute(
        f"""
        SELECT ledger_id, event_date, event_type, store_code, reference_id, reference_type,
               sku_id, qty_change
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) IN ({','.join(repr(s) for s in sorted(RETURN_RESTOCK_TYPES))})
          AND COALESCE(qty_change, 0) > 0
        """
    ).fetchall()
    for row in restock_rows:
        order_id = str(row["reference_id"] or "").strip()
        store_code = _upper(row["store_code"]) or "UNIVERSAL"
        if not order_id:
            _add(
                findings,
                code="RETURN_RESTOCK_REFERENCE_MISSING",
                message="Positive return/restock stock event has no order reference.",
                evidence={"ledger_id": row["ledger_id"], "sku_id": row["sku_id"]},
            )
            continue
        if returned_orders and order_id not in returned_order_ids:
            continue
        if store_code == "UNIVERSAL":
            accepted = conn.execute(
                """
                SELECT COALESCE(SUM(accepted_active_qty), 0)
                FROM return_qc_event
                WHERE order_id = ?
                  AND COALESCE(sku_id, '') = COALESCE(?, '')
                """,
                (order_id, row["sku_id"]),
            ).fetchone()[0]
        else:
            accepted = conn.execute(
                """
                SELECT COALESCE(SUM(accepted_active_qty), 0)
                FROM return_qc_event
                WHERE order_id = ?
                  AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
                  AND COALESCE(sku_id, '') = COALESCE(?, '')
                """,
                (order_id, store_code, row["sku_id"]),
            ).fetchone()[0]
        if _as_int(accepted) < _as_int(row["qty_change"]):
            _add(
                findings,
                code="RETURN_ACTIVE_WITHOUT_QC",
                message="Returned/cancelled units are entering active stock without accepted QC quantity.",
                evidence={
                    "ledger_id": row["ledger_id"],
                    "order_id": order_id,
                    "sku_id": row["sku_id"],
                    "qty_change": row["qty_change"],
                    "accepted_active_qty": accepted,
                },
            )


def _check_po_inbound(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    *,
    as_of: str | None,
    tolerance: float,
) -> None:
    missing = _missing_tables(conn, ("po_line", "stock_ledger", "fact_inventory_snapshot_size"))
    if missing:
        _add(
            findings,
            code="PO_INBOUND_TABLE_MISSING",
            message="PO/inbound gate cannot run because required tables are missing.",
            evidence={"missing_tables": missing},
        )
        return

    inbound_rows = conn.execute(
        """
        SELECT reference_type, reference_id, sku_id, SUM(qty_change) AS qty, COUNT(*) AS event_count
        FROM stock_ledger
        WHERE UPPER(COALESCE(event_type, '')) = 'INBOUND'
          AND COALESCE(qty_change, 0) > 0
        GROUP BY reference_type, reference_id, sku_id
        """
    ).fetchall()
    for row in inbound_rows:
        reference_type = _upper(row["reference_type"])
        reference_id = str(row["reference_id"] or "").strip()
        if reference_type not in VALID_INBOUND_REFERENCE_TYPES or not reference_id:
            _add(
                findings,
                code="PO_INBOUND_REFERENCE_NOT_LINE_GRAIN",
                message="Inbound stock event is not keyed to PO part/line grain.",
                evidence=dict(row),
            )
            continue
        received_qty = 0
        if "LINE" in reference_type:
            po_row = conn.execute(
                """
                SELECT received_qty
                FROM po_line
                WHERE CAST(po_line_id AS TEXT) = ?
                  AND COALESCE(sku_id, '') = COALESCE(?, '')
                """,
                (reference_id, row["sku_id"]),
            ).fetchone()
            if po_row is not None:
                received_qty = _as_int(po_row["received_qty"])
        else:
            po_row = conn.execute(
                """
                SELECT COALESCE(SUM(received_qty), 0) AS received_qty
                FROM po_line
                WHERE po_part_id = ?
                  AND COALESCE(sku_id, '') = COALESCE(?, '')
                """,
                (reference_id, row["sku_id"]),
            ).fetchone()
            if po_row is not None:
                received_qty = _as_int(po_row["received_qty"])
        if received_qty < _as_int(row["qty"]):
            _add(
                findings,
                code="PO_INBOUND_EXCEEDS_RECEIVED_QTY",
                message="Inbound stock events exceed received PO quantity at part/line grain.",
                evidence={**dict(row), "received_qty": received_qty},
            )

    snapshot_date = _latest_snapshot_date(conn, as_of=as_of)
    if snapshot_date is None:
        return
    snapshot_rows = conn.execute(
        """
        SELECT sku_id, SUM(COALESCE(inbound_stock, 0)) AS snapshot_inbound
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        GROUP BY sku_id
        HAVING SUM(COALESCE(inbound_stock, 0)) > 0
        """,
        (snapshot_date,),
    ).fetchall()
    open_inbound = _open_po_inbound_by_sku(conn)
    for row in snapshot_rows:
        sku_id = str(row["sku_id"] or "")
        snapshot_inbound = _as_float(row["snapshot_inbound"])
        expected_open = float(open_inbound.get(sku_id, 0))
        if snapshot_inbound - expected_open > tolerance:
            _add(
                findings,
                code="PO_INBOUND_DOUBLE_COUNT",
                message="Snapshot inbound exceeds open PO inbound; already received units may be double-counted.",
                evidence={
                    "snapshot_date": snapshot_date,
                    "sku_id": sku_id,
                    "snapshot_inbound": snapshot_inbound,
                    "open_po_inbound": expected_open,
                },
            )


def _latest_snapshot_date(conn: sqlite3.Connection, *, as_of: str | None) -> str | None:
    if as_of:
        row = conn.execute(
            """
            SELECT MAX(snapshot_date)
            FROM fact_inventory_snapshot_size
            WHERE date(snapshot_date) <= date(?)
            """,
            (as_of,),
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size").fetchone()
    return str(row[0]) if row and row[0] else None


def _open_po_inbound_by_sku(conn: sqlite3.Connection) -> dict[str, int]:
    has_header = _table_exists(conn, "po_header")
    join = "LEFT JOIN po_header ph ON ph.po_id = pl.po_id" if has_header else ""
    header_clause = (
        "AND UPPER(COALESCE(ph.status, '')) NOT IN ('CLOSED', 'CANCELLED')" if has_header else ""
    )
    rows = conn.execute(
        f"""
        SELECT pl.sku_id,
               SUM(CASE
                    WHEN COALESCE(pl.order_qty, 0) > COALESCE(pl.received_qty, 0)
                    THEN COALESCE(pl.order_qty, 0) - COALESCE(pl.received_qty, 0)
                    ELSE 0
               END) AS open_qty
        FROM po_line pl
        {join}
        WHERE UPPER(COALESCE(pl.status, '')) IN ({','.join(repr(s) for s in sorted(OPEN_PO_STATUSES))})
          {header_clause}
        GROUP BY pl.sku_id
        """
    ).fetchall()
    return {str(row["sku_id"] or ""): _as_int(row["open_qty"]) for row in rows}


def _check_ads_coverage(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    *,
    as_of: str | None,
) -> None:
    missing = _missing_tables(conn, ("sales_fact_v2", "ads_source_refresh_runs", "ads_campaign_product_daily"))
    if missing:
        _add(
            findings,
            code="ADS_TABLE_MISSING",
            message="Ads coverage gate cannot run because required tables are missing.",
            evidence={"missing_tables": missing},
        )
        return

    where = _sales_where(conn, as_of=as_of)
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            order_date AS sale_date,
            COALESCE(store_code, 'UNIVERSAL') AS store_code,
            COALESCE(sku_key, '') AS sku_key
        FROM sales_fact_v2
        WHERE {where}
          AND COALESCE(sku_key, '') <> ''
        """
    ).fetchall()
    for row in rows:
        sale_date = _date_part(row["sale_date"])
        store_code = str(row["store_code"] or "UNIVERSAL").strip()
        sku_key = str(row["sku_key"] or "").strip()
        if not sale_date:
            continue
        if not is_store_active_on(store_code, sale_date):
            continue
        coverage_mode = resolve_store_coverage_mode_on(store_code, sale_date)

        refresh = conn.execute(
            f"""
            SELECT run_id, status
            FROM ads_source_refresh_runs
            WHERE {_store_clause()} = UPPER(?)
              AND date(date_start) <= date(?)
              AND date(date_end) >= date(?)
            ORDER BY datetime(COALESCE(finished_at, started_at)) DESC
            LIMIT 1
            """,
            (store_code, sale_date, sale_date),
        ).fetchone()
        if refresh is None:
            _add(
                findings,
                code="ADS_REFRESH_MISSING",
                message="No ads source refresh covers a delivered sale date/store.",
                evidence={"sale_date": sale_date, "store_code": store_code, "sku_key": sku_key},
            )
        elif _upper(refresh["status"]) not in VALID_ADS_REFRESH_STATUSES:
            _add(
                findings,
                code="ADS_REFRESH_BLOCKED",
                message="Ads source refresh is missing/blocked/stale and cannot be treated as zero spend.",
                evidence={
                    "sale_date": sale_date,
                    "store_code": store_code,
                    "sku_key": sku_key,
                    "run_id": refresh["run_id"],
                    "status": refresh["status"],
                },
            )

        if coverage_mode == ADVERTISED_PRODUCTS_ONLY_MODE:
            month_coverage = conn.execute(
                f"""
                SELECT campaign_id, coverage_status, cost_kzt, source_run_id
                FROM ads_campaign_product_daily
                WHERE substr(date(date), 1, 7) = substr(date(?), 1, 7)
                  AND {_store_clause()} = UPPER(?)
                  AND sku_key = ?
                ORDER BY
                  CASE WHEN UPPER(TRIM(COALESCE(coverage_status, ''))) IN ({_sql_in_values(VALID_ADS_COVERAGE_STATUSES)}) THEN 0 ELSE 1 END,
                  date(date),
                  campaign_id
                LIMIT 1
                """,
                (sale_date, store_code, sku_key),
            ).fetchone()
            if month_coverage is None:
                continue
            status = _upper(month_coverage["coverage_status"])
            if status not in VALID_ADS_COVERAGE_STATUSES:
                _add(
                    findings,
                    code="ADS_COVERAGE_BLOCKED",
                    message="Advertised-product ads coverage is blocked/missing; cost_kzt must not be interpreted as zero spend.",
                    evidence=dict(month_coverage),
                )
            if month_coverage["cost_kzt"] is None:
                _add(
                    findings,
                    code="ADS_COST_MISSING",
                    message="Advertised-product ads coverage row has no cost value and cannot support profit decisions.",
                    evidence=dict(month_coverage),
                )
            continue

        coverage = conn.execute(
            f"""
            SELECT campaign_id, coverage_status, cost_kzt, source_run_id
            FROM ads_campaign_product_daily
            WHERE date(date) = date(?)
              AND {_store_clause()} = UPPER(?)
              AND sku_key = ?
            ORDER BY campaign_id
            LIMIT 1
            """,
            (sale_date, store_code, sku_key),
        ).fetchone()
        if coverage is None:
            _add(
                findings,
                code="ADS_COVERAGE_MISSING",
                message="No product-level ads coverage row exists for a delivered sale.",
                evidence={"sale_date": sale_date, "store_code": store_code, "sku_key": sku_key},
            )
            continue
        status = _upper(coverage["coverage_status"])
        if status not in VALID_ADS_COVERAGE_STATUSES:
            _add(
                findings,
                code="ADS_COVERAGE_BLOCKED",
                message="Ads coverage is blocked/missing; cost_kzt must not be interpreted as zero spend.",
                evidence=dict(coverage),
            )
        if coverage["cost_kzt"] is None:
            _add(
                findings,
                code="ADS_COST_MISSING",
                message="Ads coverage row has no cost value and cannot support profit decisions.",
                evidence=dict(coverage),
            )


def _check_cashflow_d1(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    *,
    as_of: str | None,
) -> None:
    report = evaluate_order_cashflow_coverage_conn(conn, as_of=as_of)
    if report["missing_tables"]:
        _add(
            findings,
            code="CASHFLOW_D1_TABLE_MISSING",
            message="D1 cashflow gate cannot run because required tables are missing.",
            evidence={"missing_tables": report["missing_tables"]},
        )
        return

    if report["cash_in_missing_count"]:
        _add(
            findings,
            code="CASHFLOW_D1_CASH_IN_MISSING",
            message="Delivered order lines lack same-day D1 cash-in events.",
            evidence={
                "count": report["cash_in_missing_count"],
                "samples": report["samples"].get("cash_in_missing", [])[:5],
            },
        )
    if report["modeled_receivables_count"]:
        _add(
            findings,
            code="CASHFLOW_D1_RECEIVABLES_MODELED",
            message="Paid-truth D1 cashflow still has modeled receivable leakage.",
            evidence={
                "count": report["modeled_receivables_count"],
                "samples": report["samples"].get("modeled_receivables", [])[:5],
            },
        )
    if report["balance_anchor_fake_cash_in_count"]:
        _add(
            findings,
            code="CASHFLOW_BALANCE_ANCHOR_FAKE_CASH_IN",
            message="Balance anchor evidence was converted into order-level CASH_IN.",
            evidence={
                "count": report["balance_anchor_fake_cash_in_count"],
                "samples": report["samples"].get("balance_anchor_fake_cash_in", [])[:5],
            },
        )
    if report["duplicate_cash_in_count"]:
        _add(
            findings,
            code="CASHFLOW_D1_DUPLICATE_CASH_IN",
            message="D1 order-line cash-in is not idempotent.",
            evidence={
                "count": report["duplicate_cash_in_count"],
                "samples": report["samples"].get("duplicate_cash_in", [])[:5],
            },
        )
    if report["missing_line_evidence_count"]:
        _add(
            findings,
            code="CASHFLOW_D1_LINE_EVIDENCE_MISSING",
            message="Delivered order lacks entry or sales line evidence for D1 cashflow.",
            evidence={
                "count": report["missing_line_evidence_count"],
                "samples": report["samples"].get("missing_line_evidence", [])[:5],
            },
        )


def _check_cashflow_roll_forward(
    conn: sqlite3.Connection,
    findings: list[GateFinding],
    *,
    tolerance: float,
) -> None:
    if not _table_exists(conn, "fact_cashflow_daily"):
        _add(
            findings,
            code="CASHFLOW_DAILY_TABLE_MISSING",
            message="Cashflow roll-forward gate cannot run because fact_cashflow_daily is missing.",
            evidence={},
        )
        return
    cols = _columns(conn, "fact_cashflow_daily")
    required = {
        "date",
        "cash_open",
        "cash_close",
        "cash_flow_kzt",
        "receivables_open",
        "receivables_close",
        "receivables_flow_kzt",
        "inventory_cost_open",
        "inventory_cost_close",
        "inventory_cost_flow_kzt",
        "capital_close",
    }
    missing = sorted(required - cols)
    if missing:
        _add(
            findings,
            code="CASHFLOW_ROLL_FORWARD_COLUMNS_MISSING",
            message="Cashflow daily table lacks columns required for roll-forward validation.",
            evidence={"missing_columns": missing},
        )
        return

    rows = conn.execute("SELECT * FROM fact_cashflow_daily ORDER BY date").fetchall()
    if not rows:
        _add(
            findings,
            code="CASHFLOW_DAILY_EMPTY",
            message="Cashflow daily table is empty.",
            evidence={},
        )
        return

    previous: sqlite3.Row | None = None
    for row in rows:
        cash_ok = abs((_as_float(row["cash_open"]) + _as_float(row["cash_flow_kzt"])) - _as_float(row["cash_close"])) <= tolerance
        recv_ok = abs((_as_float(row["receivables_open"]) + _as_float(row["receivables_flow_kzt"])) - _as_float(row["receivables_close"])) <= tolerance
        inv_ok = abs((_as_float(row["inventory_cost_open"]) + _as_float(row["inventory_cost_flow_kzt"])) - _as_float(row["inventory_cost_close"])) <= tolerance
        capital_ok = abs(
            (
                _as_float(row["cash_close"])
                + _as_float(row["receivables_close"])
                + _as_float(row["inventory_cost_close"])
            )
            - _as_float(row["capital_close"])
        ) <= tolerance
        if not (cash_ok and recv_ok and inv_ok and capital_ok):
            _add(
                findings,
                code="CASHFLOW_ROLL_FORWARD_MISMATCH",
                message="Cashflow daily row does not satisfy roll-forward identities.",
                evidence={"date": row["date"]},
            )

        if previous is not None:
            reset_fields = []
            for open_field, close_field in (
                ("cash_open", "cash_close"),
                ("receivables_open", "receivables_close"),
                ("inventory_cost_open", "inventory_cost_close"),
            ):
                if abs(_as_float(row[open_field]) - _as_float(previous[close_field])) > tolerance:
                    reset_fields.append(
                        {
                            "field": open_field,
                            "open": row[open_field],
                            "previous_close": previous[close_field],
                        }
                    )
            if reset_fields:
                _add(
                    findings,
                    code="CASHFLOW_OPENING_RESET",
                    message="Cashflow roll-forward opening balances reset instead of carrying prior close.",
                    evidence={"date": row["date"], "fields": reset_fields},
                )
        previous = row
