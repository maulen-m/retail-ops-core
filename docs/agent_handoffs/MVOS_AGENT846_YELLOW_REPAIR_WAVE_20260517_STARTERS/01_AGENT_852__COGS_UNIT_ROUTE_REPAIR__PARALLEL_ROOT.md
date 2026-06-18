# Agent852 - COGS Unit Route Repair

You are Agent852 for the Autonomous_business MVOS Agent846 YELLOW repair wave.

## Bootstrap

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_yellow_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT846_YELLOW_REPAIR_WAVE_20260517_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-16_mvos_source_fact_repair_round2/agent848_cashflow_cogs_balance_repair_closeout.md`
8. `~/Docs/Oracle/Autonomous_business/2026-05-16/182945_TASK-000_mvos-repair-round2-agent846-codecaptain/Answer/Code Captain_17.05.2026_09_59_38.md`

## Assignment

Resolve the Agent846 strict COGS blocker:

```text
ACMEWEAR 909054064 / SUIT-31-TS
```

Agent848 provided owner-approved copied-temp-only unit COGS:

```text
LINE-31-TS=6006.76 KZT
SUIT-21-TS=5567.22 KZT
SUIT-31-LS=5567.22 KZT
SUIT-31-TS=5567.22 KZT
```

Find the smallest safe way for the COGS validator/proof route to consume this accepted unit-COGS evidence without fake `base_cost_cny` or `weight_kg`.

## Allowed Write Scope

You are the only root agent allowed to make focused repo code/test edits in this wave.

You may edit only if necessary:

- `scripts/validate_cogs_completeness_by_month.py`
- focused tests under `tests/`
- the owning contract doc if the code change is a real contract change and the repo doc ladder requires it

You may also write evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent852_cogs_unit_route_repair_evidence/`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_yellow_repair_wave/agent852_cogs_unit_route_repair_closeout.md`

## Not Authorized

Do not mutate production `db/app.db`, workbooks, schedulers, external systems, Web_automation, Kaspi/API, ad platforms, bank/cash, PO commitments, stock, prices, or owner publication.

If the accepted unit-COGS route cannot be represented safely without a broader business-rule decision, stop YELLOW and describe the exact CodeCaptain/owner contract needed.

## Required Work

1. Inspect the validator and the source tables used by the failing strict check.
2. Prefer a tests-first patch if a code change is needed.
3. Preserve backward-compatible behavior for existing base-cost/weight routes.
4. Fail closed when unit-COGS evidence is missing, ambiguous, or outside the accepted owner approval.
5. Run the smallest focused tests/validators that prove the route.
6. Write the closeout with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

## Closeout Must Include

- the exact failing row and whether it is resolved;
- files changed, if any;
- tests and commands run;
- remaining risk;
- whether Agent859 may use the route in copied-temp synthesis;
- explicit non-authorization statement for production apply.
