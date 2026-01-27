import sqlite3
from datetime import date
from pathlib import Path

from scripts import update_cashflow_dashboard as dashboard


def test_trust_counts_classification():
    rows = [
        {"date": "2026-01-01", "is_forecast": False},
        {"date": "2026-01-02", "is_forecast": False},
        {"date": "2026-01-03", "is_forecast": False},
        {"date": "2026-01-04", "is_forecast": True},
    ]
    manual_dates = {"2026-01-02"}
    counts = dashboard._compute_trust_counts(rows, "2026-01-01", manual_dates)
    assert counts["statement_days"] == 1
    assert counts["manual_days"] == 1
    assert counts["modelled_days"] == 1
    assert counts["forecast_days"] == 1


def _init_drift_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_events (
                event_date TEXT,
                event_type TEXT,
                amount_kzt REAL,
                source TEXT
            );
            CREATE TABLE kaspi_order_sync_log (
                store_code TEXT PRIMARY KEY,
                last_success_ts TEXT,
                min_date_seen TEXT,
                max_date_seen TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_drift_report_insufficient_coverage(tmp_path, monkeypatch):
    db_path = tmp_path / "drift.db"
    _init_drift_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO kaspi_order_sync_log (store_code, last_success_ts, min_date_seen, max_date_seen)
            VALUES (?, ?, ?, ?)
            """,
            ("TEST", "2026-01-05T00:00:00", "2026-01-01", "2026-01-03"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(dashboard, "_load_required_stores", lambda: ["TEST"])

    out_path = tmp_path / "drift.md"
    conn = sqlite3.connect(str(db_path))
    try:
        dashboard._write_drift_report(conn, out_path, "2026-01-10", lookback_days=5)
    finally:
        conn.close()

    content = out_path.read_text(encoding="utf-8")
    assert "INSUFFICIENT COVERAGE" in content


def test_drift_report_respects_api_window(tmp_path, monkeypatch):
    db_path = tmp_path / "drift_ok.db"
    _init_drift_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO kaspi_order_sync_log (store_code, last_success_ts, min_date_seen, max_date_seen)
            VALUES (?, ?, ?, ?)
            """,
            ("TEST", "2026-01-05T00:00:00", "2026-01-01", "2026-01-10"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(dashboard, "_load_required_stores", lambda: ["TEST"])

    out_path = tmp_path / "drift_ok.md"
    conn = sqlite3.connect(str(db_path))
    try:
        dashboard._write_drift_report(conn, out_path, "2026-01-10", lookback_days=5)
    finally:
        conn.close()

    content = out_path.read_text(encoding="utf-8")
    assert "coverage_status: OK" in content
