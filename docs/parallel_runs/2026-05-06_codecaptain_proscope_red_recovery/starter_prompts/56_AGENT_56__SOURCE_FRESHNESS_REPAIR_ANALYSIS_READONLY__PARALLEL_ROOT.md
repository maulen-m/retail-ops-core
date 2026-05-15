# Agent 56 - Source Freshness Repair Analysis Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_56_source_freshness_repair_analysis_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_56_evidence/`

## Mission

Explain the production source-freshness blockers that made Agent 54A return RED and produce a source-by-source repair plan.

This is read-only analysis. Do not refresh external systems, do not repair production, and do not mutate the DB/workbook.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-06/120135_TASK-000_codecaptain-proscope-system-review/answer/Code_Captain_2026-05-06_12_32_00_GMT+5.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_54a_may6_freshness_asof_preflight_closeout.md`
8. `~/Docs/Autonomous_business/scripts/validate_policy_source_freshness.py`
9. `~/Docs/Autonomous_business/core/ops/policy_registry_c3.py`

## Current Known Blockers

Agent 54A recorded production strict freshness failure for as-of `2026-05-04`:

- `src_ab_db_operational_truth`: `BLOCKED`
- `src_ecommerce_po_artifacts`: `STALE`
- `src_facebook_ads_external_ads`: `STALE`
- `src_inbound_workbook`: `FUTURE`
- `src_sourcing_research_supplier_routes`: `STALE`

Agent 53 accepted temp DB passed the same strict validator.

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_56_source_freshness_repair_analysis_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_56_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not edit `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit repo files.
- Do not run write-enabled scripts.
- Do not refresh live APIs or browser sessions.
- Do not change external repos.
- Do not ask owner for authorization.
- Do not launch Agent 54.

## Required Analysis

For each blocker, identify:

- source ID and owning domain;
- expected source path or evidence pointer;
- current production source-freshness row values;
- matching Agent 53 temp source-freshness row values;
- whether the problem is stale mtime, stale content date, future date, missing evidence, policy rule, path bug, or production-vs-temp drift;
- exact repair action needed;
- whether owner input is required;
- whether the repair can run in parallel later or must wait for drift baseline decision.

Also evaluate validator design:

- Does the validator report DB path, policy version, source IDs, and as-of clearly enough?
- Is any blocker caused by directory root mtime instead of nested artifact freshness?
- Is `FUTURE` inbound caused by timezone/content-date handling or real future-dated evidence?
- Is source freshness able to pass in temp while production fails because materialization is not production-applied?

## Suggested Read-Only Evidence Commands

Use only as appropriate:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db '.schema source_freshness_result'
sqlite3 -readonly ~/Docs/Autonomous_business/db/app.db 'select * from source_freshness_result order by source_id;'
sqlite3 -readonly ~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_53_evidence/agent53_full_replay_with_wrappers_temp_20260505.db 'select * from source_freshness_result order by source_id;'
```

Do not use destructive shell commands.

## Success Criteria

Closeout must include:

- standalone `Gate: GREEN/YELLOW/RED`;
- READCHECK with files read;
- source-by-source blocker table;
- production-vs-Agent53-temp freshness comparison;
- root-cause classification for each blocker;
- repair plan with owner input requirements;
- recommendation for what can run before WS1 finishes versus what must wait;
- evidence file list.

## Gate Semantics

`GREEN`:

- every blocker has a concrete evidence-backed repair path and no unresolved source ambiguity.

`YELLOW`:

- most blockers are classified, but some require owner/external-source action.

`RED`:

- source freshness cannot be safely interpreted, or validator/source ownership is too ambiguous for current-baseline proof.
