from __future__ import annotations

import json
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from core.ops.operational_stock_daily_truth_runner import run_operational_stock_daily_truth
from core.ops.policy_materialization_c3 import (
    C3_MATERIALIZATION_ENV_GATE,
    backfill_exception_queue_metadata,
    materialize_c3_policy_state,
    materialize_copied_temp_source_freshness_bridge,
    materialize_policy_gate_results,
    materialize_source_freshness_results,
)
from core.ops.policy_registry_c3 import (
    REQUIRED_C3_GATE_NAMES,
    promote_operational_decision_policy,
    validate_exception_queue_db,
    validate_policy_gate_results,
    validate_policy_source_freshness,
)
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate as migrate_p0
from scripts.migrate_029_policy_registry_c3 import migrate as migrate_c3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_YAML = PROJECT_ROOT / "config" / "operational_decision_policy.yaml"
WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID = "src_web_automation_kaspi_marketing_directapi"
WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE = (
    Path("runs")
    / "ab_ads_source_refresh_data_gathering"
    / "20260505_source_packet_standardization"
    / "kaspi_marketing_source_freshness_packet.json"
)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _set_mtime(path: Path, iso_value: str) -> None:
    ts = datetime.fromisoformat(iso_value).timestamp()
    os.utime(path, (ts, ts))


def _test_sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tiny_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute("CREATE TABLE source_rows (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO source_rows (value) VALUES ('ok')")
        conn.commit()


def _write_json_fixture(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_copied_temp_bridge_input(
    tmp_path: Path,
    *,
    source_id: str = "src_payment_evidence_root",
    production_authority: bool = False,
    source_packet_sha: str | None = None,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    packet_path = tmp_path / "NO_NEW_PAYMENT_CONTRACT_COPIED_TEMP_20260517.md"
    packet_path.write_text(
        "SOURCE_FRESHNESS_BRIDGE_COPIED_TEMP_V1\n"
        "No production authority.\n",
        encoding="utf-8",
    )
    bridge_path = tmp_path / "copied_temp_bridge_rows.json"
    _write_json_fixture(
        bridge_path,
        {
            "bridge_rows": [
                {
                    "source_id": source_id,
                    "source_packet_path": str(packet_path),
                    "source_packet_sha": source_packet_sha or _test_sha256_file(packet_path),
                    "captured_at": "2026-05-17T22:20:00+05:00",
                    "as_of": "2026-05-17",
                    "status": "FRESH",
                    "blocks_publication": False,
                    "proof_scope": "copied_temp",
                    "production_authority": production_authority,
                    "contract_id": "PAYMENT_ROOT_NO_NEW_PAYMENT_COPIED_TEMP_20260517",
                }
            ]
        },
    )
    return bridge_path, packet_path


def _zero_write_safety() -> dict[str, object]:
    return {
        "external_write_operations": 0,
        "ad_platform_write_operations": 0,
        "campaign_bid_budget_product_state_changes": 0,
        "autonomous_business_writes": 0,
        "secret_values_stored": False,
    }


def _write_web_automation_kaspi_marketing_packet(
    source_root: Path,
    *,
    gate: str = "GREEN",
    omit_top_level_keys: tuple[str, ...] = (),
    missing_storeb_coverage: bool = False,
    coverage_date: str = "2026-05-04",
    sqlite_hash_mismatch: bool = False,
    sqlite_path_missing: bool = False,
) -> Path:
    run_root = source_root / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE.parent
    source_root_acmewear = run_root / "source_roots" / "acmewear"
    source_root_storeb = run_root / "source_roots" / "storeb"
    source_root_acmewear.mkdir(parents=True, exist_ok=True)
    source_root_storeb.mkdir(parents=True, exist_ok=True)

    sqlite_entries: list[dict[str, object]] = []
    for store, root in (("ACMEWEAR", source_root_acmewear), ("STOREB", source_root_storeb)):
        sqlite_path = root / "kaspi_marketing.sqlite"
        _write_tiny_sqlite(sqlite_path)
        sqlite_entries.append(
            {
                "role": "source_sqlite",
                "store": store,
                "path": str(sqlite_path),
                "exists": True,
                "sha256": _test_sha256_file(sqlite_path),
                "used_for_gate": True,
                "sqlite_integrity_check": "ok",
                "sqlite_tables": ["source_rows"],
            }
        )
    if sqlite_hash_mismatch:
        sqlite_entries[0]["sha256"] = "0" * 64
    if sqlite_path_missing:
        sqlite_entries[1]["path"] = str(source_root_storeb / "missing_kaspi_marketing.sqlite")

    evidence_summaries: list[dict[str, object]] = []
    closeouts: list[dict[str, object]] = []
    no_write_checks: list[dict[str, object]] = []
    for store, root in (("ACMEWEAR", source_root_acmewear), ("STOREB", source_root_storeb)):
        summary_path = root / "source_evidence_summary.json"
        _write_json_fixture(
            summary_path,
            {
                "store": store,
                "kaspi_marketing_gate": "GREEN",
                "latest_covered_date": coverage_date,
                "write_safety": _zero_write_safety(),
            },
        )
        evidence_summaries.append(
            {
                "role": "source_evidence_summary",
                "store": store,
                "path": str(summary_path),
                "exists": True,
                "sha256": _test_sha256_file(summary_path),
                "used_for_gate": True,
                "json_valid": True,
            }
        )

        closeout_path = root / f"WA_{store}_CLOSEOUT.md"
        closeout_path.write_text(
            "Gate: GREEN\n"
            "external_write_operations: 0\n"
            "ad_platform_write_operations: 0\n"
            "campaign_bid_budget_product_state_changes: 0\n"
            "autonomous_business_writes: 0\n",
            encoding="utf-8",
        )
        closeouts.append(
            {
                "role": "source_closeout",
                "store": store,
                "path": str(closeout_path),
                "exists": True,
                "sha256": _test_sha256_file(closeout_path),
                "used_for_gate": True,
            }
        )
        no_write_checks.append(
            {
                "store": store,
                "path": str(closeout_path),
                "states_no_autonomous_business_writes": True,
                "states_no_external_writes": True,
                "states_no_campaign_bid_budget_product_state_changes": True,
                "states_no_secret_storage": True,
            }
        )

    store_coverage = {
        "ACMEWEAR": {
            "gate": "GREEN",
            "business_store_code": "ACMEWEAR",
            "latest_covered_date": coverage_date,
            "date_coverage_through_2026_05_04": coverage_date >= "2026-05-04",
            "write_safety_from_summary": _zero_write_safety(),
        },
        "STOREB": {
            "gate": "GREEN",
            "business_store_code": "STOREB",
            "latest_covered_date": coverage_date,
            "date_coverage_through_2026_05_04": coverage_date >= "2026-05-04",
            "write_safety_from_closeouts": _zero_write_safety(),
        },
    }
    if missing_storeb_coverage:
        store_coverage.pop("STOREB")

    packet: dict[str, object] = {
        "schema_version": "kaspi_marketing_source_freshness_packet.v1",
        "packet_name": "kaspi_marketing_source_freshness_packet",
        "generated_by": "WA_AGENT_38",
        "generated_at": "2026-05-05T13:58:33+05:00",
        "gate": gate,
        "as_of": "2026-05-04",
        "source_policy_key": WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID,
        "ab_can_clear_src_web_automation_kaspi_marketing_directapi": True,
        "external_write_operations": 0,
        "ad_platform_write_operations": 0,
        "campaign_bid_budget_product_state_changes": 0,
        "autonomous_business_writes": 0,
        "read_only_external_operations": True,
        "agent38_live_external_operations": 0,
        "agent38_live_browser_operations": 0,
        "agent38_autonomous_business_writes": 0,
        "required_inputs": [str(source_root_acmewear), str(source_root_storeb)],
        "source_roots": [
            {"role": "acmewear", "path": str(source_root_acmewear), "exists": True},
            {"role": "storeb", "path": str(source_root_storeb), "exists": True},
        ],
        "strict_requirements": {
            "stores_required": ["ACMEWEAR", "STOREB"],
            "stores_covered": ["ACMEWEAR"] if missing_storeb_coverage else ["ACMEWEAR", "STOREB"],
            "date_coverage_through": coverage_date,
            "date_coverage_through_2026_05_04": coverage_date >= "2026-05-04",
            "all_referenced_files_exist": True,
            "all_recorded_hashes_match_at_generation": True,
            "all_source_evidence_summaries_json_valid": True,
            "all_source_sqlite_integrity_ok": True,
            "source_write_counts_zero_or_closeout_proven_zero": True,
            "no_live_calls_made_by_agent38": True,
            "no_autonomous_business_mutation_by_agent38": True,
        },
        "source_sqlite_files": sqlite_entries,
        "source_evidence_summaries": evidence_summaries,
        "source_closeout_files": closeouts,
        "closeout_text_no_write_checks": no_write_checks,
        "store_coverage": store_coverage,
        "issues": [],
        "missing_fields": [],
    }
    for key in omit_top_level_keys:
        packet.pop(key, None)

    packet_path = source_root / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE
    _write_json_fixture(packet_path, packet)
    return packet_path


def _promoted_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
        now="2026-05-03T12:00:00+05:00",
    )
    monkeypatch.delenv("ENABLE_POLICY_REGISTRY_WRITE", raising=False)
    return db_path


def _seed_stale_operational_truth(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-04-15', 'SKU_A_M', 'SKU_A', 'M', 3, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, idempotency_key
            ) VALUES ('2026-04-15', 'ANCHOR', 'SKU_A', 'SKU_A_M', 'M',
                      'ACMEWEAR', 3, 'ANCHOR_A', 'STOCK_ANCHOR', 'ledger-a')
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, status, return_flag
            ) VALUES ('O1', '2026-04-15', 'SKU_A', 'SKU_A_M', 'M',
                      'Offer A', 'ACMEWEAR', 1, 'DELIVERED', 0)
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, source, event_hash
            ) VALUES ('2026-04-15', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                      'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'O1',
                      'ORDER_MODELLED', 'cash-o1')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close,
                cash_flow_kzt, receivables_flow_kzt, inventory_cost_flow_kzt,
                inventory_on_hand_close, inventory_inbound_close,
                inventory_on_delivery_close
            ) VALUES ('2026-04-15', 0, 10000, 0, 0, 0, 0, 10000,
                      10000, 0, 0, 0, 0, 0)
            """
        )
        conn.commit()


def _seed_fresh_operational_truth_with_future_order_observations(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-05-04', 'SKU_A_M', 'SKU_A', 'M', 3, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, idempotency_key
            ) VALUES ('2026-05-04', 'ANCHOR', 'SKU_A', 'SKU_A_M', 'M',
                      'ACMEWEAR', 3, 'ANCHOR_A', 'STOCK_ANCHOR', 'ledger-a')
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, status, return_flag
            ) VALUES ('O1', '2026-05-04', 'SKU_A', 'SKU_A_M', 'M',
                      'Offer A', 'ACMEWEAR', 1, 'DELIVERED', 0)
            """
        )
        conn.executemany(
            """
            INSERT INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source,
                idempotency_key
            ) VALUES ('ACMEWEAR', ?, 'DELIVERED', ?, 'pytest', ?)
            """,
            [
                ("O1", "2026-05-04T10:00:00+05:00", "status-o1-eligible"),
                ("O2", "2026-05-05T06:00:56+05:00", "status-o2-future"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, product_id, offer_id, quantity,
                unit_price_kzt, total_price_kzt, raw_json, updated_at
            ) VALUES (?, ?, 'ACMEWEAR', 'P1', 'SKU_A_M', 1, 10000, 10000, '{}', ?)
            """,
            [
                ("entry-o1-eligible", "O1", "2026-05-04T12:00:00+05:00"),
                ("entry-o2-future", "O2", "2026-05-05T12:54:59+05:00"),
            ],
        )
        conn.execute(
            """
            INSERT INTO ads_source_refresh_runs (
                run_id, started_at, finished_at, store_code, date_start,
                date_end, product_rows_total, status
            ) VALUES ('ads-run-a', '2026-05-04T00:00:00+05:00',
                      '2026-05-04T01:00:00+05:00', 'ACMEWEAR',
                      '2026-05-04', '2026-05-04', 1, 'SUCCESS')
            """
        )
        conn.execute(
            """
            INSERT INTO ads_campaign_product_daily (
                date, store_code, campaign_id, campaign_name, sku_key,
                cost_kzt, coverage_status
            ) VALUES ('2026-05-04', 'ACMEWEAR', 'C1', 'Campaign A',
                      'SKU_A', 100, 'MAPPED')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, source, event_hash
            ) VALUES ('2026-05-04', 'CASH_IN', 'KASPI_PAY_ACMEWEAR', 10000,
                      'ACMEWEAR', 'SKU_A', 'SKU_A_M', 'ORDER', 'O1',
                      'ORDER_MODELLED', 'cash-o1')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_open, cash_close, receivables_open, receivables_close,
                inventory_cost_open, inventory_cost_close, capital_close,
                cash_flow_kzt, receivables_flow_kzt, inventory_cost_flow_kzt,
                inventory_on_hand_close, inventory_inbound_close,
                inventory_on_delivery_close
            ) VALUES ('2026-05-04', 0, 10000, 0, 0, 0, 0, 10000,
                      10000, 0, 0, 0, 0, 0)
            """
        )
        conn.commit()


def _point_sources_to_fixtures(db_path: Path, tmp_path: Path) -> None:
    fresh_file = tmp_path / "fresh.md"
    fresh_file.write_text("fresh local source\n", encoding="utf-8")
    _set_mtime(fresh_file, "2026-05-03T20:00:00+05:00")
    stale_file = tmp_path / "stale.md"
    stale_file.write_text("stale local source\n", encoding="utf-8")
    old_ts = 1_777_665_600  # 2026-04-30T00:00:00Z
    os.utime(stale_file, (old_ts, old_ts))
    bank_file = tmp_path / "bank_accounts_manual_ingest.yaml"
    bank_file.write_text(
        "as_of: 2026-05-03 19:59:00 GMT+5\n"
        "stores:\n"
        "  ACMEWEAR:\n"
        "    accounts:\n"
        "      kaspi_pay:\n"
        "        balance_kzt:\n",
        encoding="utf-8",
    )
    directory = tmp_path / "dir_source"
    directory.mkdir()

    replacements = {
        "src_web_automation_kaspi_marketing_directapi": str(fresh_file),
        "src_facebook_ads_external_ads": str(stale_file),
        "src_bank_manual_ingest": str(bank_file),
        "src_ecommerce_po_artifacts": str(directory),
        "src_sourcing_research_supplier_routes": str(directory),
        "src_inbound_workbook": str(stale_file),
        "src_payment_evidence_root": str(directory),
        "src_commerce_ops_wiki_context": str(directory),
        "src_business_wiki_context": str(directory),
        "src_finance_exec_wiki_context": str(directory),
    }
    with _connect(db_path) as conn:
        for source_id, source_path in replacements.items():
            conn.execute(
                """
                UPDATE policy_source_registry
                SET source_path=?
                WHERE policy_source_id=?
                """,
                (source_path, source_id),
            )
        conn.commit()


def _write_meta_source_packet(
    source_root: Path,
    *,
    dates: list[str] | None = None,
    gate: str = "GREEN",
    successfully_fetched: list[str] | None = None,
    platform_writes_occurred: bool = False,
    budget_writes_occurred: bool = False,
    autonomous_business_writes_performed: bool = False,
    deterministic_purchase_attribution_claimed: bool = False,
    any_spend_found: bool = False,
    ab_can_clear: bool = True,
    packet_account_id: str | None = None,
) -> Path:
    requested_dates = dates or ["2026-05-03", "2026-05-04"]
    fetched_dates = requested_dates if successfully_fetched is None else successfully_fetched
    run_root = source_root / "runs" / "ab_source_freshness_20260505_acmewear_meta_live_refresh"
    raw_root = run_root / "raw_meta_source"
    raw_paths: dict[str, str] = {}
    date_results: list[dict[str, object]] = []
    for date in requested_dates:
        raw_path = raw_root / date / f"meta_insights_live_readonly_{date}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            json.dumps(
                {
                    "run_id": "pytest-meta-live-read",
                    "run_date": date,
                    "account_id": "1517999585924947",
                    "levels": {"campaign": []},
                }
            ),
            encoding="utf-8",
        )
        raw_paths[date] = str(raw_path)
        date_results.append(
            {
                "date": date,
                "source_status": "SUCCESS" if date in fetched_dates else "MISSING",
                "clears_source_freshness": date in fetched_dates,
                "any_spend_found": any_spend_found,
                "spend": 100.0 if any_spend_found else 0.0,
                "raw_evidence_path": str(raw_path),
            }
        )
    packet = {
        "generated_at_utc": "2026-05-05T07:55:12Z",
        "gate": gate,
        "dates_requested": requested_dates,
        "dates_successfully_fetched": fetched_dates,
        "dates_clearing_source_freshness": fetched_dates,
        "source_freshness_cleared_by_date": {date: date in fetched_dates for date in requested_dates},
        "raw_evidence_paths": raw_paths,
        "platform_writes_occurred": platform_writes_occurred,
        "budget_status_campaign_adset_ad_writes_occurred": budget_writes_occurred,
        "autonomous_business_writes_performed": autonomous_business_writes_performed,
        "deterministic_purchase_attribution_claimed": deterministic_purchase_attribution_claimed,
        "any_spend_found": any_spend_found,
        "ab_can_clear_src_facebook_ads_external_ads": ab_can_clear,
        "date_results": date_results,
    }
    if packet_account_id is not None:
        packet["account_id"] = packet_account_id
    packet_path = run_root / "meta_live_refresh_summary.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return packet_path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _insert_meta_external_spend_ingestion(
    db_path: Path,
    *,
    packet_path: Path,
    source_root: Path,
) -> None:
    raw_path = (
        source_root
        / "runs"
        / "ab_source_freshness_20260505_acmewear_meta_live_refresh"
        / "raw_meta_source"
        / "2026-05-04"
        / "meta_insights_live_readonly_2026-05-04.json"
    )
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE meta_external_ads_spend_daily (
                date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                source_system TEXT NOT NULL,
                account_id TEXT NOT NULL,
                spend_amount REAL NOT NULL,
                currency_code TEXT NOT NULL,
                spend_basis TEXT NOT NULL,
                campaign_row_count INTEGER NOT NULL DEFAULT 0,
                adset_row_count INTEGER NOT NULL DEFAULT 0,
                ad_row_count INTEGER NOT NULL DEFAULT 0,
                packet_path TEXT NOT NULL,
                packet_sha256 TEXT NOT NULL,
                raw_evidence_path TEXT NOT NULL,
                raw_evidence_sha256 TEXT NOT NULL,
                raw_source_run_id TEXT,
                raw_source_fetched_at TEXT,
                generated_at_utc TEXT,
                publication_attribution_claimed INTEGER NOT NULL DEFAULT 0,
                run_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                PRIMARY KEY (source_system, store_code, date, account_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO meta_external_ads_spend_daily (
                date, store_code, source_system, account_id, spend_amount,
                currency_code, spend_basis, campaign_row_count, adset_row_count,
                ad_row_count, packet_path, packet_sha256, raw_evidence_path,
                raw_evidence_sha256, raw_source_run_id, raw_source_fetched_at,
                generated_at_utc, publication_attribution_claimed, run_id,
                ingested_at, created_by
            ) VALUES (
                '2026-05-04', 'ACMEWEAR', 'meta_instagram', '1517999585924947', 100.0,
                'UNKNOWN_META_ACCOUNT_CURRENCY', 'campaign', 0, 0, 0,
                ?, ?, ?, ?, 'pytest', '2026-05-05T07:55:12Z',
                '2026-05-05T07:55:12Z', 0, 'pytest-meta-spend-ingest',
                '2026-05-05T07:56:00Z', 'pytest'
            )
            """,
            (str(packet_path), _sha256_file(packet_path), str(raw_path), _sha256_file(raw_path)),
        )
        conn.commit()


def _point_facebook_source_to_root(db_path: Path, source_root: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET source_path=?
            WHERE policy_source_id='src_facebook_ads_external_ads'
            """,
            (str(source_root),),
        )
        conn.commit()


def _materialize_and_get_facebook_source(
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sqlite3.Row:
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-meta-source-packet",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT freshness_status, max_observed_at, blocks_publication,
                   row_count, evidence_json
            FROM v_source_freshness_current
            WHERE policy_source_id='src_facebook_ads_external_ads'
            """
        ).fetchone()
    assert row is not None
    return row


def _point_web_automation_kaspi_marketing_source_to_root(
    db_path: Path,
    source_root: Path,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET source_path=?
            WHERE policy_source_id=?
            """,
            (str(source_root), WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID),
        )
        conn.commit()


def _materialize_and_get_web_automation_kaspi_marketing_source(
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sqlite3.Row:
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-web-automation-kaspi-marketing-packet",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT freshness_status, max_observed_at, blocks_publication,
                   row_count, evidence_json
            FROM v_source_freshness_current
            WHERE policy_source_id=?
            """,
            (WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID,),
        ).fetchone()
    assert row is not None
    return row


def _seed_agent6_stock_exception(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, run_id, domain, severity, status, reason, evidence_json
            ) VALUES (
                'AGENT6_STOCK_REBUILD_20PCT_20260503:NEGATIVE_RAW_LEDGER_BALANCE:SKU_A',
                'AGENT6_STOCK_REBUILD_20PCT_20260503',
                'STOCK',
                'HIGH',
                'OPEN',
                'NEGATIVE_RAW_LEDGER_BALANCE: raw replay went below zero',
                '{"sku_key":"SKU_A","raw_current_stock":-2}'
            )
            """
        )
        conn.commit()


def _seed_agent6_exception(
    db_path: Path,
    *,
    reason_code: str,
    suffix: str,
    evidence: dict[str, object],
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, run_id, domain, severity, status, reason, evidence_json
            ) VALUES (?, 'AGENT6_STOCK_REBUILD_20PCT_20260503', 'STOCK',
                      'HIGH', 'OPEN', ?, ?)
            """,
            (
                f"AGENT6_STOCK_REBUILD_20PCT_20260503:{reason_code}:{suffix}",
                f"{reason_code}: fixture exception",
                json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()


def _exception_gate(db_path: Path) -> sqlite3.Row:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT status, blocks_owner_publication, message, evidence_json
            FROM v_policy_gate_latest
            WHERE gate_name='exception_queue'
            """
        ).fetchone()
    assert row is not None
    return row


def test_source_freshness_materializer_records_current_rows_without_hiding_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)

    dry = materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=False,
    )
    assert dry["applied"] is False
    assert dry["backup_path"] is None
    assert dry["row_count"] == dry["active_source_count"]

    assert validate_policy_source_freshness(db_path, as_of="2026-05-03")

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    applied = materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert Path(applied["backup_path"]).exists()
    assert applied["inserted_or_replaced"] == applied["active_source_count"]

    second = materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert second["source_freshness_result_count_after"] == applied["source_freshness_result_count_after"]

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT policy_source_id, freshness_status, blocks_publication,
                   row_count, evidence_json
            FROM v_source_freshness_current
            ORDER BY policy_source_id
            """
        ).fetchall()

    statuses = {row["policy_source_id"]: row["freshness_status"] for row in rows}
    assert statuses["src_ab_db_operational_truth"] == "BLOCKED"
    assert statuses["src_bank_manual_ingest"] == "BLOCKED"
    assert statuses["src_facebook_ads_external_ads"] == "STALE"
    assert statuses["src_web_automation_kaspi_marketing_directapi"] == "MISSING"
    assert all(status != "FRESH" for source_id, status in statuses.items() if "missing" in source_id)
    web_automation_evidence = json.loads(
        next(
            row["evidence_json"]
            for row in rows
            if row["policy_source_id"] == "src_web_automation_kaspi_marketing_directapi"
        )
    )
    assert "KASPI_MARKETING_SOURCE_PACKET_MISSING" in web_automation_evidence["issues"]
    evidence = json.loads(
        next(row["evidence_json"] for row in rows if row["policy_source_id"] == "src_bank_manual_ingest")
    )
    assert evidence["bank_manual_ingest_issues"]
    assert validate_policy_source_freshness(db_path, as_of="2026-05-03")


def test_source_freshness_materializer_can_filter_source_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)

    dry = materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-filtered-source-dry",
        apply=False,
        source_ids={"src_bank_manual_ingest"},
    )
    assert dry["applied"] is False
    assert dry["row_count"] == 1
    assert dry["active_source_count"] == 1
    assert dry["source_ids"] == ["src_bank_manual_ingest"]
    assert dry["source_filter"] == ["src_bank_manual_ingest"]

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    applied = materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-filtered-source-apply",
        apply=True,
        backup_dir=tmp_path / "backups",
        source_ids={"src_bank_manual_ingest"},
    )
    assert applied["inserted_or_replaced"] == 1

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT policy_source_id, freshness_status
            FROM source_freshness_result
            WHERE run_id='pytest-filtered-source-apply'
            """
        ).fetchall()

    assert [row["policy_source_id"] for row in rows] == ["src_bank_manual_ingest"]


def test_ab_operational_truth_child_split_blocks_dependent_gates_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")

    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-ab-child-split-source",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    materialize_policy_gate_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-ab-child-split-gates",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with _connect(db_path) as conn:
        source_rows = conn.execute(
            """
            SELECT psr.policy_source_id, psr.required_for_gate,
                   psr.required_for_publication, current.freshness_status,
                   current.blocks_publication, current.evidence_json
            FROM policy_source_registry psr
            LEFT JOIN v_source_freshness_current current
              ON current.policy_source_id = psr.policy_source_id
            WHERE psr.policy_source_id LIKE 'src_ab_db_%truth'
            ORDER BY psr.policy_source_id
            """
        ).fetchall()
        gate_rows = conn.execute(
            """
            SELECT gate_name, status, blocks_owner_publication,
                   source_ids_json, evidence_json
            FROM v_policy_gate_latest
            WHERE gate_name IN ('stock_source_truth', 'ads_source_truth', 'source_freshness')
            ORDER BY gate_name
            """
        ).fetchall()

    sources = {row["policy_source_id"]: row for row in source_rows}
    expected_children = {
        "src_ab_db_order_entry_truth",
        "src_ab_db_cashflow_truth",
        "src_ab_db_stock_truth",
        "src_ab_db_sales_truth",
        "src_ab_db_order_status_truth",
        "src_ab_db_ads_truth",
    }
    assert expected_children.issubset(sources)
    assert sources["src_ab_db_operational_truth"]["required_for_publication"] == 0
    assert sources["src_ab_db_operational_truth"]["required_for_gate"] == "source_freshness_rollup"
    assert sources["src_ab_db_stock_truth"]["freshness_status"] == "STALE"
    assert sources["src_ab_db_stock_truth"]["blocks_publication"] == 1
    stock_evidence = json.loads(sources["src_ab_db_stock_truth"]["evidence_json"])
    assert stock_evidence["contract_id"] == "AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1"
    assert {item["table"] for item in stock_evidence["table_observations"]} == {
        "fact_inventory_snapshot_size",
        "stock_ledger",
    }

    gate_by_name = {row["gate_name"]: row for row in gate_rows}
    assert gate_by_name["stock_source_truth"]["status"] == "BLOCKED"
    assert gate_by_name["stock_source_truth"]["blocks_owner_publication"] == 1
    stock_gate_source_ids = set(json.loads(gate_by_name["stock_source_truth"]["source_ids_json"]))
    assert "src_ab_db_stock_truth" in stock_gate_source_ids
    assert "src_ab_db_sales_truth" in stock_gate_source_ids
    assert "src_ab_db_order_status_truth" in stock_gate_source_ids
    assert "src_ab_db_operational_truth" not in stock_gate_source_ids

    assert gate_by_name["ads_source_truth"]["status"] == "BLOCKED"
    ads_gate_source_ids = set(json.loads(gate_by_name["ads_source_truth"]["source_ids_json"]))
    assert "src_ab_db_ads_truth" in ads_gate_source_ids

    source_errors = validate_policy_source_freshness(db_path, as_of="2026-05-03")
    assert any("src_ab_db_stock_truth" in err and "STALE" in err for err in source_errors)
    assert not any("src_ab_db_operational_truth" in err for err in source_errors)


def test_copied_temp_source_freshness_bridge_materializes_exact_packet_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    bridge_path, packet_path = _write_copied_temp_bridge_input(tmp_path)

    dry = materialize_copied_temp_source_freshness_bridge(
        db_path=db_path,
        bridge_path=bridge_path,
        as_of="2026-05-17",
        run_id="pytest-copied-temp-bridge",
        apply=False,
    )
    assert dry["applied"] is False
    assert dry["row_count"] == 1
    assert dry["production_authority"] is False
    assert dry["proof_scope"] == "copied_temp"

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    applied = materialize_copied_temp_source_freshness_bridge(
        db_path=db_path,
        bridge_path=bridge_path,
        as_of="2026-05-17",
        run_id="pytest-copied-temp-bridge",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert Path(applied["backup_path"]).exists()
    assert applied["inserted_or_replaced"] == 1

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT policy_source_id, freshness_status, blocks_publication,
                   source_sha256, evidence_json
            FROM source_freshness_result
            WHERE run_id='pytest-copied-temp-bridge'
            """
        ).fetchone()

    assert row["policy_source_id"] == "src_payment_evidence_root"
    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert row["source_sha256"] == _test_sha256_file(packet_path)
    evidence = json.loads(row["evidence_json"])
    assert evidence["bridge_contract"] == "SOURCE_FRESHNESS_BRIDGE_COPIED_TEMP_V1"
    assert evidence["proof_scope"] == "copied_temp"
    assert evidence["production_authority"] is False
    assert evidence["owner_publication_authority"] is False
    errors = validate_policy_source_freshness(db_path, as_of="2026-05-17", strict=True)
    assert errors
    assert all("src_payment_evidence_root" not in error for error in errors)


def test_copied_temp_source_freshness_bridge_fails_closed_on_authority_or_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    authority_bridge, _ = _write_copied_temp_bridge_input(tmp_path, production_authority=True)
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    with pytest.raises(RuntimeError, match="production_authority must be false"):
        materialize_copied_temp_source_freshness_bridge(
            db_path=db_path,
            bridge_path=authority_bridge,
            as_of="2026-05-17",
            run_id="pytest-copied-temp-bridge-authority",
            apply=True,
            backup_dir=tmp_path / "backups",
        )

    hash_bridge, _ = _write_copied_temp_bridge_input(
        tmp_path / "hash_mismatch",
        source_packet_sha="0" * 64,
    )
    with pytest.raises(RuntimeError, match="source_packet_sha mismatch"):
        materialize_copied_temp_source_freshness_bridge(
            db_path=db_path,
            bridge_path=hash_bridge,
            as_of="2026-05-17",
            run_id="pytest-copied-temp-bridge-hash",
            apply=True,
            backup_dir=tmp_path / "backups",
        )

    with _connect(db_path) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM source_freshness_result
            WHERE run_id IN (
                'pytest-copied-temp-bridge-authority',
                'pytest-copied-temp-bridge-hash'
            )
            """
        ).fetchone()[0]
    assert count == 0


def test_operational_truth_uses_latest_eligible_order_rows_before_as_of(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_fresh_operational_truth_with_future_order_observations(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-operational-future-observation",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT freshness_status, blocks_publication, max_observed_at,
                   evidence_json
            FROM v_source_freshness_current
            WHERE policy_source_id='src_ab_db_operational_truth'
            """
        ).fetchone()

    assert row is not None
    evidence = json.loads(row["evidence_json"])
    observations = {item["table"]: item for item in evidence["table_observations"]}

    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert observations["order_status_event"]["max_observed_at"].startswith(
        "2026-05-04T10:00:00"
    )
    assert observations["fact_order_entries_kaspi"]["max_observed_at"].startswith(
        "2026-05-04T12:00:00"
    )
    assert observations["order_status_event"]["latest_future_observed_at"].startswith(
        "2026-05-05T06:00:56"
    )
    assert observations["fact_order_entries_kaspi"]["latest_future_observed_at"].startswith(
        "2026-05-05T12:54:59"
    )
    assert evidence["issue_counts"] == {}


def test_meta_source_freshness_valid_fb2_packet_clears_facebook_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    _write_meta_source_packet(source_root)
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert row["row_count"] == 2
    assert row["max_observed_at"].startswith("2026-05-04T23:59:59")
    assert evidence["observation_type"] == "meta_source_freshness_packet"
    assert evidence["packet_gate"] == "GREEN"
    assert evidence["ab_can_clear_src_facebook_ads_external_ads"] is True
    assert evidence["any_spend_found"] is False
    assert evidence["dates_requested"] == ["2026-05-03", "2026-05-04"]


def test_meta_source_freshness_missing_packet_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    (source_root / "runs" / "ab_source_freshness_20260505_acmewear_meta_live_refresh").mkdir(
        parents=True
    )
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "MISSING"
    assert row["blocks_publication"] == 1
    assert evidence["observation_type"] == "meta_source_freshness_packet"
    assert "META_SOURCE_FRESHNESS_PACKET_MISSING" in evidence["issues"]


def test_meta_source_freshness_non_green_packet_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    _write_meta_source_packet(source_root, gate="YELLOW")
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "GATE_NOT_GREEN" in evidence["issues"]


def test_meta_source_freshness_incomplete_date_coverage_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    _write_meta_source_packet(source_root, successfully_fetched=["2026-05-03"])
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "REQUESTED_DATES_NOT_ALL_SUCCESSFULLY_FETCHED" in evidence["issues"]
    assert "DATE_RESULT_NOT_SUCCESS:2026-05-04" in evidence["issues"]


def test_meta_source_freshness_platform_or_ad_writes_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    _write_meta_source_packet(
        source_root,
        platform_writes_occurred=True,
        budget_writes_occurred=True,
    )
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "PLATFORM_WRITES_OCCURRED" in evidence["issues"]
    assert "BUDGET_STATUS_CAMPAIGN_ADSET_AD_WRITES_OCCURRED" in evidence["issues"]


def test_meta_source_freshness_spend_found_requires_ingestion_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    _write_meta_source_packet(source_root, any_spend_found=True)
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "SPEND_FOUND_REQUIRES_EXTERNAL_ADS_INGESTION" in evidence["issues"]


def test_meta_source_freshness_positive_spend_clears_after_ingestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Facebook_ads"
    packet_path = _write_meta_source_packet(
        source_root,
        dates=["2026-05-04"],
        gate="YELLOW",
        any_spend_found=True,
        ab_can_clear=False,
    )
    _insert_meta_external_spend_ingestion(db_path, packet_path=packet_path, source_root=source_root)
    _point_facebook_source_to_root(db_path, source_root)

    row = _materialize_and_get_facebook_source(db_path, tmp_path, monkeypatch)
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert evidence["packet_gate"] == "YELLOW"
    assert evidence["ab_can_clear_src_facebook_ads_external_ads"] is False
    assert evidence["any_spend_found"] is True
    assert evidence["positive_spend_by_date"] == {"2026-05-04": 100.0}
    assert evidence["external_spend_ingestion"]["ingestion_complete"] is True
    assert evidence["external_spend_ingestion"]["account_ids"] == ["1517999585924947"]
    assert evidence["issues"] == []


def test_web_automation_kaspi_marketing_strict_green_packet_clears_directapi_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    _write_web_automation_kaspi_marketing_packet(source_root)
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert row["row_count"] >= 2
    assert row["max_observed_at"].startswith("2026-05-04T23:59:59")
    assert evidence["observation_type"] == "web_automation_kaspi_marketing_source_packet"
    assert evidence["packet_gate"] == "GREEN"
    assert evidence["ab_can_clear_src_web_automation_kaspi_marketing_directapi"] is True
    assert evidence["stores_covered"] == ["STOREB", "ACMEWEAR"]
    assert evidence["issues"] == []


def test_web_automation_kaspi_marketing_missing_packet_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    (source_root / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE.parent).mkdir(parents=True)
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "MISSING"
    assert row["blocks_publication"] == 1
    assert evidence["observation_type"] == "web_automation_kaspi_marketing_source_packet"
    assert "KASPI_MARKETING_SOURCE_PACKET_MISSING" in evidence["issues"]


def test_web_automation_kaspi_marketing_non_green_packet_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    _write_web_automation_kaspi_marketing_packet(source_root, gate="YELLOW")
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "GATE_NOT_GREEN" in evidence["issues"]


def test_web_automation_kaspi_marketing_missing_no_write_fields_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    _write_web_automation_kaspi_marketing_packet(
        source_root,
        omit_top_level_keys=("external_write_operations",),
    )
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "NO_WRITE_FIELD_MISSING:external_write_operations" in evidence["issues"]


def test_web_automation_kaspi_marketing_missing_store_or_date_coverage_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    _write_web_automation_kaspi_marketing_packet(
        source_root,
        missing_storeb_coverage=True,
        coverage_date="2026-05-03",
    )
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "STORE_COVERAGE_MISSING:STOREB" in evidence["issues"]
    assert "DATE_COVERAGE_BEFORE_AS_OF:2026-05-03" in evidence["issues"]


def test_web_automation_kaspi_marketing_sqlite_hash_or_path_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "Web_automation"
    _write_web_automation_kaspi_marketing_packet(
        source_root,
        sqlite_hash_mismatch=True,
        sqlite_path_missing=True,
    )
    _point_web_automation_kaspi_marketing_source_to_root(db_path, source_root)

    row = _materialize_and_get_web_automation_kaspi_marketing_source(
        db_path,
        tmp_path,
        monkeypatch,
    )
    evidence = json.loads(row["evidence_json"])

    assert row["freshness_status"] == "BLOCKED"
    assert row["blocks_publication"] == 1
    assert "SOURCE_SQLITE_HASH_MISMATCH:ACMEWEAR" in evidence["issues"]
    assert "SOURCE_SQLITE_FILE_MISSING:STOREB" in evidence["issues"]


def test_directory_source_freshness_uses_recursive_latest_artifact_for_folder_pointers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "repo_root_pointer"
    nested = source_root / "docs" / "Purchase_orders" / "Products" / "LINE31"
    nested.mkdir(parents=True)
    artifact = nested / "current_route_manifest.md"
    artifact.write_text("fresh LINE31 evidence\n", encoding="utf-8")
    _set_mtime(artifact, "2026-05-04T15:33:21+05:00")
    _set_mtime(source_root, "2026-04-18T16:09:04+05:00")

    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET source_path=?
            WHERE policy_source_id='src_ecommerce_po_artifacts'
            """,
            (str(source_root),),
        )
        conn.commit()

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-recursive-source",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT freshness_status, max_observed_at, blocks_publication, evidence_json
            FROM v_source_freshness_current
            WHERE policy_source_id='src_ecommerce_po_artifacts'
            """
        ).fetchone()

    evidence = json.loads(row["evidence_json"])
    assert row["freshness_status"] == "FRESH"
    assert row["blocks_publication"] == 0
    assert row["max_observed_at"].startswith("2026-05-04T15:33:21")
    assert evidence["observation_type"] == "recursive_latest_artifact_metadata"
    assert evidence["latest_eligible_artifact"]["relative_path"].endswith("current_route_manifest.md")
    assert evidence["root_mtime"].startswith("2026-04-18T16:09:04")


def test_historical_directory_materialization_records_future_artifacts_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    source_root = tmp_path / "route_source"
    source_root.mkdir()
    stale_artifact = source_root / "route_snapshot_old.md"
    stale_artifact.write_text("old route evidence\n", encoding="utf-8")
    future_artifact = source_root / "route_snapshot_future.md"
    future_artifact.write_text("future route evidence\n", encoding="utf-8")
    _set_mtime(stale_artifact, "2026-04-20T10:00:00+05:00")
    _set_mtime(future_artifact, "2026-05-04T09:30:00+05:00")
    _set_mtime(source_root, "2026-04-20T10:00:00+05:00")

    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET source_path=?
            WHERE policy_source_id='src_sourcing_research_supplier_routes'
            """,
            (str(source_root),),
        )
        conn.commit()

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-historical-source",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT freshness_status, max_observed_at, blocks_publication, evidence_json
            FROM v_source_freshness_current
            WHERE policy_source_id='src_sourcing_research_supplier_routes'
            """
        ).fetchone()

    evidence = json.loads(row["evidence_json"])
    assert row["freshness_status"] == "STALE"
    assert row["blocks_publication"] == 1
    assert row["max_observed_at"].startswith("2026-04-20T10:00:00")
    assert evidence["latest_eligible_artifact"]["relative_path"] == "route_snapshot_old.md"
    assert evidence["future_artifact_count"] == 1
    assert evidence["latest_future_artifact"]["relative_path"] == "route_snapshot_future.md"


def test_workbook_future_for_old_as_of_becomes_fresh_for_current_as_of(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    workbook = tmp_path / "Inbound_calendar_V10.002.xlsx"
    workbook.write_bytes(b"fixture workbook")
    _set_mtime(workbook, "2026-05-04T12:50:02+05:00")

    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE policy_source_registry
            SET source_path=?
            WHERE policy_source_id='src_inbound_workbook'
            """,
            (str(workbook),),
        )
        conn.commit()

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-workbook-old-as-of",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-workbook-current-as-of",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT as_of_date, freshness_status, blocks_publication
            FROM source_freshness_result
            WHERE policy_source_id='src_inbound_workbook'
            ORDER BY as_of_date
            """
        ).fetchall()

    assert [(row["as_of_date"], row["freshness_status"]) for row in rows] == [
        ("2026-05-03", "FUTURE"),
        ("2026-05-04", "FRESH"),
    ]
    assert rows[0]["blocks_publication"] == 1
    assert rows[1]["blocks_publication"] == 0


def test_policy_gate_materializer_writes_every_required_gate_and_blocks_missing_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)
    _seed_agent6_stock_exception(db_path)
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    materialize_source_freshness_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    backfill_exception_queue_metadata(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    report = materialize_policy_gate_results(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert Path(report["backup_path"]).exists()
    assert set(report["gate_names"]) == REQUIRED_C3_GATE_NAMES

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT gate_name, status, blocks_owner_publication, evidence_json
            FROM v_policy_gate_latest
            ORDER BY gate_name
            """
        ).fetchall()

    gate_statuses = {row["gate_name"]: row["status"] for row in rows}
    assert gate_statuses["policy_registry"] == "PASS"
    assert gate_statuses["source_freshness"] == "BLOCKED"
    assert gate_statuses["ads_source_truth"] == "BLOCKED"
    assert gate_statuses["cashflow_source_truth"] == "BLOCKED"
    assert gate_statuses["exception_queue"] == "BLOCKED"
    ads_evidence = json.loads(
        next(row["evidence_json"] for row in rows if row["gate_name"] == "ads_source_truth")
    )
    assert "ADS_TABLE_EMPTY" in ads_evidence["issue_counts"]
    assert validate_policy_gate_results(db_path)
    assert any("ads_source_truth" in err for err in validate_policy_gate_results(db_path))


def test_policy_gate_materializer_dry_run_accepts_readonly_db_without_byte_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)
    before_hash = _test_sha256_file(db_path)
    with _connect(db_path) as conn:
        before_schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]

    db_path.chmod(0o444)
    try:
        report = materialize_policy_gate_results(
            db_path=db_path,
            as_of="2026-05-03",
            run_id="pytest-dry-run-readonly",
            apply=False,
        )
        assert report["applied"] is False
    finally:
        db_path.chmod(0o644)

    assert _test_sha256_file(db_path) == before_hash
    with _connect(db_path) as conn:
        after_schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]
    assert after_schema_version == before_schema_version


def test_exception_gate_counts_accepted_controls_separately_from_unresolved_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    accepted = [
        (
            "OWNER_OOS_ACTIVE_ZERO",
            "CL_NEW_CLO_MEN_T_SHIRT_BLACK_M",
            {"sku_key": "CL_NEW-CLO_MEN_T-SHIRT_BLACK", "my_size": "M", "physical_anchor_qty": 34},
        ),
        (
            "OWNER_OVERRIDE_NO_DOUBLE_REDUCE",
            "CL_OC_MEN_LINE51_WHITE",
            {"sku_key": "CL_OC_MEN_LINE51_WHITE"},
        ),
        (
            "LINE61_4XL_EXCLUDED",
            "CL_NEW_CLO2_MEN_SUIT_61_BLACK_4XL",
            {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "my_size": "4XL", "physical_anchor_qty": 27},
        ),
        (
            "NEGATIVE_RAW_LEDGER_BALANCE",
            "CL_NEW_CLO_MEN_BERSERK_RUSH_WHITE_M",
            {"sku_key": "CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE", "sku_id": "CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE_M", "my_size": "M", "raw_current_stock": -2},
        ),
    ]
    for reason_code, suffix, evidence in accepted:
        _seed_agent6_exception(
            db_path,
            reason_code=reason_code,
            suffix=suffix,
            evidence=evidence,
        )
    _seed_agent6_exception(
        db_path,
        reason_code="NEGATIVE_RAW_LEDGER_BALANCE",
        suffix="SKU_OTHER",
        evidence={"sku_key": "SKU_OTHER", "my_size": "XL", "raw_current_stock": -1},
    )

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    backfill_exception_queue_metadata(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-exception-semantics",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    materialize_policy_gate_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-exception-semantics",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    row = _exception_gate(db_path)
    evidence = json.loads(row["evidence_json"])
    assert row["status"] == "BLOCKED"
    assert row["blocks_owner_publication"] == 1
    assert evidence["accepted_active_control_count"] == 4
    assert evidence["unresolved_blocker_count"] == 1
    assert {item["control_type"] for item in evidence["accepted_active_control_rows"]} == {
        "OWNER_OOS_ACTIVE_ZERO",
        "OWNER_OVERRIDE_NO_DOUBLE_REDUCE",
        "LINE61_4XL_EXCLUDED",
        "OWNER_BERSERK_RUSH_NEGATIVE_RAW_QUARANTINE_ACTIVE_ZERO",
    }
    assert evidence["unresolved_exception_rows"][0]["exception_id"].endswith(":SKU_OTHER")

    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE exception_queue SET status='RESOLVED' WHERE exception_id LIKE '%:SKU_OTHER'"
        )
        conn.commit()

    materialize_policy_gate_results(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-exception-controls-only",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    control_only = _exception_gate(db_path)
    control_evidence = json.loads(control_only["evidence_json"])
    assert control_only["status"] == "PASS"
    assert control_only["blocks_owner_publication"] == 0
    assert control_evidence["accepted_active_control_count"] == 4
    assert control_evidence["unresolved_blocker_count"] == 0


def test_exception_backfill_assigns_owner_action_evidence_and_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_agent6_stock_exception(db_path)
    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")

    report = backfill_exception_queue_metadata(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert Path(report["backup_path"]).exists()
    assert report["updated_exception_count"] == 1
    assert validate_exception_queue_db(db_path, strict=True) == []

    second = backfill_exception_queue_metadata(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert second["updated_exception_count"] == 0

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT owner, recommended_action, evidence_paths_json,
                   policy_version_id, policy_path, policy_source_id
            FROM exception_queue
            WHERE exception_id LIKE 'AGENT6_STOCK_REBUILD_20PCT_20260503:%'
            """
        ).fetchone()

    paths = json.loads(row["evidence_paths_json"])
    assert row["owner"] == "business_owner"
    assert "negative raw ledger balance" in row["recommended_action"].lower()
    assert row["policy_version_id"]
    assert row["policy_path"] == "stock_authority.negative_active_stock_action"
    assert row["policy_source_id"] == "src_ab_db_operational_truth"
    assert any("agent_2_c3_stock_orders_returns_qc_closeout.md" in path for path in paths)
    assert any("BASELINE_20PCT_DECREASE_20260404_B6864B5C3108_lineage.json" in path for path in paths)


def test_apply_requires_env_gate_and_daily_brief_keeps_exact_c3_blockers_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _promoted_db(tmp_path, monkeypatch)
    _seed_stale_operational_truth(db_path)
    _point_sources_to_fixtures(db_path, tmp_path)
    _seed_agent6_stock_exception(db_path)

    with pytest.raises(RuntimeError, match=C3_MATERIALIZATION_ENV_GATE):
        materialize_c3_policy_state(
            db_path=db_path,
            as_of="2026-05-03",
            run_id="pytest-agent8",
            apply=True,
            backup_dir=tmp_path / "backups",
        )

    monkeypatch.setenv(C3_MATERIALIZATION_ENV_GATE, "1")
    report = materialize_c3_policy_state(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-agent8",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    assert Path(report["backup_path"]).exists()

    daily = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="pytest-agent8-brief",
        allow_green_owner_output=True,
        require_c3_policy=True,
    )
    assert daily.status == "RED"
    assert daily.owner_trust_status == "RED_BLOCKED"
    brief = Path(daily.owner_brief_path).read_text(encoding="utf-8")
    assert "src_bank_manual_ingest" in brief
    assert "ads_source_truth" in brief
    assert "exception_queue" in brief
    assert "`c3_exception_queue`: `PASS`" not in brief
    assert any(
        gate["gate_name"] == "c3_exception_queue" and gate["status"] == "BLOCKED"
        for gate in daily.release_gates
    )
    assert "GREEN_DECISION_GRADE" not in brief
