# Agent828 - Current Boundary Re-Anchor

Gate target: `GREEN` if you produce a current read-only boundary packet for the live protected surfaces without mutation.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_source_decision_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_SOURCE_DECISION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent827_mvos_command_board/MVOS_PRODUCTION_LANE_READINESS_MATRIX.tsv`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/orchestrator_review_agent827_20260515_113916.md`
7. this starter prompt

## Assignment

Produce a current-boundary re-anchor packet for DB SHA awareness after Agent827.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent828_current_boundary_reanchor/`

Required report:

`~/Docs/Autonomous_business/exports/validation/mvos_source_decision_wave/20260515_134601/agent828_current_boundary_reanchor/CURRENT_BOUNDARY_REANCHOR_PACKET.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_source_decision_wave/agent828_current_boundary_reanchor_closeout.md`

## Required Checks

- Capture start and final SHA-256 for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Capture `PRAGMA integrity_check`.
- Capture `lsof` and SQLite sidecar state for `db/app.db`.
- Capture protected-path `git status --short -- db/app.db excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Capture current high-level blocker/gate rows if available: source freshness, policy gate, exception queue counts, and key table max dates/counts.
- Preserve the distinction between current DB `b81d6290...` and prior copied-temp DB `9702c20...`.

## Boundaries

Read-only production surfaces. No copied-temp mutation required. No production DB write, workbook write, scheduler mutation, external write, owner publication, cash, PO, ads, price, stock, or lifecycle/status production repair.

Gate: GREEN
