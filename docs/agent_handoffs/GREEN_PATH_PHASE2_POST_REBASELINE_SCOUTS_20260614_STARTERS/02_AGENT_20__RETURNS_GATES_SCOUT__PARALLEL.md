# Agent 20 - Returns Gates Scout

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/START_HERE.md`
4. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/STATUS.md`
5. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_gates.csv`
7. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/starter_pack/03_packets_phase2.md`
8. this starter prompt.

Assignment:
- Rebaseline `G-RET-01`, `G-RET-02`, and related return-QC/event surfaces.
- Inspect the predicate, QC writer, returns economics validator, and schemas enough to say what is missing for a safe implementation.
- Classify the narrowest no-human implementation path versus the first point where physical QC/staff adoption is required.

Allowed:
- Read files and DB.
- Run read-only validators and shell commands.
- Write only `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts/agent20_returns_gates_scout_closeout.md`.

Forbidden:
- Production DB writes, code edits, config edits, workbook edits, dashboard/status/scoreboard edits, LaunchAgent changes, Telegram/Kaspi/Repricer/browser/external writes, and shell-sourcing `.env`.
- Running any script with `--apply` or any write-enable env gate.

Closeout must include:
- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current production DB SHA before/after your scout commands.
- Commands run and outputs summarized.
- Exact blocker rows/counts for returned-to-warehouse, return_qc_event, and return economics.
- Next safe implementation lane and whether human/staff action is required.

