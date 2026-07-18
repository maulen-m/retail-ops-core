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
    ingest_sales_to_fact_sales,
    get_unmapped_offers,
    update_returns_from_api,
    normalize_store_code,
    resolve_sales_identity,
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            idempotency_key TEXT,
            kaspi_article TEXT,
            line_identity_key TEXT
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX ux_stock_ledger_idempotency_key "
        "ON stock_ledger(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )

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
            kaspi_article TEXT,
            line_identity_key TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX ux_sales_fact_v2_order_store_article "
        "ON sales_fact_v2 (order_id, UPPER(TRIM(store_code)), "
        "UPPER(TRIM(kaspi_article))) "
        "WHERE TRIM(COALESCE(kaspi_article, '')) <> ''"
    )

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

    def test_parse_fills_blank_english_cells_from_russian_source_columns(self, tmp_path):
        """Mixed CRM rows keep English formulas, but raw Russian cells can be the only populated source."""
        data = {
            "OrderID": [""],
            "Date": [""],
            "KASPI_OFFER_NAME": [""],
            "SKU_ID": ["CL_LINE52_BLACK_M"],
            "SKU_key": ["CL_LINE52_BLACK"],
            "MY_SIZE": ["M"],
            "Quantity": [""],
            "Sell_price_kzt": [""],
            "STORE_NAME": ["Universal"],
            "№ заказа": ["ORD-R-FALLBACK"],
            "Дата поступления заказа": [date(2026, 6, 15)],
            "Название товара в Kaspi Магазине": ["Принт 5в1 черный M"],
            "Количество": [1],
            "Сумма": [15000],
            "Стоимость доставки для продавца": [900],
        }
        xlsx_path = tmp_path / "mixed_blank_formula_cells.xlsx"
        pd.DataFrame(data).to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        records = parse_sales_excel(str(xlsx_path))

        assert len(records) == 1
        assert records[0]["order_id"] == "ORD-R-FALLBACK"
        assert records[0]["order_date"] == date(2026, 6, 15)
        assert records[0]["kaspi_offer_name"] == "Принт 5в1 черный M"
        assert records[0]["quantity"] == 1
        assert records[0]["sell_price_kzt"] == 15000
        assert records[0]["delivery_fee"] == 900

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

    def test_parse_normalizes_dirty_size_tokens(self, tmp_path):
        data = {
            "OrderID": ["ORD-D1", "ORD-D2", "ORD-D3", "ORD-D4"],
            "Date": [date.today(), date.today(), date.today(), date.today()],
            "KASPI_OFFER_NAME": [
                "Принт 5в1 черный 3XL",
                "Рашгард 5 в 1 черный 128",
                "Принт 5в1 черный M",
                "Принт 5в1 черный XL",
            ],
            "SKU_ID": [
                "CL_LINE52_BLACK_3XL",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_26",
                "CL_LINE52_BLACK_M",
                "CL_LINE52_BLACK_XL",
            ],
            "SKU_key": [
                "CL_LINE52_BLACK",
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "CL_LINE52_BLACK",
                "CL_LINE52_BLACK",
            ],
            "MY_SIZE": ["3XL?", "26.0", "М", "NAN"],
            "Quantity": [1, 1, 1, 1],
            "Sell_price_kzt": [15000, 9000, 15000, 15000],
            "STORE_NAME": ["Universal", "Universal", "Universal", "Universal"],
            "Return": [0, 0, 0, 0],
        }
        df = pd.DataFrame(data)
        xlsx_path = tmp_path / "dirty_size.xlsx"
        df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

        records = parse_sales_excel(str(xlsx_path))
        assert [r["my_size"] for r in records] == ["3XL", "26", "M", "XL"]


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

    def test_ingest_same_order_same_offer_different_size_fails_closed_without_articles(
        self, test_db, tmp_path
    ):
        """An unproven size correction must not create a second sale line."""
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

        assert result["inserted"] == 1
        assert result["skipped"] == 1
        assert len(result["lifecycle_conflicts"]) == 1
        with sqlite3.connect(test_db) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM sales_fact_v2 WHERE order_id='ORD-SIZE'"
            ).fetchone()[0] == 1

    def test_ingest_same_display_offer_preserves_distinct_source_articles(
        self, test_db, tmp_path
    ):
        """Distinct exact Kaspi articles prove a genuine multi-line order."""
        data = {
            "OrderID": ["ORD-MULTI-ARTICLE", "ORD-MULTI-ARTICLE"],
            "Date": [date.today(), date.today()],
            "KASPI_OFFER_NAME": ["Shared display name", "Shared display name"],
            "Kaspi_article": ["ARTICLE-M", "ARTICLE-L"],
            "SKU_ID": ["CL_LINE52_BLACK_M", "CL_LINE52_BLACK_L"],
            "SKU_key": ["CL_LINE52_BLACK", "CL_LINE52_BLACK"],
            "MY_SIZE": ["M", "L"],
            "Quantity": [1, 1],
            "Sell_price_kzt": [15000, 15000],
            "STORE_NAME": ["Universal", "Universal"],
            "Return": [0, 0],
        }
        xlsx_path = tmp_path / "same_offer_distinct_articles.xlsx"
        pd.DataFrame(data).to_excel(
            xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False
        )

        result = ingest_sales(xlsx_path=str(xlsx_path), db_path=test_db)

        assert result["inserted"] == 2
        assert result["lifecycle_conflicts"] == []
        with sqlite3.connect(test_db) as conn:
            rows = conn.execute(
                "SELECT kaspi_article, line_identity_key FROM sales_fact_v2 "
                "WHERE order_id='ORD-MULTI-ARTICLE' ORDER BY kaspi_article"
            ).fetchall()
            ledger_rows = conn.execute(
                "SELECT kaspi_article, line_identity_key FROM stock_ledger "
                "WHERE reference_id='ORD-MULTI-ARTICLE' ORDER BY kaspi_article"
            ).fetchall()
        assert rows == [
            ("ARTICLE-L", "ARTICLE:ARTICLE-L"),
            ("ARTICLE-M", "ARTICLE:ARTICLE-M"),
        ]
        assert ledger_rows == rows

    def test_separate_batches_preserve_distinct_articles_with_same_display_offer(
        self, test_db, tmp_path
    ):
        def _write(path: Path, article: str, sku_id: str, size: str) -> None:
            pd.DataFrame(
                {
                    "OrderID": ["ORD-SEPARATE-ARTICLE"],
                    "Date": [date.today()],
                    "KASPI_OFFER_NAME": ["Shared display name"],
                    "Kaspi_article": [article],
                    "SKU_ID": [sku_id],
                    "SKU_key": ["CL_LINE52_BLACK"],
                    "MY_SIZE": [size],
                    "Quantity": [1],
                    "Sell_price_kzt": [15000],
                    "STORE_NAME": ["Universal"],
                    "Return": [0],
                }
            ).to_excel(path, sheet_name="SALES_KSP_CRM_1", index=False)

        first_path = tmp_path / "first_article.xlsx"
        second_path = tmp_path / "second_article.xlsx"
        _write(first_path, "ARTICLE-M", "CL_LINE52_BLACK_M", "M")
        _write(second_path, "ARTICLE-L", "CL_LINE52_BLACK_L", "L")

        first = ingest_sales(xlsx_path=str(first_path), db_path=test_db)
        second = ingest_sales(xlsx_path=str(second_path), db_path=test_db)

        assert first["inserted"] == 1
        assert second["inserted"] == 1
        assert second["lifecycle_conflicts"] == []
        with sqlite3.connect(test_db) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM sales_fact_v2 "
                "WHERE order_id='ORD-SEPARATE-ARTICLE'"
            ).fetchone()[0] == 2

    def test_reingest_distinct_article_batch_fails_closed_on_changed_identity(
        self, test_db, tmp_path
    ):
        first_path = tmp_path / "first_articles.xlsx"
        corrected_path = tmp_path / "corrected_articles.xlsx"
        base = {
            "OrderID": ["ORD-TWO-ARTICLES", "ORD-TWO-ARTICLES"],
            "Date": [date.today(), date.today()],
            "KASPI_OFFER_NAME": ["Shared display name", "Shared display name"],
            "Kaspi_article": ["ARTICLE-M", "ARTICLE-L"],
            "SKU_key": ["CL_LINE52_BLACK", "CL_LINE52_BLACK"],
            "Quantity": [1, 1],
            "Sell_price_kzt": [15000, 15000],
            "STORE_NAME": ["Universal", "Universal"],
            "Return": [0, 0],
        }
        pd.DataFrame(
            {
                **base,
                "SKU_ID": ["CL_LINE52_BLACK_M", "CL_LINE52_BLACK_L"],
                "MY_SIZE": ["M", "L"],
            }
        ).to_excel(first_path, sheet_name="SALES_KSP_CRM_1", index=False)
        pd.DataFrame(
            {
                **base,
                "SKU_ID": ["CL_LINE52_BLACK_M", "CL_LINE52_BLACK_XL"],
                "MY_SIZE": ["M", "XL"],
            }
        ).to_excel(corrected_path, sheet_name="SALES_KSP_CRM_1", index=False)

        first = ingest_sales(xlsx_path=str(first_path), db_path=test_db)
        corrected = ingest_sales(xlsx_path=str(corrected_path), db_path=test_db)

        assert first["inserted"] == 2
        assert corrected["inserted"] == 0
        assert len(corrected["lifecycle_conflicts"]) == 1
        with sqlite3.connect(test_db) as conn:
            rows = conn.execute(
                "SELECT sku_id FROM sales_fact_v2 WHERE order_id='ORD-TWO-ARTICLES' ORDER BY sku_id"
            ).fetchall()
        assert rows == [
            ("CL_LINE52_BLACK_L",),
            ("CL_LINE52_BLACK_M",),
        ]

    def test_reingest_size_correction_does_not_create_second_sales_fact_v2_line(
        self, test_db, tmp_path
    ):
        def _write(path: Path, sku_id: str, size: str) -> None:
            pd.DataFrame(
                {
                    "OrderID": ["ORD-CORRECTION"],
                    "Date": [date.today()],
                    "KASPI_OFFER_NAME": ["Stable public offer"],
                    "SKU_ID": [sku_id],
                    "SKU_key": ["CL_LINE52_BLACK"],
                    "MY_SIZE": [size],
                    "Quantity": [1],
                    "Sell_price_kzt": [15000],
                    "STORE_NAME": ["Universal"],
                    "Return": [0],
                }
            ).to_excel(path, sheet_name="SALES_KSP_CRM_1", index=False)

        first_path = tmp_path / "first.xlsx"
        corrected_path = tmp_path / "corrected.xlsx"
        _write(first_path, "CL_LINE52_BLACK_M", "M")
        _write(corrected_path, "CL_LINE52_BLACK_L", "L")

        first = ingest_sales(xlsx_path=str(first_path), db_path=test_db)
        corrected = ingest_sales(xlsx_path=str(corrected_path), db_path=test_db)

        assert first["inserted"] == 1
        assert corrected["inserted"] == 0
        assert corrected["skipped"] == 1
        assert len(corrected["lifecycle_conflicts"]) == 1
        with sqlite3.connect(test_db) as conn:
            rows = conn.execute(
                "SELECT sku_id, my_size FROM sales_fact_v2 WHERE order_id='ORD-CORRECTION'"
            ).fetchall()
        assert rows == [("CL_LINE52_BLACK_M", "M")]

    def test_fact_sales_reingest_size_correction_fails_closed(
        self, test_db, tmp_path
    ):
        with sqlite3.connect(test_db) as conn:
            conn.executescript(
                """
                CREATE TABLE dim_sku (
                    sku_key TEXT PRIMARY KEY,
                    base_cost_cny REAL,
                    weight_kg REAL,
                    product_type TEXT,
                    cogs_kzt REAL
                );
                INSERT INTO dim_sku VALUES ('CL_LINE52_BLACK', 47, 0.95, 'CL', NULL);
                CREATE TABLE fact_sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    kaspi_offer_name TEXT,
                    store_code TEXT NOT NULL,
                    order_date TEXT NOT NULL,
                    sku_key TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    my_size TEXT,
                    quantity INTEGER NOT NULL,
                    sell_price_kzt REAL NOT NULL,
                    product_type TEXT NOT NULL,
                    channel TEXT,
                    delivery_fee REAL NOT NULL,
                    net_rev_unit REAL NOT NULL,
                    line_net_rev REAL NOT NULL,
                    cogs_unit REAL NOT NULL,
                    cogs_line REAL NOT NULL,
                    profit_unit REAL NOT NULL,
                    profit_line REAL NOT NULL,
                    channel_code TEXT,
                    kaspi_article TEXT,
                    line_identity_key TEXT
                );
                CREATE UNIQUE INDEX ux_fact_sales_order_store_article
                ON fact_sales (
                    order_id,
                    UPPER(TRIM(store_code)),
                    UPPER(TRIM(kaspi_article))
                )
                WHERE TRIM(COALESCE(kaspi_article, '')) <> '';
                """
            )

        def _write(path: Path, sku_id: str, size: str) -> None:
            pd.DataFrame(
                {
                    "OrderID": ["ORD-FACT-CORRECTION"],
                    "Date": [date.today()],
                    "KASPI_OFFER_NAME": ["Stable fact offer"],
                    "Kaspi_article": ["ARTICLE-FACT-CORRECTION"],
                    "SKU_ID": [sku_id],
                    "SKU_key": ["CL_LINE52_BLACK"],
                    "MY_SIZE": [size],
                    "Quantity": [1],
                    "Sell_price_kzt": [15000],
                    "STORE_NAME": ["Universal"],
                    "Return": [0],
                }
            ).to_excel(path, sheet_name="SALES_KSP_CRM_1", index=False)

        first_path = tmp_path / "fact_first.xlsx"
        corrected_path = tmp_path / "fact_corrected.xlsx"
        _write(first_path, "CL_LINE52_BLACK_M", "M")
        _write(corrected_path, "CL_LINE52_BLACK_L", "L")

        first = ingest_sales_to_fact_sales(
            xlsx_path=str(first_path), db_path=test_db
        )
        corrected = ingest_sales_to_fact_sales(
            xlsx_path=str(corrected_path), db_path=test_db
        )

        assert first["inserted"] == 1
        assert corrected["inserted"] == 0
        assert corrected["skipped"] == 1
        assert len(corrected["lifecycle_conflicts"]) == 1
        with sqlite3.connect(test_db) as conn:
            rows = conn.execute(
                "SELECT sku_id, my_size, kaspi_article, line_identity_key "
                "FROM fact_sales WHERE order_id='ORD-FACT-CORRECTION'"
            ).fetchall()
        assert rows == [
            (
                "CL_LINE52_BLACK_M",
                "M",
                "ARTICLE-FACT-CORRECTION",
                "ARTICLE:ARTICLE-FACT-CORRECTION",
            )
        ]

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

    def test_ingest_does_not_replay_ledger_when_source_rows_are_rebuilt(
        self,
        test_db,
        sample_sales_excel,
    ):
        """Rebuilding sales_fact_v2 must not duplicate established stock events."""
        first = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)
        assert first["ledger_events"] == 4

        conn = sqlite3.connect(str(test_db))
        conn.execute("DELETE FROM sales_fact_v2")
        conn.commit()
        ledger_before = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(qty_change), 0) FROM stock_ledger"
        ).fetchone()
        conn.close()

        replay = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)

        conn = sqlite3.connect(str(test_db))
        ledger_after = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(qty_change), 0) FROM stock_ledger"
        ).fetchone()
        conn.close()
        assert replay["inserted"] == 4
        assert replay["ledger_events"] == 0
        assert ledger_after == ledger_before

    def test_ingest_suppresses_stock_for_active_quarantine_pair(
        self,
        test_db,
        sample_sales_excel,
    ):
        conn = sqlite3.connect(str(test_db))
        conn.execute(
            """
            CREATE TABLE fact_order_entry_header_only_source_gap_quarantine (
                store_code TEXT,
                order_id TEXT,
                publication_exclusion_required INTEGER,
                product_stock_excluded INTEGER,
                active_flag INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO fact_order_entry_header_only_source_gap_quarantine "
            "VALUES ('UNIVERSAL','ORD-001',1,1,1)"
        )
        conn.commit()
        conn.close()

        result = ingest_sales(xlsx_path=sample_sales_excel, db_path=test_db)

        conn = sqlite3.connect(str(test_db))
        quarantined_rows = conn.execute(
            "SELECT COUNT(*) FROM stock_ledger WHERE reference_id='ORD-001'"
        ).fetchone()[0]
        conn.close()
        assert result["ledger_quarantined"] == 1
        assert result["ledger_events"] == 3
        assert quarantined_rows == 0


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


class TestOfferNameIdentityMapping:
    """Tests for persistent offer-name identity overrides before CL fallback."""

    def _create_mapping_table(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE dim_offer_name_identity (
                offer_name TEXT,
                store_code TEXT,
                sku_key TEXT NOT NULL,
                sku_id TEXT NULL,
                my_size TEXT NULL,
                source TEXT,
                decided_at TEXT,
                PRIMARY KEY(offer_name, store_code)
            )
        """)
        conn.commit()
        conn.close()

    def _write_cl_row(
        self,
        tmp_path: Path,
        *,
        offer_name: str,
        sku_id: str = "CL",
        sku_key: str = "CL",
        my_size: str = "M",
    ) -> str:
        data = {
            "OrderID": ["ORD-MAP"],
            "Date": [date(2026, 7, 3)],
            "KASPI_OFFER_NAME": [offer_name],
            "SKU_ID": [sku_id],
            "SKU_key": [sku_key],
            "MY_SIZE": [my_size],
            "Quantity": [1],
            "Sell_price_kzt": [15000],
            "STORE_NAME": ["Universal"],
            "Return": [0],
        }
        xlsx_path = tmp_path / "mapped_cl_sales.xlsx"
        pd.DataFrame(data).to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)
        return str(xlsx_path)

    def _sales_identity(self, db_path: Path) -> tuple[str, str, str]:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT sku_key, sku_id, my_size FROM sales_fact_v2 WHERE order_id='ORD-MAP'"
        ).fetchone()
        conn.close()
        return row

    def test_mapped_offer_name_resolves_full_identity(self, test_db, tmp_path):
        self._create_mapping_table(test_db)
        conn = sqlite3.connect(str(test_db))
        conn.execute(
            """
            INSERT INTO dim_offer_name_identity (
                offer_name, store_code, sku_key, sku_id, my_size, source, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Mapped full offer",
                "UNIVERSAL",
                "CL_LINE52_BLACK",
                "CL_LINE52_BLACK_XL",
                "XL",
                "test",
                "2026-07-03T00:00:00Z",
            ),
        )
        conn.commit()
        conn.close()

        xlsx_path = self._write_cl_row(tmp_path, offer_name="Mapped full offer", my_size="M")
        result = ingest_sales(xlsx_path=xlsx_path, db_path=test_db, apply_to_ledger=False)

        assert result["inserted"] == 1
        assert self._sales_identity(test_db) == ("CL_LINE52_BLACK", "CL_LINE52_BLACK_XL", "XL")

    def test_resolver_uses_store_scoped_mapping_before_cl_fallback(self, test_db):
        self._create_mapping_table(test_db)
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO dim_offer_name_identity (
                offer_name, store_code, sku_key, sku_id, my_size, source, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Mapped direct resolver offer",
                "ACMEWEAR",
                "CL_LINE52_BLACK",
                "CL_LINE52_BLACK_L",
                "L",
                "test",
                "2026-07-03T00:00:00Z",
            ),
        )
        conn.commit()

        assert resolve_sales_identity(
            conn,
            "CL",
            "CL",
            "M",
            "Mapped direct resolver offer",
            "ACMEWEAR",
        ) == ("CL_LINE52_BLACK", "CL_LINE52_BLACK_L", "L")
        assert resolve_sales_identity(
            conn,
            "CL",
            "CL",
            "M",
            "Mapped direct resolver offer",
            "UNIVERSAL",
        ) == ("CL", "CL", "M")
        conn.close()

    def test_unmapped_offer_name_keeps_cl_fallback(self, test_db, tmp_path):
        self._create_mapping_table(test_db)

        xlsx_path = self._write_cl_row(tmp_path, offer_name="Still unknown offer", my_size="L")
        result = ingest_sales(xlsx_path=xlsx_path, db_path=test_db, apply_to_ledger=False)

        assert result["inserted"] == 1
        assert self._sales_identity(test_db) == ("CL", "CL", "L")

    def test_sku_key_only_mapping_does_not_guess_size_identity(self, test_db, tmp_path):
        self._create_mapping_table(test_db)
        conn = sqlite3.connect(str(test_db))
        conn.execute(
            """
            INSERT INTO dim_offer_name_identity (
                offer_name, store_code, sku_key, sku_id, my_size, source, decided_at
            ) VALUES (?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                "Mapped sku key only offer",
                "UNIVERSAL",
                "CL_LINE52_BLACK",
                "test",
                "2026-07-03T00:00:00Z",
            ),
        )
        conn.commit()
        conn.close()

        xlsx_path = self._write_cl_row(tmp_path, offer_name="Mapped sku key only offer", my_size="M")
        result = ingest_sales(xlsx_path=xlsx_path, db_path=test_db, apply_to_ledger=False)

        assert result["inserted"] == 1
        assert self._sales_identity(test_db) == ("CL_LINE52_BLACK", "CL", "M")
