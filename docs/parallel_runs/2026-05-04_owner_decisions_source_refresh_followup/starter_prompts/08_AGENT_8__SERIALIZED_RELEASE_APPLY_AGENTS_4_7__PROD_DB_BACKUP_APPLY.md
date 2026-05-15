# Agent 8 Starter: Serialized Release Apply For Agents 4-7

Gate: production `db/app.db` release/apply lane. Owner authorization was given in chat on `2026-05-04` with the instruction: `Launch serialized release/apply lane for Agents 4-7`.

This starter authorizes production `db/app.db` writes only for the exact release scope below, only after backup, only through the repo scripts' explicit env gates and `--apply`, and only with post-apply validation evidence.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
4. `~/Docs/Autonomous_business/docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
5. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/STRATEGIC_GOAL_OPTION_B_THEN_C_20260504.md`
6. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_4.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_5.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_6.md`
9. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/ORCHESTRATOR_REVIEW_AFTER_AGENT_7.md`
10. `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/FULL_ORCHESTRATOR_REVIEW_CURRENT_STATE.md`
11. this starter prompt

## Mission

Apply the accepted temp-chain work from Agents 4, 5, 6, and 7 to production `~/Docs/Autonomous_business/db/app.db` in one serialized release lane.

Apply order:

1. Agent 4 order-entry recovery.
2. Agent 5 Kaspi Pay cash anchors.
3. Agent 6 D1 cashflow translator events.
4. Agent 7 D1 residue repair entries.
5. D1 translator rerun after residue repair.
6. Post-apply dry-run and validators.

The goal is to make production order-entry and D1 cashflow truth match the green temp DB chain. Do not claim full operational-stock publication green because ads, PO/inbound, and lifecycle blockers remain outside this release.

## Allowed Writes

Allowed:

- Production `~/Docs/Autonomous_business/db/app.db` writes through the exact env-gated scripts listed below.
- One pre-write DB backup under `~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/db_backups/`.
- Evidence artifacts under `~/Docs/Autonomous_business/exports/validation/release_agents4_7_20260504/`.
- Assigned closeout file.

Not allowed:

- No workbook/source-file edits.
- No live Kaspi/ads/API calls.
- No schema refactor beyond additive table creation performed by the approved scripts.
- No synthetic order entries, cash events, stock movements, SKU mappings, ads rows, or PO receipts.
- No tolerance widening.
- No owner green publication.
- No git commit.
- No destructive git operations.

## Required Preflight

Run focused tests before any production DB write:

```bash
python3 -m pytest -q \
  tests/test_recover_order_entries_from_evidence.py \
  tests/test_kaspi_pay_cash_anchor.py \
  tests/test_order_cashflow_validators.py \
  tests/test_cashflow_translator.py \
  tests/test_repair_d1_cashflow_residue_from_evidence.py \
  tests/test_operational_stock_integration_gates.py
```

If this fails, stop and write RED/YELLOW closeout. Do not apply production DB writes.

## Required Backup

Before any production apply, create a backup:

```bash
mkdir -p ~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/db_backups
cp ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/db_backups/app_db_before_agents4_7_release_YYYYMMDD_HHMMSS_almt.db
shasum -a 256 ~/Docs/Autonomous_business/db/app.db ~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/db_backups/app_db_before_agents4_7_release_YYYYMMDD_HHMMSS_almt.db
```

Use a real timestamp in the backup filename and record it in the closeout.

## Required Pre-Write Evidence

Create an evidence root:

`~/Docs/Autonomous_business/exports/validation/release_agents4_7_20260504/`

Capture pre-write state there:

```bash
python3 scripts/recover_order_entries_from_evidence.py --db db/app.db --as-of 2026-05-03 --output-root exports/validation/release_agents4_7_20260504/pre_order_entries --strict
python3 scripts/validate_order_cashflow_coverage.py --db db/app.db --as-of 2026-05-03 --json > exports/validation/release_agents4_7_20260504/pre_order_cashflow_coverage.json
python3 scripts/validate_cashflow_actual_model_separation.py --db db/app.db --anchor-date 2026-05-03 --json > exports/validation/release_agents4_7_20260504/pre_actual_model_separation.json
sqlite3 -readonly db/app.db "SELECT COUNT(*) AS cash_anchor_table_exists FROM sqlite_master WHERE type='table' AND name='cashflow_cash_anchor'; SELECT COUNT(*) AS d1res_entries FROM fact_order_entries_kaspi WHERE entry_id LIKE 'D1RES-OCEAN-%';" > exports/validation/release_agents4_7_20260504/pre_db_counts.txt
```

If a preflight validator is slow, capture a bounded summary from existing validated artifacts and explain in closeout. Do not skip backup or post-apply validators.

## Required Production Apply Commands

Run the production writes in this exact order.

Agent 4 apply:

```bash
ENABLE_ORDER_ENTRY_RECOVERY_WRITE=1 ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE=1 \
python3 scripts/recover_order_entries_from_evidence.py \
  --db db/app.db \
  --as-of 2026-05-03 \
  --output-root exports/validation/release_agents4_7_20260504/order_entries_apply \
  --strict \
  --apply
```

Agent 5 apply:

```bash
ENABLE_CASHFLOW_ANCHOR_WRITE=1 \
python3 scripts/apply_kaspi_pay_cash_anchor.py \
  --db db/app.db \
  --source-root ~/Docs/agent_handoffs/kaspi_pay/20260504_131100/Statements/kaspi_stores \
  --cutoff 2026-05-03 \
  --run-id release-agents4-7-cash-anchor-20260503 \
  --output-root exports/validation/release_agents4_7_20260504/cash_anchor_apply \
  --strict \
  --apply \
  --redact
```

Agent 6 apply:

```bash
ENABLE_CASHFLOW_WRITE=1 \
python3 scripts/translate_orders_to_cashflow_events.py \
  --db db/app.db \
  --since 2024-08-01 \
  --until 2026-05-03 \
  --run-id release-agents4-7-d1-apply-20260503 \
  --apply \
  > exports/validation/release_agents4_7_20260504/translator_apply.txt
```

Agent 7 apply:

```bash
ENABLE_D1_RESIDUE_REPAIR_WRITE=1 ENABLE_D1_RESIDUE_REPAIR_PRODUCTION_WRITE=1 \
python3 scripts/repair_d1_cashflow_residue_from_evidence.py \
  --db db/app.db \
  --as-of 2026-05-03 \
  --output-root exports/validation/release_agents4_7_20260504/d1_residue_repair \
  --apply
```

Post-repair D1 translator apply:

```bash
ENABLE_CASHFLOW_WRITE=1 \
python3 scripts/translate_orders_to_cashflow_events.py \
  --db db/app.db \
  --since 2024-08-01 \
  --until 2026-05-03 \
  --run-id release-agents4-7-d1-repair-20260503 \
  --apply \
  > exports/validation/release_agents4_7_20260504/translator_repair_apply.txt
```

Post-apply dry-run idempotence:

```bash
python3 scripts/translate_orders_to_cashflow_events.py \
  --db db/app.db \
  --since 2024-08-01 \
  --until 2026-05-03 \
  --run-id release-agents4-7-post-apply-20260503 \
  > exports/validation/release_agents4_7_20260504/translator_post_apply_dry_run.txt
```

## Required Post-Apply Validators

Run:

```bash
python3 scripts/validate_order_cashflow_coverage.py --db db/app.db --as-of 2026-05-03 --strict --json > exports/validation/release_agents4_7_20260504/post_order_cashflow_coverage.json
python3 scripts/validate_cashflow_actual_model_separation.py --db db/app.db --anchor-date 2026-05-03 --strict --json > exports/validation/release_agents4_7_20260504/post_actual_model_separation.json
python3 scripts/validate_cashflow_invariants.py --db db/app.db > exports/validation/release_agents4_7_20260504/post_cashflow_invariants.txt
python3 scripts/validate_operational_stock_integration_gates.py --db db/app.db --as-of 2026-05-03 --json > exports/validation/release_agents4_7_20260504/post_operational_stock_integration_gates.json
sqlite3 -readonly db/app.db "SELECT COUNT(*) AS cash_anchor_rows FROM cashflow_cash_anchor; SELECT COUNT(*) AS d1res_entries FROM fact_order_entries_kaspi WHERE entry_id LIKE 'D1RES-OCEAN-%';" > exports/validation/release_agents4_7_20260504/post_db_counts.txt
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

Expected production results:

- `ORDER_ENTRY_MISSING=0` in the operational integration gate.
- D1 categories absent or zero:
  - `CASHFLOW_D1_CASH_IN_MISSING=0`
  - `CASHFLOW_D1_DUPLICATE_CASH_IN=0`
  - `CASHFLOW_D1_LINE_EVIDENCE_MISSING=0`
  - `CASHFLOW_D1_RECEIVABLES_MODELED=0`
- `validate_order_cashflow_coverage.py --strict` passes.
- actual/model separation passes.
- cashflow invariants pass.
- `cashflow_cash_anchor` has `5` anchor rows.
- `fact_order_entries_kaspi` has `9` `D1RES-OCEAN-%` repair rows, unless already-present evidence proves idempotence.
- operational integration gate remains RED only for non-D1/non-order-entry categories:
  - ads source/coverage;
  - PO/inbound line-grain/double-count;
  - residual lifecycle.

If any required post-apply validator fails because of the release, stop, write RED, and include rollback instructions from the backup. Do not attempt ad hoc SQL repair unless the owning script supports it with tests and explicit gates.

## Rollback Requirement

Closeout must include a rollback command using the exact backup path, for example:

```bash
cp <backup_path> ~/Docs/Autonomous_business/db/app.db
```

Do not run rollback unless a validator regression requires it or the owner explicitly instructs it.

## Closeout

Write closeout to:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-04_order_entry_cashflow_unblock_wave/agent_8_serialized_release_apply_agents4_7_closeout.md`

Include:

- Gate: `GREEN`, `YELLOW`, or `RED`.
- Backup path and backup SHA-256.
- Exact production write commands run.
- Pre/post counts.
- Focused test results.
- Post-apply validator results.
- Remaining non-D1 blockers.
- Statement that owner green publication is still blocked unless all non-D1 gates are green.
- Rollback command.
