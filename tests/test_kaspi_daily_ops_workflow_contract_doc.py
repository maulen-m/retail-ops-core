from pathlib import Path


def test_daily_ops_workflow_contract_doc_exists_and_maps_critical_paths() -> None:
    doc_path = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md")
    assert doc_path.exists(), "missing daily ops workflow contract doc"

    text = doc_path.read_text(encoding="utf-8")
    assert "excel_ui/run_full_import.command" in text
    assert "excel_ui/run_merged_build_waybills.command" in text
    assert "config/com.example.kaspi-import.plist" in text
    assert "config/com.example.kaspi-waybill-deadline.plist" in text
    assert "config/com.example.waybill-telegram-control.plist" in text
    assert "scripts/waybill_telegram_control_bot.py" in text
    assert "11:00" in text
    assert "15:02" in text
    assert "16:01" in text
    assert "17:02" in text
    assert "18:30" in text
    assert "Telegram /ready" in text
    assert "Telegram /halt" in text
    assert "fail-closed" in text.lower()
    assert "MISSING_PROBABLE_SIZE" in text
    assert "INVALID_PROBABLE_SIZE" in text
    assert "copy-only from visible valid `PROBABLE_SIZE`" in text
    assert "runtime/api_ledger/kaspi_api_<YYYY-MM-DD>.jsonl" in text
    assert "pass the default daily ledger to child processes" in text
    assert "30000001_PP1" in text
    assert "30000002_PP1" in text
    assert "legacy `16:00` cutoff" in text
    assert "normalize `30000001_PP1` to `UNIVERSAL`" in text


def test_daily_ops_workflow_contract_includes_prod_dry_run_checks() -> None:
    text = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")
    assert "scripts/install_single_truth_ops_scheduler.sh --validate-only" in text
    assert "scripts/check_anchor_health.py" in text
    assert "scripts/ops_status.py" in text


def test_daily_ops_workflow_contract_locks_multi_store_scale_roster() -> None:
    text = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")
    assert "Active Daily Polling Roster" in text
    assert "Archived Historical Store Identities" in text
    assert "Universal" in text
    assert "AcmeWear" in text
    assert "11KZ" in text
    assert "Store-C" in text
    assert "STORE-B" in text


def test_daily_ops_workflow_contract_locks_autonomous_shipping_authority() -> None:
    text = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")

    assert "Standing Daily Shipping Authority" in text
    assert "No per-day, per-batch, per-order, carried-order, or Telegram approval phrase" in text
    assert "one-time deployment and activation" in text
    assert "target_date + ready_set_at" in text
    assert "no date or lookback expiry" in text
    assert "required-orders JSON path and SHA-256" in text
    assert "obligation-scope hash" in text
    assert "no recovery path may select a manifest by modification time" in text
    assert "Legacy CRM compatibility only" in text
    assert "does not limit the no-expiry obligation ledger or canonical closeout scope" in text
    assert "schema_version = 2" in text
    assert "schema-v4" in text
    assert "explicit manifest path and raw-file SHA-256" in text
    assert "exact provenance" in text
    assert "channel-wide lock" in text
    assert "zero-order marker" in text
    assert "legacy scheduled slots remain preview-only" in text
