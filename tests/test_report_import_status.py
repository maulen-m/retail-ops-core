from scripts.report_import_status import normalize_store_name


def test_normalize_store_name_maps_store_codes():
    assert normalize_store_name("30362323_PP1") == "Store-C"
    assert normalize_store_name("30000002_PP1") == "STORE-B"


def test_normalize_store_name_maps_api_codes():
    assert normalize_store_name("MELVIS") == "Store-C"
    assert normalize_store_name("STOREB") == "STORE-B"
