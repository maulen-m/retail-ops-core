"""Match exchanger orders to Binance withdrawals."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from . import repository

AMOUNT_TOLERANCE = 0.2
DATE_WINDOW_DAYS = 3


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _amount_close(a: Optional[float], b: Optional[float], tol: float = AMOUNT_TOLERANCE) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def _date_close(a: Optional[datetime], b: Optional[datetime], days: int = DATE_WINDOW_DAYS) -> bool:
    if not a or not b:
        return True
    return abs((a - b).total_seconds()) <= days * 86400


def match_exchanger_order_for_withdrawal(
    withdrawal: dict,
    db_path=None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (exchanger_label, exchanger_order_id) for a withdrawal if matched."""
    address = withdrawal.get("address") or ""
    amount = withdrawal.get("amount")
    apply_time = _parse_dt(withdrawal.get("apply_time"))

    candidates: list[dict] = []
    if address:
        candidates = repository.find_exchanger_orders_by_address(address, db_path=db_path)

    if not candidates:
        candidates = repository.list_exchanger_orders(db_path=db_path, limit=200)

    for order in candidates:
        order_amount = order.get("amount_usdt")
        order_date = _parse_dt(order.get("message_date"))
        if order_amount is not None and not _amount_close(amount, order_amount):
            continue
        if not _date_close(apply_time, order_date):
            continue
        return order.get("exchanger"), order.get("exchanger_order_id")

    return None, None


def label_withdrawals_for_order(order: dict, db_path=None) -> int:
    """Apply exchanger label/order_id to matching withdrawals (unlabeled only)."""
    address = order.get("deposit_address") or ""
    order_amount = order.get("amount_usdt")
    order_date = _parse_dt(order.get("message_date"))

    withdrawals = repository.list_withdrawals(db_path=db_path, only_unlabeled=True)
    if address:
        withdrawals = [w for w in withdrawals if (w.get("address") or "") == address]

    labeled = 0
    for wd in withdrawals:
        if order_amount is not None and not _amount_close(wd.get("amount"), order_amount):
            continue
        wd_date = _parse_dt(wd.get("apply_time"))
        if not _date_close(wd_date, order_date):
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
