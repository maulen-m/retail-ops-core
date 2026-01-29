from pathlib import Path

from scripts import validate_po_contract


def test_po_contract_runner_passes_fixture():
    project_root = Path(__file__).parent.parent
    contract_path = project_root / "docs" / "validation" / "PO_CONTRACT.md"
    cases_path = project_root / "tests" / "fixtures" / "po_golden" / "po_contract_cases.json"
    expected_path = project_root / "tests" / "fixtures" / "po_golden" / "po_contract_expected.json"

    result = validate_po_contract.run_contract(
        contract_path=contract_path,
        cases_path=cases_path,
        expected_path=expected_path,
    )

    assert result["ok"] is True
    assert result["failures"] == []
