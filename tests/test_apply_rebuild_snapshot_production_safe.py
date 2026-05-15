from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from scripts.apply_rebuild_snapshot_production_safe import (
    PRODUCTION_ENV_GATE,
    ProductionSnapshotApplyError,
    apply_rebuild_snapshot_production_safe,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_snapshot_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                active_flag INTEGER
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT,
                my_size TEXT,
                active_flag INTEGER
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date DATE NOT NULL,
                event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                qty_change INTEGER NOT NULL,
                running_balance INTEGER,
                reference_id TEXT,
                reference_type TEXT,
                kaspi_offer_name TEXT,
                notes TEXT,
                input_source TEXT DEFAULT 'SYSTEM',
                created_by TEXT DEFAULT 'system',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                idempotency_key TEXT
            );
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
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                order_date TEXT,
                sku_id TEXT,
                quantity INTEGER,
                status TEXT
            );
            CREATE TABLE fact_po_lines (
                po_id TEXT,
                sku_id TEXT,
                sku_key TEXT,
                my_size TEXT,
                actual_arrival_date TEXT,
                est_arrival_date TEXT,
                received_qty INTEGER DEFAULT 0,
                order_quantity INTEGER DEFAULT 0,
                status TEXT
            );
            """
        )
        conn.execute("INSERT INTO dim_sku VALUES ('SKU_A', 1)")
        conn.execute("INSERT INTO dim_sku_size VALUES ('SKU_A_M', 'SKU_A', 'M', 1)")
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, running_balance
            ) VALUES ('2026-05-03', 'INITIAL', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 7, 7)
            """
        )
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-05-04', 'SKU_A_M', 'SKU_A', 'M', 2, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-05-02', 'SKU_A_M', 'SKU_A', 'M', 10, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_id, quantity, status
            ) VALUES ('ORDER_SIM_1', '2026-05-03', 'SKU_A_M', 3, 'DELIVERED')
            """
        )


def _call_wrapper(
    *,
    db_path: Path,
    output_root: Path,
    backup_dir: Path,
    expected_pre_sha256: str,
    expected_existing_rows: int = 1,
    expected_rows_created: int = 1,
    expected_current_stock_total: int = 7,
    expected_inbound_stock_total: int = 0,
    apply: bool = False,
    mode: str = "ledger",
) -> dict:
    return apply_rebuild_snapshot_production_safe(
        db_path=db_path,
        snapshot_date=date(2026, 5, 4),
        store_code="UNIVERSAL",
        mode=mode,
        output_root=output_root,
        backup_dir=backup_dir,
        expected_pre_sha256=expected_pre_sha256,
        expected_existing_rows=expected_existing_rows,
        expected_rows_created=expected_rows_created,
        expected_current_stock_total=expected_current_stock_total,
        expected_inbound_stock_total=expected_inbound_stock_total,
        apply=apply,
    )


def _snapshot_current_stock(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                """
                SELECT current_stock
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date='2026-05-04' AND sku_id='SKU_A_M'
                """
            ).fetchone()[0]
        )


def test_dry_run_writes_summary_and_does_not_change_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)

    summary = _call_wrapper(
        db_path=db_path,
        output_root=tmp_path / "dry",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
    )

    assert summary["apply"]["applied"] is False
    assert summary["production_db_modified"] is False
    assert summary["backup_path"] is None
    assert summary["row_counts"]["before"]["rows"] == 1
    assert summary["row_counts"]["planned"]["current_stock_total"] == 7
    assert Path(summary["summary_json"]).exists()
    assert json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))["post_sha256"] == original_sha
    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2


def test_simulate_dry_run_plans_on_copy_and_does_not_change_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)

    summary = _call_wrapper(
        db_path=db_path,
        mode="simulate",
        output_root=tmp_path / "simulate_dry",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
    )

    assert summary["apply"]["applied"] is False
    assert summary["production_db_modified"] is False
    assert summary["row_counts"]["planned"]["current_stock_total"] == 7
    assert summary["rebuild_summary"]["dry_run"]["apply_status"] == "APPLIED"
    assert "plan_copy_path" in summary["rebuild_summary"]
    assert Path(summary["rebuild_summary"]["plan_copy_path"]).exists()
    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2


def test_apply_without_env_gate_fails_before_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.delenv(PRODUCTION_ENV_GATE, raising=False)

    with pytest.raises(ProductionSnapshotApplyError, match=f"{PRODUCTION_ENV_GATE}=1"):
        _call_wrapper(
            db_path=db_path,
            output_root=tmp_path / "blocked_env",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2
    assert not (tmp_path / "backups").exists()


def test_simulate_apply_without_env_gate_fails_before_plan_copy_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.delenv(PRODUCTION_ENV_GATE, raising=False)

    with pytest.raises(ProductionSnapshotApplyError, match=f"{PRODUCTION_ENV_GATE}=1"):
        _call_wrapper(
            db_path=db_path,
            mode="simulate",
            output_root=tmp_path / "blocked_env_simulate",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2
    assert not (tmp_path / "backups").exists()
    assert not (tmp_path / "blocked_env_simulate").exists()


def test_wrong_expected_pre_sha_fails_before_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")

    with pytest.raises(ProductionSnapshotApplyError, match="pre-write SHA mismatch"):
        _call_wrapper(
            db_path=db_path,
            output_root=tmp_path / "blocked_sha",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256="0" * 64,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2
    assert not (tmp_path / "backups").exists()


def test_sidecar_files_block_apply_before_backup_or_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    Path(f"{db_path}-wal").write_text("sidecar", encoding="utf-8")
    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")

    with pytest.raises(ProductionSnapshotApplyError, match="SQLite sidecars exist"):
        _call_wrapper(
            db_path=db_path,
            output_root=tmp_path / "blocked_sidecar",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2
    assert not (tmp_path / "backups").exists()


def test_successful_apply_uses_backup_staging_and_writes_rollback_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")

    summary = _call_wrapper(
        db_path=db_path,
        output_root=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        apply=True,
    )

    assert summary["apply"]["applied"] is True
    assert summary["apply"]["target_replaced"] is True
    assert "rebuild_snapshot_staging" in summary["apply"]["staging_path"]
    assert Path(summary["backup_path"]).exists()
    assert _sha256(Path(summary["backup_path"])) == original_sha
    assert summary["rollback"]["backup_path"] == summary["backup_path"]
    assert "cp " in summary["rollback"]["restore_command"]
    assert summary["integrity_check"]["backup"] == "ok"
    assert summary["integrity_check"]["staging_before"] == "ok"
    assert summary["integrity_check"]["staging_after"] == "ok"
    assert summary["integrity_check"]["target_after"] == "ok"
    assert summary["row_counts"]["staging_after"]["rows"] == 1
    assert summary["row_counts"]["target_after"]["current_stock_total"] == 7
    assert summary["production_db_modified"] is False
    assert Path(summary["summary_json"]).exists()

    persisted = json.loads(Path(summary["summary_json"]).read_text(encoding="utf-8"))
    assert persisted["rollback"]["backup_path"] == summary["backup_path"]
    assert _snapshot_current_stock(db_path) == 7
    assert _sha256(db_path) == summary["post_sha256"]


def test_successful_simulate_apply_uses_backup_staging_and_expected_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")

    summary = _call_wrapper(
        db_path=db_path,
        mode="simulate",
        output_root=tmp_path / "simulate_apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=original_sha,
        apply=True,
    )

    assert summary["snapshot"]["mode"] == "simulate"
    assert summary["apply"]["applied"] is True
    assert summary["apply"]["target_replaced"] is True
    assert Path(summary["backup_path"]).exists()
    assert _sha256(Path(summary["backup_path"])) == original_sha
    assert summary["row_counts"]["staging_after"]["rows"] == 1
    assert summary["row_counts"]["target_after"]["current_stock_total"] == 7
    assert summary["rebuild_summary"]["staging_apply"]["apply_status"] == "APPLIED"
    assert summary["production_db_modified"] is False
    assert _snapshot_current_stock(db_path) == 7
    assert _sha256(db_path) == summary["post_sha256"]


def test_expected_row_count_mismatch_fails_before_target_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _make_snapshot_db(db_path)
    original_sha = _sha256(db_path)
    monkeypatch.setenv(PRODUCTION_ENV_GATE, "1")

    with pytest.raises(ProductionSnapshotApplyError, match="planned snapshot rows mismatch"):
        _call_wrapper(
            db_path=db_path,
            output_root=tmp_path / "mismatch",
            backup_dir=tmp_path / "backups",
            expected_pre_sha256=original_sha,
            expected_rows_created=2,
            apply=True,
        )

    assert _sha256(db_path) == original_sha
    assert _snapshot_current_stock(db_path) == 2
    assert not (tmp_path / "backups").exists()
