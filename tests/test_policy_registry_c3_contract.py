from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from core.ops.operational_stock_daily_truth_runner import run_operational_stock_daily_truth
from core.ops.policy_registry_c3 import (
    REQUIRED_C3_GATE_NAMES,
    promote_operational_decision_policy,
    validate_exception_queue_db,
    validate_manual_decision_approvals,
    validate_operational_decision_policy_registry,
    validate_policy_gate_results,
    validate_policy_registry_schema,
    validate_policy_source_freshness,
)
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate as migrate_p0
from scripts.migrate_029_policy_registry_c3 import migrate as migrate_c3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_YAML = PROJECT_ROOT / "config" / "operational_decision_policy.yaml"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _migrated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "app.db"
    migrate_p0(db_path)
    migrate_c3(db_path)
    return db_path


def _promoted_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = _migrated_db(tmp_path)
    monkeypatch.setenv("ENABLE_POLICY_REGISTRY_WRITE", "1")
    report = promote_operational_decision_policy(
        db_path=db_path,
        policy_path=POLICY_YAML,
        apply=True,
        backup_dir=tmp_path / "backups",
        actor="pytest",
        now="2026-05-03T12:00:00+05:00",
    )
    assert report["applied"] is True
    assert report["backup_path"]
    assert Path(report["backup_path"]).exists()
    return db_path


def _seed_freshness_for_all_sources(
    db_path: Path,
    *,
    status: str = "FRESH",
    as_of: str = "2026-05-03",
    observed_at: str = "2026-05-03T12:00:00+05:00",
    run_id: str = "pytest-freshness",
) -> None:
    with _connect(db_path) as conn:
        policy_version_id = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE status='ACTIVE'"
        ).fetchone()["policy_version_id"]
        rows = conn.execute(
            """
            SELECT policy_source_id
            FROM policy_source_registry
            WHERE required_for_publication = 1
              AND active_to IS NULL
            ORDER BY policy_source_id
            """
        ).fetchall()
        assert rows
        for row in rows:
            conn.execute(
                """
                INSERT INTO source_freshness_result (
                    freshness_result_id, run_id, policy_version_id, policy_source_id,
                    as_of_date, observed_at, max_observed_at, freshness_status,
                    max_age_value, max_age_unit, lag_seconds, blocks_publication,
                    evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 24, 'hours', 0,
                          CASE WHEN ?='FRESH' THEN 0 ELSE 1 END, '{}')
                """,
                (
                    f"fresh:{row['policy_source_id']}:{as_of}:{status.lower()}",
                    run_id,
                    policy_version_id,
                    row["policy_source_id"],
                    as_of,
                    observed_at,
                    observed_at,
                    status,
                    status,
                ),
            )
        conn.commit()


def _seed_required_gate_passes(db_path: Path) -> None:
    with _connect(db_path) as conn:
        policy_version_id = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE status='ACTIVE'"
        ).fetchone()["policy_version_id"]
        for gate_name in sorted(REQUIRED_C3_GATE_NAMES):
            conn.execute(
                """
                INSERT INTO policy_gate_result (
                    gate_result_id, run_id, policy_version_id, gate_name, domain,
                    status, severity, blocks_owner_publication, policy_paths_json,
                    source_ids_json, freshness_result_ids_json, message, evidence_json
                ) VALUES (?, 'pytest-gates', ?, ?, ?, 'PASS', 'INFO', 0,
                          '[]', '[]', '[]', 'fixture pass', '{}')
                """,
                (f"gate:{gate_name}:pass", policy_version_id, gate_name, gate_name),
            )
        conn.commit()


def _seed_minimal_runner_sources(db_path: Path, *, as_of: str = "2026-05-03") -> None:
    migrate_p0(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES (?, 'SKU_A_M', 'SKU_A', 'M', 3, 0)
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, idempotency_key
            ) VALUES (?, 'ANCHOR', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR',
                      3, 'ANCHOR_A', 'STOCK_ANCHOR', 'ledger-anchor-a')
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, status, return_flag
            ) VALUES ('O1', ?, 'SKU_A', 'SKU_A_M', 'M', 'Offer A',
                      'ACMEWEAR', 1, 'DELIVERED', 0)
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source, idempotency_key
            ) VALUES ('ACMEWEAR', 'O1', 'COMPLETED', ? || 'T10:00:00+05:00',
                      'fixture', 'ose-o1-completed')
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
            ) VALUES ('E1', 'O1', 'ACMEWEAR', 'OFFER_A', 1, 10000, 10000)
            """
        )
        conn.execute(
            """
            INSERT INTO ads_source_refresh_runs (
                run_id, started_at, finished_at, store_code, date_start, date_end, status
            ) VALUES ('ADS1', ? || 'T00:00:00+05:00', ? || 'T01:00:00+05:00',
                      'ACMEWEAR', ?, ?, 'SUCCESS')
            """,
            (as_of, as_of, as_of, as_of),
        )
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily (
                date, store_code, campaign_id, sku_key, cost_kzt, source_run_id, coverage_status
            ) VALUES (?, 'ACMEWEAR', 'CAMP1', 'SKU_A', 750, 'ADS1', 'COVERED')
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key, sku_id,
                ref_type, ref_id, source, event_hash
            ) VALUES (?, 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000, 'ACMEWEAR',
                      'SKU_A', 'SKU_A_M', 'ORDER', 'O1', 'ORDER_MODELLED', 'cash-o1')
            """,
            (as_of,),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close, cash_flow_kzt,
                receivables_flow_kzt, inventory_cost_flow_kzt, inventory_on_hand_close,
                inventory_inbound_close, inventory_on_delivery_close
            ) VALUES (?, 0, 10000, 0, 0, 0, 0, 10000, 10000, 0, 0, 0, 0, 0)
            """,
            (as_of,),
        )
        conn.commit()


def test_c3_schema_migration_creates_tables_views_and_active_policy_uniqueness(
    tmp_path: Path,
) -> None:
    db_path = _migrated_db(tmp_path)

    assert validate_policy_registry_schema(db_path) == []

    with _connect(db_path) as conn:
        objects = {
            row["name"]: row["type"]
            for row in conn.execute(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE name LIKE 'policy_%'
                   OR name LIKE 'source_%'
                   OR name LIKE 'v_policy_%'
                   OR name LIKE 'v_source_%'
                   OR name LIKE 'v_publication_%'
                   OR name = 'v_open_exception_queue'
                """
            )
        }
        assert objects["policy_version"] == "table"
        assert objects["policy_value"] == "table"
        assert objects["policy_source_registry"] == "table"
        assert objects["source_freshness_result"] == "table"
        assert objects["policy_gate_result"] == "table"
        assert objects["policy_change_event"] == "table"
        assert objects["source_pointer"] == "table"
        assert objects["v_policy_active_metadata"] == "view"
        assert objects["v_policy_active_value"] == "view"
        assert objects["v_source_freshness_current"] == "view"
        assert objects["v_publication_blockers"] == "view"
        assert objects["v_open_exception_queue"] == "view"

        base = {
            "namespace": "operational_decision_policy",
            "version": 1,
            "status": "ACTIVE",
            "effective_from": "2026-05-03T00:00:00+05:00",
            "timezone": "Asia/Almaty",
            "owner_role": "business_owner",
            "canonical_doc_path": "docs/ops/OPERATIONAL_DECISION_POLICY_V1.md",
            "source_yaml_path": "config/operational_decision_policy.yaml",
            "source_yaml_sha256": "fixture",
            "source_yaml_loaded_at": "2026-05-03T00:00:00+05:00",
            "approved_by": "owner",
            "approved_at": "2026-05-03T00:00:00+05:00",
            "created_by": "pytest",
        }
        conn.execute(
            """
            INSERT INTO policy_version (
                policy_version_id, namespace, version, status, effective_from,
                timezone, owner_role, canonical_doc_path, source_yaml_path,
                source_yaml_sha256, source_yaml_loaded_at, approved_by,
                approved_at, created_by
            ) VALUES ('pv-a', :namespace, :version, :status, :effective_from,
                      :timezone, :owner_role, :canonical_doc_path, :source_yaml_path,
                      :source_yaml_sha256, :source_yaml_loaded_at, :approved_by,
                      :approved_at, :created_by)
            """,
            base,
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO policy_version (
                    policy_version_id, namespace, version, status, effective_from,
                    timezone, owner_role, canonical_doc_path, source_yaml_path,
                    source_yaml_sha256, source_yaml_loaded_at, approved_by,
                    approved_at, created_by
                ) VALUES ('pv-b', :namespace, :version, :status, :effective_from,
                          :timezone, :owner_role, :canonical_doc_path, :source_yaml_path,
                          :source_yaml_sha256, :source_yaml_loaded_at, :approved_by,
                          :approved_at, :created_by)
                """,
                base,
            )


def test_policy_promotion_is_deterministic_idempotent_and_detects_yaml_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)

    assert validate_operational_decision_policy_registry(db_path, POLICY_YAML) == []

    second = promote_operational_decision_policy(
        db_path=db_path,
        policy_path=POLICY_YAML,
        apply=True,
        backup_dir=tmp_path / "backups",
        actor="pytest",
        now="2026-05-03T12:01:00+05:00",
    )
    assert second["applied"] is True
    assert second["inserted_policy_values"] == 0
    assert second["policy_version_reused"] is True

    with _connect(db_path) as conn:
        ads_value = conn.execute(
            """
            SELECT value_json
            FROM policy_value
            WHERE policy_path = 'ads_truth.active_kaspi_internal_ads_stores'
            """
        ).fetchone()["value_json"]
        assert json.loads(ads_value) == ["ACMEWEAR", "STOREB"]

        conn.execute(
            """
            UPDATE policy_value
            SET value_json = 'true'
            WHERE policy_path = 'stock_status_rules.pending_reduces_stock'
            """
        )
        conn.commit()

    errors = validate_operational_decision_policy_registry(db_path, POLICY_YAML)
    assert any("pending_reduces_stock" in err and "drift" in err.lower() for err in errors)


def test_source_registry_and_source_freshness_fail_closed_for_required_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)

    missing_errors = validate_policy_source_freshness(db_path, as_of="2026-05-03")
    assert any("missing freshness" in err.lower() for err in missing_errors)

    _seed_freshness_for_all_sources(db_path)
    assert validate_policy_source_freshness(db_path, as_of="2026-05-03") == []

    with _connect(db_path) as conn:
        source_id = conn.execute(
            """
            SELECT policy_source_id
            FROM policy_source_registry
            WHERE required_for_publication = 1
            ORDER BY policy_source_id
            LIMIT 1
            """
        ).fetchone()["policy_source_id"]
        policy_version_id = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE status='ACTIVE'"
        ).fetchone()["policy_version_id"]
        conn.execute(
            """
            INSERT INTO source_freshness_result (
                freshness_result_id, run_id, policy_version_id, policy_source_id,
                as_of_date, observed_at, max_observed_at, freshness_status,
                blocks_publication, evidence_json
            ) VALUES ('fresh:latest:stale', 'pytest-freshness', ?, ?,
                      '2026-05-03', '2026-05-03T12:05:00+05:00',
                      '2026-04-29T00:00:00+05:00', 'STALE', 1, '{}')
            """,
            (policy_version_id, source_id),
        )
        conn.commit()

    stale_errors = validate_policy_source_freshness(db_path, as_of="2026-05-03")
    assert any("STALE" in err and source_id in err for err in stale_errors)


def test_source_freshness_explicit_as_of_requires_matching_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_freshness_for_all_sources(
        db_path,
        as_of="2026-05-05",
        observed_at="2026-05-05T12:00:00+05:00",
        run_id="pytest-latest-only",
    )

    errors = validate_policy_source_freshness(db_path, as_of="2026-05-04", strict=True)

    with _connect(db_path) as conn:
        required_sources = [
            row["policy_source_id"]
            for row in conn.execute(
                """
                SELECT policy_source_id
                FROM policy_source_registry
                WHERE required_for_publication = 1
                  AND active_to IS NULL
                ORDER BY policy_source_id
                """
            )
        ]
    assert required_sources
    assert len(errors) == len(required_sources)
    assert all("2026-05-04" in err and "missing freshness result" in err for err in errors)
    assert all(source_id in "\n".join(errors) for source_id in required_sources)


def test_source_freshness_explicit_as_of_blocks_on_requested_row_not_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_freshness_for_all_sources(
        db_path,
        as_of="2026-05-04",
        observed_at="2026-05-04T12:00:00+05:00",
        run_id="pytest-requested",
    )
    _seed_freshness_for_all_sources(
        db_path,
        as_of="2026-05-05",
        observed_at="2026-05-05T12:00:00+05:00",
        run_id="pytest-latest",
    )

    with _connect(db_path) as conn:
        source_id = conn.execute(
            """
            SELECT policy_source_id
            FROM policy_source_registry
            WHERE required_for_publication = 1
            ORDER BY policy_source_id
            LIMIT 1
            """
        ).fetchone()["policy_source_id"]
        policy_version_id = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE status='ACTIVE'"
        ).fetchone()["policy_version_id"]
        conn.execute(
            """
            INSERT INTO source_freshness_result (
                freshness_result_id, run_id, policy_version_id, policy_source_id,
                as_of_date, observed_at, max_observed_at, freshness_status,
                blocks_publication, evidence_json
            ) VALUES ('fresh:requested:blocking', 'pytest-requested-blocking', ?, ?,
                      '2026-05-04', '2026-05-04T12:05:00+05:00',
                      '2026-04-29T00:00:00+05:00', 'STALE', 1, '{}')
            """,
            (policy_version_id, source_id),
        )
        conn.commit()

    errors = validate_policy_source_freshness(db_path, as_of="2026-05-04", strict=True)

    assert len(errors) == 1
    assert source_id in errors[0]
    assert "2026-05-04" in errors[0]
    assert "STALE" in errors[0]
    assert "blocks publication" in errors[0]


def test_source_freshness_without_as_of_preserves_latest_row_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_freshness_for_all_sources(
        db_path,
        status="STALE",
        as_of="2026-05-04",
        observed_at="2026-05-04T12:00:00+05:00",
        run_id="pytest-older-stale",
    )
    _seed_freshness_for_all_sources(
        db_path,
        as_of="2026-05-05",
        observed_at="2026-05-05T12:00:00+05:00",
        run_id="pytest-latest-fresh",
    )

    assert validate_policy_source_freshness(db_path, as_of=None, strict=True) == []


def test_source_freshness_cli_json_reports_requested_as_of_and_db_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_freshness_for_all_sources(
        db_path,
        as_of="2026-05-04",
        observed_at="2026-05-04T12:00:00+05:00",
        run_id="pytest-cli",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "validate_policy_source_freshness.py"),
            "--db",
            str(db_path),
            "--as-of",
            "2026-05-04",
            "--strict",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["db_path"] == str(db_path)
    assert len(payload["db_sha256"]) == 64
    assert payload["requested_as_of"] == "2026-05-04"
    assert payload["strict"] is True


def test_meta_source_scope_is_acmewear_and_storeb_uses_kaspi_internal_marketing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)

    with _connect(db_path) as conn:
        facebook = conn.execute(
            """
            SELECT policy_source_id, external_system, route_key,
                   required_for_gate, required_for_publication, freshness_basis
            FROM policy_source_registry
            WHERE policy_source_id='src_facebook_ads_external_ads'
            """
        ).fetchone()
        kaspi_internal = conn.execute(
            """
            SELECT policy_source_id, external_system, route_key,
                   required_for_gate, required_for_publication
            FROM policy_source_registry
            WHERE policy_source_id='src_web_automation_kaspi_marketing_directapi'
            """
        ).fetchone()

    assert facebook["external_system"] == "meta_instagram"
    assert facebook["route_key"] == "ACMEWEAR"
    assert facebook["required_for_gate"] == "ads_source_truth"
    assert facebook["required_for_publication"] == 1
    assert facebook["freshness_basis"] == "recursive_latest_artifact_mtime"
    assert "STOREB" not in str(facebook["route_key"])

    assert kaspi_internal["external_system"] == "kaspi_marketing_directapi"
    assert kaspi_internal["route_key"] == "ACMEWEAR_STOREB"
    assert kaspi_internal["required_for_gate"] == "ads_source_truth"
    assert kaspi_internal["required_for_publication"] == 1


def test_policy_promotion_refreshes_existing_source_registry_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET route_key=NULL,
                freshness_basis='file_mtime',
                notes='stale copied production row'
            WHERE policy_source_id='src_facebook_ads_external_ads'
            """
        )
        conn.commit()

    promote_operational_decision_policy(
        db_path=db_path,
        policy_path=POLICY_YAML,
        apply=True,
        backup_dir=tmp_path / "backups",
        actor="pytest",
        now="2026-05-03T12:02:00+05:00",
    )

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT route_key, freshness_basis, notes
            FROM policy_source_registry
            WHERE policy_source_id='src_facebook_ads_external_ads'
            """
        ).fetchone()

    assert row["route_key"] == "ACMEWEAR"
    assert row["freshness_basis"] == "recursive_latest_artifact_mtime"
    assert "STOREB uses Kaspi internal marketing evidence" in row["notes"]


def test_gate_results_publication_blockers_and_manual_approvals_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)

    assert validate_policy_gate_results(db_path)

    _seed_required_gate_passes(db_path)
    assert validate_policy_gate_results(db_path) == []

    with _connect(db_path) as conn:
        policy_version_id = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE status='ACTIVE'"
        ).fetchone()["policy_version_id"]
        conn.execute(
            """
            INSERT INTO policy_gate_result (
                gate_result_id, run_id, policy_version_id, gate_name, domain,
                status, severity, blocks_owner_publication, policy_paths_json,
                source_ids_json, freshness_result_ids_json, message, evidence_json
            ) VALUES ('gate:ads:block', 'pytest-gates', ?, 'ads_source_truth',
                      'ads', 'BLOCKED', 'ERROR', 1, '[]', '[]', '[]',
                      'ads stale', '{}')
            """,
            (policy_version_id,),
        )
        conn.execute(
            """
            INSERT INTO manual_decision_approval (
                approval_id, domain, request_type, policy_version_id,
                owner_role_required, decision, approved_by, approved_at,
                valid_from, evidence_paths_json, cannot_override_publication_gate
            ) VALUES ('approval-bad', 'ads', 'publication_waiver', ?,
                      'business_owner', 'APPROVED', 'owner',
                      '2026-05-03T12:00:00+05:00',
                      '2026-05-03T12:00:00+05:00',
                      '["/tmp/evidence.md"]', 0)
            """,
            (policy_version_id,),
        )
        blockers = conn.execute("SELECT gate_name FROM v_publication_blockers").fetchall()
        conn.commit()

    assert [row["gate_name"] for row in blockers] == ["ads_source_truth"]
    assert any("ads_source_truth" in err for err in validate_policy_gate_results(db_path))
    assert any("cannot override publication" in err.lower() for err in validate_manual_decision_approvals(db_path))


def test_exception_queue_db_contract_requires_owner_action_evidence_and_open_view(
    tmp_path: Path,
) -> None:
    db_path = _migrated_db(tmp_path)

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, run_id, domain, severity, status, reason,
                owner, recommended_action, evidence_paths_json
            ) VALUES ('ex-bad', 'pytest', 'ads', 'critical', 'OPEN',
                      'ADS_REFRESH_MISSING', '', '', '[]')
            """
        )
        conn.commit()

    errors = validate_exception_queue_db(db_path, strict=True)
    assert any("owner" in err for err in errors)
    assert any("recommended_action" in err for err in errors)
    assert any("evidence_paths_json" in err for err in errors)

    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE exception_queue
            SET owner='business_owner',
                recommended_action='Refresh required ads source and rerun C3 gates',
                evidence_paths_json='["/tmp/source.md"]'
            WHERE exception_id='ex-bad'
            """
        )
        row = conn.execute(
            "SELECT exception_id, owner FROM v_open_exception_queue WHERE exception_id='ex-bad'"
        ).fetchone()
        conn.commit()

    assert dict(row) == {"exception_id": "ex-bad", "owner": "business_owner"}
    assert validate_exception_queue_db(db_path, strict=True) == []


def test_change_events_rollback_metadata_and_source_pointer_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)

    with _connect(db_path) as conn:
        event = conn.execute(
            """
            SELECT event_type, db_backup_path, git_head
            FROM policy_change_event
            WHERE event_type='PROMOTE'
            ORDER BY event_at DESC
            LIMIT 1
            """
        ).fetchone()
        assert event["db_backup_path"]
        assert event["git_head"]

        conn.execute(
            """
            INSERT INTO policy_change_event (
                event_id, event_type, policy_version_id, from_policy_version_id,
                to_policy_version_id, actor, reason, db_backup_path, git_head
            )
            SELECT 'rollback-fixture', 'ROLLBACK', policy_version_id,
                   policy_version_id, policy_version_id, 'pytest',
                   'fixture rollback metadata', ?, ?
            FROM policy_version
            WHERE status='ACTIVE'
            """,
            (event["db_backup_path"], event["git_head"]),
        )
        wiki = conn.execute(
            """
            SELECT memory_tier, requires_source_refresh_before_apply, raw_copy_allowed
            FROM source_pointer
            WHERE source_kind='wiki'
            ORDER BY source_pointer_id
            LIMIT 1
            """
        ).fetchone()
        primary = conn.execute(
            """
            SELECT memory_tier, requires_source_refresh_before_apply, raw_copy_allowed
            FROM source_pointer
            WHERE memory_tier='primary_source'
            ORDER BY source_pointer_id
            LIMIT 1
            """
        ).fetchone()
        rollback = conn.execute(
            "SELECT event_id FROM policy_change_event WHERE event_type='ROLLBACK'"
        ).fetchone()
        conn.commit()

    assert rollback["event_id"] == "rollback-fixture"
    assert dict(wiki) == {
        "memory_tier": "compiled_memory",
        "requires_source_refresh_before_apply": 1,
        "raw_copy_allowed": 0,
    }
    assert dict(primary) == {
        "memory_tier": "primary_source",
        "requires_source_refresh_before_apply": 0,
        "raw_copy_allowed": 1,
    }


def test_daily_runner_require_c3_policy_fails_closed_when_registry_or_sources_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_runner_sources(db_path)

    missing_report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth_missing",
        run_id="fixture-c3-missing",
        allow_green_owner_output=True,
        require_c3_policy=True,
    )
    assert missing_report.status == "RED"
    assert any(result["gate_name"] == "c3_policy_registry" for result in missing_report.validation_results)
    assert any(exc["reason"] == "C3_POLICY_REGISTRY_MISSING" for exc in missing_report.exceptions)

    migrate_c3(db_path)
    monkeypatch.setenv("ENABLE_POLICY_REGISTRY_WRITE", "1")
    promote_operational_decision_policy(
        db_path=db_path,
        policy_path=POLICY_YAML,
        apply=True,
        backup_dir=tmp_path / "backups",
        actor="pytest",
        now="2026-05-03T12:00:00+05:00",
    )

    blocked_report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth_blocked",
        run_id="fixture-c3-blocked",
        allow_green_owner_output=True,
        require_c3_policy=True,
    )
    assert blocked_report.status == "RED"
    reasons = {exc["reason"] for exc in blocked_report.exceptions}
    assert "C3_SOURCE_FRESHNESS_FAIL" in reasons
    assert "C3_POLICY_GATE_RESULT_FAIL" in reasons
