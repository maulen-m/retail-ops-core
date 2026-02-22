from __future__ import annotations

from pathlib import Path


def test_po_money_gate_contract_doc_exists_and_lists_required_checks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contract_path = repo_root / "docs" / "po" / "PO_MONEY_GATE_CONTRACT.md"
    assert contract_path.exists(), f"missing contract doc: {contract_path}"
    text = contract_path.read_text(encoding="utf-8")
    required_snippets = [
        "## Required checks",
        "check_anchor_health.py",
        "validate_inbound_sheet_consistency.py",
        "validate_single_truth_system.py",
        "validate_cogs_integrity.py",
        "validate_single_truth_alignment.py",
        "validate_po_money_gate.py",
    ]
    for snippet in required_snippets:
        assert snippet in text, f"missing contract snippet: {snippet}"


def test_po_money_gate_contract_doc_uses_placeholder_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contract_path = repo_root / "docs" / "po" / "PO_MONEY_GATE_CONTRACT.md"
    text = contract_path.read_text(encoding="utf-8")
    assert "/Users/" not in text
