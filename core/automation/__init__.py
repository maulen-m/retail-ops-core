"""Automation module for PO generation and order management."""

from core.automation.po_generator import (
    calc_order_quantity,
    apply_size_splits,
    generate_po_draft,
    generate_po_draft_with_validation,
    calc_confidence_score,
)
from core.automation.order_status_manager import (
    OrderStatusManager,
    OperationResult,
    BulkOperationResult,
    get_manager,
    CANCEL_REASONS,
)

__all__ = [
    # PO Generator
    'calc_order_quantity',
    'apply_size_splits',
    'generate_po_draft',
    'generate_po_draft_with_validation',
    'calc_confidence_score',
    # Order Status Manager
    'OrderStatusManager',
    'OperationResult',
    'BulkOperationResult',
    'get_manager',
    'CANCEL_REASONS',
]
