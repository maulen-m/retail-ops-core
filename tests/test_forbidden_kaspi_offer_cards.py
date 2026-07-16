import json
from pathlib import Path


REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "owner_decisions"
    / "forbidden_kaspi_offer_cards_nike_longsleeve_2026_07_03.json"
)
BERSERK_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "owner_decisions"
    / "forbidden_kaspi_offer_cards_berserk_2026_07_17.json"
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
BERSERK_EXPECTED_DECISION_ID = "OD-FORBID-KASPI-OFFER-CARD-BERSERK-2026-07-17"
BERSERK_EXPECTED_PREFIXES = {
    "CL_NEW-CLO_MEN_BERSERK-RUSH_",
    "CL_NEW-CLO_MEN_BERSERK-SHIRT_",
}
BERSERK_OWNER_LISTED_CODES = {
    "146683357",
    "147772845",
    "145700550",
    "137440176",
    "150318626",
}
BERSERK_EXPECTED_CODES = {
    "17490091",
    "18209877",
    "30132395",
    "30321330",
    "30341507",
    "052039068",
    "120765596",
    "120765717",
    "120765723",
    "120765725",
    "120765729",
    "120770066",
    "121207859",
    "121207970",
    "121208018",
    "121208087",
    "121208216",
    "121208442",
    "121460063",
    "121460065",
    "121460073",
    "121625146",
    "121625147",
    "121625347",
    "121934234",
    "121934256",
    "121934275",
    "122188558",
    "122659793",
    "122661759",
    "122661796",
    "128750634",
    "129966843",
    "132571892",
    "132571923",
    "135106879",
    "135502266",
    "135502267",
    "135502268",
    "137440176",
    "138284689",
    "140937883",
    "142101032",
    "142102722",
    "144019144",
    "145325867",
    "145700542",
    "145700543",
    "145700546",
    "145700547",
    "145700548",
    "145700549",
    "145700550",
    "146683357",
    "146716915",
    "146716916",
    "146716917",
    "147648414",
    "147768547",
    "147772841",
    "147772845",
    "150318455",
    "150318457",
    "150318620",
    "150318626",
    "150318645",
    "150318674",
    "150318694",
    "231117565",
    "268608760",
    "598963275",
    "625888484",
    "635798142",
    "697939657",
    "863780079",
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


def _load_berserk_registry() -> dict:
    assert BERSERK_REGISTRY_PATH.exists(), (
        "Owner decision OD-FORBID-KASPI-OFFER-CARD-BERSERK-2026-07-17 is missing: "
        f"{BERSERK_REGISTRY_PATH}"
    )
    return json.loads(BERSERK_REGISTRY_PATH.read_text(encoding="utf-8"))


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


def test_berserk_registry_keeps_owner_never_enable_decision_enabled() -> None:
    registry = _load_berserk_registry()
    scope = registry.get("scope") or {}

    assert registry.get("decision_id") == BERSERK_EXPECTED_DECISION_ID
    assert registry.get("forbidden_to_enable") is True
    assert registry.get("decided_at", "").startswith("2026-07-17")
    assert set(registry.get("family_prefixes") or []) == BERSERK_EXPECTED_PREFIXES
    assert scope.get("type") == "all_stores"
    assert scope.get("future_stores") is True


def test_berserk_full_enumerated_code_set_and_owner_listed_codes_remain_registered() -> None:
    registry = _load_berserk_registry()
    registered_codes = {str(code) for code in registry.get("forbidden_product_codes", [])}

    assert registered_codes == BERSERK_EXPECTED_CODES
    assert BERSERK_OWNER_LISTED_CODES <= registered_codes
    assert registry.get("enumeration_source", {}).get("product_code_count") == len(BERSERK_EXPECTED_CODES)


def test_berserk_codes_do_not_overlap_nike_longsleeve_registry() -> None:
    nike_codes = {str(code) for code in _load_registry().get("forbidden_product_codes", [])}
    berserk_codes = {str(code) for code in _load_berserk_registry().get("forbidden_product_codes", [])}

    assert nike_codes == EXPECTED_CODES
    assert berserk_codes.isdisjoint(nike_codes)
