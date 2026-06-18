# PKT-READY Phase 0 Go/No-Go

- Repo inspected read-only: `~/Docs/Autonomous_business`
- Scratch DB base: `/tmp/green_path_scratch/restore_test.sqlite`
- Dry-run DB handling: per-candidate scratch copy when a DB override was available; skipped when dry-run would touch repo `db/app.db` or repo-local lock/output paths.

| Script | Categories | Gates | Dry-run status | Recommendation | Reason |
| --- | --- | --- | --- | --- | --- |
| `scripts/apply_header_only_source_gap_quarantine_production_safe.py` | quarantine_triage | env=ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_PRODUCTION_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --backup-dir, --classification, --expected-candidate-rows, --expected-pre-sha256, --expected-product-cashflow-delete-rows, --expected-sales-fact-product-profit-null-rows, --expected-stock-ledger-delete-rows |
| `scripts/apply_kaspi_pay_cash_anchor.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_ANCHOR_WRITE<br>apply=True<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/apply_storeb_api_order_entries_from_agent31_production_safe.py` | order_entries_backfill | env=ENABLE_STOREB_API_ORDER_ENTRY_PRODUCTION_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --api-entries, --backup-dir, --expected-candidate-entry-rows, --expected-inserted-entry-rows, --expected-pre-sha256, --expected-quarantine-rows, --expected-safe-order-rows, --quarantine-rows, --safe-rows |
| `scripts/apply_storeb_product_identity_quarantine_production_safe.py` | quarantine_triage | env=ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_PRODUCTION_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --backup-dir, --candidates, --expected-candidate-rows, --expected-pre-sha256, --expected-product-cashflow-delete-rows, --expected-stock-ledger-delete-rows |
| `scripts/apply_owner_approved_beli_child_cogs_rows.py` | cogs_backfill | env=ENABLE_OWNER_APPROVED_LINE_CHILD_COGS_ROW_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/apply_owner_confirmed_article_map_overrides.py` |  | env=ENABLE_OWNER_CONFIRMED_ARTICLE_MAP_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/apply_rebuild_snapshot_production_safe.py` |  | env=ENABLE_REBUILD_SNAPSHOT_PRODUCTION_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --backup-dir, --date, --expected-current-stock-total, --expected-existing-rows, --expected-inbound-stock-total, --expected-pre-sha256, --expected-rows-created, --mode, --store |
| `scripts/apply_line31_compact_child_cogs_exception.py` | cogs_backfill | apply=True<br>dry=False | passed (0) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/backfill_exception_queue_c3_metadata.py` | quarantine_triage | apply=True<br>dry=False | skipped (None) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/backfill_order_entries_offer_id.py` | order_entries_backfill | env=ENABLE_ORDER_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/backfill_orders_sku_from_sales_v2.py` | order_entries_backfill | env=ENABLE_ORDER_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --since, --until |
| `scripts/backfill_recent_order_identity.py` | order_entries_backfill | env=ENABLE_DB_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --as-of, --reference-csv |
| `scripts/bootstrap_ledger.py` | ledger_stock_anchor_import | apply=False<br>dry=True | skipped (None) | **NO** | no DB override detected; dry-run could inspect or open live repo db/app.db |
| `scripts/build_fact_sales_v16.py` | order_entries_backfill | apply=True<br>dry=False | passed (0) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/build_fact_sales_v16_from_api.py` | order_entries_backfill | env=ENABLE_FACT_SALES_V16_WRITE<br>apply=True<br>dry=False | failed (124) | **NO** | dry-run command failed; inspect output summary |
| `scripts/build_kaspi_marketing_owner_workbook.py` | ads_sync_backfill | apply=False<br>dry=False | passed (0) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/build_manual_stock_20260604_pre_shipments_anchor.py` | ledger_stock_anchor_import | apply=False<br>dry=False | skipped (None) | **NO** | no DB override detected; dry-run could inspect or open live repo db/app.db |
| `scripts/build_offer_stock_mapper.py` | ledger_stock_anchor_import, price_floor_generation | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/check_on_delivery_residuals.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=False<br>dry=False | failed (3) | **NO** | dry-run command failed; inspect output summary |
| `scripts/clamp_negative_ledger.py` | ledger_stock_anchor_import | env=ENABLE_NEGATIVE_LEDGER_CLAMP_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --snapshot-date |
| `scripts/daily_pipeline_v2.py` | end_of_day_apply | apply=False<br>dry=True | skipped (None) | **NO** | broad daily pipeline uses hardcoded repo DB paths in child steps |
| `scripts/dedupe_cashflow_order_events.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/deploy_kaspi_pricelist.py` | price_floor_generation | apply=False<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --store |
| `scripts/derive_fx_rates.py` | fx_import | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/detect_stockouts.py` | ledger_stock_anchor_import | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/generate_bank_accounts_history_totals.py` | cashflow_rebuild | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/generate_bank_snapshot.py` | cashflow_rebuild | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/generate_kaspi_pricelist_xml.py` | price_floor_generation | apply=False<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --store |
| `scripts/generate_recurring_commitments.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --amount-kzt, --start-date |
| `scripts/import_cash_balance_checks.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_cashflow_balance_checks.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_cashflow_commitments.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | failed (2) | **NO** | dry-run command failed; inspect output summary |
| `scripts/import_cashflow_events.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | failed (2) | **NO** | dry-run command failed; inspect output summary |
| `scripts/import_cashflow_opening_balances.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_cashflow_payouts.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_exchanger_emails.py` | fx_import | apply=False<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/import_kaspi_pay_mt940.py` |  | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_opex_protocol.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/import_po_arrivals_as_inventory_in.py` | ledger_stock_anchor_import | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_sku_costs.py` | cogs_backfill | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/import_transfer_ledger_cashflow.py` | cashflow_rebuild, ledger_stock_anchor_import | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/ingest_inventory_snapshot.py` | ledger_stock_anchor_import | apply=False<br>dry=True | failed (2) | **NO** | dry-run command failed; inspect output summary |
| `scripts/install_kaspi_marketing_scheduler.sh` | ads_sync_backfill | apply=False<br>dry=False | skipped (None) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/kaspi_marketing_scrape.py` | ads_sync_backfill | apply=False<br>dry=False | failed (1) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/mark_exchanger_order_status.py` | fx_import | apply=False<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --status |
| `scripts/materialize_ads_campaign_product_daily.py` | ads_sync_backfill | env=ENABLE_C3_ADS_SOURCE_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --end, --start |
| `scripts/materialize_copied_temp_source_freshness_bridge.py` |  | env=ENABLE_C3_POLICY_MATERIALIZATION_WRITE<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --as-of, --bridge |
| `scripts/materialize_header_only_source_gap_quarantine.py` | quarantine_triage | env=ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --classification |
| `scripts/materialize_storeb_api_order_entries_from_agent31.py` | order_entries_backfill | env=ENABLE_STOREB_API_ORDER_ENTRY_TEMP_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --api-entries, --quarantine-rows, --safe-rows |
| `scripts/materialize_storeb_product_identity_quarantine.py` | quarantine_triage | env=ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_TEMP_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --candidates |
| `scripts/materialize_negative_ledger_exceptions.py` | ledger_stock_anchor_import | env=ENABLE_NEGATIVE_LEDGER_EXCEPTION_WRITE<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --as-of, --source-csv |
| `scripts/materialize_order_status_events_from_kaspi_orders.py` |  | env=ENABLE_ORDER_STATUS_EVENT_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/materialize_policy_source_freshness.py` |  | env=ENABLE_C3_POLICY_MATERIALIZATION_WRITE<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --as-of |
| `scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py` | ledger_stock_anchor_import, order_entries_backfill | env=ENABLE_STOCK_LEDGER_SALES_REPLAY_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --end-date, --start-date |
| `scripts/migrate_013_ledger.py` | ledger_stock_anchor_import | apply=False<br>dry=False | passed (0) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/migrate_018_cashflow_calendar.py` | cashflow_rebuild | apply=False<br>dry=False | passed (0) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/migrate_021_fact_sales_v16.py` | order_entries_backfill | apply=False<br>dry=False | passed (0) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/migrate_022_po_execution_tables.py` |  | env=ENABLE_SCHEMA_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/migrate_023_po_parts_schema.py` |  | env=ENABLE_SCHEMA_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/migrate_024_order_synced_at.py` |  | env=ENABLE_SCHEMA_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/migrate_025_dim_sku_weight_guard.py` |  | env=ENABLE_SCHEMA_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/migrate_028_operational_stock_truth_p0_schema.py` | ledger_stock_anchor_import | env=ENABLE_SCHEMA_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/normalize_ledger_store_code.py` | ledger_stock_anchor_import | apply=True<br>dry=True | passed (0) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/rebuild_cashflow_calendar.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py` | order_entries_backfill | env=ENABLE_SALES_FACT_V2_REBUILD_APPLY<br>apply=True<br>dry=False | skipped (None) | **NO** | required options need task-specific inputs: --as-of |
| `scripts/reconcile_ledger_to_snapshot.py` | ledger_stock_anchor_import | env=ENABLE_STOCK_RECONCILE_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --snapshot-date |
| `scripts/reconcile_on_delivery_settlement.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/recover_order_entries_from_evidence.py` | order_entries_backfill | env=ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE,ENABLE_ORDER_ENTRY_RECOVERY_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --as-of |
| `scripts/repair_d1_cashflow_residue_from_evidence.py` | cashflow_rebuild | env=ENABLE_D1_RESIDUE_REPAIR_PRODUCTION_WRITE,ENABLE_D1_RESIDUE_REPAIR_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --as-of |
| `scripts/repair_sales_fact_v2_lifecycle_residual_from_status_evidence.py` | cashflow_rebuild, order_entries_backfill | apply=True<br>dry=True | skipped (None) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/replay_manual_stock_20260604_after_shipments_scenario.py` | ledger_stock_anchor_import | apply=False<br>dry=False | skipped (None) | **NO** | no DB override detected; dry-run could inspect or open live repo db/app.db |
| `scripts/repopulate_sales_fact_from_crm.py` | order_entries_backfill | apply=False<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/run_daily_autopilot.py` | end_of_day_apply | apply=False<br>dry=False | failed (124) | **NO** | dry-run command failed; inspect output summary |
| `scripts/run_daily_pipeline.py` | end_of_day_apply | apply=False<br>dry=True | skipped (None) | **NO** | broad daily pipeline uses hardcoded repo DB paths in child steps |
| `scripts/run_end_of_day.py` | end_of_day_apply | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | end-of-day dry-run would create a repo lock file and call hardcoded repo DB subcommands |
| `scripts/run_exchange_imports.sh` | fx_import | env=ENABLE_BANK_ACCOUNTS_WRITE<br>apply=False<br>dry=False | skipped (None) | **NO** | non-Python candidate; not run by Python dry-run harness |
| `scripts/run_offer_stock_price_sync.py` | ledger_stock_anchor_import, price_floor_generation | apply=False<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/run_operational_stock_daily_truth.py` | ledger_stock_anchor_import | env=ENABLE_OPERATIONAL_STOCK_DAILY_DB_WRITE<br>apply=False<br>dry=False | failed (124) | **NO** | dry-run command failed; inspect output summary |
| `scripts/run_stock_anchor_20pct.py` | ledger_stock_anchor_import | env=ENABLE_STOCK_ANCHOR_20PCT_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/run_write_canary.py` |  | env=ENABLE_PROD_DB_CANARY_WRITE,ENABLE_WRITE_CANARY_APPLY<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/seed_inventory_open_from_snapshot.py` |  | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | skipped (None) | **NO** | required options need task-specific inputs: --as-of |
| `scripts/sync_ads_sidecar.py` | ads_sync_backfill | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/sync_bank_manual_ingest_snapshot.py` | cashflow_rebuild | env=ENABLE_BANK_MANUAL_INGEST_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/sync_cash_balances_from_inbound_calendar.py` | cashflow_rebuild | env=ENABLE_CASH_BALANCE_SYNC_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/sync_current_stock.py` | ledger_stock_anchor_import | env=ENABLE_STOCK_SNAPSHOT_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/sync_dim_sku_from_dim_sku_light.py` |  | env=ENABLE_DIM_SKU_SYNC_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/sync_opex_schedule.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/sync_po_arrivals_to_ledger.py` | ledger_stock_anchor_import | apply=True<br>dry=True | passed (0) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/sync_po_parts_from_inbound_calendar.py` |  | env=ENABLE_PO_PART_SYNC_WRITE<br>apply=True<br>dry=True | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/transfer_ledger_autopilot.py` | cashflow_rebuild, ledger_stock_anchor_import | apply=False<br>dry=False | failed (1) | **NO** | write tokens found without --apply or --dry-run guard |
| `scripts/translate_orders_to_cashflow_events.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=True | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/translate_transfer_ledger_to_cashflow.py` | cashflow_rebuild, ledger_stock_anchor_import | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |
| `scripts/update_cashflow_dashboard.py` | cashflow_rebuild | env=ENABLE_CASHFLOW_WRITE<br>apply=True<br>dry=False | failed (1) | **NO** | dry-run command failed; inspect output summary |
| `scripts/update_dim_sku_price.py` | price_floor_generation | apply=True<br>dry=True | skipped (None) | **NO** | has --apply/write surface but no explicit env gate token found |
| `scripts/upsert_fx_rates.py` | fx_import | apply=False<br>dry=True | failed (2) | **NO** | dry-run command failed; inspect output summary |
| `scripts/validate_operational_stock_schema.py` | ledger_stock_anchor_import | apply=False<br>dry=False | passed (0) | **GO** | dry-run completed without count changes on scratch DB copy |

## Dry-Run Notes

Output summaries and sample diff/output lines are in `write_candidates.json`. Candidate commands were generated only with the repo venv Python.
