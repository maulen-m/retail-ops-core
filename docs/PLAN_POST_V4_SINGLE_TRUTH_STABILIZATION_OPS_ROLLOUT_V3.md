# PLAN_POST_V4_SINGLE_TRUTH_STABILIZATION_OPS_ROLLOUT_V3 (Ads Excluded)

## Summary
This plan executes the next highest-impact stabilization work after Ops Reliability v2.1, focused on capital protection and false-green prevention:
1. Sales Truth Consumer Lockdown (static + runtime enforcement).
2. COGS hard-block wherever profit is published.
3. Workbook freshness v2 (content-based lag, not only mtime).
4. Daily drift monitoring pack artifact.
5. Deterministic governance for `docs/transfer_ledger/*` (tracked, script-generated only).

Locked decisions:
- Ads stays out of scope and continues in separate worktree.
- Sales consumer enforcement uses static validator + runtime SQL guard.
- COGS block scope: business-insides + PO dashboard + strict chain.
- Transfer ledger policy: deterministic generation + commit.

## Current-State Facts (grounded)
1. `scripts/run_strict_daily_preflight.py` already has fail-closed workbook path, mtime controls, business-insides autogen, and alerting.
2. `scripts/validate_sales_vs_workbook_anchor.py` depends on `scripts/validate_sales_against_workbook.py`.
3. `scripts/generate_po_dashboard_data.py` still reads raw sales tables (`fact_sales_daily_size`, `fact_sales`) in profit/price paths.
4. `scripts/generate_business_insides.py` supports `--strict-cogs`, but strict preflight path does not enforce it.
5. `scripts/validate_business_insides.py` checks snapshot existence and basic metrics, not deep content integrity.
6. Transfer-ledger docs are tracked and frequently dirty; no explicit deterministic governance contract is enforced.

## Public Interfaces / Contracts to Add or Change
1. New validator: `scripts/validate_sales_truth_consumers.py`.
2. New contract config: `config/sales_truth_consumer_contract.yaml`.
3. New runtime guard module: `core/db/sales_truth_query_guard.py`.
4. New validator: `scripts/validate_profit_publication_integrity.py`.
5. Extend workbook anchor comparator:
   - `scripts/validate_sales_against_workbook.py`
   - `scripts/validate_sales_vs_workbook_anchor.py`
   - Add content-lag checks (`max_lag_days`).
6. New artifact builder: `scripts/build_single_truth_drift_pack.py`.
7. New transfer-ledger governance doc: `docs/transfer_ledger/GOVERNANCE.md`.
8. Strict-chain wiring update: `scripts/validate_params.py`.
9. Preflight strict-CODS/default behavior update: `scripts/run_strict_daily_preflight.py`.
10. Oracle pack contract update (already partially done): ensure comparator chain stays mandatory in `Oracle_listings/oracle_pack_file_lists.md`.

## Phase 0 — Baseline and Safety
1. Capture pre-change baseline outputs (read-only):
   - `python3 scripts/validate_params.py --strict`
   - `python3 scripts/validate_single_truth_system.py`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
2. Record current raw-table consumers with:
   - `rg -n "\\bfact_sales\\b|\\bsales_fact_v2\\b" scripts core`
3. No DB apply/write actions in this plan unless explicitly gated (`ENABLE_*` + `--apply`).

## Phase 1 — Sales Truth Consumer Lockdown
### Tests first (fail-first)
1. Add `tests/test_validate_sales_truth_consumers.py`:
   - fails on disallowed raw reads in production scripts.
   - passes for allowlisted staging/ingestion scripts.
2. Add `tests/test_sales_truth_query_guard.py`:
   - runtime guard blocks `SELECT` from `fact_sales`, `sales_fact_v2`, `fact_sales_daily`, `fact_sales_daily_size`.
   - runtime guard allows `view_sales_line_truth`, `view_sales_daily_truth`.
3. Add `tests/test_generate_po_dashboard_data_truth_sources.py`:
   - fails if dashboard generator still uses raw sales tables in production computation paths.

### Implementation
1. Create `config/sales_truth_consumer_contract.yaml`:
   - `production_scripts`: scripts that must use published views only.
   - `allow_raw_read_scripts`: ingestion/migration/reconciliation diagnostics.
   - `disallowed_tables`: `fact_sales`, `sales_fact_v2`, `fact_sales_daily`, `fact_sales_daily_size`.
2. Implement `scripts/validate_sales_truth_consumers.py` static scanner.
3. Implement `core/db/sales_truth_query_guard.py` using SQLite authorizer to block disallowed table reads.
4. Update production scripts to comply:
   - `scripts/generate_po_dashboard_data.py`: replace raw sales queries with `view_sales_line_truth`/`view_sales_daily_truth` aggregations.
   - `scripts/generate_business_insides.py`: enforce guarded read path in strict mode.
   - `scripts/update_cashflow_dashboard.py`: guard any direct sales reads (if present now or added later).
5. Wire `validate_sales_truth_consumers` into `validate_params.py --strict`.

### Acceptance
1. Zero disallowed raw reads in production scripts.
2. Runtime guard blocks accidental violations in strict paths.
3. Dashboard and business-insides still generate with published-view numbers only.

## Phase 2 — COGS Hard-Block Across Profit Surfaces
### Tests first (fail-first)
1. Add `tests/test_profit_publication_integrity.py`:
   - unresolved COGS rows make profit publication invalid.
   - business-insides strict generation fails with unresolved rows.
   - PO dashboard profit/ROIC fields are `N/A`/`null` for unresolved rows.
2. Extend `tests/test_run_strict_daily_preflight.py`:
   - assert preflight business-insides generation uses strict COGS mode.
3. Extend `tests/test_validate_params_strict_chain.py`:
   - strict fails when unresolved COGS leaks into published profit outputs.

### Implementation
1. Add `scripts/validate_profit_publication_integrity.py`:
   - cross-check `view_sales_line_truth` unresolved rows vs published profit fields in:
     - business-insides snapshot
     - `exports/po_dashboard_data.json`
2. Update `scripts/run_strict_daily_preflight.py`:
   - business-insides autogen invokes `scripts/generate_business_insides.py --strict-cogs`.
3. Update `scripts/generate_po_dashboard_data.py`:
   - carry per-SKU COGS status.
   - unresolved COGS rows cannot contribute to profit/ROIC totals.
   - unresolved rows are explicitly flagged in output.
4. Wire `validate_profit_publication_integrity.py` into `validate_params.py --strict`.

### Acceptance
1. Any unresolved COGS in publication window blocks strict green.
2. No profit totals include unresolved rows.
3. Operator surfaces show unresolved state explicitly, not silent numeric profit.

## Phase 3 — Workbook Freshness v2 (Content-Based)
### Tests first (fail-first)
1. Add `tests/test_validate_sales_against_workbook_freshness.py`:
   - fail when workbook max business date lags beyond threshold.
   - pass when lag within threshold.
   - fail closed on parse errors.
2. Extend preflight tests:
   - verify lag-check failure message includes workbook max date and allowed lag.

### Implementation
1. Extend `scripts/validate_sales_against_workbook.py`:
   - compute `workbook_max_date` from parsed workbook rows.
   - add `max_lag_days` check (default `1`).
2. Extend `scripts/validate_sales_vs_workbook_anchor.py` CLI passthrough.
3. Update `scripts/validate_params.py` strict workbook gate:
   - pass `max_lag_days` from env `AB_CRM_WORKBOOK_MAX_LAG_DAYS` (default `1`).
4. Keep mtime check in preflight as secondary file-level guard.
5. Update plist env contract:
   - `AB_CRM_WORKBOOK_MAX_LAG_DAYS=1`.

### Acceptance
1. “Fresh file but stale data” fails strict.
2. Workbook gate stays anti-inflation and fail-closed.

## Phase 4 — Daily Drift Monitoring Pack
### Tests first (fail-first)
1. Add `tests/test_build_single_truth_drift_pack.py`:
   - generated artifact includes all required sections.
   - no DB writes.
   - deterministic file naming/date partitioning.

### Implementation
1. Add `scripts/build_single_truth_drift_pack.py` outputting:
   - `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.md`
   - `exports/validation/<YYYY-MM-DD>/single_truth_drift_pack.json`
2. Required sections:
   - workbook overage summary (DB > workbook only).
   - unresolved COGS rows and top SKUs.
   - on-delivery residual summary.
   - dim_sku alignment summary.
   - paid-capital snapshot summary.
3. Integrate into preflight as best-effort emission after strict pass:
   - new flag `--emit-drift-pack` (default enabled for scheduler path).

### Acceptance
1. Daily drift artifact generated with complete sections.
2. Ops can detect drift without opening multiple dashboards/scripts.

## Phase 5 — Transfer Ledger Deterministic Governance (Tracked)
### Tests first (fail-first)
1. Add `tests/test_transfer_ledger_governance_contract.py`:
   - docs state “script-generated only, no manual edits”.
   - canonical script path referenced.
2. Add deterministic output test with fixture DB:
   - repeated generation yields byte-identical output for same input snapshot.

### Implementation
1. Add `docs/transfer_ledger/GOVERNANCE.md`:
   - policy: tracked, deterministic, generated only.
   - canonical generation command.
   - commit discipline and review checklist.
2. Update `docs/transfer_ledger/README.md` to reference governance doc.
3. Harden `scripts/generate_transfer_ledger_reports.py` for deterministic ordering/format where needed.

### Acceptance
1. Team uses one stable policy (no ambiguity).
2. Ledger-doc churn becomes auditable rather than noisy.

## Verification Sequence
1. Phase-targeted fail-first tests for each phase.
2. Phase-targeted green reruns.
3. Full gates:
   - `python3 scripts/validate_params.py --strict`
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q`
   - `python3 scripts/run_contract_suite.py --fixture small`
   - `python3 scripts/validate_single_truth_system.py`
   - `scripts/lint_docs.sh`
   - `scripts/check_no_db_tracked.sh`
4. Strict preflight smoke:
   - `python3 scripts/run_strict_daily_preflight.py --db db/app.db --workbook config/anchors/SALES_KSP_CRM_LATEST.xlsx --emit-lineage --send-alert-on-fail`

## Commit Sequence
1. `tests: add consumer-lockdown, runtime guard, and workbook freshness-v2 fail-first coverage`
2. `sales-truth: add consumer validator and runtime query guard; migrate production consumers to published views`
3. `cogs: enforce hard-block on unresolved COGS across business-insides and po dashboard publication`
4. `workbook: add content-lag freshness checks to workbook anchor validation`
5. `ops: add daily single-truth drift pack generation and preflight integration`
6. `transfer-ledger: add deterministic tracked governance and report contract hardening`
7. `docs: update SOP/architecture/contracts for single-truth enforcement v3`

## Assumptions / Defaults
1. Ads stream remains excluded in this plan.
2. Business timezone for workbook lag checks uses repo/operator local day unless explicit timezone config is added; default lag threshold is 1 day.
3. Ingestion/migration scripts may read raw tables and are allowlisted; production decision surfaces are not.
4. DB writes remain gated and are not introduced by this stabilization plan.
