"""
TASK-176: Tests for Sales Ingestion Module (Phase 10)

Tests the sales ingestion functions in core/ingest/sales_ingest.py.

12 tests covering:
- Excel parsing (English and Russian columns)
- Sales insertion and deduplication
- Ledger event creation
- Return handling
- Unmapped offer tracking
- Idempotency
"""

import pytest
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os

import pandas as pd

from core.ingest.sales_ingest import (
    parse_sales_excel,
    ingest_sales,
    get_unmapped_offers,
    update_returns_from_api,
    normalize_store_code,
)
from core.db.ledger import get_stock_balance, get_ledger_events


@pytest.fixture
def test_db():
    """Create a temporary database with required schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create stock_ledger table
    conn.execute("""
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date DATE NOT NULL,
            event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            qty_change INTEGER NOT NULL,
            running_balance INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT DEFAULT 'SYSTEM',
            created_by TEXT DEFAULT 'system',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create sales_fact_v2 table
    conn.execute("""
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT DEFAULT 'UNIVERSAL',
            quantity INTEGER DEFAULT 1,
            sell_price_kzt REAL,
            delivery_fee REAL,
            net_rev REAL,
            status TEXT DEFAULT 'DELIVERED',
            return_flag INTEGER DEFAULT 0,
            return_date DATE,
            api_updated_at DATETIME,
            source_file TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        )
    """)

    # Create fact_input_audit table
    conn.execute("""
        CREATE TABLE fact_input_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            change_type TEXT DEFAULT 'UPDATE',
            source TEXT DEFAULT 'SYSTEM',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create dim_sku_size table
    conn.execute("""
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            size_order INTEGER
        )
    """)

    # Seed dim_sku_size with test data
    test_sizes = [
        ("CL_LINE52_BLACK_S", "CL_LINE52_BLACK", "S", 1),
        ("CL_LINE52_BLACK_M", "CL_LINE52_BLACK", "M", 2),
        ("CL_LINE52_BLACK_L", "CL_LINE52_BLACK", "L", 3),
        ("CL_LINE52_BLACK_XL", "CL_LINE52_BLACK", "XL", 4),
        ("CL_BERSERK_BLACK_M", "CL_BERSERK_BLACK", "M", 2),
        ("CL_BERSERK_BLACK_L", "CL_BERSERK_BLACK", "L", 3),
    ]
    conn.executemany("""
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
        VALUES (?, ?, ?, ?)
    """, test_sizes)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_sales_excel(tmp_path):
    """Create a sample sales Excel file with English columns."""
    data = {
        "OrderID": ["ORD-001", "ORD-002", "ORD-003", "ORD-004"],
        "Date": [date.today() - timedelta(days=i) for i in range(4)],
        "KASPI_OFFER_NAME": [
            "Принт 5в1 черный M",
            "Принт 5в1 черный L",
            "Берсерк черный M",
            "Берсерк черный L",
        ],
        "SKU_ID": [
            "CL_LINE52_BLACK_M",
            "CL_LINE52_BLACK_L",
            "CL_BERSERK_BLACK_M",
            "CL_BERSERK_BLACK_L",
        ],
        "SKU_key": [
            "CL_LINE52_BLACK",
            "CL_LINE52_BLACK",
            "CL_BERSERK_BLACK",
            "CL_BERSERK_BLACK",
        ],
        "MY_SIZE": ["M", "L", "M", "L"],
        "Quantity": [1, 2, 1, 1],
        "Sell_price_kzt": [15000, 30000, 18000, 18000],
        "STORE_NAME": ["Universal", "Universal", "AcmeWear", "AcmeWear"],
        "Return": [0, 0, 0, 0],
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "test_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


@pytest.fixture
def russian_columns_excel(tmp_path):
    """Create a sample sales Excel file with Russian columns."""
    data = {
        "№ заказа": ["ORD-R01", "ORD-R02"],
        "Дата поступления заказа": [date.today() - timedelta(days=i) for i in range(2)],
        "Название товара в Kaspi Магазине": [
            "Принт 5в1 черный S",
            "Берсерк черный L",
        ],
        "SKU_ID": ["CL_LINE52_BLACK_S", "CL_BERSERK_BLACK_L"],
        "SKU_key": ["CL_LINE52_BLACK", "CL_BERSERK_BLACK"],
        "MY_SIZE": ["S", "L"],
        "Количество": [1, 1],
        "Сумма": [15000, 18000],
        "STORE_NAME": ["Universal", "AcmeWear"],
        "Return": [0, 0],
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "russian_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


@pytest.fixture
def delivery_fee_excel(tmp_path):
    """Create a sample sales Excel file with delivery fee columns."""
    data = {
        "OrderID": ["ORD-D01"],
        "Date": [date.today()],
        "KASPI_OFFER_NAME": ["Принт 5в1 черный M"],
        "SKU_ID": ["CL_LINE52_BLACK_M"],
        "SKU_key": ["CL_LINE52_BLACK"],
        "MY_SIZE": ["M"],
        "Quantity": [1],
        "Sell_price_kzt": [15000],
        "STORE_NAME": ["Universal"],
        "Delivery_fee_kzt": [100],
        "Стоимость доставки для продавца": [200],
        "Стоимость доставки для покупателя": [300],
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "delivery_fee_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


@pytest.fixture
def missing_sku_id_excel(tmp_path):
    """Sales Excel missing SKU_ID but with SKU_key + MY_SIZE."""
    data = {
        "OrderID": ["ORD-NO-SKUID"],
        "Date": [date.today()],
        "KASPI_OFFER_NAME": ["Принт 5в1 черный M"],
        "SKU_key": ["CL_LINE52_BLACK"],
        "MY_SIZE": ["M"],
        "Quantity": [1],
        "Sell_price_kzt": [15000],
        "STORE_NAME": ["Universal"],
        "Return": [0],
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "missing_sku_id.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


@pytest.fixture
def unmapped_sales_excel(tmp_path):
    """Create a sample sales Excel file with unmapped offers."""
    data = {
        "OrderID": ["ORD-U01", "ORD-U02", "ORD-U03"],
        "Date": [date.today() for _ in range(3)],
        "KASPI_OFFER_NAME": [
            "Принт 5в1 черный M",
            "Unknown Product 1",
            "Unknown Product 1",
        ],
        "SKU_ID": [
            "CL_LINE52_BLACK_M",
            None,  # Unmapped
            None,  # Unmapped - same offer
        ],
        "SKU_key": ["CL_LINE52_BLACK", None, None],
        "MY_SIZE": ["M", None, None],
        "Quantity": [1, 1, 1],
        "Sell_price_kzt": [15000, 10000, 10000],
        "STORE_NAME": ["Universal", "Universal", "Universal"],
        "Return": [0, 0, 0],
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "unmapped_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


@pytest.fixture
def return_sales_excel(tmp_path):
    """Create a sample sales Excel file with returns."""
    data = {
        "OrderID": ["ORD-RET01", "ORD-RET02"],
        "Date": [date.today() - timedelta(days=5), date.today()],
        "KASPI_OFFER_NAME": [
            "Принт 5в1 черный M",
            "Берсерк черный L",
        ],
        "SKU_ID": ["CL_LINE52_BLACK_M", "CL_BERSERK_BLACK_L"],
        "SKU_key": ["CL_LINE52_BLACK", "CL_BERSERK_BLACK"],
        "MY_SIZE": ["M", "L"],
        "Quantity": [1, 2],
        "Sell_price_kzt": [15000, 36000],
        "STORE_NAME": ["Universal", "Universal"],
        "Return": [1, 0],  # First is a return
    }
    df = pd.DataFrame(data)
    xlsx_path = tmp_path / "return_sales.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
    return str(xlsx_path)


class TestParseSalesExcel:
    """Tests for parse_sales_excel function."""

    def test_parse_sales_excel(self, sample_sales_excel):
        """Test basic parsing of sales Excel file."""
        records = parse_sales_excel(sample_sales_excel)

        assert len(records) == 4
        assert records[0]["order_id"] == "ORD-001"
        assert records[0]["kaspi_offer_name"] == "Принт 5в1 черный M"
        assert records[0]["sku_id"] == "CL_LINE52_BLACK_M"
        assert records[0]["quantity"] == 1
        assert records[0]["store_code"] == "UNIVERSAL"

    def test_parse_handles_russian_columns(self, russian_columns_excel):
        """Test parsing Excel file with Russian column names."""
        records = parse_sales_excel(russian_columns_excel)

        assert len(records) == 2
        assert records[0]["order_id"] == "ORD-R01"
        assert records[0]["kaspi_offer_name"] == "Принт 5в1 черный S"
        assert records[0]["sku_id"] == "CL_LINE52_BLACK_S"
        assert records[1]["store_code"] == "ACMEWEAR"

    def test_parse_prefers_seller_delivery_fee(self, delivery_fee_excel):
        """Seller delivery fee should override legacy column when present."""
        records = parse_sales_excel(delivery_fee_excel)

        assert len(records) == 1
        record = records[0]
        assert record["delivery_fee"] == 200
        assert record["delivery_fee_seller"] == 200
        assert record["delivery_fee_buyer"] == 300

    def test_parse_infers_my_size_from_sku_id(self, tmp_path):
        """Missing MY_SIZE should be inferred from SKU_ID suffix when available."""
        data = {
            "OrderID": ["ORD-MISSING"],
            "Date": [date.today()],
            "KASPI_OFFER_NAME": ["Принт 5в1 черный XL"],
            "SKU_ID": ["CL_LINE52_BLACK_XL"],
            "SKU_key": ["CL_LINE52_BLACK"],
            "MY_SIZE": [""],
            "Quantity": [1],
            "Sell_price_kzt": [15000],
            "STORE_NAME": ["Universal"],
            "Return": [0],
        }
        df = pd.DataFrame(data)
        xlsx_path = tmp_path / "missing_size.xlsx"
        df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        records = parse_sales_excel(str(xlsx_path))
        assert records[0]["my_size"] == "XL"


class TestIngestSales:
    """Tests for ingest_sales function."""

    def test_ingest_new_sales(self, test_db, sample_sales_excel):
        """Test ingesting new sales creates records."""
        result = ingest_sales(
            xlsx_path=sample_sales_excel,
            db_path=test_db,
        )

        assert result["inserted"] == 4
        assert result["skipped"] == 0
        assert len(result["errors"]) == 0

        # Verify records in database
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        sales = conn.execute("SELECT * FROM sales_fact_v2").fetchall()
        conn.close()

        assert len(sales) == 4

    def test_ingest_resolves_missing_sku_id(self, test_db, missing_sku_id_excel):
        """SKU_ID should resolve from SKU_key + MY_SIZE via dim_sku_size."""
        result = ingest_sales(
            xlsx_path=missing_sku_id_excel,
            db_path=test_db,
        )

        assert result["inserted"] == 1
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT sku_id FROM sales_fact_v2").fetchone()
        conn.close()

        assert row["sku_id"] == "CL_LINE52_BLACK_M"

    def test_ingest_dedup_exact_key(self, test_db, sample_sales_excel):
        """Test deduplication on exact key (order_id, store_code, kaspi_offer_name, sku_key, my_size)."""
        # First ingest
        result1 = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)
        assert result1["inserted"] == 4

        # Second ingest - should skip all
        result2 = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)
        assert result2["inserted"] == 0
        assert result2["skipped"] == 4

    def test_ingest_same_order_different_offers(self, test_db, tmp_path):
        """Test same order with different kaspi_offer_name are separate records."""
        data = {
            "OrderID": ["ORD-MULTI", "ORD-MULTI"],
            "Date": [date.today(), date.today()],
            "KASPI_OFFER_NAME": [
                "Принт 5в1 черный M",
                "Берсерк черный M",  # Different offer
            ],
            "SKU_ID": ["CL_LINE52_BLACK_M", "CL_BERSERK_BLACK_M"],
            "SKU_key": ["CL_LINE52_BLACK", "CL_BERSERK_BLACK"],
            "MY_SIZE": ["M", "M"],
            "Quantity": [1, 1],
            "Sell_price_kzt": [15000, 18000],
            "STORE_NAME": ["Universal", "Universal"],
            "Return": [0, 0],
        }
        df = pd.DataFrame(data)
        xlsx_path = tmp_path / "multi_offer.xlsx"
        df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        result = ingest_sales(xlsx_path=str(xlsx_path), db_path=test_db)

        # Both should be inserted (same order, different offers)
        assert result["inserted"] == 2

    def test_ingest_same_order_same_offer_different_size(self, test_db, tmp_path):
        """Test same order, same offer, different size are separate records."""
        data = {
            "OrderID": ["ORD-SIZE", "ORD-SIZE"],
            "Date": [date.today(), date.today()],
            "KASPI_OFFER_NAME": [
                "Принт 5в1 черный",
                "Принт 5в1 черный",  # Same offer name
            ],
            "SKU_ID": ["CL_LINE52_BLACK_M", "CL_LINE52_BLACK_L"],  # Different sizes
            "SKU_key": ["CL_LINE52_BLACK", "CL_LINE52_BLACK"],
            "MY_SIZE": ["M", "L"],
            "Quantity": [1, 1],
            "Sell_price_kzt": [15000, 15000],
            "STORE_NAME": ["Universal", "Universal"],
            "Return": [0, 0],
        }
        df = pd.DataFrame(data)
        xlsx_path = tmp_path / "same_offer_diff_size.xlsx"
        df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        result = ingest_sales(xlsx_path=str(xlsx_path), db_path=test_db)

        # Both should be inserted (same order, same offer, different sku_id)
        assert result["inserted"] == 2

    def test_ingest_creates_sale_events(self, test_db, sample_sales_excel):
        """Test that ingestion creates SALE events in stock_ledger."""
        result = ingest_sales(
            xlsx_path=sample_sales_excel,
            apply_to_ledger=True,
            db_path=test_db,
        )

        assert result["ledger_events"] == 4

        # Check ledger events
        events = get_ledger_events(db_path=test_db, limit=10)
        assert len(events) == 4
        for event in events:
            assert event["event_type"] == "SALE"
            assert event["qty_change"] < 0  # Sales decrease stock

    def test_ingest_return_flag_creates_return_event(self, test_db, return_sales_excel):
        """Test that return_flag=1 creates both SALE and RETURN events."""
        result = ingest_sales(
            xlsx_path=return_sales_excel,
            apply_to_ledger=True,
            db_path=test_db,
        )

        # ORD-RET01 has return_flag=1 -> SALE + RETURN events
        # ORD-RET02 has return_flag=0 -> only SALE event
        assert result["inserted"] == 2
        assert result["returns_processed"] == 1
        assert result["ledger_events"] == 3  # 2 SALEs + 1 RETURN for historical return

        # Verify the return created both events
        events = get_ledger_events(sku_id="CL_LINE52_BLACK_M", db_path=test_db)
        assert len(events) == 2
        event_types = {e["event_type"] for e in events}
        assert event_types == {"SALE", "RETURN"}

    def test_ingest_unmapped_logged(self, test_db, unmapped_sales_excel):
        """Test that unmapped offers are tracked."""
        result = ingest_sales(
            xlsx_path=unmapped_sales_excel,
            db_path=test_db,
        )

        # Should insert 1 (mapped), skip 2 (unmapped)
        assert result["inserted"] == 1
        assert len(result["unmapped"]) == 1
        assert result["unmapped"][0]["offer"] == "Unknown Product 1"

    def test_ingest_idempotent(self, test_db, sample_sales_excel):
        """Test that re-ingesting produces same result."""
        # Ingest three times
        result1 = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)
        result2 = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)
        result3 = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)

        assert result1["inserted"] == 4
        assert result2["inserted"] == 0
        assert result3["inserted"] == 0

        # Database should have exactly 4 records
        conn = sqlite3.connect(str(test_db))
        count = conn.execute("SELECT COUNT(*) FROM sales_fact_v2").fetchone()[0]
        conn.close()
        assert count == 4


class TestUpdateReturnsFromApi:
    """Tests for update_returns_from_api function."""

    def test_ingest_updates_existing_status(self, test_db, sample_sales_excel):
        """Test that API return updates existing sale status."""
        # First ingest the sale
        ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)

        # Now mark as returned via API
        api_returns = [
            {
                "order_id": "ORD-001",
                "sku_id": "CL_LINE52_BLACK_M",
                "store_code": "UNIVERSAL",
            }
        ]
        processed = update_returns_from_api(api_returns, db_path=test_db)

        assert processed == 1

        # Verify the sale was updated
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        sale = conn.execute("""
            SELECT * FROM sales_fact_v2 WHERE order_id = 'ORD-001'
        """).fetchone()
        conn.close()

        assert sale["status"] == "RETURNED"
        assert sale["return_flag"] == 1

    def test_api_return_creates_return_event(self, test_db, sample_sales_excel):
        """Test that API return creates RETURN event in ledger."""
        # Ingest without ledger events initially
        ingest_sales(
            xlsx_path=sample_sales_excel,
            apply_to_ledger=True,
            db_path=test_db,
        )

        # Get initial ledger count
        events_before = get_ledger_events(sku_id="CL_LINE52_BLACK_M", db_path=test_db)
        initial_count = len(events_before)

        # Process return via API
        api_returns = [
            {
                "order_id": "ORD-001",
                "sku_id": "CL_LINE52_BLACK_M",
                "store_code": "UNIVERSAL",
            }
        ]
        update_returns_from_api(api_returns, db_path=test_db)

        # Verify RETURN event was created
        events_after = get_ledger_events(sku_id="CL_LINE52_BLACK_M", db_path=test_db)
        assert len(events_after) == initial_count + 1

        return_events = [e for e in events_after if e["event_type"] == "RETURN"]
        assert len(return_events) == 1
        assert return_events[0]["qty_change"] == 1  # Positive: return adds stock


class TestStockBalance:
    """Tests for stock balance after sales."""

    def test_stock_decreases_after_sale(self, test_db, tmp_path):
        """Test that stock balance decreases after sale."""
        # First add initial stock
        from core.db.ledger import add_ledger_event

        add_ledger_event(
            event_type="INITIAL",
            sku_id="CL_LINE52_BLACK_M",
            qty_change=100,
            event_date=date.today() - timedelta(days=30),
            db_path=test_db,
        )

        # Verify initial balance
        balance_before = get_stock_balance(
            sku_id="CL_LINE52_BLACK_M",
            db_path=test_db,
        )
        assert balance_before == 100

        # Create and ingest a sale
        data = {
            "OrderID": ["ORD-STOCK01"],
            "Date": [date.today()],
            "KASPI_OFFER_NAME": ["Принт 5в1 черный M"],
            "SKU_ID": ["CL_LINE52_BLACK_M"],
            "SKU_key": ["CL_LINE52_BLACK"],
            "MY_SIZE": ["M"],
            "Quantity": [3],
            "Sell_price_kzt": [45000],
            "STORE_NAME": ["Universal"],
            "Return": [0],
        }
        df = pd.DataFrame(data)
        xlsx_path = tmp_path / "stock_test.xlsx"
        df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        ingest_sales(xlsx_path=str(xlsx_path), apply_to_ledger=True, db_path=test_db)

        # Verify stock decreased
        balance_after = get_stock_balance(
            sku_id="CL_LINE52_BLACK_M",
            db_path=test_db,
        )
        assert balance_after == 97  # 100 - 3


class TestNormalizeStoreCode:
    """Tests for store code normalization."""

    def test_normalize_universal(self):
        """Test normalizing 'universal' to 'UNIVERSAL'."""
        assert normalize_store_code("universal") == "UNIVERSAL"
        assert normalize_store_code("Universal") == "UNIVERSAL"
        assert normalize_store_code("UNIVERSAL") == "UNIVERSAL"

    def test_normalize_acmewear(self):
        """Test normalizing 'acmewear' variations."""
        assert normalize_store_code("acmewear") == "ACMEWEAR"
        assert normalize_store_code("AcmeWear") == "ACMEWEAR"

    def test_normalize_store-d(self):
        """Test normalizing 'store-d' variations."""
        assert normalize_store_code("store-d") == "11KZ"
        assert normalize_store_code("11_kz") == "11KZ"
        assert normalize_store_code("11 kz") == "11KZ"

    def test_normalize_empty(self):
        """Test normalizing empty/None values."""
        assert normalize_store_code(None) == "UNIVERSAL"
        assert normalize_store_code("") == "UNIVERSAL"
