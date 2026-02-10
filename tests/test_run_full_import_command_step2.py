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


def test_step2_uses_direct_write_mode_without_candidate_openpyxl_fallback():
    script_path = Path("excel_ui/run_full_import.command")
    text = script_path.read_text(encoding="utf-8")
    step2_block = _extract_step2_block(text)
    flags = _extract_cli_flags(step2_block)

    # Keep hard timeout wrapper in place.
    assert 'python3 scripts/run_with_timeout.py --timeout "${STEP2_TIMEOUT_SEC}" -- \\' in step2_block

    # Option 3 contract: no transactional candidate workbook path, strict Excel preflight.
    assert "--no-transactional" in flags
    assert "--strict-excel" in flags
    assert "--openpyxl-append-fallback" in flags
    assert "--no-prefer-xlwings-append" in flags

    # Avoid permissive runtime modes that masked append failures.
    assert "--no-strict-excel" not in flags
    assert "--no-append-integrity-check" not in flags
    assert "CRM_OPENPYXL_APPEND_FALLBACK=1" not in step2_block
