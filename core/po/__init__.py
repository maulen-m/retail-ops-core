"""
Phase 10: Purchase Order (PO) management modules.

Provides:
- lifecycle: PO lifecycle management (create, update, receive, close)
- eta: ETA calculation for PO arrivals
- recommender: ONE PO engine - canonical order quantity calculations
"""

from .lifecycle import (
    create_po,
    add_po_line,
    update_po_field,
    update_po_status,
    confirm_po_arrival,
    close_po,
    get_po,
    get_po_lines,
    PO_STATUS_FLOW,
)

from .recommender import (
    # Main calculation function
    calc_order_qty,
    OrderQtyResult,
    # Component calculations
    calc_safety_stock,
    calc_t_post,
    calc_pre_arrival,
    calc_rop,
    should_reorder,
    # ROIC
    calc_sku_roic,
    check_roic_gate,
    # Enums
    OrderStatus,
    ROICAction,
)

__all__ = [
    # Lifecycle
    "create_po",
    "add_po_line",
    "update_po_field",
    "update_po_status",
    "confirm_po_arrival",
    "close_po",
    "get_po",
    "get_po_lines",
    "PO_STATUS_FLOW",
    # Recommender
    "calc_order_qty",
    "OrderQtyResult",
    "calc_safety_stock",
    "calc_t_post",
    "calc_pre_arrival",
    "calc_rop",
    "should_reorder",
    "calc_sku_roic",
    "check_roic_gate",
    "OrderStatus",
    "ROICAction",
]
