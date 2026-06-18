# Agent 22 - Scheduler, Alert, and Ops Scout

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/START_HERE.md`
4. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/STATUS.md`
5. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_path_run/scoreboard.csv`
6. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/green_gates.csv`
7. `~/Docs/Autonomous_business/docs/plan/green_path_2026-06/dashboard/DASHBOARD_UPKEEP.md`
8. this starter prompt.

Assignment:
- Rebaseline `G-SCHED-01`, `G-SCHED-02`, `G-SCHED-03`, `G-SCHED-05`, and `G-ALERT-02`.
- Inspect LaunchAgents in presence-only/redacted form. Do not print tokens, chat IDs, message contents, or customer/operator PII.
- Determine which gates can be promoted by existing evidence, which require a live observation window, and which require unpausing a job later.

Allowed:
- Read files, logs, and launchd state with redaction/presence-only handling.
- Run read-only validators and shell commands.
- Write only `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts/agent22_sched_alert_ops_scout_closeout.md`.

Forbidden:
- Production DB writes, code edits, config edits, workbook edits, dashboard/status/scoreboard edits, LaunchAgent load/unload/bootstrap/bootout/kickstart changes, Telegram/Kaspi/Repricer/browser/external writes, and shell-sourcing `.env`.
- Printing secrets or PII.
- Running any script with `--apply` or any write-enable env gate.

Closeout must include:
- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current production DB SHA before/after your scout commands.
- Commands run and outputs summarized without secrets.
- Per-gate promotion/blocker recommendation and exact observation window needed.
- Whether daily business automations can remain paused or must be resumed for proof.

