# Agent 3 - PO, Inbound, Supplier Routes, ARC LINE31, And Cargo Handoff Truth

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_3_c3_po_inbound_supplier_routes_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/OWNER_QA_C3_SUPPLIER_LINE31_CONTEXT_20260503_210720_ALMT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/OWNER_QA_OPTION_C_INPUTS_20260503_203849_ALMT.md`
8. this assigned starter prompt.

## Key External Evidence Paths

- PO inquiry repo: `~/Cowork/Projects/E-commerce`
- Supplier communication repo: `~/Cowork/Projects/Sourcing-Research`
- ARC PO1A payment evidence: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Transactions/ARC/PO-1A_28.4.2026`
- LINE31 PO1A supplier messaging evidence: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/15.4.2026_v5/supplier_messaging/2026-04-27_tracy_po1a450_regular_availability_confirmation_images`
- LINE31 PO1A planning workbook: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/15.4.2026_v5/ACMEWEAR_LINE31_PO_Planning_Workbook_2026-04-14_adjusted_reviewed.xlsx`
- LINE31 shortage doc: `~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__LINE31_Shortage.md`
- LINE31 shortage compensation path: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/13.4.26/shortage_compensation`
- AB inbound workbook: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

## Mode

Read-only analyst. Do not edit repo files, `.claude/*`, DB, workbooks, env files, external repos, supplier communications, or external systems. The only allowed write is your assigned closeout.

## Mission

Define the C3 PO/inbound/supplier/cargo event model and source-boundary contract.

Special rule: keep the unresolved initial ARC shortage-dispute route separate from the Tracy PO1A/future order route unless owner explicitly approves a merge.

Cover:

- how AB should consume PO inquiry evidence from E-commerce;
- how AB should consume supplier communication and catalog evidence from Sourcing-Research;
- how AB should represent PO1A currently in preparation and scheduled for supplier-to-Yiwu 525 cargo handoff on `2026-05-04`;
- how AB should represent the February initial LINE31 265-unit mismatch and unresolved shortage dispute;
- how inbound actual received quantities should map from the canonical inbound workbook;
- how cargo arrival, cargo payment, Astana takeover, warehouse receipt, supplier debt, and employee approval should be distinct events;
- what must block PO/cashflow/reorder green status.

## Required Closeout Content

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- absolute paths read and which were missing or stale;
- proposed event types and source-pointer fields;
- route separation risks;
- Agent 7 implementation recommendations and tests;
- confirmation that no repo, DB, env, external repo, supplier, payment, or Web_automation files were modified.
