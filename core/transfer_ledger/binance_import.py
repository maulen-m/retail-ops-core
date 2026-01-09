"""Import Binance C2C/P2P orders into DB and ledger."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .repository import upsert_binance_c2c_order
from .service import post_binance_p2p_trade


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _to_iso(ms_or_str) -> str:
    if ms_or_str is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(ms_or_str, (int, float)):
        return datetime.fromtimestamp(ms_or_str / 1000, tz=timezone.utc).isoformat()
    # try to parse numeric string
    try:
        return datetime.fromtimestamp(float(ms_or_str) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return str(ms_or_str)


def normalize_binance_order(raw: dict) -> dict:
    order_number = raw.get("orderNumber") or raw.get("orderNo") or raw.get("orderId")
    if not order_number:
        raise ValueError("Missing orderNumber in Binance payload")

    trade_type = (raw.get("tradeType") or raw.get("tradeTypeName") or "").upper()
    asset = (raw.get("asset") or "").upper()
    fiat = (raw.get("fiat") or "").upper()

    crypto_amount = _to_float(raw.get("amount"))
    fiat_amount = _to_float(raw.get("totalPrice") or raw.get("fiatAmount"))
    unit_price = _to_float(raw.get("unitPrice") or raw.get("price"))

    if crypto_amount is None or fiat_amount is None or unit_price is None:
        raise ValueError(f"Invalid numeric fields in order {order_number}")

    return {
        "order_number": str(order_number),
        "adv_no": raw.get("advNo"),
        "trade_type": trade_type,
        "asset": asset,
        "fiat": fiat,
        "fiat_amount": fiat_amount,
        "crypto_amount": crypto_amount,
        "unit_price": unit_price,
        "order_status": raw.get("orderStatus") or raw.get("status"),
        "create_time": _to_iso(raw.get("createTime")),
        "commission": raw.get("commission"),
        "counterparty": raw.get("counterPartNickName") or raw.get("counterparty"),
        "advertisement_role": raw.get("advertisementRole"),
        "raw_json": json.dumps(raw, ensure_ascii=False),
        "source": "BINANCE_P2P",
    }


def import_binance_orders(
    raw_orders: list[dict],
    db_path=None,
    write_ledger: bool = True,
    completed_only: bool = True,
) -> dict:
    inserted = 0
    ledger_entries = 0
    errors: list[str] = []

    for raw in raw_orders:
        try:
            order = normalize_binance_order(raw)
            is_new = upsert_binance_c2c_order(order, db_path=db_path)
            if is_new:
                inserted += 1

            if write_ledger:
                if completed_only and str(order.get("order_status", "")).upper() != "COMPLETED":
                    continue
                entry_ids = post_binance_p2p_trade(
                    order_number=order["order_number"],
                    trade_type=order["trade_type"],
                    asset=order["asset"],
                    fiat=order["fiat"],
                    crypto_amount=order["crypto_amount"],
                    fiat_amount=order["fiat_amount"],
                    unit_price=order["unit_price"],
                    paid_at=order["create_time"],
                    source=order.get("source", "BINANCE_P2P"),
                    counterparty=order.get("counterparty") or "",
                    db_path=db_path,
                )
                ledger_entries += len(entry_ids)
        except Exception as exc:
            errors.append(str(exc))

    return {
        "inserted": inserted,
        "ledger_entries": ledger_entries,
        "errors": errors,
    }
