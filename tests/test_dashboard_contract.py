"""Contract tests for dashboard output (Phase 3)."""

from core.validation.dashboard_contract import (
    DEFAULT_FIXTURE,
    DEFAULT_PO_CONTRACT,
    load_cases,
    build_drafts,
    generate_dashboard_output,
    parse_po_contract_tolerances,
    validate_dashboard_output,
    hash_output,
)


def test_dashboard_contract_fixture():
    cases = load_cases(DEFAULT_FIXTURE)
    drafts = build_drafts(cases)
    output = generate_dashboard_output(cases)
    tolerances = parse_po_contract_tolerances(DEFAULT_PO_CONTRACT)

    errors = validate_dashboard_output(output, drafts, tolerances)
    assert not errors, "\n".join(errors)


def test_dashboard_contract_deterministic_hash():
    cases = load_cases(DEFAULT_FIXTURE)
    output_a = generate_dashboard_output(cases)
    output_b = generate_dashboard_output(cases)

    assert hash_output(output_a) == hash_output(output_b)
