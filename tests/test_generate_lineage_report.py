from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.generate_lineage_report import generate_lineage_report


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            quantity REAL,
            net_rev REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE fact_cashflow_events (
            event_date TEXT,
            amount_kzt REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (order_id, order_date, quantity, net_rev, status, return_flag)
        VALUES ('O1', '2026-02-08', 2, 10000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        "INSERT INTO fact_cashflow_events (event_date, amount_kzt) VALUES ('2026-02-08', 5000)"
    )
    conn.commit()
    conn.close()


def test_lineage_report_is_deterministic_with_fixed_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    output = tmp_path / "lineage.json"
    _init_db(db_path)
    workbook.write_text("fixture-workbook", encoding="utf-8")

    report = generate_lineage_report(
        db_path=db_path,
        workbook_path=workbook,
        output_path=output,
        strict_exit_code=0,
        generated_at="2026-02-13T12:00:00Z",
    )

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["generated_at"] == "2026-02-13T12:00:00Z"
    assert payload["strict_exit_code"] == 0
    assert payload["sales_truth"]["line_count"] == 1
    assert payload["cashflow"]["event_count"] == 1
    assert report["workbook"]["sha256"]


def test_lineage_report_handles_missing_workbook(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    output = tmp_path / "lineage.json"
    _init_db(db_path)

    report = generate_lineage_report(
        db_path=db_path,
        workbook_path=None,
        output_path=output,
        strict_exit_code=1,
        generated_at="2026-02-13T12:00:00Z",
    )

    assert report["workbook"]["path"] is None
    assert report["workbook"]["sha256"] is None
