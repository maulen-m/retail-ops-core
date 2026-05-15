# Owner QA Context - C3 Supplier, LINE31, PO, And Wiki Boundaries

Captured at: `2026-05-03 21:07:20 +05`

Repo: `~/Docs/Autonomous_business`

Purpose: preserve owner-provided context required for the C3 autonomous operating-system completion plan. This file is evidence for read-only Wave 1 agents and must not be treated as a formula authority. If formulas or business rules change, update the owning docs first.

Secret handling: do not copy credentials, tokens, cookies, passwords, QR/payment credentials, or private chat/session secrets into repo files, reports, tests, or evidence packs.

## Source Boundary Truth

- Purchase-order inquiry generation for suppliers lives in `~/Cowork/Projects/E-commerce`.
- Supplier communication, negotiation history, supplier product catalogs, supplier inventory data, and related supplier context live in `~/Cowork/Projects/Sourcing-Research`.
- Overall business memory wiki: `~/Docs/Oracle/knowledge-workspace/wikis/business-wiki`.
- Commerce operations memory wiki: `~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki`.
- Finance/executive memory wiki: `~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki`.
- Autonomous_business should consume durable evidence pointers, normalized events, freshness, lineage, and gates. It should not become the owner of all raw supplier chat, catalog, or wiki memory.

## Current ARC LINE31 PO1A Context

- Recent ARC supplier PO for LINE31 women clothes was paid/created around `2026-04-30`.
- Payment/check evidence path: `~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Transactions/ARC/PO-1A_28.4.2026`.
- Procurement evidence path: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/15.4.2026_v5/supplier_messaging/2026-04-27_tracy_po1a450_regular_availability_confirmation_images`.
- PO planning workbook: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/15.4.2026_v5/ACMEWEAR_LINE31_PO_Planning_Workbook_2026-04-14_adjusted_reviewed.xlsx`.
- Current owner status: PO1A is in supplier preparation.
- Current owner schedule: PO1A is scheduled to be shipped from supplier to the Chinese Yiwu warehouse of cargo company `525` on `2026-05-04`.

## Prior ARC LINE31 Shortage Dispute

- Around February 2026, the initial LINE31 ARC purchase order was received as `265` units/sets, but the supplier sent different items, colors, or sizes from what was actually ordered.
- Relevant shortage document: `~/Cowork/Projects/E-commerce/docs/inventory/products/LINE31_sales__LINE31_Shortage.md`.
- Relevant shortage compensation path: `~/Cowork/Projects/E-commerce/docs/Purchase_orders/Products/LINE31/13.4.26/shortage_compensation`.
- The shortage dispute remains unresolved and is still being negotiated with the initial ARC supplier manager.

## Route Separation Rule

- PO1A and future ARC LINE31 purchase orders are routed through Tracy.
- Tracy should remain isolated from the old shortage dispute route because she does not know about that dispute and that separation is currently in the business interest.
- The initial shortage dispute route and Tracy route must not be merged into one supplier communication state unless the owner explicitly approves.

## C3 Integration Implication

- C3 must model PO/inbound/supplier evidence as source-referenced, route-aware, and effective-dated.
- PO inquiry, supplier communication, supplier shipment, cargo handoff, Astana receipt, warehouse QC, payment, debt, and shortage/dispute state are separate event types.
- Decision-grade PO/cashflow/reorder output must fail closed if the event chain is stale, missing, route-conflicted, or unsupported by evidence.
