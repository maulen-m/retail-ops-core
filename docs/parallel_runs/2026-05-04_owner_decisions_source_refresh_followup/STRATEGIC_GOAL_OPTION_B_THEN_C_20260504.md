# Strategic Goal: Option B Now, Option C Next

Recorded: `2026-05-04`

Status: owner-approved strategic direction. This document is a planning/goal surface, not a production apply authorization.

## Core Intention

The real goal behind this execution wave is not only to clear the current blockers. The goal is to make `~/Docs/Autonomous_business` a fully functional, verifiable autonomous business operating system.

Target state:

- daily stock, orders, sales, demand, PO/inbound, ads, COGS, cash, cashflow, calendar, owner brief, and exception queues run without the owner manually asking agents to recalculate;
- the system protects capital by staying fail-closed when truth is stale, missing, duplicated, or conflicting;
- business decisions are made from repo-preserved operational/economic truth, not from ad hoc chat memory or one-off workbook calculations;
- every green decision has reproducible evidence, source lineage, tests, and rollback path;
- the system should continuously move toward a real-life verifiable `10/10` autonomous operational functionality score.

## Chosen Path

We choose:

1. Option B now: balanced operational decision-grade path.
2. Option C immediately after: robust autonomous daily operating system path.

Option B is the active execution path because it removes the live blockers that currently prevent decision-grade owner publication.

Option C follows directly after Option B because our actual target is not a one-time green report. The target is a durable autonomous system that keeps itself current every day.

## Current Score

Current practical score after Agents 1-6 and while Agent 7 is running:

- Current production decision-grade system: about `4.5/10`.
- If accepted temp-chain work is safely applied: about `5.8/10`.
- After Agent 7 and serialized release/apply lane: expected about `6.5/10`.
- After ads, PO/inbound, lifecycle, and remaining source blockers are cleared: expected about `7.5-8/10`.
- After scheduler, source manifests, exception ownership, daily owner brief, and automatic run gates are fully operational: expected about `8.5-9/10`.

A real `10/10` requires the system to be boringly reliable in daily real-life operations, not just locally test-green.

## Option B: Active Execution Path

Goal: make the current business truth kernel decision-grade enough for stock/cash/profit/PO decisions without false-green publication.

Required outcomes:

- Order-entry recovery is production-applied only through a serialized backup-first release lane.
- D1 cashflow residue is repaired or explicitly quarantined through deterministic exceptions.
- Kaspi Pay cash anchor is persisted as reconciliation evidence, not fake order-level `CASH_IN`.
- Ads source truth is refreshed for active required stores and missing ads cannot be treated as zero.
- PO/inbound line-grain and double-count blockers are fixed or quarantined.
- Order lifecycle missing-completed evidence is repaired from real source events only.
- SKU mapping gaps that affect stock/profit remain blocked or quarantined; they are not guessed.
- Owner brief remains `RED_BLOCKED` until strict source freshness and gate validators are green.

Active immediate chain:

1. Agent 7 resolves the D1 residue on a temp DB.
2. If Agent 7 closes or explicitly quarantines the residue, create one serialized production release/apply lane for Agents 4-7.
3. Run post-apply validators and owner blocked/green brief materialization.
4. Launch narrow lanes for ads, PO/inbound, lifecycle, and SKU mapping blockers.
5. Rematerialize C3 policy state and owner brief only after true source/gate green.

Non-negotiable gates:

- no production `db/app.db` write without backup, env gate, `--apply`, evidence, and rollback instructions;
- no synthetic order entries, stock movements, cash events, ads rows, PO receipts, or SKU mappings;
- no tolerance widening to force green;
- no owner publication when ads, PO, cashflow, stock, or lifecycle blockers remain unresolved;
- no treating current-day partial data as complete-day truth.

## Option C: Next Architecture Path

Goal: turn the decision-grade kernel into a daily autonomous business operating system.

Required capabilities:

- scheduled daily truth rebuild under controlled repo venv/runtime;
- canonical business automation pause/resume/status/verify workflow for frozen proof windows and live daily-ops restoration;
- explicit manifest-backed LaunchAgent scopes so order import, Google Ops Board, Telegram closeout control, shipped-truth repair, and Web_automation-adjacent business jobs are not rediscovered from scratch;
- source manifests for every API pull, workbook, statement, ads refresh, PO/inbound source, and manual owner approval;
- run status tables for every daily pipeline step;
- validation result table and exception queue as first-class decision gates;
- deterministic daily stock snapshot from anchor plus append-only ledger events;
- daily cashflow from Kaspi order lifecycle plus cash anchors and obligation events;
- ads source refresh and campaign/product daily truth for active stores;
- PO/inbound/cargo/supplier obligations linked to source evidence and cashflow;
- owner daily brief with red/green trust banner, source freshness, blockers, cash risk, reorder risk, and action queue;
- agent handoff protocol where agents repair exceptions and code, but the system runs daily without a human prompt.

Option C is complete only when:

- the daily job can run unattended;
- stale/missing/conflicting inputs block publication automatically;
- green output can be reproduced from DB/source manifests/tests;
- frozen proof windows can be entered, verified, exited, and re-verified through `scripts/manage_business_automation.py` and `docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md`;
- owner only reviews exceptions and high-capital approvals, not routine recalculations;
- cashflow, stock, ordering, inbound, ads, and product-test decisions are tied to the same repo-owned truth plane.

## 10/10 Functionality Definition

The business system approaches `10/10` when it can answer these questions every day with evidence:

- What do we have in stock by item and size right now?
- What stock is active sellable, quarantined, inbound, on-delivery, returned, or blocked?
- What sold, what was cancelled, what was returned, and what cash actually changed?
- What is current inventory COGS and estimated profit after ads?
- What ads are running, for which stores/products, with source-backed spend and sales effect?
- What POs are ordered, preparing, shipped to cargo, in transit, arrived, paid, unpaid, or disputed?
- What cargo/supplier obligations are due and how do they affect cash reserve?
- What should we reorder, not reorder, discount, liquidate, test, or stop?
- What decisions are blocked because source truth is stale or missing?
- What exact evidence makes the report green?

## Current Active Blockers To Remove

As of the latest orchestrator review:

- `CASHFLOW_D1_CASH_IN_MISSING=11`
- `CASHFLOW_D1_DUPLICATE_CASH_IN=29`
- `CASHFLOW_D1_LINE_EVIDENCE_MISSING=12`
- `ADS_COVERAGE_MISSING=4138`
- `ADS_REFRESH_MISSING=4138`
- `ORDER_LIFECYCLE_MISSING_COMPLETED=442`
- `PO_INBOUND_REFERENCE_NOT_LINE_GRAIN=312`
- `PO_INBOUND_DOUBLE_COUNT=17`
- SKU-level stock/profit remains blocked where recovered API entries lack approved article/SKU mapping.
- Production release/apply remains blocked until the temp-chain work is reviewed and serialized.

## Reference Artifacts

External Code Captain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Current source-refresh plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/NEXT_WAVE_SOURCE_REFRESH_PLAN_20260504.md`

Current orchestrator review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`

Agent 7 active starter:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/starter_prompts/07_AGENT_7__D1_RESIDUE_CLEANUP_EVIDENCE__SERIAL_TEMP_DB_NO_PROD_APPLY.md`
