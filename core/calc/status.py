"""
Status calculation for Project 3 (Phase 3 - Calc Engine).

3-state reorder logic matching Excel V15:
- REORDER: Total stock < ROP (need to place order now)
- WAIT: Current stock < ROP but Total stock >= ROP (order in transit covers)
- OK: Current stock >= ROP (no action needed)

CRITICAL: Always check Total stock FIRST, then Current stock.
The order matters for correct status assignment.

Logic:
    if total_stock < rop:
        return "REORDER"
    elif current_stock < rop:
        return "WAIT"
    else:
        return "OK"
"""

from typing import Literal

StatusType = Literal["REORDER", "WAIT", "OK"]


def calc_status(
    current_stock: int,
    total_stock: int,
    rop: float,
) -> StatusType:
    """
    Calculate reorder status based on stock levels and ROP.

    Logic (IMPORTANT - check order matters!):
    1. If total_stock < ROP → REORDER (must order immediately)
    2. Elif current_stock < ROP → WAIT (inbound covers shortfall)
    3. Else → OK (sufficient stock)

    Args:
        current_stock: On-hand inventory units
        total_stock: current_stock + inbound_stock (total available/expected)
        rop: Reorder point (D30 × L + SS_total)

    Returns:
        "REORDER", "WAIT", or "OK"

    Examples:
        >>> calc_status(50, 50, 100)  # current=50, total=50, rop=100
        'REORDER'  # Total < ROP

        >>> calc_status(50, 150, 100)  # current=50, total=150, rop=100
        'WAIT'  # Total >= ROP but Current < ROP

        >>> calc_status(150, 200, 100)  # current=150, total=200, rop=100
        'OK'  # Current >= ROP
    """
    # CRITICAL: Check total_stock FIRST
    if total_stock < rop:
        return "REORDER"
    elif current_stock < rop:
        return "WAIT"
    else:
        return "OK"


def calc_status_from_inventory(
    current_stock: int,
    inbound_stock: int,
    rop: float,
) -> StatusType:
    """
    Convenience function that calculates total_stock internally.

    Args:
        current_stock: On-hand inventory units
        inbound_stock: Units in transit (from POs)
        rop: Reorder point

    Returns:
        "REORDER", "WAIT", or "OK"
    """
    total_stock = current_stock + inbound_stock
    return calc_status(current_stock, total_stock, rop)


def get_status_priority(status: StatusType) -> int:
    """
    Get numeric priority for status (for sorting/alerting).

    Priority:
        REORDER = 1 (highest priority, needs action)
        WAIT = 2
        OK = 3 (lowest priority)

    Args:
        status: Status string

    Returns:
        Priority number (1 = most urgent)
    """
    priorities = {
        "REORDER": 1,
        "WAIT": 2,
        "OK": 3,
    }
    return priorities.get(status, 99)


def is_action_required(status: StatusType) -> bool:
    """
    Check if status requires immediate action.

    Args:
        status: Status string

    Returns:
        True if REORDER, False otherwise
    """
    return status == "REORDER"


if __name__ == "__main__":
    # Test the status logic
    print("Status Calculation Tests")
    print("=" * 50)

    test_cases = [
        # (current, total, rop, expected_status)
        (50, 50, 100, "REORDER"),     # Both below ROP
        (50, 150, 100, "WAIT"),       # Total OK, Current below
        (150, 200, 100, "OK"),        # Both above ROP
        (100, 100, 100, "OK"),        # Exactly at ROP
        (99, 100, 100, "WAIT"),       # Current just below, Total at ROP
        (99, 99, 100, "REORDER"),     # Total just below ROP
        (0, 0, 100, "REORDER"),       # Zero stock
        (0, 150, 100, "WAIT"),        # Zero current but inbound covers
    ]

    print("\n  Current  Total   ROP  → Status")
    print("-" * 50)

    all_pass = True
    for current, total, rop, expected in test_cases:
        actual = calc_status(current, total, rop)
        status = "✓" if actual == expected else "✗ FAIL"
        print(f"  {current:7d}  {total:5d}  {rop:4.0f}  → {actual:8s} {status}")
        if actual != expected:
            print(f"           Expected: {expected}")
            all_pass = False

    print("-" * 50)
    print(f"{'All tests passed!' if all_pass else 'Some tests failed!'}")
