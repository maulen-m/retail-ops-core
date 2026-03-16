from __future__ import annotations

from pathlib import Path


def test_webui_crm_chronology_authority_contract_states_workbook_anchor() -> None:
    contract = Path("docs/validation/WEBUI_CRM_CHRONOLOGY_AUTHORITY_CONTRACT.md")
    text = contract.read_text(encoding="utf-8")

    assert "WebUI remains historical status truth" in text
    assert "CRM/workbook remains the chronology authority" in text
    assert "Do not bypass DB-backed validation/publication" in text
