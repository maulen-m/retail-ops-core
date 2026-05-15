# Reviewed Agent Prompt: LINE31 PO1A / Olive Green Ingest

Status: reviewed prompt, not launched.

Use this for a single execution agent after the owner/orchestrator explicitly launches the LINE31 PO/inbound lane.

## Prompt

Read `~/Docs/Autonomous_business/AGENTS.md`, `~/Docs/Autonomous_business/docs/00_START_HERE.md`, `.claude/OPERATING.md`, and the relevant workbook/PO safety docs before editing.

Your task is to ingest the LINE31 PO1A / Olive Green preorder handoff into Autonomous Business as planned/inbound purchase-order state only.

Primary handoff:

`~/Cowork/Projects/Sourcing-Research/docs/agent_handoffs/LINE31_PO1A_OLIVE_GREEN_PREORDER_AUTONOMOUS_BUSINESS_INGEST_HANDOFF__2026-05-04.md`

Target repo:

`~/Docs/Autonomous_business`

Target external workbook:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

## Required Business Truth

Preserve the original `450`-set paid PO1A as historical/audit truth.

Represent current operational state as:

- `338` non-Olive LINE31 sets on a near-dispatch ready-stock route;
- `242` Olive Green exact-color preorder/production sets;
- provisional `15`-day preparation timing from supplier-confirmed production start;
- no current received stock;
- no current active sellable stock.

Do not create a placed/paid PO1B supplier order beyond the internal Olive Green planning quantity unless a later owner-approved source explicitly authorizes it.

## Workbook Safety

Before any workbook edit, create a timestamped GMT+5 backup of:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Backup name format:

`Inbound_calendar_V10.002__backup_before_line31_po1a_olive_split__YYYYMMDD_HHMMSS_GMT5.xlsx`

Preserve workbook sheet names, required headers, formulas, and existing row-level historical truth. Do not reorder existing machine-read columns.

If workbook schema is ambiguous, stop after backup plus read-only report and ask the orchestrator/owner before writing.

## DB Safety

If DB changes are required:

- back up `~/Docs/Autonomous_business/db/app.db` first;
- use dry-run first;
- require explicit write-enable env gates for apply;
- record backup path and rollback command in closeout.

Do not mark any LINE31 units as received or current sellable stock unless Autonomous Business has separate receipt/warehouse/QC evidence.

## Expected Work

1. Read the LINE31 handoff and cited source paths.
2. Inspect current workbook sheets and DB PO/inbound schema read-only.
3. Decide whether the workbook can safely represent the two operational routes without corrupting historical paid PO1A truth.
4. If safe, update planned/inbound state only.
5. If not safe, write a blocked report with exact missing schema/owner decisions.
6. Update repo mutable state files only as required by repo contract.

## Required Closeout

Write the closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_owner_decisions_source_refresh_followup/line31_po1a_olive_green_ingest_closeout.md`

Closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- READCHECK;
- workbook backup path;
- exact sheets/rows/columns inspected and changed;
- DB backup path if DB was touched;
- proof that LINE31 was represented as planned/inbound/preorder only, not current stock;
- any blocked or ambiguous workbook fields;
- validation commands run;
- rollback steps;
- explicit statement whether owner publication remains blocked.
