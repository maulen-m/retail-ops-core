#!/usr/bin/env python3
"""Return-pickup queue report for courier-terminal collections."""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_ACK_PATH = PROJECT_ROOT / "runtime" / "state" / "returns_pickup_ack.json"
ALMATY_TZ = ZoneInfo("Asia/Almaty")

STORE_DISPLAY = {
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "STOREB": "STORE-B",
    "11KZ": "11KZ",
    "MELVIS": "Store-C",
}
STORE_SHORTCUT = {
    "ACMEWEAR": "OF",
    "UNIVERSAL": "U",
    "STOREB": "MG",
    "11KZ": "11",
    "MELVIS": "MV",
}
STORE_ALIASES = {
    "ACMEWEAR": "ACMEWEAR",
    "ONLY FIT": "ACMEWEAR",
    "OF": "ACMEWEAR",
    "UNIVERSAL": "UNIVERSAL",
    "U": "UNIVERSAL",
    "STORE-B": "STOREB",
    "STOREB": "STOREB",
    "M GROUP": "STOREB",
    "MG": "STOREB",
    "11KZ": "11KZ",
    "11": "11KZ",
    "MELVIS": "MELVIS",
    "MV": "MELVIS",
}


def _now() -> datetime:
    return datetime.now(ALMATY_TZ)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return _upper(value) not in {"", "0", "FALSE", "NO", "N"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _status_day(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    return text[:10]


def _store_display(store_code: str) -> str:
    return STORE_DISPLAY.get(store_code, store_code)


def normalize_store_code(value: Any) -> str | None:
    raw = _upper(value).replace("_", " ")
    raw = " ".join(raw.split())
    if not raw:
        return None
    return STORE_ALIASES.get(raw)


def build_returns_pickup_reply_markup(snapshot: dict[str, Any]) -> dict[str, Any]:
    stores = list(snapshot.get("stores") or [])
    keyboard: list[list[str]] = [["Возвраты", "Помощь"]]
    ack_row: list[str] = []
    for store in stores:
        store_code = _upper(store.get("store_code"))
        shortcut = STORE_SHORTCUT.get(store_code)
        if not shortcut:
            continue
        ack_row.append(f"Забрал {shortcut}")
        if len(ack_row) == 3:
            keyboard.append(ack_row)
            ack_row = []
    if ack_row:
        keyboard.append(ack_row)
    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _ack_key(store_code: str, order_id: str) -> str:
    return f"{store_code}:{order_id}"


def _load_ack_state(path: Path = DEFAULT_ACK_PATH) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"acked_orders": {}}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"acked_orders": {}}
    if not isinstance(payload, dict):
        return {"acked_orders": {}}
    acked_orders = payload.get("acked_orders")
    if not isinstance(acked_orders, dict):
        payload["acked_orders"] = {}
    return payload


def _save_ack_state(state: dict[str, Any], path: Path = DEFAULT_ACK_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _query_pickup_ready_orders(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                UPPER(TRIM(COALESCE(store_code, ''))) AS store_code,
                TRIM(order_id) AS order_id,
                MAX(COALESCE(kaspi_status_detail, '')) AS kaspi_status_detail,
                MAX(COALESCE(status_updated_at, '')) AS status_updated_at,
                SUM(COALESCE(quantity, 1)) AS total_units
            FROM fact_orders_kaspi
            WHERE COALESCE(returned_to_warehouse, 0) IN (1, '1', 'true', 'TRUE')
              AND COALESCE(TRIM(order_id), '') != ''
            GROUP BY UPPER(TRIM(COALESCE(store_code, ''))), TRIM(order_id)
            ORDER BY UPPER(TRIM(COALESCE(store_code, ''))), COALESCE(status_updated_at, ''), TRIM(order_id)
            """
        ).fetchall()
    finally:
        conn.close()

    result: list[dict[str, Any]] = []
    for row in rows:
        store_code = _upper(row["store_code"])
        order_id = _norm(row["order_id"])
        if not store_code or not order_id:
            continue
        result.append(
            {
                "store_code": store_code,
                "display_name": _store_display(store_code),
                "order_id": order_id,
                "api_status": _upper(row["kaspi_status_detail"]),
                "status_updated_at": _norm(row["status_updated_at"]),
                "status_day": _status_day(row["status_updated_at"]),
                "total_units": max(1, _safe_int(row["total_units"], default=1)),
            }
        )
    return result


def build_pickup_ready_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    ack_path: Path = DEFAULT_ACK_PATH,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    all_orders = _query_pickup_ready_orders(db_path)
    ack_state = _load_ack_state(ack_path)
    acked_orders = ack_state.get("acked_orders") or {}

    visible_orders: list[dict[str, Any]] = []
    hidden_acked_orders = 0
    for row in all_orders:
        if _ack_key(row["store_code"], row["order_id"]) in acked_orders:
            hidden_acked_orders += 1
            continue
        visible_orders.append(row)

    visible_orders.sort(key=lambda row: (row["store_code"], row["status_updated_at"] or "9999-99-99", row["order_id"]))

    stores: list[dict[str, Any]] = []
    current_store = None
    bucket: list[dict[str, Any]] = []
    for row in visible_orders + [{"store_code": None}]:
        if row.get("store_code") != current_store:
            if bucket:
                first = bucket[0]
                status_days = [item["status_day"] for item in bucket if item["status_day"]]
                stores.append(
                    {
                        "store_code": current_store,
                        "display_name": _store_display(current_store),
                        "orders": len(bucket),
                        "units": sum(item["total_units"] for item in bucket),
                        "first_order_id": first["order_id"],
                        "oldest_day": min(status_days) if status_days else "",
                        "newest_day": max(status_days) if status_days else "",
                    }
                )
            current_store = row.get("store_code")
            bucket = []
        if row.get("store_code") is not None:
            bucket.append(row)

    return {
        "as_of": (as_of or _now()).isoformat(),
        "total_orders": len(visible_orders),
        "total_units": sum(item["total_units"] for item in visible_orders),
        "hidden_acked_orders": hidden_acked_orders,
        "orders": visible_orders,
        "stores": stores,
    }


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def fmt_row(values: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(values)) + " |"

    sep = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    out = [sep, fmt_row(headers), sep]
    out.extend(fmt_row(row) for row in rows)
    out.append(sep)
    return "\n".join(out)


def format_returns_pickup_message(snapshot: dict[str, Any]) -> str:
    total_orders = int(snapshot.get("total_orders") or 0)
    hidden_acked = int(snapshot.get("hidden_acked_orders") or 0)
    stores = list(snapshot.get("stores") or [])
    as_of = _norm(snapshot.get("as_of")).replace("T", " ")[:16]

    if total_orders <= 0:
        lines = [
            "<b>Returns Pickup Ready</b>",
            f"As of: <code>{html.escape(as_of)}</code>",
            "No unacknowledged returned/cancelled orders are currently marked as back at the pickup point.",
        ]
        if hidden_acked > 0:
            lines.append(f"Already acknowledged and hidden: <code>{hidden_acked}</code>")
        return "\n".join(lines)

    table_rows = [
        [
            store["display_name"],
            str(store["orders"]),
            str(store["units"]),
            store["oldest_day"] or "-",
            store["newest_day"] or "-",
            store["first_order_id"],
        ]
        for store in stores
    ]
    table = format_table(
        ["STORE", "ORDERS", "UNITS", "OLDEST", "NEWEST", "FIRST_ORDER_ID"],
        table_rows,
    )
    lines = [
        "<b>Returns Pickup Ready</b>",
        f"As of: <code>{html.escape(as_of)}</code>",
        f"Pickup-ready orders: <code>{total_orders}</code> | Units: <code>{int(snapshot.get('total_units') or 0)}</code>",
    ]
    if hidden_acked > 0:
        lines.append(f"Already acknowledged and hidden: <code>{hidden_acked}</code>")
    lines.extend(
        [
            "<pre>" + html.escape(table) + "</pre>",
            "Courier lookup IDs by store:",
        ]
    )
    for store in stores:
        lines.append(f"{html.escape(store['display_name'])}: <code>{html.escape(store['first_order_id'])}</code>")
    lines.append("After pickup: <code>/returns_ack_store STORE_CODE</code>")
    return "\n".join(lines)


def ack_current_pickup_orders_for_stores(
    *,
    store_codes: list[str],
    db_path: Path = DEFAULT_DB_PATH,
    ack_path: Path = DEFAULT_ACK_PATH,
    acked_by: str,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    normalized = []
    for item in store_codes:
        code = normalize_store_code(item)
        if code and code not in normalized:
            normalized.append(code)

    snapshot = build_pickup_ready_snapshot(db_path=db_path, ack_path=ack_path, as_of=as_of)
    matching_orders = [row for row in snapshot["orders"] if row["store_code"] in normalized]
    ack_state = _load_ack_state(ack_path)
    acked_orders = ack_state.setdefault("acked_orders", {})
    now_text = (as_of or _now()).isoformat()
    by_store: dict[str, int] = {}
    for row in matching_orders:
        acked_orders[_ack_key(row["store_code"], row["order_id"])] = {
            "store_code": row["store_code"],
            "order_id": row["order_id"],
            "acked_at": now_text,
            "acked_by": str(acked_by),
        }
        by_store[row["store_code"]] = by_store.get(row["store_code"], 0) + 1

    _save_ack_state(ack_state, ack_path)
    return {
        "acked_orders": len(matching_orders),
        "stores": [
            {
                "store_code": code,
                "display_name": _store_display(code),
                "acked_orders": by_store.get(code, 0),
            }
            for code in normalized
            if by_store.get(code, 0) > 0
        ],
    }


def unack_pickup_orders(
    *,
    order_ids: list[str],
    ack_path: Path = DEFAULT_ACK_PATH,
) -> dict[str, Any]:
    normalized = {_norm(item) for item in order_ids if _norm(item)}
    ack_state = _load_ack_state(ack_path)
    acked_orders = dict(ack_state.get("acked_orders") or {})
    kept: dict[str, Any] = {}
    restored: list[dict[str, str]] = []
    for key, payload in acked_orders.items():
        order_id = _norm((payload or {}).get("order_id"))
        if order_id in normalized:
            restored.append(
                {
                    "store_code": _upper((payload or {}).get("store_code")),
                    "order_id": order_id,
                }
            )
            continue
        kept[key] = payload
    ack_state["acked_orders"] = kept
    _save_ack_state(ack_state, ack_path)
    return {
        "restored_orders": len(restored),
        "orders": restored,
    }
