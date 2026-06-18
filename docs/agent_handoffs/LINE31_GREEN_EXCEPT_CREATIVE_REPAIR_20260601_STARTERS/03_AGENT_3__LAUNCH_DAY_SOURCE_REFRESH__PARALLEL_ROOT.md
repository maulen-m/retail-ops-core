# Agent 3 Starter - Launch-Day Source Refresh

You are Agent 3. Your lane refreshes launch-day source context without live writes.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Business_3/Facebook_ads/AGENTS.md`
2. `~/Docs/Web_automation/AGENTS.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_green_except_creative_repair/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_GREEN_EXCEPT_CREATIVE_REPAIR_20260601_STARTERS/03_AGENT_3__LAUNCH_DAY_SOURCE_REFRESH__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent1_facebook_ads_scaffold_closeout.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent3_web_automation_line31_context_closeout.md`

## Scope

Allowed:

- read-only Meta/Facebook, website-event, Web_automation, and Kaspi Marketing context refreshes using existing repo methods;
- local evidence under `Facebook_ads` and `Web_automation`;
- assigned closeout.

Forbidden:

- Meta publish or mutation;
- Kaspi campaign/promo mutation;
- source-pointer/scheduler changes;
- price/stock/cash/PO/supplier changes;
- website deploy.

## Task

Refresh current launch-day context for the final bridge:

- current Meta scaffold and any available Meta traffic source truth;
- website event source state if available;
- current LINE31 internal Kaspi campaign and promo context;
- mark prelaunch Meta/web rows as `PRELAUNCH_NOT_APPLICABLE` when there is no launched Meta campaign yet, instead of `MISSING_FOR_LAUNCH_DAY`;
- preserve attribution rule: directional only while internal LINE31 surfaces remain ON.

## Required Outputs

Evidence folder:

`~/Docs/Business_3/Facebook_ads/exports/validation/line31_green_except_creative_repair_20260601/source_refresh/`

Required files:

- `launch_day_source_refresh_matrix.csv`
- `prelaunch_metric_classification.md`
- `internal_kaspi_noise_refresh.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_green_except_creative_repair/agent3_launch_day_source_refresh_closeout.md`

Closeout must include standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.

Use `GREEN` if source context is current or properly classified as prelaunch-not-applicable. Use `YELLOW` for stale context. Use `RED` for mutation attempt.
