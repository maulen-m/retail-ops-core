"""Match exchanger orders to Binance withdrawals."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import repository
from .matching import address_match, amount_close, date_close, match_order_for_withdrawal, parse_dt


def _is_cancelled(order: dict) -> bool:
    return "CANCEL" in str(order.get("status") or "").upper()


def _is_real_order(order: dict) -> bool:
    order_id = str(order.get("order_id") or "")
    if order_id.isdigit():
        return True
    # Legacy fallback rows used Message-ID as order_id; keep only records that have enough identity.
    return bool(order.get("deposit_address")) and order.get("amount_usdt") is not None


def _eligible_orders(db_path=None) -> list[dict]:
    orders = repository.list_exchanger_orders(db_path=db_path, limit=500)
    return [o for o in orders if _is_real_order(o) and not _is_cancelled(o)]


def _match_score(order: dict, withdrawal: dict) -> float:
    order_dt = parse_dt(order.get("message_date"))
    wd_dt = parse_dt(withdrawal.get("apply_time") or withdrawal.get("success_time"))
    dt_delta = abs((wd_dt - order_dt).total_seconds()) if (order_dt and wd_dt) else 0.0
    amount_delta = 0.0
    if order.get("amount_usdt") is not None and withdrawal.get("amount") is not None:
        amount_delta = abs(float(withdrawal["amount"]) - float(order["amount_usdt"]))
    return amount_delta * 1000.0 + dt_delta


def _valid_link(order: dict, withdrawal: dict) -> bool:
    if _is_cancelled(order):
        return False
    order_addr = (order.get("deposit_address") or "").strip()
    wd_addr = (withdrawal.get("address") or "").strip()
    # Auto-linking without an address is too ambiguous.
    if not order_addr or not wd_addr:
        return False
    if not address_match(order_addr, wd_addr):
        return False
    if order.get("amount_usdt") is not None and withdrawal.get("amount") is not None:
        if not amount_close(withdrawal.get("amount"), order.get("amount_usdt")):
            return False
    if not date_close(
        parse_dt(order.get("message_date")),
        parse_dt(withdrawal.get("apply_time") or withdrawal.get("success_time")),
    ):
        return False
    return True


def match_exchanger_order_for_withdrawal(
    withdrawal: dict,
    db_path=None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (exchanger_label, exchanger_order_id) for a withdrawal if matched."""
    if not (withdrawal.get("address") or "").strip():
        return None, None
    candidates = _eligible_orders(db_path=db_path)
    result = match_order_for_withdrawal(withdrawal, candidates)
    if not result.match:
        return None, None
    return result.match.get("exchanger"), result.match.get("exchanger_order_id")


def label_withdrawals_for_order(order: dict, db_path=None) -> int:
    """Apply exchanger label/order_id to one best matching unlabeled withdrawal."""
    if _is_cancelled(order):
        return 0
    order_addr = (order.get("deposit_address") or "").strip()
    if not order_addr:
        return 0

    order_amount = order.get("amount_usdt")
    order_date = parse_dt(order.get("message_date"))
    best = None
    best_score = None

    withdrawals = repository.list_withdrawals(db_path=db_path, only_unlabeled=True)
    for wd in withdrawals:
        wd_addr = (wd.get("address") or "").strip()
        if not wd_addr or not address_match(order_addr, wd_addr):
            continue
        if order_amount is not None and not amount_close(wd.get("amount"), order_amount):
            continue
        wd_date = parse_dt(wd.get("apply_time") or wd.get("success_time"))
        if not date_close(wd_date, order_date):
            continue
        score = _match_score(order, wd)
        if best is None or (best_score is not None and score < best_score):
            best = wd
            best_score = score

    if not best:
        return 0

    repository.update_withdrawal_label(
        best["withdraw_id"],
        counterparty_label=order.get("exchanger") or "",
        exchanger_order_id=order.get("exchanger_order_id"),
        db_path=db_path,
    )
    repository.update_withdrawal_entry_notes(
        best["withdraw_id"],
        counterparty_label=order.get("exchanger") or "",
        exchanger_order_id=order.get("exchanger_order_id"),
        db_path=db_path,
    )
    return 1


def repair_withdrawal_labels(db_path=None) -> dict:
    """Clear invalid/duplicate labels so strict validation stays clean."""
    orders = _eligible_orders(db_path=db_path)
    order_map = {o.get("exchanger_order_id"): o for o in orders if o.get("exchanger_order_id")}
    withdrawals = repository.list_withdrawals(db_path=db_path, only_unlabeled=False)
    cleared = 0

    def _clear(wd: dict) -> None:
        nonlocal cleared
        repository.update_withdrawal_label(
            wd["withdraw_id"],
            counterparty_label="",
            exchanger_order_id="",
            db_path=db_path,
        )
        cleared += 1

    # Pass 1: clear links that no longer satisfy matching invariants.
    for wd in withdrawals:
        ex_id = wd.get("exchanger_order_id")
        if not ex_id:
            continue
        order = order_map.get(ex_id)
        if not order or not _valid_link(order, wd):
            _clear(wd)

    # Pass 2: enforce one-withdrawal-per-order by keeping only the best link.
    withdrawals = repository.list_withdrawals(db_path=db_path, only_unlabeled=False)
    by_order: dict[str, list[dict]] = {}
    for wd in withdrawals:
        ex_id = wd.get("exchanger_order_id")
        if ex_id:
            by_order.setdefault(ex_id, []).append(wd)

    for ex_id, rows in by_order.items():
        if len(rows) <= 1:
            continue
        order = order_map.get(ex_id)
        if not order:
            for wd in rows:
                _clear(wd)
            continue
        ranked = sorted(rows, key=lambda wd: _match_score(order, wd))
        for wd in ranked[1:]:
            _clear(wd)

    return {"cleared": cleared}
