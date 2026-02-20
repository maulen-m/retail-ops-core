"""
Tests for correct data grain after Phase 6.5 rebuild.

Verifies:
- fact_sales uses correct grain (order_id, kaspi_offer_name, sku_id, store_code)
- No duplicate order lines
- Daily aggregates match fact_sales totals
"""
import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"

if not DB_PATH.exists():
    pytest.skip(
        "db/app.db missing; data-grain integration tests require a seeded DB",
        allow_module_level=True,
    )


@pytest.fixture
def conn():
    """Database connection fixture."""
    connection = sqlite3.connect(DB_PATH)
    yield connection
    connection.close()


class TestFactSalesGrain:
    """Verify fact_sales has correct grain and no duplicates."""

    def test_no_duplicate_order_lines(self, conn):
        """Each (order_id, kaspi_offer_name, sku_id, store_code) should be unique."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_id, kaspi_offer_name, sku_id, store_code, COUNT(*) as cnt
            FROM fact_sales
            GROUP BY order_id, kaspi_offer_name, sku_id, store_code
            HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()
        assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate order lines"

    def test_kaspi_offer_name_populated(self, conn):
        """All rows should have kaspi_offer_name."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM fact_sales
            WHERE kaspi_offer_name IS NULL OR kaspi_offer_name = ''
        """)
        null_count = cursor.fetchone()[0]
        assert null_count == 0, f"{null_count} rows missing kaspi_offer_name"

    def test_my_size_populated(self, conn):
        """All rows should have my_size."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM fact_sales
            WHERE my_size IS NULL OR my_size = ''
        """)
        null_count = cursor.fetchone()[0]
        assert null_count == 0, f"{null_count} rows missing my_size"

    def test_record_count_reasonable(self, conn):
        """Total records should be reasonable (post-rebuild ~15,000+)."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fact_sales")
        count = cursor.fetchone()[0]
        # After rebuild: ~15,000+ (depends on CRM growth)
        # Should be significantly less than runaway duplicate counts
        assert count > 10000, f"Expected 10,000+ records, got {count}"
        assert count < 25000, f"Expected < 25,000 records (no ghost records), got {count}"

    def test_total_units_reasonable(self, conn):
        """Total units should be reasonable."""
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity) FROM fact_sales")
        total = cursor.fetchone()[0]
        # Expect ~11,700+ units (depends on dim_sku cost data)
        assert total > 10000, f"Expected 10,000+ units, got {total}"
        assert total < 20000, f"Expected < 20,000 units, got {total}"

    def test_date_range_correct(self, conn):
        """Date range should span Sep 2024 onward."""
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(order_date), MAX(order_date) FROM fact_sales")
        min_date, max_date = cursor.fetchone()
        assert min_date.startswith("2024-09"), f"Expected min date 2024-09-xx, got {min_date}"
        # Max date should be recent (not stale)
        from datetime import date, timedelta
        max_dt = date.fromisoformat(max_date)
        assert max_dt >= (date.today() - timedelta(days=45)), (
            f"Expected max date within last 45 days, got {max_date}"
        )

    def test_all_stores_present(self, conn):
        """Should have data from main stores."""
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT store_code FROM fact_sales ORDER BY store_code")
        stores = [row[0] for row in cursor.fetchall()]
        # At minimum should have UNIVERSAL (the largest store)
        assert "UNIVERSAL" in stores, f"Missing UNIVERSAL store, got: {stores}"

    def test_sku_id_matches_sku_key_size(self, conn):
        """sku_id should align with dim_sku_size mapping for sku_key/my_size."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fs.sku_id, fs.sku_key, fs.my_size,
                   ds.sku_key as dim_sku_key, ds.my_size as dim_my_size
            FROM fact_sales fs
            LEFT JOIN dim_sku_size ds ON fs.sku_id = ds.sku_id
            WHERE ds.sku_id IS NULL
               OR ds.sku_key != fs.sku_key
               OR ds.my_size != fs.my_size
        """)
        mismatches = []
        for row in cursor.fetchall():
            if row[3] is None or row[4] is None:
                mismatches.append(row)
                continue
            if row[1].casefold() != row[3].casefold():
                mismatches.append(row)
                continue
            if row[2].casefold() != row[4].casefold():
                mismatches.append(row)
        assert len(mismatches) == 0, f"{len(mismatches)} rows have sku_id not aligned to dim_sku_size"


class TestDailyAggregates:
    """Verify daily aggregates are consistent with fact_sales."""

    def test_daily_units_match_fact_sales(self, conn):
        """Sum of units in fact_sales_daily should match fact_sales."""
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity) FROM fact_sales")
        fact_total = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(units) FROM fact_sales_daily")
        daily_total = cursor.fetchone()[0]

        assert fact_total == daily_total, f"Mismatch: fact_sales={fact_total}, daily={daily_total}"

    def test_size_units_match_fact_sales(self, conn):
        """Sum of units in fact_sales_daily_size should match fact_sales."""
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(quantity) FROM fact_sales")
        fact_total = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(units) FROM fact_sales_daily_size")
        size_total = cursor.fetchone()[0]

        assert fact_total == size_total, f"Mismatch: fact_sales={fact_total}, size={size_total}"

    def test_daily_revenue_positive(self, conn):
        """Daily revenue should be positive."""
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(revenue) FROM fact_sales_daily")
        total_rev = cursor.fetchone()[0]
        assert total_rev > 0, f"Expected positive revenue, got {total_rev}"

    def test_unique_dates_match(self, conn):
        """Both daily tables should have same date coverage."""
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(DISTINCT order_date) FROM fact_sales")
        fact_dates = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT sale_date) FROM fact_sales_daily")
        daily_dates = cursor.fetchone()[0]

        assert fact_dates == daily_dates, f"Date count mismatch: fact={fact_dates}, daily={daily_dates}"

    def test_daily_size_has_required_columns(self, conn):
        """fact_sales_daily_size should have sku_key and my_size after migration."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(fact_sales_daily_size)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "sku_key" in columns, "Missing sku_key in fact_sales_daily_size"
        assert "my_size" in columns, "Missing my_size in fact_sales_daily_size"


class TestDataIntegrity:
    """Verify referential integrity and data quality."""

    def test_all_skus_exist_in_dim_sku(self, conn):
        """All sku_key values in fact_sales should exist in dim_sku."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT fs.sku_key
            FROM fact_sales fs
            LEFT JOIN dim_sku ds ON fs.sku_key = ds.sku_key
            WHERE ds.sku_key IS NULL
        """)
        orphans = cursor.fetchall()
        assert len(orphans) == 0, f"Found {len(orphans)} orphan sku_keys: {orphans[:5]}"

    def test_all_stores_exist_in_dim_store(self, conn):
        """All store_code values in fact_sales should exist in dim_store."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT fs.store_code
            FROM fact_sales fs
            LEFT JOIN dim_store ds ON fs.store_code = ds.store_code
            WHERE ds.store_code IS NULL
        """)
        orphans = cursor.fetchall()
        assert len(orphans) == 0, f"Found {len(orphans)} orphan store_codes: {orphans}"

    def test_economics_calculated(self, conn):
        """All rows with positive price should have positive economics values."""
        cursor = conn.cursor()
        # Only check rows where sell_price > 0 (zero-price rows may be returns/special orders)
        cursor.execute("""
            SELECT COUNT(*) FROM fact_sales
            WHERE sell_price_kzt > 0 AND (cogs_unit <= 0 OR net_rev_unit <= 0)
        """)
        invalid_count = cursor.fetchone()[0]
        assert invalid_count == 0, f"{invalid_count} rows with invalid economics (price > 0 but cogs/net_rev <= 0)"

    def test_no_future_dates(self, conn):
        """No order dates should be in the future."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM fact_sales
            WHERE order_date > date('now', '+1 day')
        """)
        future_count = cursor.fetchone()[0]
        assert future_count == 0, f"{future_count} rows have future dates"
