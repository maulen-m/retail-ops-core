# Agent 736 - Workbook Drift And Scheduler Forensics, Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_736_workbook_drift_scheduler_forensics_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_736_evidence/`

Parallel group:

`agent736_737_red_triage_root`

## Mission

Explain Agent735's live workbook drift in plain operational terms and determine whether it was caused by an active Kaspi import/scheduler lane, manual Excel activity, or an unknown actor.

This is read-only. Do not pause, kill, restart, or mutate schedulers. Do not mutate the live workbook, production DB, external systems, or repo code/config.

You are not alone in the codebase. Do not revert or overwrite unrelated edits by others.

## Required Context

Read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/AGENT735_ORCHESTRATOR_REVIEW_20260509.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_fresh_owner_request_preflight_no_apply_after_734_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/DRIFT_STABILITY_REPORT.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/FRESH_PRODUCTION_BOUNDARY_REPORT.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_735_evidence/FINAL_BOUNDARY_STATUS.json`

## Allowed Writes

Only write under the assigned evidence folder and assigned closeout.

## Required Evidence Files

Create:

1. `READCHECK.md`
2. `WORKBOOK_METADATA_TIMELINE.md`
3. `PROCESS_AND_SCHEDULER_SNAPSHOT.md`
4. `IMPORT_COMMAND_AND_LOG_EVIDENCE.md`
5. `DRIFT_CAUSE_DECISION.md`
6. `QUIET_WINDOW_RETRY_RECOMMENDATION.md`

## Required Work

1. Capture current metadata for `excel_ui/SALES_KSP_CRM_V3.xlsx`: SHA256, size, mtime, inode if available.
2. Capture `lsof` for the workbook and production DB.
3. Capture relevant process tree for active import/scheduler/waybill/google/db/workbook writers.
4. Inspect repo logs or run artifacts around `2026-05-09T11:01..11:07+05:00` to identify what wrote the workbook.
5. Determine whether the `scripts/import_orders_to_crm.py --no-update ...` process can write the live workbook despite `--no-update`, or whether another process likely wrote it.
6. Record whether the scheduler is still active and whether a later preflight needs an explicit quiet window.
7. Do not infer owner authorization for pausing. If quieting is needed, write the exact recommended pause/restore plan for orchestrator/owner review.

## Gate Semantics

`GREEN`:

- workbook drift cause is evidence-backed;
- no production mutation was performed by you;
- a safe retry condition or quiet-window plan is clear.

`YELLOW`:

- likely cause is narrowed but some logs/process evidence is missing.

`RED`:

- active uncontrolled writer risk remains and cannot be bounded;
- evidence suggests hidden or unsafe mutation outside expected scheduler behavior;
- any forbidden mutation occurred.

## Closeout

Write a closeout with READCHECK, files written, commands run, drift cause, current writer status, quiet-window recommendation, mutation statement, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
