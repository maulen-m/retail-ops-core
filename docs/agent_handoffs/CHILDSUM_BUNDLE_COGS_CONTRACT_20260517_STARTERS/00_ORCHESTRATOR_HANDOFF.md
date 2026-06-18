# ChildSum Bundle COGS Contract - Orchestrator Handoff

As of: `2026-05-17`

Gate: YELLOW

Status: `HANDOFF_READY_FOR_ONE_AGENT_COPIED_TEMP_CONTRACT_LANE`

## Purpose

Fix and contract the one remaining COGS representation blocker from the Agent846 copied-temp MVOS proof:

- store/order/SKU: `ACMEWEAR 909054064 / SUIT-31-TS`
- validator blocker: `cogs_source=unresolved`, blank `cogs_kzt`, `base_cost_cny=0.0`, `weight_kg=0.0`
- unresolved reason: `MISSING_BASE_AND_WEIGHT`

This handoff does not authorize production mutation. It gives the next COGS agent the exact contract shape for ChildSum bundle COGS: child-bundle unit COGS must be decomposed per included item, using each item's base cost and weight from the corresponding parental bundle part set, then summed into the child bundle.

## Evidence Already Known

Primary blocker packet:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_agent846_post_codecaptain_webui/ORCHESTRATOR_REVIEW_AFTER_AGENT846.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_agent846_post_codecaptain_webui/agent846_full_copied_temp_mvos_proof_closeout.md`
- `~/Docs/Autonomous_business/exports/validation/mvos_agent846_post_codecaptain_webui/20260517_101248/agent846_full_copied_temp_mvos_proof/28_cogs_completeness/cogs_unresolved_lines.csv`

Observed failing row:

```csv
order_id,sale_date,sale_month,store_code,sku_key,units,net_rev_kzt,cogs_kzt,cogs_source,model,base_cost_cny,weight_kg,is_unresolved,is_base_only,unresolved_reason
909054064,2026-05-04,2026-05,ACMEWEAR,SUIT-31-TS,1.0,7563.0,,unresolved,SUIT-31-TS,0.0,0.0,True,False,MISSING_BASE_AND_WEIGHT
```

Agent848 copied-temp COGS repair was accepted as a temporary proof input, but it was not a durable representation contract:

- `LINE-31-TS=6006.76 KZT` from `CL_OC_MEN_LINE51_WHITE`
- `SUIT-21-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- `SUIT-31-LS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- `SUIT-31-TS=5567.22 KZT` from `CL_NEW-CLO2_MEN_SUIT-61_BLACK`

The owner clarification for this lane is stricter: ChildSum bundle COGS should be decomposed per item COGS from parental bundle parts, not represented as an unexplained whole-parent carry-forward when component base costs and weights exist.

## ChildSum COGS Contract

For a child-bundle SKU, COGS is the sum of included component item COGS:

```text
child_unit_cogs_kzt =
  sum(component_base_cost_cny * CNY_KZT)
  + sum(component_weight_kg * USD_KZT * DLV_RATE_USD_PER_KG)
```

Required semantics:

- `base_cost_cny` means the included component item's base cost from the respective parental bundle part source.
- `weight_kg` means the included component item's weight from the respective parental bundle part source.
- If a child bundle contains a subset of a parent bundle, use only the included component rows for that child bundle.
- If only parent aggregate totals exist, allocate by explicit component shares from the parent part source; do not guess shares from names.
- The resolved sales line must expose a positive `cogs_kzt` and a non-`unresolved` `cogs_source`.
- The source label should make the basis auditable, for example `childsum_component_formula` or `owner_approved_childsum_unit_cogs_copied_temp`.

Expected `SUIT-31-TS` business meaning from the child-bundle context is a Line61 child bundle composed from the Line61 parent-family parts, likely `T-shirt + leggings + shorts`; the agent must verify the exact component list from current source truth before applying it.

## Recommended Implementation Route

Use a one-agent lane. No parallel analysts are required unless the COGS agent cannot locate component source truth.

1. Reproduce the current blocker on the Agent846 copied DB.
2. Locate the current COGS path for `view_sales_line_truth`, `sales_fact_v2`, `dim_sku`, and the cashflow translator.
3. Add a narrow contract for ChildSum bundle COGS using the existing repo pattern if one already exists.
4. Prefer component-sum representation:
   - component rows or a component COGS table/view identify child SKU, parent source SKU, component name/key, base cost, weight, and formula result;
   - `view_sales_line_truth` or its source projection resolves `SUIT-31-TS` to positive childsum COGS;
   - no fake `dim_sku.base_cost_cny` or `dim_sku.weight_kg` is inserted just to appease the validator.
5. If component truth cannot be proven from current sources, stop `YELLOW` with the exact missing source request.
6. If the orchestrator explicitly chooses the tactical copied-temp path, encode Agent848's `5567.22 KZT` for `SUIT-31-TS` as a copied-temp unit COGS override with an explicit non-formula source label. Do not label it as component formula unless component rows prove it.

## Prohibited Shortcuts

- Do not set missing COGS to zero.
- Do not invent `base_cost_cny` or `weight_kg`.
- Do not mutate `db/app.db`, `excel_ui/SALES_KSP_CRM_V3.xlsx`, source pointers, scheduler files, Web_automation, external systems, cash, PO, stock, prices, ads, or owner publication.
- Do not treat Agent848 copied-temp parent carry-forward as production authority.
- Do not clear the validator by loosening strict mode for all unresolved COGS rows.

## Acceptance Criteria

The COGS agent can close `Gate: GREEN` only if all are true:

- On a copied DB, `ACMEWEAR 909054064 / SUIT-31-TS` has positive `cogs_kzt`.
- Its `cogs_source` is not `unresolved` and identifies the ChildSum or explicit copied-temp unit basis.
- `scripts/validate_cogs_completeness_by_month.py --start 2026-05-01 --end 2026-05-17 --strict --db-path <copied_db> --truth-source db --as-of 2026-05-17 --output-dir <evidence_dir>` returns `status=PASS`.
- `cogs_unresolved_lines.csv` is empty for the May 1-17 copied-temp proof window.
- Focused tests prove missing COGS still fails closed and ChildSum COGS resolves only with auditable source truth.
- Production DB/workbook hashes are unchanged from the current reviewed boundary unless a later owner approval explicitly opens a production lane.

Close `Gate: YELLOW` if component source truth is missing, contradictory, or cannot support ChildSum formula representation without an owner/source decision.

Close `Gate: RED` if any protected production surface must be mutated to continue.

## Suggested COGS Agent Launch

Use the starter prompt:

`~/Docs/Autonomous_business/docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/01_AGENT_COGS__CHILDSUM_BUNDLE_COGS_CONTRACT__ROOT.md`

Copy-paste launch line:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/CHILDSUM_BUNDLE_COGS_CONTRACT_20260517_STARTERS/01_AGENT_COGS__CHILDSUM_BUNDLE_COGS_CONTRACT__ROOT.md. Keep the lane copied-temp/code-contract only; do not production-apply or mutate protected surfaces.
```
