import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import scripts.apply_order_cash_repair_manifest as applier
from scripts.apply_order_cash_repair_manifest import _exact_applied_state_conn
from scripts.build_sales_publication_binding_manifest import canonical_sha256, sha256_file
from scripts.rebuild_cashflow_calendar import (
    _is_order_cash_repair_reversal,
    compute_daily_rows,
)


def _repair_reversal() -> dict[str, object]:
    return {
        "event_date": "2026-01-13",
        "event_type": "CASH_IN",
        "account": "KASPI_PAY_ACMEWEAR",
        "amount_kzt": -1000.0,
        "store_code": "ACMEWEAR",
        "sku_key": "SKU",
        "sku_id": "SKU_M",
        "ref_type": "ORDER",
        "ref_id": "784153715",
        "source": "ORDER_CASH_REPAIR",
        "run_id": "order_784153715_cash_repair_v1",
        "event_hash": "a" * 64,
        "notes": (
            "exact mapped-order cash reversal; order_id=784153715; "
            "supersedes_cash_id=27690; supersedes_cash_hash="
            + "b" * 64
            + "; repair_key=ORDER784_CASH_V1"
        ),
    }


def test_exact_order_cash_repair_reversal_is_not_a_refund() -> None:
    reversal = _repair_reversal()
    assert _is_order_cash_repair_reversal(reversal) is True
    rows = compute_daily_rows(
        [
            {
                **reversal,
                "amount_kzt": 1000.0,
                "source": "ORDER_MODELLED",
                "notes": "",
            },
            reversal,
        ],
        date(2026, 1, 13),
        date(2026, 1, 13),
    )
    assert rows[0]["cash_flow_kzt"] == 0.0
    assert rows[0]["refunds_kzt"] == 0.0


def test_ordinary_or_malformed_negative_cash_in_remains_a_refund() -> None:
    malformed = {**_repair_reversal(), "notes": "missing supersession proof"}
    assert _is_order_cash_repair_reversal(malformed) is False
    rows = compute_daily_rows(
        [
            malformed,
            {
                **_repair_reversal(),
                "amount_kzt": -200.0,
                "source": "ORDER_MODELLED",
                "notes": "ordinary negative cash in",
            },
        ],
        date(2026, 1, 13),
        date(2026, 1, 13),
    )
    assert rows[0]["refunds_kzt"] == 1200.0


def test_cash_repair_exact_readback_sees_uncommitted_same_transaction_rows() -> None:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_ts TEXT,
            event_type TEXT,
            account TEXT,
            amount_kzt REAL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            notes TEXT,
            source TEXT,
            run_id TEXT,
            event_hash TEXT UNIQUE
        )
        """
    )
    event = _repair_reversal()
    manifest = {"reversals": [{"event": event}], "replacements": []}
    columns = list(event)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        f"INSERT INTO fact_cashflow_events ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})",
        [event[column] for column in columns],
    )
    state = _exact_applied_state_conn(conn, manifest)
    assert state is not None
    assert state["event_count"] == 1
    assert state["event_hashes"] == ["a" * 64]
    conn.execute("ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0] == 0
    conn.close()


def _seed_cash_apply_packet(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    db_path = tmp_path / "cash-copy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT, event_ts TEXT, event_type TEXT, account TEXT,
                amount_kzt REAL, store_code TEXT, sku_key TEXT, sku_id TEXT,
                ref_type TEXT, ref_id TEXT, notes TEXT, source TEXT,
                run_id TEXT, event_hash TEXT UNIQUE
            );
            CREATE TABLE unrelated (id INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO unrelated VALUES (1, 'preserve');
            INSERT INTO fact_cashflow_events(
                id,event_date,event_type,account,amount_kzt,store_code,sku_key,
                sku_id,ref_type,ref_id,notes,source,run_id,event_hash
            ) VALUES (
                10,'2026-01-13','CASH_IN','KASPI_PAY_ACMEWEAR',1000,'ACMEWEAR',
                'SKU','SKU_M','ORDER','784153715','stale','ORDER_MODELLED',
                'old','old-hash'
            );
            """
        )
    reversal = {
        "event_date": "2026-01-13", "event_ts": None,
        "event_type": "CASH_IN", "account": "KASPI_PAY_ACMEWEAR",
        "amount_kzt": -1000.0, "store_code": "ACMEWEAR",
        "sku_key": "SKU", "sku_id": "SKU_M", "ref_type": "ORDER",
        "ref_id": "784153715", "notes": "exact reversal",
        "source": "ORDER_CASH_REPAIR", "run_id": "repair", "event_hash": "reverse-hash",
    }
    replacement = {
        "event_date": "2026-01-13", "event_ts": "2026-01-13T00:00:00+00:00",
        "event_type": "CASH_IN", "account": "KASPI_PAY_ACMEWEAR",
        "amount_kzt": 900.0, "store_code": "ACMEWEAR",
        "sku_key": "SKU", "sku_id": "SKU_M", "ref_type": "ORDER_ENTRY",
        "ref_id": "ENTRY", "notes": "replacement", "source": "ORDER_MODELLED",
        "run_id": "repair", "event_hash": "replacement-hash",
    }
    with sqlite3.connect(db_path) as conn:
        cash_hash = applier._logical_hash(conn, "fact_cashflow_events")
    body: dict[str, object] = {
        "db_path": str(db_path.resolve()),
        "db_sha256": sha256_file(db_path),
        "cash_table_logical_sha256": cash_hash,
        "expected_insert_count": 2,
        "replacement_total_kzt": 900.0,
        "order_id": "784153715", "store_code": "ACMEWEAR",
        "repair_key": "TEST", "run_id": "repair",
        "publication_binding_id": "B",
        "publication_manifest_path": str((tmp_path / "publication.json").resolve()),
        "reversals": [{"superseded_preimage": {"id": 10}, "event": reversal}],
        "replacements": [{"source_entry_id": "ENTRY", "event": replacement}],
    }
    body["manifest_sha256"] = canonical_sha256(body)
    manifest_path = tmp_path / "cash-manifest.json"
    manifest_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return db_path, manifest_path, body


def test_cash_post_commit_failure_restores_exact_copied_preimage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, manifest_path, manifest = _seed_cash_apply_packet(tmp_path)
    pre_sha = sha256_file(db_path)
    backup_dir = tmp_path / "backups"
    output_path = tmp_path / "apply.json"
    monkeypatch.setattr(applier, "_assert_copied_target", lambda _path: None)
    monkeypatch.setattr(applier, "_validate_external", lambda _manifest: None)
    monkeypatch.setattr(applier, "build_manifest", lambda **_kwargs: manifest)
    monkeypatch.setenv(applier.WRITE_ENV_GATE, "1")

    def fail_post_commit(_path: Path) -> None:
        raise applier.OrderCashRepairApplyError("injected post-commit failure")

    monkeypatch.setattr(applier, "_post_commit_barrier", fail_post_commit)
    with pytest.raises(applier.OrderCashRepairApplyError, match="restored"):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=output_path,
            backup_dir=backup_dir,
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_insert_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert not output_path.exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0] == 1
        assert conn.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve"
    rollback_paths = list(backup_dir.glob("ROLLBACK_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "RESTORED_AFTER_POST_COMMIT_FAILURE"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha
