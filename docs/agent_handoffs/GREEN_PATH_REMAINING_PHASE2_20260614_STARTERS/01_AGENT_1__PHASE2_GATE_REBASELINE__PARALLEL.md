# Agent 1 - Phase 2 Gate Rebaseline

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/MASTER_REMEDIATION_PLAN.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_gates.csv`
7. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/scoreboard.csv`
8. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/STATUS.md`
9. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/01_AGENT_1__PHASE2_GATE_REBASELINE__PARALLEL.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent1_phase2_gate_rebaseline_closeout.md`

Role: read-only analyst. You may write only the assigned closeout file and temporary files under `/tmp/green_path_scratch/agent1_phase2_gate_rebaseline/`.

Objective:
Re-baseline the current Phase 2 gate state from the current workspace and repo mirror. Do not replay the original Phase-1 boundary assumption. Treat current scoreboard rows as authority where supported by current evidence.

Required work:
- Compare workspace and repo mirror `scoreboard.csv`, `STATUS.md`, and dashboard `progress-data.js`.
- Parse `green_gates.csv` and identify all Phase 2 gates still not GREEN, grouped by lane and dependency.
- Confirm daily business automations remain paused and DB guard is green using read-only commands.
- Identify the safest next single write lane for the orchestrator to run after scouts return.
- Surface contradictions, stale mirror data, or missing evidence as YELLOW/RED instead of smoothing them over.

Suggested read-only commands:
- `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect paused`
- `scripts/check_no_db_tracked.sh`
- `python3 - <<'PY' ...` for CSV/JS parsing if useful

Forbidden:
- No DB writes.
- No workbook writes.
- No LaunchAgent changes.
- No Telegram sends.
- No Kaspi, Repricer, Meta, or browser UI actions.
- No edits to repo files except the assigned closeout.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current counts: scoreboard rows, dashboard gates, ungreen Phase 2 gates.
- Exact next-lane recommendation with reason and stoplines.
- Commands run and key outputs.
