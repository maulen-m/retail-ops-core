# CaptainRequestEvaluation - April 23 Stock Re-Anchor Execution Plan Request

Created: 2026-05-25 12:49 +05
Repo: `~/Docs/Autonomous_business`
Request type: external expert plan review before implementation

## Plain Request

Please evaluate the proposed inventory re-anchor and return a complete, practical execution plan that the Autonomous_business orchestrator and execution agents can follow.

The human owner has corrected the inventory basis:

> The April 23 stock workbook is correct and should be treated as the latest real human-owner-approved physical stock anchor. We should rebuild current stock from that anchor by subtracting all following sales through today's date, using the repo inventory rules. This should produce a better answer than the May 25 estimate based on the later DB stock anchor, because the April 23 workbook is closer to real-life stock data.

The anchor workbook to use is:

`~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx`

The desired outputs are:

1. A rebuilt current stock and COGS workbook in the same practical format as:
   `~/Downloads/Autonomous_business_stock_assets/20260525_110409_warehouse_stock_count_and_estimate/01_ESTIMATED_CURRENT_STOCK_VALUATION_20260525.xlsx`
2. A rebuilt current inventory business evaluation workbook in the same practical format as:
   `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer copy/inventory_business_eval_tables_2026-04-23.xlsx`

## Current Known Comparison

The May 25 workbook was not directly based on the April 23 workbook. It used the production DB's later stock anchor dated 2026-05-04, then subtracted matched CRM/order depletion through 2026-05-25.

For the main products:

| Source | Basis | LINE61 | LINE51 |
| --- | ---: | ---: | ---: |
| April 23 workbook | Estimated current stock as of 2026-04-23 | 874 | 958 |
| May 25 workbook | 2026-05-04 DB anchor minus matched post-anchor depletion | 1103 | 1143 |

The owner now wants the April 23 workbook to supersede the May 4 DB anchor for this rebuild lane.

## Questions For The External Expert

Please provide a complete execution plan that answers:

1. What is the safest source hierarchy for this re-anchor?
2. Which sheet(s) and column(s) from the April 23 stock workbook should become the canonical anchor input?
3. How should `BLOCKED`, `LOW`, `MEDIUM`, negative, owner-review, and risk-flagged rows be handled?
4. What is the exact replay window: should sales subtraction begin after 2026-04-23 inclusive or exclusive, and which date field should define sale/depletion timing?
5. Which sales/order sources should be used for the post-anchor replay: DB order facts, CRM workbook, API raw order entries, WebUI ArchiveOrders, or a ranked combination?
6. What are the correct rules for cancellations, returns, refunds, replacement fulfillments, KASPI_DELIVERY/on-delivery states, and status-change timing?
7. How should COGS be carried forward from the April workbook, DB `dim_sku`, or owner-approved parent/child COGS overrides?
8. How should unmatched SKU aliases, missing sizes, bundle child SKUs, and offer-only availability rows be quarantined without corrupting physical stock truth?
9. What exact validator gates should pass before calling the copied-temp proof green?
10. What repo docs/contracts should be updated first if this becomes the new inventory source policy?
11. What production mutation path, if any, should be proposed only after copied-temp proof and owner approval?
12. What exact owner approval phrases should be required for:
    - copied-temp proof only;
    - production DB/source-contract apply;
    - publication or downstream dashboard use.

## Required Execution Strategy

Please design the plan in phases that can be run fast but safely:

1. Read-only audit of anchor workbook structure and current repo inventory contracts.
2. Anchor normalization into a deterministic table.
3. Post-anchor sales/depletion extraction and source ranking.
4. Copied-temp replay and stock/COGS rebuild.
5. Output workbook generation.
6. Validator and regression pass.
7. CodeCaptain/owner review packet.
8. Optional production re-anchor apply, only if separately authorized.

For each phase, include:

- input files;
- output artifacts;
- exact stoplines;
- validator commands or test families to run;
- agent split recommendations for tmux execution;
- what can be parallelized;
- what must be serialized;
- human-only clarifications, if any.

## Safety Boundary

This request is plan/review only unless a later explicit implementation approval is given.

Do not assume authority for:

- production DB writes;
- CRM/workbook mutation;
- source-pointer writes;
- scheduler/LaunchAgent/cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- ad-platform writes;
- stock changes in merchant systems;
- price changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication.

The desired plan should be fail-closed: if a row cannot be matched, it should become a visible quarantine/blocker rather than being smoothed into green.

## Pack Index

This pack should include:

- this request document;
- repo contract/start-here docs;
- inventory and sales data model docs;
- 10-out-of-10 acceptance contract for context;
- current source-contract registry;
- the April 23 stock anchor workbook as sidecar;
- the April 23 inventory eval workbook as sidecar;
- the May 25 estimated valuation workbook as sidecar format reference;
- the May 25 source manifest and row CSVs as sidecars;
- the mandatory full-range ArchiveOrders merged CSV.
