PROMPT_AGENT_B

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/parallel_runs/2026-04-15_po-state-integrity-gap-closure/PLAN.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-15_po-state-integrity-gap-closure`

Your role

- read-only analyst
- focus: PO workbook truth, PO funding/payment truth, exchanger/funding gaps, and the direct-PO-agent intake path

Your job

- prove what is already loaded into DB from `Inbound_calendar_V10.002.xlsx`
- prove what funding / exchanger / payout surfaces are still missing or incomplete
- define the minimum safe canonical intake path for future PO-agent conversations

Required sources to inspect

- `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`
- `scripts/sync_po_parts_from_inbound_calendar.py`
- `scripts/import_inbound_total_excel.py`
- `scripts/import_po_inbound_xlsx.py`
- `docs/inventory/INBOUND_CALENDAR_V10_002_PO_PART_TRANSITION_2026-02-07.md`
- `docs/inventory/Sales_Data_Model_V16.md`
- `db/app.db` read-only

Questions you must answer

1. Which PO/inbound/payment fields are already covered by:
   - `po_header`
   - `po_part`
   - `po_line`
2. What is still missing from:
   - `po_funding_plan`
   - `po_funding_allocations`
   - `po_exchanger_allocations`
   - `fact_cashflow_events`
3. What is the correct canonical path for future PO-agent conversations?
4. What is the minimum write sequence Agent A should run to close the gap without widening scope?

Rules

- do not modify repo files
- do not mutate the DB
- do not read Agent C's report before publishing your own first-pass findings

Output

- write findings to `agent_b_report.md`
- keep findings concise, source-backed, and actionable for Agent A
- include exact commands Agent A should run first
