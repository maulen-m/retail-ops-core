import json
from pathlib import Path


REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "owner_decisions"
    / "offer_creation_rules_2026_07_03.json"
)

EXPECTED_DECISION_ID = "OD-OFFER-CREATION-RULES-P7-2026-07-03"
EXPECTED_RULE_IDS = {
    "R1_STOCK_LE_15_NO_CREATE",
    "R2_ACMEWEAR_BRAND_MANDATORY",
}
EXPECTED_CASE = "RUSH_WHITE_M_149066056"

OWNER_DECISION_MESSAGE = (
    "Owner decision OD-OFFER-CREATION-RULES-P7-2026-07-03 encodes standing "
    "offer-creation rules; refactoring must not remove or weaken it."
)


def _load_registry() -> dict:
    assert REGISTRY_PATH.exists(), (
        f"{OWNER_DECISION_MESSAGE} Missing registry file: {REGISTRY_PATH}"
    )
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _rules_by_id(registry: dict) -> dict:
    return {rule.get("rule_id"): rule for rule in registry.get("rules", [])}


def test_registry_json_parses_and_keeps_owner_decision_id() -> None:
    registry = _load_registry()

    assert registry.get("decision_id") == EXPECTED_DECISION_ID, (
        f"{OWNER_DECISION_MESSAGE} The owner decision id must stay registered."
    )
    assert registry.get("decided_at") == "2026-07-03T15:05:00+05:00", (
        f"{OWNER_DECISION_MESSAGE} The owner decision timestamp must not drift."
    )


def test_required_offer_creation_rules_remain_registered() -> None:
    registry = _load_registry()
    rules_by_id = _rules_by_id(registry)
    missing_rule_ids = EXPECTED_RULE_IDS - set(rules_by_id)

    assert not missing_rule_ids, (
        f"{OWNER_DECISION_MESSAGE} Missing owner rule ids: "
        f"{sorted(missing_rule_ids)}."
    )
    assert rules_by_id["R1_STOCK_LE_15_NO_CREATE"].get("threshold") == 15, (
        f"{OWNER_DECISION_MESSAGE} Stock no-create threshold must remain exactly 15."
    )
    assert rules_by_id["R1_STOCK_LE_15_NO_CREATE"].get("mandatory") is True, (
        f"{OWNER_DECISION_MESSAGE} Stock no-create rule must remain mandatory."
    )
    assert rules_by_id["R2_ACMEWEAR_BRAND_MANDATORY"].get("mandatory") is True, (
        f"{OWNER_DECISION_MESSAGE} ACMEWEAR brand rule must remain mandatory."
    )
    assert rules_by_id["R2_ACMEWEAR_BRAND_MANDATORY"].get("brand") == "ACMEWEAR", (
        f"{OWNER_DECISION_MESSAGE} Own-created/uploaded offers must keep brand ACMEWEAR."
    )


def test_scope_covers_universal_storeb_and_future_stores() -> None:
    registry = _load_registry()
    scope = registry.get("scope") or {}
    named_stores = set(scope.get("named_stores") or [])

    assert scope.get("type") == "all_stores", (
        f"{OWNER_DECISION_MESSAGE} Scope must remain all stores."
    )
    assert "UNIVERSAL" in named_stores, (
        f"{OWNER_DECISION_MESSAGE} Scope must explicitly cover UNIVERSAL."
    )
    assert "STORE-B" in named_stores, (
        f"{OWNER_DECISION_MESSAGE} Scope must explicitly cover STORE-B."
    )
    assert scope.get("future_stores") is True, (
        f"{OWNER_DECISION_MESSAGE} Scope must cover future stores too."
    )


def test_rush_white_m_is_closed_as_no_create() -> None:
    registry = _load_registry()
    applied_by_case = {
        decision.get("case"): decision
        for decision in registry.get("applied_decisions", [])
    }

    assert EXPECTED_CASE in applied_by_case, (
        f"{OWNER_DECISION_MESSAGE} Applied RUSH_WHITE M no-create case must stay "
        "registered."
    )

    rush_white_m = applied_by_case[EXPECTED_CASE]
    assert rush_white_m.get("public_variant_code") == "149066056", (
        f"{OWNER_DECISION_MESSAGE} RUSH_WHITE M public variant code must remain exact."
    )
    assert rush_white_m.get("stock_balance_at_decision") == 14, (
        f"{OWNER_DECISION_MESSAGE} RUSH_WHITE M stock proof must remain 14."
    )
    assert rush_white_m.get("outcome") == "NO_CREATE", (
        f"{OWNER_DECISION_MESSAGE} RUSH_WHITE M must remain NO_CREATE."
    )
    assert rush_white_m.get("measured_from") == "stock_ledger sum 2026-07-03", (
        f"{OWNER_DECISION_MESSAGE} RUSH_WHITE M stock source must remain documented."
    )
