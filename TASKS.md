# Task Queue — Project 3

**Format:** `[STATUS] TASK-XXX: Title`
**Statuses:** `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`

---

## Phase 1: Schema & Bootstrap ✅

- [DONE] TASK-001: Create folder structure and schema.sql
- [DONE] TASK-002: Create core/db.py helper module
- [DONE] TASK-003: Create bootstrap_db.py to seed dimensions
- [DONE] TASK-004: Create test_schema.py verification
- [DONE] TASK-005: Create config YAML files

---

## Phase 2: Ingestion Pipeline ✅

- [DONE] TASK-006: Create `core/parsers/kaspi_parser.py` (Completed: 2025-12-06)
  - Parse ActiveOrders Excel format
  - Map Russian columns → DB columns
  - Extract sku_key, sku_id from Kaspi article
  - Input: ActiveOrders_*.xlsx
  - Output: List of dicts ready for DB insert

- [DONE] TASK-007: Create `scripts/ingest_active_orders.py` (Completed: 2025-12-06)
  - CLI: `python scripts/ingest_active_orders.py data_raw/ActiveOrders_2025-12-06.xlsx`
  - Idempotent: UPSERT on (order_id, sku_id, store_code)
  - Logs ingested count, skipped duplicates

- [DONE] TASK-008: Create `scripts/import_legacy_sales.py` (Completed: 2025-12-06)
  - Transforms fact_sales_raw → fact_sales with calculated economics
  - 11,567 records processed with COGS, NetRev, Profit
  - Idempotent: UPSERT on (order_id, sku_id, store_code)

- [DONE] TASK-009: Create `core/calc/economics.py` (Completed: 2025-12-06)
  - Functions: `calc_delivery_fee()`, `calc_net_rev()`, `calc_cogs()`, `calc_profit()`
  - 18 passing tests
  - Validates against LINE52 @ 12,000 KZT: COGS=5,005 ✓, NetRev=9,355 ✓, Profit=4,350 ✓

- [DONE] TASK-010: Create `scripts/build_daily_aggregates.py` (Completed: 2025-12-06)
  - Rebuild fact_sales_daily from fact_sales (625 records)
  - Rebuild fact_sales_daily_size from fact_sales (2,648 records)
  - Idempotent (DELETE + INSERT for date range)

---

## Phase 3: Calc Engine ✅

- [DONE] TASK-011: Create `core/calc/inventory.py` (Completed: 2025-12-06)
  - Functions: `calc_d30()`, `calc_sigma()`, `calc_ss_total()`, `calc_rop()`, `calc_roic()`
  - 24 passing tests
  - All formulas match Master_Inventory_Rules

- [DONE] TASK-012: Create `core/calc/status.py` (Completed: 2025-12-06)
  - Function: `calc_status(current_stock, total_stock, rop) -> str`
  - 3-state logic: REORDER / WAIT / OK
  - 17 passing tests
  - Critical: Checks Total FIRST, then Current

- [DONE] TASK-013: Create `scripts/run_sku_metrics.py` (Completed: 2025-12-06)
  - Computes metrics for all active SKUs
  - Saves to fact_sku_metrics table or exports CSV
  - Includes D₃₀, σ, SS_total, ROP, ROIC, Status, Suggested_Order_Qty

- [DONE] TASK-014: Create `scripts/validate_vs_excel.py` (Completed: 2025-12-06)
  - Compares Python outputs to Excel V15 for LINE52, LINE51
  - 13/13 tests pass within tolerances
  - D30 ±1% ✓, SS ±1% ✓, ROIC ±2% ✓, Status exact ✓

---

## Phase 4: Automation & Alerts ✅

- [DONE] TASK-015: Create `scripts/ingest_inventory_snapshot.py` (Completed: 2025-12-06)
  - Parses inventory Excel file (SKU_ID, SKU_key, MY_SIZE, Current_stock)
  - Saves to fact_inventory_snapshot_size table
  - 221 size-level records, 5,175 total units
  - 6 passing tests

- [DONE] TASK-016: Create Telegram bot for REORDER alerts (Completed: 2025-12-06)
  - Module: `core/alerts/telegram.py`
  - CLI: `scripts/run_reorder_alerts.py`
  - 24-hour cooldown to prevent alert fatigue
  - Logs to fact_alert_log for audit trail
  - 10 passing tests

- [DONE] TASK-017: Create `scripts/run_daily_pipeline.py` (Completed: 2025-12-06)
  - Orchestrator: ingest → transform → aggregate → calc → export → alert
  - CLI with --dry-run, --skip-ingest, --no-alerts options
  - Exports to exports/YYYY-MM-DD/

- [DONE] TASK-018: Create `scripts/export_po_suggestions.py` (Completed: 2025-12-06)
  - Generates PO suggestions with size splits (S, M, L, XL, 2XL, 3XL, 4XL)
  - Uses historical sales mix for size allocation
  - Exports to exports/YYYY-MM-DD/po_suggestions.csv

---

## Phase 5: Historical Data & Validation ✅

- [DONE] TASK-019: Create `scripts/import_historical_sales.py` (Completed: 2025-12-06)
  - Parse Archive_sales from SALES_KSP_CRM_GPT_15.9.25.xlsx
  - Direct import to fact_sales (bypasses fact_sales_raw)
  - Normalizes store codes, auto-creates dim_sku_size entries
  - 4,645 new records inserted (7,037 duplicates skipped)
  - Total fact_sales: 16,212 records

- [DONE] TASK-020: Rebuild aggregates with full history (Completed: 2025-12-06)
  - `python scripts/build_daily_aggregates.py`
  - fact_sales_daily: 1,311 records (406 unique dates)
  - fact_sales_daily_size: 4,711 records

- [DONE] TASK-021: Create `scripts/validate_phase5.py` (Completed: 2025-12-06)
  - Compares Python vs Excel V15 for multiple SKUs
  - Metrics: D30, sigma, SS_total, ROP, ROIC, Status
  - 16/16 tests pass within tolerances
  - Exports to reports/phase5_validation_YYYY-MM-DD.csv

- [DONE] TASK-022: Create `docs/DAILY_SOP.md` (Completed: 2025-12-06)
  - Morning routine and pipeline steps
  - PO interpretation guide
  - Error recovery procedures
  - Weekly checklist

- [DONE] TASK-023: Git remote configured (Completed: 2025-12-06)
  - Remote: https://github.com/maulen-m/Autonomous_business.git
  - All commits pushed

- [DONE] TASK-024: Create `reports/parallel_run_log.md` (Completed: 2025-12-06)
  - 7-day parallel run template
  - Day 1 (setup) completed
  - Days 2-7 pending execution

---

## Phase 6: Predictive Demand & Smart Safety Stock ✅

### Section A: Forecast Engine (Completed: 2025-12-06)

- [DONE] TASK-025: Create `core/calc/forecast.py`
  - calc_weighted_demand() with exponential decay (decay=0.95)
  - calc_trend_slope() via linear regression
  - calc_d_forecast() for horizon-based demand prediction
  - calc_confidence_interval() for uncertainty bounds

- [DONE] TASK-026: Create `core/calc/forecast_accuracy.py`
  - calc_mape(), calc_forecast_bias(), calc_mae(), calc_wmape()
  - backtest_forecast() for walk-forward validation
  - get_accuracy_grade() for MAPE -> A/B/C/D/F grading

### Section B: Foundation Tables (Completed: 2025-12-06)

- [DONE] TASK-027: Add `dim_seasonality` table
  - (month, product_type) -> multiplier mapping
  - Seeded with Kazakhstan retail patterns

- [DONE] TASK-028: Add `fact_demand_forecast` table
  - Stores forecast_date, target_date, sku_key, predicted_units

- [DONE] TASK-033: Add `dim_sku_lifecycle` table
  - lifecycle_status: GROW, MAINTAIN, HARVEST, KILL

- [DONE] TASK-040: Add `fact_stockout_events` table
  - Tracks stockout_date, duration_days, estimated_lost_sales

- [DONE] TASK-046: Add `fact_system_metrics` table
  - System health and performance logging

### Section C: Forecast Execution (Completed: 2025-12-06)

- [DONE] TASK-029: Create `scripts/run_forecast_engine.py`
  - Generates forecasts for all active SKUs
  - Horizons: 7, 14, 30 days
  - Applies seasonality multipliers

- [DONE] TASK-030: Enhanced ROP in `core/calc/inventory.py`
  - Added calc_rop_v2() with trend adjustment
  - Formula: ROP = (D + T×H) × L + SS

### Section D: Day-of-Week Patterns (Completed: 2025-12-06)

- [DONE] TASK-031: Create `core/calc/dow_patterns.py`
  - calc_dow_indices() for day-of-week multipliers
  - calc_weekend_lift() for Sat/Sun patterns
  - calc_pattern_strength() for variability

- [DONE] TASK-032: Create `scripts/report_dow_analysis.py`
  - Analyzes DOW patterns for all SKUs
  - Exports to reports/dow_analysis_YYYY-MM-DD.csv

### Section E: Stockout Tracking (Completed: 2025-12-06)

- [DONE] TASK-034: Create `scripts/detect_stockouts.py`
  - Detects zero-stock periods
  - Logs to fact_stockout_events

- [DONE] TASK-035: Create `scripts/report_stockout_costs.py`
  - Estimates lost revenue from stockouts
  - Uses D30 × margin for cost estimation

### Section F: Accuracy Tracking (Completed: 2025-12-06)

- [DONE] TASK-036: Add `fact_forecast_accuracy` table
  - Stores MAPE, bias, accuracy_date per SKU

- [DONE] TASK-037: Create `scripts/run_forecast_backtest.py`
  - Walk-forward backtesting
  - Stores accuracy metrics

- [DONE] TASK-038: Create `scripts/export_accuracy_trends.py`
  - Exports accuracy trends over time

### Section G: Portfolio Analytics (Completed: 2025-12-06)

- [DONE] TASK-039: Create `core/calc/portfolio.py`
  - calc_portfolio_roic() for portfolio-level metrics
  - identify_kill_candidates() for underperformers
  - recommend_lifecycle_status()

- [DONE] TASK-041: Create `scripts/run_portfolio_review.py`
  - Portfolio ROIC, capital at risk analysis
  - Lifecycle status recommendations
  - Exports reports/portfolio_review_YYYY-MM-DD.json

### Section H: Data Quality Monitoring (Completed: 2025-12-06)

- [DONE] TASK-042: Create `core/calc/data_quality.py`
  - detect_anomalies() for price/volume spikes
  - check_data_completeness() for missing data
  - flag_suspicious_patterns()

- [DONE] TASK-043: Create `scripts/run_data_quality_check.py`
  - Daily anomaly detection
  - Telegram alerts for critical issues
  - Exports reports/data_quality_YYYY-MM-DD.csv

### Section I: Alerts Enhancement (Completed: 2025-12-06)

- [DONE] TASK-044: Add forecast confidence to alerts
  - Low confidence forecasts flagged
  - Telegram messages include confidence bands

- [DONE] TASK-045: Create `scripts/send_weekly_summary.py`
  - Weekly metrics: ROIC, stockouts, forecast accuracy
  - Sent every Monday morning

### Section J: Export & Reports (Completed: 2025-12-06)

- [DONE] TASK-047: Create `scripts/export_forecast_report.py`
  - Full forecast report for all SKUs
  - Exports to reports/forecast_report_YYYY-MM-DD.xlsx

- [DONE] TASK-048: Create `scripts/export_safety_stock_analysis.py`
  - SS components breakdown
  - Comparison vs V15 baseline

- [DONE] TASK-049: Create `scripts/export_executive_summary.py`
  - High-level metrics for management
  - Exports to reports/executive_summary_YYYY-MM-DD.csv

- [DONE] TASK-050: Create `scripts/send_daily_digest.py`
  - Daily summary Telegram message
  - Includes key metrics, alerts, next actions

### Section K: Auto-PO System (Completed: 2025-12-06)

- [DONE] TASK-058: Add `fact_po_draft` and `fact_po_draft_lines` tables
  - Draft purchase orders with line items
  - Status tracking: PENDING, APPROVED, REJECTED, EXPIRED

- [DONE] TASK-059: Create `core/automation/po_generator.py`
  - calc_order_quantity() with ROP trigger
  - apply_size_splits() using historical mix
  - generate_po_draft() for automatic PO creation
  - calc_confidence_score() for draft quality

- [DONE] TASK-060: Create `scripts/run_auto_po.py`
  - CLI for automatic PO generation
  - --dry-run mode for testing
  - --min-confidence filter

- [DONE] TASK-061: Create `scripts/po_approval_cli.py`
  - Interactive PO approval workflow
  - approve/reject/view draft commands

- [DONE] TASK-062: Create `scripts/expire_po_drafts.py`
  - Expires stale PENDING drafts (14 days default)

- [DONE] TASK-064: Create `scripts/report_po_analytics.py`
  - PO approval rates, rejection reasons
  - Confidence vs approval correlation

- [DONE] TASK-065: Add `fact_po_execution` table
  - Tracks actual received vs ordered quantities

### Section L: Testing (Completed: 2025-12-06)

- [DONE] TASK-051: Create `tests/test_forecast.py`
  - 37 tests for forecast functions
  - Covers weighted demand, trend, MAPE, confidence

- [DONE] TASK-052: Create `tests/test_portfolio.py`
  - 18 tests for portfolio analytics
  - Covers concentration rule, lifecycle status

- [DONE] TASK-053: Create `tests/test_data_quality.py`
  - 22 tests for anomaly detection
  - Covers severity levels, thresholds

- [DONE] TASK-054: Create `tests/test_integration.py`
  - 21 end-to-end integration tests
  - Forecast → inventory → economics pipeline

### Section M: Documentation (Completed: 2025-12-06)

- [DONE] TASK-055: Update TASKS.md
  - All Phase 6 tasks documented

- [DONE] TASK-056: Create `docs/ARCHITECTURE.md`
  - System architecture overview
  - Module dependencies

- [DONE] TASK-057: Update `docs/DAILY_SOP.md`
  - Phase 6 features added to daily routine

---

## Phase 6 Summary

**Total Tests:** 201 (was 103)
**New Tables:** 9
**New Scripts:** 19
**New Core Modules:** 5

---

## Phase 6.6: Data Quality Fix (Completed: 2025-12-06)

- [DONE] TASK-070: Create `scripts/audit_dim_sku.py`
  - Identifies SKUs with missing COGS/weight data
  - Found 49 SKUs with missing costs

- [DONE] TASK-071: Create `scripts/import_sku_costs.py`
  - Imports cost data from Inventory_Core_V15_FINAL.xlsx
  - 54 SKUs with complete cost data synced

- [DONE] TASK-072: Create `scripts/reimport_skipped_sales.py`
  - Re-imports sales that were skipped due to missing COGS
  - Rebuilt fact_sales: 13,050 records (was 11,576)

- [DONE] TASK-073: Create `scripts/validate_data_completeness.py`
  - Data quality validation checks
  - All checks passing

---

## Phase 7: Capital Allocation Optimizer (Completed: 2025-12-06)

### Section B: Capital Tracking Infrastructure

- [DONE] TASK-074: Create `fact_capital_allocation` and `fact_portfolio_summary` tables
  - Migration 008 applied
  - Tracks capital deployed, ROIC, portfolio metrics per SKU

- [DONE] TASK-075: Create `scripts/build_capital_snapshot.py`
  - Builds daily capital allocation snapshot
  - Calculates ROIC, capital share, rankings

### Section C: Capital Optimizer Core

- [DONE] TASK-076: Create `core/calc/capital_optimizer.py`
  - optimize_allocation() for portfolio ROIC maximization
  - calc_portfolio_impact() for expected returns
  - check_concentration_rule() for 20% max per SKU

- [DONE] TASK-077: Create `core/calc/lifecycle_classifier.py`
  - classify_lifecycle() with GROW/MAINTAIN/HARVEST/KILL
  - update_lifecycle_statuses() to update dim_sku_lifecycle

### Section D: Portfolio Review & Reporting

- [DONE] TASK-078: Create `scripts/run_portfolio_review_v2.py`
  - Weekly portfolio analysis and recommendations
  - Exports reports/portfolio_review_YYYY-MM-DD.json

- [DONE] TASK-079: Create `scripts/generate_kill_list.py`
  - Lists SKUs recommended for liquidation
  - Estimates recovery values

### Section E: PO Integration

- [DONE] TASK-080: Add `generate_po_draft_with_validation()` to `core/automation/po_generator.py`
  - Validates PO against 20% concentration rule
  - Auto-adjusts quantities if violations

### Section F: Testing

- [DONE] TASK-081: Create `tests/test_capital_optimizer.py`
  - 12 tests for capital optimizer
  - Covers optimization, concentration, portfolio impact

- [DONE] TASK-082: Create `tests/test_lifecycle.py`
  - 13 tests for lifecycle classifier
  - Covers all lifecycle states and transitions

### Section G: Pipeline Integration

- [DONE] TASK-083: Add capital snapshot to `scripts/run_daily_pipeline.py`
  - New step: build_capital_snapshot after compute_metrics

---

## Phase 7 Summary

**Total Tests:** 243 (was 218)
**New Tables:** 2 (fact_capital_allocation, fact_portfolio_summary)
**New Scripts:** 7
**New Core Modules:** 2

---

## Phase 8: Multi-Channel Intelligence ✅

**Target:** Unified Kaspi + WB data model, channel comparison, expansion scoring
**Prerequisites:** Phase 7 complete
**Completed:** 2025-12-06

### Section A: Schema & Migrations (Completed: 2025-12-06)

- [DONE] TASK-085: Create `dim_channel` table (Migration 010)
  - Channel configuration and fee structures
  - Seeded Kaspi (12.5% commission, 2-day payment) and WB (24.5% commission, 408₽ logistics)

- [DONE] TASK-086: Create `fact_channel_metrics` table
  - Daily + rolling metrics per SKU per channel
  - Volume, revenue, margin, ROIC tracking

- [DONE] TASK-087: Create `fact_channel_inventory` table
  - Stock levels per channel, days of cover, stockout risk

- [DONE] TASK-088: Create `fact_expansion_scores` table
  - Expansion potential scores per SKU for target channels

### Section B: Channel Data Ingestion (Completed: 2025-12-06)

- [DONE] TASK-089: Create `core/calc/wb_economics.py`
  - WB net revenue formula: NetRev = Price × (1 - 24.5%) - 408₽
  - Convert to KZT with 3% tax
  - calc_wb_profit(), calc_wb_breakeven_price(), calc_wb_roic()
  - compare_kaspi_vs_wb() for channel comparison

- [DONE] TASK-090: Create `core/parsers/wb_parser.py`
  - Parse WB sales reports (Russian columns)
  - Map to internal data model, extract sku_key

- [DONE] TASK-091: Create `scripts/ingest_channel_sales.py`
  - Unified ingestion for both Kaspi and WB
  - CLI: --channel KSP|WB flag

- [DONE] TASK-092: Add WB store to `dim_store`
  - wb_fbo store with channel_code='WB'

### Section C: Channel Metrics Engine (Completed: 2025-12-06)

- [DONE] TASK-093: Create `core/calc/channel_metrics.py`
  - calc_channel_metrics_for_date() with 30-day rolling
  - save_channel_metrics() to fact_channel_metrics

- [DONE] TASK-094: Create `core/calc/channel_comparison.py`
  - compare_channels() for same SKU across channels
  - Recommend channel based on ROIC and volume

- [DONE] TASK-095: Create `scripts/build_channel_metrics.py`
  - Daily build script with --backfill option

### Section D: Expansion Scorer (Completed: 2025-12-06)

- [DONE] TASK-096: Create `core/calc/expansion_scorer.py`
  - score_sku_for_expansion() with demand/margin/competition scores
  - Recommendations: EXPAND, TEST, HOLD, SKIP

- [DONE] TASK-097: Create `scripts/run_expansion_analysis.py` (Completed: 2025-12-06)
  - Score all Kaspi SKUs for WB potential
  - Export to reports/expansion_scores_YYYY-MM-DD.csv
  - CLI with --min-score, --recommendation filters

### Section E: Transfer Recommender (Completed: 2025-12-06)

- [DONE] TASK-098: Create `core/calc/transfer_recommender.py`
  - recommend_transfers() between channels
  - Balance inventory to prevent stockouts
  - TransferRecommendation dataclass with urgency/confidence

- [DONE] TASK-099: Create `scripts/run_transfer_analysis.py`
  - Daily transfer recommendations
  - Telegram alert for critical imbalances
  - CSV export with --export flag

### Section F: Testing (Completed: 2025-12-06)

- [DONE] TASK-100: Create `tests/test_wb_economics.py`
  - 35 unit tests for WB calculations
  - Validates against WB_policy_v4.md examples
  - All tests passing

- [DONE] TASK-101: Create `tests/test_channel_metrics.py`
  - 21 tests for channel metrics calculations
  - Covers dataclasses, calculations, comparison logic

- [DONE] TASK-102: Create `tests/test_expansion_scorer.py`
  - 36 tests for expansion scoring logic
  - Covers demand/margin/competition scores, recommendations

### Section G: Pipeline Integration (Completed: 2025-12-06)

- [DONE] TASK-103: Add channel metrics to daily pipeline
  - step_build_channel_metrics() added after capital snapshot
  - Integrated in run_daily_pipeline.py

---

## Phase 8 Summary

**Total Tests:** 300 (was 243)
**New Tables:** 4 (dim_channel, fact_channel_metrics, fact_channel_inventory, fact_expansion_scores)
**New Scripts:** 5 (ingest_channel_sales, build_channel_metrics, run_expansion_analysis, run_transfer_analysis, migrate_010)
**New Core Modules:** 6 (wb_economics, wb_parser, channel_metrics, channel_comparison, expansion_scorer, transfer_recommender)

---

## Phase 9.5: Kaspi Order Automation 🚧

**Target:** Replace manual Chrome profile switching with API-based order sync
**Prerequisites:** Phase 8 complete, API tokens in .env
**Spec:** `Phase_9_5_Kaspi_Order_Automation_Mega_Tasks.md`
**Test Store:** Universal (single store validation before multi-store rollout)

### Section A: Discovery & Audit (In Progress)

- [IN_PROGRESS] TASK-110: Audit legacy script logic
  - Document `import_active_orders.py` behavior (21K chars)
  - Document `build_kaspi_orders.py` behavior (18K chars)
  - Output: `docs/legacy_kaspi_audit.md`

- [TODO] TASK-111: Map legacy columns to Project 3 schema
  - Create `config/kaspi_column_map.yaml`
  - Russian → English column mapping

### Section B: Order Ingestion Rebuild (Phase 1)

- [TODO] TASK-112: Create `core/parsers/kaspi_export_parser.py`
  - parse_active_orders(), filter_for_shipment(), normalize_order()
  - Pure Python, no xlwings dependency

- [TODO] TASK-113: Create `scripts/ingest_kaspi_export.py`
  - CLI for Excel export ingestion
  - UPSERT on (order_id, sku_id, store_code)

- [TODO] TASK-114: Create `fact_orders_kaspi` table (Migration 011)
  - Order lifecycle tracking separate from sales
  - Waybill URL and download status

### Section C: PDF Waybill Grouping (Phase 1)

- [TODO] TASK-115: Create `core/waybill/pdf_grouper.py`
  - WaybillGroup dataclass
  - NORMAL/MULTI_LINE/MULTI_QTY grouping logic
  - PDF merge with PyPDF2

- [TODO] TASK-116: Create `scripts/build_waybill_bundles.py`
  - CLI for grouped PDF generation
  - Output: NORMAL_singles/, SPECIAL_multi_line/, SPECIAL_multi_qty/

### Section D: Testing Phase 1

- [TODO] TASK-117: Create `tests/test_kaspi_export_parser.py`
  - Russian columns, date parsing, status filtering

- [TODO] TASK-118: Create `tests/test_pdf_grouper.py`
  - ZIP extraction, grouping logic, PDF merge

### Section E: Pipeline Integration Phase 1

- [TODO] TASK-119: Add kaspi export ingestion to daily pipeline
  - step_ingest_kaspi_exports() in run_daily_pipeline.py

### Section F: API Client (Phase 2)

- [TODO] TASK-120: Create `core/integrations/kaspi_api_client.py`
  - KaspiAPIClient class with retry logic
  - Multi-store token support from env vars

- [TODO] TASK-121: Create `config/kaspi_stores.yaml`
  - Store configuration with token references
  - Universal store as primary test target

### Section G: Order Sync Engine (Phase 2)

- [TODO] TASK-122: Create `core/sync/order_sync_engine.py`
  - OrderSyncEngine class
  - sync_store(), sync_all_stores(), detect_status_changes()

- [TODO] TASK-123: Create `scripts/sync_kaspi_orders.py`
  - CLI for manual and scheduled sync
  - --store, --since, --states filters

### Section H: Waybill Automation (Phase 2)

- [TODO] TASK-124: Create `core/waybill/waybill_downloader.py`
  - Async parallel download with aiohttp
  - Rate limiting respect

- [TODO] TASK-125: Create `scripts/download_waybills.py`
  - CLI for batch waybill download

### Section I: Order Status Management (Phase 2)

- [TODO] TASK-126: Create `core/automation/order_status_manager.py`
  - OrderStatusManager class
  - accept_orders(), mark_assembled(), auto_accept_ready_orders()
  - ENABLE_KASPI_WRITE guard

- [TODO] TASK-127: Create `scripts/manage_kaspi_orders.py`
  - CLI: accept, accept-ready, assemble, cancel, list-pending

### Section J: Alerts & Monitoring (Phase 2)

- [TODO] TASK-128: Create `core/alerts/order_alerts.py`
  - alert_new_orders(), alert_status_changes(), alert_shipment_ready()
  - Telegram integration

- [TODO] TASK-129: Add order sync to daily pipeline
  - step_sync_kaspi_orders(), step_download_waybills(), step_alert_shipment_ready()

### Section K: Testing Phase 2

- [TODO] TASK-130: Create `tests/test_kaspi_api_client.py`
  - Mocked API responses (vcr.py)
  - Token loading, pagination, retry logic

- [TODO] TASK-131: Create `tests/test_order_sync.py`
  - Full sync cycle, incremental sync, status detection

- [TODO] TASK-132: Create `tests/test_waybill_downloader.py`
  - Batch download, error handling

### Section L: Documentation (Phase 2)

- [TODO] TASK-133: Create `docs/KASPI_API_INTEGRATION.md`
  - Token setup, multi-store config, error handling

- [TODO] TASK-134: Update `docs/DAILY_SOP.md`
  - New order sync commands, waybill workflow

---

## Phase 9.5 Summary (Planned)

**Total Tasks:** 25
**Phase 1 (Legacy Migration):** 10 tasks, ~20 hours
**Phase 2 (API Integration):** 15 tasks, ~30 hours
**Expected ROI:** -60 min/day manual work

---

## Parking Lot (Future)

- [ ] Size allocation engine (Alloc_i formula for T_post)
- [ ] Cash ledger events
- [ ] Multi-store rollup views
- [ ] WhatsApp/Slack alert channels
- [ ] Auto-supplier ordering integration
- [ ] Machine learning forecast models
- [ ] WB tariff calculator API integration (per-SKU fees)
- [ ] Phase 9: Supplier & Logistics Optimization
- [ ] Phase 10: Autonomous Operations
