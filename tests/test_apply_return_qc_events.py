from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.apply_return_qc_events import (
    ENV_GATE,
    ReturnQcApplyError,
    apply_return_qc_events,
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
                quantity INTEGER,
                kaspi_status_detail TEXT,
                internal_status TEXT,
                returned_to_warehouse INTEGER
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
                idempotency_key TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX ux_return_qc_event_idempotency
            ON return_qc_event(idempotency_key);
            """
        )
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, sku_id, quantity, kaspi_status_detail,
                internal_status, returned_to_warehouse
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("RET-1", "ACMEWEAR", "SKU_A_M", 1, "RETURNED", "RETURNED", 1),
                ("RET-2", "STOREB", "SKU_B_L", 2, "RETURNED", "RETURNED", 1),
                ("OPEN", "ACMEWEAR", "SKU_OPEN", 1, "COMPLETED", "COMPLETED", 0),
            ],
        )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    fields = [
        "store_code",
        "order_id",
        "sku_id",
        "quantity",
        "qc_status",
        "qc_ts",
        "accepted_active_qty",
        "quarantine_qty",
        "rejected_qty",
        "writeoff_qty",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_dry_run_plans_pass_and_fail_rows_without_mutating(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    input_csv = _write_csv(
        tmp_path / "qc.csv",
        [
            {"store_code": "ACMEWEAR", "order_id": "RET-1", "sku_id": "SKU_A_M", "quantity": "1", "qc_status": "PASS", "qc_ts": "2026-06-18T12:00:00+05:00"},
            {"store_code": "STOREB", "order_id": "RET-2", "sku_id": "SKU_B_L", "quantity": "2", "qc_status": "DEFECT", "qc_ts": "2026-06-18T12:01:00+05:00"},
        ],
    )
    before = _sha256(db_path)

    summary = apply_return_qc_events(
        db_path=db_path,
        input_csv=input_csv,
        output_root=tmp_path / "out",
    )

    assert _sha256(db_path) == before
    assert summary["status"] == "DRY_RUN"
    assert summary["planned_row_count"] == 2
    assert summary["accepted_active_qty"] == 1
    assert summary["writeoff_qty"] == 2
    assert Path(summary["planned_rows_csv"]).exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM return_qc_event").fetchone()[0] == 0


def test_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    input_csv = _write_csv(
        tmp_path / "qc.csv",
        [{"store_code": "ACMEWEAR", "order_id": "RET-1", "sku_id": "SKU_A_M", "quantity": "1", "qc_status": "PASS"}],
    )
    monkeypatch.delenv(ENV_GATE, raising=False)

    with pytest.raises(ReturnQcApplyError, match=ENV_GATE):
        apply_return_qc_events(
            db_path=db_path,
            input_csv=input_csv,
            output_root=tmp_path / "out",
            apply=True,
            backup_dir=tmp_path / "backups",
        )


def test_apply_inserts_idempotent_qc_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    input_csv = _write_csv(
        tmp_path / "qc.csv",
        [{"store_code": "ACMEWEAR", "order_id": "RET-1", "sku_id": "SKU_A_M", "quantity": "1", "qc_status": "PASS", "qc_ts": "2026-06-18T12:00:00+05:00"}],
    )
    monkeypatch.setenv(ENV_GATE, "1")

    first = apply_return_qc_events(
        db_path=db_path,
        input_csv=input_csv,
        output_root=tmp_path / "out1",
        apply=True,
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256(db_path),
    )
    assert first["status"] == "APPLIED"
    assert first["applied_row_count"] == 1
    assert Path(first["backup_path"]).exists()

    second = apply_return_qc_events(
        db_path=db_path,
        input_csv=input_csv,
        output_root=tmp_path / "out2",
        apply=True,
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256(db_path),
    )
    assert second["planned_row_count"] == 0
    assert second["skipped_existing_count"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT qc_status, accepted_active_qty, quarantine_qty, rejected_qty, writeoff_qty
            FROM return_qc_event
            """
        ).fetchone()
    assert row == ("PASS", 1, 0, 0, 0)


def test_rejects_non_returned_or_over_quantity_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_db(db_path)
    input_csv = _write_csv(
        tmp_path / "bad.csv",
        [{"store_code": "ACMEWEAR", "order_id": "OPEN", "sku_id": "SKU_OPEN", "quantity": "2", "qc_status": "PASS"}],
    )

    with pytest.raises(ReturnQcApplyError, match="order is not RETURNED|returned_to_warehouse|exceeds returned quantity"):
        apply_return_qc_events(
            db_path=db_path,
            input_csv=input_csv,
            output_root=tmp_path / "out",
        )
