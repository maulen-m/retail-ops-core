import scripts.generate_po_dashboard_data as dashboard


def test_line52_and_line61_share_prep_lane() -> None:
    assert dashboard.prep_lane_for_sku("CL_OC_MEN_LINE52_BLACK") == "CORE_PRINT_SUIT"
    assert dashboard.prep_lane_for_sku("CL_NEW-CLO2_MEN_SUIT-61_BLACK") == "CORE_PRINT_SUIT"


def test_other_clothes_use_separate_lane() -> None:
    assert dashboard.prep_lane_for_sku("CL_NC_MEN_RUSH-31_BLACK") == "GENERAL_CL"
    assert dashboard.prep_lane_for_sku("ELS_POWERBANK_20000") == "ELS"
