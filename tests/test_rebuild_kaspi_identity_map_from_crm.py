from scripts.rebuild_kaspi_identity_map_from_crm import (
    build_core_majority_map,
    choose_best_identity,
)


def test_choose_best_identity_forces_line61():
    rows = [
        {
            "kaspi_article": "OF_SUIT-61_BLK_XL_48",
            "sku_key": "CL_OC_MEN_LINE51_WHITE",
            "kaspi_name_core": "Wrong",
            "weight": 1,
        }
    ]
    chosen = choose_best_identity("OF_SUIT-61_BLK_XL_48", rows)
    assert chosen["sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert chosen["kaspi_name_core"] == "6в1_Черный_+Сумка"


def test_choose_best_identity_prefers_majority_sku_key():
    rows = [
        {"kaspi_article": "ART-1", "sku_key": "A", "kaspi_name_core": "CoreA", "weight": 3},
        {"kaspi_article": "ART-1", "sku_key": "A", "kaspi_name_core": "CoreA", "weight": 1},
        {"kaspi_article": "ART-1", "sku_key": "B", "kaspi_name_core": "CoreB", "weight": 1},
    ]
    chosen = choose_best_identity("ART-1", rows)
    assert chosen["sku_key"] == "A"
    assert chosen["kaspi_name_core"] == "CoreA"


def test_build_core_majority_map_prefers_dominant_sku_per_store_core():
    rows = [
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE52_BLACK"},
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE52_BLACK"},
        {"store_code": "ACMEWEAR", "kaspi_name_core": "Принт_5в1_черный", "sku_key": "CL_OC_MEN_LINE51_WHITE"},
    ]
    out = build_core_majority_map(rows)
    assert out[("ACMEWEAR", "Принт_5в1_черный")] == "CL_OC_MEN_LINE52_BLACK"
