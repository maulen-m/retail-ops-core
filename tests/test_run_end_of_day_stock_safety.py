from __future__ import annotations

from pathlib import Path


def test_end_of_day_never_auto_clamps_negative_stock() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_end_of_day.py"
    ).read_text(encoding="utf-8")
    stock_step = source.split('script="clamp_negative_ledger.py"', 1)[0].rsplit(
        "PipelineStep(", 1
    )[1]
    stock_step += source.split('script="clamp_negative_ledger.py"', 1)[1].split(
        "),", 1
    )[0]

    assert "Audit Negative Ledger (no writes)" in stock_step
    assert '"--apply"' not in stock_step
    assert '"--force"' not in stock_step
