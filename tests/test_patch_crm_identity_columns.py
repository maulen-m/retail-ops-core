from scripts.patch_crm_identity_columns import compute_identity_patch


def test_compute_identity_patch_forces_line61_core_and_sku():
    row = {
        "Артикул": "OF_SUIT-61_BLK_3XL",
        "Название товара в Kaspi Магазине": "Спортивный костюм ACMEWEAR CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL черный 3XL",
        "SKU_key": "CL_OC_MEN_LINE51_WHITE",
        "Product_Type": "CL",
    }
    out = compute_identity_patch(row, article_identity_by_article={})
    assert out["sku_key"] == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert out["kaspi_name_core"] == "6в1_Черный_+Сумка"
