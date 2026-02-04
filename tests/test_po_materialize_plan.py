import json
import sqlite3
from pathlib import Path

import pytest


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE po_header (
            po_id TEXT PRIMARY KEY,
            supplier_code TEXT NOT NULL,
            status TEXT DEFAULT 'DRAFT',
            notes TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE po_line (
            po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            order_qty INTEGER NOT NULL,
            received_qty INTEGER DEFAULT 0,
            unit_cost_cny REAL NOT NULL,
            status TEXT DEFAULT 'PENDING'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE fact_input_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            change_type TEXT NOT NULL,
            source TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _write_dashboard(tmp_path: Path) -> Path:
    payload = {
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_message_date": "2026-01-01",
                "sku_level": [
                    {
                        "sku_key": "SKU_A",
                        "base_cost_cny": 10.0,
                        "weight_per_unit_kg": 1.2,
                    }
                ],
                "size_level": [
                    {
                        "sku_key": "SKU_A",
                        "sku_id": "SKU_A_M",
                        "size": "M",
                        "order_qty": 5,
                        "weight_kg": 6.0,
                    }
                ],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }
    path = tmp_path / "po_dashboard_data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _count_rows(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    conn.close()
    return int(row[0])


def test_materialize_dry_run_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.po.materialize import materialize_plan_po

    db_path = tmp_path / "app.db"
    _init_db(db_path)
    dashboard = _write_dashboard(tmp_path)

    monkeypatch.delenv("PO_WRITE_ENABLED", raising=False)

    result = materialize_plan_po(
        dashboard_path=dashboard,
        plan_name="PLAN-0",
        po_id="PO-TEST",
        supplier="SUPP_A",
        notes=None,
        user="tester",
        db_path=db_path,
        apply=False,
    )

    assert result["status"] == "DRY_RUN"
    assert _count_rows(db_path, "po_header") == 0
    assert _count_rows(db_path, "po_line") == 0


def test_materialize_requires_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.po.materialize import materialize_plan_po

    db_path = tmp_path / "app.db"
    _init_db(db_path)
    dashboard = _write_dashboard(tmp_path)

    monkeypatch.delenv("PO_WRITE_ENABLED", raising=False)

    with pytest.raises(RuntimeError, match="PO_WRITE_ENABLED"):
        materialize_plan_po(
            dashboard_path=dashboard,
            plan_name="PLAN-0",
            po_id="PO-TEST",
            supplier="SUPP_A",
            notes=None,
            user="tester",
            db_path=db_path,
            apply=True,
        )


def test_materialize_idempotent_on_hash_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.po.materialize import materialize_plan_po

    db_path = tmp_path / "app.db"
    _init_db(db_path)
    dashboard = _write_dashboard(tmp_path)

    monkeypatch.setenv("PO_WRITE_ENABLED", "true")

    result1 = materialize_plan_po(
        dashboard_path=dashboard,
        plan_name="PLAN-0",
        po_id="PO-TEST",
        supplier="SUPP_A",
        notes=None,
        user="tester",
        db_path=db_path,
        apply=True,
    )
    assert result1["status"] == "CREATED"
    assert _count_rows(db_path, "po_header") == 1
    assert _count_rows(db_path, "po_line") == 1

    result2 = materialize_plan_po(
        dashboard_path=dashboard,
        plan_name="PLAN-0",
        po_id="PO-TEST",
        supplier="SUPP_A",
        notes=None,
        user="tester",
        db_path=db_path,
        apply=True,
    )

    assert result2["status"] == "IDEMPOTENT"
    assert _count_rows(db_path, "po_header") == 1
    assert _count_rows(db_path, "po_line") == 1


def test_materialize_hash_mismatch_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.po.materialize import materialize_plan_po

    db_path = tmp_path / "app.db"
    _init_db(db_path)
    dashboard = _write_dashboard(tmp_path)

    monkeypatch.setenv("PO_WRITE_ENABLED", "true")

    materialize_plan_po(
        dashboard_path=dashboard,
        plan_name="PLAN-0",
        po_id="PO-TEST",
        supplier="SUPP_A",
        notes=None,
        user="tester",
        db_path=db_path,
        apply=True,
    )

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE po_header SET notes = ? WHERE po_id = ?",
        ("PLAN=PLAN-0; PLAN_HASH=deadbeef", "PO-TEST"),
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="PLAN_HASH"):
        materialize_plan_po(
            dashboard_path=dashboard,
            plan_name="PLAN-0",
            po_id="PO-TEST",
            supplier="SUPP_A",
            notes=None,
            user="tester",
            db_path=db_path,
            apply=True,
        )
