# Agent913 MVOS Source Acquisition And Source Contract Wave

Created: 2026-05-19 10:18 +05

## Purpose

Implement CodeCaptain's `YELLOW_OPERATIONAL_SOURCE_REFRESH_NEXT` recommendation after Agent9125 without forcing a fake green proof.

Agent9125 improved the copied-temp board, but the proof remains `YELLOW_RETAINED_BLOCKER_BOARD_PROOF` because stock, sales, ads, and PO/single-truth blockers are still real. Agent913 is the source-acquisition and source-contract wave that prepares the exact next materialization route before any Agent914 copied-temp proof rerun.

## Human Approval

The owner approved Agent913 MVOS source-acquisition and source-contract wave in Autonomous_business.

Allowed:

- read-only analysis;
- copied-temp-only planning/proofs;
- local evidence generation;
- source packet requirement docs;
- source contract drafts;
- focused tests;
- closeouts;
- reading existing local evidence and repos needed for stock, sales, ads, and PO/single-truth routing.

Forbidden:

- production DB writes;
- workbook writes;
- scheduler/LaunchAgent/cron changes;
- source-pointer writes;
- Web_automation writes;
- Kaspi/API/WebUI writes;
- external writes;
- ad-platform writes;
- cash movement;
- supplier payment;
- PO commitment;
- stock changes;
- price changes;
- owner publication;
- production preflight;
- production apply.

This approval does not authorize live external source fetches. If an agent determines that live Kaspi/API/WebUI/ad-platform reads are required, it must stop `YELLOW` with an exact required approval phrase instead of performing the fetch.

## Inputs

- CodeCaptain answer:
  - `~/Docs/Oracle/Autonomous_business/2026-05-19/001205_TASK-000_mvos-agent9125-yellow-retained-blocker-codecaptain/Answer/Code_captain_19.05.2026_10_02_24.md`
- Agent9125 orchestrator review:
  - `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/ORCHESTRATOR_REVIEW_AFTER_AGENT9125.md`
- Agent9125 closeout:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_closeout.md`
- Agent9125 evidence root:
  - `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9125_combined_copied_temp_rerun_evidence`
- Current source contract registry:
  - `~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts`

## Current Board

Fresh copied-temp child sources:

- `src_ab_db_order_entry_truth`
- `src_ab_db_cashflow_truth`
- `src_ab_db_order_status_truth`

Retained stale/blocking child sources:

- `src_ab_db_stock_truth`: stale at `2026-05-04`
- `src_ab_db_sales_truth`: stale at `2026-05-04`
- `src_ab_db_ads_truth`: stale at `2026-05-17` for strict May 18 gate

PO/single-truth blockers:

- `validate_po_dashboard_invariants.py` fails on stale stock snapshot;
- `validate_po_money_gate.py` still fails `inbound_sheet_consistency`, `single_truth_system`, `cogs_integrity`, and `single_truth_alignment`;
- `validate_single_truth_system.py` still fails retained DB/workbook part-history, PO-4.0 total/weight, and PO-5.2/PO-6 base-payment mismatches.

Accepted owner fact:

- Line61 shortage is settled and should not be re-asked:
  - ordered/cargo `115`;
  - actual received `92`;
  - shortage `23`;
  - XL `7`, 2XL `5`, 3XL `6`, 4XL `5`.

## Execution Split

Parallel root group `agent913_root`:

1. Agent9131: stock source packet route.
2. Agent9132: sales fact v2 source packet route.
3. Agent9133: ads May 18 or T-1 contract route.
4. Agent9134: PO/single-truth canonical refresh route.

Gated after root review:

5. Agent9135: source route synthesis and Agent914 readiness matrix.

## Agent9131: Stock Source Packet Route

Goal:

- Determine whether an accepted local fresh source exists for `fact_inventory_snapshot_size` and `stock_ledger` at or beyond the validator cutoff.
- If not, define the exact stock source packet requirements and keep `src_ab_db_stock_truth` blocked.

Required outputs:

- `STOCK_SOURCE_PACKET_REQUIREMENTS_20260518.md`
- `STOCK_SOURCE_ROUTE_MATRIX.tsv`
- closeout with `Gate: GREEN`, `YELLOW`, or `RED`

Green means:

- a concrete local accepted packet route exists, with source path, SHA, row count, capture/as-of time, SKU-size identity, store scope, stock categories, and target-table mapping; or
- no packet exists but the retained blocker is precisely documented and ready for synthesis without ambiguity.

Yellow means:

- source route is incomplete, a live read is required, or there is conflicting local evidence.

Red means:

- boundary violation, false freshness, source invention, or protected-surface mutation.

## Agent9132: Sales Fact V2 Source Packet Route

Goal:

- Determine whether an accepted local strict sales/SKU identity source exists for rebuilding `sales_fact_v2` beyond `2026-05-04`.
- If not, define exact sales source packet requirements and keep `src_ab_db_sales_truth` blocked.

Required outputs:

- `SALES_FACT_V2_SOURCE_PACKET_REQUIREMENTS_20260518.md`
- `SALES_FACT_V2_SOURCE_ROUTE_MATRIX.tsv`
- closeout with `Gate: GREEN`, `YELLOW`, or `RED`

Green means:

- a concrete local accepted packet route exists for strict rebuild, including order/store line identity, SKU mapping source, status eligibility, quantity, source SHA, and quarantine policy; or
- no packet exists but the retained blocker is precisely documented and ready for synthesis without ambiguity.

## Agent9133: Ads May 18 Or T-1 Contract Route

Goal:

- Decide whether a local May 18-covering ads source packet exists.
- If not, draft a non-authorizing `ADS_T_MINUS_1_DAILY_SCOPE_FOR_COPIED_TEMP_ONLY` contract option.

Required outputs:

- `ADS_MAY18_OR_T_MINUS_1_SCOPE_DECISION.md`
- `ADS_SOURCE_ROUTE_MATRIX.tsv`
- closeout with `Gate: GREEN`, `YELLOW`, or `RED`

Contract must preserve:

- May 17 ads coverage cannot support May 18 same-day ad-spend decisions;
- missing ads rows are not zero spend;
- owner publication remains blocked unless the publication surface explicitly uses T-1 ads scope.

## Agent9134: PO/Single-Truth Canonical Refresh Route

Goal:

- Preserve the Line61 accepted-shortage fact.
- Identify the exact canonical workbook/DB refresh required for retained PO and single-truth mismatches.
- Do not claim PO money gate green.

Required outputs:

- `PO_SINGLE_TRUTH_CANONICAL_REFRESH_PLAN.md`
- `LINE61_ACCEPTED_SHORTAGE_CLASSIFICATION_LOCK.md`
- `PO_SINGLE_TRUTH_BLOCKER_MATRIX.tsv`
- closeout with `Gate: GREEN`, `YELLOW`, or `RED`

Must cover:

- retained part-history gaps;
- PO-4.0 total/weight mismatch;
- PO-5.2/PO-6 base-payment mismatches;
- `inbound_sheet_consistency`;
- `single_truth_system`;
- `cogs_integrity`;
- `single_truth_alignment`.

## Agent9135: Synthesis And Agent914 Readiness

Launch only after root closeouts are reviewed.

Goal:

- Combine the four source routes into a single readiness board.
- Decide whether Agent914 can run copied-temp materialization/proof.
- List exact child sources still blocked and validators to rerun.

Required outputs:

- `NEXT_COPIED_TEMP_GREEN_PROOF_READINESS_MATRIX.tsv`
- `STOPLINE_MATRIX.tsv`
- `AGENT914_BOOTSTRAP_RECOMMENDATION.md`
- closeout with `Gate: GREEN`, `YELLOW`, or `RED`

Green means:

- Agent914 can safely run a copied-temp materialization/proof using only accepted local source routes/contracts.

Yellow means:

- one or more source routes remain unresolved but are correctly retained.

Red means:

- any authority boundary was violated or false-green route proposed.

## Stoplines

Stop `RED` if:

- production DB is mutated;
- workbook is mutated;
- scheduler/source-pointer/external system is mutated;
- source packet missing required SHA or row count is accepted as fresh;
- stock packet lacks SKU-size identity;
- sales packet lacks SKU mapping source;
- missing ads rows are treated as zero;
- PO money gate is greened solely from Line61 accepted shortage;
- owner publication or production preflight is implied.

Stop `YELLOW` if:

- a required source packet cannot be found locally;
- a live read-only external fetch would be needed;
- CodeCaptain/owner clarification is needed before materialization;
- validators or local evidence conflict.

## Non-Authorization

This plan does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, cash movement, supplier payment, PO commitment, stock changes, price changes, owner publication, production preflight, production apply, or treating copied-temp evidence as production truth.
