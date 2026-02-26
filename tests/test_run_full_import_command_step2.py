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


def test_step2_uses_unattended_safe_xlwings_first_mode():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "Preflight: validating local app DB..." in text
    assert "python3 scripts/check_local_app_db.py --db-path \"${PROJECT_ROOT}/db/app.db\"" in text
    step2_block = _extract_step2_block(text)
    flags = _extract_cli_flags(step2_block)

    # Keep hard timeout wrapper in place.
    assert 'python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \\' in step2_block
    assert 'CRM_XLWINGS_APPEND_TIMEOUT_SEC="${XLWINGS_APPEND_TIMEOUT_SEC}" \\' in step2_block

    # Unattended mode: avoid candidate writes and keep strict probe disabled.
    assert "--no-transactional" in flags
    assert "--no-strict-excel" in flags
    assert "--no-update" in flags

    # Keep Excel-safe append path first; openpyxl append can corrupt pivot caches.
    assert "--openpyxl-append-fallback" not in flags
    assert "--no-prefer-xlwings-append" not in flags
    assert "--no-append-integrity-check" in flags
    assert "--no-gdrive-sync" in flags

    # Keep no-gui unattended mode and do not rely on env-side toggles.
    assert "--strict-excel" not in flags
    assert "CRM_OPENPYXL_APPEND_FALLBACK=1" not in step2_block
    assert "--refresh-delivery-fees" not in flags


def test_step2_append_timeout_default_is_not_overly_aggressive():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)

    # 180s is too low for larger day volumes; keep a safer unattended default.
    assert 'XLWINGS_APPEND_TIMEOUT_SEC="${CRM_XLWINGS_APPEND_TIMEOUT_SEC:-420}"' in step2_block


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


def test_step2_propagates_include_overdue_date_window_flags():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)
    assert 'IMPORT_DATE_FLAGS=""' in text
    assert 'IMPORT_DATE_FLAGS="--include-overdue --overdue-lookback-days ${LOOKBACK_DAYS}"' in text
    assert "${IMPORT_DATE_FLAGS}" in step2_block


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


def test_command_exits_nonzero_on_hard_gate_failure():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    assert "HARD_FAIL=0" in text
    assert "if [ \"${HARD_FAIL}\" -ne 0 ]; then" in text
    assert "exit 1" in text
