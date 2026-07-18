from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from core.sales.publication_binding import install_publication_binding_schema
from core.sales.truth_view_contract import (
    TruthViewContractError,
    build_truth_view_contract,
    canonical_sha256,
    require_apply_contract_match,
    require_manifest_build_compatible,
    require_post_refresh_stored_sql,
)
from core.sales.truth_views import ensure_sales_truth_views


def _seed(path: Path, *, refreshed: bool) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL DEFAULT '',
                store_code TEXT,
                quantity REAL NOT NULL,
                sell_price_kzt REAL,
                delivery_fee REAL,
                cogs REAL,
                net_rev REAL,
                profit REAL,
                status TEXT,
                return_flag INTEGER,
                source_file TEXT,
                source_entry_id TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT
            );
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                quantity REAL NOT NULL,
                net_rev_kzt REAL NOT NULL,
                total_price_kzt REAL NOT NULL,
                source_file TEXT,
                updated_at TEXT,
                PRIMARY KEY(order_id, store_code)
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                base_cost_cny REAL,
                weight_kg REAL,
                cogs_kzt REAL
            );
            INSERT INTO dim_sku VALUES ('SKU_O1', NULL, NULL, 1000);
            INSERT INTO sales_fact_v2 VALUES (
                1, 'O1', '2026-01-13', 'SKU_O1', 'SKU_O1_2XL', '2XL',
                '', 'ACMEWEAR', 1, 8982, 637.5, NULL, 6932.88, NULL,
                'DELIVERED', 0, 'source.xlsx', 'ENTRY1', 'ARTICLE1',
                'ENTRY:ENTRY1'
            );
            INSERT INTO fact_sales_workbook_anchor VALUES (
                'O1', 'ACMEWEAR', '2026-01-13', 1, 6932.88, 8982,
                'anchor.xlsx', '2026-03-07 20:42:46'
            );
            """
        )
        if refreshed:
            install_publication_binding_schema(conn)
        ensure_sales_truth_views(conn)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def contract_pair(tmp_path: Path) -> tuple[Path, Path, dict, dict, Path]:
    legacy = tmp_path / "legacy.db"
    refreshed = tmp_path / "refreshed.db"
    probe = tmp_path / "probe"
    _seed(legacy, refreshed=False)
    _seed(refreshed, refreshed=True)
    legacy_contract = build_truth_view_contract(legacy, probe_dir=probe)
    refreshed_contract = build_truth_view_contract(refreshed, probe_dir=probe)
    return legacy, refreshed, legacy_contract, refreshed_contract, probe


def test_legacy_stored_views_fail_before_manifest_build(contract_pair) -> None:
    _legacy, _refreshed, legacy_contract, _current, probe = contract_pair
    assert legacy_contract["compatible"] is False
    assert legacy_contract["manifest_regeneration_required"] is True
    with pytest.raises(TruthViewContractError, match="refresh copied baseline"):
        require_manifest_build_compatible(legacy_contract)
    assert list(probe.iterdir()) == []


def test_refreshed_copy_exactly_matches_runtime_definition(contract_pair) -> None:
    _legacy, _refreshed, _old, current, _probe = contract_pair
    require_manifest_build_compatible(current)
    assert current["compatible"] is True
    assert current["mismatched_views"] == []
    assert current["stored_view_set_sha256"] == current[
        "runtime_expected_view_set_sha256"
    ]


def test_apply_rejects_legacy_db_under_refreshed_pin(contract_pair) -> None:
    legacy, _refreshed, _old, current, probe = contract_pair
    with pytest.raises(TruthViewContractError, match="refresh copied baseline"):
        require_apply_contract_match(
            legacy,
            pinned_contract=current,
            probe_dir=probe,
        )


def test_apply_accepts_identical_refreshed_db_and_pin(contract_pair) -> None:
    _legacy, refreshed, _old, current, probe = contract_pair
    observed = require_apply_contract_match(
        refreshed,
        pinned_contract=current,
        probe_dir=probe,
    )
    assert observed["contract_sha256"] == current["contract_sha256"]


def test_runtime_code_pin_tamper_forces_regeneration(contract_pair) -> None:
    _legacy, refreshed, _old, current, probe = contract_pair
    tampered = copy.deepcopy(current)
    tampered["runtime_code"]["truth_views_module_sha256"] = "0" * 64
    body = dict(tampered)
    body.pop("contract_sha256")
    tampered["contract_sha256"] = canonical_sha256(body)
    with pytest.raises(TruthViewContractError, match="differs from reviewed"):
        require_apply_contract_match(
            refreshed,
            pinned_contract=tampered,
            probe_dir=probe,
        )


def test_post_refresh_guard_accepts_pin_and_rejects_legacy(contract_pair) -> None:
    legacy, refreshed, _old, current, _probe = contract_pair
    current_conn = sqlite3.connect(f"file:{refreshed.resolve()}?mode=ro", uri=True)
    legacy_conn = sqlite3.connect(f"file:{legacy.resolve()}?mode=ro", uri=True)
    try:
        require_post_refresh_stored_sql(
            current_conn,
            pinned_contract=current,
        )
        with pytest.raises(TruthViewContractError, match="post-refresh stored"):
            require_post_refresh_stored_sql(
                legacy_conn,
                pinned_contract=current,
            )
    finally:
        current_conn.close()
        legacy_conn.close()
