# CRM Excel Pipeline Decommission Map - 2026-07-06

Gate: GREEN

Scope: read-only census and design map for retiring `excel_ui/SALES_KSP_CRM_V3.xlsx` as an active data feeder.

This document intentionally contains no customer names, phone numbers, or order IDs. It names files, tables, columns, scripts, gates, dates, counts, and SKU/product-system terms only.

## Executive Verdict

The workbook is no longer the primary human daily order-processing surface. The active owner/operator daily path is:

`Kaspi API / ActiveOrders export -> fact_orders_kaspi -> Google Ops Board -> Google size writeback -> DB-first closeout -> Telegram / waybill workflow`

Code evidence:
- `docs/DAILY_SOP.md` says the Google Ops Board is the primary editable daily table and that the post-cutoff green gate must not depend on the local CRM workbook.
- `docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md` defines `SalesRaw_Today.MY_SIZE` as the employee-editable size column and the explicit writeback target as `fact_orders_kaspi.assigned_size`.
- `scripts/run_google_ops_board_closeout.py:819-850` runs final size writeback first.
- `scripts/run_google_ops_board_closeout.py:925-1018` calls `ship_orders_api.py --selection-source db`, `download_waybills_api.py --db-path ...` without `--fallback-crm`, and `build_daily_waybills.py --db-path ...`.

However, the workbook is still a live scheduled and validation dependency:
- `excel_ui/run_full_import.command` still runs CRM workbook integrity checks, Excel session preflight, guarded CRM append, and final API-vs-CRM gates.
- `scripts/run_kaspi_import_scheduler.py` still runs `excel_ui/run_full_import.command` from LaunchAgent `com.example.kaspi-import-v2`.
- `scripts/sync_crm_to_db.py` still reads the workbook into `sales_fact_v2` and `fact_sales`.
- `com.example.crm-db-sync` still points at `scripts/sync_crm_to_db.py`.
- Strict anchor/preflight gates still require `config/anchors/SALES_KSP_CRM_LATEST.xlsx`.

Runtime log evidence from `runtime_logs/kaspi_import_stdout.log` on 2026-07-06 shows the fragility class: CRM snapshot mismatch sends Step 2 into the guarded Excel writer, Excel/xlwings is opened hidden, stale `~$SALES_KSP_CRM_V3.xlsx` locks are detected, the workflow reports 600-second CRM import timeouts, and Google Ops Board publish still proceeds from DB truth after the CRM lane is red.

## Census Method

Commands run, read-only except creating this file:

```bash
grep -rln "SALES_KSP_CRM" scripts core excel_ui tests config
grep -rln --exclude-dir='__pycache__' "SALES_KSP_CRM" scripts core excel_ui tests config
rg -n -i "workbook|crm|anchor" -g '*scheduler*.py' -g '*.plist' -g 'business_automation_manifest.json' scripts config docs/DAILY_SOP.md
find ~/Library/LaunchAgents -maxdepth 1 \( -name 'com.example.*.plist' -o -name 'com.autonomous-business.*.plist' \) -print
rg -n -i "SALES_KSP_CRM|workbook|crm|anchor|google-ops|waybill|shipped|import|sync_crm|run_full_import|build_waybills" ~/Library/LaunchAgents/com.example.*.plist ~/Library/LaunchAgents/com.autonomous-business.*.plist
sqlite3 -readonly db/app.db "SELECT name, sql FROM sqlite_master WHERE type IN ('table','view') AND name IN ('fact_orders_kaspi','sales_fact_v2','fact_sales','kaspi_orders_y','stock_ledger','dim_sku_size','dim_sku');"
```

Reference counts:
- Raw `grep -rln "SALES_KSP_CRM"` including `__pycache__`: 294 files.
- Actionable source/config/test/runbook hits excluding `__pycache__`: 111 files.
- Indirect sweep found additional scheduler, Google Ops Board, LaunchAgent, and runbook couplings that do not all contain the literal `SALES_KSP_CRM`.

## Lane Counts

Primary 111-file literal census, excluding `__pycache__`:

| lane | total | live | legacy | meaning |
|---|---:|---:|---:|---|
| L1 | 10 | 10 | 0 | live scheduled CRM import and CRM-to-DB sync lane |
| L2 | 10 | 5 | 5 | waybill, shipping, shipped/status lane |
| L3 | 19 | 15 | 4 | truth, anchor, green-path, and strict gates |
| L4 | 1 | 1 | 0 | Google Ops Board literal hit |
| L5 | 32 | 0 | 32 | historical one-shot backfills, repairs, proofs |
| L6 | 39 | 28 | 11 | tests/contracts, mapped to guarded lane in notes |
| total | 111 | 59 | 52 | primary literal census |

Indirect addendum not included in the 111 count:
- 22 repo files/scripts/config/docs found by scheduler/runbook/indirect coupling sweep.
- 11 LaunchAgent plists under `~/Library/LaunchAgents` found by launchd sweep.

## Primary Inventory

`reads-or-writes workbook` values:
- `read`: opens or parses the workbook.
- `write`: appends, repairs, syncs, updates, or backs up the workbook.
- `both`: reads and writes.
- `contract`: mentions or enforces the workbook contract without runtime workbook IO.
- `none`: no workbook IO despite the reference.

| file | lane | live/legacy | reads-or-writes workbook | phase to address | notes |
|---|---|---|---|---|---|
| `scripts/build_daily_waybills.py` | L2 | live | read fallback | Phase 2 | DB/API-first now; only loads CRM when DB path yields no orders or fallback enrichment is explicitly available. |
| `scripts/validate_pending_orders.py` | L1 | live | read | Phase 2 | Post-import/current batch validator tied to CRM rows. |
| `scripts/ops_preflight.py` | L3 | live | read/contract | Phase 2 | Preflight/health surface that references workbook anchor expectations. |
| `scripts/sync_sales_sources_to_db.py` | L3 | live | read | Phase 2 | Sales source reconciliation path; needs DB/API re-anchor. |
| `scripts/reconcile_sales_sources.py` | L3 | live | read | Phase 2 | Compares CRM/workbook source against DB/source views. |
| `scripts/import_orders_to_crm.py` | L1 | live | both | Phase 3 | Main Excel writer; backup-first, xlwings/openpyxl append, clears new `MY_SIZE`, updates status fields when enabled. |
| `scripts/reconcile_kaspi_archive_orders.py` | L5 | legacy | read | leave/Phase 3 | Archive reconciliation and `kaspi_orders_y` builder; not current direct-feeder input. |
| `scripts/launch_agent751_753_after_agent750.py` | L3 | legacy | contract | Phase 3 | Old Agent750 launch chain. |
| `scripts/run_owner_truth_daily.py` | L3 | live | read/contract | Phase 2 | Owner truth gate includes CRM/source truth expectations. |
| `scripts/repair_sales_crm_append_artifacts.py` | L5 | legacy | read | leave | Repair/audit artifact for old append failures. |
| `scripts/export_sizing_queue.py` | L5 | legacy | read | remove Phase 3 if unused | Legacy sizing queue export around CRM-sized orders. |
| `scripts/check_agent750_launch_readiness.py` | L3 | legacy | read/contract | leave | Old Agent750 readiness checker. |
| `scripts/validate_sales_against_workbook.py` | L3 | live | read | Phase 2 | Workbook freshness/parity validator; will go red when workbook freezes unless re-anchored. |
| `scripts/backfill_line61_kaspi_core.py` | L1 | live | both | Phase 2/3 | Still invoked by full import after CRM changes; updates workbook-derived core/grouping. |
| `scripts/validate_kaspi_parsing_integrity.py` | L3 | live | read | Phase 2 | Parsing truth guard includes workbook sample/source checks. |
| `scripts/build_ops_drift_pack.py` | L3 | live | read | Phase 2 | Drift evidence packet reads CRM-derived truth. |
| `scripts/ship_orders_api.py` | L2 | live | read fallback | Phase 2 | Current closeout passes `--selection-source db`; default/manual path remains CRM. |
| `scripts/install_single_truth_ops_scheduler.sh` | L3 | live | contract | Phase 2 | Installs strict anchor/preflight scheduler contracts. |
| `scripts/sync_crm_sizes_to_db.py` | L2 | legacy | read | Phase 3 | Copies workbook `MY_SIZE` into `fact_orders_kaspi.assigned_size` with `size_source=CRM_MANUAL`; legacy manual waybill path uses it. |
| `scripts/check_anchor_health.py` | L3 | live | read | Phase 2 | Enforces `SALES_KSP_CRM_LATEST.xlsx` symlink, mtime age, and content lag. |
| `scripts/validate_sales_truth_vs_crm_north_star.py` | L3 | live | read | Phase 2 | North-star CRM comparison. |
| `scripts/validate_webui_archive_vs_crm_band.py` | L3 | live | read | Phase 2 | Compares web/archive sources to CRM band. |
| `scripts/report_waybill_status.py` | L2 | live | read | Phase 2 | Diagnostic/status report still derives size/status from CRM rows. |
| `scripts/evaluate_import_run_result.py` | L1 | live | read | Phase 2 | Final success gate compares ActiveOrders snapshot and CRM target-day IDs. |
| `scripts/backfill_recent_order_identity.py` | L5 | legacy | read | leave | One-shot/order identity backfill. |
| `scripts/patch_crm_identity_columns.py` | L5 | legacy | write | leave | CRM identity column repair. |
| `scripts/repair_crm_workbook.py` | L5 | legacy | both | freeze Phase 3 | Workbook repair tool; retain until final freeze backup exists. |
| `scripts/sync_crm_to_db.py` | L1 | live | read | Phase 1 | Current CRM -> `sales_fact_v2` and `fact_sales` sync. Direct feeder must replace this. |
| `scripts/import_orders_to_crm.py.bak` | L5 | legacy | both | remove Phase 3 | Backup copy of old CRM writer. |
| `scripts/rebuild_april23_stock_reanchor_split_views.py` | L5 | legacy | read | leave | Historical stock re-anchor view builder. |
| `scripts/rebuild_april23_stock_reanchor_coverage_closure.py` | L5 | legacy | read | leave | Historical stock re-anchor closure. |
| `scripts/download_waybills_api.py` | L2 | live | read fallback | Phase 2 | Current closeout is API/DB; `--fallback-crm` re-enters CRM. |
| `scripts/backfill_seller_delivery_fee_history.py` | L5 | legacy | read | leave | Historical fee backfill from CRM/history. |
| `scripts/validate_shipped_truth_crm_waybill.py` | L2 | live | read | Phase 2 | Shipped truth validator is CRM-vs-API-vs-waybill; needs DB/API evidence replacement. |
| `scripts/system_doctor.py` | L3 | live | read/contract | Phase 2 | Strict doctor requires workbook anchor for owner-truth runs. |
| `scripts/restore_my_size_from_backup.py` | L5 | legacy | read/write | leave | Workbook/manual size recovery tool. |
| `scripts/build_line31_launch_preflight_packet.py` | L3 | live | read/contract | Phase 2 | LINE31 preflight can include workbook/source truth surfaces. |
| `scripts/report_agent750_next_action.py` | L3 | legacy | contract | leave | Old Agent750 next-action report. |
| `scripts/run_crm_identity_repair_canary.py` | L5 | legacy | both | leave | Repair canary for CRM identity columns. |
| `scripts/backfill_crm_archive_period.py` | L5 | legacy | read | leave | Historical CRM/archive period backfill. |
| `scripts/sync_to_gdrive.py` | L5 | legacy | read | remove Phase 3 | Old workbook-to-GDrive sync; full import skips it unattended. |
| `scripts/import_kaspi_article_map_from_crm.py` | L5 | legacy | read | Phase 3 | Mapping import from CRM; should use DB/API mapping artifacts after cutover. |
| `scripts/run_google_ops_board_prewindow_health.py` | L4 | live | read/contract | Phase 2 | Publish profile skips workbook identity sync; full profile can still run workbook map sync. |
| `scripts/reimport_skipped_sales.py` | L5 | legacy | read | leave | Historical skipped-sales reimport. |
| `scripts/patch_kaspi_parsed_fields.py` | L5 | legacy | read/write | leave | Parsed-field repair. |
| `scripts/repopulate_sales_fact_from_crm.py` | L5 | legacy | read | remove Phase 3 | Bulk CRM -> sales repopulation; superseded by direct feeder. |
| `scripts/recover_order_entries_from_evidence.py` | L5 | legacy | read | leave | Evidence-based order-entry recovery. |
| `scripts/update_order_statuses.py` | L2 | legacy | both | remove Phase 3 | Deprecated CRM status updater. |
| `scripts/import_historical_sales.py` | L5 | legacy | read | leave | Historical sales import from workbook-like source. |
| `scripts/normalize_crm_north_star_inputs.py` | L5 | legacy | read | leave | North-star input normalizer. |
| `scripts/run_phase2_june15_production_apply.py` | L3 | legacy | contract | leave | Old Phase 2 apply harness. |
| `scripts/ingest_sales_v2.py` | L5 | legacy | read | Phase 3 | Alternate/older CRM sales ingest entrypoint. |
| `scripts/ingest_agent750_codecaptain_answer.py` | L5 | legacy | contract | leave | Agent750 artifact ingest. |
| `scripts/prepare_ci_headless_fixture.py` | L5 | legacy | read/write fixture | leave | Test fixture preparation around workbook shapes. |
| `scripts/rebuild_kaspi_identity_map_from_crm.py` | L5 | legacy | read | leave | Rebuilds identity map from CRM. |
| `scripts/seed_dev_db.py` | L5 | legacy | read | leave | Dev seed path includes CRM-derived examples. |
| `scripts/rebuild_fact_sales.py` | L5 | legacy | read | Phase 3 | Rebuilds `fact_sales` from CRM. Direct feeder should replace. |
| `scripts/reconcile_crm_sales_range.py` | L5 | legacy | read | leave | Date-range CRM reconciliation. |
| `scripts/repair_crm_formula_contract.py` | L5 | legacy | both | leave | Formula repair contract for CRM. |
| `scripts/report_import_status.py` | L1 | live | read | Phase 2 | Post-import health report compares API, CRM, DB, seller fee fields. |
| `scripts/build_cross_repo_business_event_bridge_v1.py` | L5 | legacy | contract | leave | Historical bridge packet code references CRM truth. |
| `scripts/apply_fact_sales_derived_replay.py` | L5 | legacy | read | leave | Derived replay/backfill. |
| `scripts/validate_crm_workbook_integrity.py` | L1 | live | read/write repair option | Phase 3 | Hard preflight in `run_full_import.command`. |
| `core/ingest/sales_ingest.py` | L1 | live | read | Phase 1 | Core CRM parser/ingester; direct feeder must match its semantics. |
| `excel_ui/run_full_import.command` | L1 | live | both | Phase 2/3 | Launchd import path: API export, DB sync, CRM writer, gates, Google publish. |
| `excel_ui/run_merged_build_waybills.command` | L2 | legacy | read | Phase 3 | Manual path syncs CRM manual sizes and uses `--fallback-crm`. |
| `excel_ui/run_build_waybills.command` | L2 | legacy | read | Phase 3 | Manual legacy waybill path. |
| `excel_ui/proof_runs/20260406_candidate_normalization_proof/import_run.log` | L5 | legacy | none | leave/archive | Historical proof log only. |
| `excel_ui/Archive.pre_migration_20260214_011023/23.1.26/run_build_waybills.command` | L2 | legacy | read | leave/archive | Archived pre-migration waybill command. |
| `tests/test_check_agent750_launch_readiness.py` | L6 | legacy | fixture/contract | leave | Guards old L3 Agent750 readiness. |
| `tests/test_repair_crm_workbook.py` | L6 | legacy | fixture | leave | Guards L5 workbook repair. |
| `tests/test_sales_workbook_anchor_parser.py` | L6 | live | fixture | Phase 2 | Guards L3 workbook-anchor parser. |
| `tests/test_check_anchor_health.py` | L6 | live | fixture | Phase 2 | Guards L3 anchor health failure modes. |
| `tests/test_rombik_kid30_alias.py` | L6 | live | fixture | Phase 2 | Guards identity resolution used by CRM ingest. |
| `tests/test_validate_sales_vs_workbook_anchor.py` | L6 | live | fixture | Phase 2 | Guards L3 sales-vs-workbook anchor gate. |
| `tests/test_sales_ingest.py` | L6 | live | fixture | Phase 1 | Guards L1 CRM sales ingest semantics. |
| `tests/test_validate_line31_launch_readiness.py` | L6 | live | contract | Phase 2 | Guards LINE31 launch readiness gates. |
| `tests/test_ops_docs_anchor_contract.py` | L6 | live | contract | Phase 2 | Guards docs/anchor contract. |
| `tests/test_validate_shipped_truth_crm_waybill.py` | L6 | live | fixture | Phase 2 | Guards L2 shipped truth CRM/waybill validator. |
| `tests/test_archive_waybill_inputs.py` | L6 | legacy | fixture | leave | Guards archived waybill inputs. |
| `tests/test_run_full_import_command_step2.py` | L6 | live | contract | Phase 2 | Guards L1 Step 2 CRM command wiring. |
| `tests/test_classify_workbook_anchor_overages.py` | L6 | live | fixture | Phase 2 | Guards workbook-anchor overage classification. |
| `tests/test_sales_truth_workbook_anchor.py` | L6 | live | fixture | Phase 2 | Guards truth views using workbook anchor tables. |
| `tests/test_single_truth_ops_scheduler_contract.py` | L6 | live | contract | Phase 2 | Guards plists/anchor-health contract. |
| `tests/test_backfill_recent_order_identity.py` | L6 | legacy | fixture | leave | Guards L5 identity backfill. |
| `tests/test_sales_ingest_fact_sales.py` | L6 | live | fixture | Phase 1 | Guards `fact_sales` CRM ingest economics. |
| `tests/test_prepare_ci_headless_fixture.py` | L6 | legacy | fixture | leave | Guards fixture prep. |
| `tests/test_backfill_seller_delivery_fee_history.py` | L6 | legacy | fixture | leave | Guards L5 fee history backfill. |
| `tests/test_run_owner_truth_daily_contract.py` | L6 | live | contract | Phase 2 | Guards L3 owner truth daily path. |
| `tests/test_gitignore_ops_reliability.py` | L6 | live | contract | Phase 2 | Guards ops reliability file hygiene. |
| `tests/test_published_sales_truth_matches_anchor_window.py` | L6 | live | fixture | Phase 2 | Guards published truth vs workbook anchor window. |
| `tests/test_evaluate_import_run_result.py` | L6 | live | fixture | Phase 2 | Guards L1 import result gate. |
| `tests/test_daily_shipping_enablement.py` | L6 | live | contract | Phase 2 | Guards daily shipping DB-first enablement. |
| `tests/test_repair_crm_formula_contract.py` | L6 | legacy | fixture | leave | Guards formula repair contract. |
| `tests/test_kaspi_offer_manifest_workflow.py` | L6 | live | fixture | Phase 2 | Indirect workflow guard with CRM fixture references. |
| `tests/test_import_orders_to_crm.py` | L6 | live | fixture | Phase 2/3 | Guards L1 CRM writer; many current failures are file-system/log-path related, not cutover proof. |
| `tests/test_validate_sales_against_workbook_freshness.py` | L6 | live | fixture | Phase 2 | Guards workbook freshness validator. |
| `tests/test_backfill_line61_kaspi_core.py` | L6 | live | fixture | Phase 2 | Guards L1 Line61 CRM backfill. |
| `tests/test_apply_fact_sales_derived_replay.py` | L6 | legacy | fixture | leave | Guards L5 replay. |
| `tests/test_apply_workbook_anchor_date_drift_repair.py` | L6 | legacy | fixture | leave | Guards date-drift repair. |
| `tests/test_validate_crm_workbook_integrity.py` | L6 | live | fixture | Phase 3 | Guards CRM integrity validator until freeze. |
| `tests/test_sales_truth_views.py` | L6 | live | fixture | Phase 2 | Guards truth views that may use workbook anchor precedence. |
| `tests/test_system_doctor_contract.py` | L6 | live | contract | Phase 2 | Guards L3 doctor contract. |
| `tests/test_sync_sales_workbook_anchor.py` | L6 | live | fixture | Phase 2 | Guards workbook anchor table sync. |
| `tests/test_rebuild_kaspi_identity_map_from_crm.py` | L6 | legacy | fixture | leave | Guards L5 CRM identity map rebuild. |
| `tests/test_repair_sales_fact_v2_lifecycle_residual.py` | L6 | legacy | fixture | leave | Guards sales_fact_v2 lifecycle repair. |
| `tests/test_google_ops_board_prewindow_health.py` | L6 | live | fixture/contract | Phase 2 | Guards L4 Google prewindow health. |
| `tests/test_build_line31_launch_preflight_packet.py` | L6 | live | fixture/contract | Phase 2 | Guards LINE31 preflight packet. |
| `config/business_automation_manifest.json` | L1 | live | contract | Phase 2 | Protected workbook and scheduler labels include `com.example.crm-db-sync`. |
| `config/com.example.single-truth-preflight.plist` | L3 | live | contract | Phase 2 | Sets `AB_CRM_WORKBOOK_PATH` to `config/anchors/SALES_KSP_CRM_LATEST.xlsx`. |
| `config/anchors/README.md` | L3 | live | contract | Phase 2 | Anchor path authority for strict validation. |

## Indirect Coupling Addendum

These files did not all appear in the literal 111-file `SALES_KSP_CRM` census, but they are coupled through `workbook`, `crm`, `anchor`, scheduler, launchd, or daily runbooks.

| file | lane | live/legacy | reads-or-writes workbook | phase to address | notes |
|---|---|---|---|---|---|
| `scripts/run_kaspi_import_scheduler.py` | L1 | live | indirect | Phase 2 | LaunchAgent target; runs `excel_ui/run_full_import.command`. |
| `scripts/run_google_ops_board_publish_scheduler.py` | L4 | live | indirect/contract | Phase 2 | Publish scheduler; workbook map sync only when env/profile allows. |
| `scripts/sync_google_ops_board.py` | L4 | live | none | keep | Source is `db/app.db`; publishes ops board. |
| `scripts/sync_google_ops_board_sizes_to_db.py` | L4 | live | none | keep | Writes Google `MY_SIZE` to DB `assigned_size`. |
| `scripts/run_google_ops_board_closeout.py` | L4 | live | none in current command path | keep | DB-first closeout wrapper. |
| `scripts/run_google_ops_board_closeout_scheduler.py` | L4 | live | none | keep | Scheduler wrapper for closeout. |
| `scripts/run_google_ops_board_closeout_watch_scheduler.py` | L4 | live | none | keep | Monitors board readiness; can autofill probable sizes. |
| `scripts/run_google_ops_board_prewindow_health_scheduler.py` | L4 | live | indirect/contract | keep | Health scheduler wrapper. |
| `scripts/run_google_ops_board_size_writeback_scheduler.py` | L4 | live | none | keep | Google size writeback scheduler. |
| `scripts/run_kaspi_shipped_truth_sync_scheduler.py` | L2 | live | none | keep | DB-only shipped truth sync: explicitly no Excel workbook writes. |
| `scripts/run_anchor_health_alert.py` | L3 | live | read via checker | Phase 2 | Sends/records anchor-health failures; depends on `check_anchor_health.py`. |
| `config/google_ops_board.yaml` | L4 | live | contract | keep | Defines `SalesRaw_Today.MY_SIZE -> fact_orders_kaspi.assigned_size`. |
| `config/com.example.anchor-health-warning.plist` | L3 | live | contract | Phase 2 | Runs anchor health warning path. |
| `config/com.example.google-ops-board-publish.plist` | L4 | live | none | keep | Google publish LaunchAgent config. |
| `config/com.example.google-ops-board-closeout-watch.plist` | L4 | live | none | keep | Closeout watch LaunchAgent config. |
| `config/com.example.google-ops-board-prewindow-health.plist` | L4 | live | indirect/contract | keep | Prewindow health LaunchAgent config. |
| `config/com.example.google-ops-board-size-writeback.plist` | L4 | live | none | keep | Size writeback LaunchAgent config. |
| `config/com.example.waybill-telegram-control.plist` | L4 | live | none | keep | Telegram/closeout controller config; uses Google Ops Board env. |
| `config/com.example.kaspi-waybill-deadline.plist` | L4 | live | none | keep | Deadline closeout controller config. |
| `docs/DAILY_SOP.md` | L6 | live | contract | Phase 2 | Mixed: current Google-board flow plus old CRM sections. Needs cleanup during Phase 2/3. |
| `docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md` | L6 | live | contract | keep | Current Google board source/writeback contract. |
| `docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md` | L6 | live | contract | keep | Current daily ops workflow contract. |

External LaunchAgents observed in `~/Library/LaunchAgents`:

| plist | lane | live/legacy | workbook coupling | phase to address | notes |
|---|---|---|---|---|---|
| `com.example.kaspi-import-v2.plist` | L1 | live | indirect write | Phase 2 | Runs `scripts/run_kaspi_import_scheduler.py`. |
| `com.example.crm-db-sync.plist` | L1 | live | read | Phase 2 | Runs `scripts/sync_crm_to_db.py`. |
| `com.example.single-truth-preflight.plist` | L3 | live | anchor | Phase 2 | Sets CRM workbook anchor env. |
| `com.example.anchor-health-warning.plist` | L3 | live | anchor | Phase 2 | Anchor health warning. |
| `com.example.google-ops-board-publish.plist` | L4 | live | none/indirect | keep | Board publish. |
| `com.example.google-ops-board-closeout-watch.plist` | L4 | live | none | keep | Board closeout watch. |
| `com.example.google-ops-board-size-writeback.plist` | L4 | live | none | keep | Board size writeback. |
| `com.example.google-ops-board-prewindow-health.plist` | L4 | live | indirect/contract | keep | Board health. |
| `com.example.waybill-telegram-control.plist` | L4 | live | none | keep | Telegram/closeout control. |
| `com.example.kaspi-waybill-deadline.plist` | L4 | live | none | keep | Deadline closeout control. |
| `com.example.kaspi-shipped-truth-sync.plist` | L2 | live | none | keep | DB-only shipped truth sync. |

## Current Lineage

### Current DB/API daily ops lineage

1. Kaspi API and ActiveOrders export populate `fact_orders_kaspi`.
   - Current schema: `fact_orders_kaspi(id, order_id, store_code, channel_code, kaspi_offer_name, sku_key, sku_id, my_size, quantity, unit_price_kzt, created_at, planned_shipment_date, actual_shipment_date, kaspi_status, internal_status, status_updated_at, waybill_url, waybill_number, waybill_downloaded, source, source_file, imported_at, updated_at, assigned_size, size_source, size_confidence, customer_height_cm, customer_weight_kg, ... line_identity_key, UNIQUE(order_id, store_code, line_identity_key, sku_id))`.
   - `scripts/enrich_kaspi_orders_from_activeorders.py` can enrich identity and parsed `my_size` from ActiveOrders/order text. It is not the owner/operator size writeback path.
2. `scripts/sync_google_ops_board.py` loads DB rows from `fact_orders_kaspi` for the target shipment window (`scripts/sync_google_ops_board.py:319-340`).
3. Google board rows use `assigned_size` first, then `my_size`:
   - `scripts/sync_google_ops_board.py:573` sets `size_value = assigned_size or my_size`.
   - `SalesRaw_Today.MY_SIZE` is the visible editable size cell.
4. Operator-entered Google board `MY_SIZE` writes back to DB:
   - `config/google_ops_board.yaml:219-228`: `SalesRaw_Today`, key `_db_row_id`, source `MY_SIZE`, target `fact_orders_kaspi.id`, target column `assigned_size`, target source column `size_source`, source value `GOOGLE_OPS_BOARD`.
   - `scripts/sync_google_ops_board_sizes_to_db.py:172-189` updates `assigned_size`, `size_source`, and `updated_at`.
5. Automated closeout reads DB sizes:
   - `scripts/run_google_ops_board_closeout.py:925-951` calls `ship_orders_api.py --selection-source db`.
   - `scripts/run_google_ops_board_closeout.py:962-983` calls `download_waybills_api.py` without `--fallback-crm`.
   - `scripts/run_google_ops_board_closeout.py:993-1018` calls `build_daily_waybills.py --db-path ...`.

### Legacy workbook lineage

Current live legacy flow:

`ActiveOrders.xlsx -> import_orders_to_crm.py -> excel_ui/SALES_KSP_CRM_V3.xlsx sheet SALES_KSP_CRM_1 table tb_SalesRaw -> sync_crm_to_db.py/core.ingest.sales_ingest -> sales_fact_v2 + fact_sales + stock_ledger + fact_sales_daily`

Workbook write semantics:
- `scripts/import_orders_to_crm.py:102-105` defines sheet `SALES_KSP_CRM_1`, table `tb_SalesRaw`, and template defaults.
- `scripts/import_orders_to_crm.py:347-402` fails fast if the CRM workbook is open in Excel.
- `scripts/import_orders_to_crm.py:743-773` maps raw Kaspi columns Y-AZ; `MY_SIZE` is column AU.
- `scripts/import_orders_to_crm.py:775-777` marks `MY_SIZE` as human-owned.
- `scripts/import_orders_to_crm.py:1567-1579` builds append dedupe key as `order_id|planned_date|article|offer|quantity`.
- `scripts/import_orders_to_crm.py:4991-5163` appends rows by xlwings, writes date and fixed values, clears `MY_SIZE` for newly appended rows, and saves the workbook.
- `excel_ui/run_full_import.command:407-460` validates CRM workbook integrity and Excel session before Step 2.
- `excel_ui/run_full_import.command:481-535` runs the guarded CRM writer with `CRM_IMPORT_TIMEOUT_SEC` default 600 seconds.
- `excel_ui/run_full_import.command:805-828` runs final success gate through `evaluate_import_run_result.py`.
- `excel_ui/run_full_import.command:832-848` still publishes Google Ops Board from DB truth even when CRM Step 2 is red.

CRM -> DB sync semantics:
- `scripts/sync_crm_to_db.py:31-32` defaults to `excel_ui/SALES_KSP_CRM_V3.xlsx` and sheet `SALES_KSP_CRM_1`.
- Args:
  - `--dry-run`: do not write to DB.
  - `--file`, `--sheet`: source workbook/sheet.
  - `--no-ledger`: skip `stock_ledger` events.
  - `--no-reconcile`: skip deleting stale `sales_fact_v2` rows in the CRM date span.
  - `--skip-fact-sales`: skip `fact_sales` update.
  - `--skip-aggregates`: skip `fact_sales_daily` aggregate rebuild.
- Reconcile:
  - `scripts/sync_crm_to_db.py:77-143` parses CRM records, derives min/max `order_date`, builds CRM keys `(order_id, store_code, kaspi_offer_name, sku_key, my_size)` after identity resolution, and deletes `sales_fact_v2` rows in that date span whose key is absent from the CRM workbook.
- `sales_fact_v2` ingest:
  - `core/ingest/sales_ingest.py:1-14` documents the intended dedupe key `(order_id, store_code, kaspi_offer_name, sku_key, my_size)`.
  - `core/ingest/sales_ingest.py:330-370` parses workbook columns, including `OrderID`, `Date`, `KASPI_OFFER_NAME`, `SKU_ID`, `SKU_key`, `MY_SIZE`, quantity, sell price, store, return flag, and delivery fee fallbacks.
  - `core/ingest/sales_ingest.py:625-657` ingests to `sales_fact_v2` and `stock_ledger`.
  - `core/ingest/sales_ingest.py:680-693` skips unmapped rows if `sku_id`, `sku_key`, or `my_size` cannot be resolved.
  - `core/ingest/sales_ingest.py:695-712` dedupes first by `(order_id, store_code, kaspi_offer_name, sku_key, my_size)`, then by existing DB unique key `(order_id, sku_id, store_code, kaspi_offer_name)`.
  - `core/ingest/sales_ingest.py:714-742` updates an existing sale to `RETURNED` only when return flag changes to 1 and queues a return ledger event.
  - `core/ingest/sales_ingest.py:747-815` inserts new rows with status `DELIVERED` or `RETURNED` and queues SALE/RETURN ledger events.
  - `core/ingest/sales_ingest.py:823-857` writes ledger events using `inventory_pool_store_code()`, not the row store code, and logs audit for inserted batches.
- `fact_sales` ingest:
  - `core/ingest/sales_ingest.py:860-938` parses CRM into `fact_sales`, builds existing maps in the workbook date span, and uses the same logical dedupe plus DB unique fallback.
  - `core/ingest/sales_ingest.py:1033-1074` skips duplicate keys and resolves existing rows.
  - `core/ingest/sales_ingest.py:1098-1177` updates or inserts economics fields (`delivery_fee`, `net_rev_unit`, `line_net_rev`, `cogs_unit`, `cogs_line`, `profit_unit`, `profit_line`, `channel_code`).

### Where `my_size` and `size_source` come from today

For current daily ops, the owner/operator size selected on Google Ops Board lands in:

`fact_orders_kaspi.assigned_size`, `fact_orders_kaspi.size_source='GOOGLE_OPS_BOARD'`

It does not write `fact_orders_kaspi.my_size`.

Evidence:
- `config/google_ops_board.yaml:219-228` defines the target column as `assigned_size` and source value as `GOOGLE_OPS_BOARD`.
- `scripts/sync_google_ops_board_sizes_to_db.py:180-184` runs `UPDATE fact_orders_kaspi SET assigned_size = ?, size_source = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?`.
- `scripts/sync_google_ops_board.py:573` renders the board size as `assigned_size` first, then legacy `my_size`.

Legacy paths still write or derive size fields:
- `scripts/sync_crm_sizes_to_db.py:3-9` writes CRM manual sizes to `assigned_size`, `size_source=CRM_MANUAL`, `size_confidence=HIGH`.
- `scripts/sync_crm_sizes_to_db.py:280-288` updates those columns by `order_id`.
- `scripts/reconcile_kaspi_archive_orders.py:594-698` creates/uses `kaspi_orders_y` and can fill `my_size`, `assigned_size`, `size_source`, and `size_confidence` from archive/CRM/inferred sizes.
- `scripts/backfill_kaspi_order_sizes.py` uses `kaspi_orders_y` to backfill missing historical order sizes; it is out of scope for the live direct feeder.

### What `kaspi_orders_y` is

`kaspi_orders_y` is an archive reconciliation/backfill table created by `scripts/reconcile_kaspi_archive_orders.py`, not the current daily API feeder. Schema observed read-only:

`kaspi_orders_y(store_code, order_id, kaspi_offer_name, order_date, quantity, unit_price_kzt, kaspi_status, status_updated_at, planned_shipment_date, sku_key, my_size, size_source, size_confidence, pb_size_share, source_file, sku_id)`

It is built from archive/CRM/inferred size logic and then used for historical reconciliation and size backfill. It should remain out of scope for Phase 1 direct feeding except as historical parity background or a one-time legacy backfill source.

## L2 Verdict: Waybill/Shipping Runtime Workbook Dependency

Verdict: current automated daily closeout is DB/API-driven, not workbook-driven. Legacy/manual waybill commands still read the workbook and can still write DB sizes from it.

Evidence for current automated closeout:
- `scripts/run_google_ops_board_closeout.py:819-850` performs final Google size writeback.
- `scripts/run_google_ops_board_closeout.py:925-951` calls `ship_orders_api.py --selection-source db --db-path ...`.
- `scripts/ship_orders_api.py:489-503` documents `read_db_orders` as the automated closeout path using DB size truth `(assigned_size first, then my_size)` and not depending on the CRM workbook.
- `scripts/ship_orders_api.py:1571-1582` executes the DB path when `selection_source == "db"`.
- `scripts/run_google_ops_board_closeout.py:962-983` calls `download_waybills_api.py` without `--fallback-crm`.
- `scripts/download_waybills_api.py:1121-1163` uses Kaspi API planned date as primary selection.
- `scripts/download_waybills_api.py:1164-1187` only reads CRM when `fallback_crm` is true.
- `scripts/run_google_ops_board_closeout.py:993-1018` calls `build_daily_waybills.py --db-path ...`.
- `scripts/build_daily_waybills.py:2445-2564` uses API selection/cache and DB orders first; it calls `enrich_orders_with_crm(... crm_df=None)`, which returns DB orders without reading the workbook.
- `scripts/build_daily_waybills.py:2565-2578` only loads CRM if no DB/API orders were selected.

Evidence for remaining legacy/manual dependency:
- `excel_ui/run_merged_build_waybills.command:252-255` runs `sync_crm_sizes_to_db.py --upsert-missing`, copying CRM manual sizes to DB.
- `excel_ui/run_merged_build_waybills.command:358` runs `download_waybills_api.py --fallback-crm`.
- `scripts/ship_orders_api.py:1443-1448` still defaults `--selection-source` to `crm`, so any caller omitting the explicit DB flag reads the workbook.
- `scripts/download_waybills_api.py:1438-1440` exposes `--fallback-crm`.
- `scripts/build_daily_waybills.py:511-520` defines `load_crm_dataframe`; `scripts/build_daily_waybills.py:731-748` defines the CRM reader.
- `scripts/update_order_statuses.py:1-32` is explicitly deprecated but still reads/writes CRM statuses if run.

Action: Phase 2 should make all live/scheduled closeout commands fail closed if they would implicitly use CRM. Phase 3 can remove the legacy command files after owner signoff and a frozen workbook backup.

## Gates/Tests That Go Red If Workbook Freezes Today

If `SALES_KSP_CRM_V3.xlsx` is frozen without Phase 1/2 replacement, these required or active gates are expected to go red:

1. `excel_ui/run_full_import.command`
   - CRM integrity preflight, Excel preflight, Step 2 writer, fast existing-CRM gate, and final success gate remain tied to CRM.
   - Freeze/staleness will surface as `miss_crm`, `stale_crm`, seller-fee misses, append failure, or strict success gate failure.
2. `scripts/evaluate_import_run_result.py`
   - Reads ActiveOrders and CRM IDs; fails on `step2_rc != 0`, snapshot mismatch, `miss_crm`, `stale_crm`, or `miss_seller_fee`.
3. `scripts/report_import_status.py`
   - Reads API, CRM, DB, seller-fee coverage; a frozen CRM will report API-vs-CRM drift.
4. `scripts/sync_crm_to_db.py`
   - Reads frozen workbook into `sales_fact_v2` and `fact_sales`; no new rows flow to sales facts.
5. `scripts/check_anchor_health.py`
   - Enforces CRM anchor symlink, mtime max age, content lag, and future content limits.
6. `scripts/run_strict_daily_preflight.py`
   - Requires `AB_CRM_WORKBOOK_PATH`; fails stale workbook age checks before running downstream validation.
7. `scripts/validate_params.py --strict` when `AB_CRM_WORKBOOK_PATH` is set.
   - Runs `validate_sales_vs_workbook_anchor(... days=14, min_overlap_days=7, max_lag_days=...)`.
8. `scripts/system_doctor.py`
   - Strict owner-truth doctor resolves required CRM workbook anchor.
9. `scripts/validate_sales_against_workbook.py`, `scripts/validate_sales_truth_vs_crm_north_star.py`, `scripts/validate_webui_archive_vs_crm_band.py`, `scripts/reconcile_sales_sources.py`, `scripts/sync_sales_sources_to_db.py`.
   - These are CRM/workbook truth or source-comparison gates.
10. `scripts/validate_shipped_truth_crm_waybill.py`.
   - Shipped truth validator compares API vs CRM vs waybill; needs DB/API re-anchor.
11. Tests guarding those contracts:
   - `tests/test_run_full_import_command_step2.py`
   - `tests/test_evaluate_import_run_result.py`
   - `tests/test_import_orders_to_crm.py`
   - `tests/test_validate_crm_workbook_integrity.py`
   - `tests/test_check_anchor_health.py`
   - `tests/test_validate_sales_vs_workbook_anchor.py`
   - `tests/test_validate_sales_against_workbook_freshness.py`
   - `tests/test_sales_workbook_anchor_parser.py`
   - `tests/test_sync_sales_workbook_anchor.py`
   - `tests/test_sales_truth_workbook_anchor.py`
   - `tests/test_published_sales_truth_matches_anchor_window.py`
   - `tests/test_classify_workbook_anchor_overages.py`
   - `tests/test_validate_shipped_truth_crm_waybill.py`
   - `tests/test_single_truth_ops_scheduler_contract.py`
   - `tests/test_ops_docs_anchor_contract.py`
   - `tests/test_system_doctor_contract.py`

## Phase 1 Spec: Shadow Direct Feeder + Parity Validator

Goal: build a shadow direct feeder from `fact_orders_kaspi` to `sales_fact_v2` that exactly preserves `sync_crm_to_db.py` semantics where those semantics still matter, without touching the existing CRM lane.

### New direct feeder entrypoint

Proposed script:

`scripts/feed_fact_orders_kaspi_to_sales_fact_v2.py`

Default mode:
- dry-run / shadow only.
- no deletes.
- no ledger writes unless explicitly enabled later.
- write report only under `exports/decommission/crm_excel_shadow/YYYY-MM-DD/`.
- no workbook reads.
- no changes to `excel_ui/`, Google Sheets, launchd, or Telegram.

Inputs:
- DB path, default `db/app.db`.
- Date window: `--from-date`, `--to-date`, default recent shipping/order window.
- Optional target date / lookback days for daily runs.
- Optional `--source-run-id`.
- Optional `--shadow-table` only if Phase 1 chooses DB sidecar mode. Safer initial version should write JSON/CSV reports only.

Source rows:
- `fact_orders_kaspi`.
- Required source columns:
  - identity: `order_id`, `store_code`, `line_identity_key`, `kaspi_offer_name`, `sku_key`, `sku_id`
  - dates: `created_at`, `planned_shipment_date`, `actual_shipment_date`, `courier_transmission_date`, `status_updated_at`
  - size: `assigned_size`, `my_size`, `size_source`, `size_confidence`
  - quantity/price: `quantity`, `unit_price_kzt`, `delivery_cost_for_seller`, `delivery_cost`
  - status: `kaspi_status`, `internal_status`, `returned_to_warehouse`
  - source metadata: `source`, `source_file`, `imported_at`, `updated_at`
- Join `dim_sku` for `product_type`, `weight_kg`, `cogs_kzt`, and current economics defaults.
- Join `dim_sku_size` by `(sku_key, final_size)` if `sku_id` is absent or suspect.

Final size rule:
- `final_my_size = normalize_size(assigned_size, product_type)` if present.
- Else `normalize_size(my_size, product_type)` if present.
- If both are blank, row is not eligible for `sales_fact_v2`; report as `missing_size`.
- Preserve `size_source` in report. Do not silently convert Google board size into legacy CRM manual truth.

Field mapping to `sales_fact_v2`:

| `sales_fact_v2` column | direct source |
|---|---|
| `order_id` | `fact_orders_kaspi.order_id` |
| `order_date` | Phase 1 default: CRM parity mode uses same basis detected by validator; recommended canonical future basis is `created_at` date or first available sale/completion date, not planned shipment. Report both `source_order_date` and `planned_shipment_date`. |
| `sku_key` | `fact_orders_kaspi.sku_key` or identity resolver from offer/name |
| `sku_id` | `fact_orders_kaspi.sku_id` or `dim_sku_size(sku_key, final_my_size)` |
| `my_size` | `final_my_size` from `assigned_size` first, then `my_size` |
| `kaspi_offer_name` | `fact_orders_kaspi.kaspi_offer_name` |
| `store_code` | `fact_orders_kaspi.store_code` |
| `quantity` | `fact_orders_kaspi.quantity`, default 1 only if null and source row is otherwise valid |
| `sell_price_kzt` | `fact_orders_kaspi.unit_price_kzt` |
| `delivery_fee` | seller delivery fee when present; else current `calc_delivery_fee` fallback matching `ingest_sales_to_fact_sales` |
| `net_rev` | preserve current CRM parser semantics if `Total_net_rev` has a DB equivalent; otherwise compute with existing calc helper and mark computed |
| `profit` | compute using cogs/economics only after parity design confirms current `sales_fact_v2` expectations |
| `status` | `RETURNED` if API/internal/return fields say returned, `CANCELLED` if terminal cancelled and current sales rules want cancellation rows, else `DELIVERED` for completed shipped/sold rows |
| `return_flag` | 1 for returned, else 0 |
| `return_date` | return/status date when available; fallback to current date only if matching old behavior is explicitly selected |
| `source_file` | `fact_orders_kaspi` plus run id, not workbook name |

Dedupe parity:
- Logical key must match CRM lineage: `(order_id, store_code, kaspi_offer_name, sku_key, my_size)`.
- DB unique fallback must match current table constraint: `(order_id, sku_id, store_code, kaspi_offer_name)`.
- The direct feeder report must expose both keys for every row.
- Do not collapse lines only by `order_id`; multi-line and multi-size orders must remain line-grain.

Idempotency:
- Shadow mode: report-only, deterministic sorted output.
- Apply mode later:
  - Use transaction.
  - Upsert by existing logical key/fallback unique.
  - Never delete existing `sales_fact_v2` rows until a separate reconciliation mode is explicitly enabled after parity is green.
  - Add idempotency key: `direct_fact_orders_kaspi:{order_id}:{store_code}:{kaspi_offer_name}:{sku_key}:{my_size}` to any ledger/event sidecar if ledger is enabled.

Append-only guarantee:
- Phase 1 must be append/update-only in shadow reports; no production DB mutations.
- First apply candidate in Phase 2 should be append-only for rows missing from `sales_fact_v2`; no deletes/reconciles until owner separately accepts a reconcile design.

Unmapped-offer handling:
- Match `core/ingest/sales_ingest.py:680-693`: if `sku_id`, `sku_key`, or `my_size` cannot be resolved, skip row and report unmapped with source reason.
- Produce CSV sidecar `unmapped_rows.csv` with no PII and no customer names/phones.

Returns/status handling:
- Preserve current CRM behavior for parity:
  - New returned historical rows generate sale+return semantics.
  - Existing row changing from return flag 0 to 1 is updated to `RETURNED`.
- Direct feeder should prefer API/status dates over `date.today()` once parity mode is turned off, but Phase 1 parity report must show whether using current date would change output.

### Parity validator

Proposed script:

`scripts/validate_direct_sales_fact_parity.py`

Inputs:
- Current workbook path for baseline only during Phase 1.
- Direct feeder shadow output.
- Existing `sales_fact_v2` and optionally `fact_sales`.
- Date window.

Output path:

`exports/decommission/crm_excel_shadow/{YYYY-MM-DD}/{run_id}/`

Artifacts:
- `direct_feeder_shadow_rows.csv`
- `crm_baseline_rows.csv`
- `row_diff.csv`
- `summary.json`
- `summary.md`
- `unmapped_rows.csv`
- `date_basis_diff.csv`

Diff keys:
- Primary: `(order_id, store_code, kaspi_offer_name, sku_key, my_size)`.
- Secondary/fallback: `(order_id, store_code, kaspi_offer_name, sku_id)`.
- Never compare by order_id alone.

Tolerance rules:
- Row count tolerance: 0 for keys in active cutover window.
- Quantity tolerance: 0.
- Price tolerance: 0 unless existing CRM source is blank and DB source is computed; then report as `computed_price_gap`, not green.
- Date tolerance:
  - Known CRM date drift around 2026-07-04/2026-07-05 must be classified in `date_basis_diff.csv`.
  - A row can be `GREEN_WITH_DATE_BASIS_DIFF` only if all identity, quantity, price, status, and size fields match and date difference is exactly explained by configured basis (`Date` vs planned shipment/created/completion date).
- Seller delivery fee:
  - Missing CRM seller fee should not block direct feeder if DB/API has seller fee.
  - If both are missing, report `missing_seller_fee`.
- Returns:
  - Return status/flag mismatches are RED unless the row is in an explicit volatility window and the API status timestamp is newer than CRM.

GREEN criteria:
- All eligible CRM baseline rows have a direct row by primary or allowed fallback key.
- No direct row that would create a duplicate under current `sales_fact_v2` unique key.
- No unresolved size/source regressions for rows with Google board `assigned_size`.
- No row-level differences except explicitly classified date-basis differences.
- All reports are written and contain nonzero source counts for non-empty windows.

RED criteria:
- Any missing key, duplicate key, quantity/price/status/size mismatch, unmapped row not already unmapped in CRM path, or unclassified date drift.

### Shadow-mode wiring

Do not touch `excel_ui/run_full_import.command` in Phase 1.

Add a separate no-side-effect scheduler/manual command only after code exists:

```bash
python3 scripts/feed_fact_orders_kaspi_to_sales_fact_v2.py \
  --db db/app.db \
  --from-date YYYY-MM-DD \
  --to-date YYYY-MM-DD \
  --shadow-out exports/decommission/crm_excel_shadow/YYYY-MM-DD/RUN_ID/direct_feeder_shadow_rows.csv

python3 scripts/validate_direct_sales_fact_parity.py \
  --db db/app.db \
  --crm-file excel_ui/SALES_KSP_CRM_V3.xlsx \
  --direct-shadow exports/decommission/crm_excel_shadow/YYYY-MM-DD/RUN_ID/direct_feeder_shadow_rows.csv \
  --from-date YYYY-MM-DD \
  --to-date YYYY-MM-DD \
  --out-dir exports/decommission/crm_excel_shadow/YYYY-MM-DD/RUN_ID
```

Phase 1 must not:
- disable CRM import,
- change LaunchAgents,
- modify `sales_fact_v2`,
- write workbook,
- write Google Sheet,
- send Telegram,
- call Kaspi write APIs.

## Phase 2 Cutover Design

### Flag/config design

Default must be OFF.

Recommended config file:

`config/owner_decisions/retire_crm_excel_pipeline_2026_07.json`

Recommended environment gate:

`ENABLE_DIRECT_SALES_FACT_FEEDER=1`

Recommended Python helper:

`core/owner_decisions/retire_crm_excel_pipeline.py`

Cutover mode matrix:

| config/env state | behavior |
|---|---|
| config absent | old CRM lane stays live; direct feeder apply forbidden |
| config present but `enabled=false` | old CRM lane stays live; shadow direct feeder allowed |
| `enabled=true`, env gate absent | fail closed before any apply |
| `enabled=true`, env gate present | direct feeder apply allowed; CRM workbook writer disabled or skipped by guarded wrapper |
| rollback | flip config/env off; return to old CRM lane |

Draft JSON body:

```json
{
  "decision_id": "retire_crm_excel_pipeline_2026_07",
  "status": "DRAFT",
  "enabled": false,
  "owner_approved_at": null,
  "owner_approval_evidence": null,
  "scope": {
    "workbook": "excel_ui/SALES_KSP_CRM_V3.xlsx",
    "retire_as_live_feeder": true,
    "freeze_as_read_only_archive": true,
    "target_lineage": "fact_orders_kaspi -> direct feeder -> sales_fact_v2",
    "out_of_scope": [
      "kaspi_orders_y historical archive backfills",
      "physical workbook deletion before Phase 3",
      "Google Ops Board decommission"
    ]
  },
  "required_green_evidence": {
    "direct_feeder_shadow_days": 7,
    "parity_validator_status": "GREEN",
    "date_basis_diffs_classified": true,
    "unmapped_rows_regression_count": 0,
    "duplicate_key_regression_count": 0,
    "waybill_closeout_db_first_verified": true,
    "rollback_tested_by_flag_flip": true
  },
  "cutover_flags": {
    "env_gate": "ENABLE_DIRECT_SALES_FACT_FEEDER",
    "env_gate_required_value": "1",
    "default_enabled": false
  },
  "rollback": {
    "method": "set enabled=false and unset ENABLE_DIRECT_SALES_FACT_FEEDER",
    "expected_effect": "old CRM import/sync lane remains available until Phase 3 removal"
  },
  "prohibited_without_new_owner_approval": [
    "delete workbook",
    "edit launchd plists",
    "disable Google Ops Board",
    "send Telegram",
    "write Kaspi merchant state",
    "run destructive DB reconcile"
  ]
}
```

### Pytest guard sketch

Pattern reference: `tests/test_forbidden_kaspi_offer_cards.py`.

New test:

`tests/test_retire_crm_excel_pipeline_owner_decision.py`

Guard checks:
- Decision JSON exists before any code path can default to direct feeder apply.
- `enabled` defaults false.
- If `enabled=true`, required fields are present:
  - `owner_approved_at`
  - `owner_approval_evidence`
  - `required_green_evidence.parity_validator_status == "GREEN"`
  - `required_green_evidence.rollback_tested_by_flag_flip == true`
- Direct feeder apply function refuses to run unless:
  - decision file is enabled,
  - `ENABLE_DIRECT_SALES_FACT_FEEDER=1`,
  - parity report path exists and is GREEN for configured window.
- CRM writer cannot be physically disabled unless the same decision file is enabled.

Test names:
- `test_retire_crm_excel_decision_defaults_disabled`
- `test_direct_feeder_apply_requires_owner_decision_and_env_gate`
- `test_enabled_decision_requires_green_parity_and_rollback_evidence`
- `test_crm_writer_disable_requires_enabled_decision`
- `test_rollback_is_flag_flip_only_before_phase3_removal`

### Phase 2 wiring

Do this after Phase 1 shadow parity is GREEN:

1. Add direct feeder code and tests.
2. Add decision JSON with `enabled=false`.
3. Add guarded wrapper logic so scheduled sales fact update chooses:
   - old `sync_crm_to_db.py` when flag OFF,
   - direct feeder when flag ON and env gate set.
4. Update strict gates:
   - `validate_params.py --strict` should accept DB/API sales anchor when the decision is enabled.
   - `check_anchor_health.py` should downgrade CRM anchor to frozen-archive check after decision enabled.
   - `system_doctor.py` should use DB/API evidence instead of requiring CRM workbook anchor in direct-feeder mode.
5. Keep workbook file present, readable, and backed up.
6. Run rollback drill:
   - enable direct feeder on scratch/copy or shadow,
   - flip OFF,
   - prove old CRM path remains callable until Phase 3.

Rollback before Phase 3:
- set decision `enabled=false`;
- unset `ENABLE_DIRECT_SALES_FACT_FEEDER`;
- scheduled old path remains in place.

## Phase 3 Removal And Re-Anchoring

Phase 3 starts only after:
- owner decision is enabled and approved,
- Phase 2 direct feeder has been green for agreed window,
- rollback by flag flip has been tested,
- final workbook backup/read-only archive is created.

### Freeze procedure

1. Stop scheduled CRM writer only after owner approval.
2. Create final workbook backup outside git:
   - `excel_ui/backups/CRM_final_archive_YYYYMMDD_HHMMSS.xlsx`
   - record SHA-256 and file size in a decommission evidence report.
3. Set workbook read-only at file-system level if owner wants a frozen local artifact.
4. Keep `excel_ui/SALES_KSP_CRM_V3.xlsx` available as archive through at least one full post-cutover reconciliation window.
5. Remove or repoint `config/anchors/SALES_KSP_CRM_LATEST.xlsx` only after validators no longer require it.

### Removal list

Remove or archive after Phase 3 approval:
- `excel_ui/run_full_import.command` CRM Step 2 wiring, or replace with DB/API-only import wrapper.
- `scripts/import_orders_to_crm.py` live scheduler use. Keep archived copy only if needed for forensic replay.
- `scripts/sync_crm_to_db.py` scheduled use. Keep read-only utility only if needed for historical workbook replay.
- `scripts/evaluate_import_run_result.py` CRM snapshot gate, replaced by API/DB/direct-feeder parity gate.
- `scripts/report_import_status.py` CRM columns/gates, replaced by API/DB report.
- `scripts/validate_crm_workbook_integrity.py` required gate, retained only as archive integrity checker.
- `scripts/check_anchor_health.py` CRM anchor requirement, re-anchored to DB/API evidence plus frozen archive SHA.
- `scripts/run_strict_daily_preflight.py` CRM workbook requirement.
- `scripts/validate_params.py` `sales_workbook_anchor` strict gate.
- `scripts/system_doctor.py` required CRM anchor.
- `scripts/validate_sales_against_workbook.py`, `scripts/validate_sales_truth_vs_crm_north_star.py`, `scripts/validate_webui_archive_vs_crm_band.py`, `scripts/sync_sales_sources_to_db.py`, `scripts/reconcile_sales_sources.py`: replace with DB/API/direct-feeder validators or move to archive-only.
- `scripts/validate_shipped_truth_crm_waybill.py`: replace CRM expected set with `fact_orders_kaspi`/Kaspi API/waybill evidence.
- `scripts/sync_crm_sizes_to_db.py`, `scripts/update_order_statuses.py`, and double-click waybill commands that use CRM fallbacks.
- `scripts/sync_to_gdrive.py` workbook sync if no longer needed.
- `config/business_automation_manifest.json` protected workbook/scheduler entries.
- `config/com.example.single-truth-preflight.plist`, `config/com.example.anchor-health-warning.plist`, and installed LaunchAgents `com.example.single-truth-preflight`, `com.example.anchor-health-warning`, `com.example.crm-db-sync`, `com.example.kaspi-import-v2` as applicable.

Do not remove:
- `fact_orders_kaspi`
- Google Ops Board scripts/config
- `kaspi_orders_y` historical archive/backfill table and scripts, unless a separate archive-decommission decision exists
- frozen workbook archive backup

### Validators to re-anchor

| current validator/gate | current anchor | replacement anchor |
|---|---|---|
| `evaluate_import_run_result.py` | ActiveOrders vs CRM workbook | ActiveOrders/Kaspi API vs `fact_orders_kaspi` and direct-feeder shadow/apply report |
| `report_import_status.py` | API/CRM/DB table | API/DB/direct-feeder table |
| `check_anchor_health.py` | CRM symlink mtime/content lag | DB freshness, direct-feeder parity freshness, frozen archive SHA/mtime only |
| `validate_params.py --strict` | `sales_workbook_anchor` | `sales_direct_feeder_anchor` with DB/API coverage |
| `run_strict_daily_preflight.py` | required `AB_CRM_WORKBOOK_PATH` | required DB/API/direct-feeder report path |
| `system_doctor.py` | required CRM anchor | DB/API/direct-feeder and frozen archive evidence |
| `validate_sales_against_workbook.py` | workbook totals | direct-feeder vs fact_orders/sales_fact totals |
| `validate_sales_truth_vs_crm_north_star.py` | CRM north-star workbook | DB/API north-star with explicit date-basis policy |
| `validate_shipped_truth_crm_waybill.py` | API vs CRM vs waybill | API vs `fact_orders_kaspi` vs waybill |
| LINE31 readiness/advisory repo gate | broad strict repo gate may include CRM anchor | preserve LINE31 launch-blocking separation; do not let CRM retirement create fake LINE31 blockers |

## Risks

Top 5:

1. Live scheduled CRM writer still mutates the workbook.
   - `com.example.kaspi-import-v2` -> `run_kaspi_import_scheduler.py` -> `run_full_import.command` still opens Excel and writes workbook rows. A freeze without Phase 2 flagging will produce red import logs and stale sales facts.
2. `sales_fact_v2` currently depends on `sync_crm_to_db.py`.
   - If the workbook freezes before direct feeder apply is enabled, `sales_fact_v2`, `fact_sales`, `fact_sales_daily`, and any downstream profit/cashflow views that still read those tables can stale out.
3. Legacy waybill shortcuts can silently re-enter the workbook.
   - The automated Google closeout is DB/API-first, but double-click commands still run CRM size sync and `--fallback-crm`. Phase 2 must fail closed on accidental manual fallback.
4. Strict/green-path gates overlap with workbook anchors.
   - The green-path catalog has 71 gates in `docs/plan/green_path_2026-06/green_gates.csv` (72 CSV lines including header). Relevant overlaps include `G-SCHED-04` nightly strict preflight, `G-COGS-04` sales-truth chain freshness, `G-QUAR-01` workbook-anchor quarantine rows, `G-STOCK-03` anchor health in stock snapshot gates, `G-REPO-01` repo hygiene, and `G-ACC-01` final acceptance.
5. LINE31/live-state context is already YELLOW.
   - Current LINE31 non-creative matrix (`exports/validation/line31_current_noncreative_gate_refresh_current/CURRENT_NONCREATIVE_GATE_MATRIX.md`) is YELLOW with LINE31 launch-blocking retained blockers `compact_child_cogs_integrity`, `profit_publication_integrity`, and `generic_po_dashboard_stock_freshness_validator`; `strict_repo_gate` is advisory. Do not re-label CRM decommission fallout as a LINE31 launch blocker unless the current LINE31 matrix says so.

Additional risk notes:
- `exports/validation/g_test_fix_20260702/RETURN.md` records a 12-failure queue in `tests/test_import_orders_to_crm.py` caused by sandbox/log path `PermissionError`, not a proof that CRM import semantics are healthy.
- `config/owner_decisions/offer_creation_rules_2026_07_03.json` includes a recheck after the 2026-07-10 physical count; do not let CRM decommission erase count-day prep or inventory/offer safeguards.
- Telegram send and waybill printing depend on DB-first closeout artifacts and final board writeback. Phase 1 must not touch those live surfaces.
- `sales_fact_v2` table unique constraint is `(order_id, sku_id, store_code, kaspi_offer_name)`, while CRM logic uses `(order_id, store_code, kaspi_offer_name, sku_key, my_size)`. Direct feeder must report both or it can create false duplicates/false parity.
- Date basis drift is real. The parity validator must classify date-basis differences rather than silently forcing CRM `Date` semantics into DB/API truth.

## Owner Open Questions

1. Should Phase 2 disable only the scheduled CRM writer first, or also disable the scheduled `crm-db-sync` once direct feeder shadow is green?
2. What is the owner-approved shadow window: 3 days, 7 days, or a full rolling 14-day Kaspi sync window?
3. Should frozen workbook archive remain at `excel_ui/SALES_KSP_CRM_V3.xlsx` read-only, or should that path become a symlink/copy to an archive folder?
4. Should Phase 2 preserve `sales_fact_v2` ledger event behavior exactly, including `date.today()` for newly detected returns, or use API/status dates with a documented behavior change?
5. Are legacy double-click waybill commands still used by anyone, or can Phase 2 make them exit with a clear message that Google Ops Board closeout is the only supported path?
6. Should strict anchor gates use direct-feeder reports, DB freshness, or both as the new required proof?
7. Is `kaspi_orders_y` still needed for any planned historical reconciliation after Phase 3, or can it remain purely archived/inert?

## Phase 0 Completion Checklist

- Literal `SALES_KSP_CRM` source/config/test census regenerated.
- Indirect scheduler, launchd, and runbook couplings swept.
- Every actionable 111-file literal hit classified into exactly one lane.
- L2 workbook-dependency verdict answered with code evidence.
- Current lineage documented down to table/column names and CRM sync semantics.
- `kaspi_orders_y` identified and scoped out of the live direct feeder.
- Phase 1 direct feeder and parity validator design provided.
- Phase 2 owner-decision flag, JSON draft, pytest guard sketch, and rollback described.
- Phase 3 removal/re-anchor/freeze plan described.
- Existing files, DB, launchd, git state, and `.claude` state were not modified by this Phase 0 task.

Gate: GREEN
