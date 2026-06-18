# Agent 11 — Shipped-Freeze Guarded Writer

You are Agent11 in the green-path Phase-2 program. Work in:

`~/Docs/Autonomous_business`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent11_shipped_freeze_guarded_writer_closeout.md`

Standalone closeout gate line required:

`Gate: GREEN|YELLOW|RED`

## Mission

Repair only the retained `SHIPPED has missing INVENTORY_ON_DELIVERY_COST balance` freeze class that Agent9 classified as eligible. Add a narrow guard to `scripts/translate_orders_to_cashflow_events.py`, test it, dry-run the exact 18-order allowlist, then apply to production `db/app.db` only if every scope check matches.

This lane is a write-gated DB repair. Use backup-first, expected-SHA, env-gated apply, before/after evidence, validator replay, and rollback instructions.

## Fixed Inputs

Current production DB SHA before your lane must be:

`2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`

Eligible allowlist:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_scout_20260614_20260614_091127/17_eligible_18_order_ids.txt`

Parked missing-cost order:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_scout_20260614_20260614_091127/18_parked_missing_cost_order_ids.txt`

Expected scoped dry-run truth:

- exactly 18 eligible orders
- exactly 36 new events
- event types/accounts only:
  - `INVENTORY_MOVE / INVENTORY_ON_HAND_COST` negative
  - `INVENTORY_MOVE / INVENTORY_ON_DELIVERY_COST` positive
- no `CASH_IN`
- no `COGS_RECOGNIZED`
- no completed/cancelled/returned order events
- no order outside the allowlist
- parked order `956748585` must not be written
- expected added on-delivery balance is `53,898.00` KZT

## Required Implementation

Patch `scripts/translate_orders_to_cashflow_events.py` narrowly to support an explicit order allowlist and cashflow-status filter, for example:

- `--order-id-file <path>` CLI argument
- `--only-cashflow-status ON_DELIVERY` CLI argument

The guard must filter the actual modeled order rows before events are produced. It must fail closed on an empty allowlist file and on unsupported status values. It must not rely on post-hoc report string filtering.

Add focused tests in `tests/test_cashflow_translator.py` or a clearly adjacent test file proving:

- `--order-id-file` / function argument excludes non-allowlisted rows
- `--only-cashflow-status ON_DELIVERY` excludes completed rows in the same date window
- empty allowlist is rejected

Keep changes tightly scoped. Do not refactor unrelated translator behavior.

## Required Execution Sequence

1. Read current code/tests and confirm no one else changed the DB boundary.
2. Verify starting DB:
   - `shasum -a 256 db/app.db`
   - `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
   - `scripts/check_no_db_tracked.sh`
3. Patch code/tests.
4. Run focused tests for the translator.
5. Run scoped dry-run against production DB using the allowlist and `--only-cashflow-status ON_DELIVERY`. Write report under a new evidence folder:
   - `~/Docs/Autonomous_business/exports/validation/shipped_freeze_guarded_writer_20260614_<timestamp>/`
6. Independently inspect dry-run event scope. Stop with `Gate: RED` if it is not exactly the expected 18 orders / 36 events / 53,898.00 KZT and only inventory-move accounts.
7. Create production DB backup through the script's write-gated path:
   - use `--expected-pre-sha256 2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`
   - use a backup dir inside your evidence folder
   - set `ENABLE_CASHFLOW_WRITE=1 ENABLE_CASHFLOW_PROD_WRITE=1`
8. Apply only after all guards pass.
9. Post-apply validators:
   - `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
   - `scripts/check_no_db_tracked.sh`
   - `.venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db`
   - `.venv/bin/python scripts/validate_on_delivery_freeze.py --db db/app.db --until 2026-06-14`
   - `.venv/bin/python scripts/check_on_delivery_residuals.py --db db/app.db --until 2026-06-14`
10. Expected post-apply outcome:
   - cashflow invariants PASS
   - residual checker PASS
   - on-delivery freeze validator may still exit 1, but only if the remaining failure is exactly `956748585 / LINE-21-TS_3XL`
   - DB guard passes and `db/app.db` is not tracked/staged

## Forbidden

Do not write or edit:

- dashboard/status/scoreboard files
- COGS overrides or cost authority rows
- stock ledgers
- Kaspi merchant, pricing, Repricer, Telegram, LaunchAgents
- CRM/workbooks/Google board/customer/operator messages
- external accounts or browser automation

Do not invent cost for `LINE-21-TS`. Do not broaden the owner stock/allocation approval into COGS authority.

## Closeout Requirements

Your closeout must include:

- `Gate: GREEN|YELLOW|RED`
- exact code files changed
- exact tests and validators run, with pass/fail
- evidence folder path
- backup path and backup SHA
- pre/post DB SHA
- number of inserted events and run id
- before/after freeze validator summary
- parked row confirmation for `956748585`
- rollback command family pointing at the real backup path

Gate guidance:

- `GREEN` only if the 18-order guarded apply succeeded, validators pass as expected, and the only retained freeze failure is the parked LINE-21-TS row.
- `YELLOW` if code/tests are safe but apply is intentionally not performed or a known adjacent blocker remains outside this lane.
- `RED` for any scope mismatch, missing backup, DB SHA mismatch, validation regression, or uncertain write boundary.
