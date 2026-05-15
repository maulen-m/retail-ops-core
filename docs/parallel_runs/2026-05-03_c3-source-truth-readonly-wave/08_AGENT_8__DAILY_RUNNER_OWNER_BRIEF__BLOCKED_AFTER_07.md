# Agent 8 - Daily Runner, Owner Brief, And Publication Gates

Assigned closeout: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_8_c3_daily_runner_owner_brief_closeout.md`

Status: UNBLOCKED by orchestrator review after Agent 7.

Mission: connect Agent 7's policy registry foundation to source freshness rows, policy gate results, exception ownership metadata, and the daily owner blocked brief. This is not a green-publication task.

## Required Reading

Start with a READCHECK before edits. Read:

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/PLAN.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENTS_1_6.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_7.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave/agent_7_c3_policy_db_exception_queue_closeout.md`
- Agent 1-6 closeouts in the same handoff folder.

## Write Scope

You may modify `~/Docs/Autonomous_business` repo files needed for Agent 8 and your assigned closeout file.

DB writes are allowed only if backup-first, additive, idempotent, dry-run by default, and explicitly env-gated.

Do not modify external repos, source evidence folders, Web_automation files, env files, bank/payment source files, supplier communications, browser sessions, APIs, merchant cabinets, ads platforms, payment systems, or live external systems.

## Tests First

Add or update tests before implementation for:

- source freshness materialization from DB/file/source-registry observations;
- policy gate result materialization for every required C3 gate;
- deterministic exception ownership/action/evidence metadata backfill for existing open high-severity exceptions;
- daily owner brief remains `RED_BLOCKED` when source freshness or gate results are blocking;
- no fake PASS rows and no zero-spend/zero-risk interpretation for missing data;
- idempotent DB writes and backup-first apply behavior.

## Required Implementation Shape

Prioritize:

1. Add a source freshness materializer script/module. It should insert one current `source_freshness_result` row per required active source, using local evidence only: DB row counts/max dates, file existence, file mtime/hash, configured max-age rules, and source pointer metadata. Missing/stale/blocked data should be recorded as blocking, not hidden.
2. Add a policy gate result materializer script/module. It should write rows for all required C3 gate names. Gates may be `BLOCKED` or `FAIL` if evidence requires it.
3. Add deterministic exception queue metadata fill for existing Agent 6 stock exceptions: owner, recommended action, evidence path(s), policy version/path where available, and gate/source binding where practical.
4. Extend or add daily owner brief generation so `scripts/run_operational_stock_daily_truth.py --require-c3-policy --allow-green-owner-output` still outputs `RED_BLOCKED` with exact C3 source/gate/exception blockers.
5. Preserve Agent 2-6 domain contracts: stock lifecycle/QC, PO route separation, ads freshness, cashflow event-vs-bank reconciliation, wiki-as-routing-memory.

Important validator semantics:

- `validate_policy_source_freshness.py --strict` should still fail if source rows are present but blocking. That is correct.
- `validate_policy_gate_results.py --strict` should still fail if gate rows are present but blocking. That is correct.
- `validate_exception_queue_db.py --strict` should pass if all open exceptions have owner/action/evidence metadata.

## Required Verification

Run focused tests you add plus these existing Agent 7 gates where relevant:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q tests/test_policy_registry_c3_contract.py
PYTHONDONTWRITEBYTECODE=1 pytest -q tests/test_operational_decision_policy_contract.py tests/test_operational_stock_schema_contract.py tests/test_operational_stock_daily_truth_runner.py tests/test_operational_stock_integration_gates.py
python3 scripts/validate_policy_registry_schema.py --db db/app.db
python3 scripts/validate_operational_decision_policy_registry.py --db db/app.db --policy config/operational_decision_policy.yaml --strict
python3 scripts/validate_exception_queue_db.py --db db/app.db --strict
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_operational_stock_daily_truth.py --db db/app.db --as-of 2026-05-03 --output-root exports/operational_stock_daily_truth --run-id agent8-c3-blocked-brief-check --allow-green-owner-output --require-c3-policy --json
```

If source freshness or gate-result validators still fail because true source data is stale/missing/blocking, report that as expected business blocker evidence.

## Closeout

Write the assigned closeout with:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- DB backup path if any DB write occurred;
- tests/validators run with pass/fail;
- owner brief output paths;
- remaining blockers grouped by source-refresh, owner-review, implementation, and external-system access;
- exact recommendation for the next agent wave.
