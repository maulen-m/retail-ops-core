#!/usr/bin/env python3
"""
Translate Kaspi order lifecycle into cashflow events (cash-in at delivered + inventory moves).

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_db import backup_database  # noqa: E402
from core.db.queries import get_cutoff_date_almaty
from core.config.business_params import get_supplier_fx_rates, get_vat_rate
from core.calc.economics import calc_delivery_fee, calc_net_rev, calc_cogs
from core.integrations.kaspi_order_stage import (
    StageCode,
    api_state_filter_for_stage,
    classify_kaspi_stage_from_db_row,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_column_map.yaml"
EXPORT_PATH = PROJECT_ROOT / "exports" / "orders_to_cashflow_report.txt"
PROD_WRITE_ENV_GATE = "ENABLE_CASHFLOW_PROD_WRITE"
_DELIVERY_STATE = api_state_filter_for_stage(StageCode.ACCEPTED_PENDING_ASSEMBLY) or ""
DELIVERED_STAGE_CODES = {"COMPLETED", "DELIVERED", "ISSUED_COMPLETED"}
RETURN_STAGE_CODES = {"RETURNED", "CANCELLED_AFTER_DELIVERY", "CANCELLED_DELIVERED"}
CANCEL_STAGE_CODES = {"CANCELLED"}
UNKNOWN_STORE_CODES = {"", "UNKNOWN"}
SUPPORTED_ONLY_CASHFLOW_STATUSES = {"ON_DELIVERY"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(f"refusing production cashflow apply while SQLite sidecars exist: {joined}")


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _read_order_id_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"order allowlist file not found: {path}")
    order_ids = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if not order_ids:
        raise RuntimeError(f"order allowlist file is empty: {path}")
    return order_ids


def _normalize_order_id_allowlist(order_id_allowlist: set[str] | None) -> set[str] | None:
    if order_id_allowlist is None:
        return None
    normalized = {str(order_id).strip() for order_id in order_id_allowlist if str(order_id).strip()}
    if not normalized:
        raise RuntimeError("order_id_allowlist must not be empty")
    return normalized


def _normalize_only_cashflow_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized not in SUPPORTED_ONLY_CASHFLOW_STATUSES:
        supported = ", ".join(sorted(SUPPORTED_ONLY_CASHFLOW_STATUSES))
        raise RuntimeError(f"unsupported --only-cashflow-status {value!r}; supported: {supported}")
    return normalized


def _event_scope_line(event: dict) -> str:
    columns = [
        "EVENT",
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.2f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("notes") or "").replace("\t", " "),
        str(event.get("source") or ""),
        str(event.get("run_id") or ""),
    ]
    return "\t".join(columns)


def _prepare_cashflow_apply_guard(
    db_path: Path,
    *,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, object]:
    if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

    production_apply = _is_production_db(db_path)
    metadata: dict[str, object] = {
        "production_apply": production_apply,
        "pre_sha256": _sha256_file(db_path),
    }
    if not production_apply:
        return metadata

    if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
        raise RuntimeError(f"{PROD_WRITE_ENV_GATE}=1 is required for production cashflow apply.")
    if not expected_pre_sha256:
        raise RuntimeError("--expected-pre-sha256 is required for production cashflow apply.")
    if backup_dir is None:
        raise RuntimeError("--backup-dir is required for production cashflow apply.")

    _fail_on_sqlite_sidecars(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise RuntimeError(f"production DB integrity_check failed before cashflow apply: {pre_integrity}")
    pre_sha256 = str(metadata["pre_sha256"])
    if pre_sha256 != expected_pre_sha256:
        raise RuntimeError(
            "production DB SHA mismatch before cashflow apply: "
            f"expected {expected_pre_sha256}, observed {pre_sha256}"
        )

    backup_path = backup_database(db_path, backup_dir, compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise RuntimeError(f"cashflow backup integrity_check failed: {backup_integrity}")
    metadata.update(
        {
            "expected_pre_sha256": expected_pre_sha256,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "pre_integrity_check": pre_integrity,
            "backup_integrity_check": backup_integrity,
        }
    )
    return metadata

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _is_unknown_store(value: object) -> bool:
    return str(value or "").strip().upper() in UNKNOWN_STORE_CODES


def _is_weak_sku_identity(sku_key: str, sku_id: str) -> bool:
    return sku_key.strip().upper() == "CL" and sku_id.strip().upper().startswith("CL_")


def _is_recovered_blank_order_entry(line: dict) -> bool:
    return (
        str(line.get("line_ref_type") or "").strip().upper() == "ORDER_ENTRY"
        and str(line.get("line_ref_id") or "").startswith("RECOV-CURRENT_CRM-")
        and not str(line.get("sku_key") or "").strip()
        and not str(line.get("sku_id") or "").strip()
    )


def _cashflow_status_from_stage(stage: StageCode) -> str | None:
    if stage == StageCode.ISSUED_COMPLETED:
        return "COMPLETED"
    if stage == StageCode.IN_DELIVERY:
        return "ON_DELIVERY"
    if stage in {StageCode.RETURNED, StageCode.CANCELLED}:
        return "CANCELLED"
    return None


def _event_hash(event: dict) -> str:
    parts = [
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt.date().isoformat()
    except Exception:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except Exception:
            return None


def _extract_sku_from_raw_json(raw_json: str | None) -> tuple[str | None, str | None]:
    if not raw_json:
        return None, None
    try:
        payload = json.loads(raw_json)
    except Exception:
        return None, None
    candidates = []
    if isinstance(payload, dict):
        candidates.append(payload)
        item = payload.get("item")
        if isinstance(item, dict):
            candidates.append(item)
        attrs = payload.get("attributes")
        if isinstance(attrs, dict):
            candidates.append(attrs)
    for item in candidates:
        sku_key = (
            item.get("sku_key")
            or item.get("SKU_key")
            or item.get("SKU_KEY")
            or item.get("skuKey")
        )
        sku_id = (
            item.get("sku_id")
            or item.get("SKU_ID")
            or item.get("skuId")
            or item.get("my_size")
        )
        sku_key = str(sku_key or "").strip()
        sku_id = str(sku_id or "").strip()
        if sku_key and sku_id:
            return sku_key, sku_id
    return None, None


def _load_dim_sku_weights(conn: sqlite3.Connection) -> dict[str, float]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute("SELECT sku_key, weight_kg FROM dim_sku").fetchall()
    return {row[0]: float(row[1] or 0.0) for row in rows}


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row[0]: {
            "cogs_kzt": row[1] or 0.0,
            "base_cost_cny": row[2] or 0.0,
            "weight_kg": row[3] or 0.0,
        }
        for row in rows
    }


def _load_order_entries(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    if not _table_exists(conn, "fact_order_entries_kaspi"):
        return {}
    map_rows = []
    if _table_exists(conn, "dim_kaspi_article_map"):
        map_rows = conn.execute(
            """
            SELECT store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id
            FROM dim_kaspi_article_map
            WHERE sku_key IS NOT NULL
              AND trim(sku_key) <> ''
              AND sku_id IS NOT NULL
              AND trim(sku_id) <> ''
            """
        ).fetchall()

    article_map: dict[tuple[str, str], tuple[str, str]] = {}
    name_map: dict[tuple[str, str], tuple[str, str]] = {}
    ambiguous_article: set[tuple[str, str]] = set()
    ambiguous_name: set[tuple[str, str]] = set()
    for row in map_rows:
        store = str(row["store_code"] or "").strip()
        article = str(row["kaspi_article"] or "").strip()
        offer_name = str(row["kaspi_offer_name"] or "").strip()
        value = (str(row["sku_key"]), str(row["sku_id"]))
        if store and article:
            key = (store, article)
            if key in ambiguous_article:
                pass
            elif key in article_map and article_map[key] != value:
                ambiguous_article.add(key)
                article_map.pop(key, None)
            else:
                article_map[key] = value
        if store and offer_name:
            key = (store, offer_name)
            if key in ambiguous_name:
                pass
            elif key in name_map and name_map[key] != value:
                ambiguous_name.add(key)
                name_map.pop(key, None)
            else:
                name_map[key] = value

    entry_cols = _columns(conn, "fact_order_entries_kaspi")
    wanted_cols = [
        "entry_id",
        "order_id",
        "store_code",
        "offer_id",
        "quantity",
        "unit_price_kzt",
        "total_price_kzt",
        "raw_json",
        "delivery_cost_kzt",
    ]
    select_cols = [col for col in wanted_cols if col in entry_cols]
    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM fact_order_entries_kaspi"
    ).fetchall()

    def _offer_candidates(offer_id: str | None) -> list[str]:
        raw = str(offer_id or "").strip()
        if not raw:
            return []
        candidates = [raw]
        if "\t" in raw:
            candidates.extend(part.strip() for part in raw.split("\t") if part.strip())
        if " " in raw:
            candidates.extend(part.strip() for part in raw.split(" ") if part.strip())
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

    def _offer_name_from_raw(raw_json: str | None) -> str | None:
        if not raw_json:
            return None
        try:
            payload = json.loads(raw_json)
        except Exception:
            return None
        attrs = payload.get("attributes") or {}
        offer = attrs.get("offer") or {}
        name = str(offer.get("name") or "").strip()
        return name or None

    entries_by_order: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        row_dict = dict(row)
        order_id = str(row_dict.get("order_id")) if row_dict.get("order_id") is not None else ""
        store_code = (
            str(row_dict.get("store_code")).strip().upper()
            if row_dict.get("store_code") is not None
            else ""
        )
        if not order_id or not store_code:
            continue
        sku_key = None
        sku_id = None
        for candidate in _offer_candidates(row_dict.get("offer_id")):
            mapped = article_map.get((store_code, candidate))
            if mapped:
                sku_key, sku_id = mapped
                break
        if (not sku_key or not sku_id) and row_dict.get("raw_json"):
            sku_key, sku_id = _extract_sku_from_raw_json(row_dict.get("raw_json"))
        if (not sku_key or not sku_id) and row_dict.get("raw_json"):
            offer_name = _offer_name_from_raw(row_dict.get("raw_json"))
            if offer_name:
                mapped = name_map.get((store_code, offer_name))
                if mapped:
                    sku_key, sku_id = mapped
        entry_id = str(row_dict.get("entry_id") or "").strip()
        entries_by_order.setdefault((order_id, store_code), []).append(
            {
                "line_ref_type": "ORDER_ENTRY" if entry_id else "ORDER",
                "line_ref_id": entry_id or order_id,
                "entry_id": entry_id,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "quantity": float(row_dict.get("quantity") or 0.0),
                "unit_price_kzt": row_dict.get("unit_price_kzt"),
                "total_price_kzt": row_dict.get("total_price_kzt"),
                "delivery_cost_kzt": row_dict.get("delivery_cost_kzt"),
            }
        )
    return entries_by_order


def _load_sales_fact_fallback(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    if not _table_exists(conn, "sales_fact_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT order_id, store_code, sku_key, sku_id, quantity, sell_price_kzt
        FROM sales_fact_v2
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
    lines_by_order: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        order_id = str(row["order_id"]).strip()
        store_code = str(row["store_code"]).strip().upper()
        lines_by_order.setdefault((order_id, store_code), []).append(
            {
                "line_ref_type": "ORDER",
                "line_ref_id": order_id,
                "sku_key": str(row["sku_key"]).strip(),
                "sku_id": str(row["sku_id"]).strip(),
                "quantity": float(row["quantity"] or 0.0),
                "unit_price_kzt": row["sell_price_kzt"],
                "total_price_kzt": None,
            }
        )
    return lines_by_order


def _load_fact_order_line_fallback(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    if not _table_exists(conn, "fact_orders_kaspi"):
        return {}
    cols = _columns(conn, "fact_orders_kaspi")
    wanted = [
        "order_id",
        "store_code",
        "sku_key",
        "sku_id",
        "quantity",
        "unit_price_kzt",
        "delivery_cost_for_seller",
        "delivery_cost",
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
    lines_by_order: dict[tuple[str, str], list[dict]] = {}
    seen_sku: set[tuple[str, str, str]] = set()
    seen_header: set[tuple[str, str, float, float]] = set()
    for row in rows:
        row_dict = dict(row)
        order_id = str(row_dict["order_id"]).strip()
        store_code = str(row_dict["store_code"]).strip().upper()
        sku_key = str(row_dict.get("sku_key") or "").strip()
        sku_id = str(row_dict.get("sku_id") or "").strip()
        qty = float(row_dict.get("quantity") or 0.0)
        unit = float(row_dict.get("unit_price_kzt") or 0.0)
        delivery_cost = row_dict.get("delivery_cost_for_seller")
        if delivery_cost is None:
            delivery_cost = row_dict.get("delivery_cost")
        if sku_key and sku_id:
            key = (order_id, store_code, sku_id)
            if key in seen_sku:
                continue
            seen_sku.add(key)
            line_ref_id = order_id
        else:
            key = (order_id, store_code, qty, unit)
            if key in seen_header:
                continue
            seen_header.add(key)
            line_ref_id = order_id
        lines_by_order.setdefault((order_id, store_code), []).append(
            {
                "line_ref_type": "ORDER",
                "line_ref_id": line_ref_id,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "quantity": qty,
                "unit_price_kzt": unit,
                "total_price_kzt": None,
                "delivery_cost_kzt": delivery_cost,
            }
        )
    return lines_by_order


def _unit_cost_kzt_for_sku(sku_key: str | None, fx_rates, dim_costs: dict[str, dict]) -> float:
    meta = dim_costs.get(sku_key or "", {})
    base_cost = meta.get("base_cost_cny", 0.0)
    weight = meta.get("weight_kg", 0.0)
    if base_cost and base_cost > 0 and weight and weight > 0:
        return float(
            calc_cogs(
                base_cost,
                weight,
                cny_kzt=fx_rates.cny_kzt,
                volumetric_factor=fx_rates.dlv_rate_usd_kg,
                freight_rate=fx_rates.usd_kzt,
            )
        )
    cogs_unit = meta.get("cogs_kzt") or 0.0
    if cogs_unit > 0:
        return float(cogs_unit)
    return float(
        calc_cogs(
            base_cost,
            weight,
            cny_kzt=fx_rates.cny_kzt,
            volumetric_factor=fx_rates.dlv_rate_usd_kg,
            freight_rate=fx_rates.usd_kzt,
        )
    )


def _unit_cost_kzt(row: sqlite3.Row, fx_rates, dim_costs: dict[str, dict]) -> float:
    return _unit_cost_kzt_for_sku(row["sku_key"], fx_rates, dim_costs)


def _cash_account(store_code: str | None) -> str:
    if not store_code:
        return "KASPI_PAY_UNKNOWN"
    return f"KASPI_PAY_{store_code}"


def _line_ref(line: dict, order_id: str) -> tuple[str, str]:
    ref_type = str(line.get("line_ref_type") or "ORDER").strip().upper()
    ref_id = str(line.get("line_ref_id") or "").strip()
    if ref_type == "ORDER_ENTRY" and ref_id:
        return "ORDER_ENTRY", ref_id
    return "ORDER", order_id


def _sell_price_for_line(line: dict) -> float:
    qty = float(line.get("quantity") or 0.0)
    sell_price = line.get("unit_price_kzt")
    if not sell_price and line.get("total_price_kzt") and qty > 0:
        sell_price = float(line.get("total_price_kzt") or 0.0) / qty
    return float(sell_price or 0.0)


def _net_cash_amount_for_line(line: dict, event_date: str, weights: dict[str, float]) -> float:
    qty = float(line.get("quantity") or 0.0)
    sell_price = _sell_price_for_line(line)
    sku_key = line.get("sku_key")
    weight = weights.get(sku_key or "", 0.0)
    delivery_fee = line.get("delivery_cost_kzt")
    if delivery_fee is None:
        delivery_fee = calc_delivery_fee(sell_price, weight_kg=weight, delivery_type="city")
    net_rev_unit = calc_net_rev(
        sell_price,
        delivery_fee=float(delivery_fee or 0.0),
        weight_kg=weight,
        as_of_date=date.fromisoformat(event_date),
    )
    return round(float(net_rev_unit or 0.0) * qty, 2)


def _load_existing_cash_rows(conn: sqlite3.Connection) -> list[dict]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return []
    rows = conn.execute(
        """
        SELECT event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
               ref_type, ref_id, source
        FROM fact_cashflow_events
        WHERE UPPER(COALESCE(event_type, '')) = 'CASH_IN'
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _load_order_entry_cash_order_skus(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events") or not _table_exists(conn, "fact_order_entries_kaspi"):
        return set()
    rows = conn.execute(
        """
        SELECT e.order_id, COALESCE(c.sku_id, '') AS sku_id
        FROM fact_cashflow_events c
        JOIN fact_order_entries_kaspi e
          ON UPPER(COALESCE(c.ref_type, '')) = 'ORDER_ENTRY'
         AND c.ref_id = e.entry_id
        WHERE UPPER(COALESCE(c.event_type, '')) = 'CASH_IN'
          AND COALESCE(c.amount_kzt, 0) > 0
        """
    ).fetchall()
    return {
        (str(row["order_id"] or "").strip(), str(row["sku_id"] or "").strip())
        for row in rows
        if str(row["order_id"] or "").strip()
    }


def _cash_matches_line(
    cash_rows: list[dict],
    *,
    order_id: str,
    line: dict,
    event_date: str | None,
    positive: bool,
    single_line_order: bool,
) -> list[dict]:
    ref_type, ref_id = _line_ref(line, order_id)
    sku_id = str(line.get("sku_id") or "").strip()
    exact = []
    sku_fallback = []
    general_fallback = []
    for row in cash_rows:
        amount = float(row.get("amount_kzt") or 0.0)
        if positive and amount <= 0:
            continue
        if not positive and amount >= 0:
            continue
        if "RECEIVABLE" in str(row.get("account") or "").upper():
            continue
        if event_date and _parse_date(row.get("event_date")) != event_date:
            continue
        row_ref_type = str(row.get("ref_type") or "ORDER").strip().upper()
        row_ref_id = str(row.get("ref_id") or "").strip()
        row_sku_key = str(row.get("sku_key") or "").strip()
        row_sku_id = str(row.get("sku_id") or "").strip()
        if ref_type == "ORDER_ENTRY" and row_ref_type == "ORDER_ENTRY" and row_ref_id == ref_id:
            exact.append(row)
            continue
        if row_ref_type == "ORDER" and row_ref_id == order_id:
            sku_key = str(line.get("sku_key") or "").strip()
            line_specific = bool(sku_id or sku_key) and not _is_weak_sku_identity(sku_key, sku_id)
            if line_specific and (row_sku_id or row_sku_key):
                if (
                    (sku_id and row_sku_id == sku_id)
                    or (sku_key and row_sku_key == sku_key)
                    or (sku_key and row_sku_id == sku_key)
                ):
                    sku_fallback.append(row)
                continue
            if single_line_order or _is_recovered_blank_order_entry(line):
                general_fallback.append(row)
                continue
    if exact:
        return exact
    if sku_fallback:
        return sku_fallback[:1]
    return general_fallback[:1]


def _stage_events_by_order(
    conn: sqlite3.Connection,
    since: date,
    until: date,
) -> dict[tuple[str, str], dict[str, str]]:
    if not _table_exists(conn, "order_status_event"):
        return {}
    delivered_sql = ",".join("?" * len(DELIVERED_STAGE_CODES))
    return_sql = ",".join("?" * len(RETURN_STAGE_CODES))
    cancel_sql = ",".join("?" * len(CANCEL_STAGE_CODES))
    delivered_rows = conn.execute(
        f"""
        SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               order_id,
               MIN(event_ts) AS delivered_ts
        FROM order_status_event
        WHERE UPPER(COALESCE(stage_code, '')) IN ({delivered_sql})
          AND date(event_ts) BETWEEN date(?) AND date(?)
        GROUP BY UPPER(COALESCE(store_code, 'UNIVERSAL')), order_id
        """,
        (*sorted(DELIVERED_STAGE_CODES), since.isoformat(), until.isoformat()),
    ).fetchall()
    out: dict[tuple[str, str], dict[str, str]] = {}
    non_unknown_order_ids = {
        str(row["order_id"] or "").strip()
        for row in delivered_rows
        if str(row["order_id"] or "").strip() and not _is_unknown_store(row["store_code"])
    }
    for row in delivered_rows:
        order_id = str(row["order_id"] or "").strip()
        store_code = str(row["store_code"] or "").strip()
        delivered_date = _parse_date(row["delivered_ts"])
        if not order_id or not store_code or not delivered_date:
            continue
        if order_id in non_unknown_order_ids and _is_unknown_store(store_code):
            continue
        out[(order_id, store_code)] = {
            "delivered_ts": str(row["delivered_ts"]),
            "delivered_date": delivered_date,
        }

    if not out:
        return out

    terminal_rows = conn.execute(
        f"""
        SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
               order_id,
               MIN(event_ts) AS terminal_ts
        FROM order_status_event
        WHERE (
                UPPER(COALESCE(stage_code, '')) IN ({return_sql})
             OR UPPER(COALESCE(stage_code, '')) IN ({cancel_sql})
        )
          AND date(event_ts) BETWEEN date(?) AND date(?)
        GROUP BY UPPER(COALESCE(store_code, 'UNIVERSAL')), order_id
        """,
        (*sorted(RETURN_STAGE_CODES), *sorted(CANCEL_STAGE_CODES), since.isoformat(), until.isoformat()),
    ).fetchall()
    for row in terminal_rows:
        key = (str(row["order_id"] or "").strip(), str(row["store_code"] or "").strip())
        if key not in out:
            continue
        terminal_date = _parse_date(row["terminal_ts"])
        if terminal_date and terminal_date >= out[key]["delivered_date"]:
            out[key]["terminal_ts"] = str(row["terminal_ts"])
            out[key]["terminal_date"] = terminal_date
    return out


def _build_stagecode_d1_events(
    conn: sqlite3.Connection,
    *,
    since: date,
    until: date,
    run_id: str,
    weights: dict[str, float],
    entries_by_order: dict[tuple[str, str], list[dict]],
    sales_fact_fallback: dict[tuple[str, str], list[dict]],
    fact_order_fallback: dict[tuple[str, str], list[dict]],
    order_id_filter: set[str] | None = None,
) -> tuple[list[dict], Counter]:
    stage_events = _stage_events_by_order(conn, since, until)
    cash_rows = _load_existing_cash_rows(conn)
    events: list[dict] = []
    counts: Counter = Counter()

    for (order_id, store_code), stage_meta in stage_events.items():
        if order_id_filter is not None and order_id not in order_id_filter:
            continue
        lines = (
            entries_by_order.get((order_id, store_code))
            or sales_fact_fallback.get((order_id, store_code))
            or fact_order_fallback.get((order_id, store_code))
            or []
        )
        if not lines:
            counts["missing_line_evidence"] += 1
            continue
        single_line_order = len(lines) == 1
        delivered_date = stage_meta["delivered_date"]
        for line in lines:
            qty = float(line.get("quantity") or 0.0)
            if qty <= 0 or _sell_price_for_line(line) <= 0:
                counts["missing_amount_evidence"] += 1
                continue
            existing_positive = _cash_matches_line(
                cash_rows,
                order_id=order_id,
                line=line,
                event_date=delivered_date,
                positive=True,
                single_line_order=single_line_order,
            )
            cash_amount = (
                abs(float(existing_positive[0].get("amount_kzt") or 0.0))
                if existing_positive
                else _net_cash_amount_for_line(line, delivered_date, weights)
            )
            ref_type, ref_id = _line_ref(line, order_id)
            base_fields = {
                "event_date": delivered_date,
                "event_type": "CASH_IN",
                "account": _cash_account(store_code),
                "amount_kzt": cash_amount,
                "store_code": store_code,
                "sku_key": line.get("sku_key") or "",
                "sku_id": line.get("sku_id") or "",
                "ref_type": ref_type,
                "ref_id": ref_id,
                "source": "ORDER_MODELLED",
                "run_id": run_id,
            }
            if not existing_positive:
                events.append({**base_fields, "notes": f"D1 cash-in from StageCode; order_id={order_id}"})
                cash_rows.append(base_fields)
                counts["cash_in_candidates"] += 1
            else:
                counts["cash_in_existing"] += 1

            terminal_date = stage_meta.get("terminal_date")
            if not terminal_date:
                continue
            existing_negative = _cash_matches_line(
                cash_rows,
                order_id=order_id,
                line=line,
                event_date=terminal_date,
                positive=False,
                single_line_order=single_line_order,
            )
            if existing_negative:
                counts["reversal_existing"] += 1
                continue
            reversal = {
                **base_fields,
                "event_date": terminal_date,
                "amount_kzt": -abs(cash_amount),
                "notes": f"D1 cash reversal from return/cancel StageCode; order_id={order_id}",
            }
            events.append(reversal)
            cash_rows.append(reversal)
            counts["reversal_candidates"] += 1
    return events, counts


def _load_existing_cash_in(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'CASH_IN'
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_refunds(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'CASH_IN'
          AND amount_kzt < 0
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_on_delivery(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT DISTINCT ref_id, sku_id
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'INVENTORY_MOVE'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
          AND ABS(amount_kzt) > 0
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else "")
        for row in rows
        if row[0] is not None
    }


def _load_existing_cogs_dates(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, MIN(date(event_date)) as cogs_date
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'COGS_RECOGNIZED'
          AND ABS(amount_kzt) > 0
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): row[2]
        for row in rows
        if row[0] is not None and row[2] is not None
    }


def _load_existing_move_dates(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, MIN(date(event_date)) as move_date
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND event_type = 'INVENTORY_MOVE'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
          AND ABS(amount_kzt) > 0
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): row[2]
        for row in rows
        if row[0] is not None and row[2] is not None
    }


def _load_on_delivery_balances(conn: sqlite3.Connection) -> dict[tuple[str, str], float]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT ref_id, sku_id, SUM(amount_kzt) AS balance_kzt
        FROM fact_cashflow_events
        WHERE ref_type = 'ORDER'
          AND account = 'INVENTORY_ON_DELIVERY_COST'
          AND ABS(amount_kzt) > 0
        GROUP BY ref_id, sku_id
        """
    ).fetchall()
    return {
        (str(row[0]), str(row[1]) if row[1] is not None else ""): float(row[2] or 0.0)
        for row in rows
        if row[0] is not None
    }


def _has_existing(existing: set[tuple[str, str]], order_id: str, order_sku_id: str) -> bool:
    if (order_id, order_sku_id) in existing:
        return True
    return (order_id, "") in existing


def _get_existing_date(
    existing: dict[tuple[str, str], str], order_id: str, order_sku_id: str
) -> str | None:
    return existing.get((order_id, order_sku_id)) or existing.get((order_id, ""))


def _get_existing_balance(
    balances: dict[tuple[str, str], float], order_id: str, order_sku_id: str
) -> float:
    return float(balances.get((order_id, order_sku_id), balances.get((order_id, ""), 0.0)) or 0.0)


def _apply_balance_delta(
    balances: dict[tuple[str, str], float], order_id: str, order_sku_id: str, delta: float
) -> None:
    key = (order_id, order_sku_id)
    fallback = (order_id, "")
    target = key if key in balances or fallback not in balances else fallback
    balances[target] = float(balances.get(target, 0.0)) + float(delta)


def translate_orders(
    db_path: Path,
    since: date,
    until: date,
    apply: bool,
    run_id: str,
    allow_missing: bool = False,
    output_path: Path | None = None,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
    order_id_allowlist: set[str] | None = None,
    only_cashflow_status: str | None = None,
) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    order_id_filter = _normalize_order_id_allowlist(order_id_allowlist)
    status_filter = _normalize_only_cashflow_status(only_cashflow_status)

    report_lines = []
    apply_metadata: dict[str, object] = {}
    if apply:
        apply_metadata = _prepare_cashflow_apply_guard(
            db_path,
            expected_pre_sha256=expected_pre_sha256,
            backup_dir=backup_dir,
        )
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        config = {}
        if DEFAULT_CONFIG.exists():
            config = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}

        weights = _load_dim_sku_weights(conn)
        dim_costs = _load_dim_sku_costs(conn)
        entries_by_order = _load_order_entries(conn)
        sales_fact_fallback = _load_sales_fact_fallback(conn)
        fact_order_fallback = _load_fact_order_line_fallback(conn)
        existing_cash = _load_existing_cash_in(conn)
        existing_refunds = _load_existing_refunds(conn)
        existing_on_delivery = _load_existing_on_delivery(conn)
        cash_rows_for_line_matching = _load_existing_cash_rows(conn)
        order_entry_d1_cash_order_skus = _load_order_entry_cash_order_skus(conn)
        existing_cogs_dates = _load_existing_cogs_dates(conn)
        existing_move_dates = _load_existing_move_dates(conn)
        on_delivery_balances = _load_on_delivery_balances(conn)
        existing_cash_order_ids = {order_id for order_id, _ in existing_cash}
        existing_refund_order_ids = {order_id for order_id, _ in existing_refunds}
        existing_cogs_order_ids = {order_id for order_id, _ in existing_cogs_dates}
        existing_on_delivery_order_ids = {order_id for order_id, _ in existing_on_delivery}
        fx_rates = get_supplier_fx_rates(until.isoformat(), db_path=db_path)

        rows = conn.execute(
            """
            SELECT *
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
                  BETWEEN ? AND ?
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()
        if order_id_filter is not None:
            rows = [
                row
                for row in rows
                if str(row["order_id"] or "").strip() in order_id_filter
            ]
        status_filtered_out = 0
        if status_filter is not None:
            status_filtered_rows = []
            for row in rows:
                row_status = _cashflow_status_from_stage(classify_kaspi_stage_from_db_row(row))
                if row_status == status_filter:
                    status_filtered_rows.append(row)
                else:
                    status_filtered_out += 1
            rows = status_filtered_rows
        # Some orders have duplicate history rows where one row already has SKU identity,
        # but the resolved sibling can be outside this date window.
        # Build resolved keys from the whole table and use them only as a missing-SKU guard.
        resolved_order_keys = {
            (str(r[0]), str(r[1]))
            for r in conn.execute(
                """
                SELECT DISTINCT order_id, store_code
                FROM fact_orders_kaspi
                WHERE order_id IS NOT NULL
                  AND store_code IS NOT NULL
                  AND sku_key IS NOT NULL
                  AND trim(sku_key) <> ''
                  AND sku_id IS NOT NULL
                  AND trim(sku_id) <> ''
                """
            ).fetchall()
        }
        resolved_order_ids = {order_id for order_id, _ in resolved_order_keys}
        resolved_order_ids_from_entries = {
            order_id
            for (order_id, _store), lines in entries_by_order.items()
            if any(line.get("sku_key") and line.get("sku_id") for line in lines)
        }
        resolved_order_ids_from_sales = {
            order_id
            for (order_id, _store), lines in sales_fact_fallback.items()
            if any(line.get("sku_key") and line.get("sku_id") for line in lines)
        }
        # Some legacy CRM exports persist as UNKNOWN-store shadow rows, even when a
        # resolved non-UNKNOWN row exists for the same order/SKU outside the active window.
        # Skip those shadows to avoid duplicate COGS/backfill events.
        non_unknown_row_tokens: set[tuple[str, str]] = set()
        for row_order_id, row_sku_id, row_sku_key in conn.execute(
            """
            SELECT order_id, sku_id, sku_key
            FROM fact_orders_kaspi
            WHERE order_id IS NOT NULL
              AND trim(order_id) <> ''
              AND store_code IS NOT NULL
              AND UPPER(trim(store_code)) <> 'UNKNOWN'
              AND (
                    (sku_id IS NOT NULL AND trim(sku_id) <> '')
                 OR (sku_key IS NOT NULL AND trim(sku_key) <> '')
              )
            """
        ).fetchall():
            oid = str(row_order_id).strip()
            sid = str(row_sku_id or "").strip()
            skey = str(row_sku_key or "").strip()
            if sid:
                non_unknown_row_tokens.add((oid, sid))
            if skey:
                non_unknown_row_tokens.add((oid, skey))
        non_unknown_order_ids = {order_id for order_id, _ in non_unknown_row_tokens}
        resolved_completed_rows_by_key: dict[tuple[str, str], dict[str, str]] = {}
        for row_order_id, row_store_code, row_sku_key, row_sku_id in conn.execute(
            """
            SELECT order_id, store_code, sku_key, sku_id
            FROM fact_orders_kaspi
            WHERE order_id IS NOT NULL
              AND trim(order_id) <> ''
              AND store_code IS NOT NULL
              AND UPPER(trim(store_code)) <> 'UNKNOWN'
              AND internal_status = 'COMPLETED'
              AND sku_key IS NOT NULL
              AND trim(sku_key) <> ''
              AND sku_id IS NOT NULL
              AND trim(sku_id) <> ''
            """
        ).fetchall():
            key = (str(row_order_id), str(row_sku_id))
            resolved_completed_rows_by_key.setdefault(
                key,
                {
                    "order_id": str(row_order_id),
                    "store_code": str(row_store_code),
                    "sku_key": str(row_sku_key),
                    "sku_id": str(row_sku_id),
                },
            )

        events = []
        missing_sku = []
        missing_cost = []
        counts = {"completed": 0, "cancelled": 0, "on_delivery": 0, "ignored": 0}
        stagecode_events: list[dict] = []
        stagecode_counts: Counter = Counter()
        if status_filter is None:
            stagecode_events, stagecode_counts = _build_stagecode_d1_events(
                conn,
                since=since,
                until=until,
                run_id=run_id,
                weights=weights,
                entries_by_order=entries_by_order,
                sales_fact_fallback=sales_fact_fallback,
                fact_order_fallback=fact_order_fallback,
                order_id_filter=order_id_filter,
            )
        events.extend(stagecode_events)
        for event in stagecode_events:
            if event.get("event_type") != "CASH_IN":
                continue
            ref_id = str(event.get("ref_id") or "")
            sku_id = str(event.get("sku_id") or "")
            note = str(event.get("notes") or "")
            order_id_from_note = ""
            if "order_id=" in note:
                order_id_from_note = note.split("order_id=", 1)[1].split()[0]
            if float(event.get("amount_kzt") or 0.0) > 0 and order_id_from_note:
                existing_cash.add((order_id_from_note, sku_id))
                existing_cash_order_ids.add(order_id_from_note)
                cash_rows_for_line_matching.append(event)
                if str(event.get("ref_type") or "").strip().upper() == "ORDER_ENTRY":
                    order_entry_d1_cash_order_skus.add((order_id_from_note, sku_id))
            if float(event.get("amount_kzt") or 0.0) < 0 and order_id_from_note:
                existing_refunds.add((order_id_from_note, sku_id))
                existing_refund_order_ids.add(order_id_from_note)
                cash_rows_for_line_matching.append(event)

        # Global corrective pass: if completed orders already have cash/cogs but their
        # INVENTORY_ON_DELIVERY_COST balance is non-zero, add a balancing COGS entry.
        # Restrict corrections to cogs dates inside the requested window.
        stagecode_d1_order_pairs = set()
        if status_filter is None:
            stagecode_d1_order_pairs = set(_stage_events_by_order(conn, since, until).keys())
            for (order_id, order_sku_id), row_meta in resolved_completed_rows_by_key.items():
                if (order_id, str(row_meta["store_code"] or "").strip().upper()) in stagecode_d1_order_pairs:
                    continue
                if not _has_existing(existing_cash, order_id, order_sku_id):
                    continue
                cogs_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id)
                if not cogs_date:
                    continue
                try:
                    cogs_date_obj = date.fromisoformat(str(cogs_date))
                except ValueError:
                    continue
                if cogs_date_obj < since or cogs_date_obj > until:
                    continue
                imbalance = _get_existing_balance(on_delivery_balances, order_id, order_sku_id)
                if abs(imbalance) <= 0.01:
                    continue
                correction = round(-imbalance, 2)
                events.append(
                    {
                        "event_date": cogs_date_obj.isoformat(),
                        "event_type": "COGS_RECOGNIZED",
                        "account": "INVENTORY_ON_DELIVERY_COST",
                        "amount_kzt": correction,
                        "store_code": row_meta["store_code"],
                        "sku_key": row_meta["sku_key"],
                        "sku_id": row_meta["sku_id"],
                        "ref_type": "ORDER",
                        "ref_id": row_meta["order_id"],
                        "source": "ORDER_MODELLED",
                        "run_id": run_id,
                        "notes": "Backfill on-delivery balance correction",
                    }
                )
                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, correction)

        for row in rows:
            stage = classify_kaspi_stage_from_db_row(row)
            raw_internal_status = str(row["internal_status"] or "").strip().upper()
            status = _cashflow_status_from_stage(stage)
            if status is None:
                counts["ignored"] += 1
                continue
            if status_filter is not None and status != status_filter:
                counts["ignored"] += 1
                continue
            event_date = (
                _parse_date(row["status_updated_at"])
                or _parse_date(row["actual_shipment_date"])
                or _parse_date(row["planned_shipment_date"])
                or _parse_date(row["created_at"])
            )
            if not event_date:
                counts["ignored"] += 1
                continue
            if status not in {"COMPLETED", "CANCELLED", "RETURNED", "ON_DELIVERY"}:
                counts["ignored"] += 1
                continue
            order_id = str(row["order_id"]) if row["order_id"] is not None else ""
            store_code = str(row["store_code"] or "").strip().upper()
            store_code_norm = str(store_code or "").strip().upper()
            if status in {"COMPLETED", "CANCELLED"} and (order_id, store_code_norm) in stagecode_d1_order_pairs:
                counts["ignored"] += 1
                continue
            row_sku_id = str(row["sku_id"] or "").strip()
            row_sku_key = str(row["sku_key"] or "").strip()
            if store_code_norm == "UNKNOWN":
                if (
                    (row_sku_id and (order_id, row_sku_id) in non_unknown_row_tokens)
                    or (row_sku_key and (order_id, row_sku_key) in non_unknown_row_tokens)
                    or (not row_sku_id and not row_sku_key and order_id in non_unknown_order_ids)
                ):
                    counts["ignored"] += 1
                    continue
            raw_kaspi_status = str(row["kaspi_status"] or "").strip().upper()
            # Guard against premature stage inflation from API fields:
            # if DB still marks order as ACCEPTED/READY, do not model on-delivery moves yet.
            if status == "ON_DELIVERY" and raw_internal_status in {"NEW", "ACCEPTED", "READY"}:
                counts["ignored"] += 1
                continue
            order_lines = []
            if row["sku_key"] and row["sku_id"]:
                order_lines.append(
                    {
                        "sku_key": row["sku_key"],
                        "sku_id": row["sku_id"],
                        "quantity": float(row["quantity"] or 0.0),
                        "unit_price_kzt": row["unit_price_kzt"],
                        "total_price_kzt": None,
                    }
                )
            else:
                order_lines = entries_by_order.get((order_id, str(store_code)), [])
                if not order_lines:
                    order_lines = sales_fact_fallback.get((order_id, str(store_code)), [])
                if not order_lines:
                    if (order_id, str(store_code)) in resolved_order_keys:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_entries:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_sales:
                        counts["ignored"] += 1
                        continue
                    if status in {"COMPLETED", "ON_DELIVERY"}:
                        if order_id in existing_cash_order_ids and order_id in existing_cogs_order_ids:
                            counts["ignored"] += 1
                            continue
                    if status in {"CANCELLED", "RETURNED"}:
                        if order_id in existing_refund_order_ids:
                            counts["ignored"] += 1
                            continue
                        if (
                            order_id not in existing_cash_order_ids
                            and order_id not in existing_on_delivery_order_ids
                            and order_id not in existing_cogs_order_ids
                        ):
                            counts["ignored"] += 1
                            continue
                    missing_sku.append(f"{order_id}:{store_code}")
                    counts["ignored"] += 1
                    continue

            for line in order_lines:
                qty = float(line.get("quantity") or 0.0)
                if qty <= 0:
                    counts["ignored"] += 1
                    continue

                sku_key = line.get("sku_key")
                sku_id = line.get("sku_id")
                if not sku_key or not sku_id:
                    if status in {"COMPLETED", "CANCELLED"} and line.get("line_ref_type") == "ORDER_ENTRY":
                        single_line_order = len(order_lines) == 1
                        existing_positive = _cash_matches_line(
                            cash_rows_for_line_matching,
                            order_id=order_id,
                            line=line,
                            event_date=event_date,
                            positive=True,
                            single_line_order=single_line_order,
                        )
                        ref_type, ref_id = _line_ref(line, order_id)
                        if status == "COMPLETED" and not existing_positive:
                            cash_event = {
                                "event_date": event_date,
                                "event_type": "CASH_IN",
                                "account": _cash_account(store_code),
                                "amount_kzt": _net_cash_amount_for_line(line, event_date, weights),
                                "store_code": store_code,
                                "sku_key": "",
                                "sku_id": "",
                                "ref_type": ref_type,
                                "ref_id": ref_id,
                                "source": "ORDER_MODELLED",
                                "run_id": run_id,
                                "notes": f"D1 cash-in from StageCode; order_id={order_id}",
                            }
                            if not any(_event_hash(cash_event) == _event_hash(existing) for existing in events):
                                events.append(cash_event)
                                cash_rows_for_line_matching.append(cash_event)
                                counts["completed"] += 1
                        elif status == "CANCELLED":
                            existing_negative = _cash_matches_line(
                                cash_rows_for_line_matching,
                                order_id=order_id,
                                line=line,
                                event_date=event_date,
                                positive=False,
                                single_line_order=single_line_order,
                            )
                            if existing_positive and not existing_negative:
                                cash_event = {
                                    "event_date": event_date,
                                    "event_type": "CASH_IN",
                                    "account": _cash_account(store_code),
                                    "amount_kzt": -abs(float(existing_positive[0].get("amount_kzt") or 0.0)),
                                    "store_code": store_code,
                                    "sku_key": "",
                                    "sku_id": "",
                                    "ref_type": ref_type,
                                    "ref_id": ref_id,
                                    "source": "ORDER_MODELLED",
                                    "run_id": run_id,
                                    "notes": f"D1 cash reversal from return/cancel StageCode; order_id={order_id}",
                                }
                                if not any(_event_hash(cash_event) == _event_hash(existing) for existing in events):
                                    events.append(cash_event)
                                    cash_rows_for_line_matching.append(cash_event)
                                    counts["cancelled"] += 1
                        counts["ignored"] += 1
                        continue
                    if (order_id, str(store_code)) in resolved_order_keys:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_entries:
                        counts["ignored"] += 1
                        continue
                    if order_id in resolved_order_ids_from_sales:
                        counts["ignored"] += 1
                        continue
                    if status in {"COMPLETED", "ON_DELIVERY"}:
                        if order_id in existing_cash_order_ids and order_id in existing_cogs_order_ids:
                            counts["ignored"] += 1
                            continue
                    if status in {"CANCELLED", "RETURNED"}:
                        if order_id in existing_refund_order_ids:
                            counts["ignored"] += 1
                            continue
                        if (
                            order_id not in existing_cash_order_ids
                            and order_id not in existing_on_delivery_order_ids
                            and order_id not in existing_cogs_order_ids
                        ):
                            counts["ignored"] += 1
                            continue
                    missing_sku.append(f"{order_id}:{store_code}")
                    counts["ignored"] += 1
                    continue

                sell_price = line.get("unit_price_kzt")
                if not sell_price and line.get("total_price_kzt") and qty > 0:
                    sell_price = float(line.get("total_price_kzt") or 0.0) / qty
                sell_price = float(sell_price or 0.0)

                weight = weights.get(sku_key or "", 0.0)
                vat_rate = get_vat_rate(date.fromisoformat(event_date))
                delivery_fee = calc_delivery_fee(sell_price, weight_kg=weight, delivery_type="city")
                net_rev_unit = calc_net_rev(
                    sell_price,
                    delivery_fee=delivery_fee,
                    weight_kg=weight,
                    as_of_date=date.fromisoformat(event_date),
                )
                net_rev_line = round(net_rev_unit * qty, 2)
                delivery_fee_line = round(float(delivery_fee or 0.0) * qty, 2)
                unit_cost = _unit_cost_kzt_for_sku(sku_key, fx_rates, dim_costs)
                if unit_cost <= 0:
                    missing_cost.append(f"{order_id}:{sku_key}")
                    counts["ignored"] += 1
                    continue
                cost_line = round(unit_cost * qty, 2)

                order_sku_id = str(sku_id)
                order_key = (order_id, order_sku_id)
                base_fields = {
                    "store_code": store_code,
                    "sku_key": sku_key,
                    "sku_id": order_sku_id,
                    "ref_type": "ORDER",
                    "ref_id": order_id,
                    "source": "ORDER_MODELLED",
                    "run_id": run_id,
                }

                if status == "COMPLETED":
                    if _has_existing(existing_cash, order_id, order_sku_id):
                        if (order_id, order_sku_id) in order_entry_d1_cash_order_skus:
                            counts["ignored"] += 1
                            continue
                        # Legacy rows may have cash recorded but only zero-cost inventory events.
                        # Backfill missing non-zero COGS while preserving cash idempotency.
                        cogs_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id)
                        if not cogs_date:
                            move_date = _get_existing_date(existing_move_dates, order_id, order_sku_id)
                            cogs_date = move_date or event_date
                            if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_HAND_COST",
                                        "amount_kzt": -abs(cost_line),
                                        **base_fields,
                                        "notes": "Backfill on-delivery at completion",
                                    }
                                )
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_DELIVERY_COST",
                                        "amount_kzt": abs(cost_line),
                                        **base_fields,
                                        "notes": "Backfill on-delivery at completion",
                                    }
                                )
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                                existing_on_delivery.add(order_key)
                            events.append(
                                {
                                    "event_date": cogs_date,
                                    "event_type": "COGS_RECOGNIZED",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": -abs(cost_line),
                                    **base_fields,
                                    "notes": "Backfill missing COGS",
                                }
                            )
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, -abs(cost_line))
                            existing_cogs_dates[order_key] = cogs_date
                            counts["completed"] += 1
                            continue

                        # Cash/COGS already recorded; only backfill on-delivery if missing.
                        if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                            backfill_date = cogs_date or event_date
                            events.append(
                                {
                                    "event_date": backfill_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_HAND_COST",
                                    "amount_kzt": -abs(cost_line),
                                    **base_fields,
                                    "notes": "Backfill on-delivery at completion",
                                }
                            )
                            events.append(
                                {
                                    "event_date": backfill_date,
                                    "event_type": "INVENTORY_MOVE",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": abs(cost_line),
                                    **base_fields,
                                    "notes": "Backfill on-delivery at completion",
                                }
                            )
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                            existing_on_delivery.add(order_key)
                        else:
                            move_date = _get_existing_date(existing_move_dates, order_id, order_sku_id)
                            if cogs_date and move_date and move_date > cogs_date:
                                # Shift on-delivery timing earlier to avoid negative balance on cogs date.
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_HAND_COST",
                                        "amount_kzt": -abs(cost_line),
                                        **base_fields,
                                        "notes": "Timing shift (earlier on-delivery)",
                                    }
                                )
                                events.append(
                                    {
                                        "event_date": cogs_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_DELIVERY_COST",
                                        "amount_kzt": abs(cost_line),
                                        **base_fields,
                                        "notes": "Timing shift (earlier on-delivery)",
                                    }
                                )
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                                events.append(
                                    {
                                        "event_date": move_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_HAND_COST",
                                        "amount_kzt": abs(cost_line),
                                        **base_fields,
                                        "notes": "Timing shift (reverse later move)",
                                    }
                                )
                                events.append(
                                    {
                                        "event_date": move_date,
                                        "event_type": "INVENTORY_MOVE",
                                        "account": "INVENTORY_ON_DELIVERY_COST",
                                        "amount_kzt": -abs(cost_line),
                                        **base_fields,
                                        "notes": "Timing shift (reverse later move)",
                                    }
                                )
                                _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, -abs(cost_line))
                        imbalance = _get_existing_balance(on_delivery_balances, order_id, order_sku_id)
                        if abs(imbalance) > 0.01:
                            correction = round(-imbalance, 2)
                            events.append(
                                {
                                    "event_date": cogs_date or event_date,
                                    "event_type": "COGS_RECOGNIZED",
                                    "account": "INVENTORY_ON_DELIVERY_COST",
                                    "amount_kzt": correction,
                                    **base_fields,
                                    "notes": "Backfill on-delivery balance correction",
                                }
                            )
                            _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, correction)
                        counts["ignored"] += 1
                        continue
                    counts["completed"] += 1
                    if not _has_existing(existing_on_delivery, order_id, order_sku_id):
                        backfill_date = _get_existing_date(existing_cogs_dates, order_id, order_sku_id) or event_date
                        events.append(
                            {
                                "event_date": backfill_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_HAND_COST",
                                "amount_kzt": -abs(cost_line),
                                **base_fields,
                                "notes": "Backfill on-delivery at completion",
                            }
                        )
                        events.append(
                            {
                                "event_date": backfill_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_DELIVERY_COST",
                                "amount_kzt": abs(cost_line),
                                **base_fields,
                                "notes": "Backfill on-delivery at completion",
                                }
                            )
                        existing_on_delivery.add(order_key)
                    events.append(
                        {
                            "event_date": event_date,
                            "event_type": "CASH_IN",
                            "account": _cash_account(store_code),
                            "amount_kzt": net_rev_line,
                            **base_fields,
                        }
                    )
                    events.append(
                        {
                            "event_date": event_date,
                            "event_type": "COGS_RECOGNIZED",
                            "account": "INVENTORY_ON_DELIVERY_COST",
                            "amount_kzt": -abs(cost_line),
                            **base_fields,
                        }
                    )
                    existing_cogs_dates[order_key] = event_date
                    existing_cash.add(order_key)
                elif status == "CANCELLED":
                    did_write = False
                    on_delivery_balance = _get_existing_balance(on_delivery_balances, order_id, order_sku_id)
                    if abs(on_delivery_balance) > 0.01:
                        settle_amount = round(on_delivery_balance, 2)
                        events.append(
                            {
                                "event_date": event_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_HAND_COST",
                                "amount_kzt": settle_amount,
                                **base_fields,
                                "notes": "Settlement from on-delivery",
                            }
                        )
                        events.append(
                            {
                                "event_date": event_date,
                                "event_type": "INVENTORY_MOVE",
                                "account": "INVENTORY_ON_DELIVERY_COST",
                                "amount_kzt": -settle_amount,
                                **base_fields,
                                "notes": "Settlement from on-delivery",
                            }
                        )
                        _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, -settle_amount)
                        did_write = True

                    has_cash = _has_existing(existing_cash, order_id, order_sku_id)
                    already_refunded = _has_existing(existing_refunds, order_id, order_sku_id)
                    if has_cash and not already_refunded:
                        refund_cash = -abs(net_rev_line + delivery_fee_line)
                        events.append(
                            {
                                "event_date": event_date,
                                "event_type": "CASH_IN",
                                "account": _cash_account(store_code),
                                "amount_kzt": refund_cash,
                                **base_fields,
                            }
                        )
                        if abs(on_delivery_balance) <= 0.01:
                            events.append(
                                {
                                    "event_date": event_date,
                                    "event_type": "INVENTORY_RETURN",
                                    "account": "INVENTORY_ON_HAND_COST",
                                    "amount_kzt": abs(cost_line),
                                    **base_fields,
                                }
                            )
                        existing_refunds.add(order_key)
                        did_write = True

                    if did_write:
                        counts["cancelled"] += 1
                    else:
                        counts["ignored"] += 1
                        continue
                elif status == "ON_DELIVERY":
                    if _has_existing(existing_on_delivery, order_id, order_sku_id):
                        counts["ignored"] += 1
                        continue
                    counts["on_delivery"] += 1
                    events.append(
                        {
                            "event_date": event_date,
                            "event_type": "INVENTORY_MOVE",
                            "account": "INVENTORY_ON_HAND_COST",
                            "amount_kzt": -abs(cost_line),
                            **base_fields,
                            "notes": "Move to on-delivery",
                        }
                    )
                    events.append(
                        {
                            "event_date": event_date,
                            "event_type": "INVENTORY_MOVE",
                            "account": "INVENTORY_ON_DELIVERY_COST",
                            "amount_kzt": abs(cost_line),
                            **base_fields,
                            "notes": "On-delivery inventory",
                        }
                    )
                    _apply_balance_delta(on_delivery_balances, order_id, order_sku_id, abs(cost_line))
                    existing_on_delivery.add(order_key)
                else:
                    counts["ignored"] += 1
                    continue

        if missing_sku or missing_cost:
            messages = []
            if missing_sku:
                sample = ", ".join(missing_sku[:5])
                messages.append(
                    "Missing SKU resolution for "
                    f"{len(missing_sku)} order lines (sample: {sample}). "
                    "Run order enrichment to populate fact_order_entries_kaspi "
                    "and ensure dim_kaspi_article_map covers offer_id."
                )
            if missing_cost:
                sample = ", ".join(missing_cost[:5])
                messages.append(
                    "Missing unit cost for "
                    f"{len(missing_cost)} order lines (sample: {sample}). "
                    "Ensure dim_sku has base_cost_cny or cogs_kzt (or weight for calc_cogs)."
                )
            d1_stagecode_evidence_exists = bool(
                stagecode_counts.get("cash_in_candidates")
                or stagecode_counts.get("cash_in_existing")
                or stagecode_counts.get("reversal_candidates")
                or stagecode_counts.get("reversal_existing")
            )
            if not allow_missing and not d1_stagecode_evidence_exists:
                raise RuntimeError(" ".join(messages))
            report_lines.append(
                "WARNING: missing SKU/cost data quarantined from inventory/COGS translation"
            )
            for msg in messages:
                report_lines.append(f"  - {msg}")

        new_events = []
        if events:
            for event in events:
                event["event_hash"] = _event_hash(event)
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                        ",".join("?" * len(events))
                    ),
                    [e["event_hash"] for e in events],
                ).fetchall()
            }
            new_events = [e for e in events if e["event_hash"] not in existing_hashes]

        if order_id_filter is not None:
            report_lines.append(f"Order allowlist entries: {len(order_id_filter)}")
        if status_filter is not None:
            report_lines.append(f"Only cashflow status: {status_filter}")
            report_lines.append(f"Rows filtered by cashflow status: {status_filtered_out}")
        report_lines.append(f"Orders scanned: {len(rows)}")
        report_lines.append(f"StageCode D1 cash-in candidates: {stagecode_counts.get('cash_in_candidates', 0)}")
        report_lines.append(f"StageCode D1 existing cash-in lines: {stagecode_counts.get('cash_in_existing', 0)}")
        report_lines.append(f"StageCode D1 reversal candidates: {stagecode_counts.get('reversal_candidates', 0)}")
        report_lines.append(f"StageCode D1 missing line evidence: {stagecode_counts.get('missing_line_evidence', 0)}")
        report_lines.append(f"StageCode D1 missing amount evidence: {stagecode_counts.get('missing_amount_evidence', 0)}")
        report_lines.append(f"Completed orders: {counts['completed']}")
        report_lines.append(f"Cancelled/returned orders: {counts['cancelled']}")
        report_lines.append(f"On-delivery orders: {counts['on_delivery']}")
        report_lines.append(f"Ignored orders: {counts['ignored']}")
        report_lines.append(f"New cashflow events: {len(new_events)}")
        if new_events:
            report_lines.append(
                "EVENT_HEADER\tevent_date\tevent_type\taccount\tamount_kzt\tstore_code\t"
                "sku_key\tsku_id\tref_type\tref_id\tnotes\tsource\trun_id"
            )
            for event in sorted(
                new_events,
                key=lambda item: (
                    str(item.get("ref_id") or ""),
                    str(item.get("event_type") or ""),
                    str(item.get("account") or ""),
                    float(item.get("amount_kzt") or 0.0),
                ),
            ):
                report_lines.append(_event_scope_line(event))

        if apply:
            for event in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                        ref_type, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("sku_key"),
                        event.get("sku_id"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source"),
                        event.get("run_id"),
                        event.get("event_hash"),
                    ),
                )
            conn.commit()

    if apply_metadata:
        report_lines.append(f"Apply production target: {bool(apply_metadata.get('production_apply'))}")
    if apply_metadata.get("production_apply"):
        post_integrity = _sqlite_integrity_check(db_path)
        if post_integrity.lower() != "ok":
            raise RuntimeError(f"production DB integrity_check failed after cashflow apply: {post_integrity}")
        apply_metadata["post_sha256"] = _sha256_file(db_path)
        apply_metadata["post_integrity_check"] = post_integrity
        report_lines.append(f"Production pre SHA256: {apply_metadata['pre_sha256']}")
        report_lines.append(f"Production post SHA256: {apply_metadata['post_sha256']}")
        report_lines.append(f"Production backup path: {apply_metadata['backup_path']}")
        report_lines.append(f"Production backup SHA256: {apply_metadata['backup_sha256']}")
        report_lines.append(f"Production integrity check: {apply_metadata['post_integrity_check']}")

    report_path = output_path or EXPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate Kaspi orders into cashflow events")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--since", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply writes (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip unresolved/missing-cost lines and continue with deterministic rows",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Write the dry-run/apply report to this path instead of exports/orders_to_cashflow_report.txt",
    )
    parser.add_argument("--expected-pre-sha256", type=str, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument(
        "--order-id-file",
        type=Path,
        default=None,
        help="Restrict modeled order rows to newline-delimited order IDs; empty files fail closed.",
    )
    parser.add_argument(
        "--only-cashflow-status",
        type=str,
        default=None,
        help="Restrict modeled order rows to a supported cashflow status (currently: ON_DELIVERY).",
    )
    args = parser.parse_args()

    cutoff = get_cutoff_date_almaty()
    since = date.fromisoformat(args.since) if args.since else cutoff - timedelta(days=30)
    until = date.fromisoformat(args.until) if args.until else cutoff
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    if since > until:
        raise ValueError("--since must be <= --until")

    return translate_orders(
        args.db,
        since,
        until,
        args.apply,
        run_id,
        allow_missing=bool(args.allow_missing),
        output_path=args.output_path,
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
        order_id_allowlist=_read_order_id_file(args.order_id_file) if args.order_id_file else None,
        only_cashflow_status=args.only_cashflow_status,
    )


if __name__ == "__main__":
    raise SystemExit(main())
