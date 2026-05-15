# Agent825 - Boundary / Release Anchor Monitor

Gate target: `GREEN` if you maintain a current boundary monitor packet and detect no unexplained drift.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_mvos_execution_wave/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent817_codecaptain_packet_writer_closeout.md`
6. this starter prompt

## Assignment

Monitor the protected boundary while the MVOS wave runs.

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/agent825_boundary_release_anchor_monitor/`

Required report:

`MVOS_BOUNDARY_MONITOR.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/agent825_boundary_release_anchor_monitor_closeout.md`

## Required Checks

- DB/workbook SHA samples at start and final, and midpoint if the lane runs long.
- DB integrity.
- `lsof` for DB/workbook.
- SQLite sidecar files.
- Protected git status for `db/app.db` and `excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Classification: no drift, authorized daily ops drift, authorized apply drift, or unknown drift.

## Boundaries

Read-only plus local evidence/closeout writes only. Do not run production validators that write outside your evidence root. Do not run `manage_business_automation.py verify` unless you can force output into your evidence root and explain any side effects.

Gate: GREEN
