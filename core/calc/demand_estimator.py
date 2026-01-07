"""
DemandEstimator: ROIC-first demand estimation with anchor blending.

This module provides robust demand estimation by blending:
1. Anchor data from D_size_mix_reference.xlsx (expert estimates)
2. OOS-filtered sales data from the database

Key Features:
- Proper cutoff date handling (yesterday Asia/Almaty)
- OOS detection at multiple levels (Extended, Intermittent, Partial)
- Anchor-data blending based on confidence
- Coverage mask for missing days (unknown vs zero)
- Diagnostic output for all SKUs

Usage:
    estimator = DemandEstimator(DB_PATH, ANCHOR_FILE)
    results, skipped = estimator.estimate_all()
    estimator.export_diagnostics(results, DIAGNOSTICS_PATH)
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import math
import statistics
import sqlite3
import warnings

import pandas as pd


# =============================================================================
# Enums
# =============================================================================

class OOSType(Enum):
    """Out-of-stock classification types."""
    NONE = "NONE"                    # No OOS detected
    EXTENDED = "EXTENDED"            # >14 consecutive days OOS
    INTERMITTENT = "INTERMITTENT"    # >5 OOS days in last 30
    PARTIAL = "PARTIAL"              # Some sizes OOS while others sell


class ConfidenceLevel(Enum):
    """Confidence level for demand calculation."""
    HIGH = "HIGH"              # ≥60 good days
    MEDIUM = "MEDIUM"          # 30-59 good days
    LOW = "LOW"                # 14-29 good days
    ANCHOR_ONLY = "ANCHOR_ONLY"  # <14 good days


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DemandEstimatorConfig:
    """Configuration for DemandEstimator."""
    # Analysis window
    lookback_days: int = 90
    share_window_days: int = 30

    # OOS detection thresholds
    extended_oos_threshold: int = 14   # Consecutive days for EXTENDED
    intermittent_oos_threshold: int = 5  # OOS days in 30 for INTERMITTENT

    # Confidence thresholds (good days required)
    high_conf_days: int = 60
    medium_conf_days: int = 30
    low_conf_days: int = 14

    # Anchor weights by confidence level
    high_conf_anchor_weight: float = 0.1    # 10% anchor when high conf
    medium_conf_anchor_weight: float = 0.3  # 30% anchor when medium
    low_conf_anchor_weight: float = 0.5     # 50% anchor when low
    anchor_only_weight: float = 0.8         # 80% anchor when very low

    # Confidence uplift factors
    marginal_uplift: float = 1.2   # 20% uplift for 14-29 good days
    fallback_uplift: float = 1.5   # 50% uplift for <14 good days

    # Winsorization
    winsorize_percentile: float = 0.95  # Cap outliers at 95th percentile

    # Size mix guardrails
    min_size_mix: float = 0.03
    max_size_mix: float = 0.40

    # Per-size suppression threshold (relative drift)
    # A size is SUPPRESSED if (anchor_share - obs_share) / anchor_share >= this threshold
    suppression_relative_threshold: float = 0.30  # ≥30% drop from anchor = suppressed


@dataclass
class AnchorData:
    """Anchor data for a single SKU from Excel."""
    sku_key: str
    d_active: float                          # Daily demand from anchor
    sigma: float                             # Volatility from anchor
    size_shares: dict[str, float] = field(default_factory=dict)  # size -> share
    size_demands: dict[str, float] = field(default_factory=dict)  # size -> D


@dataclass
class CoverageDay:
    """Coverage status for a single day."""
    date_str: str
    has_global_sales: bool      # Did ANY SKU have sales this day?
    has_global_stock: bool      # Did ANY SKU have stock snapshot this day?
    sku_sales: int              # This SKU's sales (0 if no data)
    sku_stock: Optional[int]    # This SKU's stock (None if no snapshot)
    is_oos: bool                # True if confirmed OOS (sales=0 AND stock=0)
    is_valid: bool              # True if we can trust this day's data


@dataclass
class SizeDemandResult:
    """Per-size demand estimation result."""
    my_size: str
    sales_90d: int = 0
    share_anchor: float = 0.0
    share_data: float = 0.0
    share_final: float = 0.0
    d_size: float = 0.0
    is_partial_oos: bool = False


@dataclass
class SKUDemandResult:
    """Complete SKU-level demand estimation result."""
    sku_key: str
    cutoff_date: date

    # Anchor values
    d_anchor: float = 0.0
    sigma_anchor: float = 0.0
    has_anchor: bool = False

    # Data-driven values
    d_data: float = 0.0
    sigma_data: float = 0.0

    # Blended values
    d_final: float = 0.0
    sigma_final: float = 0.0

    # Coverage metrics
    calendar_days: int = 0
    sales_coverage_days: int = 0
    stock_coverage_days: int = 0
    eligible_days: int = 0
    unknown_days: int = 0
    good_days: int = 0
    coverage_pct: float = 0.0
    availability_score: float = 0.0

    # Confidence and weight
    confidence: ConfidenceLevel = ConfidenceLevel.ANCHOR_ONLY
    anchor_weight: float = 0.8

    # OOS detection
    oos_type: OOSType = OOSType.NONE
    oos_days_total: int = 0
    oos_extended_streak: int = 0
    partial_oos_sizes: list[str] = field(default_factory=list)

    # Suppression detection (count of sizes with ≥30% relative drift from anchor)
    suppression_count: int = 0

    # Size-level results
    size_results: dict[str, SizeDemandResult] = field(default_factory=dict)

    # Warnings and skip reason
    warnings: list[str] = field(default_factory=list)
    skip_reason: Optional[str] = None

    # Store aggregation metadata
    store_codes: list[str] = field(default_factory=list)
    store_aggregation_mode: str = "SINGLE"


# =============================================================================
# DemandEstimator Class
# =============================================================================

class DemandEstimator:
    """
    Main demand estimator class.

    Responsibilities:
    1. Load anchor data from Excel
    2. Get sales/stock history with proper cutoff
    3. Detect OOS conditions
    4. Blend anchor and data-driven estimates
    5. Produce diagnostic output
    """

    def __init__(
        self,
        db_path: Path,
        anchor_file: Optional[Path] = None,
        config: Optional[DemandEstimatorConfig] = None,
        use_db_anchors: bool = True,
    ):
        """Initialize estimator with database and anchor file paths."""
        self.db_path = Path(db_path)
        self.anchor_file = Path(anchor_file) if anchor_file else None
        self.config = config or DemandEstimatorConfig()
        self.use_db_anchors = use_db_anchors

        # Lazy-loaded data
        self._anchor_data: Optional[dict[str, AnchorData]] = None
        self._cutoff_date: Optional[date] = None
        self._global_sales_calendar: Optional[set[str]] = None
        self._global_stock_calendar: Optional[set[str]] = None
        self._stock_timeline: Optional[dict[tuple[str, str], int]] = None
        self._stock_diagnostics: Optional[list] = None
        self._stock_timeline_range: Optional[tuple[date, date]] = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def cutoff_date(self) -> date:
        """Get cutoff date (yesterday in Asia/Almaty timezone)."""
        if self._cutoff_date is None:
            from core.db.queries import get_cutoff_date_almaty
            self._cutoff_date = get_cutoff_date_almaty()
        return self._cutoff_date

    @property
    def anchor_data(self) -> dict[str, AnchorData]:
        """Get anchor data from Excel (lazy loaded)."""
        if self._anchor_data is None:
            self._anchor_data = self._load_anchor_data()
        return self._anchor_data

    # =========================================================================
    # Anchor Data Loading
    # =========================================================================

    def _load_anchor_data(self) -> dict[str, AnchorData]:
        """Load anchor data with DB-first policy and Excel fallback."""
        if self.use_db_anchors:
            anchor_data = self._load_anchor_data_from_db()
            if anchor_data:
                return anchor_data
            warnings.warn(
                "dim_anchor missing or empty; falling back to Excel anchors",
                RuntimeWarning,
            )

        if self.anchor_file is None:
            warnings.warn(
                "No anchor data available: dim_anchor missing/empty and no anchor_file provided; "
                "running data-only",
                RuntimeWarning,
            )
            return {}

        return self._load_anchor_data_from_excel()

    def _load_anchor_data_from_excel(self) -> dict[str, AnchorData]:
        """Load D_size_mix_reference.xlsx into memory."""
        if not self.anchor_file.exists():
            raise FileNotFoundError(f"Anchor file not found: {self.anchor_file}")

        df = pd.read_excel(self.anchor_file)

        # Expected columns: SKU_key, D_active, {size}_share, {size}_D, sigma
        size_share_cols = [c for c in df.columns if c.endswith('_share')]
        size_demand_cols = [c for c in df.columns if c.endswith('_D') and c != 'D_active']

        result: dict[str, AnchorData] = {}

        for _, row in df.iterrows():
            sku_key = str(row.get('SKU_key', '')).strip()
            if not sku_key:
                continue

            # Handle non-numeric D_active values (e.g., 'ELS', 'CL', NaN)
            d_active_raw = row.get('D_active', 0)
            try:
                d_active = float(d_active_raw) if pd.notna(d_active_raw) else 0.0
            except (ValueError, TypeError):
                # Non-numeric value like 'ELS' or 'CL' - skip or treat as 0
                d_active = 0.0

            # Handle sigma
            sigma_raw = row.get('sigma', 0)
            try:
                sigma = float(sigma_raw) if pd.notna(sigma_raw) else 0.0
            except (ValueError, TypeError):
                sigma = 0.0

            # Parse size shares (with error handling)
            size_shares = {}
            for col in size_share_cols:
                size = col.replace('_share', '')
                val = row.get(col, 0)
                try:
                    fval = float(val) if pd.notna(val) else 0.0
                    if fval > 0:
                        size_shares[size] = fval
                except (ValueError, TypeError):
                    pass  # Skip non-numeric values

            # Parse size demands (with error handling)
            size_demands = {}
            for col in size_demand_cols:
                size = col.replace('_D', '')
                val = row.get(col, 0)
                try:
                    fval = float(val) if pd.notna(val) else 0.0
                    if fval > 0:
                        size_demands[size] = fval
                except (ValueError, TypeError):
                    pass  # Skip non-numeric values

            result[sku_key] = AnchorData(
                sku_key=sku_key,
                d_active=d_active,
                sigma=sigma,
                size_shares=size_shares,
                size_demands=size_demands
            )

        return result

    def _load_anchor_data_from_db(self) -> dict[str, AnchorData]:
        """Load anchor data from dim_anchor table."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_anchor'"
            ).fetchone()
            if not table:
                return {}

            columns = [row["name"] for row in conn.execute("PRAGMA table_info(dim_anchor)")]
            size_share_cols = [c for c in columns if c.endswith("_share")]
            size_demand_cols = [
                c for c in columns if c.endswith("_D") and c.lower() != "d_active"
            ]

            rows = conn.execute("SELECT * FROM dim_anchor").fetchall()
            if not rows:
                return {}

            result: dict[str, AnchorData] = {}
            for row in rows:
                if "sku_key" in row.keys():
                    sku_key = str(row["sku_key"] or "").strip()
                elif "SKU_key" in row.keys():
                    sku_key = str(row["SKU_key"] or "").strip()
                else:
                    continue

                if not sku_key:
                    continue

                d_active = 0.0
                if "d_active" in row.keys() and row["d_active"] is not None:
                    d_active = float(row["d_active"])
                elif "D_active" in row.keys() and row["D_active"] is not None:
                    d_active = float(row["D_active"])

                sigma = 0.0
                if "sigma" in row.keys() and row["sigma"] is not None:
                    sigma = float(row["sigma"])

                size_shares = {
                    c.replace("_share", ""): float(row[c] or 0)
                    for c in size_share_cols
                }
                size_demands = {
                    c.replace("_D", ""): float(row[c] or 0)
                    for c in size_demand_cols
                }

                result[sku_key] = AnchorData(
                    sku_key=sku_key,
                    d_active=d_active,
                    sigma=sigma,
                    size_shares=size_shares,
                    size_demands=size_demands,
                )

            return result
        finally:
            conn.close()

    # =========================================================================
    # Global Calendars
    # =========================================================================

    def _get_global_sales_calendar(self, start_date: date, end_date: date) -> set[str]:
        """Get or cache global sales calendar."""
        if self._global_sales_calendar is None:
            from core.db.queries import get_global_sales_calendar_v2
            self._global_sales_calendar = get_global_sales_calendar_v2(
                start_date, end_date, self.db_path
            )
        return self._global_sales_calendar

    def _get_global_stock_calendar(self, start_date: date, end_date: date) -> set[str]:
        """Get or cache global stock calendar."""
        if self._global_stock_calendar is None:
            from core.db.queries import get_global_stock_calendar
            self._global_stock_calendar = get_global_stock_calendar(
                start_date, end_date, self.db_path
            )
        return self._global_stock_calendar

    # =========================================================================
    # Store and Stock Helpers
    # =========================================================================

    def _get_store_codes_for_sku(self, sku_key: str, start_date: date, end_date: date) -> list[str]:
        """Get distinct store codes for a SKU within the date range."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute("""
                SELECT DISTINCT store_code
                FROM sales_fact_v2
                WHERE sku_key = ?
                  AND order_date >= ?
                  AND order_date <= ?
            """, (sku_key, start_date.isoformat(), end_date.isoformat())).fetchall()
        finally:
            conn.close()

        codes = [r[0] for r in rows if r and r[0]]
        return sorted(set(codes))

    def _normalize_store_codes(
        self,
        store_codes: Optional[list[str]] | str,
        sku_key: str,
        start_date: date,
        end_date: date
    ) -> list[str]:
        """Normalize store codes to a sorted unique list."""
        if store_codes is None:
            codes = self._get_store_codes_for_sku(sku_key, start_date, end_date)
        elif isinstance(store_codes, str):
            codes = [store_codes]
        else:
            codes = list(store_codes)

        return sorted({c for c in codes if c})

    def _get_sku_daily_sales(
        self,
        sku_key: str,
        start_date: date,
        end_date: date,
        store_codes: list[str]
    ) -> dict[str, dict[str, int]]:
        """Aggregate daily sales by size across store codes."""
        from core.db.queries import get_sku_daily_sales_v2

        aggregated: dict[str, dict[str, int]] = {}
        for store_code in store_codes:
            daily = get_sku_daily_sales_v2(
                sku_key, start_date, end_date, store_code, self.db_path
            )
            for date_str, size_units in daily.items():
                if date_str not in aggregated:
                    aggregated[date_str] = {}
                for size, units in size_units.items():
                    aggregated[date_str][size] = aggregated[date_str].get(size, 0) + units

        return aggregated

    def _get_size_sales_90d(
        self,
        sku_key: str,
        store_codes: list[str]
    ) -> dict[str, int]:
        """Aggregate 90-day sales by size across store codes."""
        from core.db.queries import get_size_sales_90d

        aggregated: dict[str, int] = {}
        for store_code in store_codes:
            size_sales = get_size_sales_90d(sku_key, store_code, self.db_path)
            for size, units in size_sales.items():
                aggregated[size] = aggregated.get(size, 0) + int(units or 0)

        return aggregated

    def _ensure_stock_timeline(self, start_date: date, end_date: date) -> None:
        """Build and cache stock timeline for the current window."""
        if self._stock_timeline_range == (start_date, end_date) and self._stock_timeline is not None:
            return

        try:
            from core.calc.stock_timeline import StockTimelineBuilder
            builder = StockTimelineBuilder(self.db_path, lookback_days=self.config.lookback_days)
            try:
                timeline, diagnostics = builder.rebuild_timeline(end_date, start_date)
            finally:
                builder.close()

            self._stock_timeline = timeline
            self._stock_diagnostics = diagnostics
            self._stock_timeline_range = (start_date, end_date)
        except Exception as exc:
            warnings.warn(f"Stock timeline rebuild failed: {exc}", RuntimeWarning)
            self._stock_timeline = {}
            self._stock_diagnostics = []
            self._stock_timeline_range = (start_date, end_date)

    # =========================================================================
    # Coverage Mask Building
    # =========================================================================

    def _build_coverage_mask(
        self,
        sku_key: str,
        start_date: date,
        end_date: date,
        store_codes: Optional[list[str]] = None
    ) -> list[CoverageDay]:
        """
        Build coverage mask for each day in the analysis window.

        This distinguishes between:
        - Days with no global data (treat SKU data as UNKNOWN)
        - Days with global data but no SKU data (treat as ZERO for SKU)
        - Days with SKU data (use actual values)
        """
        from core.db.queries import get_sku_daily_stock, get_sku_sizes

        store_codes = store_codes or []

        # Get global calendars
        global_sales = self._get_global_sales_calendar(start_date, end_date)
        global_stock = self._get_global_stock_calendar(start_date, end_date)

        # Get SKU-specific sales (aggregated across stores)
        sku_sales = self._get_sku_daily_sales(
            sku_key, start_date, end_date, store_codes
        )
        sku_stock = get_sku_daily_stock(
            sku_key, start_date, end_date, self.db_path
        )

        # Attempt to use stock timeline reconstruction if available
        self._ensure_stock_timeline(start_date, end_date)
        timeline = self._stock_timeline or {}

        sizes = get_sku_sizes(sku_key, self.db_path)
        sku_ids = [s.get('sku_id') or f"{sku_key}_{s['my_size']}" for s in sizes] if sizes else []

        # Build coverage for each calendar day
        coverage: list[CoverageDay] = []
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()

            has_global_sales = date_str in global_sales
            has_global_stock = date_str in global_stock

            # Get SKU sales for this day
            sku_sales_today = 0
            if date_str in sku_sales:
                # Sum all sizes
                sku_sales_today = sum(sku_sales[date_str].values())

            # Get SKU stock for this day (None if unknown)
            sku_stock_today: Optional[int] = None
            if timeline and sku_ids:
                total = 0
                any_known = False
                for sku_id in sku_ids:
                    key = (sku_id, date_str)
                    if key in timeline:
                        any_known = True
                        total += timeline[key]
                if any_known:
                    sku_stock_today = total
                    has_global_stock = True
            else:
                if date_str in sku_stock:
                    # Sum all sizes
                    sku_stock_today = sum(sku_stock[date_str].values())

            # Determine OOS status
            # OOS = confirmed zero sales AND confirmed zero stock
            is_oos = False
            if has_global_sales and has_global_stock:
                # We have coverage for both - can determine OOS
                if sku_sales_today == 0 and sku_stock_today is not None and sku_stock_today == 0:
                    is_oos = True

            # Determine if this is a valid day for demand calculation
            # Valid if we have sales coverage or known stock for this SKU
            is_valid = has_global_sales or sku_stock_today is not None

            coverage.append(CoverageDay(
                date_str=date_str,
                has_global_sales=has_global_sales,
                has_global_stock=has_global_stock,
                sku_sales=sku_sales_today,
                sku_stock=sku_stock_today,
                is_oos=is_oos,
                is_valid=is_valid
            ))

            current += timedelta(days=1)

        return coverage

    # =========================================================================
    # OOS Detection
    # =========================================================================

    def _detect_oos(
        self,
        coverage: list[CoverageDay]
    ) -> tuple[OOSType, int, int, list[str]]:
        """
        Detect OOS type from coverage data.

        Returns:
            Tuple of (oos_type, total_oos_days, max_consecutive, partial_oos_sizes)
        """
        cfg = self.config

        # Count OOS days
        oos_days = [c for c in coverage if c.is_oos]
        total_oos = len(oos_days)

        # Find longest consecutive OOS streak
        max_streak = 0
        current_streak = 0
        for c in coverage:
            if c.is_oos:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        # Check for Extended OOS (>14 consecutive days)
        if max_streak > cfg.extended_oos_threshold:
            return OOSType.EXTENDED, total_oos, max_streak, []

        # Check for Intermittent OOS (>5 OOS days in last 30)
        last_30 = coverage[-30:] if len(coverage) >= 30 else coverage
        oos_in_30 = len([c for c in last_30 if c.is_oos])
        if oos_in_30 > cfg.intermittent_oos_threshold:
            return OOSType.INTERMITTENT, total_oos, max_streak, []

        # Note: Partial OOS is detected at size level in _detect_partial_oos
        return OOSType.NONE, total_oos, max_streak, []

    def _detect_partial_oos(
        self,
        sku_key: str,
        anchor: Optional[AnchorData],
        start_date: date,
        end_date: date,
        store_codes: Optional[list[str]] = None,
        size_current_stock: Optional[dict[str, int]] = None
    ) -> list[str]:
        """
        Detect size-level suppression via relative share drift OR zero current stock.

        Rule 1: A size is SUPPRESSED if its observed share dropped ≥30% relative to anchor.
        Rule 2: A size is SUPPRESSED if current stock = 0 AND anchor share ≥ 5%.

        Formula (Rule 1): relative_drift = (anchor_share - observed_share) / anchor_share
        Threshold (Rule 1): ≥30% drop = suppressed
        Threshold (Rule 2): stock=0 with anchor_share ≥5% = suppressed

        This distinguishes:
        - Genuine demand decrease (all sizes ~same relative drift)
        - Stockout suppression (specific sizes have large drift OR zero stock)

        Returns:
            List of suppressed size codes
        """
        from core.db.queries import get_sku_sizes

        if anchor is None or not anchor.size_shares:
            return []

        # Get sizes for this SKU (dedupe in case of duplicate entries)
        sizes = get_sku_sizes(sku_key, self.db_path)
        if not sizes:
            return []

        # Deduplicate size names (handles data quality issues with duplicate dim_sku_size entries)
        size_names = list(dict.fromkeys(s['my_size'] for s in sizes))

        # Get daily sales by size
        store_codes = store_codes or []
        sku_sales = self._get_sku_daily_sales(
            sku_key, start_date, end_date, store_codes
        )

        # Aggregate sales by size
        size_totals: dict[str, int] = {s: 0 for s in size_names}
        for date_str, size_units in sku_sales.items():
            for size, units in size_units.items():
                if size in size_totals:
                    size_totals[size] += units

        total_sales = sum(size_totals.values())
        if total_sales == 0:
            return []  # Can't calculate shares without sales

        # Calculate observed shares
        observed_shares = {s: (units / total_sales) for s, units in size_totals.items()}

        # Detect suppressed sizes (≥30% relative drop from anchor)
        suppressed_sizes = []
        suppression_threshold = self.config.suppression_relative_threshold  # 0.30

        for size in size_names:
            anchor_share = anchor.size_shares.get(size, 0.0)
            observed_share = observed_shares.get(size, 0.0)

            if anchor_share <= 0:
                continue

            # Calculate relative drift
            relative_drift = (anchor_share - observed_share) / anchor_share

            # Flag if ≥30% below anchor
            if relative_drift >= suppression_threshold:
                suppressed_sizes.append(size)

        # Rule 2: Zero current stock with significant anchor share
        # Catches sizes CURRENTLY out of stock, regardless of historical sales
        # (Historical sales may look "normal" due to pre-stockout period)
        if size_current_stock and anchor and anchor.size_shares:
            for size, stock in size_current_stock.items():
                if size in suppressed_sizes:
                    continue  # Already flagged by Rule 1
                anchor_share = anchor.size_shares.get(size, 0.0)
                if stock == 0 and anchor_share >= 0.05:  # 5% threshold
                    suppressed_sizes.append(size)

        return suppressed_sizes

    # =========================================================================
    # Demand Calculation
    # =========================================================================

    def _calc_d_data(
        self,
        coverage: list[CoverageDay]
    ) -> tuple[float, int]:
        """
        Calculate data-driven demand with OOS filtering.

        Returns:
            Tuple of (d_daily, good_days)
        """
        cfg = self.config

        # Filter to good days (valid and not OOS)
        good_days_list = [c for c in coverage if c.is_valid and not c.is_oos]
        good_days = len(good_days_list)

        if good_days == 0:
            return 0.0, 0

        # Get daily sales for good days
        daily_sales = [c.sku_sales for c in good_days_list]

        # Winsorize to cap outliers
        daily_sales = self._winsorize(daily_sales)

        # Calculate average
        d_raw = sum(daily_sales) / good_days

        # Apply confidence uplift
        if good_days >= cfg.medium_conf_days:
            # ACTUAL - no uplift
            d_data = d_raw
        elif good_days >= cfg.low_conf_days:
            # MARGINAL - 20% uplift
            d_data = d_raw * cfg.marginal_uplift
        else:
            # FALLBACK - 50% uplift
            d_data = d_raw * cfg.fallback_uplift

        return d_data, good_days

    def _winsorize(self, values: list[int]) -> list[int]:
        """Apply winsorization to cap outliers at 95th percentile."""
        if len(values) < 2:
            return values

        cfg = self.config
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * cfg.winsorize_percentile)
        cap = sorted_vals[min(idx, len(sorted_vals) - 1)]

        return [min(v, cap) for v in values]

    def _calc_sigma_data(self, coverage: list[CoverageDay]) -> float:
        """Calculate data-driven volatility (std dev of daily sales)."""
        good_days_list = [c for c in coverage if c.is_valid and not c.is_oos]
        if len(good_days_list) < 2:
            return 0.0

        daily_sales = [c.sku_sales for c in good_days_list]
        try:
            return statistics.stdev(daily_sales)
        except statistics.StatisticsError:
            return 0.0

    # =========================================================================
    # Confidence and Weight Calculation
    # =========================================================================

    def _calc_confidence(
        self,
        sales_days: int,
        oos_type: OOSType
    ) -> ConfidenceLevel:
        """Determine confidence level based on sales coverage."""
        cfg = self.config

        # Base confidence from sales days
        if sales_days >= cfg.high_conf_days:
            base = ConfidenceLevel.HIGH
        elif sales_days >= cfg.medium_conf_days:
            base = ConfidenceLevel.MEDIUM
        elif sales_days >= cfg.low_conf_days:
            base = ConfidenceLevel.LOW
        else:
            base = ConfidenceLevel.ANCHOR_ONLY

        # Downgrade if significant OOS
        if oos_type == OOSType.EXTENDED:
            if base == ConfidenceLevel.HIGH:
                return ConfidenceLevel.MEDIUM
            elif base == ConfidenceLevel.MEDIUM:
                return ConfidenceLevel.LOW
        elif oos_type == OOSType.INTERMITTENT:
            if base == ConfidenceLevel.HIGH:
                return ConfidenceLevel.MEDIUM

        return base

    def _calc_blend_weight(
        self,
        confidence: ConfidenceLevel,
        oos_type: OOSType,
        has_anchor: bool,
        d_anchor: float = 0.0,
        d_data: float = 0.0,
        suppression_count: int = 0
    ) -> float:
        """Calculate anchor weight based on confidence, OOS, and suppression count."""
        cfg = self.config

        if not has_anchor:
            return 0.0  # No anchor available, use data only

        # If no usable data, trust anchor fully
        if d_data <= 0 and d_anchor > 0:
            return 1.0

        # Base weight from confidence
        if confidence == ConfidenceLevel.HIGH:
            w = cfg.high_conf_anchor_weight
        elif confidence == ConfidenceLevel.MEDIUM:
            w = cfg.medium_conf_anchor_weight
        elif confidence == ConfidenceLevel.LOW:
            w = cfg.low_conf_anchor_weight
        else:
            w = cfg.anchor_only_weight

        # Adjust for OOS - increase anchor trust when data is unreliable
        if oos_type == OOSType.EXTENDED:
            w = min(0.9, w + 0.2)
        elif oos_type == OOSType.INTERMITTENT:
            w = min(0.9, w + 0.1)

        # Suppression-based anchor weight adjustment
        # If sizes show ≥30% relative drop from anchor share → stockout likely
        if has_anchor and suppression_count > 0:
            if suppression_count >= 3:
                # Multiple sizes suppressed: strong stockout signal
                w = max(w, 0.8)
            elif suppression_count >= 2:
                # Two sizes suppressed: likely stockout
                w = max(w, 0.7)
            else:
                # One size suppressed: possible stockout
                w = max(w, 0.5)

        return w

    # =========================================================================
    # Demand Blending
    # =========================================================================

    def _blend_demand(
        self,
        d_anchor: float,
        d_data: float,
        w: float
    ) -> float:
        """
        Blend anchor and data-driven demand.

        Formula: D_final = w × D_anchor + (1-w) × D_data

        Also applies safety clip to prevent extreme values.
        """
        if d_anchor <= 0 and d_data <= 0:
            return 0.0

        # Handle no anchor case
        if d_anchor <= 0:
            return d_data

        # Handle no data case
        if d_data <= 0:
            return d_anchor

        # Blend
        d_final = w * d_anchor + (1 - w) * d_data

        # Safety clip: 0.5×min ≤ D_final ≤ 1.5×max
        min_val = min(d_anchor, d_data)
        max_val = max(d_anchor, d_data)
        d_final = max(0.5 * min_val, min(1.5 * max_val, d_final))

        return d_final

    # =========================================================================
    # Size Share Blending
    # =========================================================================

    def _calc_size_shares(
        self,
        sku_key: str,
        anchor: Optional[AnchorData],
        d_final: float,
        anchor_weight: float,
        partial_oos_sizes: list[str],
        start_date: date,
        end_date: date,
        store_codes: Optional[list[str]] = None
    ) -> dict[str, SizeDemandResult]:
        """
        Calculate size-level demand with share blending.

        Steps:
        1. Get data-driven shares from recent sales
        2. Blend with anchor shares using weight
        3. Apply partial OOS protection (boost anchor for OOS sizes)
        4. Apply 3%/40% guardrails
        5. Renormalize to sum = 1.0
        """
        from core.db.queries import get_sku_sizes

        cfg = self.config

        # Get sizes for this SKU
        sizes = get_sku_sizes(sku_key, self.db_path)
        if not sizes:
            return {}

        size_names = [s['my_size'] for s in sizes]

        store_codes = store_codes or []

        # Get 90-day sales by size (aggregated across stores)
        size_sales = self._get_size_sales_90d(sku_key, store_codes)
        total_sales = sum(size_sales.values())

        # Calculate data-driven shares
        data_shares: dict[str, float] = {}
        if total_sales > 0:
            for size in size_names:
                data_shares[size] = size_sales.get(size, 0) / total_sales
        else:
            # No sales - will use anchor only
            data_shares = {s: 0.0 for s in size_names}

        # Get anchor shares
        anchor_shares: dict[str, float] = {}
        if anchor:
            anchor_shares = anchor.size_shares.copy()

        # Blend shares for each size
        blended_shares: dict[str, float] = {}
        for size in size_names:
            a_share = anchor_shares.get(size, 0.0)
            d_share = data_shares.get(size, 0.0)

            # Adjust weight for partial OOS sizes (trust anchor more)
            local_w = anchor_weight
            if size in partial_oos_sizes and anchor:
                local_w = min(0.95, local_w + 0.3)

            # Blend
            if a_share > 0 or d_share > 0:
                blended = local_w * a_share + (1 - local_w) * d_share
            else:
                blended = 0.0

            blended_shares[size] = blended

        # Apply guardrails and renormalize
        final_shares = self._apply_size_guardrails(blended_shares)

        # Build results
        results: dict[str, SizeDemandResult] = {}
        for size in size_names:
            share_final = final_shares.get(size, 0.0)
            results[size] = SizeDemandResult(
                my_size=size,
                sales_90d=size_sales.get(size, 0),
                share_anchor=anchor_shares.get(size, 0.0),
                share_data=data_shares.get(size, 0.0),
                share_final=share_final,
                d_size=d_final * share_final,
                is_partial_oos=(size in partial_oos_sizes)
            )

        return results

    def _apply_size_guardrails(
        self,
        shares: dict[str, float]
    ) -> dict[str, float]:
        """Apply 3%/40% guardrails and renormalize."""
        cfg = self.config

        if not shares:
            return {}

        # Apply floor and cap
        adjusted = {}
        for size, share in shares.items():
            if share < cfg.min_size_mix:
                adjusted[size] = cfg.min_size_mix
            elif share > cfg.max_size_mix:
                adjusted[size] = cfg.max_size_mix
            else:
                adjusted[size] = share

        # Renormalize to sum = 1.0
        total = sum(adjusted.values())
        if total > 0:
            return {s: v / total for s, v in adjusted.items()}
        else:
            # Fallback: uniform distribution
            n = len(shares)
            return {s: 1.0 / n for s in shares}

    # =========================================================================
    # Main Estimation Methods
    # =========================================================================

    def estimate_demand(
        self,
        sku_key: str,
        store_codes: Optional[list[str]] = None
    ) -> SKUDemandResult:
        """
        Estimate demand for a single SKU.

        This is the main entry point for single-SKU estimation.
        """
        cutoff = self.cutoff_date
        start_date = cutoff - timedelta(days=self.config.lookback_days)

        result = SKUDemandResult(
            sku_key=sku_key,
            cutoff_date=cutoff,
            calendar_days=self.config.lookback_days
        )

        # Normalize store codes for aggregation
        store_codes_used = self._normalize_store_codes(store_codes, sku_key, start_date, cutoff)
        result.store_codes = store_codes_used
        if store_codes is None:
            result.store_aggregation_mode = "ALL"
        elif len(store_codes_used) <= 1:
            result.store_aggregation_mode = "SINGLE"
        else:
            result.store_aggregation_mode = "FILTERED"

        # Check for anchor data
        anchor = self.anchor_data.get(sku_key)
        result.has_anchor = anchor is not None

        if anchor:
            result.d_anchor = anchor.d_active
            result.sigma_anchor = anchor.sigma
        else:
            result.warnings.append("No anchor data - using data only")

        # Build coverage mask
        coverage = self._build_coverage_mask(sku_key, start_date, cutoff, store_codes_used)

        # Coverage metrics
        result.sales_coverage_days = len([c for c in coverage if c.sku_sales > 0])
        result.stock_coverage_days = len([c for c in coverage if c.sku_stock is not None])
        result.eligible_days = len([c for c in coverage if c.is_valid])
        result.unknown_days = max(0, result.calendar_days - result.eligible_days)
        result.availability_score = (
            result.eligible_days / result.calendar_days if result.calendar_days else 0.0
        )

        # Detect OOS
        oos_type, oos_total, oos_streak, _ = self._detect_oos(coverage)
        result.oos_type = oos_type
        result.oos_days_total = oos_total
        result.oos_extended_streak = oos_streak

        # Get current stock for zero-stock detection (Rule 2)
        size_current_stock = {}
        try:
            from core.db.queries import get_size_current_stock
            store_for_stock = store_codes_used[0] if store_codes_used else "UNIVERSAL"
            size_current_stock = get_size_current_stock(sku_key, store_for_stock, self.db_path)
        except Exception:
            pass  # Graceful degradation if stock data unavailable

        # Detect partial OOS at size level (Rule 1: sales drift, Rule 2: zero stock)
        partial_oos = self._detect_partial_oos(
            sku_key, anchor, start_date, cutoff, store_codes_used,
            size_current_stock=size_current_stock
        )
        result.partial_oos_sizes = partial_oos
        if partial_oos:
            result.oos_type = OOSType.PARTIAL if result.oos_type == OOSType.NONE else result.oos_type

        # Store suppression severity for anchor weight calculation
        result.suppression_count = len(partial_oos)

        if partial_oos:
            result.warnings.append(
                f"SIZE_SUPPRESSION: {len(partial_oos)} sizes >=30% below anchor share: {partial_oos}"
            )

        # Calculate data-driven demand
        d_data, good_days = self._calc_d_data(coverage)
        result.d_data = d_data
        result.good_days = good_days
        result.coverage_pct = good_days / len(coverage) if coverage else 0

        # Calculate data-driven sigma
        result.sigma_data = self._calc_sigma_data(coverage)

        # Calculate confidence and weight
        sales_days = len([c for c in coverage if c.sku_sales > 0])
        result.confidence = self._calc_confidence(sales_days, result.oos_type)
        result.anchor_weight = self._calc_blend_weight(
            result.confidence, result.oos_type, result.has_anchor,
            d_anchor=result.d_anchor, d_data=result.d_data,
            suppression_count=result.suppression_count
        )

        # Blend demand
        result.d_final = self._blend_demand(
            result.d_anchor, result.d_data, result.anchor_weight
        )

        # Blend sigma
        if result.has_anchor and result.sigma_anchor > 0:
            result.sigma_final = (
                result.anchor_weight * result.sigma_anchor +
                (1 - result.anchor_weight) * result.sigma_data
            )
        else:
            result.sigma_final = result.sigma_data

        # Calculate size-level results
        result.size_results = self._calc_size_shares(
            sku_key, anchor, result.d_final, result.anchor_weight,
            partial_oos, start_date, cutoff, store_codes_used
        )

        # Validate size shares sum to 1
        if result.size_results:
            share_sum = sum(r.share_final for r in result.size_results.values())
            if abs(share_sum - 1.0) > 0.01:
                result.warnings.append(f"Size shares sum to {share_sum:.3f}, not 1.0")

        return result

    def estimate_all(
        self,
        store_codes: Optional[list[str]] = None
    ) -> tuple[list[SKUDemandResult], list[dict]]:
        """
        Estimate demand for all active SKUs.

        Returns:
            Tuple of (successful_estimates, skipped_skus)
        """
        from core.db.queries import get_active_sku_keys, get_sku_sizes

        # Get all active SKUs
        sku_keys = get_active_sku_keys(self.db_path)

        results: list[SKUDemandResult] = []
        skipped: list[dict] = []

        for sku_key in sku_keys:
            # Check if SKU has sizes defined
            sizes = get_sku_sizes(sku_key, self.db_path)
            if not sizes:
                skipped.append({
                    "sku_key": sku_key,
                    "reason": "NO_SIZES",
                    "details": "No sizes defined in dim_sku_size"
                })
                continue

            # Estimate demand
            try:
                result = self.estimate_demand(sku_key, store_codes)

                # Check for skip conditions
                if result.d_final <= 0 and not result.has_anchor:
                    skipped.append({
                        "sku_key": sku_key,
                        "reason": "NO_DEMAND_NO_ANCHOR",
                        "details": "Zero demand and no anchor data"
                    })
                    continue

                results.append(result)

            except Exception as e:
                skipped.append({
                    "sku_key": sku_key,
                    "reason": "ERROR",
                    "details": str(e)
                })

        return results, skipped

    # =========================================================================
    # Diagnostics Export
    # =========================================================================

    def export_diagnostics(
        self,
        results: list[SKUDemandResult],
        output_path: Path
    ) -> None:
        """Export diagnostic CSV with all intermediate values."""
        rows = []
        for r in results:
            row = {
                "sku_key": r.sku_key,
                "cutoff_date": r.cutoff_date.isoformat(),
                "calendar_days": r.calendar_days,
                "sales_coverage_days": r.sales_coverage_days,
                "stock_coverage_days": r.stock_coverage_days,
                "eligible_days": r.eligible_days,
                "unknown_days": r.unknown_days,
                "good_days": r.good_days,
                "coverage_pct": round(r.coverage_pct, 3),
                "availability_score": round(r.availability_score, 3),
                "d_anchor": round(r.d_anchor, 2),
                "d_data": round(r.d_data, 2),
                "d_final": round(r.d_final, 2),
                "sigma_anchor": round(r.sigma_anchor, 2),
                "sigma_data": round(r.sigma_data, 2),
                "sigma_final": round(r.sigma_final, 2),
                "confidence": r.confidence.value,
                "anchor_weight": round(r.anchor_weight, 2),
                "has_anchor": r.has_anchor,
                "oos_type": r.oos_type.value,
                "oos_days_total": r.oos_days_total,
                "oos_extended_streak": r.oos_extended_streak,
                "partial_oos_sizes": ",".join(r.partial_oos_sizes),
                "suppression_count": r.suppression_count,
                "store_codes": ",".join(r.store_codes),
                "store_aggregation_mode": r.store_aggregation_mode,
                "warnings": "; ".join(r.warnings),
                "skip_reason": r.skip_reason or "",
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)
