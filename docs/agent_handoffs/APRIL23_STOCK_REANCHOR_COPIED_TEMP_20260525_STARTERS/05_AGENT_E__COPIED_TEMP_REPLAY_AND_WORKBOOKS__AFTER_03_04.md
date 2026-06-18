# Agent E - Copied-Temp Replay And Workbooks

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/05_AGENT_E__COPIED_TEMP_REPLAY_AND_WORKBOOKS__AFTER_03_04.md`
7. Agent C and Agent D closeout paths after completion.

## Assignment

Run the copied-temp replay against the normalized April 23 anchor and ranked depletion rows. Generate the two review-only workbook outputs in an isolated folder.

No production DB writes, workbook mutation, source-pointer writes, scheduler changes, external writes, merchant stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_e_copied_temp_replay_and_workbooks/`

Required files:

- `agent_e_copied_temp_replay_and_workbooks_closeout.md`
- `COPIED_DB_BOUNDARY_SHA256.tsv`
- `april23_reanchored_stock_rows.csv`
- `april23_reanchor_deduction_lines.csv`
- `april23_reanchor_unmatched_deductions.csv`
- `april23_reanchor_quarantine_blockers.csv`
- `april23_reanchor_by_sku_value.csv`
- `APRIL23_REANCHOR_COPIED_TEMP_PROOF.json`
- rebuilt stock/COGS workbook;
- rebuilt inventory business evaluation workbook;
- workbook SHA256 file.

## Gate

Use `Gate: GREEN` only for copied-temp scope if replay is idempotent, totals reconcile, workbooks validate, and protected surfaces are unchanged.

Use `Gate: YELLOW` if retained blockers remain.

Use `Gate: RED` if production DB/workbook/source pointer/external surfaces are touched or if blockers are hidden.
