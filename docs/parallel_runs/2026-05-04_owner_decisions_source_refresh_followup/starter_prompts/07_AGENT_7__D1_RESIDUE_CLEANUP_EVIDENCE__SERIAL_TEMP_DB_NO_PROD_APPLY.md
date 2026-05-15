# Agent 7 Starter: D1 Residue Cleanup Evidence

Gate: serial temp-DB cleanup/evidence lane. Production `db/app.db` apply is not authorized by this starter.

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
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_6_d1_cashflow_translator_validators_closeout.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_6.md`
11. this starter prompt

## Mission

Close, or explicitly quarantine, the remaining Agent 6 strict D1 cashflow residue on a temp DB chain only:

- `cash_in_missing_count=11`
- `duplicate_cash_in_count=29`
- `missing_line_evidence_count=12`

The business objective is to make D1 order cashflow safe enough for a later serialized production release/apply lane. Your job is not to apply production changes. Your job is to determine exactly which rows are repairable from existing real source evidence and which must become deterministic exceptions.

## Required Starting Point For Temp DB Proof

Build a new temp DB chain only:

1. Copy production DB to `/private/tmp/d1_cashflow_agent7.sqlite`.
2. Apply Agent 4 order-entry recovery to that temp DB.
3. Apply Agent 5 cash-anchor records to that temp DB.
4. Apply Agent 6 D1 cashflow translator to that temp DB.
5. Apply only your source-backed residue repair or deterministic exception logic to that temp DB.
6. Validate on that temp DB.

Production `db/app.db` must not be modified.

## Allowed Writes

Allowed:

- New or updated tests under `~/Docs/Autonomous_business/tests/`.
- New or updated scripts under `~/Docs/Autonomous_business/scripts/`.
- New helper module(s) under `~/Docs/Autonomous_business/core/` only if needed.
- Additive deterministic exception artifacts or schemas only if strictly required and tested.
- Validation artifacts under `~/Docs/Autonomous_business/exports/validation/d1_cashflow_agent7_20260503/`.
- Assigned closeout file.

Not allowed:

- No production `db/app.db` writes.
- No direct edits to statement/report/CRM/archive source files.
- No live Kaspi API calls.
- No balance-anchor to fake order-level `CASH_IN`.
- No synthetic order entries, statuses, SKU mappings, or cash events.
- No cashflow green publication unless strict temp-DB validators truly pass.
- No tolerance widening.
- No broad refactor outside the D1 residue problem.

## Required Work

Write tests first, then implement the smallest safe change set.

Required behavior:

- Classify every remaining strict D1 residue row into one of:
  - `source_backed_repair`
  - `deterministic_exception`
  - `still_blocked_source_missing`
- For `cash_in_missing_count=11`, determine whether each row is missing because line evidence is absent, amount is absent, lifecycle timing is wrong, or matching logic is wrong.
- For `duplicate_cash_in_count=29`, determine whether each duplicate is a true duplicate event, a validator over-match, a multi-line order ambiguity, or legacy event overlap.
- For `missing_line_evidence_count=12`, determine whether evidence exists in recovered API entries, CRM rows, sales facts, archive backups, or fact orders. If not, do not synthesize.
- If a repair is implemented, it must be source-backed and idempotent.
- If an exception is implemented, it must be explicit, deterministic, auditable, and must not hide real missing cash.
- Keep StageCode/lifecycle contract as the trigger authority.
- Keep balance anchors as reconciliation evidence only.
- Preserve actual/model separation.

Recommended implementation surfaces:

- `~/Docs/Autonomous_business/core/cashflow/order_cashflow_validation.py`
- `~/Docs/Autonomous_business/scripts/validate_order_cashflow_coverage.py`
- `~/Docs/Autonomous_business/scripts/validate_cashflow_actual_model_separation.py`
- `~/Docs/Autonomous_business/scripts/translate_orders_to_cashflow_events.py`
- `~/Docs/Autonomous_business/scripts/recover_order_entries_from_evidence.py`
- `~/Docs/Autonomous_business/scripts/apply_kaspi_pay_cash_anchor.py`
- `~/Docs/Autonomous_business/exports/validation/d1_cashflow_agent6_20260503/order_cashflow_coverage.json`

## Required Validation

Run the smallest relevant gates:

```bash
python3 -m pytest -q <focused tests you add or touch>
cp db/app.db /private/tmp/d1_cashflow_agent7.sqlite
ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 python3 scripts/recover_order_entries_from_evidence.py --db /private/tmp/d1_cashflow_agent7.sqlite --as-of 2026-05-03 --output-root /private/tmp/d1_cashflow_agent7_order_entries --strict --apply
ENABLE_CASHFLOW_ANCHOR_WRITE=1 python3 scripts/apply_kaspi_pay_cash_anchor.py --db /private/tmp/d1_cashflow_agent7.sqlite --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores --cutoff 2026-05-03 --run-id phase2d-d1-agent7-anchor-20260503 --output-root /private/tmp/d1_cashflow_agent7_anchor --strict --apply --redact
ENABLE_CASHFLOW_WRITE=1 python3 scripts/translate_orders_to_cashflow_events.py --db /private/tmp/d1_cashflow_agent7.sqlite --since 2024-08-01 --until 2026-05-03 --run-id phase2d-d1-agent7-apply-20260503 --apply
python3 scripts/translate_orders_to_cashflow_events.py --db /private/tmp/d1_cashflow_agent7.sqlite --since 2024-08-01 --until 2026-05-03 --run-id phase2d-d1-agent7-post-apply-20260503
python3 scripts/validate_order_cashflow_coverage.py --db /private/tmp/d1_cashflow_agent7.sqlite --as-of 2026-05-03 --strict --json
python3 scripts/validate_cashflow_actual_model_separation.py --db /private/tmp/d1_cashflow_agent7.sqlite --anchor-date 2026-05-03 --strict --json
python3 scripts/validate_cashflow_invariants.py --db /private/tmp/d1_cashflow_agent7.sqlite
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/d1_cashflow_agent7.sqlite --as-of 2026-05-03 --json
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Expected result for GREEN:

- `cash_in_missing_count=0`
- `duplicate_cash_in_count=0`
- `missing_line_evidence_count=0`, or all remaining missing-line rows are explicit deterministic exceptions accepted by strict validation
- `modeled_receivables_count=0`
- `balance_anchor_fake_cash_in_count=0`
- Post-apply D1 cashflow dry-run is idempotent
- No production DB write

If strict D1 cannot be GREEN without unsupported guesses, return YELLOW with exact remaining rows, why they are unresolved, and the minimum human/source evidence needed.

## Stoplines

Stop and write RED/YELLOW closeout if:

- production `db/app.db` would need to be changed to prove success;
- a repair would require invented order entries, statuses, SKU mappings, or cash events;
- a deterministic exception would hide real missing cash;
- balance anchors are used as fake order-level cash-in;
- strict validation can only pass by widening tolerance or weakening checks;
- the temp DB chain cannot be rebuilt reproducibly;
- any DB apply lacks env gate and `--apply`.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_7_d1_residue_cleanup_evidence_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Files changed.
- Tests/gates run with results.
- Temp DB setup results for Agent 4, Agent 5, and Agent 6 prerequisites.
- Classification table for all remaining D1 residue categories.
- Exact before/after counts for `cash_in_missing`, `duplicate_cash_in`, `missing_line_evidence`, `modeled_receivables`, and `balance_anchor_fake_cash_in`.
- Whether each unresolved row is repairable, excepted, or still blocked.
- Clear statement that production `db/app.db` was not modified.
