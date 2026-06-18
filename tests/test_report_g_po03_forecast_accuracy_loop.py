from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.report_g_po03_forecast_accuracy_loop import build_forecast_accuracy_loop_report


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


def _write_config(
    path: Path,
    *,
    db_path: Path,
    scoreboard: Path,
    report_glob: str,
    auto_po_consumer: Path,
) -> None:
    _write_json(
        path,
        {
            "contract_id": "FORECAST_ACCURACY_BIAS_LOOP_V1",
            "gate_id": "G-PO-03",
            "db_path": str(db_path),
            "scoreboard_path": str(scoreboard),
            "accuracy_report_glob": report_glob,
            "auto_po_consumer_path": str(auto_po_consumer),
            "dependency_gates": ["G-PO-02"],
            "max_report_age_days": 30,
            "max_mape_pct": 30.0,
            "max_wmape_pct": 30.0,
            "max_abs_bias_pct": 5.0,
        },
    )


def _init_db(path: Path, *, accuracy_date: str = "2026-06-17", mape: float = 12.0, bias: float = 2.0) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
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
        """
    )
    conn.execute(
        "INSERT INTO fact_forecast_accuracy VALUES (?, 'SKU', 'ALL', 7, ?, ?, 24, 'v1')",
        (accuracy_date, mape, bias),
    )
    conn.commit()
    conn.close()


def _write_accuracy_csv(path: Path, *, mape: float, wmape: float, bias: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sku_key", "horizon_days", "mape", "wmape", "bias", "mae", "sample_size", "grade"])
        writer.writerow(["SKU", 7, mape, wmape, bias, 1.0, 24, "B"])


def test_stale_high_error_loop_is_armed(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    auto_po_consumer = tmp_path / "po_generator.py"
    reports = tmp_path / "reports"
    report_csv = reports / "forecast_accuracy_2025-12-06.csv"
    config = tmp_path / "config.json"
    _init_db(db, accuracy_date="2025-12-06", mape=93.74, bias=46.66)
    _write_accuracy_csv(report_csv, mape=93.74, wmape=72.76, bias=46.66)
    _write_scoreboard(scoreboard, {"G-PO-02": "ARMED"})
    auto_po_consumer.write_text("SELECT mape FROM fact_forecast_accuracy\n", encoding="utf-8")
    _write_config(
        config,
        db_path=db,
        scoreboard=scoreboard,
        report_glob=str(reports / "forecast_accuracy_*.csv"),
        auto_po_consumer=auto_po_consumer,
    )

    report = build_forecast_accuracy_loop_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["latest_report_date"] == "2025-12-06"
    assert report["latest_report_age_days"] == 194
    assert any("dependency_gate_not_green:G-PO-02=ARMED" in blocker for blocker in report["blockers"])
    assert any("avg_mape" in blocker for blocker in report["blockers"])
    assert any("avg_wmape" in blocker for blocker in report["blockers"])
    assert any("avg_bias" in blocker for blocker in report["blockers"])


def test_fresh_passing_loop_can_green(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    auto_po_consumer = tmp_path / "po_generator.py"
    reports = tmp_path / "reports"
    report_csv = reports / "forecast_accuracy_2026-06-17.csv"
    config = tmp_path / "config.json"
    _init_db(db, accuracy_date="2026-06-17", mape=12.0, bias=2.0)
    _write_accuracy_csv(report_csv, mape=12.0, wmape=10.0, bias=2.0)
    _write_scoreboard(scoreboard, {"G-PO-02": "GREEN"})
    auto_po_consumer.write_text("SELECT mape FROM fact_forecast_accuracy\n", encoding="utf-8")
    _write_config(
        config,
        db_path=db,
        scoreboard=scoreboard,
        report_glob=str(reports / "forecast_accuracy_*.csv"),
        auto_po_consumer=auto_po_consumer,
    )

    report = build_forecast_accuracy_loop_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["passed_checks"] == report["total_checks"]
    assert report["latest_report_avg_wmape"] == 10.0


def test_missing_accuracy_table_is_red(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    scoreboard = tmp_path / "scoreboard.csv"
    auto_po_consumer = tmp_path / "po_generator.py"
    reports = tmp_path / "reports"
    report_csv = reports / "forecast_accuracy_2026-06-17.csv"
    config = tmp_path / "config.json"
    sqlite3.connect(db).close()
    _write_accuracy_csv(report_csv, mape=12.0, wmape=10.0, bias=2.0)
    _write_scoreboard(scoreboard, {"G-PO-02": "GREEN"})
    auto_po_consumer.write_text("SELECT mape FROM fact_forecast_accuracy\n", encoding="utf-8")
    _write_config(
        config,
        db_path=db,
        scoreboard=scoreboard,
        report_glob=str(reports / "forecast_accuracy_*.csv"),
        auto_po_consumer=auto_po_consumer,
    )

    report = build_forecast_accuracy_loop_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T19:00:00+05:00",
    )

    assert report["gate"] == "RED"
    assert "missing_table:fact_forecast_accuracy" in report["fatal_errors"]
