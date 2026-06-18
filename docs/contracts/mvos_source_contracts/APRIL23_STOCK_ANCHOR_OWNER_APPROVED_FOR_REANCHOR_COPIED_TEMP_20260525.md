# APRIL23_STOCK_ANCHOR_OWNER_APPROVED_FOR_REANCHOR_COPIED_TEMP_20260525

Status: active copied-temp source contract.

Created: `2026-05-25 14:43 +0500`

Accepted by:

- Human owner correction on `2026-05-25`;
- Code Captain `2026-05-25 13:22:05` review.

## Purpose

This contract records the April 23 stock workbook as the latest real owner-approved physical stock anchor for the April 23 re-anchor copied-temp lane.

It supersedes the May 25 DB-anchor estimate only for this non-production proof lane. It does not create production inventory policy, owner-publication truth, PO authority, merchant stock authority, or dashboard publication authority.

## Anchor Source

Workbook:

`~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx`

Approved workbook SHA256 from Code Captain:

`2474f3834784dc1c8368fd919a81800124e59eccba34fde15129c4d70e937ca2`

Canonical sheet:

`Current_Stock_Rebuild`

Canonical quantity column:

`estimated_current_stock`

Anchor date:

`2026-04-23`

Boundary assumption:

`2026-04-23 EOD +05`

Replay window:

`2026-04-24 00:00:00+05` through `2026-05-25 23:59:59+05`

## Required Handling

The lane must preserve:

- `BLOCKED` rows;
- `LOW` confidence rows;
- negative replay contradictions;
- owner-review rows;
- missing-COGS rows;
- risk flags;
- source window gaps;
- unmatched SKU aliases;
- missing sizes;
- unresolved lifecycle/cancel/return rows.

Missing COGS must never be set to zero.

Returned or cancelled units must not be added back to sellable stock without source-backed return-QC or warehouse-return evidence.

Merchant Cabinet or offer availability evidence must not become physical stock truth.

## Allowed Scope

Allowed:

- read-only source inspection;
- local evidence generation;
- copied DB creation;
- copied-temp replay;
- copied-temp materialization;
- review-only workbooks;
- retained-blocker boards;
- validator implementation and execution for this proof lane;
- CodeCaptain/owner review packet preparation.

## Forbidden Scope

Forbidden:

- production `db/app.db` mutation;
- workbook mutation;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
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

## Green Label

The strongest allowed green label is:

`COPIED_TEMP_GREEN_PROOF_FOR_REANCHOR_SCOPE_ONLY`

That label is allowed only if all required validators pass, protected surfaces remain unchanged, and retained blockers are visible.

## Stoplines

- Do not use `Composed_Anchor_SKU_Size.anchor_qty` as the final April 23 current-stock quantity.
- Do not call the May 25 DB-anchor estimate authoritative for this lane.
- Do not hide workbook-internal risk flags.
- Do not silently clamp negative rows.
- Do not deduct rows without SKU-size identity.
- Do not infer lifecycle truth from CRM text alone.
- Do not add returns back without return-QC evidence.
- Do not use offer availability as physical stock.
- Do not use copied-temp proof as production authority.

