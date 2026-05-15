# Option A/B/C Decision-Grade Sequence Plan

Generated: `2026-05-05`

## Goal

Move from Agent 42's valid `YELLOW` temp proof to a practical, decision-grade operating path:

- Option A first: unblock useful daily stock and profit operation without hiding residual risk.
- Option B second: apply reviewed fixes into production with backup and rollback discipline.
- Option C third: make the system run daily without the owner asking agents to recalculate.

## Current Truth

Agent 42 proved:

- all required sources are fresh;
- ads source truth passes;
- cashflow source truth passes;
- stock source truth remains blocked by STOREB `ORDER_ENTRY_MISSING=23`;
- exception queue remains blocked;
- actual cash is structurally rebuilt but not reconciled to manual bank truth.

## Option A Definition

Option A is complete when a temp DB proves:

- STOREB `23` unknown-product orders cannot leak into product stock, COGS, or product profit;
- exception queue residuals are reduced by source repair where possible;
- unresolved owner-only questions are explicit and minimal;
- source freshness, ads gates, cashflow coverage, and cashflow invariants still pass;
- remaining blockers, if any, are visible and intentionally quarantined.

## Option B Definition

Option B is complete when:

- the Option A temp proof is reviewed;
- production apply is backup-first, serialized, and reversible;
- protected workbook and external systems are not mutated unless explicitly authorized;
- post-apply validators reproduce the temp proof;
- owner-facing surfaces clearly label any remaining YELLOW limitations.

## Option C Definition

Option C is complete when:

- a daily runner can refresh source data, rebuild stock/cashflow/policy gates, and write an owner brief;
- stale/missing/conflicting data produces a fail-closed exception queue;
- scheduling uses deterministic repo venv/interpreter paths;
- the owner receives a daily decision packet without manually prompting agents;
- cashflow, inventory, purchase planning, reorder timing, ads spend, and inbound decisions all read from one operational truth path.

## Stoplines

- Do not clear STOREB `23` by partial order-entry insertion.
- Do not clear weak owner-policy overlaps without exact owner approval or source repair.
- Do not treat structurally rebuilt cash as actual decision-grade cash until reconciled to manual/bank truth.
- Do not production-apply without backup, explicit apply env gate, and post-apply validators.
- Do not weaken validators to obtain green.

## Current Status After Agent 53

Agent 53 is accepted as `GREEN`.

Code Captain reviewed the Agent 54 authorization Oracle pack on `2026-05-06 11:00:00 GMT+5` and is assigned highest review authority for this decision.

Code Captain source answer:

- `~/Docs/Oracle/Autonomous_business/2026-05-05/204302_TASK-000_agent54-authorization-review/Answer/Code_Captain_2026-05-06_11_00_00_GMT+5.md`

Integrated authority memo:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/CODE_CAPTAIN_AUTHORITY_INTEGRATION_AGENT54_20260506.md`

Highest-authority decision:

- `Gate: YELLOW - CONDITIONAL GO TO ASK OWNER FOR THE EXACT PHRASE`

Option B is technically ready to request narrow owner authorization, but Agent 54 is not pre-approved. The production apply is intentionally paused on explicit human authorization because it mutates production `db/app.db`.

Agent 54 must also enforce the Code Captain May 6 freshness/as-of stopline: the reviewed command family is tied to the `2026-05-04` as-of window, so if source freshness or as-of-window proof is stale for the May 6 launch, Agent 54 must stop without mutation and require fresh temp proof or an updated readiness contract.

Local orchestrator diagnostic after reading Code Captain confirms this stopline is active on current production: `validate_policy_source_freshness.py --db ~/Docs/Autonomous_business/db/app.db --as-of 2026-05-04 --strict --json` exits `1` with stale/blocked/future source freshness rows. Therefore the most efficient safe next step is a no-mutation Agent 54A May 6 freshness/as-of preflight before asking the owner to spend authorization on Agent 54.

Option C remains blocked until Agent 54 completes and an independent post-apply reviewer verifies production state.

Prepared but not launched:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/starter_prompts/54_AGENT_54__OPTION_B_HUMAN_AUTHORIZED_PRODUCTION_APPLY_AFTER_53_GREEN.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/starter_prompts/54A_AGENT_54A__MAY6_FRESHNESS_ASOF_PREFLIGHT_BEFORE_AGENT54.md`

Required owner authorization phrase before Agent 54 launch:

```text
AUTHORIZE AGENT 54 PRODUCTION APPLY FOR ~/Docs/Autonomous_business/db/app.db AT PRE-SHA e07315150fd3ad5ad10e6e09e7853159291e954d68a63933eb837fd1fe7c880d
```
