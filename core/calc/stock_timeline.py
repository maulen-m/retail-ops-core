#!/usr/bin/env python3
"""
Stock Timeline Rebuild Module.

Reconstructs daily size-level stock history from PO receipts + sales + current stock.
This enables stock-first partial OOS detection when daily snapshots don't exist.

Algorithm (backward reconstruction):
1. Build arrivals[sku_id, d] = sum(receipts on d) from PO arrivals with DELIVERED status
2. Build sales[sku_id, d] = sum(units sold on d) from sales_fact_v2
3. Set stock_start[sku_id, cutoff_date+1] = current_stock (from latest snapshot)
4. For d going backward:
   stock_start[sku_id, d] = max(0, stock_start[sku_id, d+1] - arrivals[sku_id, d] + sales[sku_id, d])

Output:
- stock_start_by_day: dict[(sku_id, date_str)] -> int
- Diagnostics per sku_id:
  - rebuild_negative_clamps_count: How often we had to clamp to 0
  - unexplained_delta_total: Sum of clamped amounts (data quality indicator)

Usage:
    from core.calc.stock_timeline import StockTimelineBuilder
    builder = StockTimelineBuilder(db_path)
    timeline, diagnostics = builder.rebuild_timeline(sku_ids, start_date, end_date)
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass
class SKUTimelineDiagnostics:
    """Diagnostics for a single SKU's timeline rebuild."""
    sku_id: str
    sku_key: str
    current_stock: int = 0
    total_sales: int = 0
    total_arrivals: int = 0
    days_rebuilt: int = 0
    negative_clamps_count: int = 0
    unexplained_delta_total: int = 0
    first_arrival_date: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    # New fields for extended diagnostics
    base_snapshot_date_used: Optional[str] = None
    timeline_coverage_days: int = 0
    eligible_days: int = 0  # Days where stock was known (eligible for demand calc)
    unknown_days: int = 0   # Days where stock couldn't be determined


class StockTimelineBuilder:
    """
    Rebuilds daily stock timeline from PO arrivals + sales + current stock.

    This is needed because:
    1. We may not have daily stock snapshots
    2. We need to know "was this size OOS on day X?" for partial OOS detection
    """

    def __init__(self, db_path: Path, lookback_days: int = 365):
        """
        Initialize builder with database path.

        Args:
            db_path: Path to SQLite database
            lookback_days: Maximum days to rebuild (default 365)
        """
        self.db_path = Path(db_path)
        self.lookback_days = lookback_days
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_current_stock_by_size(self, snapshot_date: str) -> dict[str, dict]:
        """
        Get current stock by sku_id from latest snapshot.

        Returns:
            dict[sku_id] -> {'current_stock': int, 'sku_key': str, 'my_size': str}
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT sku_id, sku_key, my_size, current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date,))

        result = {}
        for row in cursor.fetchall():
            result[row['sku_id']] = {
                'current_stock': row['current_stock'] or 0,
                'inbound_stock': row['inbound_stock'] or 0,
                'sku_key': row['sku_key'],
                'my_size': row['my_size']
            }
        return result

    def get_latest_snapshot_date(self, max_date: str) -> Optional[str]:
        """
        Find the latest snapshot_date that is <= max_date.

        Args:
            max_date: Maximum date to look for (typically today)

        Returns:
            Latest snapshot_date string, or None if no snapshots exist
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT MAX(snapshot_date) as latest_date
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date <= ?
        """, (max_date,))
        row = cursor.fetchone()
        return row['latest_date'] if row and row['latest_date'] else None

    def forward_simulate_stock(
        self,
        base_stock: dict[str, dict],
        base_date: str,
        target_date: str
    ) -> dict[str, dict]:
        """
        Forward-simulate stock from base_date to target_date.

        IMPORTANT: The snapshot represents MORNING stock BEFORE shipping orders.
        So we must include sales from base_date itself in the simulation.

        Uses sales and arrivals to compute what stock should be as-of target_date:
        stock[target] = stock[base_morning] - sales[base..target] + arrivals[base..target]

        Args:
            base_stock: Stock levels as-of base_date MORNING (from snapshot, before shipping)
            base_date: The date of the snapshot (e.g., '2025-12-17')
            target_date: The date we want stock for (e.g., '2025-12-20')

        Returns:
            dict[sku_id] -> {'current_stock': int, 'sku_key': str, 'my_size': str, ...}
        """
        from datetime import datetime

        base_dt = datetime.fromisoformat(base_date).date()
        target_dt = datetime.fromisoformat(target_date).date()

        if target_dt < base_dt:
            # No forward simulation needed (target is before snapshot)
            return base_stock

        # Get sales and arrivals from base_date to target (inclusive)
        # NOTE: base_date is included because snapshot is MORNING stock (before shipping)
        sim_start = base_date  # Include base_date (sales shipped that day)
        sim_end = target_date

        sales_by_sku = self.get_sales_by_sku_id(sim_start, sim_end)
        arrivals_by_sku = self.get_arrivals_by_sku_id(sim_start, sim_end)

        # Build simulated stock
        result = {}
        for sku_id, stock_info in base_stock.items():
            base_qty = stock_info.get('current_stock', 0)

            # Sum sales from base_date to target (inclusive)
            sku_sales = sales_by_sku.get(sku_id, {})
            total_sales = sum(sku_sales.values())

            # Sum arrivals from base_date to target (inclusive)
            sku_arrivals = arrivals_by_sku.get(sku_id, {})
            total_arrivals = sum(sku_arrivals.values())

            # Forward simulate: stock -= sales, stock += arrivals
            simulated_stock = max(0, base_qty - total_sales + total_arrivals)

            result[sku_id] = {
                'current_stock': simulated_stock,
                'inbound_stock': stock_info.get('inbound_stock', 0),
                'sku_key': stock_info.get('sku_key', sku_id.rsplit('_', 1)[0]),
                'my_size': stock_info.get('my_size', sku_id.split('_')[-1]),
                # Track simulation details
                '_base_stock': base_qty,
                '_sales_simulated': total_sales,
                '_arrivals_simulated': total_arrivals,
            }

        return result

    def get_sales_by_sku_id(
        self,
        start_date: str,
        end_date: str
    ) -> dict[str, dict[str, int]]:
        """
        Get sales aggregated by (sku_id, date).

        Returns:
            dict[sku_id] -> dict[date_str] -> units_sold
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT sku_id, order_date, SUM(quantity) as units
            FROM sales_fact_v2
            WHERE order_date >= ? AND order_date <= ?
              AND status = 'DELIVERED'
            GROUP BY sku_id, order_date
        """, (start_date, end_date))

        result: dict[str, dict[str, int]] = {}
        for row in cursor.fetchall():
            sku_id = row['sku_id']
            if sku_id not in result:
                result[sku_id] = {}
            result[sku_id][row['order_date']] = row['units']

        return result

    def get_arrivals_by_sku_id(
        self,
        start_date: str,
        end_date: str
    ) -> dict[str, dict[str, int]]:
        """
        Get PO arrivals aggregated by (sku_id, actual_arrival_date).

        Only includes DELIVERED POs with actual_arrival_date.

        Returns:
            dict[sku_id] -> dict[date_str] -> units_received
        """
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT sku_id, actual_arrival_date, SUM(received_qty) as units
            FROM fact_po_lines
            WHERE actual_arrival_date IS NOT NULL
              AND actual_arrival_date >= ?
              AND actual_arrival_date <= ?
              AND status = 'DELIVERED'
            GROUP BY sku_id, actual_arrival_date
        """, (start_date, end_date))

        result: dict[str, dict[str, int]] = {}
        for row in cursor.fetchall():
            sku_id = row['sku_id']
            if sku_id not in result:
                result[sku_id] = {}
            result[sku_id][row['actual_arrival_date']] = row['units']

        return result

    def get_all_sku_ids(self, snapshot_date: str) -> list[str]:
        """Get all sku_ids from current snapshot."""
        conn = self._get_conn()
        cursor = conn.execute("""
            SELECT DISTINCT sku_id FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date,))
        return [row['sku_id'] for row in cursor.fetchall()]

    def rebuild_timeline(
        self,
        end_date: date,
        start_date: Optional[date] = None,
        sku_ids: Optional[list[str]] = None
    ) -> tuple[dict[tuple[str, str], int], list[SKUTimelineDiagnostics]]:
        """
        Rebuild stock timeline for all or specified sku_ids.

        Uses backward reconstruction:
        stock_start[d] = max(0, stock_start[d+1] - arrivals[d] + sales[d])

        Args:
            end_date: The "as of" date (typically today)
            start_date: Optional start date (default: end_date - lookback_days)
            sku_ids: Optional list of specific sku_ids (default: all)

        Returns:
            Tuple of:
            - stock_timeline: dict[(sku_id, date_str)] -> stock_at_start_of_day
            - diagnostics: list[SKUTimelineDiagnostics]
        """
        if start_date is None:
            start_date = end_date - timedelta(days=self.lookback_days)

        end_date_str = end_date.isoformat()
        start_date_str = start_date.isoformat()

        # Find latest snapshot <= end_date (not exact match)
        base_snapshot_date = self.get_latest_snapshot_date(end_date_str)

        if base_snapshot_date is None:
            # No snapshot available - return empty timeline with warning
            return {}, []

        # Get stock from the base snapshot
        base_stock = self.get_current_stock_by_size(base_snapshot_date)

        # Forward-simulate if base snapshot is older than end_date
        if base_snapshot_date != end_date_str:
            current_stock = self.forward_simulate_stock(
                base_stock, base_snapshot_date, end_date_str
            )
        else:
            current_stock = base_stock

        if sku_ids is None:
            sku_ids = list(current_stock.keys())

        # Get all sales and arrivals in the period
        all_sales = self.get_sales_by_sku_id(start_date_str, end_date_str)
        all_arrivals = self.get_arrivals_by_sku_id(start_date_str, end_date_str)

        # Build date list (going backward from end_date to start_date)
        date_list = []
        current = end_date
        while current >= start_date:
            date_list.append(current.isoformat())
            current -= timedelta(days=1)

        # Initialize results
        stock_timeline: dict[tuple[str, str], int] = {}
        diagnostics: list[SKUTimelineDiagnostics] = []

        for sku_id in sku_ids:
            stock_info = current_stock.get(sku_id, {})
            sku_key = stock_info.get('sku_key', sku_id.rsplit('_', 1)[0])
            current_stock_val = stock_info.get('current_stock', 0)

            sales_by_date = all_sales.get(sku_id, {})
            arrivals_by_date = all_arrivals.get(sku_id, {})

            diag = SKUTimelineDiagnostics(
                sku_id=sku_id,
                sku_key=sku_key,
                current_stock=current_stock_val,
                total_sales=sum(sales_by_date.values()),
                total_arrivals=sum(arrivals_by_date.values()),
                days_rebuilt=len(date_list),
                base_snapshot_date_used=base_snapshot_date,
                timeline_coverage_days=len(date_list),
            )

            if arrivals_by_date:
                diag.first_arrival_date = min(arrivals_by_date.keys())

            # Backward reconstruction
            # stock_start at end_date+1 = current_stock (what we have at start of "today")
            next_day_stock = current_stock_val
            in_stock_days = 0  # Days where stock > 0

            for i, date_str in enumerate(date_list):
                # stock_start[d] = stock_start[d+1] - arrivals[d] + sales[d]
                # (going backward: we add back what was sold, subtract what arrived)
                arrivals_today = arrivals_by_date.get(date_str, 0)
                sales_today = sales_by_date.get(date_str, 0)

                # Stock at start of this day
                stock_start = next_day_stock - arrivals_today + sales_today

                # Clamp to non-negative (track as diagnostic)
                if stock_start < 0:
                    diag.negative_clamps_count += 1
                    diag.unexplained_delta_total += abs(stock_start)
                    stock_start = 0

                stock_timeline[(sku_id, date_str)] = stock_start
                next_day_stock = stock_start

                # Track in-stock days
                if stock_start > 0:
                    in_stock_days += 1

            # Set eligible_days (days where stock was known/reconstructed)
            # and unknown_days (days where we couldn't determine stock)
            diag.eligible_days = len(date_list)  # All days are known after reconstruction
            diag.unknown_days = 0  # No unknown days for SKUs that exist in snapshot

            # Warnings for data quality issues
            if diag.negative_clamps_count > 10:
                diag.warnings.append(
                    f"HIGH_CLAMP_COUNT: {diag.negative_clamps_count} negative clamps"
                )
            if diag.unexplained_delta_total > diag.total_sales * 0.2:
                diag.warnings.append(
                    f"HIGH_UNEXPLAINED_DELTA: {diag.unexplained_delta_total} units"
                )

            diagnostics.append(diag)

        return stock_timeline, diagnostics

    def get_stock_on_date(
        self,
        timeline: dict[tuple[str, str], int],
        sku_id: str,
        date_str: str
    ) -> Optional[int]:
        """Get stock for a specific sku_id on a specific date."""
        return timeline.get((sku_id, date_str))

    def get_availability_by_date(
        self,
        timeline: dict[tuple[str, str], int],
        sku_key: str,
        date_str: str,
        stock_threshold: int = 0
    ) -> dict[str, bool]:
        """
        Get availability (in-stock status) for all sizes of a sku_key on a date.

        Args:
            timeline: The stock timeline
            sku_key: The SKU key (style-level)
            date_str: The date to check
            stock_threshold: Stock level below which we consider OOS (default 0)

        Returns:
            dict[my_size] -> bool (True if in stock)
        """
        result: dict[str, bool] = {}
        for (sid, d), stock in timeline.items():
            if d == date_str and sid.startswith(sku_key + "_"):
                # Extract size from sku_id
                size = sid.split("_")[-1]
                result[size] = stock > stock_threshold
        return result

    def export_diagnostics_csv(
        self,
        diagnostics: list[SKUTimelineDiagnostics],
        output_path: Path
    ) -> None:
        """Export diagnostics to CSV file."""
        rows = []
        for d in diagnostics:
            rows.append({
                'sku_id': d.sku_id,
                'sku_key': d.sku_key,
                'current_stock': d.current_stock,
                'total_sales': d.total_sales,
                'total_arrivals': d.total_arrivals,
                'days_rebuilt': d.days_rebuilt,
                'negative_clamps_count': d.negative_clamps_count,
                'unexplained_delta_total': d.unexplained_delta_total,
                'first_arrival_date': d.first_arrival_date or '',
                'base_snapshot_date_used': d.base_snapshot_date_used or '',
                'timeline_coverage_days': d.timeline_coverage_days,
                'eligible_days': d.eligible_days,
                'unknown_days': d.unknown_days,
                'warnings': '; '.join(d.warnings)
            })

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)


def rebuild_stock_timeline_for_demand(
    db_path: Path,
    cutoff_date: date,
    lookback_days: int = 90
) -> tuple[dict[tuple[str, str], int], list[SKUTimelineDiagnostics]]:
    """
    Convenience function to rebuild stock timeline for demand estimation.

    Args:
        db_path: Path to database
        cutoff_date: The cutoff date (yesterday)
        lookback_days: How many days back to rebuild (default 90)

    Returns:
        Tuple of (stock_timeline, diagnostics)
    """
    builder = StockTimelineBuilder(db_path, lookback_days=lookback_days)
    try:
        # End date is day after cutoff (current stock date)
        # We store stock as "stock_start" for that day
        end_date = cutoff_date + timedelta(days=1)  # Today
        start_date = cutoff_date - timedelta(days=lookback_days)

        timeline, diagnostics = builder.rebuild_timeline(end_date, start_date)
        return timeline, diagnostics
    finally:
        builder.close()


# ============================================================================
# CLI Interface
# ============================================================================

if __name__ == "__main__":
    import sys
    from datetime import datetime

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DB_PATH = PROJECT_ROOT / "db" / "app.db"
    OUTPUT_PATH = PROJECT_ROOT / "exports" / "stock_rebuild_diagnostics.csv"

    print("=" * 60)
    print("STOCK TIMELINE REBUILD")
    print("=" * 60)
    print(f"Database: {DB_PATH}")
    print(f"Output: {OUTPUT_PATH}")

    # Get cutoff date (yesterday)
    today = datetime.now().date()
    cutoff_date = today - timedelta(days=1)
    print(f"Cutoff date: {cutoff_date}")
    print(f"Today (stock as-of): {today}")

    # Rebuild
    builder = StockTimelineBuilder(DB_PATH, lookback_days=90)
    try:
        timeline, diagnostics = builder.rebuild_timeline(today, cutoff_date - timedelta(days=90))

        print(f"\nRebuilt timeline for {len(diagnostics)} sku_ids")
        print(f"Total timeline entries: {len(timeline)}")

        # Export diagnostics
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        builder.export_diagnostics_csv(diagnostics, OUTPUT_PATH)
        print(f"\nExported diagnostics to: {OUTPUT_PATH}")

        # Summary stats
        total_clamps = sum(d.negative_clamps_count for d in diagnostics)
        total_unexplained = sum(d.unexplained_delta_total for d in diagnostics)
        with_warnings = [d for d in diagnostics if d.warnings]

        print(f"\n--- Diagnostics Summary ---")
        print(f"Total negative clamps: {total_clamps}")
        print(f"Total unexplained delta: {total_unexplained}")
        print(f"SKUs with warnings: {len(with_warnings)}")

        if with_warnings:
            print("\nSKUs with warnings:")
            for d in with_warnings[:10]:
                print(f"  {d.sku_id}: {d.warnings}")

    finally:
        builder.close()
