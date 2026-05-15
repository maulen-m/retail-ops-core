# Agent 6 - Serialized Source Refresh Execution

Mode: write-capable execution agent after Agents 1-5 are reviewed.

Status: UNBLOCKED FOR SAFE LOCAL IMPLEMENTATION ONLY.

Orchestrator review:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_1_5.md`

## Mission After Unblocked

Read the orchestrator review and Agents 1-5 closeouts, choose the smallest safe serialized source-refresh path, and perform only the repo-local code/config/DB materializations that are proven safe, backup-first, dry-run default, tested, and env-gated.

You are the only DB-writing agent in this wave.

## Required Rules

- Start with READCHECK.
- Write tests before implementation changes.
- Use backup-first DB workflow for every `db/app.db` mutation.
- No live external writes.
- No live external reads in this pass unless the orchestrator review explicitly allows the exact read lane. Prefer local evidence and prepare exact future live-source commands instead.
- Stop and write exact owner instructions if human review/approval is required.
- Do not claim green owner publication.
- Do not weaken validators to make gates pass.
- Do not treat missing/stale source data as zero.
- Do not edit external repos, raw workbooks, payment images, supplier evidence, or browser/session state.
- You are not alone in the codebase. Do not revert unrelated changes; preserve existing work and adjust around it.

## Expected Inputs After Unblocked

Read:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_1_5.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_1_ab_operational_source_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_2_ads_source_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_3_cashflow_bank_obligations_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_4_po_inbound_refresh_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_5_owner_exception_review_pack_closeout.md`

## Safe Implementation Scope

Allowed:

- Normalize `config/bank_accounts_manual_ingest_3.5.2026.yaml` and update derived bank config/history only after tests/dry-runs prove the parse and totals are correct.
- Add a deterministic helper if needed to convert the manual bank ingest snapshot into the bank history/current config format.
- Add an env-gated `order_status_event` materializer from real local evidence in `fact_orders_kaspi` and/or `fact_order_status_observations`.
- Add a local ads importer for existing Web_automation ACMEWEAR evidence into `ads_source_refresh_runs` and `ads_campaign_product_daily`, with dry-run default, explicit `ENABLE_C3_ADS_SOURCE_WRITE=1`, strict unmapped-row reporting, and no fake zero rows.
- Fix `DIM_SKU_light_v7` parser/fallback so `scripts/sync_po_parts_from_inbound_calendar.py` can run dry-run deterministically.
- Add or stage a PO/inbound line-grain dry-run materializer/checker; apply only non-owner-dependent projection repairs.
- Re-materialize C3 state after safe local fixes and generate a blocked owner brief if any gate remains blocked.

Not allowed:

- Do not close owner stock exceptions without explicit owner decision.
- Do not force PO-4.0 green before owner/source contract decision.
- Do not mark LINE31 PO1A received until source evidence proves dispatch, cargo receipt, Astana arrival, warehouse receipt, employee quantity, and QC approval.
- Do not make cashflow green without confirmed supplier/cargo obligations.
- Do not import bank snapshots as cashflow events.
- Do not write STOREB ads rows as `UNIVERSAL`.
- Do not claim Meta/Facebook or STOREB coverage from stale or missing artifacts.

## Required Test/Validation Shape

Before touching implementation, add or identify focused tests for the changed surfaces. Expected tests include some subset of:

- bank manual ingest parse/history normalization test;
- order status event materializer idempotency/test fixture;
- ads local importer dry-run/apply contract test;
- DIM_SKU parser/fallback regression test;
- PO/inbound line-grain materializer dry-run/idempotency test.

After changes, run the smallest relevant focused tests first, then the C3 validators:

```bash
python3 scripts/validate_operational_stock_schema.py --json
python3 scripts/validate_policy_registry_schema.py --db db/app.db
python3 scripts/validate_operational_decision_policy_registry.py --db db/app.db --policy config/operational_decision_policy.yaml --strict
python3 scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-05-03 --strict
python3 scripts/validate_policy_gate_results.py --db db/app.db --strict
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_operational_stock_daily_truth.py --db db/app.db --as-of 2026-05-03 --output-root exports/operational_stock_daily_truth --run-id agent6-c3-source-refresh-check --allow-green-owner-output --require-c3-policy --json
```

Expected result may remain YELLOW/RED_BLOCKED because owner/live-source blockers are real. Do not hide that.

## Closeout Requirements

Write a closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- DB backup path if DB was touched;
- exact commands run;
- before/after evidence;
- validators run;
- rollback instructions;
- exact owner attention steps if needed.

ASSIGNED CLOSEOUT: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-refresh-owner-review-wave/agent_6_source_refresh_execution_closeout.md`
