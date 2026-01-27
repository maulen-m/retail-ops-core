import os
import sqlite3
from pathlib import Path

from scripts.import_cashflow_commitments import import_commitments


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_commitments (
                commit_date TEXT,
                commit_type TEXT,
                amount_kzt REAL,
                probability REAL,
                scenario_tag TEXT,
                ref_id TEXT,
                notes TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_import_commitments_preserves_scenario_tag(tmp_path, monkeypatch):
    db_path = tmp_path / "commitments.db"
    _init_db(db_path)

    csv_path = tmp_path / "commitments.csv"
    csv_path.write_text(
        "\n".join(
            [
                "commit_date,amount_kzt,commit_type,scenario_tag,ref_id,notes",
                "2026-01-10,100.0,PO_PAYMENT,base,PO-TEST,base row",
                "2026-01-10,200.0,PO_PAYMENT,conservative,PO-TEST,cons row",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    import_commitments(csv_path, db_path, apply=True, replace=False)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT scenario_tag, amount_kzt FROM fact_cashflow_commitments ORDER BY amount_kzt"
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("base", 100.0), ("conservative", 200.0)]
