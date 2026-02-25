from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.validate_dashboard_plan_real_contract import validate_dashboard_plan_real_contract


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT
        );
        INSERT INTO po_part (po_part_id, po_id) VALUES
            ('PO-5.1', 'PO-5'),
            ('PO-6.0a', 'PO-6');
        """
    )
    conn.commit()
    conn.close()


def test_dashboard_plan_real_contract_passes_with_valid_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    dashboard_path = tmp_path / "po_dashboard_data.json"
    _seed_db(db_path)

    payload = {
        "pos": {
            "PLAN-0": {"po_kind": "PLAN"},
            "PO-5.1": {"po_kind": "REAL_ARCHIVE"},
            "PO-6.0a": {"po_kind": "REAL_ARCHIVE"},
        },
        "archived_pos": ["PO-5.1", "PO-6.0a"],
        "real_pos": [{"po_id": "PO-5.1"}, {"po_id": "PO-6.0a"}],
    }
    dashboard_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_dashboard_plan_real_contract(db_path=db_path, dashboard_path=dashboard_path)
    assert report["ok"] is True
    assert report["errors"] == []


def test_dashboard_plan_real_contract_fails_on_phantom_real_and_bad_label(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    dashboard_path = tmp_path / "po_dashboard_data.json"
    _seed_db(db_path)

    payload = {
        "pos": {
            "PLAN-0": {"po_kind": "PLAN"},
            "PO-5.1": {"po_kind": "PLAN"},  # invalid
            "PO-999.9": {"po_kind": "REAL_ARCHIVE"},  # phantom
        },
        "archived_pos": ["PO-5.1"],
        "real_pos": [{"po_id": "PO-999.9"}],
    }
    dashboard_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_dashboard_plan_real_contract(db_path=db_path, dashboard_path=dashboard_path)
    assert report["ok"] is False
    errors = "\n".join(report["errors"])
    assert "expected po_kind=REAL_ARCHIVE" in errors
    assert "non-PLAN key missing from materialized PO ids" in errors
    assert "real_pos id missing from materialized PO ids" in errors
