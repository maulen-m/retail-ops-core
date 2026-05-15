# Agent 6 Starter: D1 Cashflow Translator And Validators

Gate: serial write-capable implementation. Production `db/app.db` apply is not authorized by this starter.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_4.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_5.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_3_deterministic_cashflow_daily_design_closeout.md`
10. this starter prompt

## Mission

Implement the minimum safe D1 order-to-cashflow translator hardening and validators needed to clear the cashflow blockers on a temp DB chain:

- `CASHFLOW_D1_CASH_IN_MISSING=20945`
- `CASHFLOW_D1_RECEIVABLES_MODELED=2187`

The design goal is not to publish cashflow green yet. The goal is to prove, on a temp DB, that after applying the already-built order-entry materializer and cash-anchor layer, the D1 cashflow translator and validators can produce deterministic, idempotent order cash events without fake cash-in from balances.

## Required Starting Point For Temp DB Proof

Build a temp DB chain only:

1. Copy production DB to `/private/tmp/d1_cashflow_agent6.sqlite`.
2. Apply Agent 4 order-entry recovery to that temp DB.
3. Apply Agent 5 cash-anchor records to that temp DB.
4. Apply your D1 cashflow translator changes to that temp DB.
5. Validate on that temp DB.

Production `db/app.db` must not be modified.

## Allowed Writes

Allowed:

- New or updated tests under `~/Docs/Autonomous_business/tests/`.
- New or updated scripts under `~/Docs/Autonomous_business/scripts/`.
- New helper module(s) under `~/Docs/Autonomous_business/core/` only if needed.
- Additive schema contract changes only if strictly required.
- Validation artifacts under `~/Docs/Autonomous_business/exports/validation/d1_cashflow_agent6_20260503/`.
- Assigned closeout file.

Not allowed:

- No production `db/app.db` writes.
- No direct edits to statement/report/CRM/archive source files.
- No live Kaspi API calls.
- No balance-anchor to fake order-level `CASH_IN`.
- No cashflow green publication.
- No tolerance widening.
- No synthetic order entries, statuses, SKU mappings, or cash events.

## Required Implementation

Write tests first, then implement the smallest safe change set.

Required behavior:

- StageCode/lifecycle contract must drive cashflow triggers. Do not compare raw status strings ad hoc where a StageCode mapping exists.
- Delivered/completed order lines after the relevant anchor must create exactly one deterministic D1 `CASH_IN` candidate each.
- Returned/cancelled-after-delivery order lines must create exactly one reversal candidate each where source evidence supports it.
- In-delivery/shipped orders must not create cash-in.
- Balance anchors must remain reconciliation evidence and must not create order-level cash-in events.
- Legacy modeled receivables must not leak into paid-truth actual cashflow.
- Event hashes must be deterministic and idempotent.
- Missing lifecycle/source evidence must fail closed or quarantine; do not synthesize.

Recommended implementation surfaces to inspect first:

- `~/Docs/Autonomous_business/scripts/translate_orders_to_cashflow_events.py`
- `~/Docs/Autonomous_business/core/cashflow/orders_to_cashflow_events.py`
- `~/Docs/Autonomous_business/core/integrations/kaspi_order_stage.py`
- `~/Docs/Autonomous_business/core/ops/operational_stock_integration_gates.py`
- `~/Docs/Autonomous_business/scripts/recover_order_entries_from_evidence.py`
- `~/Docs/Autonomous_business/scripts/apply_kaspi_pay_cash_anchor.py`

Required validators:

Add or extend validators so temp DB proof can explicitly report:

- D1 cash-in missing count;
- modeled receivables count;
- actual/model separation;
- no balance-anchor fake `CASH_IN`;
- post-apply idempotence.

Suggested new scripts:

- `scripts/validate_order_cashflow_coverage.py`
- `scripts/validate_cashflow_actual_model_separation.py`

## Required Validation

Run the smallest relevant gates:

```bash
python3 -m pytest -q <focused tests you add or touch>
cp db/app.db /private/tmp/d1_cashflow_agent6.sqlite
ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 python3 scripts/recover_order_entries_from_evidence.py --db /private/tmp/d1_cashflow_agent6.sqlite --as-of 2026-05-03 --output-root /private/tmp/d1_cashflow_agent6_order_entries --strict --apply
ENABLE_CASHFLOW_ANCHOR_WRITE=1 python3 scripts/apply_kaspi_pay_cash_anchor.py --db /private/tmp/d1_cashflow_agent6.sqlite --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores --cutoff 2026-05-03 --run-id phase2c-d1-agent6-anchor-20260503 --output-root /private/tmp/d1_cashflow_agent6_anchor --strict --apply --redact
python3 scripts/translate_orders_to_cashflow_events.py --db /private/tmp/d1_cashflow_agent6.sqlite --since 2024-08-01 --until 2026-05-03 --run-id phase2c-d1-agent6-preview-20260503
ENABLE_CASHFLOW_WRITE=1 python3 scripts/translate_orders_to_cashflow_events.py --db /private/tmp/d1_cashflow_agent6.sqlite --since 2024-08-01 --until 2026-05-03 --run-id phase2c-d1-agent6-apply-20260503 --apply
python3 scripts/translate_orders_to_cashflow_events.py --db /private/tmp/d1_cashflow_agent6.sqlite --since 2024-08-01 --until 2026-05-03 --run-id phase2c-d1-agent6-post-apply-20260503
python3 scripts/validate_order_cashflow_coverage.py --db /private/tmp/d1_cashflow_agent6.sqlite --as-of 2026-05-03 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --db /private/tmp/d1_cashflow_agent6.sqlite --anchor-date 2026-05-03 --strict --json
python3 scripts/validate_cashflow_invariants.py --db /private/tmp/d1_cashflow_agent6.sqlite
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/d1_cashflow_agent6.sqlite --as-of 2026-05-03 --json
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

If the exact translator CLI cannot support this yet, update it safely with tests and report the final exact commands in closeout.

Expected temp DB result for GREEN:

- `CASHFLOW_D1_CASH_IN_MISSING=0`.
- `CASHFLOW_D1_RECEIVABLES_MODELED=0`.
- Order-entry blocker remains `0` after Agent 4 temp apply.
- Cash anchor records exist for five stores after Agent 5 temp apply.
- Post-apply D1 cashflow dry-run is idempotent.
- No balance-anchor fake cash-in events.

If `ORDER_LIFECYCLE_MISSING_COMPLETED=442` blocks full D1 green, do not synthesize lifecycle events. Either repair from existing real DB/API/status evidence without live calls or return YELLOW with exact unresolved order counts and source requirements.

## Stoplines

Stop and write RED/YELLOW closeout if:

- production `db/app.db` would need to be changed to prove success;
- D1 cash-in depends on balance anchors instead of order lifecycle events;
- raw statuses are used inconsistently with the StageCode contract;
- missing lifecycle evidence would require guesses;
- cashflow events are not idempotent;
- modeled receivables remain in paid-truth actual cashflow;
- order-entry or cash-anchor temp setup fails;
- current-day partial data is treated as complete;
- any DB apply lacks env gate and `--apply`.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_6_d1_cashflow_translator_validators_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Files changed.
- Tests/gates run with results.
- Temp DB setup results for Agent 4 and Agent 5 prerequisites.
- D1 translator preview/apply/post-apply counts.
- D1 cash-in missing count after temp apply.
- modeled receivables count after temp apply.
- actual/model separation result.
- Remaining non-D1 blockers.
- Clear statement that production `db/app.db` was not modified.
