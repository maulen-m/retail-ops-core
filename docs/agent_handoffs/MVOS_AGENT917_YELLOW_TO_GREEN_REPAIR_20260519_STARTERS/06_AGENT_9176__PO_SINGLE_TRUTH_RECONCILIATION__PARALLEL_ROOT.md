# Agent9176 Starter - PO/Single-Truth Reconciliation

You are Agent9176. Your lane is read-only/evidence-only with respect to repo state.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT917_YELLOW_TO_GREEN_REPAIR_20260519_STARTERS/06_AGENT_9176__PO_SINGLE_TRUTH_RECONCILIATION__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-19_mvos_agent916_nonproduction_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9167.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_copied_temp_rerun_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/031_validate_single_truth_system.stdout.txt`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/034_validate_single_truth_alignment.stdout.txt`
11. `~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent916_nonproduction_repair_wave/agent9167_implementation_copied_temp_rerun_evidence/validator_outputs/035_validate_po_money_gate.stdout.txt`

## Scope

Write only under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9176_po_single_truth_reconciliation_evidence/`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-19_mvos_agent917_yellow_to_green_repair_wave/agent9176_po_single_truth_reconciliation_closeout.md`

Do not edit repo files, production DB, workbooks, config, source pointers, schedulers, Web_automation, external systems, supplier payments, cash, stock, prices, PO commitments, or owner publication.

## Task

Create the exact canonical reconciliation route for PO/single-truth blockers.

Preserve accepted Line61 shortage exactly:

- ordered/cargo `115`;
- actual received `92`;
- shortage `23`;
- size shortage XL `7`, 2XL `5`, 3XL `6`, 4XL `5`;
- this clears unknown mismatch only; it does not green unrelated PO money, cost, alignment, or dashboard failures.

Targets:

- `17` historical DB-only part IDs;
- PO-4 total/weight mismatch;
- PO-5.2/PO-6 base-payment mismatches;
- inventory cost drift and single-truth alignment failures;
- PO money gate retained failures.

## Required Outputs

Inside your evidence folder:

- `PO_SINGLE_TRUTH_CANONICAL_RECONCILIATION_PLAN.md`
- `PO_PART_HISTORY_MISMATCH_MATRIX.tsv`
- `PO_BASE_PAYMENT_MISMATCH_MATRIX.tsv`
- `PO_MONEY_GATE_CLOSURE_CONDITIONS.tsv`
- `COMMANDS_RUN.tsv`

The closeout must include a standalone line:

`Gate: <GREEN/YELLOW/RED>`

Use `GREEN` only if Agent9178 receives an exact copied-temp-safe reconciliation route. Use `YELLOW` if production/workbook correction is required later. Use `RED` for boundary violation or Line61-shortage false-green risk.
