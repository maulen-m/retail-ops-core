# STOREB Owner Mapping Production Apply Closeout

Generated at: `2026-05-12T10:25:47+0500`

Gate: `GREEN_PRODUCTION_DB_APPLY_ONLY`

## Scope

The owner explicitly authorized:

`Apply only the already-proven STOREB owner mapping replay to production DB, backup-first, no workbook, no scheduler, no external writes, no owner publication yet.`

No workbook, scheduler, Web_automation, browser/session, external system, Kaspi merchant, cash, PO, ad-spend, price, stock, or owner-publication action was performed.

## Result

The already-proven STOREB owner mapping replay was applied to production `db/app.db`.

- Production DB before SHA: `ee7d2999852d5a438605e7057bd82f954c0df4466016704a55e0b09f91e99820`
- Production DB after SHA: `80d32c82932a801c6165e6014f3b66ef094352309d64ec037b78be81c8a0448d`
- Workbook SHA unchanged: `abef2d310e768bc76f54c9cfe5a6f72c6d22eab2504894114bafb493916f67a8`
- DB integrity after: `ok`
- Final `lsof db/app.db`: no holders observed

## Applied Data

- Window: `2026-05-05..2026-05-11`
- Store: `STOREB`
- SKU: `CL_OC_MEN_LINE52_BLACK`
- Before rows: `0`
- After rows: `7`
- After cost: `38624.07` KZT
- Source rows mapped: `70/70`
- Product-code mappings: `10/10`
- Owner-confirmed product-code mappings loaded: `7`
- Unmapped rows: `0`

## Evidence

- Evidence root: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321`
- Final classification: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/final_blocker_classification.json`
- Adapter apply report: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/adapter_apply/report.json`
- Post rows CSV: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/adapter_apply/post_ads_campaign_product_daily_rows.csv`
- Post refresh CSV: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/adapter_apply/post_ads_source_refresh_runs.csv`

## Backups

- Explicit pre-apply backup: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/backups/app_db_pre_storeb_owner_mapping_apply_20260512_102321.sqlite`
- Explicit pre-apply backup SHA: `7ce528f05ce21fa2fd16b922e132553612a149d34e662318a200648d895c2af2`
- Script backup: `~/Docs/Autonomous_business/exports/validation/storeb_owner_mapping_production_apply/20260512_102321/adapter_apply/backups/app_2026-05-12_102457.db`
- Script backup SHA: `5161bcab9d0c2514c0214141d5852aa72335ef354ec7027ed3615e3dba05b7b0`

Rollback, if explicitly needed later:

1. Ensure no process holds `db/app.db`.
2. Preserve the current post-apply DB as a separate timestamped copy.
3. Replace `db/app.db` from the explicit pre-apply backup above.
4. Rerun DB integrity and the ads validators.

## Validators

- `validate_ads_sidecar_readiness.py`: `PASS`
- `validate_ads_offer_universe_coverage.py`: `PASS`
- `validate_ads_spend_reality.py`: `PASS`
- Focused materializer tests: `8 passed`
- Docs lint: `OK`
- DB tracked guard: `OK`

## Next Gate

STOREB ads mapping is no longer the production blocker for this window.

Still blocked until a separate reviewed/authorized lane:

- owner publication;
- scheduler install, enablement, or execution;
- workbook mutation;
- Web_automation or external writes;
- Kaspi merchant writes;
- ad-spend, cash, PO, price, or stock decisions.
