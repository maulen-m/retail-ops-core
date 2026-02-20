import sqlite3
from datetime import date
from pathlib import Path

from scripts.backfill_orders_sku_from_sales_v2 import backfill_orders


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            internal_status TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date DATE,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_order(conn, **kwargs) -> None:
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name,
            internal_status, kaspi_status, kaspi_status_detail, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kwargs.get("order_id"),
            kwargs.get("store_code"),
            kwargs.get("sku_key"),
            kwargs.get("sku_id"),
            kwargs.get("my_size"),
            kwargs.get("kaspi_offer_name"),
            kwargs.get("internal_status"),
            kwargs.get("kaspi_status"),
            kwargs.get("kaspi_status_detail"),
            kwargs.get("status_updated_at"),
            kwargs.get("actual_shipment_date"),
            kwargs.get("planned_shipment_date"),
            kwargs.get("created_at"),
            kwargs.get("updated_at"),
        ),
    )


def _insert_sale(conn, **kwargs) -> None:
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kwargs.get("order_id"),
            kwargs.get("order_date"),
            kwargs.get("sku_key"),
            kwargs.get("sku_id"),
            kwargs.get("my_size"),
            kwargs.get("kaspi_offer_name"),
            kwargs.get("store_code"),
        ),
    )


def test_backfill_updates_missing_sku_key(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="111",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_sale(
        conn,
        order_id="111",
        order_date="2026-01-10",
        sku_key="CL_NEW-CLO2_MEN_SUIT-61_BLACK",
        sku_id="CL_NEW-CLO2_MEN_SUIT-61_BLACK_L",
        my_size="L",
        kaspi_offer_name="Some offer",
        store_code="ACMEWEAR",
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["updated"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id, my_size, kaspi_offer_name FROM fact_orders_kaspi"
    ).fetchone()
    conn.close()
    assert row[0] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert row[1] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK_L"
    assert row[2] == "L"
    assert row[3] == "Some offer"


def test_backfill_skips_ambiguous_orders(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="222",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_sale(
        conn,
        order_id="222",
        order_date="2026-01-10",
        sku_key="SKU_A",
        sku_id="SKU_A_L",
        my_size="L",
        kaspi_offer_name="Offer A",
        store_code="ACMEWEAR",
    )
    _insert_sale(
        conn,
        order_id="222",
        order_date="2026-01-10",
        sku_key="SKU_B",
        sku_id="SKU_B_M",
        my_size="M",
        kaspi_offer_name="Offer B",
        store_code="ACMEWEAR",
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["ambiguous"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id FROM fact_orders_kaspi"
    ).fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None


def test_backfill_respects_status_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="333",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="NEW",
        kaspi_status="NEW",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_sale(
        conn,
        order_id="333",
        order_date="2026-01-10",
        sku_key="SKU_C",
        sku_id="SKU_C_S",
        my_size="S",
        kaspi_offer_name="Offer C",
        store_code="ACMEWEAR",
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["skipped_status"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id FROM fact_orders_kaspi"
    ).fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None


def test_backfill_skips_duplicate_sku_id(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="444",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_order(
        conn,
        order_id="444",
        store_code="ACMEWEAR",
        sku_key="SKU_X",
        sku_id="SKU_X_L",
        my_size="L",
        kaspi_offer_name="Offer X",
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_sale(
        conn,
        order_id="444",
        order_date="2026-01-10",
        sku_key="SKU_X",
        sku_id="SKU_X_L",
        my_size="L",
        kaspi_offer_name="Offer X",
        store_code="ACMEWEAR",
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["skipped_duplicate"] == 1

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT sku_key, sku_id FROM fact_orders_kaspi WHERE order_id='444'"
    ).fetchall()
    conn.close()
    assert len(rows) == 2


def test_backfill_fallback_order_only(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="555",
        store_code="30137883_PP1",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    _insert_sale(
        conn,
        order_id="555",
        order_date="2026-01-10",
        sku_key="SKU_FALLBACK",
        sku_id="SKU_FALLBACK_L",
        my_size="L",
        kaspi_offer_name="Offer F",
        store_code="ACMEWEAR",
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["fallback_order_only"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id FROM fact_orders_kaspi WHERE order_id='555'"
    ).fetchone()
    conn.close()
    assert row[0] == "SKU_FALLBACK"
    assert row[1] == "SKU_FALLBACK_L"


def test_backfill_uses_article_map(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="666",
        store_code="UNIVERSAL",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-10 00:00:00",
        created_at="2026-01-10 00:00:00",
        updated_at="2026-01-10 00:00:00",
    )
    conn.execute(
        "INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id) VALUES (?, ?, ?, ?)",
        ("UNIVERSAL", "ART-1", "SKU_ART", "SKU_ART_S"),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
        ("SKU_ART_S", "SKU_ART", "S"),
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        order_article_map={"666": "ART-1"},
        exports_dir=tmp_path,
    )
    assert stats["fallback_article_map"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id, my_size FROM fact_orders_kaspi WHERE order_id='666'"
    ).fetchone()
    conn.close()
    assert row[0] == "SKU_ART"
    assert row[1] == "SKU_ART_S"
    assert row[2] == "S"


def test_backfill_uses_article_map_with_store_code(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="777",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-12 00:00:00",
        created_at="2026-01-12 00:00:00",
        updated_at="2026-01-12 00:00:00",
    )
    conn.execute(
        "INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id) VALUES (?, ?, ?, ?)",
        ("UNIVERSAL", "ART-2", "SKU_OTHER", "SKU_OTHER_S"),
    )
    conn.execute(
        "INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id) VALUES (?, ?, ?, ?)",
        ("ACMEWEAR", "ART-2", "SKU_TARGET", "SKU_TARGET_M"),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
        ("SKU_TARGET_M", "SKU_TARGET", "M"),
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        order_article_map={"777": "ART-2"},
        exports_dir=tmp_path,
    )
    assert stats["fallback_article_map"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id, my_size FROM fact_orders_kaspi WHERE order_id='777'"
    ).fetchone()
    conn.close()
    assert row[0] == "SKU_TARGET"
    assert row[1] == "SKU_TARGET_M"
    assert row[2] == "M"


def test_backfill_uses_sales_fact_outside_window(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    _insert_order(
        conn,
        order_id="888",
        store_code="ACMEWEAR",
        sku_key=None,
        sku_id=None,
        my_size=None,
        kaspi_offer_name=None,
        internal_status="COMPLETED",
        kaspi_status="ARCHIVE",
        status_updated_at="2026-01-15 00:00:00",
        created_at="2026-01-15 00:00:00",
        updated_at="2026-01-15 00:00:00",
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("888", "2025-12-10", "SKU_OUTSIDE", "SKU_OUTSIDE_L", "L", "OFFER", "ACMEWEAR"),
    )
    conn.commit()
    conn.close()

    stats = backfill_orders(
        db_path=db_path,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
        apply=True,
        exports_dir=tmp_path,
    )
    assert stats["updated"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT sku_key, sku_id, my_size FROM fact_orders_kaspi WHERE order_id='888'"
    ).fetchone()
    conn.close()
    assert row[0] == "SKU_OUTSIDE"
    assert row[1] == "SKU_OUTSIDE_L"
    assert row[2] == "L"
