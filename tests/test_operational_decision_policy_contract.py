from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "operational_decision_policy.yaml"
DOC_PATH = ROOT / "docs" / "ops" / "OPERATIONAL_DECISION_POLICY_V1.md"
AUTHORITY_INDEX_PATH = ROOT / "docs" / "authority" / "INDEX.md"
OWNER_QA_DIR = ROOT / "docs" / "parallel_runs" / "2026-05-03_operational-stock-truth-system"


def _load_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_operational_decision_policy_is_fail_closed_and_current_scope() -> None:
    policy = _load_policy()

    assert policy["version"] == 1
    assert policy["status"] == "active"
    assert policy["fail_closed_default"] is True

    scope = policy["store_scope"]
    assert set(scope["all_kaspi_stores"]) == {"ACMEWEAR", "UNIVERSAL", "STOREB", "11KZ", "MELVIS"}
    assert set(scope["active_positive_stock_stores"]) == {"ACMEWEAR", "UNIVERSAL", "STOREB"}
    assert set(scope["inactive_stores"]) == {"11KZ", "MELVIS"}

    ads = policy["ads_truth"]
    assert set(ads["active_kaspi_internal_ads_stores"]) == {"ACMEWEAR", "STOREB"}
    assert ads["storeb_marketing_access_via"] == "UNIVERSAL"
    assert ads["missing_required_ads_blocks_profit_publication"] is True

    stock = policy["stock_status_rules"]
    assert stock["pending_reduces_stock"] is False
    assert stock["dispatched_or_shipped_reduces_stock"] is True
    assert stock["delivered_remains_sold"] is True
    assert stock["returned_increases_active_stock_after"] == "qc_acceptance"


def test_decision_thresholds_protect_capital_and_profit_publication() -> None:
    policy = _load_policy()
    freshness = policy["decision_thresholds"]["freshness"]

    assert freshness["kaspi_orders"]["max_age_hours"] <= 24
    assert freshness["kaspi_order_status_events"]["max_age_hours"] <= 24
    assert freshness["kaspi_internal_ads_required_stores"]["max_age_hours"] <= 24
    assert freshness["bank_balances"]["max_age_days"] <= 7

    reconciliation = policy["decision_thresholds"]["reconciliation"]
    assert reconciliation["stock_units_tolerance"] == 0
    assert reconciliation["po_received_units_tolerance"] == 0
    assert reconciliation["profit_publish_kzt_tolerance"] <= 100

    sku_mapping = policy["decision_thresholds"]["sku_mapping"]
    assert sku_mapping["min_confidence_for_auto_include"] == 1.0
    assert sku_mapping["max_sales_to_ignore_unmapped_sku"] == 2
    assert sku_mapping["unmapped_sku_action_above_ignore_cap"] == "quarantine_and_block_publication"

    publication = policy["publication_gates"]
    assert publication["unknown_cogs_blocks_profit_publication"] is True
    assert publication["missing_required_ads_blocks_profit_publication"] is True
    assert publication["negative_active_stock_action"] == "normalize_to_zero_and_raise_exception"

    cash = policy["cashflow_truth"]
    assert cash["owner_cash_reserve_min_kzt"] == 1_500_000
    assert cash["bank_balance_manual_review_max_age_days"] <= 7


def test_manual_review_ownership_has_clear_auto_repair_boundaries() -> None:
    ownership = _load_policy()["manual_review_ownership"]

    assert ownership["daily_exception_queue"]["owner"] == "business_owner"
    assert ownership["daily_exception_queue"]["max_resolution_age_business_days"] == 1
    assert ownership["warehouse_qc_returns"]["owner"] == "warehouse_employee"
    assert ownership["sku_merge_or_override"]["owner"] == "business_owner"
    assert ownership["supplier_cargo_cash_obligations"]["owner"] == "business_owner"
    assert ownership["agent_auto_repair"]["allowed"] is True
    assert ownership["agent_auto_repair"]["may_override_publication_gates"] is False
    assert ownership["agent_auto_repair"]["requires_deterministic_source"] is True


def test_policy_doc_and_owner_qa_capture_are_authoritative_without_secrets() -> None:
    policy_doc = DOC_PATH.read_text(encoding="utf-8")
    authority_index = AUTHORITY_INDEX_PATH.read_text(encoding="utf-8")
    qa_docs = sorted(OWNER_QA_DIR.glob("OWNER_QA_OPTION_C_INPUTS_*.md"))

    assert "docs/ops/OPERATIONAL_DECISION_POLICY_V1.md" in authority_index
    assert "config/operational_decision_policy.yaml" in policy_doc
    assert "Do not copy secrets into this document" in policy_doc
    assert qa_docs, "Expected a timestamped owner QA capture for Option C inputs"

    latest_qa = qa_docs[-1].read_text(encoding="utf-8")
    assert "20% proportional LINE51 stock reduction" in latest_qa
    assert "normalize to zero" in latest_qa
    assert "Inbound_calendar_V10.002.xlsx" in latest_qa
    assert "bank_accounts_manual_ingest_3.5.2026.yaml" in latest_qa
    assert "1,500,000 KZT" in latest_qa
    assert "secrets are referenced by environment variable name only" in latest_qa
    assert "Password_UNIVERSAL=" not in latest_qa
    assert "Kaspi_marketing_Password_UNIVERSAL=" not in latest_qa
