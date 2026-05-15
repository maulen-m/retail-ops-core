# Agent 1 Starter: Order-Entry Recovery Evidence Map

Gate: read-only analyst. Do not modify DB, Excel workbooks, source statements, or shared code.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_1_ab_operational_source_refresh_closeout.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_FINAL_REVIEW.md`
7. this starter prompt

## Mission

Build a read-only evidence map for recovering `ORDER_ENTRY_MISSING=15046` without synthesizing item entries.

Use the owner-approved hierarchy:

1. current CRM workbook first;
2. existing closer-to-truth sources next, including API/DB/source backups where available;
3. reserve archive workbook last;
4. quarantine anything unrecovered from real evidence.

Primary current CRM:

`~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`

Reserve archive fallback:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Sales_archive/SALES_KSP_CRM_GPT_Sales_archive.xlsx`

## Required Analysis

1. Identify the current missing-order-entry set from existing gates, DB, or run artifacts.
2. Compare missing order IDs/store/date pairs against the current CRM workbook.
3. Compare remaining missing order IDs against stronger existing sources before using the archive fallback.
4. Compare remaining missing order IDs against the archive workbook.
5. Classify each candidate recovery row by evidence source and confidence.
6. Identify schema mappings needed to populate canonical order-entry truth safely.
7. Produce exact counts by source, store, date range, and recovery status.

## Hard Rules

- Do not infer item entries from order headers or totals.
- Do not guess sizes from names unless the source already contains item-level size evidence and the repo has an approved mapping rule.
- Do not write to `db/app.db`.
- Do not edit CRM/archive workbooks.
- Do not call live external APIs unless the orchestrator explicitly authorizes live reads for your pane.
- If evidence is insufficient, mark the order as unrecovered/quarantined.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_1_order_entry_recovery_evidence_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Sources inspected.
- Commands run.
- Counts recovered from current CRM.
- Counts recoverable from stronger existing sources.
- Counts recoverable only from archive fallback.
- Counts still unrecovered/quarantined.
- Exact proposed Phase 2 apply plan and tests.
