import os
import sqlite3
import sys
from pathlib import Path

import pytest

from scripts.deploy_kaspi_pricelist import (
    LocalUploader,
    deploy_pricelist,
    rollback_pricelist,
    main as deploy_main,
)


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
            avg_sell_price_kzt_used REAL,
            active_flag INTEGER DEFAULT 1
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
        "INSERT INTO dim_sku (sku_key, model, product_type, base_cost_cny, weight_kg, avg_sell_price_kzt_used, active_flag) VALUES (?,?,?,?,?,?,?)",
        ("CL_TEST_SKU", "Test Model", "CL", 10, 0.5, 12000, 1),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, active_flag) VALUES (?,?,?,?)",
        ("CL_TEST_SKU_S", "CL_TEST_SKU", "S", 1),
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


def _write_allowlist(path: Path) -> None:
    path.write_text("CL_TEST_SKU_S\n", encoding="utf-8")


def test_deploy_requires_env_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)
    allowlist_path = tmp_path / "allowlist.txt"
    _write_allowlist(allowlist_path)

    monkeypatch.delenv("ENABLE_KASPI_PRICELIST_PUBLISH", raising=False)
    args = [
        "deploy_kaspi_pricelist.py",
        "--store",
        "UNIVERSAL",
        "--db",
        str(db_path),
        "--config",
        str(cfg_path),
        "--output-dir",
        str(tmp_path / "exports"),
        "--allowlist",
        str(allowlist_path),
        "--publish",
        "--bucket",
        "test-bucket",
        "--prefix",
        "kaspi",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(RuntimeError):
        deploy_main()


def test_deploy_requires_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)

    monkeypatch.setenv("ENABLE_KASPI_PRICELIST_PUBLISH", "1")
    args = [
        "deploy_kaspi_pricelist.py",
        "--store",
        "UNIVERSAL",
        "--db",
        str(db_path),
        "--config",
        str(cfg_path),
        "--output-dir",
        str(tmp_path / "exports"),
        "--publish",
        "--bucket",
        "test-bucket",
    ]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(RuntimeError):
        deploy_main()


def test_deploy_backup_and_rollback_local(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db(db_path)
    cfg_path = tmp_path / "kaspi_pricelist.yaml"
    _write_config(cfg_path)
    allowlist_path = tmp_path / "allowlist.txt"
    _write_allowlist(allowlist_path)

    output_dir = tmp_path / "exports"
    remote_root = tmp_path / "remote"
    uploader = LocalUploader(remote_root)

    dest_path = remote_root / "UNIVERSAL" / "kaspi_catalog.xml"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text("OLD_XML", encoding="utf-8")

    deploy_pricelist(
        store_codes=["UNIVERSAL"],
        db_path=db_path,
        config_path=cfg_path,
        output_dir=output_dir,
        allowlist_path=allowlist_path,
        publish=True,
        uploader=uploader,
    )

    backup_path = remote_root / "UNIVERSAL" / "kaspi_catalog_last_good.xml"
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "OLD_XML"
    assert dest_path.read_text(encoding="utf-8") != "OLD_XML"

    rollback_pricelist(store_codes=["UNIVERSAL"], uploader=uploader)
    assert dest_path.read_text(encoding="utf-8") == "OLD_XML"
