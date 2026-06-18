# Agent859 - Synthesis Copied-Temp MVOS Rerun

You are Agent859 for the Autonomous_business MVOS Agent846 YELLOW repair wave.

Do not start until Agents 852, 853, 854, 855, and 858 have written closeouts and the orchestrator has reviewed them.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT846_YELLOW_REPAIR_WAVE_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent852_cogs_unit_route_repair_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent853_source_freshness_repair_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent854_lifecycle_cancellation_repair_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent855_storeb_ads_11956144b_repair_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent858_po_status_ledger_repair_closeout.md`
12. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/ORCHESTRATOR_REVIEW_AFTER_REPAIR_ROOT.md`

## Assignment

After root closeouts are reviewed, synthesize the repair wave and run one copied-temp-only MVOS proof rerun if it is safe and meaningful.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_agent846_yellow_repair_wave/20260517_143308/agent859_synthesis_copied_temp_rerun/`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent859_synthesis_copied_temp_rerun_closeout.md`

## Write Scope

You may write only:

- the assigned evidence root;
- the assigned closeout;
- copied DBs inside the assigned evidence root.

Do not mutate production `db/app.db`, workbooks, scheduler/LaunchAgent/cron state, source pointers, Web_automation, Kaspi/API, ad platforms, bank/cash, PO commitments, stock, prices, owner publication, or external systems.

## Required Work

1. Read all five root closeouts and record their gates.
2. If any root closeout is missing or RED, stop RED.
3. If any root closeout is YELLOW, preserve the final gate as YELLOW unless a copied-temp validator run genuinely proves the blocker can be cleared without hiding risk.
4. Resample production boundary before copying:
   - `db/app.db` SHA-256;
   - `excel_ui/SALES_KSP_CRM_V3.xlsx` SHA-256;
   - file stats;
   - `sqlite3 db/app.db 'PRAGMA integrity_check;'`;
   - `lsof` for DB/workbook;
   - protected-surface git status.
5. Copy production DB to the assigned evidence root and mutate only the copy.
6. Apply only root-agent accepted copied-temp routes.
7. Rerun the smallest meaningful validator chain from Agent846.
8. Preserve every still-blocked source row, ads row, cancellation row, PO row, or status-ledger row visibly.
9. Write the closeout with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Closeout Must Include

- root closeout gate matrix;
- production boundary hashes and copied DB path;
- copied-temp changes made;
- validators run and exact exits;
- final retained blockers;
- exact production candidates if any, expected usually none;
- explicit non-authorization statement for production apply or owner publication.
