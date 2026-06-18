# Agent C - Anchor Normalization

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/03_AGENT_C__ANCHOR_NORMALIZATION__AFTER_01.md`
7. Agent A closeout path after completion.

## Assignment

After Agent A closes out, normalize the April 23 `Current_Stock_Rebuild` anchor into deterministic CSV artifacts. Keep all risk flags visible.

No production DB writes, workbook mutation, source-pointer writes, scheduler changes, external writes, merchant stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_c_anchor_normalization/`

Required files:

- `agent_c_anchor_normalization_closeout.md`
- `april23_anchor_normalized.csv`
- `april23_anchor_audit.csv`
- `april23_anchor_quarantine_seed.csv`
- `APRIL23_ANCHOR_NORMALIZATION_REPORT.md`

## Gate

Use `Gate: GREEN` only if normalized totals reconcile and all risks are visible.

Use `Gate: YELLOW` if retained risks remain.

Use `Gate: RED` if quantities are changed without audit, missing COGS is zeroed, or blocked rows are hidden.
