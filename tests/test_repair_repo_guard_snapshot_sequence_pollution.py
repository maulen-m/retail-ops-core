from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.repair_repo_guard_snapshot_sequence_pollution import (
    ENV_GATE,
    SnapshotSequenceCleanupError,
    repair_snapshot_sequence_pollution,
)


def _make_polluted_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_inventory_snapshot_size (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                current_stock INTEGER NOT NULL DEFAULT 0,
                inbound_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(snapshot_date, sku_id)
            );
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-06-16', 'SKU_A_M', 'SKU_A', 'M', 5, 0);
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2099-12-31', 'TEST_1', 'TEST', 'M', 1, 0);
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2099-12-31', 'TEST_2', 'TEST', 'L', 1, 0);
            DELETE FROM fact_inventory_snapshot_size WHERE snapshot_date='2099-12-31';
            """
        )


def _sha(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seq(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return int(
            conn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='fact_inventory_snapshot_size'"
            ).fetchone()[0]
        )


def test_snapshot_sequence_cleanup_dry_run_reports_gap(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_polluted_db(db_path)

    summary = repair_snapshot_sequence_pollution(
        db_path=db_path,
        apply=False,
        expected_pre_sha256=None,
        backup_dir=None,
        output=None,
        expected_current_seq=None,
        target_seq=None,
        expected_gap=None,
    )

    assert summary["state_before"]["current_seq"] == 3
    assert summary["state_before"]["max_rowid"] == 1
    assert summary["inferred_gap"] == 2
    assert summary["updated_row_count"] == 0
    assert _seq(db_path) == 3


def test_snapshot_sequence_cleanup_requires_apply_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_polluted_db(db_path)

    with pytest.raises(SnapshotSequenceCleanupError, match=ENV_GATE):
        repair_snapshot_sequence_pollution(
            db_path=db_path,
            apply=True,
            expected_pre_sha256=_sha(db_path),
            backup_dir=tmp_path / "backups",
            output=None,
            expected_current_seq=3,
            target_seq=1,
            expected_gap=2,
        )


def test_snapshot_sequence_cleanup_apply_resets_only_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_polluted_db(db_path)
    pre_sha = _sha(db_path)
    monkeypatch.setenv(ENV_GATE, "1")

    summary = repair_snapshot_sequence_pollution(
        db_path=db_path,
        apply=True,
        expected_pre_sha256=pre_sha,
        backup_dir=tmp_path / "backups",
        output=tmp_path / "summary.json",
        expected_current_seq=3,
        target_seq=1,
        expected_gap=2,
    )

    assert summary["updated_row_count"] == 1
    assert summary["state_after"]["current_seq"] == 1
    assert summary["state_after"]["row_count"] == 1
    assert summary["state_after"]["polluted_test_date_rows"] == 0
    assert Path(summary["backup_path"]).exists()
    assert _seq(db_path) == 1
