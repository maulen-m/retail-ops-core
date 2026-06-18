from __future__ import annotations

import json
from pathlib import Path
import plistlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_line31_spend_vs_stock_guard_plist_contract() -> None:
    plist_path = PROJECT_ROOT / "config" / "com.example.line31-spend-vs-stock-guard.plist"
    assert plist_path.exists(), "missing LINE31 spend-vs-stock guard plist"

    plist = plistlib.loads(plist_path.read_bytes())
    args = plist.get("ProgramArguments", [])
    interval = plist.get("StartCalendarInterval", {})

    assert plist.get("Label") == "com.example.line31-spend-vs-stock-guard"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"
    assert args == [
        "/bin/bash",
        "~/Docs/Autonomous_business/scripts/run_line31_spend_vs_stock_guard.sh",
    ]
    assert int(interval.get("Hour", -1)) == 6
    assert int(interval.get("Minute", -1)) == 10
    assert plist.get("RunAtLoad") is False


def test_line31_spend_vs_stock_wrapper_is_strict_and_repo_local() -> None:
    wrapper = (PROJECT_ROOT / "scripts" / "run_line31_spend_vs_stock_guard.sh").read_text(
        encoding="utf-8"
    )

    assert "~/Docs/Autonomous_business" in wrapper
    assert "scripts/report_line31_spend_vs_stock_guard.py" in wrapper
    assert "--strict" in wrapper
    assert "--json" in wrapper
    assert "load_dotenv" not in wrapper


def test_line31_spend_vs_stock_manifest_scope_is_not_daily_ops() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / "config" / "business_automation_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    daily = set(manifest["scopes"]["daily-ops"]["labels"])
    all_business = set(manifest["scopes"]["all-business"]["labels"])
    labels = {row["label"]: row for row in manifest["labels"]}

    assert "com.example.line31-spend-vs-stock-guard" not in daily
    assert "com.example.line31-spend-vs-stock-guard" in all_business
    assert labels["com.example.line31-spend-vs-stock-guard"]["risk"] == [
        "production_db_read_possible"
    ]
