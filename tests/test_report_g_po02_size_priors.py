from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_po02_size_priors import build_size_priors_report


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


def _write_config(path: Path, *, db_path: Path, scoreboard: Path, run_dashboard: bool = False) -> None:
    _write_json(
        path,
        {
            "contract_id": "PO_SIZE_PRIORS_REBUILD_V1",
            "gate_id": "G-PO-02",
            "db_path": str(db_path),
            "scoreboard_path": str(scoreboard),
            "dependency_gates": ["G-COGS-04", "G-STOCK-03", "G-RET-02"],
            "max_prior_age_days": 30,
            "max_forecast_age_days": 30,
            "max_mape_pct": 30.0,
            "run_dashboard_invariants": run_dashboard,
        },
    )


def _init_db(path: Path, *, fresh: bool) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_size_probability (
            id INTEGER PRIMARY KEY,
            level TEXT NOT NULL,
            key_value TEXT NOT NULL,
            mode_size TEXT NOT NULL,
            mode_share REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            confidence TEXT NOT NULL,
            size_distribution TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE fact_forecast_accuracy (
            accuracy_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            store_code TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            mape REAL NOT NULL,
            bias REAL NOT NULL,
            sample_size INTEGER NOT NULL,
            model_version TEXT
        );
        CREATE TABLE fact_demand_forecast (
            forecast_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            store_code TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            predicted_units REAL NOT NULL
        );
        CREATE TABLE fact_po_draft (draft_id INTEGER PRIMARY KEY);
        CREATE TABLE fact_po_execution (execution_id INTEGER PRIMARY KEY);
        """
    )
    prior_date = "2026-06-17" if fresh else "2025-12-07"
    forecast_date = "2026-06-17" if fresh else "2025-12-06"
    mape = 12.0 if fresh else 93.74
    conn.executemany(
        """
        INSERT INTO dim_size_probability(level, key_value, mode_size, mode_share, sample_count, confidence, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("OFFER", "SKU", "XL", 0.5, 250, "HIGH", prior_date),
            ("PRODUCT_TYPE", "CL", "L", 0.4, 200, "MEDIUM", prior_date),
            ("STYLE", "SUIT", "XL", 0.45, 300, "HIGH", prior_date),
        ],
    )
    conn.execute(
        "INSERT INTO fact_forecast_accuracy VALUES (?, 'SKU', 'ALL', 7, ?, 2.0, 50, 'v1')",
        (forecast_date, mape),
    )
    conn.execute(
        "INSERT INTO fact_demand_forecast VALUES (?, ?, 'SKU', 'ALL', 7, 10)",
        (forecast_date, forecast_date),
    )
    conn.commit()
    conn.close()


def test_stale_priors_are_armed(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _init_db(db, fresh=False)
    _write_scoreboard(scoreboard, {"G-COGS-04": "GREEN", "G-STOCK-03": "GREEN", "G-RET-02": "ARMED"})
    _write_config(config, db_path=db, scoreboard=scoreboard)

    report = build_size_priors_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["prior_latest_updated_at"].startswith("2025-12-07")
    assert any("dependency_gate_not_green:G-RET-02=ARMED" in blocker for blocker in report["blockers"])
    assert any("prior_age_days" in blocker for blocker in report["blockers"])


def test_fresh_priors_and_green_dependencies_can_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    _init_db(db, fresh=True)
    _write_scoreboard(scoreboard, {"G-COGS-04": "GREEN", "G-STOCK-03": "GREEN", "G-RET-02": "GREEN"})
    _write_config(config, db_path=db, scoreboard=scoreboard)

    report = build_size_priors_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["passed_checks"] == report["total_checks"]
    assert report["forecast_accuracy_avg_mape"] == 12.0
