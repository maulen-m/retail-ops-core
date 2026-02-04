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
