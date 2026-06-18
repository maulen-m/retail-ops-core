import sqlite3

import pytest

from scripts.repair_repo_guard_alert_log_pollution import (
    ENV_GATE,
    EXPECTED_ROWS,
    RepoGuardAlertLogCleanupError,
    _sha256_file,
    repair_alert_log_pollution,
)


def _seed_alert_log(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE fact_alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_date TEXT NOT NULL,
                alert_time TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'SENT',
                external_id TEXT,
                suppression_reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        for row in EXPECTED_ROWS:
            conn.execute(
                """
                INSERT INTO fact_alert_log
                (id, alert_date, alert_time, alert_type, channel, store_code,
                 sku_key, message, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["alert_date"],
                    row["alert_time"],
                    row["alert_type"],
                    row["channel"],
                    row["store_code"],
                    row["sku_key"],
                    row["message"],
                    row["status"],
                ),
            )
        conn.execute(
            """
            INSERT INTO fact_alert_log
            (alert_date, alert_time, alert_type, channel, store_code,
             sku_key, message, status)
            VALUES ('2026-06-16', '2026-06-16 15:00:00', 'REORDER',
                    'telegram', 'REAL_STORE', 'REAL_SKU', 'keep', 'SENT')
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_count(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM fact_alert_log").fetchone()[0]
    finally:
        conn.close()


def test_dry_run_does_not_delete(tmp_path):
    db_path = tmp_path / "app.db"
    _seed_alert_log(db_path)

    summary = repair_alert_log_pollution(
        db_path=db_path,
        apply=False,
        expected_pre_sha256=None,
        backup_dir=None,
        output=None,
    )

    assert summary["matched_row_count"] == len(EXPECTED_ROWS)
    assert summary["deleted_row_count"] == 0
    assert _row_count(db_path) == len(EXPECTED_ROWS) + 1


def test_apply_requires_env_gate(tmp_path):
    db_path = tmp_path / "app.db"
    _seed_alert_log(db_path)

    with pytest.raises(RepoGuardAlertLogCleanupError, match=ENV_GATE):
        repair_alert_log_pollution(
            db_path=db_path,
            apply=True,
            expected_pre_sha256=_sha256_file(db_path),
            backup_dir=tmp_path / "backups",
            output=None,
        )


def test_apply_deletes_only_exact_pollution_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    _seed_alert_log(db_path)
    pre_sha = _sha256_file(db_path)
    monkeypatch.setenv(ENV_GATE, "1")

    summary = repair_alert_log_pollution(
        db_path=db_path,
        apply=True,
        expected_pre_sha256=pre_sha,
        backup_dir=tmp_path / "backups",
        output=None,
    )

    assert summary["deleted_row_count"] == len(EXPECTED_ROWS)
    assert summary["remaining_matched_row_count"] == 0
    assert summary["backup_integrity_check"] == "ok"
    assert _row_count(db_path) == 1
