# Agent 5 Starter: Cash Anchor Preview And Persistence

Gate: serial write-capable implementation. Production `db/app.db` apply is not authorized by this starter.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
5. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_ROOT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_4.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_2_kaspi_pay_cash_anchor_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_3_deterministic_cashflow_daily_design_closeout.md`
9. this starter prompt

## Mission

Implement the minimum safe cash-anchor preview and persistence layer for the provided Kaspi Pay package.

The owner-approved rule:

- The `2026-05-04 13:11 +0500` statements/reports are a one-time cash anchor/backfill input.
- Future daily cashflow must not require daily manual statement downloads.
- Decision-grade cutoff is `2026-05-03`; `2026-05-04` is partial and must be excluded.
- Cash anchors are reconciliation evidence, not fake order-level `CASH_IN`.

Source package:

`~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores`

Prior backup if needed for reconciliation:

`~/Documents/External_database/snapshots.nosync/20260213_211004/External_database/kaspi_pay/statements/kaspi_stores`

## Allowed Writes

Allowed:

- New or updated tests under `~/Docs/Autonomous_business/tests/`.
- New or updated scripts under `~/Docs/Autonomous_business/scripts/`.
- New helper module(s) under `~/Docs/Autonomous_business/core/` only if needed.
- Additive schema/migration files if needed.
- Update `~/Docs/Autonomous_business/db/schema.sql` only if adding a new canonical table contract.
- Validation artifacts under `~/Docs/Autonomous_business/exports/validation/kaspi_pay_cash_anchor/2026-05-03/`.
- Assigned closeout file.

Not allowed:

- No production `db/app.db` writes.
- No edits to source statement/report files.
- No recurring manual statement-download workflow as the daily design.
- No fake order-level cash-in events from balances.
- No raw account IDs, card numbers, BIN/IIN, raw order IDs, or transaction descriptions in generated owner-facing artifacts.
- No cashflow green publication.

Temp DB apply is allowed only on a copied database under `/private/tmp` or another clearly non-production temp path.

## Required Implementation

1. Write tests first.
2. Implement redaction-safe preview script, suggested name:

   `~/Docs/Autonomous_business/scripts/preview_kaspi_pay_cash_anchor.py`

3. Implement apply script or dry-run/apply mode, suggested name:

   `~/Docs/Autonomous_business/scripts/apply_kaspi_pay_cash_anchor.py`

4. Add a dedicated anchor persistence contract, preferably:

   `cashflow_cash_anchor` or `cashflow_anchor_run`

5. The preview/apply path must:

   - require exactly the five expected stores unless explicitly configured otherwise;
   - verify one statement and one sales report per current store;
   - parse statements and reconcile opening balance plus transactions to source close;
   - derive anchor closing balance through `2026-05-03`;
   - count and exclude `2026-05-04` partial transactions/rows;
   - hash source files and store only redacted account identity;
   - record source root, store, account mask/hash, statement/report hashes, opening date/balance, anchor date/balance, source close date/balance, post-cutoff transaction count/sum, statement txn count, sales-report row counts, reconciliation status, trust class, and run id;
   - default to dry-run;
   - require an explicit env gate and `--apply` for writes;
   - be idempotent: post-apply dry-run against the same temp DB should report zero new inserts.

## Required Tests

At minimum, add focused tests for:

- complete five-store package passes;
- missing store/report fails;
- partial current day is excluded from decision-grade anchor;
- statement bridge error must be zero;
- raw account IDs/card/BIN/IIN/order IDs/transaction text are redacted from generated artifacts;
- balance anchor cannot create order-level `CASH_IN`;
- temp DB apply idempotency;
- post-apply dry-run zero.

Use compact fixtures where possible. Do not require source files with sensitive data inside tests unless sanitized fixtures already exist.

## Required Validation

Run the smallest relevant gates:

```bash
python3 -m pytest -q <focused tests you add or touch>
python3 scripts/preview_kaspi_pay_cash_anchor.py --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores --cutoff 2026-05-03 --output-root exports/validation/kaspi_pay_cash_anchor/2026-05-03 --redact --strict
cp db/app.db /private/tmp/kaspi_pay_cash_anchor_agent5.sqlite
ENABLE_CASHFLOW_ANCHOR_WRITE=1 python3 scripts/apply_kaspi_pay_cash_anchor.py --db /private/tmp/kaspi_pay_cash_anchor_agent5.sqlite --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores --cutoff 2026-05-03 --run-id phase2b-cash-anchor-agent5-20260503 --output-root /private/tmp/kaspi_pay_cash_anchor_agent5_apply --strict --apply
python3 scripts/apply_kaspi_pay_cash_anchor.py --db /private/tmp/kaspi_pay_cash_anchor_agent5.sqlite --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores --cutoff 2026-05-03 --run-id phase2b-cash-anchor-agent5-20260503 --output-root /private/tmp/kaspi_pay_cash_anchor_agent5_post_apply --strict
python3 scripts/validate_cashflow_invariants.py --db /private/tmp/kaspi_pay_cash_anchor_agent5.sqlite
rg -n "KZ[0-9A-Z]{10,}|ИИН|БИН|Номер карты|Детали покупки" exports/validation/kaspi_pay_cash_anchor/2026-05-03
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Expected temp-DB result:

- Anchor records inserted for all five stores.
- Post-apply dry-run reports zero new anchor inserts.
- No order-level cash-in events are created by the anchor apply.
- Cashflow invariants still pass.

## Stoplines

Stop and write RED/YELLOW closeout if:

- any store lacks a current statement or sales report;
- statement bridge error is non-zero;
- `2026-05-04` partial data is treated as complete;
- raw account IDs, card numbers, BIN/IIN, raw order IDs, or transaction descriptions appear in generated artifacts;
- the implementation creates fake order-level `CASH_IN` from balance anchors;
- temp DB apply is not idempotent;
- production `db/app.db` would need to be changed to prove success;
- cashflow green would require D1 order-cash remediation in the same slice.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_5_cash_anchor_preview_persistence_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Files changed.
- Tests/gates run with results.
- Preview counts by store.
- Temp DB apply counts.
- Post-apply idempotence result.
- Redaction/privacy scan result.
- Remaining non-cash-anchor blockers.
- Clear statement that production `db/app.db` was not modified.
