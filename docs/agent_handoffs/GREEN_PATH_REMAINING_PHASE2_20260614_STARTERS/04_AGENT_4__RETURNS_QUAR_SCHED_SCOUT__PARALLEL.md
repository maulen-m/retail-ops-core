# Agent 4 - Returns, Quarantine, Scheduler Scout

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/green_path_run/DEFERRED_QUEUE.md`
7. `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_PHASE2_20260614_STARTERS/04_AGENT_4__RETURNS_QUAR_SCHED_SCOUT__PARALLEL.md`

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent4_returns_quar_sched_scout_closeout.md`

Role: read-only analyst. You may write only the assigned closeout file and temporary files under `/tmp/green_path_scratch/agent4_returns_quar_sched/`.

Objective:
Re-baseline returns, quarantine, and parked scheduler data gates so the orchestrator knows which lane is ready after COGS/FX/cash sequencing.

Required work:
- Inspect returns validators and current returns/QC state.
- Inspect quarantine/exception queue validators and current retained warning classes.
- Verify daily automations remain paused, then identify which parked scheduler jobs should clear after which Phase 2 data gates.
- Decide whether any returns/quarantine patch is safe before COGS/cash, or whether these lanes should wait.
- Keep warning quarantines visible; do not propose hiding retained blockers as green.

Suggested read-only commands:
- `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect paused`
- `python3 scripts/validate_returns_economics_audit.py`
- `python3 scripts/validate_exceptions_schema.py`
- `python3 scripts/validate_exception_queue_db.py`
- `python3 scripts/run_end_of_day.py --verbose` only if it is a dry-run/non-apply path under current repo contract; otherwise inspect logs/scripts and state why skipped.

Forbidden:
- No `--apply`.
- No write-enable env vars.
- No LaunchAgent load/unload.
- No Telegram sends.
- No DB, workbook, Kaspi, Repricer, browser, or WA writes.
- No edits to repo files except the assigned closeout.

Closeout must include:
- Standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Returns state and validator status.
- Quarantine/exception state and validator status.
- Scheduler parked-job dependency map.
- Exact recommended next action and stoplines.
- Commands run and key outputs.
