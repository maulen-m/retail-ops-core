"""Match exchanger orders to Binance withdrawals (compat wrapper)."""

from __future__ import annotations

from typing import Optional

from . import repository
from .matching import (
    DATE_WINDOW_DAYS,
    USDT_AMOUNT_TOLERANCE as AMOUNT_TOLERANCE,
    address_match,
    amount_close,
    date_close,
    match_order_for_withdrawal,
    parse_dt,
)


def match_exchanger_order_for_withdrawal(
    withdrawal: dict,
    db_path=None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (exchanger_label, exchanger_order_id) for a withdrawal if matched."""
    candidates = repository.list_exchanger_orders(db_path=db_path, limit=200)
    result = match_order_for_withdrawal(withdrawal, candidates)
    if not result.match:
        return None, None
    return result.match.get("exchanger"), result.match.get("exchanger_order_id")


def label_withdrawals_for_order(order: dict, db_path=None) -> int:
    """Apply exchanger label/order_id to matching withdrawals (unlabeled only)."""
    address = order.get("deposit_address") or ""
    order_amount = order.get("amount_usdt")
    order_date = parse_dt(order.get("message_date"))

    withdrawals = repository.list_withdrawals(db_path=db_path, only_unlabeled=True)
    if address:
        withdrawals = [w for w in withdrawals if address_match(address, w.get("address") or "")]

    labeled = 0
    for wd in withdrawals:
        if order_amount is not None and not amount_close(wd.get("amount"), order_amount):
            continue
        wd_date = parse_dt(wd.get("apply_time"))
        if not date_close(wd_date, order_date):
            continue
        repository.update_withdrawal_label(
            wd["withdraw_id"],
            counterparty_label=order.get("exchanger") or "",
            exchanger_order_id=order.get("exchanger_order_id"),
            db_path=db_path,
        )
        repository.update_withdrawal_entry_notes(
            wd["withdraw_id"],
            counterparty_label=order.get("exchanger") or "",
            exchanger_order_id=order.get("exchanger_order_id"),
            db_path=db_path,
        )
        labeled += 1

    return labeled
