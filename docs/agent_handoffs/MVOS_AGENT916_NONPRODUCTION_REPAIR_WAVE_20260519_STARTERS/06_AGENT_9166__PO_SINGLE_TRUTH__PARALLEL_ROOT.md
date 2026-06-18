# Agent9166 Starter - PO/Single-Truth Reconciliation Route

You are Agent9166. Your lane is read-only/evidence-only.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT916_NONPRODUCTION_REPAIR_WAVE_20260519_STARTERS/06_AGENT_9166__PO_SINGLE_TRUTH__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent915_copied_temp_proof_wave/agent915_copied_temp_mvos_proof_closeout.md`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9166_po_single_truth_evidence/`

Do not edit repo files, DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, or ad platforms.

## Task

Create the exact canonical refresh route for PO money and single-truth blockers.

Preserve Line61 shortage as accepted real business truth:

- ordered/cargo `115`;
- actual received `92`;
- shortage `23`;
- XL `7`;
- 2XL `5`;
- 3XL `6`;
- 4XL `5`;
- classification `PO_ACCEPTED_REAL_SHORTAGE_LINE61_2026_05_OWNER_CONFIRMED`.

Do not use Line61 shortage to green unrelated PO failures.

Required outputs:

- `PO_SINGLE_TRUTH_REPAIR_PLAN.md`
- `PO_PART_HISTORY_MISMATCH_MATRIX.tsv`
- `PO_BASE_PAYMENT_MISMATCH_MATRIX.tsv`
- `PO4_TOTAL_WEIGHT_ROUTE.md`
- `COMMANDS_RUN.tsv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9166_po_single_truth_closeout.md`

The closeout must include:

`Gate: GREEN`

Use `GREEN` only if the route preserves Line61 truth and keeps PO money, part-history, base-payment, and alignment blockers visible. Use `YELLOW` if later write approval is needed. Use `RED` for boundary violation or false-green risk.
