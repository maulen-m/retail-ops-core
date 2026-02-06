import sqlite3
from pathlib import Path

from scripts.validate_single_truth_alignment import validate_alignment_payload


def _seed_po_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_line (
            po_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            order_qty INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO po_line (po_id, sku_key, my_size, order_qty) VALUES (?, ?, ?, ?)",
        [
            ("PO-5", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 110),
            ("PO-5", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 240),
        ],
    )
    conn.commit()
    conn.close()


def test_validate_alignment_flags_real_archive_qty_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 999,
                        "baseline_snapshot_date": "2026-01-21",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert any("po_line" in err and "PO-5" in err for err in errors)


def test_validate_alignment_flags_snapshot_after_message_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-01-22",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert any("baseline_snapshot_date" in err for err in errors)
