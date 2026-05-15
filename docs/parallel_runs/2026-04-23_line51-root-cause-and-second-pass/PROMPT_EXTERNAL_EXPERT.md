# PROMPT_EXTERNAL_EXPERT — LINE51 / Active-Stock Second Pass

You are reviewing a corrected second-pass stock investigation for the Autonomous_business repo.

Your task is not to repeat the prior workbook blindly. Your task is to use the corrected assumptions and produce the strongest possible approximate current stock view without pretending uncertainty is resolved.

## What Changed Since The First External Pass

The prior pass was useful, but two important problems were identified:

1. landed COGS / valuation surfaces were understated because the internal pack exposed base-like `cogs_kzt` values rather than the repaired landed-cost surface
2. return / quarantine handling was too optimistic for active-stock interpretation

This second pass must explicitly separate:

- `physical_stock_estimate`
- `active_stock_estimate`
- `quarantine_stock_estimate`
- `expected_quarantine_stock_estimate`

## Core Business Facts

1. We do not currently have a near-term full manual warehouse recount.
2. LINE51 is suspected to be materially overstated in the first external rebuild.
3. Owner rough warehouse estimate for LINE51 total family stock is about `750` units, but size allocation is unknown.
4. LINE52 manual recount remains strong physical evidence, but may still include quarantine units unless explicitly proven otherwise.
5. The goal is decision usefulness, not false precision.

## Non-Negotiable Rules

1. Do not treat `RETURN_IN` as active stock by default.
2. Do not treat quarantine / pending-QC units as active stock.
3. Do not apply a blanket global haircut unless the provided evidence clearly supports it.
4. If a correction is only justified for one family, keep it family-specific.
5. Preserve blocked families as blocked when the evidence still does not support promotion.

## What You Must Evaluate

1. LINE51 root-cause:
   - undercounted sales?
   - overcounted returns?
   - cancellation misclassification?
   - mapping duplication?
   - anchor overstatement?
2. Whether LINE51’s problem likely generalizes to other high-capital families.
3. Whether any global correction factor is justified.
4. A corrected approximate current stock view by family and by SKU-size where possible.

## Required Outputs

Produce:

1. one Excel workbook with the final results
2. one markdown summary explaining:
   - what was changed from the first pass
   - what is considered active vs quarantine vs expected quarantine
   - what remains blocked
   - what is still uncertain

Inside the Excel workbook, include at minimum:

- `Executive_Summary`
- `Family_Level_Decision_View`
- `SKU_Size_Active_Stock`
- `SKU_Size_Physical_Stock`
- `Quarantine_Overlay`
- `LINE51_Root_Cause`
- `Global_vs_Family_Adjustment_Test`
- `Blocked_And_Low_Confidence`

## Preferred Decision Posture

- If evidence is strong enough, recommend family-specific overrides.
- If evidence is not strong enough for a family, keep it owner-review.
- If evidence is weak or contradictory, fail closed and say so plainly.

## Inputs

Use the corrected second-pass bundle prepared by the internal execution agent, including:

- repaired landed-cost surfaces
- quarantine exports
- LINE51-specific root-cause findings
- cross-family sensitivity findings
- any override-ready sidecars

Do not rely on the original first-pass finance/capital sheet as authoritative unless the corrected pack explicitly republishes it.
