# PROMPT_AGENT_A — Build Override-Ready Active-Stock Sidecar And External Second-Pass Bundle

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_line51-root-cause-and-second-pass/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_b_report.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_c_report.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_a_execution_log.md`
8. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass`

## Role

You are Agent A, the only write-capable execution agent for this run.

## Objective

Use Agent B and Agent C findings to build the smallest safe internal decision surface and the best possible external second-pass bundle.

This is not a broad stock rewrite. Your job is to:

1. synthesize the LINE51 root-cause findings
2. decide whether any family-level override is justified
3. create an override-ready, quarantine-aware active-stock sidecar
4. prepare the corrected context bundle and prompt for the external expert

## Primary Questions

1. Does LINE51 need a temporary family-level override, and if so what should the rule look like?
2. Is any global correction factor justified by evidence, or must corrections stay family-specific?
3. What exact files and assumptions should the external expert receive next?

## Expected Outputs

Produce or update, at minimum:

1. a short execution summary in:
   - `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_a_execution_log.md`
2. one operator-facing sidecar folder under the shared handoff folder, containing:
   - `active_stock_sidecar_2026-04-23.csv`
   - `family_override_recommendations_2026-04-23.md`
   - `external_second_pass_context_checklist_2026-04-23.md`
   - `external_second_pass_prompt_2026-04-23.md`
3. update:
   - `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/status_board.md`

## Sidecar Requirements

The sidecar should be practical and explicit, not magical. Include at least:

- `sku_key`
- `my_size`
- `stock_id`
- current rebuilt quantity
- quarantine-sensitive quantity if applicable
- active-stock estimate after Agent B/C findings
- confidence label
- override source / rationale
- whether the row is safe for:
  - owner review
  - active-stock use
  - PO use

If LINE51 receives a family-total override, preserve that explicitly as an override layer, not as silent truth replacement.

## Constraints

- Keep changes surgical.
- Prefer read-only export regeneration over DB mutation.
- Do not hide uncertainty.
- Do not apply a blanket 20% haircut unless B/C evidence clearly justifies it.
- If B/C findings do not justify a global rule, preserve family-specific handling.
- No DB writes unless backup-first, env-gated, CLI-gated, and explicitly logged.

## Validation

If you only regenerate read-only handoff artifacts and helper sidecars, run only the smallest relevant checks:

- targeted tests if code changes
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs or markdown specs changed

Do not rerun unrelated broad repo gates for ceremony if you did not change their domains. Instead record inherited red gates honestly.

## Output Shape

Your execution log must include:

- ordered actions
- commands run
- files changed
- whether LINE51 got an evidence-backed override recommendation
- whether a global correction factor was rejected or accepted
- the exact external-expert prompt path
- remaining stoplines
