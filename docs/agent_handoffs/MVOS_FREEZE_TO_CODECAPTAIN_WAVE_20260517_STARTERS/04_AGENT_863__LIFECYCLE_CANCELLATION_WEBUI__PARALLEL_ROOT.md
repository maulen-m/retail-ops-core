# Agent863 Starter: Lifecycle Cancellation WebUI Route

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_freeze_to_codecaptain_wave/agent863_lifecycle_cancellation_webui_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business/exports/validation/mvos_freeze_to_codecaptain_wave/20260517_183241/agent863_lifecycle_cancellation_webui`

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/PLAN.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_freeze_to_codecaptain_wave/ORCHESTRATOR_HANDOFF.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Assignment

Use the fresh manual WebUI ArchiveOrders downloads to resolve or narrow the five cancellation blockers.

Fresh source root:

`~/Docs/Autonomous_business/imports/webui_archive_manual/17.05.2026_18_26_58`

Known cancellation blockers:

- `STOREB 915465339`
- `STOREB 919478081`
- `STOREB 919976585`
- `UNIVERSAL 919005528`
- `UNIVERSAL 919681847`

Do:

- Import/normalize the manual WebUI source root using `scripts/run_webui_archive_source_refresh.py --mode import-existing` where safe.
- Validate status-change-date evidence.
- Join the five cancellation rows to the normalized output.
- Classify which rows are source-resolved and which still need API/CodeCaptain contract review.

Do not:

- mutate production DB/workbook;
- synthesize missing status-change dates;
- use browser/live automation unless import-existing fails and the stopline is recorded.

Closeout must include:

- standalone `Gate: <GREEN/YELLOW/RED>` line;
- exact source path and generated pack path;
- row-level cancellation status table;
- recommendation for Agent867 copied-temp proof.
