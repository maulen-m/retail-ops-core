# Agent 7 - C3 Policy DB Registry And Exception Queue

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_7_c3_policy_db_exception_queue_closeout.md`

Status: UNBLOCKED by orchestrator review after Agents 1-6 closeouts.

Mission: implement tests-first effective-dated policy/source registry, source freshness, gate results, owner review ownership, rollback metadata, source pointers, and daily exception queue in AB. This is a C3 foundation implementation pass, not final owner publication.

## Required Reading

Start with a READCHECK before edits. Read these files first:

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_1_6.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_1_c3_policy_registry_authority_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_2_c3_stock_orders_returns_qc_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_3_c3_po_inbound_supplier_routes_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_4_c3_ads_marketing_directapi_truth_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_5_c3_cashflow_cargo_obligations_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_6_c3_wiki_context_synthesis_closeout.md`

## Write Scope

You may modify `~/Docs/Autonomous_business` repo files needed for the C3 foundation and your assigned closeout file.

Do not modify external repos, external evidence folders, env files, supplier communications, Web_automation files, bank/payment source files, or live external systems.

DB writes are allowed only if backup-first, additive, idempotent, and explicitly env-gated. Dry-run must be default. Do not claim owner publication is green.

## Tests First

Before implementation, add or update failing tests for the real success criteria:

- effective-dated policy registry schema and active-policy uniqueness;
- YAML-to-DB policy promotion drift detection;
- source registry and source freshness fail-closed behavior;
- policy gate results and publication blockers;
- manual decision approvals and non-overridable publication gates;
- exception queue required DB fields/views;
- rollback/change-event metadata;
- daily runner fails closed when C3 active policy or required sources are missing/stale;
- source-pointer classification for wiki/context facts versus primary source truth.

Then implement the smallest safe additive code/schema changes needed to pass the tests.

## Required Implementation Shape

Prioritize these deliverables:

1. Add an additive C3 migration script, dry-run by default, apply gated by an explicit environment variable, with DB backup path recorded.
2. Add or extend validators for policy registry schema, policy registry drift, source freshness, gate results, and exception queue DB contract.
3. Add deterministic policy promotion from `config/operational_decision_policy.yaml` into DB registry rows.
4. Add source-registry/source-pointer rows or seed logic for the source families identified in the orchestrator review.
5. Add DB views for active policy, current source freshness, publication blockers, and open exceptions.
6. Wire C3 fail-closed checks into the daily truth runner enough that Agent 8 can build the owner brief without recomputing business math in the UI/report layer.

Preserve these domain contracts:

- stock/order/return/QC rules from Agent 2;
- PO/inbound route separation from Agent 3;
- ads source and DirectAPI dry-run/post-verify rules from Agent 4;
- cashflow event-versus-bank-reconciliation separation from Agent 5;
- wiki-as-routing-memory rule from Agent 6.

If scope pressure appears, do not dilute gates. Implement the foundation cleanly and leave data backfills/source refreshes as explicit blockers for Agent 8 or owner review.

## Required Verification

Run the smallest relevant focused gates, including any new tests you add. At minimum, attempt:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q tests/test_operational_decision_policy_contract.py tests/test_operational_stock_schema_contract.py tests/test_operational_stock_daily_truth_runner.py tests/test_operational_stock_integration_gates.py
```

Also run the new validators you add. If global integration gates still fail because real source data is missing/stale, report that honestly and keep owner publication blocked.

## Closeout

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- DB backup path if any DB write occurred;
- tests/validators run with pass/fail;
- remaining blockers;
- exact recommendation for whether Agent 8 may be launched.
