#!/usr/bin/env python3
"""Shadow direct feeder from fact_orders_kaspi to sales_fact_v2-shaped rows.

Phase 1 is report-only. Even when --apply and AB_DIRECT_FEEDER_APPLY=1 are
present, this script refuses to mutate sales_fact_v2 until the Phase 2 owner
decision exists.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "decommission" / "crm_excel_shadow"
APPLY_REFUSAL = "Phase 2 not enabled: owner decision retire_crm_excel_pipeline required"

sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import calc_delivery_fee, calc_net_rev  # noqa: E402
from core.ingest.sales_ingest import (  # noqa: E402
    build_sales_dedupe_key,
    normalize_store_code,
    resolve_sales_identity_detail,
)
from core.product_truth.rombik_kid30_alias import apply_rombik_kid30_alias  # noqa: E402
from core.utils.sku_normalize import normalize_sku_key, normalize_size  # noqa: E402


SHADOW_COLUMNS = [
    "run_id",
    "source_table",
    "source_row_id",
    "order_id",
    "store_code",
    "line_identity_key",
    "order_date",
    "order_date_basis",
    "source_order_date",
    "planned_shipment_date",
    "actual_shipment_date",
    "courier_transmission_date",
    "status_updated_date",
    "created_date",
    "sku_key",
    "sku_id",
    "my_size",
    "final_my_size_source",
    "kaspi_offer_name",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "delivery_fee_source",
    "net_rev",
    "net_rev_source",
    "cogs",
    "cogs_source",
    "profit",
    "profit_source",
    "status",
    "return_flag",
    "return_date",
    "source_file",
    "source_imported_at",
    "source_updated_at",
    "size_source",
    "size_confidence",
    "logical_dedupe_key",
    "db_unique_key",
    "existing_sale_id_logical",
    "existing_sale_id_db_unique",
]

UNMAPPED_COLUMNS = [
    "run_id",
    "source_lane",
    "reason",
    "source_row_id",
    "order_id",
    "store_code",
    "line_identity_key",
    "kaspi_offer_name",
    "source_sku_key",
    "source_sku_id",
    "assigned_size",
    "my_size",
    "final_my_size",
    "size_source",
    "created_date",
    "planned_shipment_date",
    "actual_shipment_date",
    "status_updated_date",
]


DATE_FILTER_COLUMNS = {
    "created_at": ["created_at"],
    "planned_shipment_date": ["planned_shipment_date"],
    "actual_shipment_date": ["actual_shipment_date"],
    "courier_transmission_date": ["courier_transmission_date"],
    "status_updated_at": ["status_updated_at"],
    "imported_at": ["imported_at"],
    "updated_at": ["updated_at"],
    "any_relevant": [
        "created_at",
        "planned_shipment_date",
        "actual_shipment_date",
        "courier_transmission_date",
        "status_updated_at",
        "imported_at",
        "updated_at",
    ],
}

ORDER_DATE_BASIS_COLUMNS = {
    "created_at": "created_at",
    "planned_shipment_date": "planned_shipment_date",
    "actual_shipment_date": "actual_shipment_date",
    "courier_transmission_date": "courier_transmission_date",
    "status_updated_at": "status_updated_at",
    "imported_at": "imported_at",
    "updated_at": "updated_at",
}


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _select_expr(columns: set[str], column: str, default: Any = None, alias: str | None = None) -> str:
    out = alias or column
    if column in columns:
        return f"{column} AS {out}"
    return f"{_sql_literal(default)} AS {out}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return None
    return text


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else ""


def _truthy(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "returned", "return", "возврат"}


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace("\u00a0", "").replace(" ", "")
        if value.count(",") == 1 and value.count(".") == 0:
            value = value.replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _source_order_date(row: sqlite3.Row | dict[str, Any], basis: str) -> str:
    if basis == "first_available":
        for column in (
            "actual_shipment_date",
            "courier_transmission_date",
            "status_updated_at",
            "planned_shipment_date",
            "created_at",
        ):
            text = _date_text(row[column])
            if text:
                return text
        return ""
    column = ORDER_DATE_BASIS_COLUMNS[basis]
    return _date_text(row[column])


def _status_from_order(row: sqlite3.Row | dict[str, Any]) -> tuple[str, int, str]:
    status_parts = []
    for key in ("internal_status", "kaspi_status", "kaspi_status_detail"):
        try:
            status_parts.append(str(row[key] or ""))
        except (KeyError, IndexError):
            continue
    status_text = " ".join(status_parts).upper()
    returned = _truthy(row["returned_to_warehouse"]) or any(
        token in status_text for token in ("RETURN", "RETURNED", "ВОЗВР", "ВОЗВРАТ")
    )
    if returned:
        return "RETURNED", 1, _date_text(row["status_updated_at"]) or _date_text(row["actual_shipment_date"])
    if any(token in status_text for token in ("CANCEL", "CANCELLED", "ОТМЕН")):
        return "CANCELLED", 0, ""
    return "DELIVERED", 0, ""


def _sku_key_for_sku_id(conn: sqlite3.Connection, sku_id: str | None) -> str | None:
    if not sku_id or not _table_exists(conn, "dim_sku_size"):
        return None
    row = conn.execute(
        "SELECT sku_key FROM dim_sku_size WHERE sku_id = ?",
        (sku_id,),
    ).fetchone()
    return _clean_text(row["sku_key"]) if row else None


def _sku_meta(conn: sqlite3.Connection, sku_key: str | None) -> dict[str, Any]:
    if not sku_key or not _table_exists(conn, "dim_sku"):
        return {}
    cols = _table_columns(conn, "dim_sku")
    wanted = [col for col in ("product_type", "weight_kg", "cogs_kzt", "base_cost_cny") if col in cols]
    if not wanted:
        return {}
    row = conn.execute(
        f"SELECT {', '.join(wanted)} FROM dim_sku WHERE sku_key = ?",
        (sku_key,),
    ).fetchone()
    return dict(row) if row else {}


def _resolve_identity_for_direct_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    final_size: str,
    final_size_source: str,
) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    source_sku_id = _clean_text(row["sku_id"])
    source_sku_key = _clean_text(row["sku_key"])
    if source_sku_key:
        source_sku_key = normalize_sku_key(source_sku_key)

    if final_size_source == "assigned_size":
        sku_key_input = source_sku_key or _sku_key_for_sku_id(conn, source_sku_id)
        sku_id_input = None
    else:
        sku_key_input = source_sku_key
        sku_id_input = source_sku_id

    event_date = _parse_date(row["created_at"]) or _parse_date(row["planned_shipment_date"])
    alias = apply_rombik_kid30_alias(
        sku_key=sku_key_input,
        sku_id=sku_id_input,
        my_size=final_size,
        event_at=event_date,
        kaspi_article=_clean_text(row["kaspi_article"]),
        kaspi_offer_name=_clean_text(row["kaspi_offer_name"]),
    )
    sku_key_input = alias["sku_key"]
    sku_id_input = alias["sku_id"]
    final_size = alias["my_size"] or final_size

    resolution = resolve_sales_identity_detail(
        conn,
        sku_id_input,
        sku_key_input,
        final_size,
        _clean_text(row["kaspi_offer_name"]),
        _clean_text(row["store_code"]),
    )
    return resolution.sku_key, resolution.sku_id, resolution.my_size, {
        "offer_name_mapping_hit": resolution.offer_name_mapping_hit,
        "offer_name_mapping_sku_key_only": resolution.offer_name_mapping_sku_key_only,
    }


def _existing_sale_ids(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    store_code: str,
    kaspi_offer_name: str,
    sku_key: str,
    sku_id: str,
    my_size: str,
) -> tuple[str, str]:
    if not _table_exists(conn, "sales_fact_v2"):
        return "", ""
    logical = conn.execute(
        """
        SELECT sale_id FROM sales_fact_v2
        WHERE order_id = ? AND store_code = ? AND kaspi_offer_name = ?
          AND sku_key = ? AND my_size = ?
        LIMIT 1
        """,
        (order_id, store_code, kaspi_offer_name, sku_key, my_size),
    ).fetchone()
    fallback = conn.execute(
        """
        SELECT sale_id FROM sales_fact_v2
        WHERE order_id = ? AND sku_id = ? AND store_code = ? AND kaspi_offer_name = ?
        LIMIT 1
        """,
        (order_id, sku_id, store_code, kaspi_offer_name),
    ).fetchone()
    return (
        str(logical["sale_id"]) if logical else "",
        str(fallback["sale_id"]) if fallback else "",
    )


def _date_filter_sql(columns: set[str], basis: str) -> tuple[str, list[str]]:
    candidates = [column for column in DATE_FILTER_COLUMNS[basis] if column in columns]
    if not candidates:
        raise RuntimeError(f"fact_orders_kaspi has no columns for date filter basis {basis}")
    clauses = [f"date({column}) BETWEEN ? AND ?" for column in candidates]
    return "(" + " OR ".join(clauses) + ")", candidates


def _fetch_source_rows(
    conn: sqlite3.Connection,
    *,
    from_date: str,
    to_date: str,
    date_filter_basis: str,
) -> list[sqlite3.Row]:
    columns = _table_columns(conn, "fact_orders_kaspi")
    if not columns:
        raise RuntimeError("missing required table: fact_orders_kaspi")
    select_columns = [
        _select_expr(columns, "id", None, "id"),
        _select_expr(columns, "order_id", ""),
        _select_expr(columns, "store_code", ""),
        _select_expr(columns, "channel_code", "KSP"),
        _select_expr(columns, "kaspi_offer_name", ""),
        _select_expr(columns, "sku_key", ""),
        _select_expr(columns, "sku_id", ""),
        _select_expr(columns, "my_size", ""),
        _select_expr(columns, "quantity", 1),
        _select_expr(columns, "unit_price_kzt", None),
        _select_expr(columns, "created_at", ""),
        _select_expr(columns, "planned_shipment_date", ""),
        _select_expr(columns, "actual_shipment_date", ""),
        _select_expr(columns, "courier_transmission_date", ""),
        _select_expr(columns, "status_updated_at", ""),
        _select_expr(columns, "kaspi_status", ""),
        _select_expr(columns, "kaspi_status_detail", ""),
        _select_expr(columns, "internal_status", ""),
        _select_expr(columns, "source", ""),
        _select_expr(columns, "source_file", ""),
        _select_expr(columns, "imported_at", ""),
        _select_expr(columns, "updated_at", ""),
        _select_expr(columns, "assigned_size", ""),
        _select_expr(columns, "size_source", ""),
        _select_expr(columns, "size_confidence", ""),
        _select_expr(columns, "delivery_cost_for_seller", None),
        _select_expr(columns, "delivery_cost", None),
        _select_expr(columns, "returned_to_warehouse", 0),
        _select_expr(columns, "kaspi_article", ""),
        _select_expr(columns, "line_identity_key", ""),
    ]
    where_sql, basis_columns = _date_filter_sql(columns, date_filter_basis)
    params: list[str] = []
    for _ in basis_columns:
        params.extend([from_date, to_date])
    sql = f"""
        SELECT {', '.join(select_columns)}
        FROM fact_orders_kaspi
        WHERE {where_sql}
        ORDER BY
            date(COALESCE(planned_shipment_date, created_at, status_updated_at)),
            order_id,
            store_code,
            kaspi_offer_name,
            sku_id,
            line_identity_key
    """
    return list(conn.execute(sql, params))


def _unmapped_from_row(
    row: sqlite3.Row,
    *,
    run_id: str,
    reason: str,
    final_size: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source_lane": "direct_feeder",
        "reason": reason,
        "source_row_id": row["id"] or "",
        "order_id": _clean_text(row["order_id"]) or "",
        "store_code": (_clean_text(row["store_code"]) or "").upper(),
        "line_identity_key": _clean_text(row["line_identity_key"]) or "",
        "kaspi_offer_name": _clean_text(row["kaspi_offer_name"]) or "",
        "source_sku_key": _clean_text(row["sku_key"]) or "",
        "source_sku_id": _clean_text(row["sku_id"]) or "",
        "assigned_size": _clean_text(row["assigned_size"]) or "",
        "my_size": _clean_text(row["my_size"]) or "",
        "final_my_size": final_size or "",
        "size_source": _clean_text(row["size_source"]) or "",
        "created_date": _date_text(row["created_at"]),
        "planned_shipment_date": _date_text(row["planned_shipment_date"]),
        "actual_shipment_date": _date_text(row["actual_shipment_date"]),
        "status_updated_date": _date_text(row["status_updated_at"]),
    }


def build_shadow_rows(
    conn: sqlite3.Connection,
    *,
    from_date: str,
    to_date: str,
    run_id: str,
    date_filter_basis: str = "any_relevant",
    order_date_basis: str = "planned_shipment_date",
) -> dict[str, Any]:
    source_rows = _fetch_source_rows(
        conn,
        from_date=from_date,
        to_date=to_date,
        date_filter_basis=date_filter_basis,
    )
    shadow_rows: list[dict[str, Any]] = []
    unmapped_rows: list[dict[str, Any]] = []

    for row in source_rows:
        order_id = _clean_text(row["order_id"]) or ""
        store_code = (_clean_text(row["store_code"]) or "UNIVERSAL").upper()
        store_code = normalize_store_code(store_code)
        kaspi_offer_name = _clean_text(row["kaspi_offer_name"]) or ""
        source_sku_key = _clean_text(row["sku_key"])
        source_sku_id = _clean_text(row["sku_id"])
        assigned_size = _clean_text(row["assigned_size"])
        legacy_size = _clean_text(row["my_size"])

        initial_key = source_sku_key or _sku_key_for_sku_id(conn, source_sku_id)
        product_type = None
        if initial_key and "_" in initial_key:
            product_type = initial_key.split("_", 1)[0]
        elif source_sku_id and "_" in source_sku_id:
            product_type = source_sku_id.split("_", 1)[0]

        final_size_source = "assigned_size" if assigned_size else "my_size"
        raw_final_size = assigned_size or legacy_size
        final_size = normalize_size(raw_final_size, product_type=product_type) if raw_final_size else None
        if not final_size:
            unmapped_rows.append(
                _unmapped_from_row(row, run_id=run_id, reason="missing_size", final_size="")
            )
            continue

        sku_key, sku_id, my_size, _resolution_meta = _resolve_identity_for_direct_row(
            conn,
            row,
            final_size,
            final_size_source,
        )
        if not sku_key or not sku_id or not my_size:
            missing = []
            if not sku_key:
                missing.append("sku_key")
            if not sku_id:
                missing.append("sku_id")
            if not my_size:
                missing.append("my_size")
            unmapped_rows.append(
                _unmapped_from_row(
                    row,
                    run_id=run_id,
                    reason="unresolved_" + "_".join(missing),
                    final_size=final_size,
                )
            )
            continue

        sku_meta = _sku_meta(conn, sku_key)
        quantity = _to_int(row["quantity"], 1) or 1
        sell_price = _to_float(row["unit_price_kzt"])
        seller_fee = _to_float(row["delivery_cost_for_seller"])
        source_delivery = _to_float(row["delivery_cost"])
        if seller_fee is not None:
            delivery_fee = seller_fee
            delivery_fee_source = "delivery_cost_for_seller"
        elif source_delivery is not None:
            delivery_fee = source_delivery
            delivery_fee_source = "delivery_cost"
        elif sell_price is not None:
            delivery_fee = calc_delivery_fee(
                sell_price,
                weight_kg=_to_float(sku_meta.get("weight_kg")),
            )
            delivery_fee_source = "calc_delivery_fee"
        else:
            delivery_fee = None
            delivery_fee_source = "missing"

        order_date = _source_order_date(row, order_date_basis)
        source_order_date = _date_text(row["created_at"])
        net_rev = None
        net_rev_source = "missing_price"
        if sell_price is not None:
            net_rev = calc_net_rev(
                sell_price,
                delivery_fee=delivery_fee,
                weight_kg=_to_float(sku_meta.get("weight_kg")),
                as_of_date=_parse_date(order_date),
            ) * quantity
            net_rev_source = "calc_net_rev_line"

        status, return_flag, return_date = _status_from_order(row)
        logical_key = build_sales_dedupe_key(
            order_id,
            store_code,
            kaspi_offer_name,
            sku_key,
            my_size,
        )
        db_key = (order_id, sku_id, store_code, kaspi_offer_name)
        existing_logical, existing_fallback = _existing_sale_ids(
            conn,
            order_id=order_id,
            store_code=store_code,
            kaspi_offer_name=kaspi_offer_name,
            sku_key=sku_key,
            sku_id=sku_id,
            my_size=my_size,
        )

        shadow_rows.append(
            {
                "run_id": run_id,
                "source_table": "fact_orders_kaspi",
                "source_row_id": row["id"] or "",
                "order_id": order_id,
                "store_code": store_code,
                "line_identity_key": _clean_text(row["line_identity_key"]) or "",
                "order_date": order_date,
                "order_date_basis": order_date_basis,
                "source_order_date": source_order_date,
                "planned_shipment_date": _date_text(row["planned_shipment_date"]),
                "actual_shipment_date": _date_text(row["actual_shipment_date"]),
                "courier_transmission_date": _date_text(row["courier_transmission_date"]),
                "status_updated_date": _date_text(row["status_updated_at"]),
                "created_date": _date_text(row["created_at"]),
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": my_size,
                "final_my_size_source": final_size_source,
                "kaspi_offer_name": kaspi_offer_name,
                "quantity": quantity,
                "sell_price_kzt": sell_price if sell_price is not None else "",
                "delivery_fee": round(delivery_fee, 2) if delivery_fee is not None else "",
                "delivery_fee_source": delivery_fee_source,
                "net_rev": round(net_rev, 2) if net_rev is not None else "",
                "net_rev_source": net_rev_source,
                "cogs": "",
                "cogs_source": "not_computed_phase1",
                "profit": "",
                "profit_source": "not_computed_phase1",
                "status": status,
                "return_flag": return_flag,
                "return_date": return_date,
                "source_file": f"fact_orders_kaspi:{run_id}",
                "source_imported_at": _clean_text(row["imported_at"]) or "",
                "source_updated_at": _clean_text(row["updated_at"]) or "",
                "size_source": _clean_text(row["size_source"]) or "",
                "size_confidence": _clean_text(row["size_confidence"]) or "",
                "logical_dedupe_key": "|".join(logical_key),
                "db_unique_key": "|".join(db_key),
                "existing_sale_id_logical": existing_logical,
                "existing_sale_id_db_unique": existing_fallback,
            }
        )

    shadow_rows.sort(
        key=lambda r: (
            str(r["order_date"]),
            str(r["order_id"]),
            str(r["store_code"]),
            str(r["kaspi_offer_name"]),
            str(r["sku_id"]),
            str(r["line_identity_key"]),
        )
    )
    logical_counts = Counter(row["logical_dedupe_key"] for row in shadow_rows)
    db_counts = Counter(row["db_unique_key"] for row in shadow_rows)
    summary = {
        "run_id": run_id,
        "mode": "shadow",
        "db_mutations": 0,
        "from_date": from_date,
        "to_date": to_date,
        "date_filter_basis": date_filter_basis,
        "order_date_basis": order_date_basis,
        "source_rows": len(source_rows),
        "shadow_rows": len(shadow_rows),
        "unmapped_rows": len(unmapped_rows),
        "missing_size": sum(1 for row in unmapped_rows if row["reason"] == "missing_size"),
        "duplicate_logical_keys": sum(1 for count in logical_counts.values() if count > 1),
        "duplicate_db_unique_keys": sum(1 for count in db_counts.values() if count > 1),
    }
    return {"rows": shadow_rows, "unmapped": unmapped_rows, "summary": summary}


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Direct Feeder Shadow Summary",
        "",
        f"- run_id: {summary['run_id']}",
        f"- mode: {summary['mode']}",
        f"- window: {summary['from_date']}..{summary['to_date']}",
        f"- date_filter_basis: {summary['date_filter_basis']}",
        f"- order_date_basis: {summary['order_date_basis']}",
        f"- source_rows: {summary['source_rows']}",
        f"- shadow_rows: {summary['shadow_rows']}",
        f"- unmapped_rows: {summary['unmapped_rows']}",
        f"- missing_size: {summary['missing_size']}",
        f"- duplicate_logical_keys: {summary['duplicate_logical_keys']}",
        f"- duplicate_db_unique_keys: {summary['duplicate_db_unique_keys']}",
        f"- db_mutations: {summary['db_mutations']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_run_id() -> str:
    return "direct_feeder_" + datetime.now().strftime("%Y%m%dT%H%M%S")


def resolve_output_paths(args: argparse.Namespace) -> tuple[Path, Path, str]:
    run_id = args.source_run_id or default_run_id()
    if args.out_dir:
        out_dir = args.out_dir
    elif args.shadow_out:
        out_dir = args.shadow_out.parent
    else:
        out_dir = DEFAULT_OUTPUT_ROOT / date.today().isoformat() / run_id
    shadow_csv = args.shadow_out or out_dir / "direct_feeder_shadow_rows.csv"
    return out_dir, shadow_csv, run_id


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--source-run-id")
    parser.add_argument("--shadow-out", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--date-filter-basis",
        choices=sorted(DATE_FILTER_COLUMNS),
        default="any_relevant",
    )
    parser.add_argument(
        "--order-date-basis",
        choices=sorted([*ORDER_DATE_BASIS_COLUMNS, "first_available"]),
        default="planned_shipment_date",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.apply:
        if os.environ.get("AB_DIRECT_FEEDER_APPLY") != "1":
            print("ERROR: apply requires AB_DIRECT_FEEDER_APPLY=1 and --apply", file=sys.stderr)
        print(f"ERROR: {APPLY_REFUSAL}", file=sys.stderr)
        return 2

    out_dir, shadow_csv, run_id = resolve_output_paths(args)
    with _connect_readonly(args.db) as conn:
        result = build_shadow_rows(
            conn,
            from_date=args.from_date,
            to_date=args.to_date,
            run_id=run_id,
            date_filter_basis=args.date_filter_basis,
            order_date_basis=args.order_date_basis,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(shadow_csv, result["rows"], SHADOW_COLUMNS)
    _write_csv(out_dir / "unmapped_rows.csv", result["unmapped"], UNMAPPED_COLUMNS)
    (out_dir / "summary.json").write_text(
        json.dumps(result["summary"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary_md(out_dir / "summary.md", result["summary"])

    print(json.dumps({**result["summary"], "out_dir": str(out_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
