from pathlib import Path


def test_daily_ops_workflow_contract_doc_exists_and_maps_critical_paths() -> None:
    doc_path = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md")
    assert doc_path.exists(), "missing daily ops workflow contract doc"

    text = doc_path.read_text(encoding="utf-8")
    assert "excel_ui/run_full_import.command" in text
    assert "excel_ui/run_merged_build_waybills.command" in text
    assert "config/com.example.kaspi-import.plist" in text
    assert "config/com.example.kaspi-waybill-deadline.plist" in text
    assert "11:00" in text
    assert "16:03" in text
    assert "18:30" in text
    assert "fail-closed" in text.lower()


def test_daily_ops_workflow_contract_includes_prod_dry_run_checks() -> None:
    text = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")
    assert "scripts/install_single_truth_ops_scheduler.sh --validate-only" in text
    assert "scripts/check_anchor_health.py" in text
    assert "scripts/ops_status.py" in text


def test_daily_ops_workflow_contract_locks_multi_store_scale_roster() -> None:
    text = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")
    assert "Multi-Store Scale Roster" in text
    assert "Universal" in text
    assert "AcmeWear" in text
    assert "11KZ" in text
    assert "Store-C" in text
    assert "STORE-B" in text
