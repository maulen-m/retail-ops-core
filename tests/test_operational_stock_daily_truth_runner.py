from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.ops.operational_stock_daily_truth_runner import run_operational_stock_daily_truth
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate


def _seed_minimal_green_sources(db_path: Path, *, as_of: str = "2026-05-03") -> None:
    migrate(db_path)
    with sqlite3.connect(str(db_path)) as conn:
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
                entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt,
                total_price_kzt, updated_at
            ) VALUES ('E1', 'O1', 'ACMEWEAR', 'OFFER_A', 1, 10000, 10000,
                      ? || 'T10:00:00+05:00')
            """,
            (as_of,),
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


def test_runner_fail_closed_fixture_writes_red_outputs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    migrate(db_path)
    output_root = tmp_path / "daily_truth"

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=output_root,
        run_id="fixture-red",
        allow_green_owner_output=False,
    )

    assert report.status == "RED"
    assert report.owner_trust_status == "RED_BLOCKED"
    assert report.owner_brief_path is not None
    brief = Path(report.owner_brief_path).read_text(encoding="utf-8")
    assert "Trust banner: RED_BLOCKED" in brief
    assert "GREEN_DECISION_GRADE" not in brief
    assert any(result["severity"] == "ERROR" for result in report.validation_results)


def test_source_freshness_fixture_blocks_stale_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_green_sources(db_path, as_of="2026-04-30")

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="fixture-stale",
        allow_green_owner_output=True,
        max_source_lag_days=1,
    )

    assert report.status == "RED"
    assert any(result["gate_name"] == "source_freshness" for result in report.validation_results)
    assert any(exc["reason"].startswith("SOURCE_STALE") for exc in report.exceptions)


def test_source_freshness_uses_as_of_slice_when_later_snapshot_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_green_sources(db_path, as_of="2026-05-03")
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES ('2026-05-04', 'SKU_A_M', 'SKU_A', 'M', 4, 0)
            """
        )
        conn.commit()

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="fixture-as-of-slice",
        allow_green_owner_output=True,
    )

    assert not any(exc["reason"] == "SOURCE_FUTURE_DATED" for exc in report.exceptions)
    source_freshness = next(
        result for result in report.validation_results if result["gate_name"] == "source_freshness"
    )
    assert source_freshness["status"] == "PASS"
    inventory_manifest = next(
        item for item in report.source_manifests if item["table"] == "fact_inventory_snapshot_size"
    )
    assert inventory_manifest["max_observed_date"] == "2026-05-03"
    assert inventory_manifest["latest_table_date"] == "2026-05-04"
    assert inventory_manifest["future_row_count"] == 1


def test_report_lineage_fixture_contains_manifests_hashes_and_validation(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_green_sources(db_path)

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="fixture-lineage",
        allow_green_owner_output=False,
    )

    lineage_path = Path(report.lineage_json_path)
    payload = json.loads(lineage_path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "fixture-lineage"
    assert payload["as_of_date"] == "2026-05-03"
    assert payload["source_manifests"]
    assert all(item["source_sha256"] for item in payload["source_manifests"])
    assert payload["validation_results"]
    assert payload["release_gates"]
    assert payload["owner_outputs"]["owner_brief_md"] == report.owner_brief_path


def test_red_owner_brief_fixture_preserves_agent7_blockers(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_green_sources(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            DELETE FROM order_status_event
            WHERE order_id = 'O1' AND stage_code = 'COMPLETED'
            """
        )
        conn.commit()

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="fixture-owner-brief",
        allow_green_owner_output=True,
    )

    brief = Path(report.owner_brief_path).read_text(encoding="utf-8")

    assert report.owner_trust_status == "RED_BLOCKED"
    assert "ORDER_LIFECYCLE_MISSING_COMPLETED" in brief
    assert "Owner publication is blocked" in brief
    assert "No green release has been published" in brief


def test_exception_reason_counts_cover_full_set_when_samples_are_capped(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_minimal_green_sources(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("DELETE FROM order_status_event WHERE order_id = 'O1'")
        conn.execute("DELETE FROM fact_order_entries_kaspi WHERE order_id = 'O1'")
        conn.commit()

    report = run_operational_stock_daily_truth(
        db_path=db_path,
        as_of="2026-05-03",
        output_root=tmp_path / "daily_truth",
        run_id="fixture-capped-exceptions",
        allow_green_owner_output=True,
        max_exception_items=1,
    )
    payload = json.loads(Path(report.exception_report_json_path).read_text(encoding="utf-8"))

    assert len(payload["exceptions"]) == 1
    assert payload["exception_count_total"] > len(payload["exceptions"])
    assert sum(payload["exception_counts_by_reason"].values()) == payload["exception_count_total"]
    assert payload["exception_counts_by_reason"]["ORDER_ENTRY_MISSING"] == 1
    assert payload["exception_counts_by_reason"]["ORDER_LIFECYCLE_MISSING_COMPLETED"] == 1
