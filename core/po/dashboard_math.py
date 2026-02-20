"""PO dashboard math helpers (shared, deterministic)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def round_half_up_1dp(value: float) -> float:
    """Round to one decimal using half-up semantics."""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compute_doc_values(pre_arrival: float, order_qty: float, demand: float) -> tuple[float, float]:
    """
    Return (pre_arr_doc, post_arr_doc) with dashboard rounding policy.

    For non-positive demand, preserve legacy sentinel semantics.
    """
    if demand > 0:
        pre_doc = pre_arrival / demand
        post_doc = (pre_arrival + order_qty) / demand
        return (round_half_up_1dp(pre_doc), round_half_up_1dp(post_doc))

    pre_doc = 999.0 if pre_arrival > 0 else 0.0
    post_doc = 999.0 if (pre_arrival + order_qty) > 0 else 0.0
    return (pre_doc, post_doc)
