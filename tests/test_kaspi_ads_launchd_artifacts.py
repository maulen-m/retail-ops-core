from __future__ import annotations

import plistlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_plist(path: Path) -> dict:
    with path.open("rb") as fh:
        payload = plistlib.load(fh)
    assert isinstance(payload, dict)
    return payload


def test_hourly_launchd_contract() -> None:
    path = PROJECT_ROOT / "config" / "com.example.kaspi-marketing-hourly.plist"
    payload = _load_plist(path)

    assert payload["Label"] == "com.example.kaspi-marketing-hourly"
    start = payload["StartCalendarInterval"]
    assert isinstance(start, list)
    assert len(start) == 24
    hours = sorted(int(item["Hour"]) for item in start)
    minutes = {int(item["Minute"]) for item in start}
    assert hours == list(range(24))
    assert minutes == {5}

    argv = payload["ProgramArguments"]
    rendered = " ".join(str(x) for x in argv)
    assert "~/Docs/Autonomous_business__wt_ads_v1/" in rendered
    assert "kaspi_ads_hourly_pipeline.py" in rendered
    assert "--ads-db" in rendered
    assert "--stores-config" in rendered
    assert "--env-file" in rendered

    assert payload["StandardOutPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/hourly_snapshot_stdout.log"
    assert payload["StandardErrorPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/hourly_snapshot_stderr.log"


def test_daily_healthcheck_launchd_contract() -> None:
    path = PROJECT_ROOT / "config" / "com.example.kaspi-marketing-healthcheck.plist"
    payload = _load_plist(path)

    assert payload["Label"] == "com.example.kaspi-marketing-healthcheck"
    start = payload["StartCalendarInterval"]
    assert int(start["Hour"]) == 6
    assert int(start["Minute"]) == 20

    rendered = " ".join(str(x) for x in payload["ProgramArguments"])
    assert "kaspi_ads_healthcheck.py" in rendered
    assert "--ads-db" in rendered
    assert "--stores-config" in rendered
    assert "--require-recon-rows" in rendered
    assert "~/Docs/Autonomous_business__wt_ads_v1/" in rendered

    assert payload["StandardOutPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_healthcheck_stdout.log"
    assert payload["StandardErrorPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_healthcheck_stderr.log"


def test_daily_coverage_launchd_contract() -> None:
    path = PROJECT_ROOT / "config" / "com.example.kaspi-marketing-coverage.plist"
    payload = _load_plist(path)

    assert payload["Label"] == "com.example.kaspi-marketing-coverage"
    start = payload["StartCalendarInterval"]
    assert int(start["Hour"]) == 6
    assert int(start["Minute"]) == 25

    rendered = " ".join(str(x) for x in payload["ProgramArguments"])
    assert "kaspi_ads_campaign_coverage_report.py" in rendered
    assert "--out" in rendered
    assert "reports/marketing/trust_loop/kaspi_ads_campaign_coverage_latest.json" in rendered
    assert "~/Docs/Autonomous_business__wt_ads_v1/" in rendered

    assert payload["StandardOutPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_coverage_stdout.log"
    assert payload["StandardErrorPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_coverage_stderr.log"


def test_daily_brief_launchd_contract() -> None:
    path = PROJECT_ROOT / "config" / "com.example.kaspi-marketing-daily-brief.plist"
    payload = _load_plist(path)

    assert payload["Label"] == "com.example.kaspi-marketing-daily-brief"
    start = payload["StartCalendarInterval"]
    assert int(start["Hour"]) == 6
    assert int(start["Minute"]) == 40

    rendered = " ".join(str(x) for x in payload["ProgramArguments"])
    assert "kaspi_ads_elasticity.py" in rendered
    assert "--out-dir" in rendered
    assert "reports/marketing/daily_brief" in rendered
    assert "~/Docs/Autonomous_business__wt_ads_v1/" in rendered

    assert payload["StandardOutPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_daily_brief_stdout.log"
    assert payload["StandardErrorPath"] == "~/Docs/Autonomous_business__wt_ads_v1/logs/kaspi_ads_daily_brief_stderr.log"
