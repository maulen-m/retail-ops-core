# Agent854 - Lifecycle Cancellation Repair

You are Agent854 for the Autonomous_business MVOS Agent846 YELLOW repair wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/PLAN.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT846_YELLOW_REPAIR_WAVE_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_post_codecaptain_webui/WEBUI_STATUS_REFRESH_CLOSEOUT.md`
10. `~/Docs/Autonomous_business/exports/validation/mvos_20260517_webui_status_refresh_residual_join/RESIDUAL_112_JOIN_REPORT.md`
11. `~/Docs/Autonomous_business/exports/validation/mvos_20260517_webui_status_refresh_residual_join/residual_112_joined_to_20260517_webui.csv`
12. `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/Answer/Code Captain_17.05.2026_09_59_38.md`

## Assignment

Resolve or keep blocked the five remaining lifecycle cancellation rows:

| store_code | order_id | status |
|---|---|---|
| `STOREB` | `915465339` | `CANCELLING` |
| `STOREB` | `919478081` | `CANCELLING` |
| `STOREB` | `919976585` | `CANCELLING` |
| `UNIVERSAL` | `919005528` | `CANCELLING` |
| `UNIVERSAL` | `919681847` | `CANCELLING` |

Use the manually supplied WebUI archive import first:

`~/Docs/Autonomous_business/imports/webui_archive_manual/17.05.2026_09_54_42`

If needed, you may run read-only WebUI/API checks using existing repo methods. No external writes.

## Write Scope

Read-only with respect to repo state. Write only:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent854_lifecycle_cancellation_repair_evidence/`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent854_lifecycle_cancellation_repair_closeout.md`

## Not Authorized

Do not mutate production DB, workbooks, scheduler/LaunchAgent/cron state, Web_automation, Kaspi/API state, external accounts, owner publication, cash, PO, stock, or price.

## Required Work

1. For each of the five rows, search current local WebUI archive output and source CSVs.
2. Check whether a valid `status_change_at` or cancellation-specific source contract exists.
3. If no source exists, define the exact minimal manual/API/WebUI source evidence needed.
4. Produce an Agent859-ready table with `RESOLVED`, `API_CONTRACT_REVIEW`, or `KEEP_BLOCKED`.
5. Write the closeout with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Closeout Must Include

- one row per order;
- source path, source timestamp, and evidence status;
- whether Agent859 may consume the row in copied-temp proof;
- explicit list of rows that must remain blocked;
- explicit non-authorization statement for production apply.
