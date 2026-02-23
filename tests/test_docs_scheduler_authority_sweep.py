from pathlib import Path


AUTHORITY_DOC = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md")
INCIDENT_DOC = Path("docs/KASPI_IMPORT_SCHEDULER_INCIDENT_SUMMARY_2026-02-17.md")

ACTIVE_DOCS = [
    Path("docs/DAILY_SOP.md"),
    Path("docs/DAILY_WORKFLOW.md"),
    Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md"),
    Path("docs/WRITE_APPLY_RUNBOOK.md"),
]


def test_active_docs_do_not_reference_deprecated_1605_import_schedule() -> None:
    for path in ACTIVE_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "16:05" not in text, f"active doc still references deprecated scheduler time: {path}"


def test_incident_doc_with_historical_1605_is_explicitly_archived_and_points_to_authority() -> None:
    text = INCIDENT_DOC.read_text(encoding="utf-8")
    assert "16:05" in text, "test must guard a real historical incident doc"
    assert "ARCHIVED — schedule references preserved for incident history" in text
    assert str(AUTHORITY_DOC) in text
