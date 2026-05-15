# PROMPT_AGENT_A_FOLLOWUP — Reconcile Second-Pass Pack With Quarantine Stock Truth

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PROMPT_AGENT_A.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_a_execution_log.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`
8. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Role

You are still Agent A, the only write-capable execution agent for this rollout.

This is a bounded follow-up pass. Do not reopen the landed-cost repair broadly unless Agent C's findings force one small corrective adjustment.

## Objective

Reconcile the corrected second-pass expert inputs with Agent C's quarantine-stock findings so the next expert pass consumes:

1. repaired landed COGS
2. quarantine-aware stock interpretation
3. narrowed recompute scope instead of a full unnecessary rebuild

## What Is Already Done

Treat these as already established unless your direct verification proves otherwise:

- supplier-landed FX precedence is now routed `USDT_KZT / USDT_CNY` first, fallback `73` second
- touched cost consumers no longer silently rely on base-only pseudo-COGS
- touched DIM consumers default to `DIM_SKU_light_v7`
- second-pass landed-cost inputs already exist under `second_pass_inputs/`

Do not repeat the entire cost-truth rollout. Build on it.

## New Required Inputs From Agent C

Agent C's report is now substantive and changes the stock interpretation:

- `current_stock_rebuild_2026-04-23.csv` is not safe as active sellable stock as written
- `movement_replay_2026-04-23.csv` already re-adds return legs
- quarantine stock must be separated from active stock
- `24` rebuilt families overlap quarantine candidates
- `48` rebuilt rows currently depend on `return_in_qty`
- LINE52 remains strong physical-anchor evidence, but must not be presented as clean active-stock truth

Primary source:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`

## Execution Order

1. Read Agent C's report in full.
2. Verify whether your current `second_pass_inputs/` pack already includes the quarantine files and a quarantine-aware sidecar.
3. If not, add the smallest correct overlay so the second pass is quarantine-aware without rerunning the whole anchor exercise.
4. Recompute only the subset Agent C identified as affected:
   - the `24` rebuilt families that overlap quarantine candidates
   - the `48` rows with positive `return_in_qty`
   - then regenerate the global rollups that depend on them
5. Revise the expert-pack spec so it explicitly separates:
   - `active_stock`
   - `quarantine_stock`
   - `expected_quarantine_stock`
6. Downgrade LINE52 wording:
   - allowed: strongest physical-anchor evidence
   - not allowed: hard `PROMOTE_NOW` for active sellable stock
7. Mark first-pass finance/capital workbook outputs as non-authoritative unless regenerated under the repaired landed-cost plus quarantine-aware interpretation.
8. Update execution log and status board with the new outputs and remaining stoplines.

## Required Output Additions

At minimum, produce or update the following in:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/second_pass_inputs/`

Required surfaces:

1. updated `second_pass_expert_pack_spec_2026-04-23.md`
2. one quarantine-aware sidecar containing at least:
   - `sku_key`
   - `stock_id`
   - `estimated_current_stock`
   - `return_in_qty`
   - `active_stock_if_return_in_not_active`
   - `family_quarantine_candidate_units`
   - `family_qc_rows`
   - `quarantine_bucket_mix`
   - `needs_family_recompute`
3. any recomputed aggregate stock / concentration / valuation outputs that change because of the quarantine overlay

Also include these files in the pack spec as authoritative quarantine inputs:

- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_summary.md`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_backlog.csv`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/employee_qc_queue.csv`

## Constraints

- Keep changes surgical.
- Prefer read-only export regeneration over DB mutation.
- Do not rerun broad stock reconstruction unless the narrowed subset path proves impossible.
- Do not narratively smooth quarantine units into active stock.
- Do not present LINE52 manual recount as active-only unless you can prove quarantine exclusion from repo evidence.
- No DB writes without backup-first, env gate, CLI gate, and explicit logging.

## Validation

Run the smallest relevant checks for any changed code or exported logic.

At minimum:

- targeted tests first, if code changed
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs/spec files changed

If you only regenerate read-only pack artifacts and handoff files, do not rerun unrelated broad gates just for ceremony. Instead, record the already-known repo-wide red gates as inherited stoplines.

## Output

Update:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_a_execution_log.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/status_board.md`

Log:

- ordered actions
- commands run
- files changed
- output paths
- pass/fail validations
- whether the second-pass expert pack is now quarantine-aware
- remaining stoplines before external second pass
