from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_ret03_comeback_rate import build_comeback_rate_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_scoreboard(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gate_id", "state", "evidence", "dated"])
        for gate_id, state in rows.items():
            writer.writerow([gate_id, state, "fixture", "20260618_1900"])


def _write_config(path: Path, *, db_path: Path, scoreboard: Path) -> None:
    _write_json(
        path,
        {
            "contract_id": "RETURN_COMEBACK_RATE_V1",
            "gate_id": "G-RET-03",
            "db_path": str(db_path),
            "scoreboard_path": str(scoreboard),
            "dependency_gate": "G-RET-02",
            "maturity_days": 30,
            "required_qc_telemetry_days": 30,
            "pass_statuses": ["PASS", "PASSED", "SELLABLE", "ACCEPTED", "OK"],
        },
    )


def _init_db(path: Path, *, qc_rows: list[tuple] | None = None) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_id TEXT,
            quantity INTEGER DEFAULT 1,
            internal_status TEXT,
            kaspi_status_detail TEXT,
            returned_to_warehouse INTEGER DEFAULT 0,
            status_updated_at TEXT,
            updated_at TEXT,
            created_at TEXT
        );
        CREATE TABLE return_qc_event (
            qc_event_id TEXT PRIMARY KEY,
            store_code TEXT NOT NULL,
            order_id TEXT NOT NULL,
            order_entry_id TEXT,
            sku_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            return_stage TEXT,
            qc_status TEXT NOT NULL,
            qc_ts TEXT,
            accepted_active_qty INTEGER NOT NULL DEFAULT 0,
            quarantine_qty INTEGER NOT NULL DEFAULT 0,
            rejected_qty INTEGER NOT NULL DEFAULT 0,
            writeoff_qty INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            idempotency_key TEXT NOT NULL
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY,
            event_date TEXT,
            event_type TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            qty_change INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            notes TEXT,
            input_source TEXT,
            idempotency_key TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi(
            order_id, store_code, sku_id, quantity, internal_status,
            kaspi_status_detail, returned_to_warehouse, status_updated_at, updated_at, created_at
        ) VALUES (?, 'UNIVERSAL', 'SKU', 1, 'RETURNED', 'RETURNED', 1, ?, ?, ?)
        """,
        [
            ("r-old-1", "2026-05-01", "2026-05-01", "2026-05-01"),
            ("r-old-2", "2026-05-03", "2026-05-03", "2026-05-03"),
            ("r-new-1", "2026-06-12", "2026-06-12", "2026-06-12"),
        ],
    )
    for row in qc_rows or []:
        conn.execute(
            """
            INSERT INTO return_qc_event(
                qc_event_id, store_code, order_id, sku_id, quantity, qc_status, qc_ts,
                accepted_active_qty, quarantine_qty, rejected_qty, writeoff_qty, source, idempotency_key
            ) VALUES (?, 'UNIVERSAL', ?, 'SKU', 1, ?, ?, ?, 0, 0, ?, 'TEST', ?)
            """,
            row,
        )
    conn.commit()
    conn.close()


def test_no_qc_telemetry_is_armed_not_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _init_db(db)
    _write_scoreboard(scoreboard, {"G-RET-02": "ARMED"})
    _write_config(config, db_path=db, scoreboard=scoreboard)

    report = build_comeback_rate_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["return_qc_event_count"] == 0
    assert report["eligible_returned_orders"] == 2
    assert report["comeback_rate"] is None
    assert any("return_qc_event_count=0" in blocker for blocker in report["blockers"])


def test_qc_telemetry_under_30_days_is_armed(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _init_db(
        db,
        qc_rows=[
            ("qc-1", "r-old-1", "PASS", "2026-06-10T10:00:00+05:00", 1, 0, "key-1"),
            ("qc-2", "r-old-2", "FAIL", "2026-06-12T10:00:00+05:00", 0, 1, "key-2"),
        ],
    )
    _write_scoreboard(scoreboard, {"G-RET-02": "GREEN"})
    _write_config(config, db_path=db, scoreboard=scoreboard)

    report = build_comeback_rate_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["qc_telemetry_days"] == 3
    assert report["comeback_rate"] == 0.5
    assert any("qc_telemetry_days=3<30" in blocker for blocker in report["blockers"])


def test_mature_qc_telemetry_can_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _init_db(
        db,
        qc_rows=[
            ("qc-1", "r-old-1", "PASS", "2026-05-01T10:00:00+05:00", 1, 0, "key-1"),
            ("qc-2", "r-old-2", "FAIL", "2026-05-31T10:00:00+05:00", 0, 1, "key-2"),
        ],
    )
    _write_scoreboard(scoreboard, {"G-RET-02": "GREEN"})
    _write_config(config, db_path=db, scoreboard=scoreboard)

    report = build_comeback_rate_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["eligible_returned_orders"] == 2
    assert report["qc_passed_reentered_orders"] == 1
    assert report["comeback_rate"] == 0.5
