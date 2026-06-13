# Green Path Phase 2 Order Entry And D1 Recovery

Gate: YELLOW

Date: 2026-06-14

## Scope

Recovered the source-backed ACMEWEAR/UNIVERSAL `ORDER_ENTRY_MISSING` cohort and repaired the follow-on D1 cash-in coverage gap without replaying broad cashflow translation into quarantined STOREB rows.

No Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes were performed.

## Safety Decisions

The broad order-to-cashflow replay was explicitly rejected after copied-DB proof:

- evidence: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/copied_db_combined/`
- result: `finding_count=341`
- rejection reason: the broad replay inserted 66 cashflow events and created quarantine leakage:
  - `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK=2`
  - `ORDER_ENTRY_QUARANTINE_PRODUCT_COGS_LEAK=1`

The accepted path was the narrow copied proof:

- evidence: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/copied_db_focused_d1/`
- order-entry apply proof: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/copied_db_focused_order_entry_apply/summary.json`
- focused D1 cash-in proof: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/copied_db_focused_d1_cash_in_apply/summary.json`
- copied result: `finding_count=338`, no `CASHFLOW_D1_CASH_IN_MISSING`, no quarantine leakage

## Committed Code

- `74734f2 fix: harden order-entry recovery production apply`
- `8d701f29 fix: gate production cashflow applies`
- `d0ee151e fix: add focused d1 cash-in repair`

## Production Apply

Production DB pre-SHA:

```text
16f80740ef01928dd94f2180f4ace1116e37e80f751d54022278bca0e767840b
```

Order-entry recovery:

- summary: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_order_entry_apply/summary.json`
- backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_order_entry/app_2026-06-14_031017.db`
- backup SHA: `ffbcb5204a70b9160bc73d487915e8b6fe1f0c70c55bdfa794fbd7d28849e8df`
- inserted entries: `169`
- source: `CURRENT_CRM`
- post-SHA: `982aea590ffefd0dbb57fd07c1880f8baa1b8309d2708582f8350809986c75c0`

Focused D1 cash-in repair:

- summary: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_d1_cash_in_apply/summary.json`
- backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_d1_cash_in/app_2026-06-14_031022.db`
- backup SHA: `5064cd28a6b18e4d9a098b5593850f3431cd137955b6d365f0dfd958ad017d8e`
- inserted cash-in events: `2`
- coverage before: `cash_in_missing_count=2`
- coverage after: `cash_in_missing_count=0`
- post-SHA: `6aaab613d45ab46f780b378a43124091605c968e578a241ed56c422c156feeaa`

Cashflow daily rebuild:

- output: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_cashflow_rebuild_apply.txt`
- backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_cashflow_rebuild/app_2026-06-14_031029.db`
- backup SHA: `41fef085dcf8061bb86173a8ac1161f7af994c73c5b793ca6d631e56e0f9fc56`
- range: `2026-04-16` to `2026-06-13`
- system events generated: `0`
- daily rows computed: `59`
- final DB SHA: `11e3979042a9f7ee5990bc8b6ca4123145208a51a9433029c2f45e5c5e61a596`
- final integrity: `ok`

## Validation

Focused tests:

```bash
.venv/bin/python -m pytest -q tests/test_repair_d1_cash_in_from_validator_evidence.py tests/test_recover_order_entries_from_evidence.py tests/test_cashflow_translator.py tests/test_rebuild_cashflow_calendar_write_gate.py
```

Result: `63 passed`.

Production operational validator:

- evidence: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_operational_stock_after_focused_recovery.json`
- result: `RED`, `finding_count=338`

Current production finding census:

```text
ERROR ORDER_ENTRY_MISSING                                    63
ERROR ORDER_LIFECYCLE_MISSING_COMPLETED                       8
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

Production policy freshness:

- evidence: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_policy_source_freshness_after_focused_recovery.json`
- exit code: `1`
- known blocker: `src_ab_db_stock_truth` is stale for requested as-of `2026-06-13`

Daily ops after production apply:

- evidence: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/daily_ops_paused_after_prod_apply_retry.json`
- result: `ok=true`, `labels=0/10 loaded`, cron quiet, production DB and CRM workbook surfaces quiet

DB tracked/staged guard:

- `scripts/check_no_db_tracked.sh`
- result: `DB guard OK`

## Remaining Stoplines

The order-entry/D1 lane is complete for source-backed ACMEWEAR/UNIVERSAL evidence. Remaining Phase 2 blockers are:

- `ORDER_ENTRY_MISSING=63`, all currently STOREB/unrecovered source cases.
- `ORDER_LIFECYCLE_MISSING_COMPLETED=8`.
- `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=244` warnings.
- `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23` warnings.
- `src_ab_db_stock_truth` stale, still tied to the remaining 9 owner-approval stock rows.

Next best lane is to classify the remaining 63 STOREB `ORDER_ENTRY_MISSING` rows with either real entry evidence or an explicit no-entry quarantine contract, then repair the 8 lifecycle rows.
