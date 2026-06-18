from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_cash04_redeployment_discipline import build_redeployment_discipline_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_scoreboard(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gate_id", "status", "summary", "timestamp"])
        for gate_id, status in rows.items():
            writer.writerow([gate_id, status, "fixture", "20260618_1900"])


def _write_dashboard(path: Path, rows: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"gates": [{"id": gate_id, "status": status} for gate_id, status in rows.items()]}
    path.write_text("window.GP = " + json.dumps(payload) + ";\n", encoding="utf-8")


def _write_ledger(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "ledger_id",
        "tranche_id",
        "owner_decision_id",
        "proceeds_event_ref",
        "proceeds_amount_kzt",
        "proceeds_received_date",
        "redeployment_decision",
        "redeployment_amount_kzt",
        "redeployment_ref",
        "gate_snapshot",
        "allowed",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_config(path: Path, *, db_path: Path, scoreboard: Path, ledger: Path, dashboard: Path | None = None) -> None:
    _write_json(
        path,
        {
            "contract_id": "REDEPLOYMENT_DISCIPLINE_V1",
            "gate_id": "G-CASH-04",
            "db_path": str(db_path),
            "dashboard_path": str(dashboard) if dashboard else str(path.parent / "dashboard.js"),
            "scoreboard_path": str(scoreboard),
            "ledger_path": str(ledger),
            "effective_at": "2026-06-13T00:00:00+05:00",
            "liquidation_execution_gate": "G-LIQ-02",
            "required_green_before_redeployment": [
                "G-STOCK-03",
                "G-STOCK-05",
                "G-CASH-02",
                "G-CASH-03",
                "G-MET-01",
            ],
            "po_commitment_types": ["PO_PAYMENT"],
            "search_terms": ["liquidation", "tranche", "markdown", "redeploy"],
        },
    )


def _init_db(path: Path, *, liquidation_event: bool = False, draft_rows: int = 0, execution_rows: int = 0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            account TEXT NOT NULL,
            amount_kzt REAL NOT NULL,
            ref_type TEXT,
            ref_id TEXT,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'SYSTEM'
        );
        CREATE TABLE fact_cashflow_commitments (
            commit_id INTEGER PRIMARY KEY,
            commit_date TEXT NOT NULL,
            commit_type TEXT NOT NULL,
            amount_kzt REAL NOT NULL,
            probability REAL,
            scenario_tag TEXT,
            ref_id TEXT,
            notes TEXT
        );
        CREATE TABLE fact_po_draft (draft_id INTEGER PRIMARY KEY);
        CREATE TABLE fact_po_execution (execution_id INTEGER PRIMARY KEY);
        CREATE TABLE fact_po_lines (id INTEGER PRIMARY KEY);
        CREATE TABLE fact_cash_ledger (id INTEGER PRIMARY KEY);
        """
    )
    if liquidation_event:
        conn.execute(
            """
            INSERT INTO fact_cashflow_events(event_date, event_type, account, amount_kzt, ref_type, ref_id, notes, source)
            VALUES ('2026-06-18', 'CASH_IN', 'kaspi', 1000, 'liquidation', 'T1', 'liquidation proceeds held', 'TEST')
            """
        )
    for index in range(draft_rows):
        conn.execute("INSERT INTO fact_po_draft(draft_id) VALUES (?)", (index + 1,))
    for index in range(execution_rows):
        conn.execute("INSERT INTO fact_po_execution(execution_id) VALUES (?)", (index + 1,))
    conn.commit()
    conn.close()


def test_redeployment_guard_is_armed_before_liquidation_start(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    ledger = tmp_path / "ledger.csv"
    config = tmp_path / "config.json"
    _init_db(db)
    _write_scoreboard(
        scoreboard,
        {
            "G-LIQ-02": "PENDING",
            "G-STOCK-03": "GREEN",
            "G-STOCK-05": "GREEN",
            "G-CASH-02": "GREEN",
            "G-CASH-03": "GREEN",
            "G-MET-01": "ARMED",
        },
    )
    _write_ledger(ledger, [])
    _write_config(config, db_path=db, scoreboard=scoreboard, ledger=ledger)

    report = build_redeployment_discipline_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "ARMED"
    assert report["redeployment_allowed"] is False
    assert report["ungated_redeployment_count"] == 0
    assert any("liquidation_gate_not_green:G-LIQ-02=PENDING" in blocker for blocker in report["blockers"])


def test_redeployment_guard_is_red_when_money_moves_while_gates_not_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    ledger = tmp_path / "ledger.csv"
    config = tmp_path / "config.json"
    _init_db(db)
    _write_scoreboard(
        scoreboard,
        {
            "G-LIQ-02": "GREEN",
            "G-STOCK-03": "GREEN",
            "G-STOCK-05": "GREEN",
            "G-CASH-02": "RED",
            "G-CASH-03": "GREEN",
            "G-MET-01": "ARMED",
        },
    )
    _write_ledger(
        ledger,
        [
            {
                "ledger_id": "rd-1",
                "tranche_id": "T1",
                "owner_decision_id": "OD-011",
                "proceeds_event_ref": "cashflow:1",
                "proceeds_amount_kzt": "1000",
                "proceeds_received_date": "2026-06-18",
                "redeployment_decision": "BUY_STOCK",
                "redeployment_amount_kzt": "500",
                "redeployment_ref": "po:draft",
                "gate_snapshot": "G-CASH-02=RED;G-MET-01=ARMED",
                "allowed": "false",
                "notes": "fixture",
            }
        ],
    )
    _write_config(config, db_path=db, scoreboard=scoreboard, ledger=ledger)

    report = build_redeployment_discipline_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "RED"
    assert report["ungated_redeployment_count"] == 1
    assert any(row["ledger_id"] == "rd-1" for row in report["ungated_redeployments"])


def test_redeployment_guard_can_green_after_gate_stack_and_ledger_review(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    ledger = tmp_path / "ledger.csv"
    config = tmp_path / "config.json"
    _init_db(db, liquidation_event=True)
    _write_scoreboard(
        scoreboard,
        {
            "G-LIQ-02": "GREEN",
            "G-STOCK-03": "GREEN",
            "G-STOCK-05": "GREEN",
            "G-CASH-02": "GREEN",
            "G-CASH-03": "GREEN",
            "G-MET-01": "GREEN",
        },
    )
    _write_ledger(
        ledger,
        [
            {
                "ledger_id": "rd-1",
                "tranche_id": "T1",
                "owner_decision_id": "OD-011",
                "proceeds_event_ref": "cashflow:1",
                "proceeds_amount_kzt": "1000",
                "proceeds_received_date": "2026-06-18",
                "redeployment_decision": "HELD_AS_CASH",
                "redeployment_amount_kzt": "0",
                "redeployment_ref": "",
                "gate_snapshot": "all_green",
                "allowed": "true",
                "notes": "reviewed",
            }
        ],
    )
    _write_config(config, db_path=db, scoreboard=scoreboard, ledger=ledger)

    report = build_redeployment_discipline_report(config_path=config, output_root=tmp_path / "out")

    assert report["gate"] == "GREEN"
    assert report["redeployment_allowed"] is True
    assert report["proceeds_ledger_rows"] == 1
    assert report["ungated_redeployment_count"] == 0


def test_dashboard_supplies_pending_state_when_scoreboard_has_no_row(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    dashboard = tmp_path / "progress-data.js"
    ledger = tmp_path / "ledger.csv"
    config = tmp_path / "config.json"
    _init_db(db)
    _write_scoreboard(scoreboard, {"G-MET-01": "ARMED"})
    _write_dashboard(
        dashboard,
        {
            "G-LIQ-02": "PENDING",
            "G-STOCK-03": "GREEN",
            "G-STOCK-05": "GREEN",
            "G-CASH-02": "GREEN",
            "G-CASH-03": "GREEN",
            "G-MET-01": "PENDING",
        },
    )
    _write_ledger(ledger, [])
    _write_config(config, db_path=db, scoreboard=scoreboard, ledger=ledger, dashboard=dashboard)

    report = build_redeployment_discipline_report(config_path=config, output_root=tmp_path / "out")

    assert report["liquidation_gate_status"] == "PENDING"
    assert report["required_gate_statuses"]["G-MET-01"] == "ARMED"
