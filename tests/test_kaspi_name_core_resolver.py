import sqlite3

from core.utils.kaspi_name_core_resolver import (
    KaspiNameCoreMaps,
    SAFE_KASPI_NAME_CORE_SOURCES,
    load_active_kaspi_name_core_maps,
    resolve_kaspi_name_core,
)

LINE31_STORE = "ACMEWEAR"
LINE31_OFFER = "ACMEWEAR OF_LINE31_ST_SB_XL"
LINE31_OLIVE_SKU = "CL_OF_ARC_WM_LINE31_B-C-005_CARDAMOM-GREEN_J-C-005_CARDAMOM-GREEN_L-C-015_OLIVE-GREEN"
LINE31_ESPRESSO_SKU = "CL_OF_ARC_WM_LINE31_C-008_ESPRESSO"
LINE31_IRIS_SKU = "CL_OF_ARC_WM_LINE31_C-010_IRIS-PURPLE"
LINE31_OLIVE_CORE = "Женский_3в1_ОЛИВКОВЫЙ"
LINE31_ESPRESSO_CORE = "Женский_3в1_КОРИЧНЕВЫЙ"
LINE31_IRIS_CORE = "Женский_3в1_СИРЕНЕВЫЙ"


def _connect_article_map_db(tmp_path):
    db_path = tmp_path / "resolver.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    return conn


def _insert_article_map(
    conn,
    *,
    store_code,
    offer_name,
    sku_key,
    kaspi_name_core,
    active_flag=1,
    updated_at="2026-05-04 10:00:00",
):
    conn.execute(
        """
        INSERT INTO dim_kaspi_article_map (
            store_code, kaspi_offer_name, sku_key, kaspi_name_core, active_flag, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (store_code, offer_name, sku_key, kaspi_name_core, active_flag, updated_at),
    )


def _insert_ambiguous_line31_store_offer_rows(conn):
    _insert_article_map(
        conn,
        store_code=LINE31_STORE,
        offer_name=LINE31_OFFER,
        sku_key=LINE31_OLIVE_SKU,
        kaspi_name_core=LINE31_OLIVE_CORE,
        updated_at="2026-05-04 09:00:00",
    )
    _insert_article_map(
        conn,
        store_code=LINE31_STORE,
        offer_name=LINE31_OFFER,
        sku_key=LINE31_ESPRESSO_SKU,
        kaspi_name_core=LINE31_ESPRESSO_CORE,
        updated_at="2026-05-04 09:05:00",
    )
    _insert_article_map(
        conn,
        store_code=LINE31_STORE,
        offer_name=LINE31_OFFER,
        sku_key=LINE31_IRIS_SKU,
        kaspi_name_core=LINE31_IRIS_CORE,
        updated_at="2026-05-04 09:10:00",
    )
    conn.commit()


def test_resolve_kaspi_name_core_exact_sku_beats_conflicting_store_offer(tmp_path):
    conn = _connect_article_map_db(tmp_path)
    try:
        _insert_ambiguous_line31_store_offer_rows(conn)
        maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys={LINE31_OLIVE_SKU},
            store_offer_pairs={(LINE31_STORE, LINE31_OFFER)},
        )
    finally:
        conn.close()

    resolution = resolve_kaspi_name_core(
        store_code=LINE31_STORE,
        kaspi_offer_name=LINE31_OFFER,
        sku_key=LINE31_OLIVE_SKU,
        maps=maps,
        allow_unsafe_fallback=False,
    )

    assert resolution.core == LINE31_OLIVE_CORE
    assert resolution.source == "sku_key"
    assert resolution.safe is True


def test_load_active_maps_excludes_ambiguous_store_offer_rows(tmp_path):
    conn = _connect_article_map_db(tmp_path)
    try:
        _insert_ambiguous_line31_store_offer_rows(conn)
        maps = load_active_kaspi_name_core_maps(
            conn,
            store_offer_pairs={(LINE31_STORE, LINE31_OFFER)},
        )
    finally:
        conn.close()

    assert ("ACMEWEAR", "acmewear of_line31_st_sb_xl") not in maps.by_store_offer

    resolution = resolve_kaspi_name_core(
        store_code=LINE31_STORE,
        kaspi_offer_name=LINE31_OFFER,
        sku_key="",
        maps=maps,
        allow_unsafe_fallback=False,
    )

    assert resolution.core == ""
    assert resolution.source == "unresolved"


def test_resolve_kaspi_name_core_forced_core_wins_before_maps():
    maps = KaspiNameCoreMaps(
        by_store_offer={("ACMEWEAR", "acmewear of_line31_st_sb_xl"): LINE31_IRIS_CORE},
        by_sku_key={LINE31_OLIVE_SKU: LINE31_OLIVE_CORE},
    )

    resolution = resolve_kaspi_name_core(
        store_code=LINE31_STORE,
        kaspi_offer_name=LINE31_OFFER,
        sku_key=LINE31_OLIVE_SKU,
        maps=maps,
        preferred_core="Manual_Override_Core",
        preferred_source="forced_core",
    )

    assert resolution.core == "Manual_Override_Core"
    assert resolution.source == "forced_core"
    assert resolution.safe is True


def test_resolve_kaspi_name_core_uses_sku_family_mapping(tmp_path):
    conn = _connect_article_map_db(tmp_path)
    try:
        _insert_article_map(
            conn,
            store_code="UNIVERSAL",
            offer_name="Комплект Antec RASH-921 Рашгард 5 в 1 черный XL",
            sku_key="CL_OC_MEN_LINE52_BLACK",
            kaspi_name_core="Принт_5в1_черный",
            updated_at="2026-04-15 10:30:56",
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
    conn = _connect_article_map_db(tmp_path)
    try:
        _insert_article_map(
            conn,
            store_code="ACMEWEAR",
            offer_name="SUIT-31-TS-ST-3XL-54",
            sku_key="SUIT-31-TS",
            kaspi_name_core="SUIT-31-TS-ST",
            updated_at="2026-05-03 10:30:56",
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
