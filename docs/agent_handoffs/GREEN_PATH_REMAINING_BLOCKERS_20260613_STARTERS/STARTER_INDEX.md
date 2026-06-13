# Green Path Remaining Blockers 20260613 Starter Index

Workflow: clear the remaining active C3 blockers after lines, residuals, FX, and bank source route have been repaired.

Canonical plan inputs:

- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
- `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_14_bank_source_route_closeout.md`

Shared closeout folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/`

Current active C3 blocker set after Agent 14:

- `src_ab_db_ads_truth`: STALE, ads tables max `2026-05-11`.
- `src_ab_db_cashflow_truth`: STALE, `fact_cashflow_daily` max `2026-05-31`.
- `src_ab_db_sales_truth`: STALE, `sales_fact_v2` max `2026-05-31`.
- `src_ab_db_stock_truth`: STALE, stock tables max `2026-05-31`.
- `src_facebook_ads_external_ads`: STALE, accepted packet max `2026-05-04`.
- `src_web_automation_kaspi_marketing_directapi`: BLOCKED, accepted packet max `2026-05-04`.

Launch order:

1. Agents 15, 16, and 17 may run in parallel.
2. Agent 15 has the only Autonomous_business production DB write lease in this wave.
3. Agent 16 works in `~/Docs/Web_automation` only and must not mutate Autonomous_business DB.
4. Agent 17 works in `~/Docs/Business_3/Facebook_ads` only and must not mutate Autonomous_business DB or perform ad-platform writes.
5. The orchestrator reads all closeouts before materializing combined AB source/gate rows again.

Starter prompts:

- `15_AGENT_15__AB_INTERNAL_FRESHNESS_WRITER__PARALLEL_ROOT.md`
- `16_AGENT_16__WA_KASPI_MARKETING_PACKET__PARALLEL_ROOT.md`
- `17_AGENT_17__META_SOURCE_PACKET_BOUNDARY__PARALLEL_ROOT.md`

Do not claim overall GREEN from a single lane. A lane can be GREEN only for its assigned blocker set; overall source/gate GREEN requires orchestrator rerun after all closeouts.
