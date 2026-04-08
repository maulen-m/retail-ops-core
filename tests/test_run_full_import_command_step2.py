from pathlib import Path


def _extract_step2_block(script_text: str) -> str:
    marker = "# Step 2: Import new orders to CRM (also updates existing order status columns)"
    start = script_text.index(marker)
    tail = script_text[start:]
    end = tail.index("STEP2_RC=$?")
    return tail[:end]


def _extract_cli_flags(step2_block: str) -> set[str]:
    flags: set[str] = set()
    for line in step2_block.splitlines():
        stripped = line.strip().rstrip("\\").strip()
        if stripped.startswith("--"):
            flags.add(stripped)
    return flags


def test_step2_uses_transactional_strict_xlwings_mode():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "Preflight: validating local app DB..." in text
    assert "python3 scripts/check_local_app_db.py --db-path \"${PROJECT_ROOT}/db/app.db\"" in text
    step2_block = _extract_step2_block(text)
    flags = _extract_cli_flags(step2_block)

    # Keep hard timeout wrapper in place.
    assert 'python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \\' in step2_block
    assert 'CRM_XLWINGS_APPEND_TIMEOUT_SEC="${XLWINGS_APPEND_TIMEOUT_SEC}" \\' in step2_block

    # Step 2 must now write through the transactional + strict Excel path.
    assert "--no-transactional" not in flags
    assert "--no-strict-excel" not in flags
    assert "--no-update" in flags

    # Keep Excel-safe append path first; openpyxl append can corrupt pivot caches.
    assert "--openpyxl-append-fallback" not in flags
    assert "--no-prefer-xlwings-append" not in flags
    assert "--no-append-integrity-check" not in flags
    assert "--allow-large-reconcile-delete" not in flags
    assert "--no-gdrive-sync" in flags

    # Keep no-gui unattended mode and do not rely on env-side toggles.
    assert "--strict-excel" in flags
    assert "CRM_OPENPYXL_APPEND_FALLBACK=1" not in step2_block
    assert 'REFRESH_DELIVERY_FEES="${KASPI_REFRESH_DELIVERY_FEES:-1}"' in text
    assert 'REFRESH_DELIVERY_FLAGS="--refresh-delivery-fees --refresh-fees-from ${REFRESH_FEES_FROM} --refresh-fees-to ${REFRESH_FEES_TO}"' in text
    assert "${REFRESH_DELIVERY_FLAGS}" in step2_block
    assert "--skip-fixed-backfill" not in flags
    assert 'FIXED_BACKFILL_FLAGS="--fixed-backfill-from ${REFRESH_FEES_FROM} --fixed-backfill-to ${REFRESH_FEES_TO}"' in text
    assert "${FIXED_BACKFILL_FLAGS}" in step2_block


def test_step2_append_timeout_default_is_not_overly_aggressive():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)

    # 180s is too low for larger day volumes; keep a safer unattended default.
    assert 'XLWINGS_APPEND_TIMEOUT_SEC="${CRM_XLWINGS_APPEND_TIMEOUT_SEC:-420}"' in step2_block


def test_late_arrival_topup_uses_transactional_strict_xlwings_mode():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    late_marker = 'TOPUP_STEP2_RC=$?'
    topup_block = text[text.index('python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \\', text.index("Late-arrival top-up pass")):text.index(late_marker)]
    flags = _extract_cli_flags(topup_block)

    assert "--no-transactional" not in flags
    assert "--no-strict-excel" not in flags
    assert "--strict-excel" in flags
    assert "--skip-fixed-backfill" not in flags
    assert "${FIXED_BACKFILL_FLAGS}" in topup_block


def test_dotenv_export_skips_shell_invalid_keys():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert 'SHELL_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")' in text
    assert "if not SHELL_KEY_RE.match(key):" in text


def test_command_only_runs_excel_session_preflight_at_write_boundaries():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "run_excel_session_preflight()" in text
    assert "read_import_summary_fields()" in text
    assert "python3 scripts/import_orders_to_crm.py --excel-session-preflight-only" in text
    assert 'run_excel_session_preflight "Preflight: validating Excel session state..."' not in text
    assert text.index(
        'run_excel_session_preflight "Preflight: validating Excel session state before CRM import..."'
    ) < text.index("# Step 2: Import new orders to CRM (also updates existing order status columns)")


def test_step2c_backfill_is_skipped_when_import_is_noop():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "Step 2c: Backfilling Line61 Kaspi_name_core..." in text
    assert "NO-OP: skipping Line61 Kaspi_name_core backfill (no CRM changes)." in text


def test_store-c_zero_orders_does_not_raise_warning_noise():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "MELVIS_RC=$?" in text
    assert "No MELVIS rows found for filter; continuing." in text


def test_step2b_validation_is_skipped_in_no_update_mode():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "STEP2_NO_UPDATE=1" in text
    assert "NO-OP: skipping pending order validation in --no-update mode." in text


def test_step2_failure_skips_backfill_health_and_final_gate():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "STEP2_SKIP_DOWNSTREAM=0" in text
    assert 'if [ "${STEP2_RETRYABLE_TOPUP}" != "1" ]; then' in text
    assert "NO-OP: skipping Line61 Kaspi_name_core backfill (Step 2 did not reach a safe write-complete state)." in text
    assert "NO-OP: skipping pending order validation (Step 2 did not reach a safe write-complete state)." in text
    assert "NO-OP: skipping post-import health report (Step 2 did not reach a safe write-complete state)." in text
    assert "NO-OP: skipping final success gate (Step 2 did not reach a safe write-complete state)." in text


def test_step2_propagates_include_overdue_date_window_flags():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)
    assert 'IMPORT_DATE_FLAGS=""' in text
    assert 'IMPORT_DATE_FLAGS="--include-overdue --overdue-lookback-days ${LOOKBACK_DAYS}"' in text
    assert "${IMPORT_DATE_FLAGS}" in step2_block


def test_step2_final_flag_does_not_accidentally_continue_into_shell_assignments():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)
    lines = step2_block.splitlines()
    last_flag_line = next(line for line in lines[::-1] if "--no-gdrive-sync" in line)
    assert not last_flag_line.rstrip().endswith("\\")


def test_post_import_runs_machine_readable_health_report_and_gate():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "HEALTH_JSON=" in text
    assert "ACTIVEORDERS_SNAPSHOT=" in text
    assert "mktemp -t activeorders_snapshot_" in text
    assert "python3 scripts/report_import_status.py --since-days" in text
    assert "--json-out \"${HEALTH_JSON}\"" in text
    assert "EVAL_CMD=(" in text
    assert "python3 scripts/evaluate_import_run_result.py" in text
    assert "--step2-rc \"${STEP2_RC}\"" in text
    assert "--health-json \"${HEALTH_JSON}\"" in text
    assert "--activeorders-file \"${ACTIVEORDERS_SNAPSHOT}\"" in text
    assert "--crm-file \"excel_ui/SALES_KSP_CRM_V3.xlsx\"" in text
    assert "--target-date \"$(date +%Y-%m-%d)\"" in text


def test_post_import_health_triggers_bounded_late_arrival_topup_before_gate():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert 'LATE_ARRIVAL_RETRY_MAX="${KASPI_LATE_ARRIVAL_RETRY_MAX:-2}"' in text
    assert "Late-arrival top-up pass" in text
    assert 'run_excel_session_preflight "Preflight: validating Excel session state before late-arrival top-up..."' in text
    assert "Post-import health found ${MISS_CRM} live API orders missing in CRM." in text
    assert "Re-exporting ActiveOrders and rerunning CRM import." in text
    assert 'ACTIVEORDERS_SNAPSHOT=$(mktemp -t activeorders_snapshot_' in text
    assert 'cp "excel_ui/ActiveOrders/ActiveOrders.xlsx" "${ACTIVEORDERS_SNAPSHOT}"' in text


def test_post_import_health_also_retries_when_stale_today_rows_remain():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "STALE_CRM=" in text
    assert 'if [ -z "${MISS_CRM}" ] || [ "${MISS_CRM}" -le 0 ]; then' in text
    assert 'if [ -n "${STALE_CRM}" ] && [ "${STALE_CRM}" -gt 0 ]; then' in text
    assert "Post-import health found ${STALE_CRM} stale today rows in CRM." in text
    assert "Re-exporting ActiveOrders and rerunning CRM import." in text


def test_successful_topup_clears_initial_step2_failure_before_final_gate():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "TOPUP_STEP2_RC=$?" in text
    assert 'if [ ${TOPUP_STEP2_RC} -ne 0 ]; then' in text
    assert "STEP2_RC=${TOPUP_STEP2_RC}" in text
    assert "STEP2_RC=0" in text
    assert text.index("STEP2_RC=0") > text.index("TOPUP_STEP2_RC=$?")


def test_late_arrival_topup_final_flag_does_not_accidentally_continue_into_shell_assignments():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    late_marker = 'TOPUP_STEP2_RC=$?'
    topup_block = text[text.index('python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \\', text.index("Late-arrival top-up pass")):text.index(late_marker)]
    lines = topup_block.splitlines()
    last_flag_line = next(line for line in lines[::-1] if "--no-gdrive-sync" in line)
    assert not last_flag_line.rstrip().endswith("\\")


def test_successful_topup_defers_initial_step2_warning_until_final_state_is_known():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert 'STEP2_WARN_MSG=""' in text
    assert 'STEP2_WARN_MSG="CRM import errors. Fix: open CRM and re-run import_orders_to_crm.py --verbose."' in text
    assert 'WARNINGS+=("${STEP2_WARN_MSG}")' in text
    assert text.index('WARNINGS+=("${STEP2_WARN_MSG}")') > text.index("while [")


def test_command_exits_nonzero_on_hard_gate_failure():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "HARD_FAIL=0" in text
    assert "if [ \"${HARD_FAIL}\" -ne 0 ]; then" in text
    assert "exit 1" in text
