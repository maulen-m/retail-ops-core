"""
Calculation modules for Project 3.

This package contains pure functions for:
- economics: Unit economics (COGS, NetRev, Profit, delivery fees)
- inventory: D30, sigma, SS, ROP, ROIC calculations
- status: Reorder status logic (REORDER/WAIT/OK)
"""

from .economics import (
    calc_delivery_fee,
    calc_cogs,
    calc_net_rev,
    calc_profit,
    calc_line_values,
)

from .inventory import (
    calc_d30,
    calc_sigma,
    calc_ss_total,
    calc_rop,
    calc_roic,
    calc_k_avg,
    calc_suggested_order_qty,
    calc_all_metrics,
    DEFAULT_PARAMS,
)

from .status import (
    calc_status,
    calc_status_from_inventory,
    get_status_priority,
    is_action_required,
)

__all__ = [
    # Economics
    "calc_delivery_fee",
    "calc_cogs",
    "calc_net_rev",
    "calc_profit",
    "calc_line_values",
    # Inventory
    "calc_d30",
    "calc_sigma",
    "calc_ss_total",
    "calc_rop",
    "calc_roic",
    "calc_k_avg",
    "calc_suggested_order_qty",
    "calc_all_metrics",
    "DEFAULT_PARAMS",
    # Status
    "calc_status",
    "calc_status_from_inventory",
    "get_status_priority",
    "is_action_required",
]
