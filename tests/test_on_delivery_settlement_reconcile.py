import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.reconcile_on_delivery_settlement import (
    _read_order_id_file,
    find_settlement_gaps,
    reconcile_on_delivery_settlement,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            internal_status TEXT,
            status_updated_at TEXT,
            sku_key TEXT,
            sku_id TEXT
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
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
        );
        """
    )
    conn.commit()
    conn.close()


def _seed_gap(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-1', 'ACMEWEAR', 'COMPLETED', '2026-02-08', 'SKU_A', 'SKU_A_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-02-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 1500, 'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'ORD-1', 'ORDER_MODELLED', 'h1')
        """
    )
    conn.commit()
    conn.close()


def test_detects_completed_orders_with_nonzero_on_delivery_balance(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)

    gaps = find_settlement_gaps(db_path=db_path, since="2026-02-01", until="2026-02-08")
    assert len(gaps) == 1
    assert gaps[0]["order_id"] == "ORD-1"
    assert gaps[0]["balance_kzt"] == 1500.0
    assert gaps[0]["event_date"] == "2026-02-08"


def test_uses_actual_terminal_status_date_not_until_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)

    gaps = find_settlement_gaps(db_path=db_path, since="2026-02-01", until="2026-02-20")

    assert len(gaps) == 1
    assert gaps[0]["event_date"] == "2026-02-08"


def test_order_allowlist_filters_candidates_and_rejects_empty_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)

    assert find_settlement_gaps(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        order_id_allowlist={"OTHER"},
    ) == []

    try:
        find_settlement_gaps(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            order_id_allowlist=set(),
        )
    except RuntimeError as exc:
        assert "allowlist is empty" in str(exc)
    else:
        raise AssertionError("empty settlement allowlist should fail closed")


def test_order_id_file_missing_empty_and_duplicate_handling(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not found"):
        _read_order_id_file(tmp_path / "missing.txt")

    empty = tmp_path / "empty.txt"
    empty.write_text("\n  \n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="allowlist is empty"):
        _read_order_id_file(empty)

    populated = tmp_path / "orders.txt"
    populated.write_text("ORD-1\nORD-1\n ORD-2 \n", encoding="utf-8")
    assert _read_order_id_file(populated) == {"ORD-1", "ORD-2"}


def test_reconcile_script_generates_settlement_events_idempotently(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    first = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        apply=True,
        run_id="TEST-RUN",
        expected_pre_sha256=_sha256(db_path),
        order_id_allowlist={"ORD-1"},
        expected_candidate_count=1,
    )
    with pytest.raises(RuntimeError, match="candidate count mismatch"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            run_id="TEST-RUN",
            expected_pre_sha256=_sha256(db_path),
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
        )

    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='INVENTORY_SETTLEMENT'"
    ).fetchone()[0]
    balance = conn.execute(
        """
        SELECT SUM(amount_kzt) FROM fact_cashflow_events
        WHERE account='INVENTORY_ON_DELIVERY_COST' AND ref_id='ORD-1'
        """
    ).fetchone()[0]
    conn.close()

    assert first["inserted"] == 1
    assert count == 1
    assert float(balance or 0.0) == 0.0


def test_production_settlement_apply_requires_prod_gate_and_backup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import scripts.reconcile_on_delivery_settlement as settlement_mod

    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setattr(settlement_mod, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")
    monkeypatch.delenv("ENABLE_CASHFLOW_PROD_WRITE", raising=False)

    try:
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            run_id="PROD-BLOCKED",
            expected_pre_sha256=_sha256(db_path),
            backup_dir=tmp_path / "backups",
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
        )
    except RuntimeError as exc:
        assert "ENABLE_CASHFLOW_PROD_WRITE=1" in str(exc)
    else:
        raise AssertionError("production settlement apply should require prod env gate")

    monkeypatch.setenv("ENABLE_CASHFLOW_PROD_WRITE", "1")
    try:
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            run_id="PROD-MISSING-SHA",
            backup_dir=tmp_path / "backups",
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
        )
    except RuntimeError as exc:
        assert "--expected-pre-sha256" in str(exc)
    else:
        raise AssertionError("production settlement apply should require expected SHA")

    result = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        apply=True,
        run_id="PROD-OK",
        expected_pre_sha256=_sha256(db_path),
        backup_dir=tmp_path / "backups",
        order_id_allowlist={"ORD-1"},
        expected_candidate_count=1,
    )

    backup_path = Path(str(result["apply_metadata"]["backup_path"]))
    assert result["inserted"] == 1
    assert backup_path.exists()
    assert result["apply_metadata"]["backup_integrity_check"] == "ok"


def test_expected_count_and_copy_sha_fail_before_nonproduction_apply(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    try:
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            order_id_allowlist={"ORD-1", "ORD-MISSING"},
            expected_candidate_count=2,
            expected_pre_sha256=_sha256(db_path),
        )
    except RuntimeError as exc:
        assert "candidate count mismatch" in str(exc)
    else:
        raise AssertionError("candidate-count mismatch should fail before apply")

    try:
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
            expected_pre_sha256="0" * 64,
        )
    except RuntimeError as exc:
        assert "DB SHA mismatch" in str(exc)
    else:
        raise AssertionError("copy SHA mismatch should fail before apply")

    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM fact_cashflow_events WHERE event_type='INVENTORY_SETTLEMENT'"
    ).fetchone()[0]
    conn.close()
    assert count == 0


def test_copy_apply_requires_scope_count_and_sha(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    with pytest.raises(RuntimeError, match="--order-id-file"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
        )
    with pytest.raises(RuntimeError, match="--expected-candidate-count"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            order_id_allowlist={"ORD-1"},
        )
    with pytest.raises(RuntimeError, match="--expected-pre-sha256"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
        )


def test_missing_terminal_timestamp_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO fact_orders_kaspi VALUES ('ORD-NO-DATE','ACMEWEAR','COMPLETED',NULL,'SKU_A','SKU_A_M')"
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,account,amount_kzt,store_code,sku_key,sku_id,ref_type,ref_id,source,event_hash)
        VALUES ('2026-02-08','INVENTORY_MOVE','INVENTORY_ON_DELIVERY_COST',1500,'ACMEWEAR','SKU_A','SKU_A_M','ORDER','ORD-NO-DATE','ORDER_MODELLED','h-no-date')
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="missing or invalid terminal status timestamp"):
        find_settlement_gaps(db_path=db_path, until="2026-02-20")


def test_allowlist_apply_mutates_only_allowlisted_order(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO fact_orders_kaspi VALUES ('ORD-2','STOREB','COMPLETED','2026-02-09','SKU_B','SKU_B_L')"
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,account,amount_kzt,store_code,sku_key,sku_id,ref_type,ref_id,source,event_hash)
        VALUES ('2026-02-09','INVENTORY_MOVE','INVENTORY_ON_DELIVERY_COST',700,'STOREB','SKU_B','SKU_B_L','ORDER','ORD-2','ORDER_MODELLED','h2')
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    result = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-20",
        apply=True,
        expected_pre_sha256=_sha256(db_path),
        order_id_allowlist={"ORD-1"},
        expected_candidate_count=1,
    )

    conn = sqlite3.connect(str(db_path))
    balances = dict(
        conn.execute(
            "SELECT ref_id,SUM(amount_kzt) FROM fact_cashflow_events WHERE account='INVENTORY_ON_DELIVERY_COST' GROUP BY ref_id"
        ).fetchall()
    )
    stored_date = conn.execute(
        "SELECT event_date FROM fact_cashflow_events WHERE event_type='INVENTORY_SETTLEMENT' AND ref_id='ORD-1'"
    ).fetchone()[0]
    conn.close()
    assert result["inserted"] == 1
    assert balances == {"ORD-1": 0.0, "ORD-2": 700.0}
    assert stored_date == "2026-02-08"


def test_existing_event_hash_collision_fails_before_partial_success(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    _seed_gap(db_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-02-01",
        until="2026-02-08",
        apply=True,
        run_id="HASH-RUN-1",
        expected_pre_sha256=_sha256(db_path),
        order_id_allowlist={"ORD-1"},
        expected_candidate_count=1,
    )
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date,event_type,account,amount_kzt,store_code,sku_key,sku_id,ref_type,ref_id,source,event_hash)
        VALUES ('2026-02-08','INVENTORY_MOVE','INVENTORY_ON_DELIVERY_COST',1500,'ACMEWEAR','SKU_A','SKU_A_M','ORDER','ORD-1','ORDER_MODELLED','h-reopened')
        """
    )
    conn.commit()
    conn.close()
    before = _sha256(db_path)

    with pytest.raises(RuntimeError, match="new settlement event count mismatch"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-02-01",
            until="2026-02-08",
            apply=True,
            run_id="HASH-RUN-2",
            expected_pre_sha256=before,
            order_id_allowlist={"ORD-1"},
            expected_candidate_count=1,
        )

    assert _sha256(db_path) == before


def test_detects_gap_when_order_sku_id_drift_differs_from_cashflow_sku_id(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-DRIFT', 'STOREB', 'COMPLETED', '2026-03-08', 'SKU_B', 'SKU_B_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-03-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 375, 'STOREB', 'SKU_B', 'SKU_B_L', 'ORDER', 'ORD-DRIFT', 'ORDER_MODELLED', 'h-drift')
        """
    )
    conn.commit()
    conn.close()

    gaps = find_settlement_gaps(db_path=db_path, since="2026-03-08", until="2026-03-08")

    assert len(gaps) == 1
    assert gaps[0]["order_id"] == "ORD-DRIFT"
    assert gaps[0]["balance_kzt"] == 375.0


def test_skips_orders_without_deterministic_sku_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-NO-SKU', 'ACMEWEAR', 'COMPLETED', '2026-03-08', NULL, '')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-03-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 3975, 'ACMEWEAR', NULL, '', 'ORDER', 'ORD-NO-SKU', 'ORDER_MODELLED', 'h-nosku')
        """
    )
    conn.commit()
    conn.close()

    gaps = find_settlement_gaps(db_path=db_path, since="2026-03-08", until="2026-03-08")

    assert gaps == []


def test_reconcile_drifted_order_uses_order_level_balance_idempotently(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi
        (order_id, store_code, internal_status, status_updated_at, sku_key, sku_id)
        VALUES ('ORD-DRIFT-APPLY', 'STOREB', 'COMPLETED', '2026-03-08', 'SKU_B', 'SKU_B_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id, ref_type, ref_id, source, event_hash)
        VALUES ('2026-03-08', 'INVENTORY_MOVE', 'INVENTORY_ON_DELIVERY_COST', 375, 'STOREB', 'SKU_B', 'SKU_B_L', 'ORDER', 'ORD-DRIFT-APPLY', 'ORDER_MODELLED', 'h-drift-apply')
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    first = reconcile_on_delivery_settlement(
        db_path=db_path,
        since="2026-03-08",
        until="2026-03-08",
        apply=True,
        run_id="DRIFT-RUN",
        expected_pre_sha256=_sha256(db_path),
        order_id_allowlist={"ORD-DRIFT-APPLY"},
        expected_candidate_count=1,
    )
    with pytest.raises(RuntimeError, match="candidate count mismatch"):
        reconcile_on_delivery_settlement(
            db_path=db_path,
            since="2026-03-08",
            until="2026-03-08",
            apply=True,
            run_id="DRIFT-RUN",
            expected_pre_sha256=_sha256(db_path),
            order_id_allowlist={"ORD-DRIFT-APPLY"},
            expected_candidate_count=1,
        )

    assert first["inserted"] == 1
    assert find_settlement_gaps(db_path=db_path, since="2026-03-08", until="2026-03-08") == []
