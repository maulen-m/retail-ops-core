# Agent 4 Starter: Order-Entry Recovery Materializer

Gate: serial write-capable implementation. Production `db/app.db` apply is not authorized by this starter.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/SOURCE_AUTHORIZATION_ORDER_ENTRY_CASHFLOW_20260504_131100_ALMT.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_ROOT.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_1_order_entry_recovery_evidence_closeout.md`
8. this starter prompt

## Mission

Implement the minimum safe order-entry recovery materializer to clear `ORDER_ENTRY_MISSING=15046` from real evidence only.

Agent 1 already proved read-only recoverability:

- Current CRM workbook: `1,135` target rows.
- Saved API order-entry JSONL: `13,909` target rows.
- WebUI archive source backups: `2` target rows.
- Reserve archive workbook required after stronger sources: `0`.
- Unrecovered/quarantine: `0`.

Your job is to turn that evidence map into tested, idempotent repo code and temp-DB validation evidence.

## Allowed Writes

Allowed:

- New or updated tests under `~/Docs/Autonomous_business/tests/`.
- New or updated script(s) under `~/Docs/Autonomous_business/scripts/`.
- New helper module(s) under `~/Docs/Autonomous_business/core/` only if needed.
- Validation artifacts under `~/Docs/Autonomous_business/exports/validation/order_entry_recovery_20260504/`.
- Assigned closeout file.

Not allowed:

- No production `db/app.db` writes.
- No edits to source CRM/archive workbooks.
- No live Kaspi API calls.
- No production cashflow writes.
- No SKU/profit/stock green publication.
- No raw phone/address/PII copied into workbook-derived `raw_json` or artifacts.

Temp DB apply is allowed only on a copied database under `/private/tmp` or another clearly non-production temp path.

## Required Implementation

1. Write tests first.
2. Implement a dry-run-default script, suggested name:

   `~/Docs/Autonomous_business/scripts/recover_order_entries_from_evidence.py`

3. The script must:

   - build the current `ORDER_ENTRY_MISSING` target set using the current validator-compatible logic;
   - apply the source hierarchy: current CRM first, saved API JSONL next, WebUI archive backups next, reserve archive last;
   - never synthesize entries from order headers, totals, names, or expected stock movement;
   - produce deterministic provenance for non-API entry rows;
   - dedupe overlapping API evidence by stable entry/source keys;
   - redact workbook-derived raw payloads so phone/address/PII are not stored;
   - keep unrecovered rows in an explicit quarantine/preview output if any appear;
   - default to dry-run;
   - require an explicit env gate and `--apply` for writes;
   - be idempotent: post-apply dry-run against the same temp DB should report zero new inserts.

4. It must separate:

   - order-entry row recovered;
   - SKU/article mapping sufficient for stock/profit rebuild.

   Do not claim SKU-level stock/profit green if `dim_kaspi_article_map` does not cover an API entry.

## Required Tests

At minimum, add focused tests for:

- source hierarchy priority;
- no synthetic entries when evidence is missing;
- deterministic provenance key for workbook/WebUI rows;
- API dedupe;
- redaction of PII from workbook-derived raw payloads;
- temp DB apply idempotency;
- validator-facing dry-run counts.

Use small fixtures where possible; do not require huge real workbooks in unit tests unless the repo already has safe fixture patterns.

## Required Validation

Run the smallest relevant gates:

```bash
python3 -m pytest -q <focused tests you add or touch>
python3 scripts/recover_order_entries_from_evidence.py --db db/app.db --as-of 2026-05-03 --output-root exports/validation/order_entry_recovery_20260504 --strict
cp db/app.db /private/tmp/order_entry_recovery_agent4.sqlite
ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 python3 scripts/recover_order_entries_from_evidence.py --db /private/tmp/order_entry_recovery_agent4.sqlite --as-of 2026-05-03 --output-root /private/tmp/order_entry_recovery_agent4_apply --strict --apply
python3 scripts/recover_order_entries_from_evidence.py --db /private/tmp/order_entry_recovery_agent4.sqlite --as-of 2026-05-03 --output-root /private/tmp/order_entry_recovery_agent4_post_apply --strict
python3 scripts/validate_operational_stock_integration_gates.py --db /private/tmp/order_entry_recovery_agent4.sqlite --as-of 2026-05-03 --json
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Expected temp-DB result:

- `ORDER_ENTRY_MISSING` absent or zero.
- If other blockers remain, report them honestly and do not mark overall operational stock green.

## Stoplines

Stop and write RED/YELLOW closeout if:

- evidence counts differ materially from Agent 1 without a clear source explanation;
- the script needs live API calls;
- any source row lacks exact `order_id + store_code`;
- any source row lacks item/article and quantity evidence;
- workbook-derived raw JSON would include phone/address/PII;
- temp DB apply is not idempotent;
- production `db/app.db` would need to be changed to prove success;
- `ORDER_ENTRY_MISSING` remains after temp DB apply and cannot be quarantined without synthesis.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_4_order_entry_recovery_materializer_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Files changed.
- Tests/gates run with results.
- Dry-run counts.
- Temp DB apply counts.
- Post-apply idempotence result.
- Remaining non-order-entry blockers, if any.
- Clear statement that production `db/app.db` was not modified.
