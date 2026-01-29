import sqlite3
from pathlib import Path

import pytest

from core.integrations.kaspi_pricelist.generator import generate_pricelist


def _setup_db(db_path: Path, with_price: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            product_type TEXT NOT NULL,
            base_cost_cny REAL NOT NULL,
            weight_kg REAL NOT NULL,
            avg_sell_price_kzt_used REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    price = 12000 if with_price else None
    conn.execute(
        "INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, avg_sell_price_kzt_used) VALUES (?,?,?,?,?,?)",
        ("CL_TEST_SKU", "Test Model", "CL", 10, 0.5, price),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?,?,?)",
        ("CL_TEST_SKU_S", "CL_TEST_SKU", "S"),
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock) VALUES (?,?,?,?,?,?)",
        ("2026-01-27", "CL_TEST_SKU_S", "CL_TEST_SKU", "S", 3, 2),
    )
    conn.commit()
    conn.close()


def _setup_db_two_skus(db_path: Path) -> None:
    _setup_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, avg_sell_price_kzt_used) VALUES (?,?,?,?,?,?)",
        ("CL_TEST_SKU2", "Test Model 2", "CL", 12, 0.6, 15000),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?,?,?)",
        ("CL_TEST_SKU2_S", "CL_TEST_SKU2", "S"),
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock) VALUES (?,?,?,?,?,?)",
        ("2026-01-27", "CL_TEST_SKU2_S", "CL_TEST_SKU2", "S", 4, 1),
    )
    conn.commit()
    conn.close()


def _write_config(path: Path) -> None:
    config_text = (
        "defaults:\n"
        "  brand: \"No brand\"\n"
        "  preorder_days: 7\n"
        "\n"
        "stores:\n"
        "  UNIVERSAL:\n"
        "    company: \"TestCo\"\n"
        "    merchant_id: \"123\"\n"
        "    warehouses:\n"
        "      - PP1\n"
    )
    path.write_text(config_text, encoding="utf-8")


def test_generate_pricelist_dry_run(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)

    output_dir = tmp_path / "exports"
    result = generate_pricelist(
        db_path=db_path,
        store_code="UNIVERSAL",
        config_path=cfg_path,
        output_dir=output_dir,
        dry_run=True,
        publish_path=None,
    )

    assert result.catalog_path.exists()
    assert result.diff_report_path.exists()
    xml = result.catalog_path.read_text(encoding="utf-8")
    assert "<offer sku=\"CL_TEST_SKU_S\"" in xml


def test_generate_pricelist_missing_price(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path, with_price=False)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)

    with pytest.raises(ValueError):
        generate_pricelist(
            db_path=db_path,
            store_code="UNIVERSAL",
            config_path=cfg_path,
            output_dir=tmp_path / "exports",
            dry_run=True,
            publish_path=None,
        )


def test_generate_pricelist_allowlist_filters_offers(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db_two_skus(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)
    allowlist_path = tmp_path / "allowlist.txt"
    allowlist_path.write_text("CL_TEST_SKU_S\n", encoding="utf-8")

    output_dir = tmp_path / "exports"
    result = generate_pricelist(
        db_path=db_path,
        store_code="UNIVERSAL",
        config_path=cfg_path,
        output_dir=output_dir,
        dry_run=True,
        publish_path=None,
        allowlist_path=allowlist_path,
    )

    xml = result.catalog_path.read_text(encoding="utf-8")
    assert "<offer sku=\"CL_TEST_SKU_S\"" in xml
    assert "CL_TEST_SKU2_S" not in xml
    assert result.offer_count == 1


def test_generate_pricelist_publish_creates_backup(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)

    output_dir = tmp_path / "exports"
    publish_path = tmp_path / "publish.xml"
    publish_path.write_text("OLD_XML", encoding="utf-8")

    generate_pricelist(
        db_path=db_path,
        store_code="UNIVERSAL",
        config_path=cfg_path,
        output_dir=output_dir,
        dry_run=False,
        publish_path=publish_path,
    )

    backup_path = publish_path.with_name("publish_last_good.xml")
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "OLD_XML"
