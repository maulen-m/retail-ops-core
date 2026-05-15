# Agent818 - Daily Survival Brief Builder

Gate target: `GREEN` if you produce a review-only Daily Survival Brief v1 that is useful to the owner/operator and does not imply unauthorized action.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Oracle/Autonomous_business/2026-05-15/0920_TASK-000_post-order-entry-next-phase-proof-wave-codecaptain/Answer/Code Captain_15.05.2026_11_07_20.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-15/0920_TASK-000_post-order-entry-next-phase-proof-wave-codecaptain/BOUNDARY_GREEN_WARNING_BLOCKED_MATRIX.tsv`
7. this starter prompt

## Assignment

Build `DAILY_SURVIVAL_BRIEF_2026-05-15_DRAFT.md` under:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent818_daily_survival_brief/`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent818_daily_survival_brief_closeout.md`

## Required Content

- Trust banner with DB SHA, workbook SHA, as-of date, and evidence roots.
- Cash risk, order/shipping risk, inventory/stock risk, ads status, exception queue.
- Decisions marked `ALLOWED`, `REVIEW`, or `BLOCKED`.
- Plain-English owner/operator action list.
- Visible warning/blocker labels: `23`, `249`, `252`, STOREB ads mapping, cashflow staleness, PO delta `23`, and `9` open STOCK/HIGH exceptions.

## Boundaries

Read-only plus local evidence/brief/closeout writes only. No production mutation, workbook mutation, scheduler mutation, external write, owner publication/send, cash movement, supplier payment, PO commitment, ads/bid/budget change, price change, or stock change.

Gate: GREEN
