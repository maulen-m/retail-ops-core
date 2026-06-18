from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from build_g_price03_remediation_packet import (
    build_bucket_matrix,
    floor_for_family,
    summarize_current_rows,
)


def test_floor_authority_distinguishes_suit_alias_from_beli_missing() -> None:
    floor_map = {
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK": {"Min_price_35pct": "10769"},
    }

    suit_key, suit_floor, suit_source = floor_for_family("SUIT-31-LS", floor_map)
    beli_key, beli_floor, beli_source = floor_for_family("LINE-31-TS", floor_map)

    assert suit_key == "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    assert suit_floor == 10769.0
    assert "not price-write authority" in suit_source
    assert beli_key == "LINE-31-TS"
    assert beli_floor is None
    assert "Missing SKU-wide compact LINE floor authority" in beli_source


def test_bucket_matrix_flags_current_suit_exposure_and_beli_authority_gap() -> None:
    red_rows = [
        {
            "sku_key": "SUIT-31-TS",
            "stores": "ACMEWEAR",
            "floor_sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
            "floor_min_price_kzt": "10769.00",
            "under_floor_units": "2",
            "gap_total_kzt": "2558.00",
            "missing_floor_rows": "0",
            "min_sell_price_kzt": "9490.00",
        },
        {
            "sku_key": "LINE-31-TS",
            "stores": "ACMEWEAR",
            "floor_sku_key": "LINE-31-TS",
            "floor_min_price_kzt": "",
            "under_floor_units": "0",
            "gap_total_kzt": "0.00",
            "missing_floor_rows": "3",
            "min_sell_price_kzt": "9990.00",
        },
    ]
    current_summary = summarize_current_rows(
        [
            {
                "store": "ACMEWEAR",
                "family": "SUIT-31-TS",
                "price": "7990.00",
                "floor_min_price_kzt": "10769.00",
                "relation": "below_floor",
            },
            {
                "store": "ACMEWEAR",
                "family": "LINE-31-TS",
                "price": "9990.00",
                "floor_min_price_kzt": "",
                "relation": "missing_floor",
            },
        ]
    )

    matrix = {row["sku_key"]: row for row in build_bucket_matrix(red_rows, current_summary)}

    assert matrix["SUIT-31-TS"]["current_status"] == "current_acmewear_compact_price_below_parent_floor"
    assert matrix["SUIT-31-TS"]["approval_status"] == "required_before_any_live_price_or_offer_write"
    assert matrix["LINE-31-TS"]["current_status"] == "missing_compact_beli_floor_authority"
    assert matrix["LINE-31-TS"]["approval_status"] == "required_before_scoring_or_live_price_write"
