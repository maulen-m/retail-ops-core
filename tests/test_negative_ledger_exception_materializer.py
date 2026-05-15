from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from core.ops.policy_materialization_c3 import (
    C3_MATERIALIZATION_ENV_GATE,
    materialize_policy_gate_results,
)
from core.ops.policy_registry_c3 import (
    promote_operational_decision_policy,
    validate_exception_queue_db,
)
from scripts.materialize_negative_ledger_exceptions import (
    NEGATIVE_LEDGER_EXCEPTION_ENV_GATE,
    materialize_negative_ledger_exceptions,
)
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate as migrate_p0
from scripts.migrate_029_policy_registry_c3 import migrate as migrate_c3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_YAML = PROJECT_ROOT / "config" / "operational_decision_policy.yaml"


def _promoted_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "app.db"
    migrate_p0(db_path)
    migrate_c3(db_path)
    monkeypatch.setenv("ENABLE_POLICY_REGISTRY_WRITE", "1")
    promote_operational_decision_policy(
        db_path=db_path,
        policy_path=POLICY_YAML,
        apply=True,
        backup_dir=tmp_path / "backups",
        actor="pytest",
        now="2026-05-04T12:00:00+05:00",
    )
    monkeypatch.delenv("ENABLE_POLICY_REGISTRY_WRITE", raising=False)
    return db_path


def _write_queue(path: Path) -> None:
    fields = [
        "sku_id",
        "store_code",
        "ledger_balance_morning_2026_05_04",
        "owner_policy_overlap",
        "action_bucket",
        "recommended_next_action",
        "return_qc_residual_overlap_count",
        "overlap_basis",
        "recent_events_before_2026_05_04",
    ]
    rows = [
        {
            "sku_id": "SKU_EXACT_A",
            "store_code": "UNIVERSAL",
            "ledger_balance_morning_2026_05_04": "-1",
            "owner_policy_overlap": "exact_owner_accepted_negative_raw_quarantine_active_zero",
            "action_bucket": "exact_owner_approved_active_zero_quarantine",
        },
        {
            "sku_id": "SKU_EXACT_B",
            "store_code": "UNIVERSAL",
            "ledger_balance_morning_2026_05_04": "-1",
            "owner_policy_overlap": "owner_black_tshirt_oos_active_zero_exact_size",
            "action_bucket": "exact_owner_approved_active_zero_quarantine",
        },
        {
            "sku_id": "SKU_WEAK",
            "store_code": "UNIVERSAL",
            "ledger_balance_morning_2026_05_04": "-2",
            "owner_policy_overlap": "weak_family_overlap",
            "action_bucket": "weak_family_overlap_not_auto_clearable",
            "recommended_next_action": "owner review required",
        },
        {
            "sku_id": "SKU_UNRESOLVED",
            "store_code": "UNIVERSAL",
            "ledger_balance_morning_2026_05_04": "-3",
            "owner_policy_overlap": "none_found",
            "action_bucket": "unresolved_no_owner_policy_overlap",
            "recommended_next_action": "ledger source repair required",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_negative_ledger_materializer_separates_exact_controls_from_owner_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    queue = tmp_path / "negative_queue.csv"
    _write_queue(queue)

    dry = materialize_negative_ledger_exceptions(
        db_path=db_path,
        source_csv=queue,
        output_root=tmp_path / "dry",
        as_of="2026-05-04",
        run_id="pytest-negative-ledger",
        apply=False,
    )
    assert dry["exception_row_count"] == 4
    assert dry["counts"] == {
        "exact_owner_approved_active_zero_quarantine": 2,
        "weak_family_overlap_not_auto_clearable": 1,
        "unresolved_no_owner_policy_overlap": 1,
    }

    monkeypatch.setenv(NEGATIVE_LEDGER_EXCEPTION_ENV_GATE, "1")
    applied = materialize_negative_ledger_exceptions(
        db_path=db_path,
        source_csv=queue,
        output_root=tmp_path / "apply",
        as_of="2026-05-04",
        run_id="pytest-negative-ledger",
        apply=True,
    )
    assert applied["applied_rows"] == 4
    assert validate_exception_queue_db(db_path, strict=True) == []

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_policy_gate_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-negative-ledger-gates",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT status, blocks_owner_publication, evidence_json
            FROM v_policy_gate_latest
            WHERE gate_name='exception_queue'
            """
        ).fetchone()

    evidence = json.loads(row["evidence_json"])
    assert row["status"] == "BLOCKED"
    assert row["blocks_owner_publication"] == 1
    assert evidence["accepted_active_control_count"] == 2
    assert evidence["unresolved_blocker_count"] == 2
    assert {
        item["control_type"] for item in evidence["accepted_active_control_rows"]
    } == {"OWNER_NEGATIVE_LEDGER_ACTIVE_ZERO_QUARANTINE"}
