# Agent 1 - Baseline Preservation And Run Readiness

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_1_baseline_preservation_closeout.md`

Before executing, read:

1. `~/AGENTS.md` from chat context if available; otherwise `~/.codex/AGENTS.md`
2. `~/Docs/Autonomous_business/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
4. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`

Role: read-only baseline verifier. You may write only your assigned closeout file.

Tasks:

- Verify the private preservation pack exists at `~/Backups/green_path/20260613_1855_resume_preserve`.
- Confirm AB and WA are on branch `greenpath/20260613-phase2-truth`.
- Confirm daily ops are paused using `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect paused` from AB.
- Confirm `scripts/check_no_db_tracked.sh` passes in AB.
- Confirm the waybill repair closeout exists and reports 29 orders, 21 PDFs, and Telegram 21/21.
- Confirm backup `20260613_034450` still exists locally and the external backup path is reachable.
- Do not modify LaunchAgents, DBs, workbooks, configs, tracked files, or external systems.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include commands run and exact pass/fail summary.
- Use `Gate: RED` for missing preservation, active daily ops, tracked DB, missing backup, or missing waybill closeout.
