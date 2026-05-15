# Agent755 - Web Automation Ads Freshness/Watchers Inventory

You are Agent755. Your task is a read-only first-pass inventory of Web_automation freshness, heartbeat, experiment-dashboard, scheduled-checkpoint, and watcher patterns that may help Autonomous Business resolve `ADS_SOURCE_STALE`.

Gate target: `GREEN`, `YELLOW`, or `RED`.

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_755_web_ads_freshness_watchers_inventory_closeout.md`

Assigned evidence directory:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_755_web_ads_freshness_watchers_inventory_evidence/`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/WEB_AUTOMATION_ADS_ADOPTION_DISCOVERY_CONTROL_20260510_215225.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CASH_RISK_DAILY_OPERATOR_REVIEW_SURFACE_20260510_200936.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
6. `~/Docs/Web_automation/AGENTS.md`
7. `~/Docs/Web_automation/Docs/00_START_HERE.md`
8. `~/Docs/Web_automation/Docs/marketing_watcher_plan.md`
9. this assigned starter prompt

You are not required to wait for Agents754 or 756. Do not read their reports before writing your own first-pass closeout.

## Scope

Inventory only these Web_automation areas unless evidence directly points elsewhere:

- `web_auto/experiment_dashboard.py`
- `web_auto/scheduled_checkpoints.py`
- `web_auto/marketing_experiments.py`
- `web_auto/cli.py` sections for `experiment-dashboard`, `scheduled-checkpoint`, and `kaspi-marketing watch`
- `config/schedules/line61_line51_checkpoints.yaml`
- `Docs/marketing_watcher_plan.md`
- docs surfaced by `rg` for `watch-health`, `heartbeat`, `allow-stale`, `live-readonly`, and `backfill-gaps`

## Hard Stoplines

- Do not run live fetches.
- Do not run scheduled checkpoints.
- Do not open browser or log in.
- Do not read `.env`, cookies, storage state, browser profile files, or secrets.
- Do not write inside `~/Docs/Web_automation`.
- Do not write inside `~/Docs/Autonomous_business` except if `agent_complete.py` writes completion metadata.
- Do not mutate DBs, workbooks, schedulers, LaunchAgents, ad platforms, Kaspi, Google, bank, or external systems.
- Do not treat `--allow-stale` as proof of freshness; document how stale remains visible.

## Deliverable

Write the assigned closeout with:

- standalone line `Gate: GREEN` if Web_automation freshness/heartbeat patterns are clearly reusable for an AB design-only adapter;
- `Gate: YELLOW` if promising but requiring live-readonly proof, operator rule, or CodeCaptain review;
- `Gate: RED` if reuse is unsafe or blocked.

Required sections:

- `Read Scope`
- `Freshness And Heartbeat Entrypoints`
- `Scheduled Checkpoint Modes`
- `Stale Source Handling`
- `Backfill Or Gap Handling`
- `Safety Boundaries`
- `Reusable Pieces For Autonomous Business`
- `Risks Or Unknowns`
- `Recommended Next Step`

Prefer exact file paths and line references. Keep the closeout compact but evidence-backed.
