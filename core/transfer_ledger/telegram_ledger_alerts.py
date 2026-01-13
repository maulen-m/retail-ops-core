"""Telegram alert helpers for transfer ledger updates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sqlite3
from typing import Optional

from core.alerts.telegram import get_telegram_config, send_message
from core.transfer_ledger.repository import (
    get_po_total_cny_from_lines,
    list_po_funding_plan,
    list_pos_for_allocation,
    list_po_exchanger_allocations,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "db" / "app.db"
LOCAL_TZ = timezone(timedelta(hours=5))
UTC = timezone.utc
EPOCH = datetime.min.replace(tzinfo=UTC)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        else:
            dt = dt.astimezone(UTC)
        return dt
    except Exception:
        return None


def _fmt_dt(value) -> str:
    dt = value if isinstance(value, datetime) else _parse_dt(value)
    if not dt:
        return ""
    local = dt.astimezone(LOCAL_TZ)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return ""


def _ascii_table(rows, cols) -> list[str]:
    widths = [w for _, w in cols]
    sep = "+" + "+".join("-" * w for w in widths) + "+"
    header = "|" + "|".join(name.ljust(widths[i]) for i, (name, _) in enumerate(cols)) + "|"
    lines = [sep, header, sep]
    for r in rows:
        line = "|" + "|".join(str(r[i]).ljust(widths[i])[:widths[i]] for i in range(len(cols))) + "|"
        lines.append(line)
    lines.append(sep)
    return lines


def _avg_recent_rate(rates: list[tuple[datetime, float]], dt: Optional[datetime], window: int = 5) -> Optional[float]:
    if not dt:
        if rates:
            return rates[-1][1]
        return None
    values = [rate for rate_dt, rate in rates if rate_dt and rate_dt <= dt]
    if not values:
        return rates[-1][1] if rates else None
    recent = values[-window:]
    return sum(recent) / len(recent)


def _load_po_plan(conn: sqlite3.Connection) -> list[tuple[datetime, str, Optional[float], Optional[float]]]:
    plan_rows = list_po_funding_plan(db_path=DB_PATH)
    if plan_rows:
        plan = []
        for row in plan_rows:
            po_id = row.get("po_id")
            po_date = _parse_dt(row.get("message_date"))
            if not po_id or not po_date:
                continue
            total_cny = row.get("total_cny")
            total_usdt = row.get("total_usdt")
            try:
                total_cny = float(total_cny) if total_cny is not None else None
            except Exception:
                total_cny = None
            try:
                total_usdt = float(total_usdt) if total_usdt is not None else None
            except Exception:
                total_usdt = None
            plan.append((po_date, po_id, total_cny, total_usdt))
        return plan

    # Fallback to PO header/lines
    po_rows = list_pos_for_allocation(db_path=DB_PATH)
    plan = []
    for row in po_rows:
        po_id = row.get("po_id")
        po_date = _parse_dt(row.get("message_date") or row.get("created_at"))
        if not po_id or not po_date:
            continue
        total_cny = row.get("total_cost_cny")
        if total_cny is None or float(total_cny or 0) <= 0:
            total_cny = get_po_total_cny_from_lines(po_id, db_path=DB_PATH)
        try:
            total_cny = float(total_cny) if total_cny is not None else None
        except Exception:
            total_cny = None
        plan.append((po_date, po_id, total_cny, None))
    return plan


def _load_exchanger_orders(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT exchanger_order_id, exchanger, order_id, status, message_date,
               amount_usdt, amount_cny, deposit_address
        FROM exchanger_orders
        WHERE amount_usdt IS NOT NULL AND amount_cny IS NOT NULL
        ORDER BY message_date ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _load_p2p_orders(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT order_number, create_time, fiat_amount, crypto_amount, unit_price
        FROM binance_c2c_orders
        WHERE trade_type='BUY' AND asset='USDT' AND fiat='KZT' AND order_status='COMPLETED'
        ORDER BY create_time DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _estimate_paid_kzt(paid_usdt: float, p2p_orders: list[dict]) -> Optional[float]:
    if paid_usdt <= 0:
        return None
    remaining = paid_usdt
    paid_kzt = 0.0
    for order in p2p_orders:
        order_usdt = order.get("crypto_amount")
        order_kzt = order.get("fiat_amount")
        if order_usdt is None or order_kzt is None:
            continue
        try:
            order_usdt = float(order_usdt)
            order_kzt = float(order_kzt)
        except Exception:
            continue
        if order_usdt <= 0:
            continue
        unit_rate = order_kzt / order_usdt
        take = min(remaining, order_usdt)
        paid_kzt += take * unit_rate
        remaining -= take
        if remaining <= 0:
            break
    return paid_kzt if paid_kzt > 0 else None


def _build_po_state(
    orders: list[dict],
    po_plan: list[tuple[datetime, str, Optional[float], Optional[float]]],
    alloc_map: dict[str, str],
    ex_rates: list[tuple[datetime, float]],
) -> tuple[dict[str, dict], dict[str, str], dict[str, datetime], dict[str, Optional[float]]]:
    po_state = {}
    po_dates = {}
    po_total_usdt = {}
    for po_date, po_id, total_cny, total_usdt in sorted(po_plan, key=lambda x: (x[0], x[1])):
        po_state[po_id] = {
            "total_cny": total_cny,
            "paid_cny": 0.0,
            "paid_usdt": 0.0,
        }
        po_dates[po_id] = po_date
        po_total_usdt[po_id] = total_usdt

    if not po_state:
        return {}, {}, {}, {}

    po_list = sorted(
        [(po_dates[po_id], po_id, po_state[po_id]["total_cny"]) for po_id in po_state],
        key=lambda x: (x[0], x[1]),
    )

    orders = [
        o for o in orders
        if o.get("amount_cny") is not None and o.get("amount_usdt") is not None
    ]
    orders.sort(key=lambda o: _parse_dt(o.get("message_date")) or EPOCH)

    order_to_po: dict[str, str] = {}
    po_last_payment: dict[str, datetime] = {}

    po_idx = 0
    for order in orders:
        if (order.get("status") or "").upper() == "CANCELLED":
            continue
        order_dt = _parse_dt(order.get("message_date"))
        if not order_dt:
            continue
        amount_cny = float(order.get("amount_cny") or 0)
        amount_usdt = float(order.get("amount_usdt") or 0)
        if amount_cny <= 0 or amount_usdt <= 0:
            continue

        ex_id = order.get("exchanger_order_id")
        explicit_po = alloc_map.get(ex_id)
        if explicit_po and explicit_po in po_state:
            po_state[explicit_po]["paid_cny"] += amount_cny
            po_state[explicit_po]["paid_usdt"] += amount_usdt
            order_to_po[ex_id] = explicit_po
            po_last_payment[explicit_po] = order_dt
            continue

        while po_idx + 1 < len(po_list) and order_dt >= po_list[po_idx + 1][0]:
            po_idx += 1

        remaining = amount_cny
        last_po_id = None
        i = po_idx
        while remaining > 0 and i < len(po_list):
            _, po_id, total_cny = po_list[i]
            if total_cny is None:
                i += 1
                continue
            state = po_state[po_id]
            left = total_cny - state["paid_cny"]
            if left <= 0:
                i += 1
                continue
            alloc_amt = min(left, remaining)
            state["paid_cny"] += alloc_amt
            ratio = alloc_amt / amount_cny if amount_cny else 0
            state["paid_usdt"] += amount_usdt * ratio
            remaining -= alloc_amt
            last_po_id = po_id
            if remaining <= 0:
                break
            i += 1

        if last_po_id:
            order_to_po[ex_id] = last_po_id
            po_last_payment[last_po_id] = order_dt

    # Fill missing total_usdt via ex_rates near PO date
    for po_id, total_usdt in po_total_usdt.items():
        if total_usdt is None:
            total_cny = po_state[po_id]["total_cny"]
            rate = _avg_recent_rate(ex_rates, po_dates.get(po_id), window=5)
            if total_cny and rate:
                po_total_usdt[po_id] = total_cny / rate

    return po_state, order_to_po, po_last_payment, po_total_usdt


def build_po_summary_for_order(order: dict, db_path: Path = DB_PATH) -> dict:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    po_plan = _load_po_plan(conn)
    if not po_plan:
        conn.close()
        return {"po_id": "", "note": "No PO plan data found"}

    orders = _load_exchanger_orders(conn)
    ex_rates = []
    for r in orders:
        dt = _parse_dt(r.get("message_date"))
        amt_usdt = r.get("amount_usdt")
        amt_cny = r.get("amount_cny")
        if not dt or amt_usdt is None or amt_cny is None:
            continue
        try:
            rate = float(amt_cny) / float(amt_usdt)
        except Exception:
            continue
        if rate > 0:
            ex_rates.append((dt, rate))
    ex_rates.sort(key=lambda x: x[0])

    alloc_rows = list_po_exchanger_allocations(db_path=db_path)
    alloc_map = {r["exchanger_order_id"]: r["po_id"] for r in alloc_rows if r.get("exchanger_order_id")}

    po_state, order_to_po, po_last_payment, po_total_usdt = _build_po_state(
        orders=orders,
        po_plan=po_plan,
        alloc_map=alloc_map,
        ex_rates=ex_rates,
    )

    ex_id = order.get("exchanger_order_id")
    po_id = alloc_map.get(ex_id) or order_to_po.get(ex_id) or ""

    p2p_orders = _load_p2p_orders(conn)
    p2p_rates = []
    for r in p2p_orders:
        dt = _parse_dt(r.get("create_time"))
        rate = r.get("unit_price")
        if dt and rate is not None:
            try:
                p2p_rates.append((dt, float(rate)))
            except Exception:
                continue
    p2p_rates.sort(key=lambda x: x[0])

    conn.close()

    if not po_id or po_id not in po_state:
        return {"po_id": po_id, "note": "PO not resolved"}

    state = po_state[po_id]
    total_cny = state.get("total_cny")
    total_usdt = po_total_usdt.get(po_id)
    po_date = next((d for d, pid, *_ in po_plan if pid == po_id), None)

    paid_cny = state.get("paid_cny", 0.0)
    paid_usdt = state.get("paid_usdt", 0.0)

    if total_cny is not None:
        left_cny = total_cny - paid_cny
    else:
        left_cny = None

    if total_usdt is not None and total_cny:
        left_usdt = total_usdt * (left_cny / total_cny) if left_cny is not None else None
    else:
        left_usdt = None

    total_kzt = None
    if total_usdt is not None:
        rate_kzt = _avg_recent_rate(p2p_rates, po_date, window=5)
        if rate_kzt:
            total_kzt = total_usdt * rate_kzt

    paid_kzt = _estimate_paid_kzt(paid_usdt, p2p_orders) if paid_usdt else None
    left_kzt = None
    if left_usdt is not None:
        rate_kzt = _avg_recent_rate(p2p_rates, po_date or po_last_payment.get(po_id), window=5)
        if rate_kzt:
            left_kzt = left_usdt * rate_kzt

    fx_usdt_cny = (paid_cny / paid_usdt) if paid_usdt and paid_cny else None
    fx_usdt_kzt = (paid_kzt / paid_usdt) if paid_usdt and paid_kzt else None
    fx_cny_kzt = (paid_kzt / paid_cny) if paid_cny and paid_kzt else None

    return {
        "po_id": po_id,
        "po_date": po_date,
        "total_cny": total_cny,
        "total_usdt": total_usdt,
        "total_kzt": total_kzt,
        "paid_cny": paid_cny,
        "paid_usdt": paid_usdt,
        "paid_kzt": paid_kzt,
        "left_cny": left_cny,
        "left_usdt": left_usdt,
        "left_kzt": left_kzt,
        "fx_usdt_cny": fx_usdt_cny,
        "fx_usdt_kzt": fx_usdt_kzt,
        "fx_cny_kzt": fx_cny_kzt,
    }


def build_pending_po_table(db_path: Path = DB_PATH, limit: int = 20) -> tuple[str, str]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    po_plan = _load_po_plan(conn)
    orders = _load_exchanger_orders(conn)
    ex_rates = []
    for r in orders:
        dt = _parse_dt(r.get("message_date"))
        amt_usdt = r.get("amount_usdt")
        amt_cny = r.get("amount_cny")
        if not dt or amt_usdt is None or amt_cny is None:
            continue
        try:
            rate = float(amt_cny) / float(amt_usdt)
        except Exception:
            continue
        if rate > 0:
            ex_rates.append((dt, rate))
    ex_rates.sort(key=lambda x: x[0])

    alloc_rows = list_po_exchanger_allocations(db_path=db_path)
    alloc_map = {r["exchanger_order_id"]: r["po_id"] for r in alloc_rows if r.get("exchanger_order_id")}

    po_state, _, _, po_total_usdt = _build_po_state(
        orders=orders,
        po_plan=po_plan,
        alloc_map=alloc_map,
        ex_rates=ex_rates,
    )

    p2p_orders = _load_p2p_orders(conn)
    p2p_rates = []
    for r in p2p_orders:
        dt = _parse_dt(r.get("create_time"))
        rate = r.get("unit_price")
        if dt and rate is not None:
            try:
                p2p_rates.append((dt, float(rate)))
            except Exception:
                continue
    p2p_rates.sort(key=lambda x: x[0])

    conn.close()

    rows = []
    for po_date, po_id, total_cny, _ in sorted(po_plan, key=lambda x: (x[0], x[1])):
        if po_id not in po_state:
            continue
        state = po_state[po_id]
        paid_cny = state.get("paid_cny", 0.0)
        paid_usdt = state.get("paid_usdt", 0.0)
        total_usdt = po_total_usdt.get(po_id)
        left_cny = (total_cny - paid_cny) if total_cny is not None else None

        if total_usdt is not None and total_cny:
            left_usdt = total_usdt * (left_cny / total_cny) if left_cny is not None else None
        else:
            left_usdt = None

        rate_kzt = _avg_recent_rate(p2p_rates, po_date, window=5)
        left_kzt = left_usdt * rate_kzt if left_usdt is not None and rate_kzt else None

        if left_cny is None:
            continue
        if left_cny <= 0:
            continue

        rows.append(
            [
                po_id,
                _fmt_dt(po_date),
                _fmt(total_cny),
                _fmt(paid_cny),
                _fmt(left_cny),
                _fmt(total_usdt),
                _fmt(paid_usdt),
                _fmt(left_usdt),
                _fmt(left_kzt),
            ]
        )

    cols = [
        ("PO", 12),
        ("PO_Date", 19),
        ("Total_CNY", 12),
        ("Paid_CNY", 12),
        ("Left_CNY", 12),
        ("Total_USDT", 12),
        ("Paid_USDT", 12),
        ("Left_USDT", 12),
        ("Left_KZT", 12),
    ]

    rows = sorted(rows, key=lambda r: r[1])
    total = len(rows)
    if limit and len(rows) > limit:
        rows = rows[:limit]
    table = "\n".join(_ascii_table(rows, cols))
    return table, f"{total} open PO(s)" + (f" (showing {len(rows)})" if limit and total > limit else "")


def build_exchanger_update_message(order: dict, db_path: Path = DB_PATH) -> str:
    summary = build_po_summary_for_order(order, db_path=db_path)

    amount_usdt = order.get("amount_usdt")
    amount_cny = order.get("amount_cny")
    rate = None
    if amount_usdt and amount_cny:
        try:
            rate = float(amount_cny) / float(amount_usdt)
        except Exception:
            rate = None

    header = [
        "<b>Exchanger update</b>",
        f"<b>Order:</b> {order.get('exchanger')} #{order.get('order_id')}",
        f"<b>Status:</b> {(order.get('status') or '').upper()}",
        f"<b>Date:</b> {_fmt_dt(order.get('message_date'))}",
    ]
    if amount_usdt and amount_cny:
        header.append(f"<b>USDT → CNY:</b> {_fmt(amount_usdt)} → {_fmt(amount_cny)} (rate {_fmt(rate, 4)})")
    addr = order.get("deposit_address")
    if addr:
        header.append(f"<b>Deposit:</b> <code>{addr}</code>")

    if summary.get("po_id"):
        header.append(f"<b>PO:</b> {summary.get('po_id')}")
        header.append(f"<b>PO Date:</b> {_fmt_dt(summary.get('po_date'))}")
        header.append(
            "<b>Total:</b> "
            f"CNY {_fmt(summary.get('total_cny'))} | "
            f"USDT {_fmt(summary.get('total_usdt'))} | "
            f"KZT≈{_fmt(summary.get('total_kzt'))}"
        )
        header.append(
            "<b>Paid:</b> "
            f"CNY {_fmt(summary.get('paid_cny'))} | "
            f"USDT {_fmt(summary.get('paid_usdt'))} | "
            f"KZT≈{_fmt(summary.get('paid_kzt'))}"
        )
        header.append(
            "<b>FX (paid part):</b> "
            f"USDT/CNY {_fmt(summary.get('fx_usdt_cny'), 4)} | "
            f"USDT/KZT {_fmt(summary.get('fx_usdt_kzt'), 4)} | "
            f"CNY/KZT {_fmt(summary.get('fx_cny_kzt'), 4)}"
        )

        rows = [
            [
                summary.get("po_id"),
                _fmt_dt(summary.get("po_date")),
                _fmt(summary.get("total_cny")),
                _fmt(summary.get("paid_cny")),
                _fmt(summary.get("left_cny")),
                _fmt(summary.get("paid_usdt")),
                _fmt(summary.get("paid_kzt")),
                _fmt(summary.get("fx_usdt_cny"), 4),
                _fmt(summary.get("fx_usdt_kzt"), 4),
                _fmt(summary.get("fx_cny_kzt"), 4),
            ]
        ]
        cols = [
            ("PO", 12),
            ("PO_Date", 19),
            ("Total_CNY", 12),
            ("Paid_CNY", 12),
            ("Left_CNY", 12),
            ("Paid_USDT", 12),
            ("Paid_KZT", 12),
            ("USDT/CNY", 10),
            ("USDT/KZT", 10),
            ("CNY/KZT", 10),
        ]
        table = "\n".join(_ascii_table(rows, cols))
        header.append("<pre>" + table + "</pre>")
    else:
        header.append("<i>PO not resolved for this order.</i>")

    return "\n".join(header)


def send_exchanger_update_alert(order: dict, db_path: Path = DB_PATH) -> bool:
    _load_env_file(PROJECT_ROOT / ".env")
    try:
        config = get_telegram_config()
    except Exception:
        return False

    message = build_exchanger_update_message(order, db_path=db_path)
    result = send_message(config["chat_id"], message, config["token"])
    return bool(result.get("success"))
