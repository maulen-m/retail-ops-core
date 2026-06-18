from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from scripts.apply_owner_confirmed_article_map_overrides import run


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT NOT NULL,
            merchant_id TEXT,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            kaspi_name_core TEXT,
            sku_key TEXT,
            sku_id TEXT,
            model TEXT,
            brand TEXT,
            source TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (
            store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, source, active_flag
        ) VALUES (
            'UNIVERSAL', '132822924_328581041', 'Леггинсы PRO COMBAT 2010 белый XL',
            'CL_NEW-CLO_MEN_LEG_WHITE', 'CL_NEW-CLO_MEN_LEG_WHITE',
            'manual_unresolved_sku_resolution', 0
        )
        """
    )
    conn.commit()
    conn.close()


def test_owner_confirmed_article_map_dry_run_does_not_mutate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    summary = run(db_path=db_path, output_root=tmp_path / "out", apply=False)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT sku_id, active_flag FROM dim_kaspi_article_map WHERE kaspi_article='132822924_328581041'"
    ).fetchone()
    conn.close()

    assert summary["apply_status"] == "DRY_RUN"
    assert row == ("CL_NEW-CLO_MEN_LEG_WHITE", 0)


def test_owner_confirmed_article_map_apply_is_env_gated(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_OWNER_CONFIRMED_ARTICLE_MAP_WRITE=1"):
        run(db_path=db_path, output_root=tmp_path / "out", apply=True)


def test_owner_confirmed_article_map_apply_updates_exact_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    monkeypatch.setenv("ENABLE_OWNER_CONFIRMED_ARTICLE_MAP_WRITE", "1")

    summary = run(db_path=db_path, output_root=tmp_path / "out", apply=True)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT sku_key, sku_id, active_flag, source
        FROM dim_kaspi_article_map
        WHERE kaspi_article='132822924_328581041'
        """
    ).fetchone()
    conn.close()

    assert summary["apply_status"] == "APPLIED"
    assert Path(summary["backup_path"]).exists()
    assert row == (
        "CL_NEW-CLO_MEN_LEG_WHITE",
        "CL_NEW-CLO_MEN_LEG_WHITE_XL",
        1,
        "OWNER_CONFIRMED_2026_05_21_UNIVERSAL_132822924_328581041",
    )
