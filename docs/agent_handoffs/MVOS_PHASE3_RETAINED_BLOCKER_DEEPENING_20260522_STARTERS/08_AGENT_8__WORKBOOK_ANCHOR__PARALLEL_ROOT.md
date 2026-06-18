# Agent 8 - Workbook Anchor Mismatch Route

Parallel group: `phase3_root`
Assigned gate: read-only/copied-temp only
Closeout path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent8_workbook_anchor_closeout.md`
Evidence root: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent8_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/08_AGENT_8__WORKBOOK_ANCHOR__PARALLEL_ROOT.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/PHASE2_ORCHESTRATOR_REVIEW.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_serialized_copied_temp_integrator_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_evidence/RETAINED_BLOCKER_BOARD.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_evidence/VALIDATOR_EXIT_MATRIX.tsv`

## Mission

Deepen blocker `B005_workbook_content_lag`: explain exactly why `validate_sales_vs_workbook_anchor.py` fails after Phase 2 copied-temp sales rebuild passed.

Use current repo state and Agent 7 evidence as authority. Do not depend on chat history.

## Required Work

1. Create the evidence root.
2. Capture start boundary:
   - `git status --short` for protected surfaces;
   - SHA for `db/app.db`, `excel_ui/SALES_KSP_CRM_V3.xlsx`, and Agent 7 copied DB if read;
   - `./scripts/check_no_db_tracked.sh`.
3. Read Agent 7 workbook-anchor failure:
   - `commands/74_validate_sales_vs_workbook_anchor.stdout.txt`
   - `commands/74_validate_sales_vs_workbook_anchor.stderr.txt`
4. Re-run the validator read-only if useful, writing stdout/stderr/exit into your evidence root.
5. Inspect the validator implementation enough to classify the failure:
   - stale workbook date lag;
   - unit mismatch;
   - net revenue mismatch;
   - parser/schema issue;
   - copied-temp sales fact legitimately ahead of workbook;
   - other.
6. If safe, extract a compact mismatch table by date/store from read-only sources. Do not write to the workbook.
7. Identify the minimum next repair route:
   - workbook import/refresh route;
   - validator contract change;
   - copied-temp sidecar route;
   - retain blocker until live daily ops refreshes workbook;
   - owner clarification required.

## Forbidden

- No production DB writes.
- No workbook writes.
- No source-pointer writes.
- No scheduler/LaunchAgent/cron changes.
- No external/Kaspi/WebUI/API writes or fetches.
- No owner publication or production preflight.

## Closeout Requirements

Write the closeout at the assigned path. Include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- concise summary of exact workbook-anchor failure;
- table of mismatch classes and counts;
- exact evidence paths;
- whether the blocker can be closed autonomously later without human input;
- exact next command or route if known;
- protected-surface boundary result.
