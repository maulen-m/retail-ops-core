from pathlib import Path


def test_daily_ops_workflow_contract_doc_exists_and_maps_critical_paths() -> None:
    doc_path = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md")
    assert doc_path.exists(), "missing daily ops workflow contract doc"

    text = doc_path.read_text(encoding="utf-8")
    assert "excel_ui/run_full_import.command" in text
    assert "excel_ui/run_build_waybills.command" in text
    assert "config/com.example.kaspi-import.plist" in text
    assert "config/com.example.kaspi-waybill-deadline.plist" in text
    assert "11:00" in text
    assert "16:03" in text
    assert "18:30" in text
    assert "fail-closed" in text.lower()
