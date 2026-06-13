# Agent 2 - Phase 2 Lines FX Profit Cash Scout

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_2_lines_fx_profit_cash_scout_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`

Role: read-only scout for `PKT-LINES`, `PKT-FX`, `PKT-PROFIT`, and `PKT-CASH`. You may write only your assigned closeout file.

Tasks:

- Re-baseline entry numbers read-only for the entries hole, status-event freshness, COGS completeness by month, FX freshness, and cash anchor state.
- Identify the exact scripts and env gates the writer must use for the first `PKT-LINES` apply.
- Flag any mismatch between the packet and current validator/script behavior.
- Check the addendum rule: `PKT-FX` before any `PKT-PROFIT` apply that depends on FX.
- Do not run apply paths. Do not mutate DB, repo files, LaunchAgents, workbooks, or external systems.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include read-only commands and current baseline counts.
- Use `Gate: YELLOW` if the first writer lane is feasible but needs packet adjustment.
- Use `Gate: RED` only if `PKT-LINES` cannot safely start.
