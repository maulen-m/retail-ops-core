# Agent 64 - Owner Phrase Contract Draft Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_owner_phrase_contract_draft_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_evidence/`

## Mission

Draft a new owner authorization phrase contract for later review.

This is a drafting-only lane. It must not ask the owner to authorize anything, must not mutate production, and must not present the phrase as active or usable until a later review explicitly approves it.

## Bootstrap Context

Before writing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_WS4_DRAFTING_GATE_DECISION_20260507.md`
7. `~/Docs/Oracle/Autonomous_business/2026-05-07/094107_TASK-000_codecaptain-ws4-conditional-proscope-review/Answer/Code_Captain_2026-05-07_10_22_00_GMT+5.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_asof_materializer_contract_fix_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_62_pinned_reproof_after_asof_fix_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_63_conditional_ws4_readiness_pack_for_codecaptain_closeout.md`
11. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SHIPPING_DISCREPANCY_DECISION_20260506.md`

## Write Boundary

Allowed writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_owner_phrase_contract_draft_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_64_evidence/**`

Forbidden:

- Do not mutate production `~/Docs/Autonomous_business/db/app.db`.
- Do not edit the live CRM workbook.
- Do not edit source code.
- Do not pause/unload schedulers.
- Do not call live APIs, web UIs, browser automation, banks, Kaspi, ads platforms, Google, Web_automation, or external systems.
- Do not ask the owner for the phrase.
- Do not mark the phrase active.
- Do not reuse, quote as active, or request the old Agent54 owner phrase.
- Do not create a production apply script or run any apply command.

## Required Outputs

Write these files under the assigned evidence folder:

1. `OWNER_AUTHORIZATION_PHRASE_DRAFT__INACTIVE_REVIEW_REQUIRED.md`
2. `OWNER_PHRASE_DRAFT_REVIEW_CHECKLIST.md`
3. `OWNER_PLAIN_ENGLISH_BRIEF__NOT_AUTHORIZATION_REQUEST.md`

The phrase draft must include:

- a large `INACTIVE DRAFT - NOT AN AUTHORIZATION REQUEST` banner;
- exact target scope: production `~/Docs/Autonomous_business/db/app.db` only, for a later lane if approved;
- exact pinned proof authority: Agent62 temp DB SHA `e7d497c4403f3777ad77d7e3c1db83d5e8678360016e166394e4bdbebe2a1022`;
- exact as-of boundary: `2026-05-04`;
- required expected row matrix from Agent62;
- required post-as-of leakage expectations: zero post-as-of rows in `order_status_event`, `sales_fact_v2`, `stock_ledger`, `fact_cashflow_events`, and `fact_cashflow_daily`;
- all CodeCaptain stoplines from the May 7 answer;
- all Agent63 YELLOW items;
- apply-time preflight requirements: current DB SHA, workbook SHA, DB integrity, no SQLite sidecars, no `lsof` holder, backup path/SHA, rollback command, env gate plus `--apply`, pinned validators, row-count/leakage proof;
- explicit sentence that no owner should type or approve this phrase until a later review tells the owner to do so.

The review checklist must make it easy for the orchestrator to reject the draft if:

- any stopline is missing;
- any YELLOW item is hidden;
- the phrase can be confused with an active request;
- old Agent54 phrase wording appears;
- any production write or owner request happened.

The owner plain-English brief must explain:

- what has been proven;
- what has not been proven;
- why no action is requested from the owner yet;
- what will happen before the owner is ever asked for authorization.

## Gate Semantics

`GREEN`:

- Draft files are complete, inactive, review-required, and contain all required stoplines and YELLOW limitations.
- No production mutation, owner request, old phrase reuse, live API, workbook edit, or scheduler change occurred.

`YELLOW`:

- Draft is useful but has a clearly listed ambiguity that requires orchestrator/CodeCaptain review before it can become an owner request.

`RED`:

- Any production mutation occurred.
- Owner authorization was requested.
- The phrase is marked active or usable now.
- The old Agent54 phrase is reused or requested.
- Stoplines or YELLOW limitations are hidden.
- The draft permits production apply without a fresh apply-time boundary and owner exact phrase.

## Closeout Requirements

The closeout must include:

- standalone `Gate: GREEN/YELLOW/RED` line;
- READCHECK list;
- exact files written;
- mutation statement;
- whether any phrase text is inactive-only;
- whether any stopline was not included;
- recommended next step after orchestrator review.
