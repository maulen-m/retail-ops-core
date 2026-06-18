from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.report_g_met04_capital_hours import build_capital_hours_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_db(path: Path, *, with_rows: bool = True, qc_rows: int = 0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_cashflow_daily (
            date TEXT PRIMARY KEY,
            inventory_on_hand_open REAL DEFAULT 0,
            inventory_on_hand_close REAL DEFAULT 0,
            inventory_inbound_open REAL DEFAULT 0,
            inventory_inbound_close REAL DEFAULT 0,
            inventory_on_delivery_open REAL DEFAULT 0,
            inventory_on_delivery_close REAL DEFAULT 0,
            receivables_open REAL DEFAULT 0,
            receivables_close REAL DEFAULT 0
        );
        CREATE TABLE return_qc_event (
            qc_event_id TEXT PRIMARY KEY,
            qc_ts TEXT
        );
        """
    )
    if with_rows:
        conn.executemany(
            """
            INSERT INTO fact_cashflow_daily(
                date,
                inventory_on_hand_open, inventory_on_hand_close,
                inventory_inbound_open, inventory_inbound_close,
                inventory_on_delivery_open, inventory_on_delivery_close,
                receivables_open, receivables_close
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-15", 100, 120, 300, 300, 20, 10, 0, 0),
                ("2026-06-16", 120, 140, 300, 250, 10, 0, 0, 0),
            ],
        )
    for index in range(qc_rows):
        conn.execute(
            "INSERT INTO return_qc_event(qc_event_id, qc_ts) VALUES (?, ?)",
            (f"qc-{index}", "2026-06-16T12:00:00+05:00"),
        )
    conn.commit()
    conn.close()


def _write_config(path: Path, *, db_path: Path, required_stages: list[str], require_qc: bool = True) -> None:
    _write_json(
        path,
        {
            "contract_id": "CAPITAL_HOURS_STAGE_LEDGER_V1",
            "gate_id": "G-MET-04",
            "db_path": str(db_path),
            "period_days": 7,
            "max_latest_daily_lag_days": 2,
            "required_stages": required_stages,
            "return_qc_required_for_green": require_qc,
            "dedicated_stage_event_ledger_required_for_green": False,
            "stage_sources": [
                {
                    "stage": "on_hand",
                    "source_table": "fact_cashflow_daily",
                    "open_column": "inventory_on_hand_open",
                    "close_column": "inventory_on_hand_close",
                },
                {
                    "stage": "on_delivery",
                    "source_table": "fact_cashflow_daily",
                    "open_column": "inventory_on_delivery_open",
                    "close_column": "inventory_on_delivery_close",
                },
                {
                    "stage": "receivable",
                    "source_table": "fact_cashflow_daily",
                    "open_column": "receivables_open",
                    "close_column": "receivables_close",
                },
            ],
            "stage_event_ledger_candidates": [],
            "source_tables_for_context": ["fact_cashflow_daily", "return_qc_event"],
        },
    )


def test_missing_target_stages_are_armed_not_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db)
    _write_config(
        config,
        db_path=db,
        required_stages=["paid_supplier", "on_hand", "on_delivery", "returned", "quarantine", "receivable"],
    )

    report = build_capital_hours_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:40:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["stage_count_measured"] == 3
    assert any("stage_source_missing:paid_supplier" in blocker for blocker in report["measurement_blockers"])
    assert any("return_qc_event_count=0" in blocker for blocker in report["measurement_blockers"])


def test_available_stages_can_green_when_required_scope_is_measured(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db, qc_rows=1)
    _write_config(
        config,
        db_path=db,
        required_stages=["on_hand", "on_delivery", "receivable"],
    )

    report = build_capital_hours_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:40:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["period_start"] == "2026-06-15"
    assert report["period_end"] == "2026-06-16"
    assert report["stage_hours_by_stage"]["on_hand"]["capital_hours"] == 5760.0
    assert report["measurement_blockers"] == []


def test_no_cashflow_rows_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    config = tmp_path / "config.json"
    _write_db(db, with_rows=False)
    _write_config(config, db_path=db, required_stages=["on_hand"], require_qc=False)

    report = build_capital_hours_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:40:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("latest_cashflow_date_present" in blocker for blocker in report["blockers"])
