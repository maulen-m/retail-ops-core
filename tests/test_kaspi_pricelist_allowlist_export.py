import sqlite3
from pathlib import Path

from scripts.export_kaspi_pricelist_allowlist import export_allowlist


def _setup_db_with_flags(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            active_flag INTEGER DEFAULT 1
        )
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, ?)", ("SKU_A", 1))
    conn.execute("INSERT INTO dim_sku (sku_key, active_flag) VALUES (?, ?)", ("SKU_B", 0))
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, active_flag) VALUES (?, ?, ?)",
        ("SKU_A_S", "SKU_A", 1),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, active_flag) VALUES (?, ?, ?)",
        ("SKU_B_S", "SKU_B", 1),
    )
    conn.commit()
    conn.close()


def _setup_db_without_flags(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL
        )
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key) VALUES (?)", ("SKU_A",))
    conn.execute("INSERT INTO dim_sku (sku_key) VALUES (?)", ("SKU_B",))
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key) VALUES (?, ?)",
        ("SKU_A_S", "SKU_A"),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key) VALUES (?, ?)",
        ("SKU_B_S", "SKU_B"),
    )
    conn.commit()
    conn.close()


def test_export_allowlist_filters_active(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db_with_flags(db_path)
    output_path = tmp_path / "allowlist.txt"

    count = export_allowlist(db_path=db_path, output_path=output_path)

    assert count == 1
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["SKU_A_S"]


def test_export_allowlist_defaults_active_when_flags_missing(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _setup_db_without_flags(db_path)
    output_path = tmp_path / "allowlist.txt"

    count = export_allowlist(db_path=db_path, output_path=output_path)

    assert count == 2
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["SKU_A_S", "SKU_B_S"]
