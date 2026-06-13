# Green Path Phase 2 Orchestrator Closeout

Gate: YELLOW

Date: 2026-06-14

## Current State

Phase 2 implementation is durably committed for the lanes that had source-backed authority:

- C3/source-freshness and Meta external spend provenance are committed.
- Ads source truth is green after scope/backfill repair.
- Stock source-backed negative rows are repaired in production.
- STOREB 251-row header-only source-gap cleanup is repaired in production without replacing the hot DB file.
- The `906730647` stale header-only quarantine row is reclassified against real API entry evidence.
- Source-backed ACMEWEAR/UNIVERSAL missing order-entry rows are recovered in production, with focused D1 cash-in repair and no broad cashflow replay.

The repo is not yet allowed to claim full green state because `stock_source_truth` still has 9 negative stock_ledger rows that require explicit owner approval or a new exact source artifact, and the deeper operational stock integration validator still has order-entry and lifecycle blockers. These are intentional stoplines, not code failures.

Current audit addendum: `docs/agent_handoffs/GREEN_PATH_PHASE2_CURRENT_GATE_AUDIT_AND_HEADER_ONLY_PROOF_20260614.md`. Header-only production apply closeout: `docs/agent_handoffs/GREEN_PATH_PHASE2_HEADER_ONLY_PROD_APPLY_20260614.md`. Real-entry reclassification closeout: `docs/agent_handoffs/GREEN_PATH_PHASE2_906730647_REAL_ENTRY_RECLASSIFICATION_20260614.md`. Order-entry/D1 recovery closeout: `docs/agent_handoffs/GREEN_PATH_PHASE2_ORDER_ENTRY_D1_RECOVERY_20260614.md`. The compact C3 publication blockers are stock-related, but full Phase-2 closeout also requires resolving the current remaining STOREB `ORDER_ENTRY_MISSING` and lifecycle findings.

No Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes were performed by this orchestrator closeout step.

## Committed Checkpoints

- `5e943c5 feat: harden c3 source freshness evidence`
- `14311b0 fix: backfill ads source truth`
- `b849ef6 feat: apply governed stock source repairs`
- `48f7e93 fix: apply header-only quarantine safely`
- `3609334 fix: reclassify header-only order with real entry`
- `74734f2 fix: harden order-entry recovery production apply`
- `8d701f29 fix: gate production cashflow applies`
- `d0ee151e fix: add focused d1 cash-in repair`

Earlier phase checkpoints on this branch:

- `305ab88 docs: add phase2 retained blocker wave2 starters`
- `8cb0b1f docs: quarantine june beli ads gap`
- `01c9a7d docs: anchor ads partial apply`
- `b815dfc docs: anchor cashflow apply and final blockers`
- `40b21ec docs: add phase2 blocker repair starters`

## Lane Closeouts

- Meta external spend: `docs/agent_handoffs/GREEN_PATH_PHASE2_META_EXTERNAL_SPEND_PROD_APPLY_20260613.md`
- Ads source truth: `docs/agent_handoffs/GREEN_PATH_PHASE2_ADS_SCOPE_BACKFILL_PROD_APPLY_20260613.md`
- Stock source-backed repair: `docs/agent_handoffs/GREEN_PATH_PHASE2_STOCK_SOURCE_BACKED_PROD_APPLY_20260614.md`
- Stock owner-approval remaining dry-run: `docs/agent_handoffs/GREEN_PATH_PHASE2_STOCK_OWNER_APPROVAL_REMAINING_DRYRUN_20260614.md`
- Current gate audit and header-only copied proof: `docs/agent_handoffs/GREEN_PATH_PHASE2_CURRENT_GATE_AUDIT_AND_HEADER_ONLY_PROOF_20260614.md`
- Header-only production apply: `docs/agent_handoffs/GREEN_PATH_PHASE2_HEADER_ONLY_PROD_APPLY_20260614.md`
- `906730647` real-entry reclassification: `docs/agent_handoffs/GREEN_PATH_PHASE2_906730647_REAL_ENTRY_RECLASSIFICATION_20260614.md`
- Order-entry and focused D1 recovery: `docs/agent_handoffs/GREEN_PATH_PHASE2_ORDER_ENTRY_D1_RECOVERY_20260614.md`

## Production DB Evidence

- Cashflow D1 backup: `exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/backups/app_before_agent18_cashflow_d1_prod_apply_20260613.db`
- Ads partial backup: `exports/validation/agent21_ads_partial_prod_apply_20260613/backups/app_before_agent21_ads_partial_apply_20260613.db`
- Meta spend backup: `exports/validation/orchestrator_meta_external_spend_prod_apply_20260613/backups/app_before_meta_external_spend_prod_apply_20260613.db`
- Ads scope/backfill backup: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/backups/app_before_ads_scope_backfill_prod_apply_20260613.db`
- Stock source-backed backup: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/backups/app_before_stock_source_backed_repair_prod_apply_20260614.db`
- Header-only production apply backup: `exports/validation/orchestrator_header_only_prod_apply_20260614/backups/app_2026-06-14_004623.db`
- `906730647` real-entry reclassification backup: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/backups/app_2026-06-14_011044.db`
- Order-entry recovery backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_order_entry/app_2026-06-14_031017.db`
- Focused D1 cash-in backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_d1_cash_in/app_2026-06-14_031022.db`
- Cashflow daily rebuild backup: `exports/validation/orchestrator_order_entry_missing_recovery_20260614/backups_cashflow_rebuild/app_2026-06-14_031029.db`
- STOREB current-63 order-entry recovery backup: `exports/validation/orchestrator_storeb_63_api_refetch_20260614/backups_order_entry_current_63/app_2026-06-14_032820.db`
- Lifecycle residual repair backup: `exports/validation/orchestrator_lifecycle_residual_repair_20260614/backups_prod_lifecycle/app_2026-06-14_033810.db`

## Validation

Commands/results already run for this closeout:

- Focused pytest:
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_ads_active_scope.py tests/test_kaspi_marketing_scrape.py tests/test_materialize_ads_campaign_product_daily.py tests/test_materialize_meta_external_ads_spend.py tests/test_policy_materialization_c3.py tests/test_materialize_governed_stock_repairs.py`
  Result: `63 passed`.
- DB tracked/staged guard:
  `scripts/check_no_db_tracked.sh`
  Result: `DB guard OK`.
- Daily ops pause verification:
  `python3 scripts/manage_business_automation.py verify --scope daily-ops --expect paused --output-json exports/automation_control/2026-06-14/20260614_final_orchestrator_verify_daily_ops_paused.json`
  Result: `verify: OK`, `labels: 0/10 loaded`, evidence `exports/automation_control/2026-06-14/20260614_001645_verify_daily-ops`.
- Header-only wrapper focused pytest:
  `pytest -q tests/test_header_only_source_gap_quarantine.py tests/test_header_only_source_gap_quarantine_prod_wrapper.py`
  Result: `8 passed`.
- Header-only production apply validation:
  `exports/validation/orchestrator_header_only_prod_apply_20260614/operational_stock_after_prod_apply.json`
  Result: `RED`, `finding_count=496`; C3 strict validators still block on `src_ab_db_stock_truth`, `source_freshness`, and `stock_source_truth`.
- Daily ops pause verification after header-only production apply:
  `exports/validation/orchestrator_header_only_prod_apply_20260614/daily_ops_paused_after_prod_apply.json`
  Result: `ok=true`, `labels: 0/10 loaded`, protected surfaces quiet, cron quiet.
- `906730647` reclassification focused pytest:
  `pytest -q tests/test_header_only_real_entry_reclassification.py tests/test_header_only_source_gap_quarantine.py tests/test_header_only_source_gap_quarantine_prod_wrapper.py`
  Result: `14 passed`.
- `906730647` production apply validation:
  `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/operational_stock_after_prod_apply.json`
  Result: `RED`, `finding_count=494`; header-only leak errors are gone.
- Daily ops pause verification after `906730647` production apply:
  `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/daily_ops_paused_after_prod_apply.json`
  Result: `ok=true`, `labels: 0/10 loaded`, protected surfaces quiet, cron quiet.
- Order-entry/D1 focused pytest:
  `pytest -q tests/test_repair_d1_cash_in_from_validator_evidence.py tests/test_recover_order_entries_from_evidence.py tests/test_cashflow_translator.py tests/test_rebuild_cashflow_calendar_write_gate.py`
  Result: `63 passed`.
- Order-entry/D1 production apply validation:
  `exports/validation/orchestrator_order_entry_missing_recovery_20260614/prod_operational_stock_after_focused_recovery.json`
  Result: `RED`, `finding_count=338`; no `CASHFLOW_D1_CASH_IN_MISSING`, no quarantine leakage.
- Daily ops pause verification after order-entry/D1 production apply:
  `exports/validation/orchestrator_order_entry_missing_recovery_20260614/daily_ops_paused_after_prod_apply_retry.json`
  Result: `ok=true`, `labels: 0/10 loaded`, protected surfaces quiet, cron quiet.
- STOREB current-63 scoped order-entry tests:
  `pytest -q tests/test_recover_order_entries_from_evidence.py`
  Result: `20 passed`.
- STOREB current-63 production apply validation:
  `exports/validation/orchestrator_storeb_63_api_refetch_20260614/prod_operational_stock_after_current_63.json`
  Result: `RED`, `finding_count=275`; `ORDER_ENTRY_MISSING` cleared to `0`, no D1 cash-in gap.
- Lifecycle residual repair tests:
  `pytest -q tests/test_repair_sales_fact_v2_lifecycle_residual.py tests/test_recover_order_entries_from_evidence.py`
  Result: `25 passed`.
- Lifecycle production apply validation:
  `exports/validation/orchestrator_lifecycle_residual_repair_20260614/prod_operational_stock_after_lifecycle.json`
  Result: `GREEN`, `finding_count=267`, with only warning quarantines:
  `ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED=244`,
  `ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED=23`.
- Current D1 coverage probe:
  `exports/validation/orchestrator_lifecycle_residual_repair_20260614/prod_d1_cash_in_probe_after_lifecycle/summary.json`
  Result: `PASS`, `cash_in_missing_count=0`, `would_insert_event_rows=0`.
- Current strict source freshness:
  `exports/validation/orchestrator_lifecycle_residual_repair_20260614/prod_policy_source_freshness_after_lifecycle.json`
  Result: fails only `src_ab_db_stock_truth STALE`.
- Governed stock materializer guard tests:
  `pytest -q tests/test_materialize_governed_stock_repairs.py tests/test_repair_sales_fact_v2_lifecycle_residual.py tests/test_recover_order_entries_from_evidence.py`
  Result: `30 passed`.

Known validation caveat:

- `scripts/lint_docs.sh` still fails on pre-existing green-path banned-number references outside the newly committed lane closeouts.

## Remaining Stopline

Production negative stock rows after source-backed repairs:

```text
SUIT-31-LS_3XL|UNIVERSAL|-3
LINE-31-TS_3XL|UNIVERSAL|-2
SUIT-31-LS_XL|UNIVERSAL|-2
LINE-31-LS_XL|UNIVERSAL|-1
LINE-31-TS_XL|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_L|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_M|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_S|UNIVERSAL|-1
SUIT-31-TS_XL|UNIVERSAL|-1
```

Snapshot rebuild still correctly refuses while those rows remain negative.

Prepared approval-gated manifest:

- `config/governed_stock_owner_approval_repairs_20260614.json`
- No-approval dry-run proof: `exports/validation/orchestrator_owner_approval_stock_stopline_20260614/dry_run_without_owner_evidence/`
- Result: `blocked_count=9`, `candidate_event_count=0`, `applied_rows=0`
- Approval evidence under `docs/agent_handoffs` is rejected by the materializer so closeouts and starter prompts cannot authorize a write.

## Additional Phase 2 Blockers From Current Audit

Current operational stock integration finding census after STOREB current-63 and lifecycle production applies:

```text
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

There are no remaining operational-stock `ERROR` findings. The validator status is `GREEN`; these 267 rows are retained warning quarantines and remain excluded from product-level stock/COGS/profit publication truth.

The 251-row header-only cleanup, `906730647` real-entry reclassification, 169 source-backed order-entry recovery rows, 2 focused D1 cash-in rows, cashflow daily rebuild, 64 STOREB API-entry rows, and 8 lifecycle residual reclassifications are now applied in production.

Final DB SHA after this lane: `6a3292128172d6f271bd00f1e78da043c07f3e657d542019a700722ad85365cb`.

## Approval Phrases Needed

LINE/SUIT parent-child allocation:

```text
I approve a governed stock allocation contract from the approved parent physical stock pools to these compact child stock_ledger rows, effective 2026-06-11T22:00:00+05:00, using the 2026-06-04 approved manual stock count plus the 2026-06-11 owner-authoritative ADDITION batch and the existing compact child article-map evidence as source artifacts. Allocate exactly: SUIT-31-LS_3XL +3 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_3XL; SUIT-31-LS_XL +2 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL; SUIT-31-TS_XL +1 from CL_NEW-CLO2_MEN_SUIT-61_BLACK_XL; LINE-31-LS_XL +1 from CL_OC_MEN_LINE51_WHITE_XL; LINE-31-TS_XL +1 from CL_OC_MEN_LINE51_WHITE_XL; LINE-31-TS_3XL +2 from CL_OC_MEN_LINE51_WHITE_3XL. This authorizes a mapping/allocation contract, not invented stock and not a NEGATIVE_CLAMP_* repair. It does not authorize Kaspi merchant, pricing, workbook, Telegram, LaunchAgent, customer, or operator-message writes.
```

KID-31 black manual owner fact:

```text
I create a manual owner stock fact for KID-31 black letter rows because no exact source artifact currently proves the S/M/L allocation. Effective 2026-06-04T14:00:23+05:00, add exactly CL_NEW-CLO_KIDS_KID-31_BLACK_L +1, CL_NEW-CLO_KIDS_KID-31_BLACK_M +1, and CL_NEW-CLO_KIDS_KID-31_BLACK_S +1 to the UNIVERSAL stock ledger as owner-approved manual facts. This approval does not claim these rows came from the numeric/height 22/24/26/28/30 count unless a separate mapping contract is approved. This is not a NEGATIVE_CLAMP_* repair and does not authorize external writes.
```

## Next Step After Approval

After the owner supplies the exact approval phrase(s), run the same backup-first pattern:

1. Save the exact owner approval text in a separate non-handoff evidence file.
2. Dry-run `config/governed_stock_owner_approval_repairs_20260614.json` on production DB and copied DB with `--approval-evidence`.
3. Apply only with explicit env gates, `--expected-pre-sha256`, and `--backup-dir`.
4. Rebuild the stock snapshot for `2026-06-13`.
5. Replay C3 materialization.
6. Re-run DB guard, stock validators, source-freshness gate, and daily-ops paused verification.
