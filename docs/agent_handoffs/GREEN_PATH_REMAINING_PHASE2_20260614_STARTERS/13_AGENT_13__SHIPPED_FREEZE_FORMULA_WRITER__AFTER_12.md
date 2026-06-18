# Agent 13 — Shipped-Freeze Formula-Landed Writer

You are Agent13 in the green-path Phase-2 program. Work in:

`~/Docs/Autonomous_business`

Closeout path:

`~/Docs/Autonomous_business_agent_handoffs/20260614_green_path_remaining_phase2/agent13_shipped_freeze_formula_writer_closeout.md`

Standalone closeout gate line required:

`Gate: GREEN|YELLOW|RED`

## Mission

Apply the guarded shipped-freeze on-delivery inventory moves using the existing Agent11 translator guard patch and Agent12's formula-landed authority decision.

This is a write-gated DB repair. It may write only `db/app.db` through `scripts/translate_orders_to_cashflow_events.py --apply` after backup, expected SHA, exact dry-run scope, and env gates all pass.

## Fixed Authority

Expected pre-apply DB SHA:

`2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37`

Allowlist:

`~/Docs/Autonomous_business/exports/validation/shipped_freeze_scout_20260614_20260614_091127/17_eligible_18_order_ids.txt`

Parked row that must remain untouched:

`956748585 / ACMEWEAR / LINE-21-TS_3XL`

Formula-landed dry-run truth:

- exactly 18 allowlisted ON_DELIVERY orders
- exactly 36 new events
- exactly 18 positive `INVENTORY_ON_DELIVERY_COST` events
- positive `INVENTORY_ON_DELIVERY_COST` sum exactly `64,446.22` KZT
- paired negative `INVENTORY_ON_HAND_COST` sum exactly `-64,446.22` KZT
- no `CASH_IN`
- no `COGS_RECOGNIZED`
- no completed/cancelled/returned events
- no order outside the allowlist
- no row for parked `956748585`

## Required Sequence

1. Create evidence root:
   `~/Docs/Autonomous_business/exports/validation/shipped_freeze_formula_writer_20260614_<timestamp>/`
2. Verify no code edits are needed. Use the existing `--order-id-file` and `--only-cashflow-status ON_DELIVERY` guard.
3. Pre-check:
   - `shasum -a 256 db/app.db`
   - `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
   - `scripts/check_no_db_tracked.sh`
   - fail if SQLite sidecars exist or script production guard refuses
4. Run focused translator tests proving the guard and formula path:
   - `.venv/bin/python -m pytest -q tests/test_cashflow_translator.py -k "unit_cost_prefers_formula_landed_cogs_over_stored_legacy or order_id_allowlist or only_on_delivery or empty_order_id_allowlist or creates_on_delivery_for_shipped_kaspi_delivery"`
5. Run guarded dry-run:
   ```bash
   .venv/bin/python scripts/translate_orders_to_cashflow_events.py \
     --db db/app.db \
     --since 2026-06-13 \
     --until 2026-06-13 \
     --run-id "$RUN_ID" \
     --allow-missing \
     --order-id-file exports/validation/shipped_freeze_scout_20260614_20260614_091127/17_eligible_18_order_ids.txt \
     --only-cashflow-status ON_DELIVERY \
     --output-path "$OUT/01_dry_run_report.txt"
   ```
6. Independently parse the dry-run event rows. Stop before apply unless all formula-landed dry-run truth bullets match exactly.
7. Apply through the script's production guard:
   ```bash
   ENABLE_CASHFLOW_WRITE=1 ENABLE_CASHFLOW_PROD_WRITE=1 \
   .venv/bin/python scripts/translate_orders_to_cashflow_events.py \
     --db db/app.db \
     --since 2026-06-13 \
     --until 2026-06-13 \
     --run-id "$RUN_ID" \
     --allow-missing \
     --order-id-file exports/validation/shipped_freeze_scout_20260614_20260614_091127/17_eligible_18_order_ids.txt \
     --only-cashflow-status ON_DELIVERY \
     --apply \
     --expected-pre-sha256 2c654acab422b86ee15448dc69d2041194ec834d5246e4c57148d0feef6c9b37 \
     --backup-dir "$OUT/backup" \
     --output-path "$OUT/02_apply_report.txt"
   ```
8. Post-apply readbacks:
   - inserted event count and sum for `$RUN_ID`
   - positive on-delivery count/sum
   - no row for `956748585`
   - backup path and backup SHA
   - pre/post DB SHA
9. Validators:
   - `sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'`
   - `scripts/check_no_db_tracked.sh`
   - `.venv/bin/python scripts/validate_cashflow_invariants.py --db db/app.db`
   - `.venv/bin/python scripts/check_on_delivery_residuals.py --db db/app.db --until 2026-06-14 --output-dir "$OUT/check_on_delivery_residuals"`
   - `.venv/bin/python scripts/validate_on_delivery_freeze.py --db db/app.db --until 2026-06-14`

Expected retained freeze result after apply:

- `validate_on_delivery_freeze.py` may exit non-zero only if the sole remaining failure is `956748585 / ACMEWEAR / LINE-21-TS_3XL`.
- Any other freeze failure is a stopline.

## Forbidden

No code edits unless the existing Agent11 guard is missing or broken, in which case stop. No COGS overrides. No stock ledger writes. No dashboards/status/scoreboard edits. No external systems. No Telegram, LaunchAgents, Kaspi merchant, Repricer, pricing, workbooks, browser automation, customer/operator messages, or paid API usage.

## Closeout Requirements

Include:

- `Gate: GREEN|YELLOW|RED`
- evidence root
- exact commands run and results
- backup path and backup SHA
- pre/post DB SHA
- inserted event count and sum
- validator results
- final freeze validator retained-row summary
- rollback command family using the real backup path

Gate guidance:

- `GREEN` only if the formula-landed apply inserted exactly 36 events and the only retained freeze failure is the parked LINE row.
- `YELLOW` only if apply was intentionally skipped after safe code/test/dry-run evidence.
- `RED` for any pre-SHA mismatch, dry-run mismatch, backup failure, apply failure, validator regression, or unexpected retained freeze row.
