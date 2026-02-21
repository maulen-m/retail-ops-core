# 2-Week Execution Board (A -> C -> B)

## Objective
Convert the recommended sequence into an execution-grade 2-week board that closes highest business-risk gaps first:

- `A`: Trust closure (data correctness + strict publication safety)
- `C`: Financial realism (ads-aware profit and capital visibility)
- `B`: Operations throughput (shipping/waybill runtime reliability)

Window:
- Week 1: `2026-02-23` to `2026-02-27`
- Week 2: `2026-03-02` to `2026-03-06`

Non-negotiables:
- Tests-first, fail-first evidence before every behavior change.
- Fail-closed only; no warning-only downgrade for stop-line checks.
- No DB write/apply unless both env gate + explicit `--apply` exist and are covered by tests.
- Keep unrelated repo changes untouched.

## Owners
- `Truth/DB Owner`: `db_main` (data contracts, validators, schema-safe changes)
- `Finance Owner`: `main_agent_1` (cashflow/profit publication paths)
- `Ops Runtime Owner`: `main_agent_1` (waybill/ship runtime reliability)
- `Reviewer`: `Adil` (final business acceptance, 0-5% human effort)

## Board

| ID | Window | Owner | Task | Deliverables (exact paths) | Fail-first tests (must fail first) | Task gates (must pass) | Stop-line criteria |
|---|---|---|---|---|---|---|---|
| A-1 | W1 D1-D2 | Truth/DB Owner | Inbound workbook mismatch detector (cargo vs inbound sheets) | `scripts/validate_inbound_sheet_consistency.py`, `tests/test_validate_inbound_sheet_consistency.py`, `docs/inventory/INBOUND_SHEET_PRECHECK_CONTRACT.md`, `exports/validation/board_2w_2026-02-23/a1/` | `test_flags_qty_mismatch_between_cargo_and_inbounds`, `test_reports_authoritative_sheet_precedence`, `test_exit_nonzero_on_contract_breach` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_validate_inbound_sheet_consistency.py`, `python3 scripts/validate_inbound_sheet_consistency.py --xlsx "config/anchors/INBOUND_CALENDAR_LATEST.xlsx"` | Any mismatch undetected; any authoritative-sheet ambiguity; validator exits 0 while breaches exist |
| A-2 | W1 D2-D4 | Truth/DB Owner | Offer linkage strict closure for publish safety | `scripts/reconcile_offer_linkage.py`, `scripts/validate_offer_stock_sync.py` updates, `tests/test_reconcile_offer_linkage.py`, `exports/validation/board_2w_2026-02-23/a2/` | `test_unresolved_offers_fail_strict_publish`, `test_bidirectional_mapping_required_for_publish`, `test_idempotent_reconcile_no_duplicate_links` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_reconcile_offer_linkage.py tests/test_validate_offer_stock_sync.py`, `python3 scripts/validate_offer_stock_sync.py --strict` | Strict publish can pass with unresolved offers; mapping non-idempotent; store-level linkage drift |
| A-3 | W1 D4-D5 | Truth/DB Owner + Finance Owner | COGS hard-block in all profit outputs (no partial COGS publication) | `scripts/validate_cogs_integrity.py` hardening, `scripts/generate_business_insides.py` guard updates, `scripts/generate_po_dashboard_data.py` guard updates, `tests/test_profit_publication_integrity.py`, `exports/validation/board_2w_2026-02-23/a3/` | `test_profit_is_na_when_unresolved_cogs_rows_exist`, `test_dashboard_profit_blocks_on_partial_cogs`, `test_business_insides_fails_strict_on_unresolved_cogs` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_profit_publication_integrity.py tests/test_business_insides_cogs_strictness.py`, `python3 scripts/validate_cogs_integrity.py` | Any published profit includes unresolved/partial COGS; strict validators return PASS with unresolved rows |
| C-1 | W2 D1-D2 | Finance Owner | Ads sidecar read-only integration from external DB (coverage-first) | `core/ads/sidecar.py`, `scripts/build_ads_sidecar_snapshot.py`, `tests/test_ads_sidecar_snapshot.py`, `docs/KASPI_MARKETING_ADS_INTEGRATION_CONTRACT.md`, `exports/validation/board_2w_2026-02-23/c1/` | `test_sidecar_fails_closed_when_ads_db_missing`, `test_sidecar_reports_mapping_coverage`, `test_no_write_side_effects_in_readonly_mode` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_ads_sidecar_snapshot.py`, `python3 scripts/build_ads_sidecar_snapshot.py --db "~/Documents/useful tables/Main crm spreadsheets/main tables/External_database/Kaspi_marketing/db/kaspi_marketing.db"` | Sidecar silently succeeds with missing source DB; writes to app DB without gate; zero coverage reported as PASS |
| C-2 | W2 D2-D4 | Finance Owner | Profit-after-ads integration in business outputs (without cash-close distortion) | `scripts/generate_business_insides.py` updates, `scripts/update_cashflow_dashboard.py` component cards, `tests/test_profit_after_ads_publication.py`, `exports/validation/board_2w_2026-02-23/c2/` | `test_profit_after_ads_uses_sidecar_only`, `test_cash_close_statement_values_unchanged_by_ads`, `test_unmapped_ads_reported_not_hidden` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_profit_after_ads_publication.py tests/test_generate_business_insides.py`, `python3 scripts/generate_business_insides.py --as-of 2026-03-06 --strict-cogs` | Cash-close path changes from ads attribution; unmapped ads silently dropped; profit-after-ads shown without coverage disclaimer |
| C-3 | W2 D4 | Finance Owner | Capital view consistency: paid/unpaid inbound obligations unified across dashboards | `scripts/update_cashflow_dashboard.py`, `scripts/validate_single_truth_system.py` rules, `tests/test_paid_capital_components_consistency.py`, `exports/validation/board_2w_2026-02-23/c3/` | `test_paid_capital_components_match_contract`, `test_unpaid_inbound_obligations_visible`, `test_dashboard_and_business_insides_component_parity` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_paid_capital_components_consistency.py`, `python3 scripts/validate_single_truth_system.py` | Paid/unpaid definitions diverge between surfaces; obligations hidden in one dashboard |
| B-1 | W2 D4-D5 | Ops Runtime Owner | Waybill runtime health state machine (API delayed URL + fallback clarity) | `scripts/download_waybills_api.py`, `scripts/build_daily_waybills.py`, `tests/test_waybill_runtime_health.py`, `exports/validation/board_2w_2026-02-23/b1/` | `test_delayed_waybill_url_reported_as_pending_not_missing`, `test_store_filter_aliases_are_validated`, `test_api_error_does_not_mark_shipped_false_positive` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_waybill_runtime_health.py tests/test_waybill_selection_filters.py`, `python3 scripts/report_waybill_status.py --date 2026-03-06` | Any false shipped counts; pending/delayed states misclassified as missing; store alias mismatch causes silent skip |
| B-2 | W2 D5 | Ops Runtime Owner | Pre-shipment hard preflight + retry/backoff contract and runbook closure | `scripts/run_build_waybills.command` preflight contract update, `tests/test_waybill_preflight_contract.py`, `docs/DAILY_SOP.md` update, `exports/validation/board_2w_2026-02-23/b2/` | `test_preflight_blocks_on_anchor_or_api_contract_failure`, `test_retry_policy_caps_and_reports`, `test_operator_output_contains_stopline_reason` | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/test_waybill_preflight_contract.py`, `bash scripts/install_single_truth_ops_scheduler.sh --validate-only`, `python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business` | Shipment command can run after hard preflight failure; retries unbounded; operator lacks explicit stop reason |

## End-of-Phase Global Gates
Run at end of each phase (`A`, `C`, `B`) and record logs under `exports/validation/board_2w_2026-02-23/<phase>/global_gates.md`:

```bash
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python3 scripts/run_contract_suite.py --fixture small
python3 scripts/validate_single_truth_system.py
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

## Release Gate (end of 2 weeks)
Required for declaring sprint completion:

```bash
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
python3 scripts/run_contract_suite.py --fixture small
python3 scripts/validate_single_truth_system.py
bash scripts/install_single_truth_ops_scheduler.sh --validate-only
python3 scripts/check_anchor_health.py --project-root ~/Docs/Autonomous_business
python3 scripts/ops_status.py --project-root ~/Docs/Autonomous_business
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```

## Stop-line Rules (global)
- Any fail-closed guard returns non-zero and is bypassed in code path.
- Any profit metric is published while unresolved COGS rows exist.
- Any write-capable path can mutate state without env gate + `--apply`.
- Any CI/local gate divergence is unexplained in evidence artifacts.

## Rollback Protocol (per task)
1. Revert only the task commit range:
```bash
git revert <newest_commit> ... <oldest_commit>
```
2. Re-run minimum safety gates:
```bash
python3 scripts/validate_params.py --strict
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
scripts/lint_docs.sh
scripts/check_no_db_tracked.sh
```
3. If any DB apply was explicitly executed for that task, restore from the recorded backup path and rerun strict gates.

## Minimal Human Actions (0-5%)
- PR review/merge decision.
- Secrets/login checks only where external systems require it (no manual data edits as part of normal execution).
