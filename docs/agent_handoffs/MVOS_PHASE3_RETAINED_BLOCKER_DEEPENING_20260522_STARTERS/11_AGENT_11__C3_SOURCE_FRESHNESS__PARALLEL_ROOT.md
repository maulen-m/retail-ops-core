# Agent 11 - C3 Source Freshness And Policy Gate Decomposition Route

Parallel group: `phase3_root`
Assigned gate: read-only/copied-temp only
Closeout path: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent11_c3_source_freshness_closeout.md`
Evidence root: `~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase3_retained_blocker_deepening/agent11_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE3_RETAINED_BLOCKER_DEEPENING_20260522_STARTERS/11_AGENT_11__C3_SOURCE_FRESHNESS__PARALLEL_ROOT.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/PHASE2_ORCHESTRATOR_REVIEW.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_serialized_copied_temp_integrator_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos_phase2_owner_confirmed_blocker_closure/agent7_evidence/RETAINED_BLOCKER_BOARD.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_retained_blocker_repair_wave/agent882_c3_source_freshness_bridge_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911b_ab_operational_truth_source_freshness_closeout.md`

## Mission

Deepen retained blockers `R002` and `R003`:

- strict source freshness fails for `src_ab_db_operational_truth`, `src_bank_manual_ingest`, `src_facebook_ads_external_ads`, and `src_web_automation_kaspi_marketing_directapi`;
- C3 gates `ads_source_truth`, `cashflow_source_truth`, `source_freshness`, and `stock_source_truth` still block.

Do not upgrade copied-temp bridge proof into production/source-pointer truth.

## Required Work

1. Create the evidence root.
2. Capture start boundary:
   - protected-surface `git status --short`;
   - SHA for `db/app.db` and Agent 7 copied DB if read;
   - `./scripts/check_no_db_tracked.sh`.
3. Read Agent 7 C3 outputs:
   - `commands/70_validate_policy_source_freshness_20260521.stdout.json`
   - `commands/71_validate_policy_gate_results.stdout.json`
   - `commands/60_materialize_policy_source_freshness_after_po_ads.stdout.json`
   - `commands/61_materialize_policy_gate_results_after_po_ads.stdout.json`
4. Read prior Agent 882 and Agent 911b closeouts enough to avoid flattening older bridge proof into current-source truth.
5. Build a source-freshness decomposition table under your evidence root with:
   - source id;
   - current validator status;
   - latest observed date;
   - expected freshness date/window;
   - blocked policy gate(s);
   - local-only route, copied-temp bridge route, human-only route, CodeCaptain route, or hard retained route.
6. Explicitly classify physical stock:
   - owner confirmed no fresher physical stock source exists;
   - offer availability must not be promoted to physical stock truth.
7. Identify which C3 rows can be deepened locally without source-pointer writes and which cannot.

## Forbidden

- No production DB writes.
- No source-pointer writes.
- No workbook writes.
- No scheduler/LaunchAgent/cron changes.
- No Web_automation writes.
- No external/Kaspi/WebUI/API writes or fetches.
- No owner publication or production preflight.

## Closeout Requirements

Write the closeout at the assigned path. Include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- source-freshness decomposition summary;
- exact policy gates still blocked;
- what can be autonomously done next and what cannot;
- exact evidence paths;
- protected-surface boundary result.
