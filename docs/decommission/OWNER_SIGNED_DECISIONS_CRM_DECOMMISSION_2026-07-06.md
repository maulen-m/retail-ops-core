# OWNER DECISION FORM — CRM Excel Pipeline Decommission (2026-07-06)

Program: retire `excel_ui/SALES_KSP_CRM_V3.xlsx` from the order pipeline.
Map (committed `d7444a38`): `Autonomous_business/docs/decommission/crm_excel_pipeline_decommission_map_2026-07-06.md`
Phase 1 (shadow feeder + parity validator) is building now — none of these answers block it.
These answers gate **Phase 2 (cutover)** and **Phase 3 (removal)**.

> **OPTION ZERO:** write "ACCEPT ALL RECOMMENDED" at the bottom and every question takes its recommended default.

---

## Q1. Phase 2 cutover order — what gets disabled first?

**Recommendation: one single gated flip — direct-feeder apply ON + scheduled CRM writer OFF + `crm-db-sync` OFF, together.**
One cutover event = one rollback flag = one thing to reason about. Sequencing them days apart creates a window where the workbook is half-alive (written but not synced, or synced but stale) — exactly the fragility we're removing.
*Example:* the flip happens the morning after parity goes GREEN; if anything looks wrong by evening, flip the flag back and the old lane runs the next scheduled slot unchanged.

**ANSWER Q1:** ________**Recommendation: one single gated flip — direct-feeder apply ON + scheduled CRM writer OFF + `crm-db-sync` OFF, together.**_______

## Q2. Shadow parity window length?

**Recommendation: 7 days**, with early-green allowed at day 4 if parity is clean AND the window has already exercised ≥1 return and ≥1 multi-line order.
3 days can miss weekend order patterns and returns entirely; 14 days just delays removal of a known fragility source with no added proof.
*Example:* shadow starts 07-07 → earliest cutover 07-11 (early-green), normal cutover 07-14.

**ANSWER Q2:** ________ 7 days_______

## Q3. Frozen workbook — where does the file live after cutover?

**Recommendation: keep it at its current path, made read-only (chmod 444), plus one archived copy under `backups/`.**
Keeping the path valid means any straggler script fails soft (reads stale-but-real data and gets flagged by validators) instead of crashing on a missing file mid-transition. Moving it can come later, once Phase 3 confirms zero readers.
*Example:* `excel_ui/SALES_KSP_CRM_V3.xlsx` (read-only) + `backups/archive/SALES_KSP_CRM_V3_frozen_2026-07.xlsx`.

**ANSWER Q3:** ______**Recommendation: keep it at its current path, made read-only (chmod 444), plus one archived copy under `backups/`.**_________

## Q4. Return-ledger dates — keep old `date.today()` behavior or switch to real API/status dates?

**Recommendation: switch to API/status dates at cutover, as a documented behavior change.**
The old behavior stamps a return with whatever day the import happened to run — that's an artifact of the Excel lane, not truth. Real status dates make P&L and buyout math honest. During the shadow window the parity report shows exactly which rows this would change, so the delta is known before it happens.
*Example:* a return Kaspi reports on 07-09 but imported 07-11 books as 07-09 (new) instead of 07-11 (old).

**ANSWER Q4:** _______________

## Q5. Legacy double-click waybill commands (`run_merged_build_waybills.command`, CRM-fallback paths)?

**Recommendation: fail-closed at Phase 2 — they exit with a clear message pointing to the Google board closeout, with a 30-day emergency override env var, then delete in Phase 3.**
Your employee workflow is board → Telegram; the biggest recurrence risk in the map is a manual shortcut silently re-entering the workbook. Fail-closed makes that impossible by default while keeping a documented escape hatch for one month.
*Example message:* "CRM lane retired 2026-07 (owner decision). Use Google Ops Board closeout. Emergency: AB_LEGACY_WAYBILL_OVERRIDE=1."

**ANSWER Q5:** ______**Recommendation: switch to API/status dates at cutover, as a documented behavior change._________

## Q6. What replaces the workbook as the strict-anchor proof for daily gates?

**Recommendation: both — DB freshness AND the direct-feeder parity/apply report.**
Two independent proofs: "the data is recent" (DB max order_date vs now) and "the pipe that produced it ran clean" (feeder report GREEN). One can be green while the other is broken; requiring both keeps the strict gates as strict as the workbook anchor was.

**ANSWER Q6:** _____ Recommendation: both — DB freshness AND the direct-feeder parity/apply report.__________

## Q7. `kaspi_orders_y` (old archive-reconciler table)?

**Recommendation: leave archived and inert — no rebuild, no removal, separate owner decision if ever needed.**
It's historical reconciliation surface, out of the live lane. Touching it now widens blast radius for zero daily-ops benefit.

**ANSWER Q7:** __________ leave archived and inert — no rebuild, no removal, separate owner decision if ever needed._____

---

## Defaults table (what OPTION ZERO signs)

| Q | Default |
|---|---|
| 1 | Single gated flip: feeder ON + CRM writer OFF + crm-db-sync OFF together |
| 2 | 7-day shadow window, early-green at day 4 if returns + multi-line covered |
| 3 | Freeze in place read-only + backup copy |
| 4 | Real API/status dates from cutover (documented change) |
| 5 | Legacy commands fail-closed + 30-day override env, deleted in Phase 3 |
| 6 | DB freshness + feeder report, both required |
| 7 | kaspi_orders_y stays archived/inert |

## Already locked (no answer needed)
- **Phase 4 E2E acceptance (your 07-06 instruction):** after cutover, on a real operating day — fetch → Google board ingest → employee fills sizes + sets ready → assembly → grouped PDF bundles delivered to Telegram, with committed evidence bundle. Old lane stays OFF-but-recoverable until this passes.
- Rollback for the whole program = one flag flip, never a git revert.
- No Kaspi write APIs anywhere in any phase.

**OWNER SIGNATURE / ANSWERS:** _______yes fully agree with all recommendations. i approve them all.________
