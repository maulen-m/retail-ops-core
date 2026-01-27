import os
import sqlite3
import sys
from pathlib import Path

import pytest

from scripts.generate_kaspi_pricelist_xml import main as pricelist_main


def _setup_db(db_path: Path) -> None:
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

    conn.execute(
        "INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, avg_sell_price_kzt_used) VALUES (?,?,?,?,?,?)",
        ("CL_TEST_SKU", "Test Model", "CL", 10, 0.5, 12000),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?,?,?)",
        ("CL_TEST_SKU_S", "CL_TEST_SKU", "S"),
    )
    conn.execute(
        "INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock) VALUES (?,?,?,?,?,?)",
        ("2026-01-27", "CL_TEST_SKU_S", "CL_TEST_SKU", "S", 3, 0),
    )
    conn.commit()
    conn.close()


def _write_config(path: Path) -> None:
    config_text = (
        "defaults:\n"
        "  brand: \"No brand\"\n"
        "  preorder_days: 7\n"
        "stores:\n"
        "  UNIVERSAL:\n"
        "    company: \"TestCo\"\n"
        "    merchant_id: \"123\"\n"
        "    warehouses:\n"
        "      - PP1\n"
    )
    path.write_text(config_text, encoding="utf-8")


def test_publish_requires_env_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)
    publish_path = tmp_path / "publish.xml"

    monkeypatch.delenv("ENABLE_KASPI_PRICELIST_PUBLISH", raising=False)
    args = [
        "generate_kaspi_pricelist_xml.py",
        "--store",
        "UNIVERSAL",
        "--db",
        str(db_path),
        "--config",
        str(cfg_path),
        "--output-dir",
        str(tmp_path / "exports"),
        "--publish",
        "--publish-path",
        str(publish_path),
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(RuntimeError):
        pricelist_main()


def test_publish_writes_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)
    publish_path = tmp_path / "publish.xml"

    monkeypatch.setenv("ENABLE_KASPI_PRICELIST_PUBLISH", "1")
    args = [
        "generate_kaspi_pricelist_xml.py",
        "--store",
        "UNIVERSAL",
        "--db",
        str(db_path),
        "--config",
        str(cfg_path),
        "--output-dir",
        str(tmp_path / "exports"),
        "--publish",
        "--publish-path",
        str(publish_path),
    ]
    monkeypatch.setattr(sys, "argv", args)

    assert pricelist_main() == 0
    assert publish_path.exists()
