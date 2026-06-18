from scripts.materialize_temporary_ocr_stock_override import (
    OWNER_CONFLICT_HOLD_ROWS,
    PARKED_JUNE11_ROWS,
    _apply_owner_conflict_holds,
    _source_rows_from_june11_consensus,
)


def test_june11_line52_semantics_preserve_xl_as_addition_not_full_replacement():
    rows = _source_rows_from_june11_consensus()
    by_sku_size = {(row.sku_key, row.my_size): row for row in rows}

    line52_s = by_sku_size[("CL_OC_MEN_LINE52_BLACK", "S")]
    line52_xl = by_sku_size[("CL_OC_MEN_LINE52_BLACK", "XL")]
    line52_3xl = by_sku_size[("CL_OC_MEN_LINE52_BLACK", "3XL")]

    assert line52_s.semantic == "FULL_SUPERSEDE"
    assert line52_s.quantity == 72
    assert line52_xl.semantic == "ADDITION"
    assert line52_xl.quantity == 12
    assert line52_3xl.semantic == "ADDITION"
    assert line52_3xl.quantity == 13


def test_owner_conflict_hold_blocks_line52_xl_activation():
    rows = [
        {
            "sku_id": "CL_OC_MEN_LINE52_BLACK_XL",
            "activation_recommendation": "ACTIVATE_OK_POSITIVE_TEMP_STOCK",
            "authority": "TEMP_OCR_OVERRIDE_OR_PRIOR_FRESHEST_PER_OWNER_PRECEDENCE",
            "source_semantic": "ADDITION",
            "candidate_action": "INSERT",
            "notes": "arrow on S row only; other rows are additions",
        }
    ]

    _apply_owner_conflict_holds(rows)

    assert OWNER_CONFLICT_HOLD_ROWS[0]["sku_id"] == "CL_OC_MEN_LINE52_BLACK_XL"
    assert rows[0]["activation_recommendation"] == "OWNER_CONFLICT_HOLD_DO_NOT_ACTIVATE_PENDING_RECOUNT"
    assert rows[0]["authority"] == "OWNER_CONFLICT_HOLD_SUPERSEDES_TEMP_ACTIVATION"
    assert rows[0]["candidate_action"] == "OWNER_HOLD"


def test_june11_mapping_flagged_families_are_parked_not_applied():
    rows = _source_rows_from_june11_consensus()
    safe_sku_keys = {row.sku_key for row in rows}
    parked = " ".join(row["family_guess"] for row in PARKED_JUNE11_ROWS)

    assert "3_in_1_with_logotypes" in parked
    assert "RUSH_WHITE / RUSH_BLACK" in parked
    assert "T-SHIRT short-sleeve WHITE / BLACK" in parked
    assert "RUSH_WHITE" not in safe_sku_keys
    assert "T-SHIRT short-sleeve WHITE / BLACK" not in safe_sku_keys


def test_rombik_s_uses_shared_pool_aliases():
    rows = _source_rows_from_june11_consensus()
    shared = [row for row in rows if row.stock_pool_id == "SHARED_ROMBIK_BLACK_S_MEN_KIDS"]

    assert len(shared) == 1
    assert shared[0].semantic == "ADDITION"
    assert shared[0].quantity == 1
    assert shared[0].applies_to_sku_ids == (
        "CL_NEW-CLO_MEN_ROMBIK_BLACK_S",
        "CL_NEW-CLO_KID_ROMBIK_BLACK_S",
    )
