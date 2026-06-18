# Agent D - Depletion Extraction And Ranking

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/PLAN.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-25_april23_stock_reanchor_copied_temp/VALIDATOR_MATRIX.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/00_SUBORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/APRIL23_STOCK_REANCHOR_COPIED_TEMP_20260525_STARTERS/04_AGENT_D__DEPLETION_EXTRACTION_RANKING__AFTER_01_02.md`
7. Agent A and Agent B closeout paths after completion.

## Assignment

Build the post-anchor depletion candidate and ranked movement tables for `2026-04-24..2026-05-25`. Use only identity-bearing and lifecycle-supported rows for SKU-size deduction. Quarantine unresolved rows.

No production DB writes, workbook mutation, source-pointer writes, scheduler changes, external writes, merchant stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Outputs

Write closeout and evidence under:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-25_april23_stock_reanchor_copied_temp/agent_d_depletion_extraction_ranking/`

Required files:

- `agent_d_depletion_extraction_ranking_closeout.md`
- `post_anchor_depletion_candidates.csv`
- `post_anchor_depletion_ranked.csv`
- `post_anchor_unmatched_or_quarantined.csv`
- `POST_ANCHOR_SOURCE_RANKING_DECISION.md`
- `POST_ANCHOR_REPLAY_WINDOW_COVERAGE.json`

## Gate

Use `Gate: GREEN` only when every deducted movement is identity-bearing and lifecycle-supported.

Use `Gate: YELLOW` when source gaps or quarantines remain visible.

Use `Gate: RED` if unresolved rows are deducted, cancelled/returned rows are added back without return-QC, or source gaps are hidden.
