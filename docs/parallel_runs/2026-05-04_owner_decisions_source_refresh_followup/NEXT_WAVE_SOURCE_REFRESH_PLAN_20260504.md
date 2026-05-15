# Next Wave Source Refresh Plan

Recorded: `2026-05-04`

Status: plan and starter prompts only. No DB/workbook/source writes are authorized by this plan.

## Objective

Remove the current decision-grade blockers without creating false-green data:

- recover real order-entry evidence for `ORDER_ENTRY_MISSING=15046`;
- convert the `2026-05-04 13:11 +0500` Kaspi Pay statements/reports into a trusted cash anchor;
- replace future recurring manual statement downloads with deterministic daily cashflow computation from Kaspi API orders/sales plus confirmed anchors;
- preserve owner stock/quarantine decisions and LINE31 planned inbound context as separate lanes.

## Authoritative Inputs

Owner decisions and stock/PO answers:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`

Order-entry and cashflow source authorization:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`

Prior final review with blocker counts:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_FINAL_REVIEW.md`

## Recommended Execution Shape

Phase 1 should be read-only and parallel:

- Agent 1: order-entry recovery evidence map.
- Agent 2: Kaspi Pay cash anchor evidence map.
- Agent 3: deterministic daily cashflow design contract.

Phase 2 should be one serialized write-capable executor only after Phase 1 closes:

- implement the minimum code/config changes required to ingest evidence safely;
- run dry-run first;
- back up `db/app.db` before apply;
- apply only behind explicit write-enable env flags and `--apply`;
- rerun integration gates.

Phase 3 should rematerialize owner brief and stock/cashflow publication:

- only after order-entry, cashflow, ads, PO/inbound, and owner-stock decisions are represented in operational truth;
- keep unrecovered items quarantined instead of forcing green.

## Starter Prompts

Use these starter prompts for the next read-only wave:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/starter_prompts/01_AGENT_1__ORDER_ENTRY_RECOVERY__READONLY_PARALLEL.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/starter_prompts/02_AGENT_2__KASPI_PAY_CASH_ANCHOR__READONLY_PARALLEL.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/starter_prompts/03_AGENT_3__DETERMINISTIC_CASHFLOW_DAILY_DESIGN__READONLY_PARALLEL.md`

Existing reviewed LINE31 prompt remains a separate planned-inbound lane:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/LINE31_PO1A_OLIVE_GREEN_INGEST_AGENT_PROMPT_REVIEWED_20260504.md`

## Success Gates

Phase 1 closeouts must answer:

- how many missing order entries are recoverable from current CRM;
- how many are recoverable from stronger sources than archive fallback;
- how many remain unrecovered and must be quarantined;
- whether the Kaspi Pay source package can establish a reliable cash anchor through `2026-05-03`;
- whether future daily cashflow can be computed from API events and anchor snapshots without manual statement downloads;
- exact scripts, tests, and apply gates required for Phase 2.

Phase 2 cannot start if:

- Phase 1 proposes synthetic entries;
- Phase 1 cannot separate actual cash from modeled receivables;
- source coverage is ambiguous by store/date;
- required apply rollback path is missing.
