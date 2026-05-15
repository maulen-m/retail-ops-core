# Agent777 - Non-Ads Owner-Publication Blocker Map

## Mission

Map the remaining non-ads owner-publication blockers after the STOREB ads fix.

Focus on cashflow, stock/order truth, PO/inbound truth, exception queue, and warning cohorts. Do not solve them; produce the exact clearing checklist and safest parallelization plan.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/.claude/OPERATING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_PLAN_20260512_131702.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/FIXED_EXECUTION_BOUNDARY_C3_WAVE_ORCHESTRATOR_HANDOFF_20260512_131702.md`
6. `~/Docs/Autonomous_business/docs/agent_handoffs/FIXED_EXECUTION_BOUNDARY_C3_WAVE_STARTERS_20260512_131702/03_AGENT_777__NON_ADS_PUBLICATION_BLOCKER_MAP__PARALLEL_ROOT.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/owner_publication_readiness_delta_after_storeb_prod_apply_20260512_122050_agent774_closeout.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/mvos_phase_c_plus_20260511_154019_agent766_owner_publication_delta_closeout.md`

Sibling Agents775 and 776 run in parallel. Treat your result as provisional until Agent775 resolves the current boundary drift.

## Assigned Closeout

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent777_non_ads_publication_blocker_map_20260512_131702_closeout.md`

## Assigned Evidence Root

`~/Docs/Autonomous_business/exports/validation/fixed_execution_boundary_c3_wave/20260512_131702/agent777_non_ads_blockers`

Create this folder if needed. You may write only inside this evidence root and to the assigned closeout.

## Scope

Allowed:

- Read repo docs, scripts, current DB, and prior closeouts.
- Run read-only DB queries and validators/reporters when outputs are under the assigned evidence root.
- Write evidence files under the assigned evidence root.
- Write the assigned closeout.

Forbidden:

- No production DB mutation.
- No protected workbook mutation.
- No copied-temp repair unless it is only diagnostic and fully contained under the assigned evidence root.
- No scheduler, LaunchAgent, plist, cron, Web_automation, browser/session, external writes, owner publication, owner approval request, cash, PO, ad-spend, price, or stock action.
- No hiding, clearing, downgrading, or productizing warning cohorts.

## Required Checks

At minimum, map:

- `cashflow_source_truth`
- `stock_source_truth`
- `po_source_truth`
- `exception_queue`
- warning cohorts:
  - `fact_order_entry_product_identity_quarantine`
  - `fact_order_entry_header_only_source_gap_quarantine`

Suggested commands:

```bash
sqlite3 -readonly -header -csv db/app.db "SELECT domain, gate_name, status, severity, blocks_owner_publication, message, created_at, run_id FROM v_policy_gate_latest ORDER BY domain, gate_name;"
sqlite3 -readonly -header -csv db/app.db "SELECT policy_source_id, as_of_date, max_observed_at, row_count, freshness_status, blocks_publication, created_at, run_id FROM v_source_freshness_current ORDER BY policy_source_id;"
sqlite3 -readonly -header -csv db/app.db "SELECT status, severity, domain, reason, COUNT(*) AS n FROM exception_queue GROUP BY status, severity, domain, reason ORDER BY status, severity, domain, reason;"
sqlite3 -readonly -header -csv db/app.db "SELECT 'product_identity_quarantine' AS cohort, COUNT(*) AS rows, COUNT(DISTINCT order_id) AS distinct_orders, MIN(order_date) AS min_order_date, MAX(order_date) AS max_order_date, GROUP_CONCAT(DISTINCT store_code) AS stores FROM fact_order_entry_product_identity_quarantine UNION ALL SELECT 'header_only_source_gap', COUNT(*), COUNT(DISTINCT order_id), MIN(order_date), MAX(order_date), GROUP_CONCAT(DISTINCT store_code) FROM fact_order_entry_header_only_source_gap_quarantine;"
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict
python3 scripts/run_operational_stock_daily_truth.py --help
```

Run additional focused validators only after inspecting help and confirming output-contained behavior.

## Required Analysis

Closeout must include:

- Current blocker matrix by domain.
- Exact source freshness rows that block non-ads publication.
- Exception queue counts and exact reasons.
- Warning cohort counts and why they remain non-product truth.
- A ranked clearing checklist.
- Which clearing tasks can run in parallel after boundary acceptance.
- Which tasks require human approval before production apply or owner-facing use.

## Gate Rules

Use:

- `Gate: GREEN` if the non-ads blocker map is complete and actionable.
- `Gate: YELLOW` if blockers are clear but some evidence sources or command contracts still need review.
- `Gate: RED` if current evidence is unstable, missing, or unsafe to summarize.

The closeout must include a standalone line exactly like:

`Gate: YELLOW`

## Completion

After writing the closeout, run the tmux completion command appended by the orchestrator. Do not manually ping any pane.
