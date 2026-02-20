import json
import sqlite3
from pathlib import Path

from scripts.backfill_order_entries_offer_id import backfill_offer_id


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            offer_id TEXT,
            raw_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def test_backfill_offer_id_from_raw_json(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    payload = {
        "attributes": {
            "offer": {
                "code": "CL_OC_MEN_LINE52_BLACK_S_117313518",
                "name": "Some Offer",
            }
        }
    }
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO fact_order_entries_kaspi (entry_id, order_id, offer_id, raw_json) VALUES (?, ?, ?, ?)",
        ("entry-1", "777", None, json.dumps(payload)),
    )
    conn.commit()
    conn.close()

    stats = backfill_offer_id(db_path=db_path, apply=True)
    assert stats["updated"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT offer_id FROM fact_order_entries_kaspi WHERE entry_id='entry-1'"
    ).fetchone()
    conn.close()
    assert row[0] == "CL_OC_MEN_LINE52_BLACK_S_117313518"


def test_backfill_offer_id_skips_missing_code(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    payload = {"attributes": {"offer": {"name": "No code"}}}
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO fact_order_entries_kaspi (entry_id, order_id, offer_id, raw_json) VALUES (?, ?, ?, ?)",
        ("entry-2", "888", None, json.dumps(payload)),
    )
    conn.commit()
    conn.close()

    stats = backfill_offer_id(db_path=db_path, apply=True)
    assert stats["missing_code"] == 1
