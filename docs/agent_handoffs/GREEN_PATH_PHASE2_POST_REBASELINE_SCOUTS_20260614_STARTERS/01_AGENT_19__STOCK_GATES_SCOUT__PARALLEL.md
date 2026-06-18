# Agent 19 - Stock Gates Scout

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
- Rebaseline only stock gates `G-STOCK-01`, `G-STOCK-02`, `G-STOCK-04`, and `G-STOCK-05`.
- Determine which can be promoted from existing evidence, which need a narrow code/evidence repair, and which require a standing observation window or owner/source fact.
- Inspect the actual validators/scripts enough to state what they check, not just whether they exist.
- Use read-only DB access only, preferably `file:db/app.db?mode=ro` or copied DB if a validator might mutate metadata.

Allowed:
- Read files and DB.
- Run read-only validators and shell commands.
- Write only `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts/agent19_stock_gates_scout_closeout.md`.

Forbidden:
- Production DB writes, code edits, config edits, workbook edits, dashboard/status/scoreboard edits, LaunchAgent changes, Telegram/Kaspi/Repricer/browser/external writes, and shell-sourcing `.env`.
- Running any script with `--apply` or any write-enable env gate.

Closeout must include:
- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current production DB SHA before/after your scout commands.
- Commands run and outputs summarized.
- Per-gate recommendation with exact evidence paths and next command.
- Whether human approval is required, with exact phrase only if unavoidable.

