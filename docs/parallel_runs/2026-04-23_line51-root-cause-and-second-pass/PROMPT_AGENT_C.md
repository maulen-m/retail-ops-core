# PROMPT_AGENT_C — Cross-Family Overstatement Sensitivity Audit

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

You are Agent C, read-only analyst.

## Objective

Determine whether LINE51’s apparent overstatement is local or part of a broader pattern affecting other top-value or top-unit families.

## Primary Questions

1. Does the evidence support a global haircut rule?
2. If not, which families appear uniquely exposed?
3. Which top families are likely still directionally usable without strong override?
4. Which families should remain blocked or owner-review only?
5. What family-level guidance should Agent A encode into an interim decision sidecar?

## Minimum Families To Inspect

- `CL_OC_MEN_LINE51_WHITE`
- `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
- `CL_OC_MEN_LINE52_BLACK`
- `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK`
- `CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE`
- `CL_NEW-CLO_MEN_T-SHIRT_BLACK`

Inspect more if the evidence forces it.

## Required Deliverable

Write:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_c_report.md`

Use this structure:

1. Findings (highest severity first)
2. Is a global correction factor justified?
3. Family-by-family sensitivity table
4. Which families are:
   - usable with caution
   - require family override
   - remain blocked
5. What Agent A should encode for interim business use
6. What the external expert must be told explicitly
7. Commands run

## Constraints

- Do not modify repo files.
- Do not mutate `db/app.db`.
- Do not read Agent B's report before publishing your own first-pass findings.
- Do not confuse physical-stock plausibility with active-stock truth; quarantine remains a separate bucket.
