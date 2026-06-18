# Agent912A / Transport Agent9121 - Operational Source Refresh Packet

Gate target: `GREEN` if packet and copied-temp observations are complete without boundary violation. Otherwise `YELLOW` with exact unresolved routes.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_AGENT912_OPERATIONAL_SOURCE_REFRESH_C3_SPLIT_20260518_STARTERS/01_AGENT_9121__OPERATIONAL_SOURCE_REFRESH_PACKET__PARALLEL_ROOT.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT9115.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent911_retained_blocker_repair_wave/agent911e_combined_synthesis_rerun_closeout.md`
8. `~/Docs/Oracle/Autonomous_business/2026-05-18/225410_TASK-000_mvos-agent911-yellow-retained-blocker-codecaptain/answer/Code Captain_18.05.2026_23_25_41.md`

## Assignment

Create a copied-temp operational source refresh packet for the six stale operational tables identified by Agent9115 and CodeCaptain.

## Scope

Write scope:
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9121_operational_source_refresh_packet_evidence/`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9121_operational_source_refresh_packet_closeout.md`

Do not edit shared repo files. You are not alone in the codebase.

Allowed:
- read-only repo inspection;
- copied DB inside assigned evidence folder;
- copied-temp materializer dry-runs/applies only inside assigned evidence;
- validator reruns on copied DB;
- local evidence generation.

Forbidden:
- production DB writes;
- workbook writes;
- source-pointer writes;
- scheduler/external/Web_automation/Kaspi/API/WebUI writes;
- owner publication or production preflight.

## Required Work

1. Capture boundary:
   - `db/app.db` SHA;
   - CRM workbook SHA;
   - inbound workbook SHA if used;
   - DB integrity;
   - protected DB/workbook git status.
2. Copy `db/app.db` into the assigned evidence folder.
3. For each table, record max observed timestamp, row count, status, domain, and publication dependency:
   - `fact_inventory_snapshot_size`;
   - `stock_ledger`;
   - `sales_fact_v2`;
   - `order_status_event`;
   - `ads_source_refresh_runs`;
   - `ads_campaign_product_daily`;
   - `fact_cashflow_daily`;
   - `fact_cashflow_events`;
   - `fact_order_entries_kaspi`.
4. Determine whether each stale table has a valid copied-temp refresh/materializer/source route now.
5. If a copied-temp route exists and is already authorized by CodeCaptain/user boundary, test it only on the copied DB.
6. Rerun source freshness and policy gate validators on copied DB if meaningful.

## Required Artifacts

- `BOUNDARY_SNAPSHOT_AGENT9121.json`
- `OPERATIONAL_TABLE_REFRESH_BEFORE_AFTER.tsv`
- `OPERATIONAL_SOURCE_REFRESH_ROUTE_MATRIX.tsv`
- `SOURCE_PACKET_OR_MATERIALIZER_ROUTE.md`
- `VALIDATOR_REPLAY_RECOMMENDATION.md`
- command logs and copied DB integrity outputs

## Closeout

Write:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-18_mvos_agent912_operational_source_refresh_c3_split/agent9121_operational_source_refresh_packet_closeout.md`

The closeout must include:

```text
Gate: <GREEN/YELLOW/RED>
```

State whether Agent9125 can use your evidence for the combined copied-temp rerun.
