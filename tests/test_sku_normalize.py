from core.utils.sku_normalize import normalize_size


def test_normalize_size_strips_excel_float_suffix():
    assert normalize_size("26.0", product_type="CL") == "26"
    assert normalize_size("32.0", product_type="CL") == "32"


def test_normalize_size_handles_common_dirty_tokens():
    assert normalize_size("3XL?", product_type="CL") == "3XL"
    assert normalize_size("NAN", product_type="CL") is None
    assert normalize_size("BLACK", product_type="CL") is None


def test_normalize_size_maps_cyrillic_letters():
    assert normalize_size("М", product_type="CL") == "M"
