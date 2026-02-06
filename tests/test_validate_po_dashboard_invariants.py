import sqlite3
from pathlib import Path

from scripts.validate_po_dashboard_invariants import validate_payload


def _make_db(db_path: Path, with_portfolio: bool = True) -> None:
    conn = sqlite3.connect(str(db_path))
    if with_portfolio:
        conn.execute(
            """
            CREATE TABLE portfolio_active (
                sku_key TEXT PRIMARY KEY,
                active_flag INTEGER DEFAULT 1
            )
            """
        )
    conn.commit()
    conn.close()


def test_missing_portfolio_table_is_error(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, with_portfolio=False)

    payload = {
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=db_path, strict_portfolio=True)
    assert any("portfolio_active" in err for err in errors)


def test_portfolio_coverage_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, with_portfolio=True)
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        "INSERT INTO portfolio_active (sku_key, active_flag) VALUES (?, 1)",
        [("SKU_A",), ("SKU_B",)],
    )
    conn.commit()
    conn.close()

    payload = {
        "summary": {"total_skus": 1},
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [
                    {"sku_key": "SKU_A", "notes": ""},
                ],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=db_path, strict_portfolio=True)
    assert any("coverage" in err or "Portfolio" in err for err in errors)


def test_fatal_fallback_notes_block(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, with_portfolio=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO portfolio_active (sku_key, active_flag) VALUES ('SKU_A', 1)"
    )
    conn.commit()
    conn.close()

    payload = {
        "summary": {"total_skus": 1},
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [
                    {"sku_key": "SKU_A", "notes": "NO_DEMAND_ESTIMATE"},
                ],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=db_path, strict_portfolio=True)
    assert any("NO_DEMAND_ESTIMATE" in err for err in errors)


def test_real_pos_min_fields_enforced(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, with_portfolio=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO portfolio_active (sku_key, active_flag) VALUES ('SKU_A', 1)"
    )
    conn.commit()
    conn.close()

    payload = {
        "summary": {"total_skus": 1},
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [
                    {"sku_key": "SKU_A", "notes": ""},
                ],
            }
        },
        "archived_pos": [],
        "real_pos": [
            {
                "po_id": "PO-1",
                "status": "IN_TRANSIT",
                "message_date": None,
                "units_total": 0,
            }
        ],
    }

    errors = validate_payload(payload, db_path=db_path, strict_portfolio=True)
    assert any("real_pos" in err for err in errors)


def test_post_doc_monotonicity_enforced() -> None:
    payload = {
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [
                    {
                        "sku_key": "CL_TEST",
                        "po_qty_total": 10,
                        "d_sku": 2.0,
                        "pre_arr_doc": 5.0,
                        "post_arr_doc": 5.0,
                    }
                ],
                "size_level": [
                    {
                        "sku_key": "CL_TEST",
                        "size": "M",
                        "order_qty": 10,
                        "d_size": 2.0,
                        "pre_arr_doc": 5.0,
                        "post_arr_doc": 5.0,
                        "pre_arrival": 5,
                        "target": 20,
                        "deficit_size": 10,
                    }
                ],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("post_arr_doc" in err for err in errors)


def test_real_archive_post_doc_formula_mismatch_fails() -> None:
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 1215,
                        "d_sku": 20.0,
                        "pre_arrival": 0,
                        "pre_arr_doc": 0.0,
                        "post_arr_doc": 99.2,
                        "consumption_until_arrival": 700.0,
                        "consumption_until_arrival_capped": 115.0,
                    }
                ],
                "size_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "size": "M",
                        "order_qty": 110,
                        "d_size": 1.8,
                        "pre_arr_doc": 0.0,
                        "post_arr_doc": 61.1,
                        "pre_arrival": 0,
                        "target": 0,
                        "deficit_size": 0,
                    }
                ],
            }
        },
        "archived_pos": ["PO-5"],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("formula" in err and "post_arr_doc" in err for err in errors)


def test_real_archive_requires_capped_consumption_field() -> None:
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 1215,
                        "d_sku": 20.0,
                        "pre_arrival": 0,
                        "pre_arr_doc": 0.0,
                        "post_arr_doc": 60.8,
                        "consumption_until_arrival": 700.0,
                    }
                ],
                "size_level": [],
            }
        },
        "archived_pos": ["PO-5"],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("consumption_until_arrival_capped" in err for err in errors)
