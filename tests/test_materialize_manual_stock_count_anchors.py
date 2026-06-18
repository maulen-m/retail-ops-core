import json
import os
import sqlite3
from pathlib import Path

import pytest

from scripts.materialize_manual_stock_count_anchors import (
    ENV_GATE,
    INPUT_SOURCE,
    materialize_manual_stock_count_anchors,
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _create_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE stock_anchor (
                anchor_id TEXT PRIMARY KEY,
                anchor_type TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                total_units INTEGER NOT NULL DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE stock_adjustment_batch (
                batch_id TEXT PRIMARY KEY,
                anchor_id TEXT NOT NULL,
                method TEXT NOT NULL,
                method_version TEXT NOT NULL,
                reduction_rate REAL,
                target_units_delta INTEGER,
                generated_units_delta INTEGER,
                dry_run_report_path TEXT,
                approved_by TEXT,
                approved_at TEXT,
                applied_at TEXT,
                rollback_batch_id TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                idempotency_key TEXT
            );
            """
        )


def _manifest(path: Path) -> Path:
    payload = {
        "schema_version": "manual_warehouse_stock_count_manifest_v1",
        "batch_id": "TEST_MANUAL_COUNT",
        "status": "OWNER_APPROVED",
        "approval": {
            "approved_by": "owner",
            "approved_at": "2026-06-04T00:00:00+05:00",
        },
        "count_scope": {
            "method": "manual_human_count_before_daily_shipments",
            "quarantine_returns_included": False,
            "cancellation_units_included": False,
            "missing_size_policy": "do_not_infer_zero_for_sizes_absent_from_this_manifest",
            "duplicate_size_policy": "sum_same_model_size_color_or_pattern_rows_when_they_appear_multiple_times_in_source_images",
        },
        "precedence": {"rank": 20, "rule": "test"},
        "expected_totals": {
            "raw_row_count": 2,
            "aggregate_stock_pool_row_count": 2,
            "total_units": 12,
            "folder_totals": {"04.06.2026_14_00_23": 12},
            "product_totals": {"Test": 12},
        },
        "rows": [
            {
                "row_id": "ROW-1",
                "count_timestamp_at_almaty": "2026-06-04T14:00:23+05:00",
                "timestamp_folder": "04.06.2026_14_00_23",
                "source_image": "image1.jpg",
                "model_label": "Test",
                "sku_key": "SKU_A",
                "sku_id": "SKU_A_M",
                "applies_to_sku_ids": ["SKU_A_M"],
                "stock_pool_id": "SKU_A_M",
                "ocr_size_label": "M",
                "canonical_size": "M",
                "color_or_pattern": "black",
                "quantity": 7,
                "counting_policy": "single_sku_pool",
                "timing_policy": "pre_2026_06_04_daily_kaspi_shipments",
            },
            {
                "row_id": "ROW-2",
                "count_timestamp_at_almaty": "2026-06-04T14:00:23+05:00",
                "timestamp_folder": "04.06.2026_14_00_23",
                "source_image": "image2.jpg",
                "model_label": "Test",
                "sku_key": "SKU_B",
                "sku_id": "SKU_B_L",
                "applies_to_sku_ids": ["SKU_B_L"],
                "stock_pool_id": "SKU_B_L",
                "ocr_size_label": "L",
                "canonical_size": "L",
                "color_or_pattern": "black",
                "quantity": 5,
                "counting_policy": "single_sku_pool",
                "timing_policy": "pre_2026_06_04_daily_kaspi_shipments",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _insert_covered_rows(db_path: Path) -> None:
    key = "TEMP_OCR_OVERRIDE:TEST_MANUAL_COUNT:ROW-1:SKU_A_M:2026-06-04T14:00:23+05:00:FULL_SUPERSEDE"
    notes = {
        "source_doc": "MANIFEST_PATH",
        "source_quantity": 7,
        "balance_before_override": 9,
        "predicted_balance_after_override": 7,
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, notes, input_source,
                created_by, idempotency_key
            )
            VALUES (?, 'ADJUSTMENT', ?, ?, ?, 'UNIVERSAL', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-04",
                "SKU_A",
                "SKU_A_M",
                "M",
                -2,
                "ROW-1",
                "TEMP_OCR_FULL_SUPERSEDE",
                json.dumps(notes),
                INPUT_SOURCE,
                "test",
                key,
            ),
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, input_source,
                created_by
            )
            VALUES ('2026-06-03', 'INITIAL', 'SKU_B', 'SKU_B_L', 'L', 'UNIVERSAL', 5, 'prior', 'TEST', 'TEST', 'test')
            """
        )


def test_dry_run_proves_existing_ledger_and_zero_delta_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    manifest = _manifest(tmp_path / "manifest.approved.json")
    _create_schema(db_path)
    _insert_covered_rows(db_path)
    # Align note source_doc with the actual temp manifest path.
    with sqlite3.connect(db_path) as conn:
        notes = json.loads(conn.execute("SELECT notes FROM stock_ledger WHERE idempotency_key IS NOT NULL").fetchone()[0])
        notes["source_doc"] = str(manifest)
        conn.execute("UPDATE stock_ledger SET notes = ? WHERE idempotency_key IS NOT NULL", (json.dumps(notes),))

    before = _sha256(db_path)
    summary = materialize_manual_stock_count_anchors(
        db_path=db_path,
        manifest_paths=[manifest],
        output_root=tmp_path / "out",
    )
    after = _sha256(db_path)

    assert before == after
    assert summary["is_safe_to_apply"] is True
    assert summary["existing_ledger_rows"] == 1
    assert summary["noop_zero_delta_rows"] == 1
    assert summary["anchor_insert_count"] == 1
    assert summary["batch_insert_count"] == 1


def test_apply_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    manifest = _manifest(tmp_path / "manifest.approved.json")
    _create_schema(db_path)
    _insert_covered_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        notes = json.loads(conn.execute("SELECT notes FROM stock_ledger WHERE idempotency_key IS NOT NULL").fetchone()[0])
        notes["source_doc"] = str(manifest)
        conn.execute("UPDATE stock_ledger SET notes = ? WHERE idempotency_key IS NOT NULL", (json.dumps(notes),))

    monkeypatch.delenv(ENV_GATE, raising=False)
    with pytest.raises(RuntimeError, match=f"{ENV_GATE}=1"):
        materialize_manual_stock_count_anchors(
            db_path=db_path,
            manifest_paths=[manifest],
            output_root=tmp_path / "out",
            apply=True,
            expected_pre_sha256=_sha256(db_path),
            backup_dir=tmp_path / "backups",
        )


def test_apply_inserts_metadata_only_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    manifest = _manifest(tmp_path / "manifest.approved.json")
    _create_schema(db_path)
    _insert_covered_rows(db_path)
    with sqlite3.connect(db_path) as conn:
        notes = json.loads(conn.execute("SELECT notes FROM stock_ledger WHERE idempotency_key IS NOT NULL").fetchone()[0])
        notes["source_doc"] = str(manifest)
        conn.execute("UPDATE stock_ledger SET notes = ? WHERE idempotency_key IS NOT NULL", (json.dumps(notes),))

    monkeypatch.setenv(ENV_GATE, "1")
    summary = materialize_manual_stock_count_anchors(
        db_path=db_path,
        manifest_paths=[manifest],
        output_root=tmp_path / "out",
        apply=True,
        expected_pre_sha256=_sha256(db_path),
        backup_dir=tmp_path / "backups",
    )

    assert summary["status"] == "APPLIED"
    assert Path(summary["backup_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM stock_anchor").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM stock_adjustment_batch").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0] == 2

    again = materialize_manual_stock_count_anchors(
        db_path=db_path,
        manifest_paths=[manifest],
        output_root=tmp_path / "out2",
    )
    assert again["anchor_insert_count"] == 0
    assert again["batch_insert_count"] == 0


def test_missing_coverage_blocks_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    manifest = _manifest(tmp_path / "manifest.approved.json")
    _create_schema(db_path)
    monkeypatch.setenv(ENV_GATE, "1")

    summary = materialize_manual_stock_count_anchors(
        db_path=db_path,
        manifest_paths=[manifest],
        output_root=tmp_path / "out",
    )

    assert summary["is_safe_to_apply"] is False
    assert summary["blocked_rows"] == 2
    with pytest.raises(RuntimeError, match="not safe to apply"):
        materialize_manual_stock_count_anchors(
            db_path=db_path,
            manifest_paths=[manifest],
            output_root=tmp_path / "out2",
            apply=True,
            expected_pre_sha256=_sha256(db_path),
            backup_dir=tmp_path / "backups",
        )
