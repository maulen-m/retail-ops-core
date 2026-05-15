from __future__ import annotations

from pathlib import Path
import plistlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_operational_stock_daily_truth_plist_uses_repo_venv_interpreter() -> None:
    plist_path = PROJECT_ROOT / "config" / "com.example.operational-stock-daily-truth.plist"
    assert plist_path.exists(), "missing operational stock daily truth launchd plist"

    plist = plistlib.loads(plist_path.read_bytes())
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.operational-stock-daily-truth"
    assert args[0] == "~/Docs/Autonomous_business/.venv/bin/python"
    assert args[1] == "~/Docs/Autonomous_business/scripts/run_operational_stock_daily_truth_scheduler.py"
    assert "/usr/bin/env" not in args
    assert "/usr/bin/python3" not in args


def test_operational_stock_daily_truth_scheduler_is_fail_closed_by_default() -> None:
    scheduler = (
        PROJECT_ROOT / "scripts" / "run_operational_stock_daily_truth_scheduler.py"
    ).read_text(encoding="utf-8")

    assert "AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT" in scheduler
    assert "--allow-green-owner-output" not in scheduler
    assert "run_operational_stock_daily_truth.py" in scheduler
    assert ".venv/bin/python" in scheduler
