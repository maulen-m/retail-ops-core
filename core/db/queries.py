"""
TASK-165: Size-level data queries for Phase 9.6
TASK-189: Phase 10 integration (stock_ledger, sales_fact_v2)

Provides functions to retrieve size-level sales and inventory data
needed by the size-aware PO allocation engine.

Tables used (legacy):
- fact_sales_daily_size: Daily sales by size
- fact_inventory_snapshot_size: Daily stock levels by size
- fact_po_lines: Legacy PO lines

Tables used (Phase 10 - v2 functions):
- stock_ledger: Event-sourced stock changes
- sales_fact_v2: Deduplicated sales records
- po_header: PO header records
- po_line: PO line items
- dim_sku_size: Size definitions for a SKU
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Import from package
from . import get_db, DEFAULT_DB_PATH


def get_size_sales_history(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    days: int = 90,
    db_path: Optional[Path] = None
) -> dict[str, list[int]]:
    """
    Get daily sales history by size for a SKU.

    TASK-165: Returns {size: [daily_units]} for the last N days.
    List is chronological (oldest first).

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        days: Number of days of history (default: 90)
        db_path: Optional database path

    Returns:
        Dict mapping size -> list of daily sales units
        Example: {"S": [1, 2, 0, 3, ...], "M": [3, 4, 2, 5, ...], ...}

    Note:
        - Missing days are filled with 0
        - Sizes come from dim_sku_size to ensure all sizes are present
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get sales data
        sales_data = conn.execute("""
            SELECT sale_date, my_size, units
            FROM fact_sales_daily_size
            WHERE sku_key = ?
              AND store_code = ?
              AND sale_date >= ?
              AND sale_date <= ?
            ORDER BY sale_date
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        # Build date -> size -> units mapping
        sales_by_date: dict[str, dict[str, int]] = {}
        for row in sales_data:
            d = row["sale_date"]
            if d not in sales_by_date:
                sales_by_date[d] = {}
            sales_by_date[d][row["my_size"]] = row["units"]

        # Generate complete date list
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current.isoformat())
            current += timedelta(days=1)

        # Build result with all sizes and all dates (fill missing with 0)
        result: dict[str, list[int]] = {}
        for size in sizes:
            result[size] = []
            for d in date_list:
                units = sales_by_date.get(d, {}).get(size, 0)
                result[size].append(units)

        return result


def get_size_stock_history(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    days: int = 90,
    db_path: Optional[Path] = None
) -> dict[str, list[int]]:
    """
    Get daily stock history by size for a SKU.

    TASK-165: Returns {size: [daily_stock]} for the last N days.
    List is chronological (oldest first).

    This is used for OOS-filtered demand calculation - days where
    both sales=0 AND stock=0 are considered true stockouts.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        days: Number of days of history (default: 90)
        db_path: Optional database path

    Returns:
        Dict mapping size -> list of daily stock levels
        Example: {"S": [10, 8, 5, 12, ...], "M": [20, 18, 15, 22, ...], ...}

    Note:
        - Missing days are filled with 0 (assumed OOS)
        - Sizes come from dim_sku_size to ensure all sizes are present
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get stock data
        stock_data = conn.execute("""
            SELECT snapshot_date, my_size, current_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
              AND snapshot_date >= ?
              AND snapshot_date <= ?
            ORDER BY snapshot_date
        """, (sku_key, start_date.isoformat(), end_date.isoformat())).fetchall()

        # Build date -> size -> stock mapping
        stock_by_date: dict[str, dict[str, int]] = {}
        for row in stock_data:
            d = row["snapshot_date"]
            if d not in stock_by_date:
                stock_by_date[d] = {}
            stock_by_date[d][row["my_size"]] = row["current_stock"]

        # Generate complete date list
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current.isoformat())
            current += timedelta(days=1)

        # Build result with all sizes and all dates (fill missing with 0)
        result: dict[str, list[int]] = {}
        for size in sizes:
            result[size] = []
            for d in date_list:
                stock = stock_by_date.get(d, {}).get(size, 0)
                result[size].append(stock)

        return result


def get_size_current_stock(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get current on-hand stock by size for a SKU.

    TASK-165: Returns {size: current_units} from the latest snapshot.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping size -> current stock units
        Example: {"S": 20, "M": 35, "L": 45, "XL": 25, ...}

    Note:
        - Returns 0 for sizes with no snapshot data
        - Uses the most recent snapshot date
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Get latest snapshot date
        latest = conn.execute("""
            SELECT MAX(snapshot_date) as max_date
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
        """, (sku_key,)).fetchone()

        if not latest or not latest["max_date"]:
            # No snapshot data, return all zeros
            return {size: 0 for size in sizes}

        # Get current stock from latest snapshot
        stock_data = conn.execute("""
            SELECT my_size, current_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
              AND snapshot_date = ?
        """, (sku_key, latest["max_date"])).fetchall()

        # Build result
        result = {size: 0 for size in sizes}
        for row in stock_data:
            if row["my_size"] in result:
                result[row["my_size"]] = row["current_stock"]

        return result


def get_size_inbound(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get inbound (in-transit) stock by size for a SKU.

    TASK-165: Returns {size: inbound_units} from latest snapshot or PO lines.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping size -> inbound stock units
        Example: {"S": 0, "M": 50, "L": 0, "XL": 30, ...}

    Note:
        - Returns 0 for sizes with no inbound
        - Aggregates from fact_po_lines where status IN ('IN_TRANSIT', 'PAID')
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # First try: Get from latest inventory snapshot (inbound_stock column)
        latest = conn.execute("""
            SELECT MAX(snapshot_date) as max_date
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
        """, (sku_key,)).fetchone()

        result = {size: 0 for size in sizes}

        if latest and latest["max_date"]:
            inbound_data = conn.execute("""
                SELECT my_size, inbound_stock
                FROM fact_inventory_snapshot_size
                WHERE sku_key = ?
                  AND snapshot_date = ?
            """, (sku_key, latest["max_date"])).fetchall()

            for row in inbound_data:
                if row["my_size"] in result:
                    result[row["my_size"]] = row["inbound_stock"] or 0

        # Also add from PO lines if no snapshot data
        po_data = conn.execute("""
            SELECT my_size, SUM(order_quantity - COALESCE(received_qty, 0)) as pending
            FROM fact_po_lines
            WHERE sku_key = ?
              AND store_code = ?
              AND status IN ('IN_TRANSIT', 'PAID', 'UNPAID')
              AND order_quantity > COALESCE(received_qty, 0)
            GROUP BY my_size
        """, (sku_key, store_code)).fetchall()

        for row in po_data:
            if row["my_size"] in result:
                # Add PO inbound to snapshot inbound (avoid double counting)
                if result[row["my_size"]] == 0:
                    result[row["my_size"]] = int(row["pending"] or 0)

        return result


def get_size_sales_90d(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get total 90-day sales by size for a SKU.

    Helper function for generate_po_draft().

    Args:
        sku_key: Style-level SKU key
        store_code: Store code
        db_path: Optional database path

    Returns:
        Dict mapping size -> total units sold in last 90 days
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        # Get aggregated sales
        sales_data = conn.execute("""
            SELECT my_size, SUM(units) as total_units
            FROM fact_sales_daily_size
            WHERE sku_key = ?
              AND store_code = ?
              AND sale_date >= ?
              AND sale_date <= ?
            GROUP BY my_size
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        # Build result
        result = {size: 0 for size in sizes}
        for row in sales_data:
            if row["my_size"] in result:
                result[row["my_size"]] = row["total_units"] or 0

        return result


def get_sku_age_days(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> int:
    """
    Get the age of a SKU in days since first sale.

    Helper function for new SKU adjustment in generate_po_draft().

    Args:
        sku_key: Style-level SKU key
        store_code: Store code
        db_path: Optional database path

    Returns:
        Days since first sale, or 0 if no sales found
    """
    with get_db(db_path) as conn:
        first_sale = conn.execute("""
            SELECT MIN(sale_date) as first_date
            FROM fact_sales_daily_size
            WHERE sku_key = ?
              AND store_code = ?
              AND units > 0
        """, (sku_key, store_code)).fetchone()

        if not first_sale or not first_sale["first_date"]:
            return 0

        first_date = datetime.fromisoformat(first_sale["first_date"]).date()
        return (date.today() - first_date).days


# ==============================================================================
# TASK-189: Phase 10 Integration (v2 functions using stock_ledger, sales_fact_v2)
# ==============================================================================

def get_size_current_stock_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get current on-hand stock by size using stock_ledger.

    TASK-189: Uses event-sourced stock_ledger instead of fact_inventory_snapshot_size.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping size -> current stock units
        Example: {"S": 20, "M": 35, "L": 45, "XL": 25, ...}
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate current stock from ledger events
        stock_data = conn.execute("""
            SELECT my_size, SUM(qty_change) as balance
            FROM stock_ledger
            WHERE sku_key = ?
              AND store_code = ?
            GROUP BY my_size
        """, (sku_key, store_code)).fetchall()

        # Build result
        result = {size: 0 for size in sizes}
        for row in stock_data:
            if row["my_size"] in result:
                result[row["my_size"]] = row["balance"] or 0

        return result


def get_size_inbound_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get inbound (in-transit) stock by size using po_line/po_header.

    TASK-189: Uses Phase 10 PO tables instead of fact_po_lines.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping size -> inbound stock units
        Example: {"S": 0, "M": 50, "L": 0, "XL": 30, ...}

    Note:
        - Returns pending qty (order_qty - received_qty) for POs not yet closed
        - Only includes POs with status not in CLOSED/CANCELLED
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate inbound from po_line joined with po_header
        inbound_data = conn.execute("""
            SELECT
                pl.my_size,
                SUM(pl.order_qty - COALESCE(pl.received_qty, 0)) as pending
            FROM po_line pl
            JOIN po_header ph ON pl.po_id = ph.po_id
            WHERE pl.sku_key = ?
              AND pl.status IN ('PENDING', 'PARTIAL')
              AND ph.status NOT IN ('CLOSED', 'CANCELLED')
            GROUP BY pl.my_size
        """, (sku_key,)).fetchall()

        # Build result
        result = {size: 0 for size in sizes}
        for row in inbound_data:
            if row["my_size"] in result:
                result[row["my_size"]] = int(row["pending"] or 0)

        return result


def get_size_sales_90d_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, int]:
    """
    Get total 90-day sales by size using sales_fact_v2.

    TASK-189: Uses deduplicated sales_fact_v2 instead of fact_sales_daily_size.

    Args:
        sku_key: Style-level SKU key
        store_code: Store code
        db_path: Optional database path

    Returns:
        Dict mapping size -> total units sold in last 90 days
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        # Get aggregated sales from sales_fact_v2
        sales_data = conn.execute("""
            SELECT my_size, SUM(quantity) as total_units
            FROM sales_fact_v2
            WHERE sku_key = ?
              AND store_code = ?
              AND sale_date >= ?
              AND sale_date <= ?
              AND status NOT IN ('CANCELLED', 'RETURNED')
            GROUP BY my_size
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        # Build result
        result = {size: 0 for size in sizes}
        for row in sales_data:
            if row["my_size"] in result:
                result[row["my_size"]] = row["total_units"] or 0

        return result


def get_size_sales_history_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    days: int = 90,
    db_path: Optional[Path] = None
) -> dict[str, list[int]]:
    """
    Get daily sales history by size using sales_fact_v2.

    TASK-189: Aggregates sales_fact_v2 by day instead of using fact_sales_daily_size.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        days: Number of days of history (default: 90)
        db_path: Optional database path

    Returns:
        Dict mapping size -> list of daily sales units
        Example: {"S": [1, 2, 0, 3, ...], "M": [3, 4, 2, 5, ...], ...}

    Note:
        - Missing days are filled with 0
        - Sizes come from dim_sku_size to ensure all sizes are present
        - Excludes CANCELLED and RETURNED sales
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get sales data aggregated by day from sales_fact_v2
        sales_data = conn.execute("""
            SELECT sale_date, my_size, SUM(quantity) as units
            FROM sales_fact_v2
            WHERE sku_key = ?
              AND store_code = ?
              AND sale_date >= ?
              AND sale_date <= ?
              AND status NOT IN ('CANCELLED', 'RETURNED')
            GROUP BY sale_date, my_size
            ORDER BY sale_date
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        # Build date -> size -> units mapping
        sales_by_date: dict[str, dict[str, int]] = {}
        for row in sales_data:
            d = row["sale_date"]
            if d not in sales_by_date:
                sales_by_date[d] = {}
            sales_by_date[d][row["my_size"]] = row["units"]

        # Generate complete date list
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current.isoformat())
            current += timedelta(days=1)

        # Build result with all sizes and all dates (fill missing with 0)
        result: dict[str, list[int]] = {}
        for size in sizes:
            result[size] = []
            for d in date_list:
                units = sales_by_date.get(d, {}).get(size, 0)
                result[size].append(units)

        return result


def get_size_stock_history_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    days: int = 90,
    db_path: Optional[Path] = None
) -> dict[str, list[int]]:
    """
    Get daily stock history by size using stock_ledger.

    TASK-189: Calculates running balances from stock_ledger instead of
    using fact_inventory_snapshot_size.

    This is used for OOS-filtered demand calculation - days where
    both sales=0 AND stock=0 are considered true stockouts.

    Args:
        sku_key: Style-level SKU key (e.g., "CL_OC_MEN_LINE52_BLACK")
        store_code: Store code (default: "UNIVERSAL")
        days: Number of days of history (default: 90)
        db_path: Optional database path

    Returns:
        Dict mapping size -> list of daily stock levels (EOD balance)
        Example: {"S": [10, 8, 5, 12, ...], "M": [20, 18, 15, 22, ...], ...}

    Note:
        - Missing days use previous day's balance
        - Sizes come from dim_sku_size to ensure all sizes are present
    """
    with get_db(db_path) as conn:
        # Get all sizes for this SKU
        sizes_result = conn.execute("""
            SELECT DISTINCT my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        sizes = [row["my_size"] for row in sizes_result]

        if not sizes:
            return {}

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Generate complete date list
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current.isoformat())
            current += timedelta(days=1)

        result: dict[str, list[int]] = {}

        for size in sizes:
            sku_id = f"{sku_key}_{size}"

            # Get all events for this sku_id up to end_date
            events = conn.execute("""
                SELECT event_date, qty_change
                FROM stock_ledger
                WHERE sku_id = ?
                  AND store_code = ?
                  AND event_date <= ?
                ORDER BY event_date, ledger_id
            """, (sku_id, store_code, end_date.isoformat())).fetchall()

            # Build event changes by date
            changes_by_date: dict[str, int] = {}
            for row in events:
                d = row["event_date"]
                if d not in changes_by_date:
                    changes_by_date[d] = 0
                changes_by_date[d] += row["qty_change"]

            # Calculate running balance for each date in the range
            # Start with balance before start_date
            balance_before = conn.execute("""
                SELECT COALESCE(SUM(qty_change), 0) as balance
                FROM stock_ledger
                WHERE sku_id = ?
                  AND store_code = ?
                  AND event_date < ?
            """, (sku_id, store_code, start_date.isoformat())).fetchone()

            running_balance = balance_before["balance"] if balance_before else 0

            daily_balances = []
            for d in date_list:
                # Apply changes for this date
                running_balance += changes_by_date.get(d, 0)
                daily_balances.append(running_balance)

            result[size] = daily_balances

        return result


def get_sku_age_days_v2(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> int:
    """
    Get the age of a SKU in days since first sale using sales_fact_v2.

    TASK-189: Uses sales_fact_v2 instead of fact_sales_daily_size.

    Args:
        sku_key: Style-level SKU key
        store_code: Store code
        db_path: Optional database path

    Returns:
        Days since first sale, or 0 if no sales found
    """
    with get_db(db_path) as conn:
        first_sale = conn.execute("""
            SELECT MIN(sale_date) as first_date
            FROM sales_fact_v2
            WHERE sku_key = ?
              AND store_code = ?
              AND status NOT IN ('CANCELLED', 'RETURNED')
        """, (sku_key, store_code)).fetchone()

        if not first_sale or not first_sale["first_date"]:
            return 0

        first_date = datetime.fromisoformat(first_sale["first_date"]).date()
        return (date.today() - first_date).days


def get_po_lines_for_sku(
    sku_key: str,
    status: str = None,
    db_path: Optional[Path] = None
) -> list[dict]:
    """
    Get PO lines for a SKU from po_line/po_header.

    TASK-189: New function for Phase 10 PO tracking.

    Args:
        sku_key: Style-level SKU key
        status: Optional filter by PO line status (PENDING, PARTIAL, RECEIVED)
        db_path: Optional database path

    Returns:
        List of PO line dicts with po_id, sku_id, my_size, order_qty,
        received_qty, status, and po_status from po_header
    """
    with get_db(db_path) as conn:
        conditions = ["pl.sku_key = ?"]
        params = [sku_key]

        if status:
            conditions.append("pl.status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions)

        rows = conn.execute(f"""
            SELECT
                pl.po_line_id,
                pl.po_id,
                pl.sku_id,
                pl.my_size,
                pl.order_qty,
                pl.received_qty,
                pl.unit_cost_cny,
                pl.status as line_status,
                ph.status as po_status,
                ph.supplier_code,
                ph.ast_arrival_real as eta
            FROM po_line pl
            JOIN po_header ph ON pl.po_id = ph.po_id
            WHERE {where_clause}
            ORDER BY ph.created_at DESC, pl.my_size
        """, params).fetchall()

        return [dict(row) for row in rows]


def get_stock_movement_summary(
    sku_key: str,
    store_code: str = "UNIVERSAL",
    days: int = 30,
    db_path: Optional[Path] = None
) -> dict:
    """
    Get stock movement summary for a SKU from stock_ledger.

    TASK-189: New function for Phase 10 reporting.

    Args:
        sku_key: Style-level SKU key
        store_code: Store code
        days: Number of days to summarize
        db_path: Optional database path

    Returns:
        Dict with:
        - current_stock: Total current balance by size
        - movements: {event_type: total_qty_change} summary
        - by_size: {size: {event_type: qty}} breakdown
    """
    with get_db(db_path) as conn:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Current stock by size
        current_stock = conn.execute("""
            SELECT my_size, SUM(qty_change) as balance
            FROM stock_ledger
            WHERE sku_key = ?
              AND store_code = ?
            GROUP BY my_size
        """, (sku_key, store_code)).fetchall()

        # Movement summary
        movements = conn.execute("""
            SELECT event_type, SUM(qty_change) as total
            FROM stock_ledger
            WHERE sku_key = ?
              AND store_code = ?
              AND event_date >= ?
            GROUP BY event_type
        """, (sku_key, store_code, start_date.isoformat())).fetchall()

        # Breakdown by size and event type
        by_size = conn.execute("""
            SELECT my_size, event_type, SUM(qty_change) as total
            FROM stock_ledger
            WHERE sku_key = ?
              AND store_code = ?
              AND event_date >= ?
            GROUP BY my_size, event_type
        """, (sku_key, store_code, start_date.isoformat())).fetchall()

        # Build result
        result = {
            "current_stock": {row["my_size"]: row["balance"] for row in current_stock},
            "movements": {row["event_type"]: row["total"] for row in movements},
            "by_size": {},
        }

        for row in by_size:
            size = row["my_size"]
            if size not in result["by_size"]:
                result["by_size"][size] = {}
            result["by_size"][size][row["event_type"]] = row["total"]

        return result


# ==============================================================================
# DEMAND ESTIMATOR: Query helpers for DemandEstimator module
# ==============================================================================

def get_cutoff_date_almaty() -> date:
    """
    Get yesterday's date in Asia/Almaty timezone.

    This is the proper cutoff for demand calculation - we use yesterday
    because today's data may be incomplete.

    Returns:
        date: Yesterday in Asia/Almaty timezone
    """
    import zoneinfo

    almaty_tz = zoneinfo.ZoneInfo("Asia/Almaty")
    now_almaty = datetime.now(almaty_tz)
    yesterday = now_almaty.date() - timedelta(days=1)
    return yesterday


def get_global_sales_calendar(
    start_date: date,
    end_date: date,
    db_path: Optional[Path] = None
) -> set[str]:
    """
    Get set of dates that have ANY sales records globally.

    Used by DemandEstimator to distinguish "no data" from "true zero sales".
    If a date is not in this set, it means the ingest didn't run that day
    (or there were truly no sales globally), so missing SKU sales should
    be treated as UNKNOWN, not zero.

    Args:
        start_date: Start of date range
        end_date: End of date range
        db_path: Optional database path

    Returns:
        Set of date strings (ISO format) that have sales records
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT DISTINCT sale_date
            FROM fact_sales_daily_size
            WHERE sale_date >= ?
              AND sale_date <= ?
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        return {row["sale_date"] for row in rows}


def get_global_stock_calendar(
    start_date: date,
    end_date: date,
    db_path: Optional[Path] = None
) -> set[str]:
    """
    Get set of dates that have ANY stock snapshots globally.

    Used by DemandEstimator to distinguish "no snapshot" from "true zero stock".
    If a date is not in this set, it means no snapshot was taken that day,
    so missing SKU stock should be treated as UNKNOWN, not zero.

    Args:
        start_date: Start of date range
        end_date: End of date range
        db_path: Optional database path

    Returns:
        Set of date strings (ISO format) that have stock snapshots
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT DISTINCT snapshot_date
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date >= ?
              AND snapshot_date <= ?
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        return {row["snapshot_date"] for row in rows}


def get_active_sku_keys(db_path: Optional[Path] = None) -> list[str]:
    """
    Get list of all active SKU keys from dim_sku.

    Used by DemandEstimator to enumerate all SKUs that should be processed.
    Filters to only sku_keys where active_flag = 1.

    Args:
        db_path: Optional database path

    Returns:
        List of distinct sku_key strings that are active
    """
    with get_db(db_path) as conn:
        # First check if dim_sku exists with active_flag
        try:
            rows = conn.execute("""
                SELECT DISTINCT sku_key
                FROM dim_sku
                WHERE active_flag = 1
                ORDER BY sku_key
            """).fetchall()
        except sqlite3.OperationalError:
            # Fall back to dim_sku_size if dim_sku doesn't exist
            rows = conn.execute("""
                SELECT DISTINCT sku_key
                FROM dim_sku_size
                WHERE active_flag = 1
                ORDER BY sku_key
            """).fetchall()

        return [row["sku_key"] for row in rows]


def get_sku_sizes(
    sku_key: str,
    db_path: Optional[Path] = None
) -> list[dict]:
    """
    Get all sizes for a SKU with their metadata.

    Args:
        sku_key: Style-level SKU key
        db_path: Optional database path

    Returns:
        List of dicts with my_size, size_order, sku_id
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT sku_id, my_size, size_order
            FROM dim_sku_size
            WHERE sku_key = ?
            ORDER BY size_order
        """, (sku_key,)).fetchall()

        return [dict(row) for row in rows]


def get_sku_daily_sales(
    sku_key: str,
    start_date: date,
    end_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, dict[str, int]]:
    """
    Get daily sales by size for a SKU within a date range.

    Unlike get_size_sales_history which fills missing with 0,
    this returns ONLY the days that have actual data.

    Args:
        sku_key: Style-level SKU key
        start_date: Start of date range
        end_date: End of date range
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping date_str -> {size: units}
        Only includes dates that have data (no gap filling)
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT sale_date, my_size, units
            FROM fact_sales_daily_size
            WHERE sku_key = ?
              AND store_code = ?
              AND sale_date >= ?
              AND sale_date <= ?
            ORDER BY sale_date
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        result: dict[str, dict[str, int]] = {}
        for row in rows:
            d = row["sale_date"]
            if d not in result:
                result[d] = {}
            result[d][row["my_size"]] = row["units"]

        return result


def get_sku_daily_stock(
    sku_key: str,
    start_date: date,
    end_date: date,
    db_path: Optional[Path] = None
) -> dict[str, dict[str, int]]:
    """
    Get daily stock snapshots by size for a SKU within a date range.

    Unlike get_size_stock_history which fills missing with 0,
    this returns ONLY the days that have actual snapshots.

    Args:
        sku_key: Style-level SKU key
        start_date: Start of date range
        end_date: End of date range
        db_path: Optional database path

    Returns:
        Dict mapping date_str -> {size: current_stock}
        Only includes dates that have snapshots (no gap filling)
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT snapshot_date, my_size, current_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_key = ?
              AND snapshot_date >= ?
              AND snapshot_date <= ?
            ORDER BY snapshot_date
        """, (sku_key, start_date.isoformat(), end_date.isoformat())).fetchall()

        result: dict[str, dict[str, int]] = {}
        for row in rows:
            d = row["snapshot_date"]
            if d not in result:
                result[d] = {}
            result[d][row["my_size"]] = row["current_stock"]

        return result


def get_sku_daily_sales_v2(
    sku_key: str,
    start_date: date,
    end_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Optional[Path] = None
) -> dict[str, dict[str, int]]:
    """
    Get daily sales by size for a SKU using sales_fact_v2.

    V2 version that reads from sales_fact_v2 instead of fact_sales_daily_size
    for fresh data. This table is synced daily from CRM.

    Args:
        sku_key: Style-level SKU key
        start_date: Start of date range
        end_date: End of date range
        store_code: Store code (default: "UNIVERSAL")
        db_path: Optional database path

    Returns:
        Dict mapping date_str -> {size: units}
        Only includes dates that have data (no gap filling)
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT order_date, my_size, SUM(quantity) as units
            FROM sales_fact_v2
            WHERE sku_key = ?
              AND store_code = ?
              AND order_date >= ?
              AND order_date <= ?
              AND status NOT IN ('CANCELLED', 'RETURNED')
            GROUP BY order_date, my_size
            ORDER BY order_date
        """, (sku_key, store_code, start_date.isoformat(), end_date.isoformat())).fetchall()

        result: dict[str, dict[str, int]] = {}
        for row in rows:
            d = row["order_date"]
            if d not in result:
                result[d] = {}
            result[d][row["my_size"]] = row["units"]

        return result


def get_global_sales_calendar_v2(
    start_date: date,
    end_date: date,
    db_path: Optional[Path] = None
) -> set[str]:
    """
    Get set of dates that have ANY sales records globally using sales_fact_v2.

    V2 version reads from sales_fact_v2 for fresh data.
    Used by DemandEstimator to distinguish "no data" from "true zero sales".

    Args:
        start_date: Start of date range
        end_date: End of date range
        db_path: Optional database path

    Returns:
        Set of date strings (ISO format) that have sales records
    """
    with get_db(db_path) as conn:
        rows = conn.execute("""
            SELECT DISTINCT order_date
            FROM sales_fact_v2
            WHERE order_date >= ?
              AND order_date <= ?
              AND status NOT IN ('CANCELLED', 'RETURNED')
        """, (start_date.isoformat(), end_date.isoformat())).fetchall()

        return {row["order_date"] for row in rows}


def get_max_sales_date(db_path: Optional[Path] = None) -> Optional[date]:
    """
    Get the maximum sale_date in the database.

    Used to detect stale data - if max_sales_date < cutoff_date - 1,
    the sales data may be outdated.

    Args:
        db_path: Optional database path

    Returns:
        Maximum sale_date or None if no sales
    """
    with get_db(db_path) as conn:
        row = conn.execute("""
            SELECT MAX(sale_date) as max_date
            FROM fact_sales_daily_size
        """).fetchone()

        if row and row["max_date"]:
            return date.fromisoformat(row["max_date"])
        return None
