# Phase 20 Owner Facts And Retained Blocker Addendum

Status: ACTIVE_NON_PRODUCTION_ADDENDUM
Created: `2026-05-22T03:29:30+0500`

This addendum records owner-confirmed facts and current retained-blocker routing
after Phase 19. It is a local contract/evidence doc only. It does not mutate the
active source packet root, source pointers, production DB, workbooks,
schedulers, Web_automation, Kaspi/API/WebUI, ad platforms, cash, PO, stock,
prices, or owner-publication surfaces.

## Authority Boundary

Allowed:

- read-only analysis;
- copied-temp DB proofs;
- local evidence docs;
- local contract docs;
- validator/test runs;
- Oracle pack drafts.

Not authorized:

- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler, LaunchAgent, or cron changes;
- Web_automation writes;
- Kaspi/API/WebUI mutations;
- external writes;
- ad-platform writes or ad spend;
- stock changes;
- price changes;
- cash movement;
- supplier payment;
- PO commitment;
- owner publication;
- production preflight;
- production apply.

## Owner Facts That Should Not Be Re-Asked

| fact_id | owner-confirmed fact | proof effect | re-ask rule |
| --- | --- | --- | --- |
| `OWNER_FACT_UNIVERSAL_132822924_328581041_20260521` | Universal offer `132822924_328581041`, product id `MTE3MDQ5MjU1`, decoded product code `117049255`, name `Леггинсы PRO COMBAT 2010 белый XL / Леггинсы PRO COMBAT белый`, category `Мужское термобелье`, SKU family `CL_NEW-CLO_MEN_LEG_WHITE`, price seen `1500 KZT`, warehouse `30000001_PP1`. | May be used for copied-temp proof planning as `CL_NEW-CLO_MEN_LEG_WHITE_XL`; does not authorize production/source application. | Do not re-ask this identity unless source evidence contradicts it or a production/source-pointer/write lane is requested. |
| `OWNER_FACT_NO_FRESHER_PHYSICAL_STOCK_20260521` | No fresher physical stock data exists than the last physical stock source already used. | Stock freshness remains an honest retained blocker; offer availability cannot clear physical stock truth. | Do not re-ask for fresher physical stock in this wave unless the owner creates/provides a new source file/export. |

## Current Copied-Temp Closures To Preserve

| closure_id | status | required wording |
| --- | --- | --- |
| `UNIVERSAL_LEG_WHITE_XL_SALES_IDENTITY` | Copied-temp closed / stop for production | Strict sales rebuild passes with owner-confirmed Universal mapping, but production/source gates remain blocked. |
| `ORDER_ENTRY_NO_REAL_ENTRY_QUARANTINE_COPIED_TEMP_V1` | Copied-temp closed / stop for production | Universal `922898360` and `923528055` remain no-real-entry quarantine rows; `0` synthetic item-entry rows are inserted. |
| `WORKBOOK_ANCHOR_FACT_SALES_WORKBOOK_ANCHOR` | Copied-temp closed / stop for production | `8353` workbook-anchor rows are accepted on copied DB only; production route needs review and later write gate. |
| `DAY_COMPLETE_844362551_861137901` | Copied-temp closed / stop for production | The two day-complete rows pass only on copied DB; current-window status-ledger continuity remains retained. |
| `SINGLE_TRUTH_EVIDENCE_LOCAL_SCOPE` | Copied-temp partial closed / stop for PO money | Evidence-local single-truth system passes, but full alignment still fails physical-stock drift. |

## Retained Blockers To Keep Visible

| retained_id | current retained reason | required treatment |
| --- | --- | --- |
| `PHYSICAL_STOCK_SOURCE_TRUTH` | Last physical stock source is stale and owner confirmed no fresher physical stock source currently exists. | Keep stock/PO/publication blocked unless fresh physical stock appears or CodeCaptain accepts a substitute stock/capital-risk contract. |
| `C3_SOURCE_FRESHNESS_POLICY_GATES` | Source freshness and policy gates still retain exact rows. | Do not claim owner-publication green from copied-temp bridges. |
| `STOREB_MAY18_ADS_RETAINED_SPEND` | STOREB May 18 keeps `10` source-backed rows and `3837.32 KZT` retained spend without current-source related-product truth. | Keep spend visible; do not zero unmapped rows. |
| `ACMEWEAR_LINE31_STARRY_BLACK_ADS_COVERAGE` | `CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK` lacks an exact May 18 ads packet row or source-backed zero-spend/no-campaign proof. | Keep ads coverage retained until exact source evidence appears. |
| `STATUS_LEDGER_CURRENT_WINDOW` | Three-store scoped ledger passes only through `2026-05-17`; current `2026-05-05..2026-05-18` window remains retained. | Do not use copied-temp day-complete closure as status-ledger green. |
| `PO_MONEY_PHYSICAL_STOCK_DRIFT` | PO money required failure remains physical-stock inventory cost drift. | Do not claim PO money green until accepted physical stock/capital-risk route clears it. |
| `B012_LINE31LS_COGS_AUTHORITY` | `ACMEWEAR 929183530 / LINE-31-LS_2XL` identity is proven, but accepted `LINE-31-LS` COGS authority/default repeated-run route is missing. | Keep B012 `YELLOW`; do not infer LINE-31-LS COGS from adjacent LINE51 or LINE-31-TS authority. |
| `DIRTY_REPO_PRODUCTION_READINESS` | Dirty state is grouped but not cleaned/committed/parked. | Do not run production preflight from dirty state. |
| `AUTOMATION_PAUSE_BOUNDARY` | All-business automation is paused unless owner explicitly resumes exact scope. | Do not resume scheduler/LaunchAgent/cron from this addendum. |

## Registry Impact

The active JSON registry remains valid as a historical active registry. This
addendum is the current Phase 20 overlay for owner facts and retained-blocker
wording. It intentionally does not change `source_packet_root` or any source
pointer.

Agents should read this addendum together with:

- `docs/current/CURRENT_AUTHORITY_INDEX.md`;
- `docs/current/CURRENT_SOURCE_TRUTH_MAP.md`;
- `docs/current/CURRENT_BLOCKER_BOARD.tsv`;
- `docs/current/CURRENT_PRODUCTION_WRITE_BOUNDARY.md`;
- `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json`.

## Exit Gate

This addendum can become obsolete only when a later owner-approved or
CodeCaptain-reviewed boundary explicitly supersedes these facts and retained
blockers. Until then, copied-temp closures remain non-production evidence and
retained blockers remain visible.

