"""Orders -> cashflow translation helpers.

Canonical entrypoint for D1 cash-in + on-delivery inventory moves.
"""
from __future__ import annotations

from scripts.translate_orders_to_cashflow_events import translate_orders  # noqa: F401

__all__ = ["translate_orders"]
