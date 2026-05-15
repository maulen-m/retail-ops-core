# PROMPT_AGENT_C — Audit Stock Anchor Salvage Under Quarantine Rules

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PLAN.md`
5. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Role

You are Agent C, read-only analyst.

Your job is to determine what remains valid from the external stock-anchor rebuild now that the repo has a separate return/cancel quarantine contract.

## Independence Rule

Do not read Agent B's report before publishing your own first-pass report.

## Primary Question

Which parts of the external expert's stock rebuild remain usable evidence, and which parts must now be downgraded, blocked, or recomputed because:

1. the valuation layer was base-only / lower-bound
2. the new quarantine contract exists
3. stock investigation originally started before returns/cancels were separated cleanly

## Inspect What You Need

Likely high-priority surfaces:

- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/External_expert_answer/External_expert_answer.md`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/stock_anchor_selection_and_rebuild_v2_report_2026-04-23.md`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/current_stock_rebuild_2026-04-23.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/movement_replay_2026-04-23.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/inventory_business_eval_tables_2026-04-23.xlsx`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_summary.md`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_backlog.csv`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/employee_qc_queue.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/Line52_16.4.26_manual_recount_ (after_16th aprilshipping).md`

Inspect extra artifacts only if needed.

## Required Findings

Your report must answer:

1. What remains valid from the composed-anchor logic itself?
2. Which totals or promotion recommendations are no longer safe because of quarantine truth?
3. Does the external movement replay already include return legs, and if yes, what still remains missing for active-stock truth?
4. Which SKU families can be tentatively promoted now?
5. Which families must remain owner-review?
6. Which families must remain blocked?
7. What exact files, assumptions, and clarifications must be included in the second-pass expert pack?
8. Should the second pass recompute everything, or only the blocked / affected subset?

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not assume returned stock is active stock.
- Do not turn the current rebuild into decision-grade truth by narrative smoothing.

## Output

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`

Use this shape:

1. Findings (highest severity first)
2. What remains usable
3. What must be downgraded or blocked
4. Exact pack additions / corrections for the second pass
5. Recommended next step for Agent A
6. Commands run
