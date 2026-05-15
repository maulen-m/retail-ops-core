# Agent 63 - Conditional WS4 Readiness Pack For CodeCaptain

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_conditional_ws4_readiness_pack_for_codecaptain_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_evidence/`

Dependency:

- Launch only after Agent62 closeout is reviewed.
- Required dependency closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_62_pinned_reproof_after_asof_fix_closeout.md`

## Mission

Prepare a conditional WS4 readiness pack for CodeCaptain review.

This pack must make the production apply boundary explicit, pinned to the reviewed proof, and honest about remaining YELLOW items. It must not ask the owner for an authorization phrase and must not perform production apply.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SHIPPING_DISCREPANCY_DECISION_20260506.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-06/120135_TASK-000_codecaptain-proscope-system-review/answer/Code_Captain_2026-05-06_12_32_00_GMT+5.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_asof_materializer_contract_fix_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_62_pinned_reproof_after_asof_fix_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_59_workbook_tail_shipping_forensics_closeout.md`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_60_default_current_validator_daily_blocker_closeout.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_conditional_ws4_readiness_pack_for_codecaptain_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_evidence/**`
- A compact flat CodeCaptain review pack under `~/Docs/Oracle/Autonomous_business/2026-05-06/` if needed.

Forbidden:

- Do not mutate production `db/app.db`.
- Do not edit the live CRM workbook.
- Do not edit source code unless a tiny manifest-generation helper is absolutely required.
- Do not pause/unload schedulers.
- Do not call live APIs or external systems.
- Do not ask for owner production-apply authorization.
- Do not create or reuse the old Agent54 owner phrase.

## Required Pack Contents

Create a conditional WS4 readiness pack that includes:

- exact as-of date: `2026-05-04`;
- proof DB path and SHA from Agent62;
- frozen baseline DB/workbook paths and SHAs;
- current production DB/workbook SHAs for awareness only;
- source-freshness and validator matrix;
- clear distinction between pinned release proof and default-current/daily-current proof;
- production apply boundary, write scope, backup-first requirements, and rollback path;
- explicit stoplines;
- list of accepted YELLOW conditions and why they are not hidden:
  - `912298499` employee follow-up/ship tomorrow;
  - `912168984` system rescue required for missing `MY_SIZE`;
  - workbook tail requires canonical status refresh before another send build;
  - 23 STOREB product-identity quarantine residuals remain visible as WARN;
  - Option C remains validate-only until production release anchor exists.
- CodeCaptain request prompt asking whether this conditional WS4 contract is sufficient to proceed to owner-phrase drafting, not production apply.

## Gate Semantics

`GREEN`:

- Agent62 is non-RED and provides usable pinned proof;
- readiness pack is complete, flat/compact, source-cited, and ready for CodeCaptain review;
- no production mutation or owner phrase request occurred.

`YELLOW`:

- pack is useful but CodeCaptain review should be scoped as conditional because a specific YELLOW item remains unresolved.

`RED`:

- Agent62 is RED;
- pack hides a YELLOW/RED risk;
- production mutation occurs;
- old Agent54 phrase or direct production apply is requested.
