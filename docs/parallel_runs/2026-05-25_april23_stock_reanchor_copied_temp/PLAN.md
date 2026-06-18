# April 23 Stock Re-Anchor Copied-Temp Execution Plan

Created: `2026-05-25 14:43 +0500`
Repo: `~/Docs/Autonomous_business`
Mode: `read-only and copied-temp only`
Gate before launch: `YELLOW_ACCEPT_TO_START_NONPRODUCTION_APRIL23_REANCHOR_LANE_ONLY`

## Purpose

The human owner corrected the inventory basis on `2026-05-25`: the April 23 stock workbook is the latest real owner-approved physical stock anchor for this rebuild lane. The May 25 workbook that used the later `2026-05-04` DB stock anchor is now a format/reference artifact only, not the authority for this re-anchor.

This plan converts Code Captain's `2026-05-25 13:22:05` answer into a repo-executable non-production lane. The lane must prove the April 23 anchor, replay source-backed post-anchor movements through `2026-05-25`, generate review-only workbooks, and package evidence for review. It must stop before production apply, production preflight, dashboard publication, PO commitment, merchant stock changes, or any external action.

## Source References

Code Captain answer:

`~/Docs/Oracle/Autonomous_business/2026-05-25/125117_TASK-000_CaptainRequestEvaluation_april23_stock_reanchor_execution_plan/Answer/Code Captain_25.05.2026_13_22_05.md`

Owner-approved anchor workbook:

`~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx`

Format-reference inventory eval workbook:

`~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/inventory_business_eval_tables_2026-04-23.xlsx`

Superseded May 25 DB-anchor estimate, format reference only:

`~/Downloads/Autonomous_business_stock_assets/20260525_110409_warehouse_stock_count_and_estimate/01_ESTIMATED_CURRENT_STOCK_VALUATION_20260525.xlsx`

## Authority Boundary

Authorized by owner on `2026-05-25`:

- repo documentation for the execution plan;
- copied-temp source-contract planning;
- starter/handoff creation;
- read-only source inspection;
- local evidence generation;
- copied-temp DB/materialization proof planning;
- validator planning and execution on copied-temp artifacts;
- review packet preparation.

Not authorized:

- production DB writes;
- workbook mutation;
- source-pointer writes;
- scheduler, LaunchAgent, or cron changes;
- Web_automation changes;
- Kaspi/API/WebUI writes;
- ad-platform writes;
- merchant stock changes;
- price changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- downstream dashboard publication;
- production preflight;
- production apply.

## Canonical Decision

Use `Current_Stock_Rebuild` from the April 23 workbook as the canonical April 23 SKU-size anchor surface for this lane.

Replay quantity basis:

- anchor quantity column: `estimated_current_stock`;
- anchor date: `2026-04-23`;
- anchor boundary assumption: `2026-04-23 EOD +05`, unless a later source proves a more precise timestamp;
- replay window: `2026-04-24 00:00:00+05` through `2026-05-25 23:59:59+05`.

Do not use `Composed_Anchor_SKU_Size.anchor_qty` as the final current-stock quantity. It is support/provenance, not the final post-movement stock surface.

## Required Contract Addendum

This lane is governed by:

`~/Docs/Autonomous_business/docs/contracts/mvos_source_contracts/APRIL23_STOCK_ANCHOR_OWNER_APPROVED_FOR_REANCHOR_COPIED_TEMP_20260525.md`

Required contract ID:

`APRIL23_STOCK_ANCHOR_OWNER_APPROVED_FOR_REANCHOR_COPIED_TEMP_20260525`

The addendum must preserve:

- `production_use_allowed=false`;
- `owner_publication_authority=false`;
- `row_risk_flags_preserved=true`;
- `blocked_rows_remain_blocking=true`;
- `offer_availability_is_not_physical_stock=true`.

## Phase 1 - Read-Only Anchor And Source Audit

Goal: prove the April 23 workbook can be used as a controlled anchor input and identify replay source gaps before any copied-temp replay.

Inputs:

- April 23 stock anchor workbook;
- April 23 inventory eval workbook;
- May 25 valuation workbook as format reference;
- May 25 source manifest and deduction CSVs;
- `AGENTS.md`;
- `docs/00_START_HERE.md`;
- `docs/inventory/Master_Inventory_Rules_v9.md`;
- `docs/inventory/Sales_Data_Model_V16.md`;
- `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`;
- active source-contract registry.

Outputs:

- `APRIL23_REANCHOR_SOURCE_MANIFEST.json`;
- `APRIL23_ANCHOR_SCHEMA_AUDIT.json`;
- `APRIL23_ANCHOR_ROW_PROFILE.tsv`;
- `APRIL23_SUPPORT_SHEET_AUDIT.md`;
- `POST_ANCHOR_SOURCE_GAP_REPORT.md`.

Stoplines:

- expected workbook sheet or column is missing;
- anchor workbook SHA differs from approved source without an owner explanation;
- duplicate `stock_id`;
- duplicate `sku_key + my_size` anchor key;
- non-numeric anchor quantities not quarantined;
- evidence that the approved workbook was mutated after approval;
- post-anchor replay window cannot be source-covered or explicitly retained.

Expected gate:

- `YELLOW_ANCHOR_AUDIT_READY`; or
- `RED_ANCHOR_SCHEMA_STOP`.

## Phase 2 - Anchor Normalization

Goal: normalize `Current_Stock_Rebuild` into deterministic CSV inputs without losing row-level risk.

Outputs:

- `april23_anchor_normalized.csv`;
- `april23_anchor_audit.csv`;
- `april23_anchor_quarantine_seed.csv`;
- `APRIL23_ANCHOR_NORMALIZATION_REPORT.md`.

Required fields:

- `anchor_as_of_date`;
- `anchor_boundary_semantics`;
- `sku_key`;
- `my_size`;
- `stock_id`;
- `base_anchor_qty_raw`;
- `anchor_qty_decision_sellable`;
- `anchor_source`;
- `anchor_surface_type`;
- `confidence_score`;
- `confidence_band`;
- `promotion_status`;
- `risk_flags`;
- `cogs_kzt`;
- `cogs_status`;
- `row_status`;
- `quarantine_reason`;
- `provenance`.

Stoplines:

- row totals change without an audit explanation;
- `BLOCKED` rows become PO-safe;
- negative rows are silently clamped;
- missing COGS is set to zero;
- support-sheet anchor quantities replace `estimated_current_stock`.

Expected gate:

- `YELLOW_ANCHOR_NORMALIZED_WITH_RETAINED_RISK`; or
- `GREEN_ANCHOR_NORMALIZED_NO_SCHEMA_BLOCKERS`.

## Phase 3 - Post-Anchor Depletion Extraction And Ranking

Goal: build identity-bearing movement rows for `2026-04-24..2026-05-25`.

Source ranking:

1. DB stock ledger physical-out events with identity and source.
2. API raw order entries with entry IDs and quantity.
3. WebUI ArchiveOrders lifecycle/status for `status_change_at` and terminal statuses.
4. DB order facts with exact SKU/size and lifecycle.
5. CRM workbook rows with exact `SKU_ID` or `MY_SIZE`, only when lifecycle is source-backed.
6. May 25 deduction audit for reconciliation and format, not canonical authority.

Outputs:

- `post_anchor_depletion_candidates.csv`;
- `post_anchor_depletion_ranked.csv`;
- `post_anchor_unmatched_or_quarantined.csv`;
- `POST_ANCHOR_SOURCE_RANKING_DECISION.md`;
- `POST_ANCHOR_REPLAY_WINDOW_COVERAGE.json`.

Stoplines:

- missing replay coverage for `2026-04-24..2026-05-25`;
- rows deducted only from CRM text without identity;
- missing sizes deducted at SKU-size grain;
- cancelled or returned rows added back without return-QC;
- stale ArchiveOrders CSV treated as current-window evidence.

Expected gate:

- `YELLOW_REPLAY_SOURCE_GAPS_VISIBLE`; or
- `GREEN_REPLAY_SOURCE_COVERAGE_READY`.

## Phase 4 - Copied-Temp Replay And Stock/COGS Rebuild

Goal: replay ranked movements against the April 23 normalized anchor in a copied DB or isolated evidence folder only.

Outputs:

- `april23_reanchored_stock_rows.csv`;
- `april23_reanchor_deduction_lines.csv`;
- `april23_reanchor_unmatched_deductions.csv`;
- `april23_reanchor_quarantine_blockers.csv`;
- `april23_reanchor_by_sku_value.csv`;
- `APRIL23_REANCHOR_COPIED_TEMP_PROOF.json`;
- `COPIED_DB_BOUNDARY_SHA256.tsv`.

Stoplines:

- production DB touched;
- copied DB SHA not recorded;
- replay is not idempotent;
- negative rows are hidden;
- row count mismatch is unexplained;
- missing COGS is valued as zero.

Expected gate:

- `COPIED_TEMP_GREEN_PROOF_FOR_REANCHOR_SCOPE_ONLY`; or
- `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

## Phase 5 - Review-Only Workbook Generation

Goal: produce the two requested Excel artifacts in an isolated output folder.

Stock and COGS workbook sheets:

- `Summary`;
- `Estimated_Stock`;
- `By_SKU_Value`;
- `Deduction_Lines`;
- `Unmatched_Deductions`;
- `Sources`;
- `Quarantine_Blockers`;
- `Anchor_Audit`.

Inventory business evaluation workbook sheets:

- `Executive_Summary`;
- `SKU_Key_Totals`;
- `Financial_Allocations`;
- `OOS_Size_Count_By_SKU_Key`;
- `OOS_Size_Detail`;
- `Retained_Blockers`;
- `COGS_Exposure`.

Required banners:

- `COPIED_TEMP_REVIEW_ONLY`;
- `NOT_PHYSICAL_RECOUNT`;
- `NO_PRODUCTION_DB_WRITE`;
- `NO_PO_COMMITMENT`;
- `NO_MERCHANT_STOCK_CHANGE`;
- `RETAINED_BLOCKERS_VISIBLE`.

Stoplines:

- output overwrites protected live workbook;
- quarantine is hidden;
- missing COGS included as zero;
- totals do not reconcile to source CSVs;
- source dates and warnings are omitted.

Expected gate:

- `YELLOW_OUTPUTS_REVIEW_READY`; or
- `GREEN_OUTPUT_WORKBOOK_CONTRACT_PASS`.

## Phase 6 - Validators And Regression

Goal: prove the copied-temp re-anchor did not corrupt sales, stock, COGS, PO, or owner surfaces.

Use the validator matrix:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`

Outputs:

- `VALIDATOR_EXIT_MATRIX.tsv`;
- `RETAINED_BLOCKER_BOARD.md`;
- `APRIL23_REANCHOR_VALIDATOR_SUMMARY.md`.

Stoplines:

- any required validator fails;
- required validator is missing and hand-waived;
- retained blocker affects a claimed green surface;
- source freshness is red for a claimed publication surface.

Expected gate:

- `COPIED_TEMP_GREEN_PROOF_FOR_REANCHOR_SCOPE_ONLY`; or
- `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`.

## Phase 7 - CodeCaptain And Owner Review Packet

Goal: package evidence for decision only, not production apply.

Required files:

- `APRIL23_REANCHOR_DECISION_SUMMARY.md`;
- `APRIL23_REANCHOR_SOURCE_MANIFEST.json`;
- `APRIL23_ANCHOR_SCHEMA_AUDIT.json`;
- `POST_ANCHOR_SOURCE_RANKING_DECISION.md`;
- `APRIL23_REANCHOR_REPLAY_POLICY.md`;
- `APRIL23_REANCHOR_QUARANTINE_MATRIX.tsv`;
- `VALIDATOR_EXIT_MATRIX.tsv`;
- rebuilt workbooks;
- SHA256 file;
- delta comparison vs April 23 and May 25;
- owner approval phrase request;
- stopline log.

Expected gate:

`CODECAPTAIN_REVIEW_PACKET_READY_NONPROD_ONLY`

## Phase 8 - Future Production Apply, Not Authorized

This plan does not authorize Phase 8.

Production re-anchor discussion requires:

- copied-temp proof completed;
- all relevant validators passing or retained blockers explicitly accepted;
- CodeCaptain review;
- fresh production DB/workbook SHA;
- DB integrity check;
- holder check;
- backup path/SHA/integrity;
- rollback command;
- exact dry-run diff;
- write-command manifest;
- exact owner approval phrase;
- post-apply validation matrix;
- release anchor.

Expected gate until then:

`NO_PRODUCTION_APPLY_AUTHORIZED`

## Human Questions To Ask Only If Blocked

1. Should `2026-04-23 EOD +05` be accepted as the anchor boundary if no timestamp exists?
2. Is there a fresh return-QC or warehouse-return source for rows that would otherwise be returned-to-stock?
3. Should any named `BLOCKED`, negative, or missing-COGS high-value rows be reviewed manually?
4. Should production policy review be requested after copied-temp proof?

Do not ask the owner to resolve rows that source evidence can resolve, bless missing COGS as zero, or approve PO/stock actions from a review workbook.
