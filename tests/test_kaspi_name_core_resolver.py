import sqlite3

from core.utils.kaspi_name_core_resolver import (
    SAFE_KASPI_NAME_CORE_SOURCES,
    load_active_kaspi_name_core_maps,
    resolve_kaspi_name_core,
)


def test_resolve_kaspi_name_core_uses_sku_family_mapping(tmp_path):
    db_path = tmp_path / "resolver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_offer_name, sku_key, kaspi_name_core, active_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "UNIVERSAL",
                "Комплект Antec RASH-921 Рашгард 5 в 1 черный XL",
                "CL_OC_MEN_LINE52_BLACK",
                "Принт_5в1_черный",
                1,
                "2026-04-15 10:30:56",
            ),
        )
        conn.commit()

        maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys={"CL_OC_MEN_LINE52_BLACK_103217238_44/46, 48"},
            store_offer_pairs={("UNIVERSAL", "Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48")},
        )
    finally:
        conn.close()

    resolution = resolve_kaspi_name_core(
        store_code="UNIVERSAL",
        kaspi_offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48",
        sku_key="CL_OC_MEN_LINE52_BLACK_103217238_44/46, 48",
        maps=maps,
    )

    assert resolution.core == "Принт_5в1_черный"
    assert resolution.source == "sku_family"
    assert resolution.safe is True
    assert resolution.source in SAFE_KASPI_NAME_CORE_SOURCES


def test_resolve_kaspi_name_core_uses_compact_exact_sku_mapping(tmp_path):
    db_path = tmp_path / "resolver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(
            """
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                kaspi_name_core TEXT,
                active_flag INTEGER,
                updated_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_offer_name, sku_key, kaspi_name_core, active_flag, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ACMEWEAR",
                "SUIT-31-TS-ST-3XL-54",
                "SUIT-31-TS",
                "SUIT-31-TS-ST",
                1,
                "2026-05-03 10:30:56",
            ),
        )
        conn.commit()

        maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys={"SUIT-31-TS"},
            store_offer_pairs={
                ("ACMEWEAR", "Спортивный костюм ACMEWEAR SUIT-31-TS-ST-3XL-54 черный 3XL")
            },
        )
    finally:
        conn.close()

    resolution = resolve_kaspi_name_core(
        store_code="ACMEWEAR",
        kaspi_offer_name="Спортивный костюм ACMEWEAR SUIT-31-TS-ST-3XL-54 черный 3XL",
        sku_key="SUIT-31-TS",
        sku_id="SUIT-31-TS_3XL",
        maps=maps,
    )

    assert resolution.core == "SUIT-31-TS-ST"
    assert resolution.source == "sku_key"
    assert resolution.safe is True


def test_resolve_kaspi_name_core_marks_raw_offer_extract_as_unsafe():
    resolution = resolve_kaspi_name_core(
        store_code="UNIVERSAL",
        kaspi_offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный 46, 48",
        sku_key="CL_OC_MEN_LINE52_BLACK_103217238_44/46, 48",
    )

    assert resolution.source == "raw_offer_extract"
    assert resolution.safe is False
