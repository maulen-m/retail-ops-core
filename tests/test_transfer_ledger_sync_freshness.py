from datetime import datetime, timedelta
from pathlib import Path

import sqlite3

from core.transfer_ledger import repository
from scripts import validate_transfer_ledger_sync_freshness as sync_check


def _write_config(path: Path, sources: list[str], max_age_hours: int) -> None:
    content = (
        "settings:\n"
        f"  max_age_hours: {max_age_hours}\n"
        "  required_sources:\n"
        + "".join([f"    - {s}\n" for s in sources])
    )
    path.write_text(content, encoding="utf-8")


def test_transfer_ledger_sync_freshness_pass(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()

    now = datetime.now().isoformat()
    repository.record_sync_log(
        "binance_p2p",
        success=True,
        last_run_ts=now,
        min_date_seen=now,
        max_date_seen=now,
        rows_total=1,
        rows_inserted=1,
        db_path=db_path,
    )

    config_path = tmp_path / "transfer_ledger_sync.yaml"
    _write_config(config_path, ["binance_p2p"], 25)
    monkeypatch.setattr(sync_check, "CONFIG_PATH", config_path)

    assert sync_check.validate(db_path) == 0


def test_transfer_ledger_sync_freshness_fails_when_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()

    config_path = tmp_path / "transfer_ledger_sync.yaml"
    _write_config(config_path, ["binance_p2p"], 25)
    monkeypatch.setattr(sync_check, "CONFIG_PATH", config_path)

    assert sync_check.validate(db_path) == 1


def test_transfer_ledger_sync_freshness_fails_when_stale(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    db_path.touch()

    stale = (datetime.now() - timedelta(hours=5)).isoformat()
    repository.ensure_schema(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO transfer_ledger_sync_log
            (source, last_run_ts, last_success_ts, min_date_seen, max_date_seen,
             rows_total, rows_inserted, errors_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            ("binance_p2p", stale, stale, stale, stale, 1, 1, 0),
        )
        conn.commit()

    config_path = tmp_path / "transfer_ledger_sync.yaml"
    _write_config(config_path, ["binance_p2p"], 1)
    monkeypatch.setattr(sync_check, "CONFIG_PATH", config_path)

    assert sync_check.validate(db_path) == 1
