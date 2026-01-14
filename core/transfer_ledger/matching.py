"""Centralized matching + tolerance logic for transfer ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .money import quantize_usdt, to_decimal

# Tolerances (centralized)
USDT_AMOUNT_TOLERANCE = Decimal("2.0")
DATE_WINDOW_DAYS = 3
ADDRESS_PREFIX_LEN = 6
ADDRESS_SUFFIX_LEN = 6
UNMATCHED_AGE_DAYS = 3


def parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _partial_tokens(addr: str) -> Optional[tuple[str, str]]:
    text = addr.strip()
    if not text:
        return None
    for token in ("...", "…"):
        if token in text:
            pre, post = text.split(token, 1)
            return pre.strip(), post.strip()
    if len(text) <= ADDRESS_PREFIX_LEN + ADDRESS_SUFFIX_LEN:
        return text[:ADDRESS_PREFIX_LEN], text[-ADDRESS_SUFFIX_LEN:]
    return None


def address_match(order_addr: str, withdrawal_addr: str) -> bool:
    if not order_addr or not withdrawal_addr:
        return False
    if order_addr == withdrawal_addr:
        return True
    tokens = _partial_tokens(order_addr)
    if tokens:
        pre, post = tokens
        return withdrawal_addr.startswith(pre) and withdrawal_addr.endswith(post)
    tokens = _partial_tokens(withdrawal_addr)
    if tokens:
        pre, post = tokens
        return order_addr.startswith(pre) and order_addr.endswith(post)
    return False


def amount_close(a: object, b: object, tolerance: Decimal = USDT_AMOUNT_TOLERANCE) -> bool:
    dec_a = quantize_usdt(a)
    dec_b = quantize_usdt(b)
    if dec_a is None or dec_b is None:
        return False
    return abs(dec_a - dec_b) <= tolerance


def date_close(a: Optional[datetime], b: Optional[datetime], days: int = DATE_WINDOW_DAYS) -> bool:
    if not a or not b:
        return True
    return abs((a - b).total_seconds()) <= days * 86400


def effective_usdt(amount_usdt: object, fee_usdt: object) -> Decimal:
    base = to_decimal(amount_usdt) or Decimal("0")
    fee = to_decimal(fee_usdt) or Decimal("0")
    return base + fee


@dataclass
class MatchResult:
    match: Optional[dict]
    reason: str


def match_withdrawal_for_order(
    order: dict,
    withdrawals: list[dict],
    used_ids: Optional[set[str]] = None,
) -> MatchResult:
    address = (order.get("deposit_address") or "").strip()
    amount = order.get("amount_usdt")
    order_dt = parse_dt(order.get("message_date"))
    used = used_ids or set()

    best = None
    best_delta = None
    for wd in withdrawals:
        wd_id = wd.get("withdraw_id")
        if not wd_id or wd_id in used:
            continue
        if address and not address_match(address, wd.get("address") or ""):
            continue
        if amount is not None and not amount_close(amount, wd.get("amount")):
            continue
        wd_dt = parse_dt(wd.get("apply_time"))
        if not date_close(order_dt, wd_dt):
            continue
        if order_dt and wd_dt:
            delta = abs((wd_dt - order_dt).total_seconds())
        else:
            delta = 0
        if best is None or (best_delta is not None and delta < best_delta):
            best = wd
            best_delta = delta

    return MatchResult(best, "matched" if best else "no_match")


def match_order_for_withdrawal(
    withdrawal: dict,
    orders: list[dict],
) -> MatchResult:
    address = withdrawal.get("address") or ""
    amount = withdrawal.get("amount")
    apply_time = parse_dt(withdrawal.get("apply_time"))

    best = None
    best_delta = None
    for order in orders:
        if address and not address_match(address, order.get("deposit_address") or ""):
            continue
        if not amount_close(amount, order.get("amount_usdt")):
            continue
        order_dt = parse_dt(order.get("message_date"))
        if not date_close(apply_time, order_dt):
            continue
        if apply_time and order_dt:
            delta = abs((apply_time - order_dt).total_seconds())
        else:
            delta = 0
        if best is None or (best_delta is not None and delta < best_delta):
            best = order
            best_delta = delta

    return MatchResult(best, "matched" if best else "no_match")
