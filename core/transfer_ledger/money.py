"""Decimal helpers for currency math (USDT/CNY/KZT)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

USDT_QUANT = Decimal("0.01")
CNY_QUANT = Decimal("0.01")
KZT_QUANT = Decimal("1")


def to_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _quantize(value: Decimal, quant: Decimal) -> Decimal:
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def quantize_usdt(value: object) -> Optional[Decimal]:
    dec = to_decimal(value)
    if dec is None:
        return None
    return _quantize(dec, USDT_QUANT)


def quantize_cny(value: object) -> Optional[Decimal]:
    dec = to_decimal(value)
    if dec is None:
        return None
    return _quantize(dec, CNY_QUANT)


def quantize_kzt(value: object) -> Optional[Decimal]:
    dec = to_decimal(value)
    if dec is None:
        return None
    return _quantize(dec, KZT_QUANT)
