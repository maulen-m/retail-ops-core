"""
Business Parameters with Effective Dates

Handles time-varying business parameters like VAT rates and FX rates that change over time.

VAT Schedule:
- VAT = 0.03 (3%) through 2025-12-31
- VAT = 0.04 (4%) from 2026-01-01 onward

FX Rates:
- CNY/KZT, USD/KZT, delivery rate USD/kg
- Stored in dim_fx_rates table (when available) or uses fallback defaults

This module provides effective-dated lookups for parameters that change over time.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Union
import sqlite3

# VAT rate schedule (effective_date: rate)
# Rate applies FROM that date onward until next entry
VAT_SCHEDULE = [
    (date(2026, 1, 1), 0.04),   # 4% from 2026-01-01
    (date(1900, 1, 1), 0.03),   # 3% default (historical)
]


def get_vat_rate(as_of_date: Union[date, datetime, None] = None) -> float:
    """
    Get the VAT rate effective on a given date.

    VAT Schedule:
        - Through 2025-12-31: 3% (0.03)
        - From 2026-01-01:    4% (0.04)

    Args:
        as_of_date: Date to check. If None, uses today's date.
                    Accepts date or datetime objects.

    Returns:
        VAT rate as a decimal (e.g., 0.03 for 3%)

    Examples:
        >>> get_vat_rate(date(2025, 12, 31))
        0.03
        >>> get_vat_rate(date(2026, 1, 1))
        0.04
        >>> get_vat_rate(date(2025, 6, 15))
        0.03
        >>> get_vat_rate(date(2026, 6, 15))
        0.04
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Convert datetime to date if needed
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.date()

    # VAT_SCHEDULE is sorted newest first
    for effective_date, rate in VAT_SCHEDULE:
        if as_of_date >= effective_date:
            return rate

    # Fallback (should never reach here)
    return 0.03


# Export the default/current VAT rate for backwards compatibility
VAT_RATE_CURRENT = get_vat_rate()


# =============================================================================
# FX RATES
# =============================================================================

# Default FX rates (fallback when no DB data available)
# These match the historical values used in the codebase
DEFAULT_FX_RATES = {
    "cny_kzt": 78.0,        # CNY to KZT exchange rate
    "usd_kzt": 530.0,       # USD to KZT exchange rate
    "dlv_rate_usd_kg": 2.66  # Delivery rate in USD per kg (volumetric factor)
}

# Database path (relative to project root)
_DB_PATH = Path(__file__).parent.parent.parent / "db" / "app.db"


@dataclass(frozen=True)
class FXRates:
    """
    Immutable FX rates snapshot.

    Attributes:
        cny_kzt: CNY to KZT exchange rate
        usd_kzt: USD to KZT exchange rate
        dlv_rate_usd_kg: Delivery rate in USD per kg
        effective_date: Date these rates are effective from
        source: Where the rates came from (DB, FALLBACK)
    """
    cny_kzt: float
    usd_kzt: float
    dlv_rate_usd_kg: float
    effective_date: Optional[date] = None
    source: str = "FALLBACK"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "cny_kzt": self.cny_kzt,
            "usd_kzt": self.usd_kzt,
            "dlv_rate_usd_kg": self.dlv_rate_usd_kg,
        }


def get_fx_rates(
    as_of_date: Union[date, datetime, None] = None,
    db_path: Union[str, Path, None] = None
) -> FXRates:
    """
    Get FX rates effective on a given date.

    Looks up rates from dim_fx_rates table if available, otherwise
    returns fallback defaults.

    Args:
        as_of_date: Date to check. If None, uses today's date.
        db_path: Optional path to database. Defaults to db/app.db.

    Returns:
        FXRates dataclass with cny_kzt, usd_kzt, dlv_rate_usd_kg

    Examples:
        >>> rates = get_fx_rates()
        >>> rates.cny_kzt
        78.0
        >>> rates.to_dict()
        {'cny_kzt': 78.0, 'usd_kzt': 530.0, 'dlv_rate_usd_kg': 2.66}
    """
    if as_of_date is None:
        as_of_date = date.today()

    # Convert datetime to date if needed
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.date()

    # Determine database path
    if db_path is None:
        db_path = _DB_PATH

    db_path = Path(db_path)

    # Try to get from database
    if db_path.exists():
        try:
            rates = _get_fx_rates_from_db(db_path, as_of_date)
            if rates:
                return rates
        except Exception:
            # Fall through to defaults on any DB error
            pass

    # Return defaults
    return FXRates(
        cny_kzt=DEFAULT_FX_RATES["cny_kzt"],
        usd_kzt=DEFAULT_FX_RATES["usd_kzt"],
        dlv_rate_usd_kg=DEFAULT_FX_RATES["dlv_rate_usd_kg"],
        effective_date=None,
        source="FALLBACK"
    )


def _get_fx_rates_from_db(db_path: Path, as_of_date: date) -> Optional[FXRates]:
    """
    Query dim_fx_rates for rates effective on as_of_date.

    Returns the most recent rates where effective_date <= as_of_date.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='dim_fx_rates'
        """)
        if not cursor.fetchone():
            return None

        # Get most recent rates before or on as_of_date
        cursor.execute("""
            SELECT effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg, source
            FROM dim_fx_rates
            WHERE effective_date <= ?
            ORDER BY effective_date DESC
            LIMIT 1
        """, (as_of_date.isoformat(),))

        row = cursor.fetchone()
        if row:
            eff_date_str, cny_kzt, usd_kzt, dlv_rate, source = row
            eff_date = date.fromisoformat(eff_date_str) if eff_date_str else None
            return FXRates(
                cny_kzt=cny_kzt,
                usd_kzt=usd_kzt,
                dlv_rate_usd_kg=dlv_rate,
                effective_date=eff_date,
                source=source or "DB"
            )
        return None
    finally:
        conn.close()


def set_fx_rates(
    cny_kzt: float,
    usd_kzt: float,
    dlv_rate_usd_kg: float,
    effective_date: Union[date, datetime, None] = None,
    source: str = "MANUAL",
    db_path: Union[str, Path, None] = None
) -> None:
    """
    Insert or update FX rates in dim_fx_rates table.

    Args:
        cny_kzt: CNY to KZT exchange rate
        usd_kzt: USD to KZT exchange rate
        dlv_rate_usd_kg: Delivery rate in USD per kg
        effective_date: Date these rates are effective from. Defaults to today.
        source: Source of the rates (e.g., 'MANUAL', 'API', 'IMPORT')
        db_path: Optional path to database. Defaults to db/app.db.
    """
    if effective_date is None:
        effective_date = date.today()

    if isinstance(effective_date, datetime):
        effective_date = effective_date.date()

    if db_path is None:
        db_path = _DB_PATH

    db_path = Path(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_fx_rates (
                effective_date TEXT PRIMARY KEY,
                cny_kzt REAL NOT NULL,
                usd_kzt REAL NOT NULL,
                dlv_rate_usd_kg REAL NOT NULL,
                source TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Insert or replace
        cursor.execute("""
            INSERT OR REPLACE INTO dim_fx_rates
            (effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg, source, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (effective_date.isoformat(), cny_kzt, usd_kzt, dlv_rate_usd_kg, source))

        conn.commit()
    finally:
        conn.close()


# =============================================================================
# DEMAND OVERRIDES
# =============================================================================

def _normalize_date(value: Union[str, date, None]) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Unsupported date value: {value}")


def get_demand_overrides(
    as_of_date: Union[str, date, None] = None,
    db_path: Union[str, Path, None] = None
) -> dict[str, float]:
    """
    Get active demand overrides from dim_demand_overrides table.

    Returns a dict mapping sku_key -> d_override for active overrides.
    Active if start_date <= as_of_date < end_date (and active_flag=1).
    If multiple active windows exist, the latest start_date wins.
    Falls back to empty dict if table doesn't exist or is empty.

    Args:
        as_of_date: Date to evaluate overrides. Defaults to today.
        db_path: Optional path to database. Defaults to db/app.db.

    Returns:
        Dict of sku_key -> d_override (daily demand override)

    Example:
        >>> overrides = get_demand_overrides()
        >>> overrides.get("CL_OC_MEN_LINE52_BLACK", None)
        50.0
    """
    if db_path is None:
        db_path = _DB_PATH

    db_path = Path(db_path)

    if not db_path.exists():
        return {}

    as_of = _normalize_date(as_of_date) or date.today()
    as_of_iso = as_of.isoformat()

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='dim_demand_overrides'
        """)
        if not cursor.fetchone():
            conn.close()
            return {}

        # Detect date columns (for backwards compatibility)
        cursor.execute("PRAGMA table_info(dim_demand_overrides)")
        columns = {row[1] for row in cursor.fetchall()}
        has_dates = "start_date" in columns and "end_date" in columns

        if has_dates:
            cursor.execute("""
                SELECT sku_key, d_override, start_date
                FROM dim_demand_overrides
                WHERE active_flag = 1
                  AND (start_date IS NULL OR start_date <= ?)
                  AND (end_date IS NULL OR end_date > ?)
                ORDER BY start_date DESC
            """, (as_of_iso, as_of_iso))
        else:
            cursor.execute("""
                SELECT sku_key, d_override, NULL as start_date
                FROM dim_demand_overrides
                WHERE active_flag = 1
            """)

        result = {}
        for sku_key, d_override, _ in cursor.fetchall():
            if sku_key not in result:
                result[sku_key] = d_override
        conn.close()
        return result

    except Exception:
        return {}


def set_demand_override(
    sku_key: str,
    d_override: float,
    start_date: Union[str, date, None] = None,
    end_date: Union[str, date, None] = None,
    reason: str = "",
    source: str = "MANUAL",
    active_flag: int = 1,
    db_path: Union[str, Path, None] = None
) -> None:
    """
    Insert or update a demand override in dim_demand_overrides table.
    Multi-window overrides are supported via (sku_key, start_date, end_date).

    Args:
        sku_key: SKU key to override (e.g., "CL_OC_MEN_LINE52_BLACK")
        d_override: Daily demand override value
        start_date: Start date (inclusive). Defaults to today.
        end_date: End date (exclusive). Defaults to far future.
        reason: Reason for override (e.g., "Seasonal adjustment", "Launch period")
        source: Source of override (MANUAL, IMPORT, SEASONAL)
        active_flag: 1 = active, 0 = disabled
        db_path: Optional path to database. Defaults to db/app.db.
    """
    if db_path is None:
        db_path = _DB_PATH

    db_path = Path(db_path)

    start = _normalize_date(start_date) or date.today()
    end = _normalize_date(end_date) or date(9999, 12, 31)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Ensure table exists (multi-window schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dim_demand_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_key TEXT NOT NULL,
                d_override REAL NOT NULL,
                start_date TEXT,
                end_date TEXT,
                reason TEXT,
                source TEXT,
                active_flag INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Backfill/migrate older schemas if id column missing
        cursor.execute("PRAGMA table_info(dim_demand_overrides)")
        existing = {row[1] for row in cursor.fetchall()}
        if "id" not in existing:
            has_start = "start_date" in existing
            has_end = "end_date" in existing
            has_reason = "reason" in existing
            has_source = "source" in existing
            has_active = "active_flag" in existing
            has_created = "created_at" in existing
            has_updated = "updated_at" in existing
            cursor.execute("""
                CREATE TABLE dim_demand_overrides_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_key TEXT NOT NULL,
                    d_override REAL NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    reason TEXT,
                    source TEXT,
                    active_flag INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            cursor.execute(f"""
                INSERT INTO dim_demand_overrides_v2
                (sku_key, d_override, start_date, end_date, reason, source, active_flag, created_at, updated_at)
                SELECT
                    sku_key,
                    d_override,
                    {"start_date" if has_start else "NULL"} as start_date,
                    {"end_date" if has_end else "NULL"} as end_date,
                    {"reason" if has_reason else "NULL"} as reason,
                    {"source" if has_source else "NULL"} as source,
                    {"active_flag" if has_active else "1"} as active_flag,
                    {"created_at" if has_created else "datetime('now')"} as created_at,
                    {"updated_at" if has_updated else "datetime('now')"} as updated_at
                FROM dim_demand_overrides
            """)
            cursor.execute("DROP TABLE dim_demand_overrides")
            cursor.execute("ALTER TABLE dim_demand_overrides_v2 RENAME TO dim_demand_overrides")

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_demand_overrides_window "
            "ON dim_demand_overrides(sku_key, start_date, end_date)"
        )

        # Preserve created_at if record exists for same window
        cursor.execute(
            """
            SELECT created_at FROM dim_demand_overrides
            WHERE sku_key = ? AND start_date = ? AND end_date = ?
            """,
            (sku_key, start.isoformat(), end.isoformat())
        )
        row = cursor.fetchone()
        created_at = row[0] if row and row[0] else None

        cursor.execute("""
            INSERT INTO dim_demand_overrides
            (sku_key, d_override, start_date, end_date, reason, source, active_flag, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), datetime('now'))
            ON CONFLICT(sku_key, start_date, end_date) DO UPDATE SET
                d_override = excluded.d_override,
                reason = excluded.reason,
                source = excluded.source,
                active_flag = excluded.active_flag,
                updated_at = excluded.updated_at
        """, (
            sku_key,
            d_override,
            start.isoformat(),
            end.isoformat(),
            reason,
            source,
            active_flag,
            created_at,
        ))

        conn.commit()
    finally:
        conn.close()


def delete_demand_override(
    sku_key: str,
    db_path: Union[str, Path, None] = None
) -> bool:
    """
    Delete a demand override (or set active_flag=0 to disable).

    Args:
        sku_key: SKU key to delete
        db_path: Optional path to database.

    Returns:
        True if override was deleted, False if not found
    """
    if db_path is None:
        db_path = _DB_PATH

    db_path = Path(db_path)

    if not db_path.exists():
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM dim_demand_overrides WHERE sku_key = ?
        """, (sku_key,))

        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


if __name__ == "__main__":
    # Test boundary dates
    print("VAT Rate Schedule Tests")
    print("=" * 50)

    test_dates = [
        (date(2025, 1, 1), 0.03, "2025-01-01 (mid 3% period)"),
        (date(2025, 12, 30), 0.03, "2025-12-30 (day before boundary)"),
        (date(2025, 12, 31), 0.03, "2025-12-31 (last day of 3%)"),
        (date(2026, 1, 1), 0.04, "2026-01-01 (first day of 4%)"),
        (date(2026, 1, 2), 0.04, "2026-01-02 (day after boundary)"),
        (date(2026, 6, 15), 0.04, "2026-06-15 (mid 4% period)"),
    ]

    all_pass = True
    for test_date, expected, description in test_dates:
        actual = get_vat_rate(test_date)
        passed = actual == expected
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {description}: {actual} (expected {expected})")
        if not passed:
            all_pass = False

    print()
    print(f"Current VAT rate (today): {get_vat_rate()}")
    print(f"Overall: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
