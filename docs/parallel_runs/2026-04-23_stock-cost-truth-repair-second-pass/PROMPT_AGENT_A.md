# PROMPT_AGENT_A — Execute Stock/Cost Truth Repair

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_b_report.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`
7. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Role

You are Agent A, the only write-capable execution agent for this rollout.

Start only after Agent B and Agent C have published first-pass reports.

## Objective

Implement the smallest safe repo-side repair so future stock analysis and expert packs stop consuming base-only pseudo-COGS as if it were landed COGS.

This is not a broad stock rewrite. Your job is to:

1. repair or tightly narrow the landed-cost truth surface
2. preserve the useful stock-anchor evidence
3. align the output posture with the new return/cancel quarantine contract
4. prepare a corrected second-pass expert input set

## Known Starting Facts

These are already established from direct investigation:

- `sync_truth_workbook_to_db.py` maps `Base_cost_kzt` to `cogs_kzt`
- `sync_dim_sku_from_dim_sku_light.py` defaults to `DIM_SKU_light_v6`
- `sync_po_parts_from_inbound_calendar.py` defaults to `DIM_SKU_light_v6`
- external answer values like LINE51 `4680`, LINE61 `4134`, LINE52 `3666` are base-only / lower-bound, not landed
- the repo now has a separate quarantine truth export with `379` quarantine units and `632` QC rows

Do not assume the external expert was simply wrong. Treat the external pack as partially poisoned by repo-side truth surfaces until proven otherwise.

## Execution Order

1. Read Agent B and Agent C reports fully.
2. If B/C materially conflict, write a stopline summary before coding.
3. Add tests first for the exact surfaces you will change.
4. Repair the smallest correct set of truth surfaces, likely including some combination of:
   - stopping `Base_cost_kzt -> cogs_kzt` leakage
   - adding a repo-local consumer-safe v7 surface or explicit import path
   - replacing stale v6 defaults where required
   - regenerating the cost/mapping sidecar used by downstream analysis
5. Re-evaluate whether any stock/business artifact can be promoted after the quarantine contract.
6. Prepare the corrected second-pass expert prompt/pack spec only after the inputs are fixed.
7. Run the relevant validations.
8. Update execution log and status board.

## Constraints

- Keep changes surgical.
- Do not refactor adjacent systems just because they are ugly.
- Do not loosen validators.
- Do not hide provenance.
- No DB writes without backup-first, env gate, CLI gate, and explicit logging.
- If the correct repair requires a doc/rule update first, stop and record that stopline instead of inventing new business math.

## Expected Outputs

At minimum, produce source-backed execution notes and exact output paths for:

- repaired repo files
- any regenerated cost/mapping sidecar or export surface
- any updated validation artifacts
- the revised second-pass expert prompt/pack specification

If a second-pass Oracle pack is prepared in this run, log its exact root path.

## Required Validation

Run the smallest relevant gates for the changed surfaces, including:

- targeted tests first
- `pytest -q` or targeted pytest subset
- `python3 scripts/validate_inventory_cost_drift.py` if cost truth is touched
- `python3 scripts/validate_cogs_integrity.py` if COGS truth is touched
- `python3 scripts/validate_profit_publication_integrity.py` if publication surfaces are touched
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs changed
- `python3 scripts/validate_params.py --strict` at the end

If a broader strict gate is already red for unrelated reasons, record that explicitly instead of masking it.

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_a_execution_log.md`
- update `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/status_board.md`

Include:

- ordered actions
- commands run
- files changed
- output paths
- pass/fail gates
- remaining stoplines
- DB backup path and rollback steps if applicable
