from pathlib import Path


def test_daily_workflow_defers_to_kaspi_ops_contract_for_schedule() -> None:
    workflow = Path("docs/DAILY_WORKFLOW.md").read_text(encoding="utf-8")
    assert "docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md" in workflow
    assert "15:02" in workflow
    assert "16:01" in workflow
    assert "17:02" in workflow
    assert "16:00 | Second order import" not in workflow
    assert "Fill or confirm `SalesRaw_Today.MY_SIZE`" in workflow
    assert "Run_Control.ready_for_closeout = READY" in workflow
    assert "No daily owner approval phrase" in workflow
    assert "no age expiry" in workflow
    assert "Current production path is" not in workflow
    assert "This document does not assert that the production scheduler is currently installed, loaded, or running." in workflow
    assert "next-day order prep | Manual" not in workflow
    assert "Confirm handover in Kaspi seller portal" not in workflow
    assert "seller-portal confirmation is not a canonical employee system action" in workflow
    assert "schema-version-2" in workflow
    assert "schema-v4" in workflow
    assert "If it is zero, no bundle is sent" in workflow
    assert "Uncertain obligations can never become zero-order success" in workflow


def test_daily_sop_lists_current_import_and_waybill_schedule_pair() -> None:
    sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    assert "09:30" in sop
    assert "11:00" in sop
    assert "15:02" in sop
    assert "16:01" in sop
    assert "17:02" in sop
    assert "18:30" in sop
    assert "19:15" in sop
    assert "30000001_PP1" in sop
    assert "30000002_PP1" in sop
    assert "no active PP1 store uses a `16:00` same-day cutoff" in sop
    assert "Canonical Employee Shipping Workflow After Activation" in sop
    assert "No daily owner approval phrase" in sop
    assert "target_date + ready_set_at" in sop
    assert "no age expiry" in sop
    assert "preserve only rows still present in DB-selected shipping truth" not in sop
    assert "fresh source-backed eligible DB rows union unresolved shipping obligations" in sop
    assert "Phase 9.5: Legacy Manual Kaspi API Operations (Technical Recovery Only)" in sop
    assert "When to Run:** Every morning and before processing shipments" not in sop
    assert "Legacy Google Ops Board size-writeback preview is unscheduled and manual-only" in sop
    assert "READY closeout owns the request-bound size writeback" in sop
    assert "immutable live send manifest is schema v4" in sop
    assert "If the reconciled required-order count is nonzero" in sop
    assert "proven zero-order request sends no bundle" in sop


def test_scheduler_incident_doc_marks_current_contract_as_superseding_1605() -> None:
    incident = Path("docs/KASPI_IMPORT_SCHEDULER_INCIDENT_SUMMARY_2026-02-17.md").read_text(
        encoding="utf-8"
    )
    assert "Current authoritative schedule" in incident
    assert "11:00" in incident
    assert "15:02" in incident
    assert "16:01" in incident
    assert "17:02" in incident
