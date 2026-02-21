from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.validate_offer_linkage import validate_offer_linkage


def _setup_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_offer_stock_mapper_current (
            store_code TEXT,
            offer_id TEXT,
            sku_key TEXT,
            mapping_method TEXT,
            is_ambiguous INTEGER DEFAULT 0
        );
        CREATE TABLE dim_kaspi_article_map (
            kaspi_offer_id TEXT,
            sku_key TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def test_unresolved_offers_fail_strict_publish(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _setup_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_offer_stock_mapper_current
        (store_code, offer_id, sku_key, mapping_method, is_ambiguous)
        VALUES ('UNIVERSAL', 'OF_LINE52_XL', '', 'unresolved', 0)
        """
    )
    conn.commit()
    conn.close()

    report = validate_offer_linkage(db_path=db_path)
    assert report["ok"] is False
    assert any("unresolved" in err.lower() for err in report["errors"])


def test_bidirectional_mapping_required_for_publish(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _setup_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_offer_stock_mapper_current
        (store_code, offer_id, sku_key, mapping_method, is_ambiguous)
        VALUES ('UNIVERSAL', 'OF_LINE61_XL', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'sku_key_exact', 0)
        """
    )
    conn.commit()
    conn.close()

    report = validate_offer_linkage(db_path=db_path)
    assert report["ok"] is False
    assert any("bidirectional" in err.lower() for err in report["errors"])


def test_offer_linkage_passes_when_mapping_is_resolved_and_bidirectional(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _setup_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_offer_stock_mapper_current
        (store_code, offer_id, sku_key, mapping_method, is_ambiguous)
        VALUES ('UNIVERSAL', 'OF_LINE61_XL', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK', 'sku_key_exact', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (kaspi_offer_id, sku_key)
        VALUES ('OF_LINE61_XL', 'CL_NEW-CLO2_MEN_SUIT-61_BLACK')
        """
    )
    conn.commit()
    conn.close()

    report = validate_offer_linkage(db_path=db_path)
    assert report["ok"] is True
    assert report["errors"] == []
