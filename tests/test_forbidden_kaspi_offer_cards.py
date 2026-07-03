import json
from pathlib import Path


REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "owner_decisions"
    / "forbidden_kaspi_offer_cards_nike_longsleeve_2026_07_03.json"
)

EXPECTED_DECISION_ID = "OD-FORBID-KASPI-OFFER-CARD-NIKE-LONGSLEEVE-2026-07-03"
EXPECTED_SLUG = "sportivnyi-kostjum-18107200-643074"
EXPECTED_FAMILY = "18107200-643074"
EXPECTED_CODES = {
    "110261375",
    "120980444",
    "120980449",
    "132848895",
    "152381039",
    "157715221",
}

OWNER_DECISION_MESSAGE = (
    "Owner decision OD-FORBID-KASPI-OFFER-CARD-NIKE-LONGSLEEVE-2026-07-03 "
    "forbids the Kaspi Nike long-sleeve card family from any sellable surface; "
    "refactoring must not remove or weaken it."
)


def _load_registry() -> dict:
    assert REGISTRY_PATH.exists(), (
        f"{OWNER_DECISION_MESSAGE} Missing registry file: {REGISTRY_PATH}"
    )
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_keeps_owner_forbidden_decision_enabled() -> None:
    registry = _load_registry()

    assert registry.get("decision_id") == EXPECTED_DECISION_ID, OWNER_DECISION_MESSAGE
    assert registry.get("forbidden_to_enable") is True, (
        f"{OWNER_DECISION_MESSAGE} forbidden_to_enable must remain true."
    )
    assert registry.get("kaspi_card_slug") == EXPECTED_SLUG, (
        f"{OWNER_DECISION_MESSAGE} The forbidden Kaspi card slug must stay registered."
    )
    assert registry.get("kaspi_family") == EXPECTED_FAMILY, (
        f"{OWNER_DECISION_MESSAGE} The forbidden Kaspi family must stay registered."
    )


def test_all_forbidden_product_codes_remain_registered() -> None:
    registry = _load_registry()

    registered_codes = {str(code) for code in registry.get("forbidden_product_codes", [])}
    missing_codes = EXPECTED_CODES - registered_codes

    assert not missing_codes, (
        f"{OWNER_DECISION_MESSAGE} Missing forbidden product codes: "
        f"{sorted(missing_codes)}."
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


def test_historical_attribution_exception_cannot_be_used_for_sellability() -> None:
    registry = _load_registry()
    attribution_note = registry.get("attribution_note") or {}
    reactivation_policy = registry.get("reactivation_policy") or {}

    assert attribution_note.get("map_ids") == [3542, 3543, 3544, 3545], (
        f"{OWNER_DECISION_MESSAGE} Historical dim_kaspi_article_map ids must stay "
        "documented for attribution-only handling."
    )
    assert "historical" in attribution_note.get("active_flag_policy", ""), (
        f"{OWNER_DECISION_MESSAGE} active_flag=1 must remain attribution-only."
    )
    assert "must never" in attribution_note.get("sellability_policy", ""), (
        f"{OWNER_DECISION_MESSAGE} Historical mappings must not become sellable."
    )
    assert reactivation_policy.get("status") == (
        "forbidden_until_new_explicit_owner_decision"
    ), (
        f"{OWNER_DECISION_MESSAGE} Reactivation must require a new explicit owner "
        "decision file."
    )
