# Orchestrator Handoff - LINE31 Final Creative Meta Publish

Created: 2026-06-01 15:28 +05

Gate: READY_WHEN_FINAL_CREATIVE_EXISTS

## Objective

Use this starter only after the owner provides the final LINE31 creative asset URI, thumbnail, and SHA-256 mapping, or when an execution agent is assigned to fill that mapping from final local files.

The lane should produce a launch-ready or published closeout without widening scope beyond LINE31 countrywide Meta.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-06-01_line31_final_creative_meta_publish/PLAN.md`

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS`

## Shared Handoff Folder

`~/Docs/Autonomous_business_agent_handoffs/2026-06-01_line31_final_creative_meta_publish`

## Evidence Root

`~/Docs/Autonomous_business/exports/validation/line31_goal_stock_dashboard_repair_20260601_133438`

## Launch Order

Single serialized agent:

- Agent 1: final creative mapping validation, final approval check, and LINE31 countrywide Meta publish readiness/publish closeout.

Do not parallelize the final publish step.

## Required Launch Line

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md.
```

## Boundary

This starter does not itself authorize publish. The agent must find the exact owner approval phrase from the intake file after the final creative mapping is filled and strict validation passes.

Internal Kaspi LINE31 campaigns remain ON unless there is separate explicit owner approval to pause them.
