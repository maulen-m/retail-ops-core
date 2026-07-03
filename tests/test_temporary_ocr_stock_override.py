from scripts.materialize_temporary_ocr_stock_override import (
    BLACK_TSHIRT_OOS_EVENT_DATE,
    BLACK_TSHIRT_OOS_EVENT_TS,
    OWNER_CONFLICT_HOLD_ROWS,
    PARKED_JUNE11_ROWS,
    _apply_owner_conflict_holds,
    _source_rows_from_owner_black_tshirt_oos,
    _source_rows_from_recovered_returns,
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


def test_recovered_returns_line52_totals_and_zero_trace_rows():
    rows, trace_rows, parked_rows = _source_rows_from_recovered_returns()
    line52 = [row for row in rows if row.sku_key == "CL_OC_MEN_LINE52_BLACK"]
    totals = {}
    for row in line52:
        totals[row.my_size] = totals.get(row.my_size, 0) + row.quantity

    assert totals == {
        "M": 2,
        "L": 5,
        "XL": 16,
        "2XL": 8,
        "3XL": 15,
        "4XL": 6,
    }
    assert any(
        row["product_label"] == "line52 black"
        and row["my_size"] == "S"
        and row["quantity"] == 0
        and row["status"] == "trace_only_zero"
        for row in trace_rows
    )
    assert all("LINE31" in row["family_guess"] for row in parked_rows)


def test_recovered_returns_cover_every_source_image():
    _, trace_rows, _ = _source_rows_from_recovered_returns()
    image_names = {row["source_image"].rsplit("/", 1)[-1] for row in trace_rows}

    assert image_names == {
        "Kids_3_in_1.jpg",
        "ROMBIK_men.jpg",
        "Line61.jpg",
        "LINE31.jpg",
        "line51.jpg",
        "line52.jpg",
        "rombik_men_and_kids.JPG",
        "beli_ts_21.JPG",
        "blk_ts21.JPG",
        "LINE31.JPG",
        "line51.JPG",
        "Line61.JPG",
        "line52.JPG",
    }


def test_recovered_returns_rombik_s_uses_shared_pool_aliases():
    rows, _, _ = _source_rows_from_recovered_returns()
    shared = [
        row for row in rows
        if row.stock_pool_id == "SHARED_ROMBIK_BLACK_S_MEN_KIDS"
        and row.batch_id.startswith("ASTANA_RETURNS_RECOVERED_READY_TO_SELL")
    ]

    assert len(shared) == 2
    assert sum(row.quantity for row in shared) == 2
    assert shared[0].applies_to_sku_ids == (
        "CL_NEW-CLO_MEN_ROMBIK_BLACK_S",
        "CL_NEW-CLO_KID_ROMBIK_BLACK_S",
    )


def test_owner_black_tshirt_oos_rows_full_supersede_active_sizes_to_zero():
    rows = _source_rows_from_owner_black_tshirt_oos()

    assert [row.my_size for row in rows] == ["S", "M", "L", "XL", "2XL", "3XL"]
    assert {row.sku_key for row in rows} == {"CL_NEW-CLO_MEN_T-SHIRT_BLACK"}
    assert {row.semantic for row in rows} == {"FULL_SUPERSEDE"}
    assert {row.quantity for row in rows} == {0}
    assert {row.event_ts for row in rows} == {BLACK_TSHIRT_OOS_EVENT_TS}
    assert {row.event_date for row in rows} == {BLACK_TSHIRT_OOS_EVENT_DATE}
    assert {row.confidence for row in rows} == {"OWNER_CONFIRMED"}
    assert all("20260628_black_tshirt_oos.md" in row.source_doc for row in rows)
