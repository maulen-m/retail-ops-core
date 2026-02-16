from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = PROJECT_ROOT / "docs" / "ops" / "RUNBOOK_KASPI_ADS_HOURLY.md"


def test_runbook_references_stable_ads_log_paths() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")
    expected_logs = [
        "logs/hourly_snapshot_stdout.log",
        "logs/hourly_snapshot_stderr.log",
        "logs/kaspi_ads_healthcheck_stdout.log",
        "logs/kaspi_ads_healthcheck_stderr.log",
        "logs/kaspi_ads_coverage_stdout.log",
        "logs/kaspi_ads_coverage_stderr.log",
        "logs/kaspi_ads_daily_brief_stdout.log",
        "logs/kaspi_ads_daily_brief_stderr.log",
    ]
    for item in expected_logs:
        assert item in content


def test_runbook_references_launchd_labels_and_plists() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")
    expected_labels = [
        "com.example.kaspi-marketing-hourly",
        "com.example.kaspi-marketing-healthcheck",
        "com.example.kaspi-marketing-coverage",
        "com.example.kaspi-marketing-daily-brief",
    ]
    expected_plists = [
        "config/com.example.kaspi-marketing-hourly.plist",
        "config/com.example.kaspi-marketing-healthcheck.plist",
        "config/com.example.kaspi-marketing-coverage.plist",
        "config/com.example.kaspi-marketing-daily-brief.plist",
    ]
    for item in expected_labels + expected_plists:
        assert item in content


def test_runbook_includes_recommended_schedule_sections() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")
    assert "Recommended Schedule" in content
    assert "Hourly pipeline" in content
    assert "Daily healthcheck/trust loop" in content
    assert "Daily brief generation" in content


def test_runbook_includes_single_command_trust_loop() -> None:
    content = RUNBOOK.read_text(encoding="utf-8")
    assert "Single-Command Daily Trust Loop" in content
    assert "scripts/kaspi_ads_daily_trust_loop.py" in content
    assert "reports/marketing/trust_loop/kaspi_ads_daily_trust_loop_latest.json" in content
