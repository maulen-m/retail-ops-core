# Agent 21 - Ads, Pricing, and LINE31 Scout

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
- Rebaseline Phase-2/facing gates `G-ADS-02`, `G-ADS-03`, `G-PRICE-01`, `G-PRICE-04`, and `G-LINE31-01`.
- Determine whether any gate can be promoted from current source freshness, zero-spend/armed-guard evidence, or existing validation artifacts.
- Identify exact current blockers, required validators, and whether any external action would be required later.

Allowed:
- Read files and local DBs read-only.
- Run read-only validators and shell commands.
- Write only `~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_post_rebaseline_scouts/agent21_ads_pricing_line31_scout_closeout.md`.

Forbidden:
- Production DB writes, code edits, config edits, workbook edits, dashboard/status/scoreboard edits, LaunchAgent changes, Telegram/Kaspi/Repricer/browser/external writes, ad-platform writes, pricing uploads, and shell-sourcing `.env`.
- Running any script with `--apply` or any write-enable env gate.

Closeout must include:
- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Current production DB SHA before/after your scout commands.
- Commands run and outputs summarized.
- Per-gate current state, evidence path, and next safe command.
- External-write approvals needed later, if any, stated as explicit stoplines.

