from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from core.ops import manual_stock_count_reconcile as reconcile
from scripts import reconcile_manual_stock_count as reconcile_cli


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE dim_sku (
              sku_key TEXT PRIMARY KEY, active_flag INTEGER
            );
            CREATE TABLE dim_sku_size (
              sku_id TEXT PRIMARY KEY, sku_key TEXT, my_size TEXT, active_flag INTEGER
            );
            CREATE TABLE stock_ledger (
              ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_date TEXT NOT NULL,
              event_time TEXT,
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
              input_source TEXT,
              created_by TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              idempotency_key TEXT
            );
            CREATE UNIQUE INDEX ux_test_ledger_key ON stock_ledger(idempotency_key)
              WHERE idempotency_key IS NOT NULL;
            CREATE TABLE stock_anchor (
              anchor_id TEXT PRIMARY KEY, anchor_type TEXT NOT NULL,
              source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL,
              snapshot_date TEXT NOT NULL, as_of_date TEXT NOT NULL,
              row_count INTEGER NOT NULL, total_units INTEGER NOT NULL,
              approved_by TEXT, approved_at TEXT, status TEXT NOT NULL,
              notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE stock_adjustment_batch (
              batch_id TEXT PRIMARY KEY, anchor_id TEXT NOT NULL, method TEXT NOT NULL,
              method_version TEXT NOT NULL, reduction_rate REAL,
              target_units_delta INTEGER, generated_units_delta INTEGER,
              dry_run_report_path TEXT, approved_by TEXT, approved_at TEXT,
              applied_at TEXT, rollback_batch_id TEXT, status TEXT NOT NULL,
              notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO dim_sku VALUES ('SKU', 1);
            INSERT INTO dim_sku_size VALUES ('SKU_M', 'SKU', 'M', 1);
            """
        )
        events = [
            ("2026-07-14", "2026-07-14 10:00:00", 10),
            ("2026-07-15", "2026-07-15 06:59:00", -3),
            ("2026-07-15", "2026-07-15 08:00:00", -2),
            ("2026-07-16", "2026-07-16 05:00:00", 4),
        ]
        for event_date, event_time, qty in events:
            conn.execute(
                """
                INSERT INTO stock_ledger (
                  event_date, event_time, event_type, sku_key, sku_id, my_size,
                  store_code, qty_change, running_balance, input_source, created_by
                ) VALUES (?, ?, 'ADJUSTMENT', 'SKU', 'SKU_M', 'M', 'UNIVERSAL', ?, 999, 'TEST', 'TEST')
                """,
                (event_date, event_time, qty),
            )


def _manifest(path: Path, *, shared: bool = False, timestamp: str = "2026-07-15T12:00:00+05:00") -> Path:
    sku_id = "SKU_M"
    pool = "SHARED_POOL" if shared else sku_id
    aliases = [sku_id, "SKU_ALIAS"] if shared else [sku_id]
    policy = "shared_stock_pool" if shared else "single_sku_pool"
    data = {
        "schema_version": "manual_warehouse_stock_count_manifest_v1",
        "batch_id": "COUNT_2026_07_15",
        "status": "OWNER_APPROVED",
        "location": {"warehouse": "Astana", "timezone": "Asia/Almaty"},
        "approval": {
            "approved_by": "owner",
            "approved_at": "2026-07-15T13:00:00+05:00",
        },
        "count_scope": {
            "method": "manual_count_at_exact_cut",
            "quarantine_returns_included": False,
            "cancellation_units_included": False,
            "missing_size_policy": "do_not_infer_zero_for_absent_sizes",
        },
        "precedence": {"rank": 100},
        "known_corrections": [],
        "rows": [
            {
                "row_id": "COUNT-001",
                "count_timestamp_at_almaty": timestamp,
                "timestamp_folder": "15.07.2026_12_00_00",
                "stock_pool_id": pool,
                "model_label": "SKU",
                "sku_key": "SKU",
                "sku_id": sku_id,
                "applies_to_sku_ids": aliases,
                "canonical_size": "M",
                "ocr_size_label": "M",
                "color_or_pattern": "BLACK",
                "quantity": 5,
                "source_image": "count-block-1.jpg",
                "counting_policy": policy,
            }
        ],
        "expected_totals": {
            "raw_row_count": 1,
            "aggregate_stock_pool_row_count": 1,
            "total_units": 5,
            "folder_totals": {"15.07.2026_12_00_00": 5},
            "product_totals": {"SKU": 5},
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _insert_movement(
    db: Path,
    *,
    event_date: str,
    event_time: str,
    qty_change: int,
) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO stock_ledger (
              event_date, event_time, event_type, sku_key, sku_id, my_size,
              store_code, qty_change, running_balance, input_source, created_by
            ) VALUES (?, ?, 'ADJUSTMENT', 'SKU', 'SKU_M', 'M', 'UNIVERSAL', ?, NULL, 'TEST', 'TEST')
            """,
            (event_date, event_time, qty_change),
        )


def test_dry_run_uses_exact_cut_and_leaves_db_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    before = _sha(db)

    summary = reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=tmp_path / "dry",
    )

    assert summary["status"] == "DRY_RUN"
    assert summary["gate"] == "GREEN"
    assert _sha(db) == before == summary["pre_sha256"] == summary["post_sha256"]
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=tmp_path / "dry"
    )
    row = plan.rows[0]
    assert row.pre_count_balance == 7
    assert row.post_count_movement == 2
    assert row.current_ledger_balance == 9
    assert row.adjustment_delta == -2
    assert row.projected_current_balance == 7
    assert row.arithmetic_proven is True
    assert row.action == "INSERT"


def test_apply_backup_running_balance_and_idempotent_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    monkeypatch.setenv(reconcile.ENV_GATE, "1")

    first = reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=tmp_path / "apply-one",
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    assert first["status"] == "APPLIED"
    assert first["backup_integrity_check"] == "ok"
    assert Path(first["backup_path"]).exists()
    assert first["running_balance_mismatches"] == 0
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT qty_change, running_balance FROM stock_ledger ORDER BY ledger_id"
        ).fetchall()
        assert [(row["qty_change"], row["running_balance"]) for row in rows] == [
            (10, 10),
            (-3, 7),
            (-2, 5),
            (4, 9),
            (-2, 7),
        ]
        assert conn.execute("SELECT COUNT(*) FROM stock_anchor").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM stock_adjustment_batch").fetchone()[0] == 1

    second = reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=tmp_path / "apply-one",
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    assert second["existing_rows"] == 1
    assert second["insert_rows"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM stock_ledger WHERE input_source = ?",
            (reconcile.INPUT_SOURCE,),
        ).fetchone()[0] == 1


def test_existing_adjustment_accepts_ordinary_post_count_movement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    output = tmp_path / "apply"
    monkeypatch.setenv(reconcile.ENV_GATE, "1")
    reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=output,
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    _insert_movement(
        db,
        event_date="2026-07-17",
        event_time="2026-07-17 08:00:00",
        qty_change=-1,
    )

    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=output
    )
    assert plan.rows[0].action == "EXISTS"
    assert plan.rows[0].blocker == ""
    assert plan.rows[0].post_count_movement == 1
    rerun = reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=output,
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    assert rerun["existing_rows"] == 1
    assert rerun["blocked_rows"] == 0


def test_existing_adjustment_blocks_late_pre_count_movement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    output = tmp_path / "apply"
    monkeypatch.setenv(reconcile.ENV_GATE, "1")
    reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=output,
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    _insert_movement(
        db,
        event_date="2026-07-14",
        event_time="2026-07-14 11:00:00",
        qty_change=1,
    )

    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=output
    )
    assert plan.rows[0].action == "BLOCKED"
    assert "LATE_PRE_COUNT_MOVEMENT_AFTER_RECONCILIATION" in plan.rows[0].blocker


def test_existing_adjustment_note_arithmetic_is_immutable_and_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    output = tmp_path / "apply"
    monkeypatch.setenv(reconcile.ENV_GATE, "1")
    reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=output,
        apply=True,
        expected_pre_sha256=_sha(db),
    )
    with sqlite3.connect(db) as conn:
        note_text = conn.execute(
            "SELECT notes FROM stock_ledger WHERE input_source = ?",
            (reconcile.INPUT_SOURCE,),
        ).fetchone()[0]
        note = json.loads(note_text)
        note["original_post_count_movement"] += 1
        conn.execute(
            "UPDATE stock_ledger SET notes = ? WHERE input_source = ?",
            (json.dumps(note, sort_keys=True, separators=(",", ":")), reconcile.INPUT_SOURCE),
        )

    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=output
    )
    assert plan.rows[0].action == "BLOCKED"
    assert "EXISTING_NOTE_PROJECTED_ARITHMETIC_FAILED" in plan.rows[0].blocker


def test_apply_fails_closed_on_env_and_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    monkeypatch.delenv(reconcile.ENV_GATE, raising=False)
    with pytest.raises(RuntimeError, match=reconcile.ENV_GATE):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "blocked-env",
            apply=True,
            expected_pre_sha256=_sha(db),
        )
    monkeypatch.setenv(reconcile.ENV_GATE, "1")
    with pytest.raises(RuntimeError, match="pre-SHA mismatch"):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "blocked-sha",
            apply=True,
            expected_pre_sha256="0" * 64,
        )


def test_shared_pool_and_naive_timestamp_are_blocked(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    shared = _manifest(tmp_path / "shared.approved.json", shared=True)
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=shared, output_root=tmp_path / "shared-out"
    )
    assert plan.is_clean is False
    assert "SHARED_POOL_REQUIRES_EXPLICIT_ALLOCATION" in plan.rows[0].blocker

    naive = _manifest(
        tmp_path / "naive.approved.json", timestamp="2026-07-15T12:00:00"
    )
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=naive, output_root=tmp_path / "naive-out"
    )
    assert plan.is_clean is False
    assert "timezone-aware" in ";".join(plan.blockers)


def test_missing_parent_and_blank_db_size_fail_closed(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM dim_sku WHERE sku_key = 'SKU'")
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=tmp_path / "parent-missing"
    )
    assert "SKU_PARENT_MISSING" in plan.rows[0].blocker

    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO dim_sku VALUES ('SKU', 1)")
        conn.execute("UPDATE dim_sku_size SET my_size = '' WHERE sku_id = 'SKU_M'")
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=tmp_path / "blank-size"
    )
    assert "DB_MY_SIZE_BLANK" in plan.rows[0].blocker


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("batch_id", "BLANK_BATCH_ID"),
        ("stock_pool_id", "BLANK_STOCK_POOL_ID"),
        ("sku_key", "BLANK_SKU_KEY"),
        ("sku_id", "BLANK_SKU_ID"),
        ("canonical_size", "BLANK_CANONICAL_SIZE"),
    ],
)
def test_blank_manifest_canonical_target_identity_fails_locally(
    tmp_path: Path, target: str, expected: str
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / f"blank-{target}.approved.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if target == "batch_id":
        data[target] = " "
    else:
        data["rows"][0][target] = " "
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        reconcile.build_reconcile_plan(
            db_path=db, manifest_path=manifest, output_root=tmp_path / "blank-target"
        )


def test_same_day_null_event_time_blocks(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            UPDATE stock_ledger SET event_time = NULL
            WHERE ledger_id = (
              SELECT MIN(ledger_id) FROM stock_ledger WHERE event_date = '2026-07-15'
            )
            """
        )
    manifest = _manifest(tmp_path / "count.approved.json")
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=tmp_path / "out"
    )
    assert "NULL_EVENT_TIME" in plan.rows[0].blocker


def test_duplicate_aggregate_target_and_malformed_event_date_block(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest_path = _manifest(tmp_path / "duplicate.approved.json")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    second = dict(data["rows"][0])
    second.update(
        {
            "row_id": "COUNT-002",
            "count_timestamp_at_almaty": "2026-07-15T13:00:00+05:00",
            "timestamp_folder": "15.07.2026_13_00_00",
        }
    )
    data["rows"].append(second)
    data["expected_totals"] = {
        "raw_row_count": 2,
        "aggregate_stock_pool_row_count": 2,
        "total_units": 10,
        "folder_totals": {
            "15.07.2026_12_00_00": 5,
            "15.07.2026_13_00_00": 5,
        },
        "product_totals": {"SKU": 10},
    }
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest_path, output_root=tmp_path / "duplicate-out"
    )
    assert all("DUPLICATE_AGGREGATE_TARGET_IDENTITY" in row.blocker for row in plan.rows)

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE stock_ledger SET event_date = 'not-a-date' WHERE ledger_id = 1")
    normal_manifest = _manifest(tmp_path / "normal.approved.json")
    plan = reconcile.build_reconcile_plan(
        db_path=db,
        manifest_path=normal_manifest,
        output_root=tmp_path / "malformed-date-out",
    )
    assert "UNPARSEABLE_EVENT_DATE" in plan.rows[0].blocker


def test_production_gate_requires_second_env_and_dated_sha_locked_instrument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    monkeypatch.setattr(reconcile, "DEFAULT_DB_PATH", db)
    monkeypatch.setenv(reconcile.ENV_GATE, "1")
    monkeypatch.delenv(reconcile.PRODUCTION_ENV_GATE, raising=False)
    with pytest.raises(RuntimeError, match=reconcile.PRODUCTION_ENV_GATE):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "prod",
            apply=True,
            expected_pre_sha256=_sha(db),
        )

    monkeypatch.setenv(reconcile.PRODUCTION_ENV_GATE, "1")
    current_date = datetime.now(reconcile.ALMATY).date().isoformat()
    pre_sha = _sha(db)
    manifest_sha = _sha(manifest)
    arbitrary = tmp_path / f"OWNER_COUNT_APPLY_{current_date}.md"
    arbitrary.write_text("fixture-only owner instrument", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly match"):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "prod-arbitrary",
            apply=True,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "prod-backup",
            owner_instrument=arbitrary,
            owner_instrument_sha256=_sha(arbitrary),
        )

    stale = tmp_path / "OWNER_COUNT_APPLY_20000101.md"
    stale.write_text(
        reconcile.required_owner_approval_phrase(
            apply_date_almaty=current_date,
            batch_id="COUNT_2026_07_15",
            manifest_sha256=manifest_sha,
            expected_pre_db_sha256=pre_sha,
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="current Asia/Almaty"):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "prod-stale",
            apply=True,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "prod-backup",
            owner_instrument=stale,
            owner_instrument_sha256=_sha(stale),
        )

    unrelated = tmp_path / f"OWNER_OTHER_APPLY_{current_date}.md"
    unrelated.write_text(
        reconcile.required_owner_approval_phrase(
            apply_date_almaty=current_date,
            batch_id="UNRELATED_BATCH",
            manifest_sha256=manifest_sha,
            expected_pre_db_sha256=pre_sha,
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exactly match"):
        reconcile.reconcile_manual_stock_count(
            db_path=db,
            manifest_path=manifest,
            output_root=tmp_path / "prod-unrelated",
            apply=True,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "prod-backup",
            owner_instrument=unrelated,
            owner_instrument_sha256=_sha(unrelated),
        )

    instrument = tmp_path / f"OWNER_COUNT_APPLY_{current_date}.md"
    instrument.write_text(
        reconcile.required_owner_approval_phrase(
            apply_date_almaty=current_date,
            batch_id="COUNT_2026_07_15",
            manifest_sha256=manifest_sha,
            expected_pre_db_sha256=pre_sha,
        ),
        encoding="utf-8",
    )
    summary = reconcile.reconcile_manual_stock_count(
        db_path=db,
        manifest_path=manifest,
        output_root=tmp_path / "prod-ok",
        apply=True,
        expected_pre_sha256=pre_sha,
        backup_dir=tmp_path / "prod-backup",
        owner_instrument=instrument,
        owner_instrument_sha256=_sha(instrument),
    )
    assert summary["owner_instrument_sha256"] == _sha(instrument)
    assert summary["backup_integrity_check"] == "ok"


def test_cli_prints_exact_current_owner_phrase_without_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _manifest(tmp_path / "count.approved.json")
    expected_pre_sha = "a" * 64
    result = reconcile_cli.main(
        [
            "--manifest",
            str(manifest),
            "--expected-pre-sha256",
            expected_pre_sha,
            "--print-required-owner-approval-phrase",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out.strip()
    assert output == reconcile.required_owner_approval_phrase(
        apply_date_almaty=datetime.now(reconcile.ALMATY).date().isoformat(),
        batch_id="COUNT_2026_07_15",
        manifest_sha256=_sha(manifest),
        expected_pre_db_sha256=expected_pre_sha,
    )


def test_existing_legacy_anchor_source_sha_blocks_rematerialization(tmp_path: Path) -> None:
    db = tmp_path / "fixture.db"
    _create_db(db)
    manifest = _manifest(tmp_path / "count.approved.json")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO stock_anchor (
              anchor_id, anchor_type, source_path, source_sha256, snapshot_date,
              as_of_date, row_count, total_units, status
            ) VALUES (?, 'LEGACY_MANUAL_COUNT', ?, ?, '2026-07-15', '2026-07-15', 1, 5, 'APPROVED')
            """,
            ("COUNT_2026_07_15", str(manifest.resolve()), _sha(manifest)),
        )
        conn.execute(
            """
            INSERT INTO stock_adjustment_batch (
              batch_id, anchor_id, method, method_version, status
            ) VALUES (?, ?, 'LEGACY_TEMP_OCR', 'v0', 'APPLIED')
            """,
            ("COUNT_2026_07_15_GOVERNED_SUPERSESSION_DELTA", "COUNT_2026_07_15"),
        )

    plan = reconcile.build_reconcile_plan(
        db_path=db, manifest_path=manifest, output_root=tmp_path / "legacy-out"
    )
    assert plan.is_clean is False
    assert any(
        blocker.startswith("LEGACY_STOCK_ANCHOR_ALREADY_GOVERNS_MANIFEST")
        for blocker in plan.metadata_blockers
    )
    assert any(
        blocker.startswith("LEGACY_ADJUSTMENT_BATCH_ALREADY_GOVERNS_MANIFEST")
        for blocker in plan.metadata_blockers
    )
    assert plan.rows[0].action == "BLOCKED"
    assert "GLOBAL_METADATA_BLOCKER" in plan.rows[0].blocker
