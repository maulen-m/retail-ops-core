# PLAN — Stock/Cost Truth Repair And Second-Pass Expert Repack

Date: 2026-04-23

## Purpose

Repair the repo-side landed-cost truth surfaces, preserve the usable part of the external stock-anchor work, overlay the new return/cancel quarantine contract, and prepare a corrected second-pass expert pack instead of repeating the same base-only COGS mistake.

## Why This Run Exists

Direct repo investigation plus the internal review established four important facts:

1. The external expert's stock-anchor reasoning is useful, but his finance/capital layer is not promotable as final truth.
2. The Oracle pack handed the expert a tainted cost surface: repo and pack artifacts expose base-cost-like values as `cogs_kzt`.
3. Live repo scripts still default to `DIM_SKU_light_v6` surfaces even though current operating rule authority has moved to v7/v9.
4. Stock investigation started before the return/cancel quarantine contract was formalized, so the external stock outputs must now be reevaluated under the new quarantine truth.

Concrete evidence already observed:

- `~/Docs/Autonomous_business/scripts/sync_truth_workbook_to_db.py` maps `Base_cost_kzt` into `cogs_kzt`.
- `~/Docs/Autonomous_business/scripts/sync_dim_sku_from_dim_sku_light.py` still defaults to `DIM_SKU_light_v6`.
- `~/Docs/Autonomous_business/scripts/sync_po_parts_from_inbound_calendar.py` still defaults to `DIM_SKU_light_v6`.
- The external rebuild uses unit values like:
  - `CL_OC_MEN_LINE51_WHITE` -> `4680`
  - `CL_NEW-CLO2_MEN_SUIT-61_BLACK` -> `4134`
  - `CL_OC_MEN_LINE52_BLACK` -> `3666`
- But current v7/v9 rule surfaces imply landed estimates around:
  - LINE51 -> `6394.5`
  - LINE61 -> `5919`
  - LINE52 -> `5005.5`
- The new return/cancel export now exposes:
  - `379` quarantine / expected-quarantine units
  - `632` employee QC rows
  - `258` exception rows

## Repo And Handoff Paths

- Operating repo: `~/Docs/Autonomous_business`
- Run pack: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass`
- Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Canonical Protocol

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/ARCHITECTURE.md`
- `~/Docs/Autonomous_business/docs/profit/PROFIT_REALISM_CONTRACT.md`
- `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
- `~/Docs/Autonomous_business/docs/protocol/active/PO_making_logic_v3.md`
- `~/Cowork/Projects/Sourcing-Research/docs/inventory/Dim_sku_light_v7.md`
- `~/Cowork/Projects/Sourcing-Research/docs/inventory/Master_Inventory_Rules_v9.md`

## External Analysis Artifacts To Review

Oracle pack root:

- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail`

External answer folder:

- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer`

Most relevant answer artifacts:

- `External_expert_answer/External_expert_answer.md`
- `stock_anchor_selection_and_rebuild_v2_report_2026-04-23.md`
- `current_stock_rebuild_2026-04-23.csv`
- `movement_replay_2026-04-23.csv`
- `inventory_business_eval_tables_2026-04-23.xlsx`
- `product_kaspi_offer_mapping_catalog.csv`

New quarantine truth artifacts:

- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_summary.md`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_backlog.csv`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/employee_qc_queue.csv`

## Execution Posture

- Agent A is the only write-capable execution agent.
- Agents B and C are read-only analysts.
- B and C publish independently before reading each other.
- Agent A starts only after B and C publish first-pass reports.
- Any DB mutation must be backup-first, env-gated, CLI-gated, and logged.
- No source swap or formula change without explicit provenance.

## Scope Of This Run

In scope:

1. Identify exactly where landed-cost truth is broken in repo and Oracle-pack consumer surfaces.
2. Decide what part of the external stock-anchor work remains valid after the quarantine contract.
3. Repair repo-side cost truth surfaces with the smallest correct change.
4. Prepare a corrected second-pass expert pack/prompt.

Out of scope for this run:

- manual warehouse recount itself
- pretending current stock is decision-grade before the quarantine overlay and cost-truth repair are complete
- unrelated PO/dashboard refactors
- broad business wiki ingestion

## Business Rules For This Run

1. Published COGS/profit must use landed cost, not base-only cost.
2. Returned or cancelled-after-movement stock is not automatically active sellable stock.
3. Quarantine/pending-QC stock is operationally visible, but not the same as active stock.
4. The external expert output may be retained as evidence, but only the parts that still survive current repo contracts.
5. If uncertainty remains after B/C review, fail closed and narrow the next pass instead of smoothing contradictions away.

## Desired Deliverables

### 1. Agent B Deliverable — Cost Truth Surface Audit

Required outcome:

- exact list of repo and Oracle-pack surfaces where `base` is being used or published as `cogs`
- exact list of v6 defaults that still need retirement or compatibility handling
- exact landed-cost formula/parameter references Agent A must honor
- exact minimum repair sequence for Agent A

### 2. Agent C Deliverable — Stock Anchor Salvage Under Quarantine Rules

Required outcome:

- what remains valid from the external stock-anchor decision
- what must be downgraded because the new quarantine contract exists
- what can already be promoted now
- what must stay owner-review or blocked
- what the corrected second-pass expert pack must include

### 3. Agent A Deliverable — Minimal Safe Repair Path

Required outcome:

1. implement or narrow the repo-side cost-truth repair
2. regenerate the corrected consumer surface(s) that future external analysis should read
3. document the stock-truth posture after quarantine overlay
4. prepare the revised second-pass expert prompt/pack inputs
5. run the smallest relevant validations and record exact results

## Validation Expectations

Minimum for Agent A:

- targeted tests first for any changed logic
- `pytest -q` or targeted pytest subset for touched surfaces
- `python3 scripts/validate_inventory_cost_drift.py` if cost surfaces are touched
- `python3 scripts/validate_cogs_integrity.py` if COGS truth/publication is touched
- `python3 scripts/validate_profit_publication_integrity.py` if publishability is touched
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are changed
- `python3 scripts/validate_params.py --strict` at the end, with clear separation between pre-existing failures and any new failures

If DB is touched:

- create backup first
- log backup path
- log restore command

## Agent Split

### Agent B — Repo/Pack Cost Truth Analyst

Read-only. Determine exactly how landed-cost truth is currently lost or mislabeled.

Core questions:

1. Which repo scripts and exported surfaces are publishing base-only cost as `cogs_kzt`?
2. Which live defaults still point to `DIM_SKU_light_v6`?
3. Which missing-COGS rows in the expert answer are actually present in `Dim_sku_light_v7.md`?
4. What is the smallest safe repair sequence for Agent A?
5. Can Agent A repair this without DB mutation, or is DB/state rebuild unavoidable?

Publish:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_b_report.md`

### Agent C — Stock Salvage / Quarantine Overlay Analyst

Read-only. Determine what remains valid from the expert stock-anchor work after the new returns/cancels contract.

Core questions:

1. Which parts of the composed-anchor logic still stand?
2. Which unit totals / family promotions are invalidated by quarantine truth or cost-surface issues?
3. Did the external movement replay already include return legs, and if so, what still remains incomplete for active-stock truth?
4. Which SKU families can be promoted now, which must stay owner-review, and which must stay blocked?
5. What exact files and clarifications must be added to the second-pass expert pack?

Publish:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`

### Agent A — Execution Agent

Write-capable after B and C publish. Implement the smallest safe repair path in causal order:

1. read B and C reports
2. stop and document if they materially conflict
3. add/adjust tests first
4. repair repo-side cost-truth surfaces
5. regenerate the corrected downstream consumer surface(s)
6. record the post-repair stock-truth posture under quarantine rules
7. prepare the corrected second-pass expert prompt/pack spec
8. run validations
9. update execution log and status board

## Launch Order

1. Agent B and Agent C can run in parallel.
2. Agent A starts only after B and C publish first-pass reports.
3. If B/C disagree materially, Agent A writes a stopline summary before coding.

## Done Criteria

This run is successful when:

- the repo-side landed-cost truth bug surface is pinned down precisely
- the salvageable part of the external stock-anchor work is separated from the unsafe part
- a minimal repair path is ready or implemented through Agent A
- the next expert pass can be run against corrected inputs instead of repeating the same COGS mistake
- all conclusions are traceable to exact repo paths, Oracle-pack artifacts, and command outputs
