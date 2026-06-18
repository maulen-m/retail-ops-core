from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.apply_returned_to_warehouse_flags import (
    ENV_GATE,
    ReturnedToWarehouseFlagError,
    apply_returned_to_warehouse_flags,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_id TEXT,
                my_size TEXT,
                quantity INTEGER,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                returned_to_warehouse INTEGER,
                created_at TEXT,
                status_updated_at TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TRIGGER trg_orders_kaspi_updated
            AFTER UPDATE ON fact_orders_kaspi
            FOR EACH ROW
            BEGIN
                UPDATE fact_orders_kaspi
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
            """
        )
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, sku_id, my_size, quantity,
                kaspi_status, kaspi_status_detail, internal_status,
                returned_to_warehouse, created_at, status_updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("OLD", "ACMEWEAR", "SKU_OLD", "M", "ARCHIVE", "RETURNED", "RETURNED", 0, "2026-05-20", "2026-05-30"),
                ("NEW", "ACMEWEAR", "SKU_NEW", "L", "ARCHIVE", "RETURNED", "RETURNED", 0, "2026-06-01", "2026-06-15"),
                ("DONE", "STOREB", "SKU_DONE", "S", "ARCHIVE", "RETURNED", "RETURNED", 1, "2026-06-01", "2026-06-16"),
                ("COMP", "STOREB", "SKU_COMP", "S", "ARCHIVE", "COMPLETED", "COMPLETED", 0, "2026-06-01", "2026-06-16"),
            ],
        )


def test_dry_run_does_not_mutate_and_scopes_to_window(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    before = _sha256(db_path)

    summary = apply_returned_to_warehouse_flags(
        db_path=db_path,
        since=date(2026, 6, 1),
        until=date(2026, 6, 17),
        output_root=tmp_path / "out",
    )

    assert _sha256(db_path) == before
    assert summary["candidate_row_count"] == 1
    assert summary["candidate_order_count"] == 1
    assert summary["before"]["returned_rows"] == 2
    assert summary["before"]["flagged_rows"] == 1
    assert Path(summary["candidate_rows_csv"]).exists()


def test_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    monkeypatch.delenv(ENV_GATE, raising=False)

    with pytest.raises(ReturnedToWarehouseFlagError, match=ENV_GATE):
        apply_returned_to_warehouse_flags(
            db_path=db_path,
            since=date(2026, 6, 1),
            until=date(2026, 6, 17),
            output_root=tmp_path / "out",
            apply=True,
            backup_dir=tmp_path / "backups",
        )


def test_apply_flags_only_post_restoration_returned_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    monkeypatch.setenv(ENV_GATE, "1")

    summary = apply_returned_to_warehouse_flags(
        db_path=db_path,
        since=date(2026, 6, 1),
        until=date(2026, 6, 17),
        output_root=tmp_path / "out",
        apply=True,
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256(db_path),
    )

    assert summary["status"] == "APPLIED"
    assert summary["applied_row_count"] >= 1
    assert summary["after"]["coverage_rows_pct"] == 100.0
    assert summary["remaining_unflagged_row_count"] == 0
    assert Path(summary["backup_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("SELECT order_id, returned_to_warehouse FROM fact_orders_kaspi").fetchall())
    assert rows["NEW"] == 1
    assert rows["DONE"] == 1
    assert rows["OLD"] == 0
    assert rows["COMP"] == 0
