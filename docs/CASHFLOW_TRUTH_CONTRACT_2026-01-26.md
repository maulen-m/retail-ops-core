End goal

A single, conservative, decision‑grade Treasury + Capital control plane that:

Anchors to bank truth (A1): end‑of‑day statement close as the official “cashflow starts here” (with explicit trust labeling for post‑anchor days).

Maintains an append‑only event ledger for:

Cash movements (multi‑account + multi‑currency)

Inventory at cost, split into on‑hand + inbound + on‑delivery

Commitments (PO payment schedules, OPEX schedule, freight, taxes, etc.)

Produces a daily Cashflow Calendar + a strict PO preflight gate that blocks unsafe POs unless explicitly overridden (capital protection first).

Runs with minimal manual work: daily Kaspi API sync (rolling 14‑day window), deterministic rebuild, and only “as needed” manual balance snapshots.

Uses Kaspi API’s maximum potential: stores the newly captured order metadata and (next) ingests order entries + product metadata so Excel exports are no longer a dependency. 

KASPI_API_WORKFLOW_UPDATE_2026-…

Sales_Data_Model_V16

Your locked “truth contract” (what the system must obey)

I’m treating these as binding system physics:

Anchor: A1 statement EOD close

Decision‑grade horizon: from last statement day

Cash scope: all accounts are business‑usable; transfers are TRACK

Orders→cash: D1 cash-in at DELIVERED (with 14‑day return/refund reversal risk)

Returns policy: commission refunded; delivery cost not refunded

On‑delivery: E1 inventory asset, separate subaccount INVENTORY_ON_DELIVERY_COST

Inventory valuation: F3 hybrid

base cost becomes inventory when paid (cash→inventory)

landed/delivery costs added when paid/known

inventory value includes on‑hand + inbound

OPEX: 2,652,000 KZT/month, schedule is in the OPEX protocol spreadsheet

Preflight cash floor: X months of OPEX + (you also mentioned a practical minimum like 500k KZT)

Stale API sync: block EOD

Must‑be‑green stores for decision‑grade: UNIVERSAL, STOREB, ACMEWEAR

Critical mismatches vs current repo assumptions (fix NOW — capital risk)

These are the places where current docs/code are inconsistent with your answers, and will silently produce bad PO gating if left unchanged:

Receivables vs cash-at-delivered

Current cashflow docs still model delivered orders as receivables first + later “payouts → cash.” 

KASPI_ORDER_CASHFLOW_TRACKING

Plan G45 also explicitly states “sales do NOT instantly become cash,” which contradicts your D1 rule. 

PLAN_G45_G49_CASHFLOW_COMMITMEN…

Current translator code generates SALE_ACCRUED (receivable-like) and PAYOUT_EXPECTED events for completed orders. 

20260126_222657_kaspi_api_workf…

Impact: dashboard can look “green” while the meaning of cash is wrong → capital loss via false affordability.

OPEX commitments are outdated

Current commitments generator references 2,300,000 KZT/month, but your updated OPEX is 2,652,000 KZT/month. 

20260127_013406_repo_context_pa…

Impact: preflight is optimistic by ~352k/month → systematically under-protects cash.

Inventory cost scope mismatch (on‑hand only vs on‑hand+inbound)

Current cashflow plan says inventory cost equals warehouse on-hand at cost. 

PLAN_G40_G44_CASHFLOW_TRUSTED_D…

Your contract requires on‑hand + inbound, and “cash → inventory” at payment time (F3).

Impact: wrong capital picture; commitments/PO timing logic gets skewed.

Architecture recommendation

Build as separate modules with clean boundaries, but execute them in one daily pipeline:

core/sync/ (Kaspi API ingest → DB)

core/cashflow/ (DB → events → daily calendar → preflight)

core/treasury/transfer_ledger/ (FX + Binance/WeChat broker flows + PO payments → normalized ledger)

scripts/run_end_of_day.py orchestrates: sync → rebuild → preflight → exports

This matches the repo’s existing separation patterns and the “deterministic rebuild from DB” design in the cashflow tracking doc (orders sync → translator to events → rebuild daily). 

20260127_013406_repo_context_pa…

Non‑negotiable design rule: Cashflow must not call Kaspi API directly. It must read DB only. That keeps cashflow deterministic and testable even when API is flaky.

Merged execution plan (aiming for 80–90% completion)

This plan assumes: the “Kaspi API workflow update” (new order fields + migration 014) is already merged/committed, as documented. 

KASPI_API_WORKFLOW_UPDATE_2026-…

Phase 0 — Lock the Cashflow Truth Contract into the repo (doc + config)

Problem: docs/code disagree on what “cashflow” means.
Fix: write one canonical contract and make code reference it.

Deliverables:

docs/CASHFLOW_TRUTH_CONTRACT_2026-01-26.md (your A1/D1/E1/F3/OPEX/preflight rules)

Update:

docs/KASPI_ORDER_CASHFLOW_TRACKING.md to reflect D1 cash-in at delivered, and E1 on‑delivery = inventory, not receivable. (Current mapping is receivable/payout based.) 

KASPI_ORDER_CASHFLOW_TRACKING

Plan docs G40–G49: mark old assumptions as superseded or revise the “Kaspi reality” section. 

PLAN_G45_G49_CASHFLOW_COMMITMEN…

Acceptance gates:

Contract is explicit: timezone, anchor, trust labeling, and event categories are unambiguous.

Phase 1 — Update Orders→Cashflow translator to D1 “cash-at-delivered”

Goal: stop modelling receivables for Kaspi if Pay balance is credited on delivery.

Implementation:

Modify core/cashflow/orders_to_cashflow_events.py:

COMPLETED/DELIVERED ⇒ create CASH_IN to the correct Kaspi Pay store account

RETURNED/REFUNDED ⇒ create cash reversal, and ensure delivery fee is not reversed (matches policy). 

KASPI_ORDER_CASHFLOW_TRACKING

SHIPPED/on‑delivery ⇒ no cash, just inventory reclassification (see Phase 3)

Keep receivables columns (for compatibility), but default them to 0 for Kaspi D1 mode (or keep a switch so you can compare).

Add a calibration report:

Compare modeled cash-in totals vs statement credits on statement-backed days; fail if outside your ±5% HARD tolerance.

Acceptance gates:

Deterministic rebuild works end‑to‑end.

Reconciliation checks enforced (HARD) on statement-backed days.

Phase 2 — Commitments realism (OPEX + PO splits) with scenarios

Your V4 plan already sets the right concept: commitments must be scenario-based and preflight must fail if conservative breaches the floor. 

PLAN_G45_G49_CASHFLOW_COMMITMEN…

2A) OPEX

Replace the old “2.3m/month” placeholder generator with an importer from OPEX_protocol_26.01.2026.xlsx.

Generate commitments by schedule type:

“monthly”: post on the specified day-of-month

“daily”: allocate by day (or treat as a daily recurring commitment)

Keep loan commitments until their end dates (you noted Gold loans end after 2026‑07‑25).

2B) PO payment schedule truth

Update PO plan to reflect:

PO‑4.1: 20,500 CNY already paid on 2026‑01‑22

remaining payments: flexible window until 2026‑03‑10

Represent uncertainty as scenarios:

BASE: expected payment dates

CONSERVATIVE: earliest plausible payment dates + extra buffer

2C) Cash floor

Recommendation (capital-protective):

BASE floor: 1.0× monthly OPEX

CONSERVATIVE floor: 1.15× monthly OPEX, effective 2026-07-02 by
`config/owner_decisions/opex_loans_floor_refresh_2026_07_02.json`.

plus absolute minimum cash (e.g., 500k KZT)

Preflight gate uses CONSERVATIVE by default.

Acceptance gates:

Preflight fails if conservative drops below floor.

Commitments table shows next payments (OPEX + PO) clearly.

Phase 3 — Inventory-at-cost ledger: on-hand + inbound + on-delivery (E1 + F3)

Goal: inventory becomes a balance-sheet engine, not a fragile snapshot.

Implementation:

Track separate inventory accounts:

INVENTORY_ON_HAND_COST

INVENTORY_INBOUND_COST

INVENTORY_ON_DELIVERY_COST (you explicitly want this)

Anchor inventory values from the latest snapshot ≤ anchor date, but include inbound.
(Inventory SQL already computes inbound and on-hand value separately: inbound_stock * COGS_unit and current_stock * COGS_unit.) 

20260127_013406_repo_context_pa…

Daily movements (post-anchor):

PO payment (base cost) ⇒ cash decreases; inbound inventory increases (F3)

Freight/landed payment ⇒ increases inventory cost when paid/known (F3)

PO arrival ⇒ move inbound → on-hand (no cash)

SHIPPED ⇒ move on-hand → on-delivery

DELIVERED ⇒ move on-delivery → COGS (and cash-in happens in Phase 1)

RETURN ⇒ reverse cash-in; reverse COGS back into on-hand (delivery fee stays as expense/cost)

Acceptance gates:

Inventory accounts never go negative.

Sum of inventory accounts reconciles to snapshot within tolerance on statement-backed days (or explicitly mark “modelled inventory” post-anchor).

Phase 4 — Integrate the Transfer Ledger for maximum automation (Binance/USDT → supplier CNY)

This is already a major asset in the repo: the transfer ledger is designed as an immutable, normalized ledger, with import scripts for Binance P2P/withdrawals and exchanger emails, and explicit FX capture. 

20260127_013406_repo_context_pa…

What to do:

Build a translator: transfer_ledger_entries → fact_cashflow_events

internal transfers (Kaspi Pay → Gold → Universal) become cash reclass events

Binance conversions and supplier payments become cash-out + (for PO base cost) inventory inbound increases

Link transfer ledger entries to PO IDs (commitment_id / reference_id) so PO funding becomes auditable.

Acceptance gates:

Idempotent imports (safe to rerun).

No double counting between statements and transfer ledger.

Phase 5 — Kaspi API enrichment: order entries + product dims (the big automation unlock)

You now have order-level metadata captured (delivery_mode, payment_mode, delivery_cost_for_seller, approved_by_bank_date, etc.). 

KASPI_API_WORKFLOW_UPDATE_2026-…


Next step is line-item truth:

The API response model supports entries and provides relationships to orderentries, and those entries include attributes like quantity, totalPrice, weight, basePrice, deliveryCost, category, etc. 

20260126_222657_kaspi_api_workf…

Implement:

fact_order_entries_kaspi

dim_masterproduct, dim_merchantproduct, dim_point_of_service

Strategy to avoid fragility:

Make enrichment optional (--enrich-entries flag / env var)

Fetch entries only for new/changed orders

Cache dims by ID to avoid repeated API calls

Fail-open for enrichment (warn + continue), but keep the core orders sync strict.

Acceptance gates:

Core sync is unaffected by enrichment failures.

Multi-line orders no longer get misrepresented as quantity=1 at order-level.

Phase 6 — Auto-generate Fact_Sales (V16) from API (eliminate Excel dependency)

Fact_Sales V16’s declared grain is order line (OrderID × SKU_ID × Store). 

Sales_Data_Model_V16


That aligns perfectly with orderentries.

Deliverables:

A deterministic builder that outputs Fact_Sales using:

order entry quantity, offer code/name, and merchantProduct mapping for SKU_key

delivery fee from matrix (v8) and/or compare vs API delivery_cost_for_seller

Net_rev_unit formula is already specified in V16. 

Sales_Data_Model_V16

Acceptance gates:

Fact_Sales matches V16 schema and reconciles to known totals.

Multi-line/multi-qty correctness is fixed permanently.

Phase 7 — “10% safety margin” optional upgrades

These are valuable but not required to reach 80–90% completion:

Additional analytics using new fields:

SLA: planned vs actual delivery dates

returns risk profiling using returned_to_warehouse, express 

KASPI_API_WORKFLOW_UPDATE_2026-…

Kaspi Goods API automation (price/stock/product upload) — powerful but introduces more operational risk; keep behind explicit enablement. 

20260126_222657_kaspi_api_workf…

Execute cashflow and API parts separately or together?

Separate modules, executed together is the optimal tradeoff:

Separate modules:

fewer coupling bugs

deterministic cashflow rebuild

testability and rollback safety

Executed together daily:

your post-anchor cashflow depends on fresh order lifecycle states (14‑day rolling capture requirement) 

KASPI_ORDER_CASHFLOW_TRACKING

Daily pipeline order (recommended):

Kaspi orders sync (strict; block EOD if required stores stale)

Optional order-entry enrichment (fail-open)

Transfer ledger imports (Binance/exchanger)

Cashflow rebuild (events → daily calendar)

Preflight gate (conservative scenario)

Exports / dashboards
