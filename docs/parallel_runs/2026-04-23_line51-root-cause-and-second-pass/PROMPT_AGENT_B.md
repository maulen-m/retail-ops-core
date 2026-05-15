# PROMPT_AGENT_B — LINE51 Root-Cause Audit

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_line51-root-cause-and-second-pass/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`
6. this prompt

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass`

## Role

You are Agent B, read-only analyst.

## Objective

Audit `CL_OC_MEN_LINE51_WHITE` specifically and determine the most likely causes of overstatement in the external rebuild.

## Primary Questions

1. Is LINE51 stock likely overstated because sales are undercounted?
2. Is LINE51 stock likely overstated because return legs are being treated as active stock?
3. Are cancellations being misinterpreted or insufficiently modeled for LINE51?
4. Are there mapping / alias / duplicate article issues that inflate LINE51?
5. Is the March 2 anchor itself likely too high for LINE51?
6. If you had to rank root causes by likelihood, what is the order?

## High-Priority Sources

- external workbook and CSVs under:
  - `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer`
- quarantine exports:
  - `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_summary.md`
  - `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_backlog.csv`
  - `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/employee_qc_queue.csv`
- repo truth / order movement surfaces as needed
- previous repaired landed-cost and second-pass artifacts, only if they help answer LINE51 chronology

## Required Deliverable

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_b_report.md`

Use this structure:

1. Findings (highest severity first)
2. LINE51 chronology summary
3. Ranked root-cause candidates
4. What is proven vs what remains inference
5. Whether a LINE51 family-total override is justified now
6. Exact evidence / files Agent A should carry into the next step
7. Commands run

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read Agent C's report before publishing your own first-pass findings.
- Stay concrete and source-backed; avoid vague “maybe demand changed” narratives unless tied to data.
