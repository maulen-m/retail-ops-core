from pathlib import Path


def test_merged_waybill_command_uses_dual_output_layout() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--output-layout per-store-and-merged" in text
    assert "PER_STORE/" in text
    assert "MERGED/" in text


def test_merged_waybill_command_keeps_stopline_report() -> None:
    text = Path("excel_ui/run_merged_build_waybills.command").read_text(encoding="utf-8")
    assert "--strict-stopline" in text
