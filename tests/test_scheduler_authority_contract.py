from pathlib import Path


def test_daily_workflow_defers_to_kaspi_ops_contract_for_schedule() -> None:
    workflow = Path("docs/DAILY_WORKFLOW.md").read_text(encoding="utf-8")
    assert "docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md" in workflow
    assert "16:03" in workflow
    assert "16:00 | Second order import" not in workflow


def test_daily_sop_lists_current_import_and_waybill_schedule_pair() -> None:
    sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    assert "11:00" in sop
    assert "16:03" in sop
    assert "18:30" in sop


def test_scheduler_incident_doc_marks_current_contract_as_superseding_1605() -> None:
    incident = Path("docs/KASPI_IMPORT_SCHEDULER_INCIDENT_SUMMARY_2026-02-17.md").read_text(
        encoding="utf-8"
    )
    assert "Current authoritative schedule" in incident
    assert "11:00" in incident
    assert "16:03" in incident
