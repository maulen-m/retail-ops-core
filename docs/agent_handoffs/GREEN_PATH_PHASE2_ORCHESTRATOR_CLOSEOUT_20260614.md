# Green Path Phase 2 Orchestrator Closeout

Gate: YELLOW

Date: 2026-06-14

## Current State

Phase 2 implementation is durably committed for the lanes that had source-backed authority:

- C3/source-freshness and Meta external spend provenance are committed.
- Ads source truth is green after scope/backfill repair.
- Stock source-backed negative rows are repaired in production.

The repo is not yet allowed to claim full green state because `stock_source_truth` still has 9 negative stock_ledger rows that require explicit owner approval or a new exact source artifact. This is an intentional stopline, not a code failure.

No Kaspi merchant, pricing, Telegram, LaunchAgent, workbook, customer, or operator-message writes were performed by this orchestrator closeout step.

## Committed Checkpoints

- `5e943c5 feat: harden c3 source freshness evidence`
- `14311b0 fix: backfill ads source truth`
- `b849ef6 feat: apply governed stock source repairs`

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

## Production DB Evidence

- Cashflow D1 backup: `exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/backups/app_before_agent18_cashflow_d1_prod_apply_20260613.db`
- Ads partial backup: `exports/validation/agent21_ads_partial_prod_apply_20260613/backups/app_before_agent21_ads_partial_apply_20260613.db`
- Meta spend backup: `exports/validation/orchestrator_meta_external_spend_prod_apply_20260613/backups/app_before_meta_external_spend_prod_apply_20260613.db`
- Ads scope/backfill backup: `exports/validation/orchestrator_ads_scope_backfill_prod_apply_20260613/backups/app_before_ads_scope_backfill_prod_apply_20260613.db`
- Stock source-backed backup: `exports/validation/orchestrator_stock_source_backed_repair_prod_apply_20260614/backups/app_before_stock_source_backed_repair_prod_apply_20260614.db`

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

1. Create a manifest for the approved LINE/SUIT allocation and/or KID-31 manual facts.
2. Dry-run on production DB and copied DB.
3. Apply only with explicit env gates and a DB backup.
4. Rebuild the stock snapshot for `2026-06-13`.
5. Replay C3 materialization.
6. Re-run DB guard, stock validators, source-freshness gate, and daily-ops paused verification.

