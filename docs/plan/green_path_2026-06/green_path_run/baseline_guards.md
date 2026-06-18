# PKT-READY Baseline Guards

- Repo inspected read-only: `~/Docs/Autonomous_business`
- Scratch env: `/tmp/green_path_scratch`

| Gate | Command | Exit | Summary |
| --- | --- | ---: | --- |
| `validate_write_side_gating` | `~/Docs/Autonomous_business/.venv/bin/python scripts/validate_write_side_gating.py` | 0 | checked_count=38 |
| `pytest` | `~/Docs/Autonomous_business/.venv/bin/python -m pytest -q` | 1 | 49 failed, 3371 passed, 4 skipped, 1 xfailed, 33 warnings in 264.77s (0:04:24) |
| `check_no_db_tracked` | `bash scripts/check_no_db_tracked.sh` | 0 | bash: warning: setlocale: LC_ALL: cannot change locale (C.UTF-8): No such file or directory |
| `lint_docs` | `bash scripts/lint_docs.sh` | 1 | Docs lint failed. Remove legacy references in non-archive docs. |

## validate_write_side_gating

- Command: `~/Docs/Autonomous_business/.venv/bin/python scripts/validate_write_side_gating.py`
- Exit code: `0`
- Timed out: `False`
- Last output lines:

```
WRITE_SIDE_GATING PASS
checked_count=38

```

## pytest

- Command: `~/Docs/Autonomous_business/.venv/bin/python -m pytest -q`
- Exit code: `1`
- Timed out: `False`
- Last output lines:

```
FAILED tests/test_prepare_line31_launch_readiness_from_assets.py::test_prepare_launch_readiness_asset_dir_with_approval_is_launch_ready
FAILED tests/test_prepare_line31_launch_readiness_from_assets.py::test_prepare_launch_readiness_owner_approved_records_evidence
FAILED tests/test_rebuild_sales_fact_v2_size_prefers_assigned_size.py::test_assigned_size_overrides_legacy_my_size
FAILED tests/test_rebuild_sales_fact_v2_size_prefers_assigned_size.py::test_assigned_size_rebuilds_sku_id_after_parser_alias_mapping
FAILED tests/test_report_line31_next_inputs_status.py::test_next_inputs_command_outputs_json
FAILED tests/test_run_webui_archive_full_parse.py::test_run_webui_archive_full_parse_marks_missing_credentials_without_download
FAILED tests/test_sales_fact_v2_builder_grain.py::test_builder_keeps_order_entry_grain_and_totals
FAILED tests/test_sales_fact_v2_builder_grain.py::test_builder_fails_closed_when_identity_missing_in_strict_mode
FAILED tests/test_sales_fact_v2_sale_date_semantics.py::test_sale_date_prefers_status_updated_at
FAILED tests/test_sales_fact_v2_sale_date_semantics.py::test_sale_date_falls_back_when_status_updated_missing
FAILED tests/test_sync_kaspi_orders_enrich_flag.py::test_main_calls_enrichment_for_all_mode
FAILED tests/test_sync_kaspi_orders_enrich_flag.py::test_main_calls_enrichment_for_single_store_mode
FAILED tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_pass
FAILED tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_fails_when_missing
FAILED tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_webui_pass
FAILED tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_webui_fallback_contract_pass
FAILED tests/test_triage_owner_truth_stoplines.py::test_triage_owner_truth_stoplines_db_uses_publication_validation_fallback
FAILED tests/test_validate_inbound_sheet_consistency.py::test_flags_qty_mismatch_between_cargo_and_inbounds
FAILED tests/test_validate_inbound_sheet_consistency.py::test_reports_authoritative_sheet_precedence
FAILED tests/test_validate_inbound_sheet_consistency.py::test_parses_styled_cargo_sheet_layout
FAILED tests/test_validate_inbound_sheet_consistency.py::test_fails_when_no_comparable_cargo_keys_exist
FAILED tests/test_validate_inbound_sheet_consistency.py::test_exit_nonzero_on_contract_breach
FAILED tests/test_validate_inbound_sheet_consistency.py::test_classifies_exact_line61_shortage_as_visible_production_safe_truth
FAILED tests/test_validate_inbound_sheet_consistency.py::test_copied_temp_allowance_passes_only_exact_line61_shortage
FAILED tests/test_validate_opex_readiness.py::test_validate_opex_readiness_pass
FAILED tests/test_validate_returns_economics_audit.py::test_validate_returns_economics_fails_stale_leak
FAILED tests/test_validate_sales_engine_self_sufficient.py::test_self_sufficient_validator_writes_report_and_passes
FAILED tests/test_validate_sales_engine_self_sufficient.py::test_self_sufficient_validator_fails_closed_on_parity_error
FAILED tests/test_validate_sales_engine_self_sufficient.py::test_self_sufficient_validator_allows_unmapped_rows_if_parity_passes
FAILED tests/test_validate_shipped_truth_crm_waybill.py::test_validate_passes_with_cancel_normalization
FAILED tests/test_validate_line31_launch_readiness.py::test_current_line31_evidence_passes_when_pending_creative_is_allowed
FAILED tests/test_validate_line31_launch_readiness.py::test_line31_launch_readiness_commands_do_not_mutate_protected_surfaces
FAILED tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_falls_back_to_repo_quarantine_csv
FAILED tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_falls_back_to_repo_authority_decision
FAILED tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_accepts_workbook_anchor_quarantine_under_crm_authority
FAILED tests/test_validate_webui_archive_bands.py::test_validate_webui_archive_vs_current_db_keeps_workbook_anchor_quarantine_hard_without_crm_authority
FAILED tests/test_waybill_selection_filters.py::test_build_daily_waybills_read_db_orders_filters_status_signature
FAILED tests/test_write_line31_current_launch_status.py::test_current_status_points_to_latest_packet_and_pending_creative
49 failed, 3371 passed, 4 skipped, 1 xfailed, 33 warnings in 264.77s (0:04:24)

```

## check_no_db_tracked

- Command: `bash scripts/check_no_db_tracked.sh`
- Exit code: `0`
- Timed out: `False`
- Last output lines:

```
DB guard OK (no tracked/staged .db files).

bash: warning: setlocale: LC_ALL: cannot change locale (C.UTF-8): No such file or directory
```

## lint_docs

- Command: `bash scripts/lint_docs.sh`
- Exit code: `1`
- Timed out: `False`
- Last output lines:

```
docs/plan/green_path_2026-06/canonical_numbers.csv:28:CN-027,april_100pct_margin_fiction,"April 2026: sales 4,856,291 / COGS 0 / profit 4,856,291 (100% margin) in fact_cashflow_daily; May COGS coverage 11.7%; no June rows at all",KZT,frozen series,VERIFIED,live_reverified,MATCH,V6,fiction intact and un-remediated
docs/plan/green_path_2026-06/green_gates.csv:23:G-COGS-03,profit_cogs,"April 100%-margin fiction corrected per owner restatement decision (restate vs annotate-only); profit publication integrity validator passes",POINT_IN_TIME,"python3 scripts/validate_profit_publication_integrity.py; python3 scripts/validate_monthly_economics_parity.py",exit 0; April margin ≠ 100% or annotated per OD-014,n/a,"RED (4,856,291 @ 100%; CN-027)",INEF-03,OD-014,G-COGS-02,2,WS-PROFIT,HARD,yes (annotate-only path),RB-DB,CN-027

bash: warning: setlocale: LC_ALL: cannot change locale (C.UTF-8): No such file or directory
ERROR: docs lint found banned pattern: \b856\b
Docs lint failed. Remove legacy references in non-archive docs.
```
