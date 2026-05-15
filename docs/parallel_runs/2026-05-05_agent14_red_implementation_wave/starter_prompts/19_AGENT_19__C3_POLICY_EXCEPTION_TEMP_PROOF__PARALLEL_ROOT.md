# Agent 19 - C3 Policy And Exception Semantics Temp Proof

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/agent_19_c3_policy_exception_temp_proof_closeout.md`

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-05_agent14_red_implementation_wave/PLAN.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_implementation_wave/README.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-05_agent14_red_remediation_wave/agent_16_c3_policy_exception_semantics_closeout.md`
7. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/OWNER_ANSWERS_AND_DECISIONS_20260504_125448_ALMT.md`
8. this starter prompt

## Mission

Implement and prove the C3 source-freshness and exception-semantics repairs from Agent 16.

You are not alone in the codebase. Do not revert edits made by others. Touch only your owned files. If an owned file has unexpected concurrent edits, stop and close out YELLOW/RED with evidence.

## Owner Truth To Encode

The owner decision document already resolves the `NEGATIVE_RAW_LEDGER_BALANCE` ambiguity for Berserk Rush:

- active sellable stock is `0`;
- returned/cancelled stock remains quarantine until employee QC acceptance;
- this should not block further business decisions.

Do not ask the owner again for this point unless the affected rows are not the Berserk Rush rows described by the owner decision.

## Owned Write Set

Primary:

- `~/Docs/Autonomous_business/core/ops/policy_materialization_c3.py`
- `~/Docs/Autonomous_business/core/ops/policy_registry_c3.py`
- `~/Docs/Autonomous_business/core/ops/operational_stock_daily_truth_runner.py`
- `~/Docs/Autonomous_business/tests/test_policy_materialization_c3.py`
- `~/Docs/Autonomous_business/tests/test_policy_registry_c3_contract.py`
- `~/Docs/Autonomous_business/tests/test_operational_stock_daily_truth_runner.py`

Docs/config only if behavior changes require it:

- `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
- `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`

Forbidden:

- production `db/app.db` writes;
- derived-table replay scripts owned by Agent 18;
- ads materializer files owned by Agent 20;
- weakening ads/source freshness to hide missing evidence.

## Required Implementation

Write tests first, then code.

Required behavior:

1. Directory source freshness must support recursive/latest-artifact semantics where policy config intends a source folder, not only root directory mtime.
2. Historical as-of materialization must distinguish future evidence from stale evidence.
3. Inbound workbook future status for `2026-05-03` must not imply stale source truth for a current `2026-05-04` run.
4. Accepted active controls must be visible but not global publication blockers:
   - `OWNER_OOS_ACTIVE_ZERO`;
   - `OWNER_OVERRIDE_NO_DOUBLE_REDUCE`;
   - `LINE61_4XL_EXCLUDED`;
   - owner-approved Berserk Rush `NEGATIVE_RAW_LEDGER_BALANCE` quarantine/active-zero rows.
5. Unresolved exceptions must still block.
6. Owner brief gate rendering must align with the latest materialized policy gate; metadata-only validator PASS must not be shown as semantic publication PASS if policy gate is blocked.
7. Facebook/Meta source freshness must remain fail-closed for ACMEWEAR if required and stale. Do not remove it from publication scope unless the owner-approved policy already says so.
8. STOREB must not require Meta/Facebook evidence. STOREB ads scope is Kaspi internal marketing.

## Required Temp Proof

Use a copied temp DB, not production:

`/private/tmp/agent19_c3_policy_exception_temp_proof_20260504.db`

Run materializers and validators against the temp DB where supported. Do not production-apply.

## Required Gates

Run focused tests for your changed files.

Run relevant validators against the temp DB:

- `python3 scripts/materialize_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04`
- `python3 scripts/materialize_policy_gate_results.py --db <temp_db>`
- `python3 scripts/validate_policy_source_freshness.py --db <temp_db> --as-of 2026-05-04 --strict`
- `python3 scripts/validate_policy_gate_results.py --db <temp_db> --strict`
- `python3 scripts/validate_exception_queue_db.py --db <temp_db> --strict`
- `sqlite3 <temp_db> 'PRAGMA integrity_check;'`

If a command has a different CLI shape, use the correct repo-local equivalent and record the exact command.

## Closeout Requirements

Include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- files changed;
- tests written first;
- commands run and key outputs;
- accepted-control counts versus unresolved-blocker counts;
- source freshness statuses after temp materialization;
- remaining production apply stoplines.
