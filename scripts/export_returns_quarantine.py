#!/usr/bin/env python3
"""Export return/cancel backlog and pending-QC quarantine queue.

This rollout is intentionally export-only. Returned/cancelled units are never
restored to active stock here; employee QC must create a future explicit event.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_order_stage import (  # noqa: E402
    StageCode,
    classify_kaspi_stage_from_db_row,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "returns_quarantine"
DEFAULT_SINCE = "2026-02-01"

RETURN_CANCEL_STAGES = {
    StageCode.CANCELLED,
    StageCode.CANCELLING,
    StageCode.RETURN_REQUESTED,
    StageCode.RETURNED,
}
RETURN_CANCEL_STATUSES = {
    "CANCELLED",
    "CANCELLING",
    "RETURNING",
    "RETURNED",
    "KASPI_DELIVERY_RETURN_REQUESTED",
}
BACKLOG_COLUMNS = [
    "as_of",
    "store_code",
    "order_code",
    "order_id",
    "line_id",
    "entry_id",
    "created_at",
    "status_change_date",
    "status_change_date_source",
    "api_state",
    "api_status",
    "stage_code",
    "internal_status",
    "returned_to_warehouse",
    "courier_transmission_date",
    "waybill_number",
    "delivery_mode",
    "cancel_reason",
    "article",
    "kaspi_offer_name",
    "seller_system_name",
    "sku_key",
    "sku_id",
    "mapped_size",
    "quantity",
    "line_total_kzt",
    "delivery_fee_seller_kzt",
    "source",
    "source_file",
    "source_file_format",
    "window_since",
    "window_until",
    "event_type",
    "physical_bucket",
    "sales_effect",
    "active_stock_effect",
    "quarantine_effect",
    "confidence",
    "exception_reason",
]
QC_COLUMNS = [
    "order_code",
    "store_code",
    "line_id",
    "sku_key",
    "sku_id",
    "mapped_size",
    "quantity",
    "status_change_date",
    "stage_code",
    "internal_status",
    "returned_to_warehouse",
    "suggested_action",
    "physical_bucket",
    "qc_status",
    "qc_notes",
    "exception_reason",
]


@dataclass(frozen=True)
class ExportResult:
    backlog_rows: list[dict[str, Any]]
    exception_rows: list[dict[str, Any]]
    qc_rows: list[dict[str, Any]]
    output_dir: Path | None = None
    summary: dict[str, Any] | None = None


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "n"}


def _quantity(value: Any) -> int:
    try:
        return max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        return 0


def _money(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return _norm(value)


def _status_change(row: dict[str, Any]) -> tuple[str, str]:
    for column, source in (
        ("status_updated_at", "DB_STATUS_UPDATED_AT_FALLBACK"),
        ("actual_shipment_date", "DB_ACTUAL_SHIPMENT_DATE_FALLBACK"),
        ("courier_transmission_date", "DB_COURIER_TRANSMISSION_DATE_FALLBACK"),
        ("created_at", "DB_CREATED_AT_FALLBACK"),
    ):
        value = _norm(row.get(column))
        if value:
            return value, source
    return "", "MISSING_STATUS_CHANGE_DATE"


def _load_article_map(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, str]]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    rows = conn.execute(
        """
        SELECT store_code, kaspi_article, sku_key, sku_id, kaspi_offer_name, kaspi_name_core
        FROM dim_kaspi_article_map
        WHERE COALESCE(active_flag, 1) = 1
          AND COALESCE(TRIM(kaspi_article), '') != ''
        """
    ).fetchall()
    return {
        (_upper(row["store_code"]), _norm(row["kaspi_article"])): {
            "sku_key": _norm(row["sku_key"]),
            "sku_id": _norm(row["sku_id"]),
            "kaspi_offer_name": _norm(row["kaspi_offer_name"]),
            "seller_system_name": _norm(row["kaspi_name_core"]),
        }
        for row in rows
    }


def _load_sku_sizes(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    if not _table_exists(conn, "dim_sku_size"):
        return {}
    rows = conn.execute(
        """
        SELECT sku_id, sku_key, my_size
        FROM dim_sku_size
        WHERE COALESCE(active_flag, 1) = 1
        """
    ).fetchall()
    return {
        _norm(row["sku_id"]): {
            "sku_key": _norm(row["sku_key"]),
            "mapped_size": _norm(row["my_size"]),
        }
        for row in rows
        if _norm(row["sku_id"])
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _candidate_orders(
    conn: sqlite3.Connection,
    *,
    since: str,
    as_of: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            id,
            order_id,
            store_code,
            kaspi_offer_name,
            sku_key,
            sku_id,
            my_size,
            assigned_size,
            quantity,
            unit_price_kzt,
            created_at,
            actual_shipment_date,
            kaspi_status,
            kaspi_status_detail,
            internal_status,
            status_updated_at,
            waybill_number,
            source,
            source_file,
            courier_transmission_date,
            delivery_mode,
            delivery_cost,
            delivery_cost_for_seller,
            returned_to_warehouse
        FROM fact_orders_kaspi
        WHERE (
            date(COALESCE(created_at, status_updated_at)) BETWEEN date(?) AND date(?)
            OR date(COALESCE(status_updated_at, created_at)) BETWEEN date(?) AND date(?)
        )
        ORDER BY store_code, order_id
        """,
        (since, as_of, since, as_of),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        stage = classify_kaspi_stage_from_db_row(row)
        status_values = {
            _upper(row.get("kaspi_status")),
            _upper(row.get("kaspi_status_detail")),
            _upper(row.get("internal_status")),
        }
        if (
            stage in RETURN_CANCEL_STAGES
            or bool(status_values & RETURN_CANCEL_STATUSES)
            or _truthy(row.get("returned_to_warehouse"))
        ):
            row["stage_code"] = stage.value
            candidates.append(row)
    return candidates


def _entries_by_order(conn: sqlite3.Connection, order_ids: set[str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not order_ids or not _table_exists(conn, "fact_order_entries_kaspi"):
        return {}
    placeholders = ",".join("?" for _ in sorted(order_ids))
    rows = conn.execute(
        f"""
        SELECT
            entry_id,
            order_id,
            store_code,
            product_id,
            offer_id,
            quantity,
            unit_price_kzt,
            total_price_kzt,
            delivery_cost_kzt,
            category_title
        FROM fact_order_entries_kaspi
        WHERE order_id IN ({placeholders})
        ORDER BY store_code, order_id, entry_number, entry_id
        """,
        tuple(sorted(order_ids)),
    ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (_upper(row["store_code"]), _norm(row["order_id"]))
        grouped.setdefault(key, []).append(dict(row))
    return grouped


def _resolve_line_identity(
    *,
    order: dict[str, Any],
    entry: dict[str, Any] | None,
    article_map: dict[tuple[str, str], dict[str, str]],
    sku_sizes: dict[str, dict[str, str]],
) -> tuple[dict[str, str], list[str], str]:
    store_code = _upper(order.get("store_code"))
    article = _norm((entry or {}).get("offer_id") or (entry or {}).get("product_id"))
    mapped = article_map.get((store_code, article)) if article else None
    if mapped and mapped.get("sku_key"):
        sku_id = mapped.get("sku_id") or ""
        sku_size = sku_sizes.get(sku_id, {})
        return (
            {
                "article": article,
                "sku_key": mapped["sku_key"],
                "sku_id": sku_id,
                "mapped_size": sku_size.get("mapped_size") or _norm(order.get("my_size") or order.get("assigned_size")),
                "kaspi_offer_name": mapped.get("kaspi_offer_name") or _norm(order.get("kaspi_offer_name")),
                "seller_system_name": mapped.get("seller_system_name") or "",
            },
            [],
            "HIGH_ENTRY_ARTICLE_MAP",
        )

    sku_key = _norm(order.get("sku_key"))
    sku_id = _norm(order.get("sku_id"))
    mapped_size = _norm(order.get("my_size") or order.get("assigned_size"))
    if sku_id in sku_sizes:
        sku_key = sku_key or sku_sizes[sku_id]["sku_key"]
        mapped_size = mapped_size or sku_sizes[sku_id]["mapped_size"]
    reasons: list[str] = []
    if not sku_key:
        reasons.append("MISSING_SKU_KEY")
    if not mapped_size:
        reasons.append("MISSING_SIZE")
    return (
        {
            "article": article,
            "sku_key": sku_key,
            "sku_id": sku_id,
            "mapped_size": mapped_size,
            "kaspi_offer_name": _norm(order.get("kaspi_offer_name")),
            "seller_system_name": "",
        },
        reasons,
        "MEDIUM_HEADER_IDENTITY" if not reasons else "LOW_EXCEPTION",
    )


def _effect_contract(
    *,
    stage_code: str,
    returned_to_warehouse: bool,
    courier_transmission_date: str,
    actual_shipment_date: str,
    quantity: int,
    has_exception: bool,
) -> dict[str, str]:
    if has_exception or quantity <= 0:
        return {
            "event_type": "EXCEPTION",
            "physical_bucket": "UNKNOWN_NEEDS_REVIEW",
            "sales_effect": "EXCEPTION",
            "active_stock_effect": "0",
            "quarantine_effect": "0",
        }
    stock_moved = bool(courier_transmission_date or actual_shipment_date)
    if stage_code == StageCode.RETURNED.value or returned_to_warehouse:
        return {
            "event_type": "RETURNED_TO_WAREHOUSE",
            "physical_bucket": "RETURNED_TO_WAREHOUSE",
            "sales_effect": "REVERSE_OR_EXCLUDE_RETURN",
            "active_stock_effect": "0",
            "quarantine_effect": f"+{quantity}",
        }
    if stage_code in {StageCode.CANCELLING.value, StageCode.RETURN_REQUESTED.value}:
        return {
            "event_type": "EXPECTED_RETURN",
            "physical_bucket": "EXPECTED_RETURN",
            "sales_effect": "NOT_FINAL_SALE",
            "active_stock_effect": "0",
            "quarantine_effect": f"+{quantity}",
        }
    if stage_code == StageCode.CANCELLED.value and stock_moved:
        return {
            "event_type": "CANCELLED_AFTER_STOCK_MOVED",
            "physical_bucket": "UNKNOWN_NEEDS_REVIEW",
            "sales_effect": "NOT_SALE",
            "active_stock_effect": "0",
            "quarantine_effect": f"+{quantity}",
        }
    return {
        "event_type": "CANCELLED_BEFORE_STOCK_MOVED",
        "physical_bucket": "NONE",
        "sales_effect": "NOT_SALE",
        "active_stock_effect": "0",
        "quarantine_effect": "0",
    }


def build_return_cancel_exports(
    *,
    db_path: Path = DEFAULT_DB,
    since: str = DEFAULT_SINCE,
    as_of: str,
) -> ExportResult:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        article_map = _load_article_map(conn)
        sku_sizes = _load_sku_sizes(conn)
        orders = _candidate_orders(conn, since=since, as_of=as_of)
        entries = _entries_by_order(
            conn,
            {_norm(row["order_id"]) for row in orders},
        )
    finally:
        conn.close()

    backlog_rows: list[dict[str, Any]] = []
    for order in orders:
        order_key = (_upper(order.get("store_code")), _norm(order.get("order_id")))
        order_entries = entries.get(order_key) or [None]
        for index, entry in enumerate(order_entries, start=1):
            line_identity, identity_reasons, confidence = _resolve_line_identity(
                order=order,
                entry=entry,
                article_map=article_map,
                sku_sizes=sku_sizes,
            )
            quantity = _quantity((entry or {}).get("quantity") if entry else order.get("quantity"))
            reasons = list(identity_reasons)
            if quantity <= 0:
                reasons.append("MISSING_OR_ZERO_QUANTITY")
            status_change_date, status_change_source = _status_change(order)
            line_id = _norm((entry or {}).get("entry_id")) or f"HEADER:{order['store_code']}:{order['order_id']}:{index}"
            effects = _effect_contract(
                stage_code=_norm(order.get("stage_code")),
                returned_to_warehouse=_truthy(order.get("returned_to_warehouse")),
                courier_transmission_date=_norm(order.get("courier_transmission_date")),
                actual_shipment_date=_norm(order.get("actual_shipment_date")),
                quantity=quantity,
                has_exception=bool(reasons),
            )
            line_total = (entry or {}).get("total_price_kzt")
            if line_total in (None, "") and order.get("unit_price_kzt") not in (None, ""):
                try:
                    line_total = float(order["unit_price_kzt"]) * quantity
                except (TypeError, ValueError):
                    line_total = ""
            row = {
                "as_of": as_of,
                "store_code": _upper(order.get("store_code")),
                "order_code": _norm(order.get("order_id")),
                "order_id": _norm(order.get("order_id")),
                "line_id": line_id,
                "entry_id": _norm((entry or {}).get("entry_id")),
                "created_at": _norm(order.get("created_at")),
                "status_change_date": status_change_date,
                "status_change_date_source": status_change_source,
                "api_state": _norm(order.get("kaspi_status")),
                "api_status": _norm(order.get("kaspi_status_detail")),
                "stage_code": _norm(order.get("stage_code")),
                "internal_status": _norm(order.get("internal_status")),
                "returned_to_warehouse": "1" if _truthy(order.get("returned_to_warehouse")) else "0",
                "courier_transmission_date": _norm(order.get("courier_transmission_date")),
                "waybill_number": _norm(order.get("waybill_number")),
                "delivery_mode": _norm(order.get("delivery_mode")),
                "cancel_reason": "",
                "article": line_identity["article"],
                "kaspi_offer_name": line_identity["kaspi_offer_name"],
                "seller_system_name": line_identity["seller_system_name"],
                "sku_key": line_identity["sku_key"],
                "sku_id": line_identity["sku_id"],
                "mapped_size": line_identity["mapped_size"],
                "quantity": str(quantity),
                "line_total_kzt": _money(line_total),
                "delivery_fee_seller_kzt": _money(
                    (entry or {}).get("delivery_cost_kzt")
                    if entry
                    else order.get("delivery_cost_for_seller") or order.get("delivery_cost")
                ),
                "source": _norm(order.get("source") or "DB"),
                "source_file": _norm(order.get("source_file")),
                "source_file_format": "SQLITE_DB",
                "window_since": since,
                "window_until": as_of,
                **effects,
                "confidence": confidence,
                "exception_reason": ";".join(dict.fromkeys(reasons)),
            }
            backlog_rows.append(row)

    exception_rows = [row for row in backlog_rows if row["exception_reason"]]
    qc_rows = [_qc_row(row) for row in backlog_rows if _needs_qc(row)]
    summary = _summarize(backlog_rows, exception_rows, qc_rows)
    return ExportResult(
        backlog_rows=backlog_rows,
        exception_rows=exception_rows,
        qc_rows=qc_rows,
        summary=summary,
    )


def _needs_qc(row: dict[str, Any]) -> bool:
    return row["returned_to_warehouse"] == "1"


def _qc_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "order_code": row["order_code"],
        "store_code": row["store_code"],
        "line_id": row["line_id"],
        "sku_key": row["sku_key"],
        "sku_id": row["sku_id"],
        "mapped_size": row["mapped_size"],
        "quantity": row["quantity"],
        "status_change_date": row["status_change_date"],
        "stage_code": row["stage_code"],
        "internal_status": row["internal_status"],
        "returned_to_warehouse": row["returned_to_warehouse"],
        "suggested_action": "INSPECT_CONDITION_AND_SIZE",
        "physical_bucket": row["physical_bucket"],
        "qc_status": "PENDING_QC",
        "qc_notes": "",
        "exception_reason": row["exception_reason"],
    }


def _summarize(
    backlog_rows: list[dict[str, Any]],
    exception_rows: list[dict[str, Any]],
    qc_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "backlog_rows": len(backlog_rows),
        "backlog_orders": len({row["order_id"] for row in backlog_rows}),
        "exception_rows": len(exception_rows),
        "qc_rows": len(qc_rows),
        "stage_counts": dict(Counter(row["stage_code"] for row in backlog_rows)),
        "event_counts": dict(Counter(row["event_type"] for row in backlog_rows)),
        "quarantine_units": sum(
            _quantity(row["quarantine_effect"].lstrip("+"))
            for row in backlog_rows
            if row["quarantine_effect"].startswith("+")
        ),
    }


def write_exports(
    result: ExportResult,
    *,
    output_dir: Path,
    since: str,
    as_of: str,
) -> ExportResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    backlog_csv = output_dir / "return_cancel_backlog.csv"
    exceptions_csv = output_dir / "return_cancel_exceptions.csv"
    qc_csv = output_dir / "employee_qc_queue.csv"
    summary_md = output_dir / "return_cancel_summary.md"
    _write_csv(backlog_csv, BACKLOG_COLUMNS, result.backlog_rows)
    _write_csv(exceptions_csv, BACKLOG_COLUMNS, result.exception_rows)
    _write_csv(qc_csv, QC_COLUMNS, result.qc_rows)
    summary_md.write_text(
        _summary_markdown(
            result.summary or {},
            since=since,
            as_of=as_of,
            backlog_csv=backlog_csv,
            exceptions_csv=exceptions_csv,
            qc_csv=qc_csv,
        ),
        encoding="utf-8",
    )
    return ExportResult(
        backlog_rows=result.backlog_rows,
        exception_rows=result.exception_rows,
        qc_rows=result.qc_rows,
        output_dir=output_dir,
        summary=result.summary,
    )


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summary_markdown(
    summary: dict[str, Any],
    *,
    since: str,
    as_of: str,
    backlog_csv: Path,
    exceptions_csv: Path,
    qc_csv: Path,
) -> str:
    lines = [
        "# Return/Cancel Quarantine Summary",
        "",
        f"- window: `{since}` to `{as_of}`",
        f"- backlog csv: `{backlog_csv}`",
        f"- exceptions csv: `{exceptions_csv}`",
        f"- employee QC queue csv: `{qc_csv}`",
        "",
        "## Counts",
        "",
        f"- backlog rows: `{summary.get('backlog_rows', 0)}`",
        f"- backlog orders: `{summary.get('backlog_orders', 0)}`",
        f"- exception rows: `{summary.get('exception_rows', 0)}`",
        f"- employee QC rows: `{summary.get('qc_rows', 0)}`",
        f"- quarantine / expected-quarantine units: `{summary.get('quarantine_units', 0)}`",
        "",
        "## Stage Counts",
        "",
    ]
    for key, value in sorted((summary.get("stage_counts") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Event Counts", ""])
    for key, value in sorted((summary.get("event_counts") or {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Contract Notes",
            "",
            "- Returned units are quarantine candidates only; they are not active stock.",
            "- QC rows default to `PENDING_QC`; no row is restocked, written off, or marked missing by this export.",
            "- `status_change_date` is DB fallback truth unless a future Archive/API status-date refresh is wired in.",
            "",
            "## Daily Automation Stopline",
            "",
            "- This export script is safe to run daily as a read-only artifact generator.",
            "- It is not yet wired into the daily pipeline because API/archive status-date freshness and entry coverage must be validated fail-closed first.",
            "- Required hook before pipeline integration: fresh Archive/API status-date export or validator proving current DB lifecycle coverage for cancelled/returned/current return-request rows.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export return/cancel quarantine backlog and pending QC queue")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or args.output_root / args.as_of
    result = build_return_cancel_exports(
        db_path=args.db,
        since=args.since,
        as_of=args.as_of,
    )
    result = write_exports(
        result,
        output_dir=output_dir,
        since=args.since,
        as_of=args.as_of,
    )
    summary = result.summary or {}
    print(f"return_cancel_backlog={output_dir / 'return_cancel_backlog.csv'}")
    print(f"return_cancel_summary={output_dir / 'return_cancel_summary.md'}")
    print(f"return_cancel_exceptions={output_dir / 'return_cancel_exceptions.csv'}")
    print(f"employee_qc_queue={output_dir / 'employee_qc_queue.csv'}")
    print(
        "summary: "
        f"backlog_rows={summary.get('backlog_rows', 0)} "
        f"backlog_orders={summary.get('backlog_orders', 0)} "
        f"exceptions={summary.get('exception_rows', 0)} "
        f"qc_rows={summary.get('qc_rows', 0)} "
        f"quarantine_units={summary.get('quarantine_units', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
