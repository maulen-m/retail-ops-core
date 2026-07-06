import json
from pathlib import Path


REGISTRY_DIR = (
    Path(__file__).resolve().parents[1] / "config" / "owner_decisions"
)


def _load(name: str) -> dict:
    path = REGISTRY_DIR / name
    assert path.exists(), f"Missing owner decision registry: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_common(registry: dict) -> None:
    assert registry["decision_id"].startswith("OD-")
    assert registry["decided_at"].startswith("2026-07-06T00:")
    assert "owner_answer_verbatim" in registry
    assert "source_context" in registry
    assert registry["source_context"]["source_file"].endswith(
        "OWNER_APPROVALS_20260702_RESUME.md"
    )


def test_price_floor_doctrine_retires_30_35_and_keeps_5pct_poc_redline() -> None:
    registry = _load("price_floor_doctrine_5pct_poc_2026_07_06.json")
    _assert_common(registry)

    policy = registry["floor_policy"]
    assert policy["retired_floor_poc_percentages"] == [30, 35]
    assert policy["active_sell_off_red_line_poc_percentage"] == 5
    assert policy["profit_basis"] == "profit_on_cogs"

    delegations = {item["delegation_id"]: item for item in registry["delegations"]}
    assert delegations["ONE_WAY_UP_AUTO_APPLY_5PCT_POC"]["status"] == "approved"
    assert delegations["ONE_WAY_UP_AUTO_APPLY_5PCT_POC"]["direction"] == (
        "one_way_up_only"
    )


def test_shr_supplier_payment_delay_registers_due_date_and_po_freeze() -> None:
    registry = _load("shr_supplier_payment_delay_2026_07_06.json")
    _assert_common(registry)

    payable = registry["supplier_payable"]
    assert payable["amount_kzt"] == 3_175_272
    assert payable["amount_cny"] == 44_101
    assert payable["purchase_orders"] == ["5.2", "6.0a", "6.0b"]
    assert payable["due_date"] == "2026-09-04"

    commitment = registry["cashflow_commitment_pointer"]
    assert commitment["commit_type"] == "PO_PAYMENT"
    assert commitment["ref_id"] == "SHR_PAYMENT_DELAY_20260706"

    constraints = {item["constraint_id"] for item in registry["constraints"]}
    assert "NO_NEW_MEN_PRODUCT_POS_UNTIL_REPAID" in constraints


def test_suit_beli_and_ls_disposition_remain_exact() -> None:
    registry = _load("line61_price_hold_ls_bundle_removal_2026_07_06.json")
    _assert_common(registry)

    decisions = {item["product_key"]: item for item in registry["pricing_decisions"]}
    assert decisions["SUIT-61"]["price_kzt"] == 19_990
    assert decisions["SUIT-61"]["elasticity_test"] == "not_authorized"
    assert decisions["LINE51"]["kaspi_card_id"] == "165486887"
    assert decisions["LINE51"]["price_kzt"] == 17_000

    disposition = {item["offer_group"]: item for item in registry["offer_group_disposition"]}
    assert disposition["LS31 BLK"]["remove_from_store"] == "ACMEWEAR"
    assert disposition["LS31 BLK"]["belongs_on_store"] == "UNIVERSAL"
    assert disposition["LS21 BLK"]["remove_from_store"] == "ACMEWEAR"
    assert disposition["LS21 BLK"]["belongs_on_store"] == "UNIVERSAL"


def test_marketing_delegation_uses_net_profit_after_ads_and_budget_cap() -> None:
    registry = _load("marketing_control_delegation_2026_07_06.json")
    _assert_common(registry)

    delegation = registry["delegation"]
    assert delegation["status"] == "approved"
    assert delegation["profitability_metric"] == "net_profit_after_ads"
    assert delegation["profitability_metric_is_exclusive"] is True

    budget = registry["ads_test_budget"]
    assert budget["daily_increment_kzt"] == 10_000
    assert budget["duration_days"] == 14
    assert budget["total_cap_kzt"] == 140_000

    line61 = registry["line61_budget_correction_delegation"]
    assert line61["status"] == "approved_under_unprofitability_evidence"
