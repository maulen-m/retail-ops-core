# Agent 61 - As-Of Materializer Contract Fix

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_asof_materializer_contract_fix_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_evidence/`

## Mission

Fix the as-of contract risk identified by Agent60: `scripts/materialize_order_status_events_from_kaspi_orders.py --as-of YYYY-MM-DD` must not insert or claim to materialize order-status events after the requested as-of date.

This is a tests-first code fix. It is not a production apply, not a workbook edit, and not a shipping-run mutation.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/PLAN.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/00_ORCHESTRATOR_HANDOFF.md`
6. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/SHIPPING_DISCREPANCY_DECISION_20260506.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_60_default_current_validator_daily_blocker_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_58_frozen_baseline_ws3_replay_closeout.md`

## Write Boundary

Allowed repo writes:

- `scripts/materialize_order_status_events_from_kaspi_orders.py`
- focused tests proving the as-of contract, preferably under `tests/`
- minimal docs in this run folder only if needed to record the contract

Allowed handoff writes:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_asof_materializer_contract_fix_closeout.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_61_evidence/**`

Forbidden:

- Do not mutate `~/Docs/Autonomous_business/db/app.db`.
- Do not edit `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`.
- Do not edit frozen baseline DB/workbook files.
- Do not pause/unload schedulers.
- Do not call live Kaspi, bank, marketing, Google, browser, or external APIs.
- Do not launch production apply or ask for an owner authorization phrase.
- Do not implement the `912168984` shipping rescue in this lane; only preserve the decision as context.

You are not alone in the codebase. Do not revert unrelated edits from prior agents.

## Required Sequence

1. Write a READCHECK section in the closeout with files read, assumptions, and exact write boundary.
2. Inspect `scripts/materialize_order_status_events_from_kaspi_orders.py` and its existing tests/callers.
3. Add a failing test first proving that `--as-of 2026-05-04` must not insert `order_status_event` rows with `date(event_ts) > 2026-05-04`.
4. Implement the smallest safe fix so `--as-of` is an enforced candidate filter, not report-only metadata.
5. Preserve default/no-as-of behavior for daily-current runs.
6. Include observable evidence in CLI/log output where practical, such as candidate count before/after as-of filtering.
7. Run focused tests, including the new test and any existing tests for the materializer or operational stock integration gates.
8. Run a temp-DB smoke, not production, proving no post-as-of event insertion.

## Required Verification

At minimum run and record:

```bash
pytest -q <new_or_existing_asof_materializer_tests>
pytest -q tests/test_operational_stock_integration_gates.py tests/test_policy_registry_c3_contract.py tests/test_policy_materialization_c3.py
python3 scripts/materialize_order_status_events_from_kaspi_orders.py --help
```

If test names differ, record the exact commands actually run.

## Gate Semantics

`GREEN`:

- tests were written before/failing or clearly documented as contract-first;
- the materializer enforces `--as-of`;
- focused tests pass;
- temp smoke proves no post-as-of insertion;
- production DB/workbook/external systems untouched.

`YELLOW`:

- fix is partially proven but a dependency or existing failing test prevents full confidence;
- behavior is safe but needs Agent62 reproof to validate integration.

`RED`:

- production mutation occurs;
- as-of remains report-only;
- tests cannot prove the contract;
- a required gate fails in a way that can hide publication risk.
