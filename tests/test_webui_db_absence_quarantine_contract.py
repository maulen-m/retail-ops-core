from __future__ import annotations

from pathlib import Path


def test_webui_db_absence_quarantine_contract_states_allowed_residuals() -> None:
    contract = Path("docs/validation/WEBUI_DB_ABSENCE_QUARANTINE_CONTRACT.md")
    text = contract.read_text(encoding="utf-8")

    assert "DB_QUARANTINE_NO_FACT_ORDER_ENTRIES" in text
    assert "DB_ONLY_NO_WEBUI_LINEAGE" in text
    assert "documented quarantine" in text
    assert "DATE_MISMATCH" in text
    assert "CRM_REMAINS_CHRONOLOGY_AUTHORITY" in text
