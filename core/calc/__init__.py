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
)

__all__ = [
    "calc_delivery_fee",
    "calc_cogs",
    "calc_net_rev",
    "calc_profit",
]
