# Agent 50 - Option B Production Baseline Catch-Up Temp Replay After Agent 49 RED

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_50_option_b_production_baseline_catchup_temp_replay_after_49_red_closeout.md`

## Dependency

Do not start until Agent 49 is complete and reviewed by the orchestrator.

Required review:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_49.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_option_abc_decision_grade_sequence/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_46.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_47.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/ORCHESTRATOR_REVIEW_AFTER_AGENT_49.md`
9. Agent 46, 47, and 49 closeouts and evidence
10. this starter prompt

## Mission

Find the minimum safe way to bring a current-production-derived temp DB to the accepted Agent 46 baseline.

Agent 49 proved the two-row STOREB residue cleanup works on temp, but also proved current production is behind Agent 46:

- `stock_ledger`, `sales_fact_v2`, and `fact_cashflow_daily` are stale in production;
- `ads_source_refresh_runs` and `ads_campaign_product_daily` are empty in production;
- source/gate validators fail beyond the known `exception_queue` limitation.

Your job is to identify and, if safe on temp only, replay the reviewed materialization sequence needed to reproduce Agent 46 from current production.

## Write Boundary

Allowed:

- temp DB and evidence under `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_50_evidence/`;
- assigned closeout.

Forbidden:

- production `db/app.db` writes;
- workbook edits;
- Web_automation writes;
- external/live calls;
- ad hoc production SQL;
- copying Agent 46 tables into production;
- weakening validators.

## Required Work

1. Read Agent 46, 47, and 49 closeouts and evidence.
2. Copy current production `db/app.db` to:
   `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_option_abc_decision_grade_sequence/agent_50_evidence/agent50_prod_baseline_catchup_temp_20260505.db`
3. Build a before matrix comparing current production, Agent 49 temp, and Agent 46 accepted temp for at least:
   - `fact_inventory_snapshot_size`
   - `stock_ledger`
   - `sales_fact_v2`
   - `order_status_event`
   - `fact_order_entries_kaspi`
   - `ads_source_refresh_runs`
   - `ads_campaign_product_daily`
   - `fact_cashflow_events`
   - `fact_cashflow_daily`
   - `fact_order_entry_product_identity_quarantine`
   - `policy_source_freshness`
   - `policy_gate_result`
4. Identify the exact scripts/materializers and evidence files that produced the Agent 46 accepted temp state. Prefer existing scripts; do not invent SQL.
5. On the Agent 50 temp DB only, replay the sequence if and only if the scripts and env gates are clear. Candidate categories to inspect:
   - order/lifecycle/order-entry refresh;
   - sales fact and stock ledger replay;
   - inventory snapshot refresh;
   - ads DirectAPI sidecar/materializer from Web_automation evidence;
   - cashflow rebuild through `2026-05-04`;
   - STOREB quarantine apply including the two product-cashflow residue rows;
   - source freshness and policy gate materialization.
6. If a replay step is not safe or not discoverable, stop before that step and write the exact blocker.
7. Rerun the Agent 46 validator set on the Agent 50 temp DB after any replay:
   - operational stock integration gates;
   - policy gate results;
   - source freshness;
   - order cashflow coverage;
   - cashflow invariants;
   - cashflow actual/model separation;
   - ads sidecar readiness;
   - ads offer-universe coverage;
   - ads spend reality;
   - DB integrity.
8. State whether production apply can be re-authorized. If not, provide the exact next minimal lane.
9. Provide a production apply contract only if fully supported by temp proof:
   - exact scripts;
   - env gates;
   - expected row deltas;
   - backup path requirements;
   - rollback command family;
   - validators and expected statuses.

## Expected Gate

`GREEN` only if current-production-derived temp DB reaches the Agent 46 accepted baseline or better, with only accepted visible limitations and production untouched.

`YELLOW` if the root mismatch is fully classified and a safe production apply contract is ready but not yet executed.

`RED` if temp replay regresses, cannot identify safe scripts, or leaves source/gate blockers unexplained.
