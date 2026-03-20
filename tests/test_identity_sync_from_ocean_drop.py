from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts.sync_dim_kaspi_article_map_from_ocean_drop import (
    IdentitySyncError,
    sync_dim_kaspi_article_map_from_ocean_drop,
)
from scripts.sync_order_size_overrides_from_ocean_drop import (
    SizeOverrideError,
    sync_order_size_overrides_from_ocean_drop,
)


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            source TEXT,
            active_flag INTEGER
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            assigned_size TEXT,
            size_source TEXT,
            size_confidence TEXT,
            updated_at TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id, source, active_flag) VALUES ('ACMEWEAR', 'OLD_ART', 'OLD', 'OLD', 'seed', 1)"
    )
    conn.execute(
        "INSERT INTO fact_orders_kaspi (order_id, assigned_size, size_source, size_confidence) VALUES ('ORD-1', '', '', '')"
    )
    conn.commit()
    conn.close()


def _write_ocean_drop(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "№ заказа": "ORD-1",
                "Склад передачи КД": "30137883_PP1",
                "Артикул": "NEW_ART",
                "mapped_sku_key": "SKU_NEW",
                "mapped_size": "L",
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def test_identity_sync_requires_apply_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    csv_path = tmp_path / "ocean.csv"
    _seed_db(db)
    _write_ocean_drop(csv_path)

    monkeypatch.delenv("ENABLE_OCEAN_DROP_IDENTITY_APPLY", raising=False)
    with pytest.raises(IdentitySyncError, match="ENABLE_OCEAN_DROP_IDENTITY_APPLY"):
        sync_dim_kaspi_article_map_from_ocean_drop(
            db_path=db,
            ocean_drop_path=csv_path,
            as_of=date(2026, 2, 26),
            output_root=tmp_path / "out",
            strict=True,
            apply=True,
            backup_root=tmp_path / "backups",
        )


def test_size_override_sync_updates_order_on_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    csv_path = tmp_path / "ocean.csv"
    _seed_db(db)
    _write_ocean_drop(csv_path)

    monkeypatch.setenv("ENABLE_OCEAN_DROP_SIZE_APPLY", "1")
    report = sync_order_size_overrides_from_ocean_drop(
        db_path=db,
        ocean_drop_path=csv_path,
        as_of=date(2026, 2, 26),
        output_root=tmp_path / "out",
        strict=True,
        apply=True,
        backup_root=tmp_path / "backups",
    )
    assert report["status"] == "APPLIED"

    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT assigned_size, size_source, size_confidence FROM fact_orders_kaspi WHERE order_id='ORD-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("L", "OCEAN_DROP", "HIGH")


def test_size_override_sync_fails_closed_when_order_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    csv_path = tmp_path / "ocean.csv"
    _seed_db(db)
    _write_ocean_drop(csv_path)

    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM fact_orders_kaspi")
    conn.commit()
    conn.close()

    with pytest.raises(SizeOverrideError, match="missing orders"):
        sync_order_size_overrides_from_ocean_drop(
            db_path=db,
            ocean_drop_path=csv_path,
            as_of=date(2026, 2, 26),
            output_root=tmp_path / "out",
            strict=True,
            apply=False,
            backup_root=tmp_path / "backups",
        )
