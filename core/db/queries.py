"""
TASK-165: Size-level data queries for Phase 9.6

Provides functions to retrieve size-level sales and inventory data
needed by the size-aware PO allocation engine.

Tables used:
- fact_sales_daily_size: Daily sales by size
- fact_inventory_snapshot_size: Daily stock levels by size
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
