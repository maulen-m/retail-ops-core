What’s actually happening (evidence-based)

On 2026‑02‑08, BUSINESS_INSIDES_2026-02-08.md was generated using sales_fact_v2 (DELIVERED, return_flag=0) and shows “Last 7 Days” Net Rev values like 294,228 (Feb‑03), 428,146 (Feb‑04), 328,984 (Feb‑07).



On 2026‑02‑09, the same BUSINESS_INSIDES_2026-02-08.md (as-of date still 2026‑02‑08) was regenerated but now uses view_sales_line_truth / view_sales_daily_truth, and the exact inflated numbers you pasted appear (e.g., Feb‑07 “Units Shipped 77 / Net Rev 482,681”).



The view’s logic shows why this can happen: it unions sales_fact_v2 with fact_sales rows that don’t match (order_id, store_code, sku_id) in v2, and it treats all fact_sales rows as DELIVERED with return_flag=0 (no real status/return filtering).



The agent’s own reconciliation CSV shows that for Feb‑03..Feb‑07, fact_sales is systematically larger than v2 on units and net rev (and often has very different COGS). Example:

2026‑02‑07: v2_units=50 vs fact_units=78 and v2_net_rev=328,983.99 vs fact_net_rev=451,359.20




That aligns exactly with the inflated Business-Insides table that uses the view.

Conclusion: the “canonical interface” is currently not safe as a published truth source for recent performance. It’s letting an untrusted table (fact_sales) override/augment recent days.

The most efficient approach
Principle

Correctness > coverage. If fact_sales is wrong for recent days, don’t use it there — even if it gives “more rows”. Use it only where you’ve proven parity.

Minimal corrective change (high impact, low scope)

Freeze “published sales truth” for recent dates to v2 only

In view_sales_line_truth, do not union in fact_sales rows for dates where v2 exists (or for dates >= v2’s min_date).

Keep fact_sales_lookup (COGS fallback) because it’s valuable and doesn’t contaminate revenue/units if used carefully.

Make Business‑Insides and dashboard read from the “published truth”

Until the view is fixed, Business‑Insides should go back to v2-only (the older behavior) because it produced sane values.



Add a strict workbook anchor validator

The workbook is our best grounded operational anchor; use it to prevent silent drift.

The “external reference check” currently reports huge diffs but still says “ok” (so it’s not acting as a gate).





Convert that into a fail-the-build validator for recent windows.

De-scope (postpone) items from the agent plan

Ads integration is important, but do not add it while sales truth is drifting — it adds another moving part and makes debugging harder.

Event chronology / restamping fixes are also important, but first stop the obvious inflation in sales truth feeding Business‑Insides.

Measurable success criteria (so we don’t “feel” it’s fixed)

Pick a recent anchor window (suggest: last 14 days where workbook is trustworthy).

For each day in window:

units_db_published must be within ±5% of units_workbook

net_rev_db_published must be within ±5% of net_rev_workbook

db_published must not exceed workbook by more than tolerance (because workbook is “what we shipped”; cancellations/returns can make reality lower, not higher)

Plus:

Business‑Insides “Last 7 days” must match the published truth daily table exactly (no independent logic).

The validator must hard-fail if max_abs_diff breaches tolerance.

Concrete plan for the agent (tests-first, anchored to SALES_KSP_CRM_V3.xlsx)
Phase 0 — lock definitions (no code yet)

Define what the Business‑Insides “Date” means:

Default recommendation: treat it as the shipping journal day (workbook “Date”), not “delivered payout day”.

Define what “published sales truth” is:

Default recommendation: sales_fact_v2 is authoritative for recent days; fact_sales is legacy/history or COGS-only lookup until reconciled.

Phase 1 — tests (fail first)

Add tests that will fail on current inflated state:

test_sales_workbook_anchor_parser.py

Read SALES_KSP_CRM_V3.xlsx (path passed via env var in tests, or use a tiny extracted fixture CSV committed to repo).

Assert parser outputs daily totals for a known mini-window (e.g., 2026‑02‑02..2026‑02‑07).

test_published_sales_truth_matches_anchor_window.py

Query DB “published truth daily” for the same window.

Assert diffs within tolerance.

test_business_insides_uses_published_truth.py

Ensure Business‑Insides generator reads only the published truth view/table.

Phase 2 — diagnose (read-only scripts)

Add script scripts/compare_sales_sources_to_workbook.py (dry-run only):

Inputs:

--workbook <path>

--db <path>

--start/--end

Outputs:

Daily table comparing:

workbook totals

sales_fact_v2 totals

fact_sales totals

view_sales_daily_truth totals (current)

Per-store breakdown (if available) to localize drift.

Phase 3 — fix the inflation at the source (smallest change)

Fix view_sales_line_truth creation logic:

Keep v2 selection with strict filters (DELIVERED, return_flag=0).



Change fact_sales inclusion policy:

Option A (recommended): include fact_sales lines only for dates < min(v2.sale_date).

Re-run Business‑Insides; verify Feb‑03..Feb‑07 stop inflating (should revert to v2-like values).



Phase 4 — promote the validator to a strict gate

Make a scripts/validate_sales_against_workbook.py validator.

Wire it into our strict validation chain (similar to other validators).

Fail if drift exceeds tolerance.

Phase 5 — only after green: revisit deeper issues

If v2 has missing COGS, fill deterministically (dim_sku + calc_cogs).

Then do ads attribution.