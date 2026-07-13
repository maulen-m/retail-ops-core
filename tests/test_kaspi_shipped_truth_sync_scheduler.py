from __future__ import annotations

import json
import plistlib
from datetime import date
from pathlib import Path

from scripts import run_kaspi_shipped_truth_sync_scheduler as mod


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_shipped_truth_sync_plist_contract() -> None:
    plist_path = Path("config/com.example.kaspi-shipped-truth-sync.plist")
    assert plist_path.exists()
    plist = plistlib.loads(plist_path.read_bytes())
    intervals = plist.get("StartCalendarInterval", [])
    pairs = sorted((int(item["Hour"]), int(item["Minute"])) for item in intervals)
    env = plist.get("EnvironmentVariables", {})
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.kaspi-shipped-truth-sync"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"
    assert pairs == [(9, 30), (19, 15)]
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_kaspi_shipped_truth_sync_scheduler.py",
    ]
    assert env.get("ENABLE_KASPI_SHIPPED_TRUTH_SYNC") == "1"
    assert plist.get("StandardOutPath") == (
        "~/Docs/Autonomous_business/runtime_logs/kaspi_shipped_truth_sync_stdout.log"
    )
    assert plist.get("StandardErrorPath") == (
        "~/Docs/Autonomous_business/runtime_logs/kaspi_shipped_truth_sync_stderr.log"
    )


def test_shipped_truth_sync_scheduler_runs_db_only_kaspi_status_sync(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_text("not sqlite, summary is stubbed", encoding="utf-8")
    sync_path = tmp_path / "scripts" / "sync_kaspi_orders.py"
    db_check_path = tmp_path / "scripts" / "check_local_app_db.py"
    sync_path.parent.mkdir(parents=True)
    sync_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    db_check_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    json_out = tmp_path / "sync_report.json"
    child_calls: list[dict[str, object]] = []

    def fake_run(command, cwd, env, text=False, capture_output=False):
        child_calls.append({"command": list(command), "cwd": str(cwd), "env": dict(env)})
        return _Result(stdout="ok\n")

    monkeypatch.delenv("KASPI_API_CALL_LEDGER_PATH", raising=False)
    monkeypatch.delenv("KASPI_API_CALL_LEDGER", raising=False)
    monkeypatch.setenv("ENABLE_KASPI_SHIPPED_TRUTH_SYNC", "1")
    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SYNC_KASPI_ORDERS_PATH", sync_path)
    monkeypatch.setattr(mod, "DB_CHECK_PATH", db_check_path)
    monkeypatch.setattr(mod, "_db_shipped_summary", lambda _db_path: {"max_shipped_at": "", "row_count": 0})
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    rc = mod.main(
        [
            "--target-date",
            "2026-04-22",
            "--lookback-days",
            "7",
            "--db-path",
            str(db_path),
            "--json-out",
            str(json_out),
            "--reason",
            "test",
        ]
    )

    assert rc == 0
    assert len(child_calls) == 2
    db_check_command = child_calls[0]["command"]
    sync_command = child_calls[1]["command"]
    assert str(db_check_path) in db_check_command
    assert str(sync_path) in sync_command
    assert "--all" in sync_command
    assert "--since" in sync_command
    assert sync_command[sync_command.index("--since") + 1] == "2026-04-16"
    assert "--states" in sync_command
    assert sync_command[sync_command.index("--states") + 1] == "KASPI_DELIVERY,ARCHIVE"
    joined = " ".join(sync_command)
    assert "import_orders_to_crm" not in joined
    assert "sync_google_ops_board" not in joined
    assert "ActiveOrders" not in joined
    assert child_calls[1]["env"]["KASPI_API_CALL_LEDGER_PATH"] == str(
        tmp_path / "runtime" / "api_ledger" / "kaspi_api_2026-04-22.jsonl"
    )

    report = json.loads(json_out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["target_date"] == "2026-04-22"
    assert report["states"] == ["KASPI_DELIVERY", "ARCHIVE"]
    assert report["reason"] == "test"


def test_shipped_truth_sync_scheduler_blocks_without_apply_gate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ENABLE_KASPI_SHIPPED_TRUTH_SYNC", raising=False)
    monkeypatch.setattr(mod, "today_almaty", lambda: date(2026, 4, 22))

    rc = mod.main(
        [
            "--target-date",
            "2026-04-22",
            "--json-out",
            str(tmp_path / "blocked.json"),
        ]
    )

    assert rc == 78
