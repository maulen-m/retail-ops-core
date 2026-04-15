PLAN

Title

- PO State Integrity Gap Closure

Purpose

- Close the remaining PO funding, cash freshness, stock freshness, sales/cashflow freshness, and domain-registry gaps so `Autonomous_business` becomes traceable and decision-grade across finance, inventory, and ops.

Repo

- `~/Docs/Autonomous_business`

Canonical protocol

- `docs/PARALLEL_EXECUTION_PROTOCOL.md`
- skill: `autonomous-business-parallel-rollout`

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `docs/inventory/Sales_Data_Model_V16.md`
- `docs/inventory/INBOUND_CALENDAR_V10_002_PO_PART_TRANSITION_2026-02-07.md`
- `docs/PLAN_INBOUND_FULL_REPO_STATE_SYNC_2026-03-02.md`
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md`

Execution posture

- one write-capable execution agent
- two read-only analyst agents
- fail-closed
- no hidden provenance
- no touching the parallel Google Sheet API / CRM / WhatsApp / import rollout being handled in another track

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_po-state-integrity-gap-closure`

As-of window

- `2026-04-15`

Known evidence at plan start

- Workbook path under review:
  - `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
- Verified from the operating DB:
  - `po_line` count is aligned to workbook `Inbounds_sheet` at the size-line level
  - `po_part` count is aligned to workbook `PO_part_id_Totals` at the part-summary level
  - `po_funding_plan` currently has `0` rows
  - `po_exchanger_allocations` currently has `0` rows
  - `po_funding_allocations` has historical rows but is not, by itself, a complete PO funding truth layer
- Freshness gaps observed:
  - `config/bank_accounts.yaml` is stale versus current business day
  - inventory snapshot facts are stale
  - harmonized sales facts are behind raw Kaspi order truth
  - `fact_cashflow_daily` trails the event spine

Target end state

- PO logistics truth is deterministic and current
- PO funding truth is explicit, current, and traceable
- cash balances are current and imported into cashflow
- stock snapshot is current and anchored
- harmonized sales and cashflow rollups are current
- each owner domain has a visible freshness / provenance registry
- validators can fail closed on stale or missing truth instead of silently drifting

Out of scope

- do not touch the Google Sheet API integration track
- do not touch the CRM / WhatsApp / import rollout track
- do not rewrite adjacent systems just to make them prettier
- do not invent direct DB writes from chat conversations with PO agents

Role split

Agent A

- execution agent
- only writer in the repo
- only agent allowed to mutate `db/app.db`
- reads analyst reports and executes the repair path

Agent B

- read-only analyst
- focus: PO workbook truth, PO funding/payment truth, exchanger/funding gaps, and direct-PO-agent intake path

Agent C

- read-only analyst
- focus: freshness/completeness across cash, stock, sales, cashflow, ops, and the domain-registry / validator surface

First-pass independence rule

- Agent B publishes before reading Agent C
- Agent C publishes before reading Agent B
- Agent A consumes both reports
- second-pass cross-review happens only if Agent A explicitly requests it

Required handoff files

- `README.md`
- `status_board.md`
- `agent_b_report.md`
- `agent_c_report.md`
- `agent_a_execution_log.md`

Launch order

1. Agent B
2. Agent C
3. Agent A after B and C publish first-pass reports

Concrete workstreams

Workstream 1: PO logistics and funding closure

- confirm canonical workbook-to-DB coverage for:
  - `Inbounds_sheet` -> `po_line`, `po_header`
  - `PO_part_id_Totals` -> `po_part`
- identify the exact missing funding surfaces:
  - `po_funding_plan`
  - `po_funding_allocations`
  - `po_exchanger_allocations`
  - any missing cashflow translation of PO funding / delivery payouts
- propose the minimum canonical intake path for direct PO-agent conversations:
  - conversation -> staging registry -> approved promotion -> workbook or DB sync
- forbid “chat message directly edits DB” as a normal path

Workstream 2: Cash and capital freshness closure

- refresh `Cash_Balances` -> `bank_accounts_history.yaml` -> `bank_accounts.yaml` -> balance-check import
- confirm the latest balance snapshot date and the import date inside `fact_cashflow_events`
- identify any currencies / stores / accounts that still rely on ad hoc manual handling

Workstream 3: Stock freshness closure

- identify the current canonical stock workbook / anchor
- refresh the inventory snapshot into DB
- verify inventory value used by capital / dashboard surfaces is built from the refreshed anchor

Workstream 4: Sales and cashflow freshness closure

- determine whether current-day archive/API sales truth is fully translated into the harmonized sales layer
- close the gap between `fact_orders_kaspi`, `fact_sales`, `fact_sales_v16`, `fact_cashflow_events`, and `fact_cashflow_daily`
- ensure the daily rollup is rebuilt after upstream source refresh

Workstream 5: Domain registry and freshness board

- create or extend one visible registry per owner domain:
  - PO / inbound
  - funding / exchanger
  - bank balances / cash
  - stock snapshot
  - sales truth
  - cashflow
  - ops / shipment chronology
- each registry entry must show:
  - source
  - canonical path
  - last_sync
  - as_of
  - validator
  - current status

Execution order for Agent A

1. Read Agent B and Agent C reports.
2. Freeze a baseline in `agent_a_execution_log.md`:
   - current max dates
   - current red/green validators
   - current DB backup path once backup is taken
3. Apply the smallest safe closure sequence:
   - funding / source contract gaps first
   - then cash balance freshness
   - then stock freshness
   - then sales/cashflow rebuild
   - then registry / validator closure
4. After each write path:
   - record command
   - record backup path if DB touched
   - rerun the smallest relevant validator immediately
5. Finish with final repo gates and a concise “remaining blockers or green state” closeout.

Minimum validator set for this rollout

- `python3 scripts/validate_inbound_sheet_consistency.py`
- `python3 scripts/validate_single_truth_system.py`
- `python3 scripts/validate_po_dashboard_invariants.py`
- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_params.py --strict`
- `pytest -q` for any touched scripts/tests
- `scripts/lint_docs.sh` if docs change

Success criteria

- PO part / inbound truth is current and proven against the workbook
- funding / exchanger truth is no longer implicit or missing
- cash balances are current and visible in both config and cashflow
- stock truth is current in DB
- harmonized sales + cashflow daily are rebuilt to current truth
- domain registries exist and make freshness gaps obvious
- final closeout clearly states either:
  - fully green decision-grade state, or
  - the smallest remaining explicit blocker

Stop rules

- analysts do not modify repo state
- execution agent does not start DB mutation before upstream analysis
- no source swap without explicit provenance
- stop if closing this gap would require touching the parallel Google Sheet API / CRM / WhatsApp / import track

Deliverables

- updated repo state only through Agent A
- readable analyst reports in the shared handoff folder
- execution log with commands, backups, and rollback steps
- visible registry / freshness artifacts for the closed domains

Generated from

- `python3 scripts/init_parallel_rollout.py`
- repo `Autonomous_business`
- run dir `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-15_po-state-integrity-gap-closure`
