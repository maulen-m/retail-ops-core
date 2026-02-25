from __future__ import annotations

from scripts.build_daily_ops_timings import evaluate_timing_budget


def test_timing_budget_contract_passes_under_budget() -> None:
    payload = {
        "runs": [
            {"total_duration_sec": 10.0},
            {"total_duration_sec": 12.0},
        ]
    }
    report = evaluate_timing_budget(payload=payload, max_avg_total_sec=15.0)
    assert report["ok"] is True
    assert report["avg_total_duration_sec"] == 11.0


def test_timing_budget_contract_fails_over_budget() -> None:
    payload = {
        "runs": [
            {"total_duration_sec": 40.0},
            {"total_duration_sec": 44.0},
        ]
    }
    report = evaluate_timing_budget(payload=payload, max_avg_total_sec=30.0)
    assert report["ok"] is False
    assert "budget exceeded" in " ".join(report["errors"]).lower()

