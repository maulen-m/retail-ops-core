from pathlib import Path
import plistlib


def _read_plist(name: str) -> dict:
    path = Path(f"config/{name}")
    assert path.exists(), f"missing launchd plist: {name}"
    return plistlib.loads(path.read_bytes())


def test_google_ops_board_publish_plist_contract() -> None:
    plist = _read_plist("com.example.google-ops-board-publish.plist")
    intervals = plist.get("StartCalendarInterval", [])
    pairs = sorted((int(item["Hour"]), int(item["Minute"])) for item in intervals)
    env = plist.get("EnvironmentVariables", {})
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.google-ops-board-publish"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"
    assert pairs == [
        (14, 1), (14, 11), (14, 21), (14, 31), (14, 41), (14, 51),
        (15, 1), (15, 11), (15, 21), (15, 31), (15, 41), (15, 51),
        (16, 1), (16, 11), (16, 21), (16, 31), (16, 41), (16, 51),
        (17, 1), (17, 11),
    ]
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_google_ops_board_publish_scheduler.py",
    ]
    assert env.get("ENABLE_GOOGLE_OPS_BOARD_WRITE") == "1"
    assert env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") == "~/Docs/Business/S/ab-ops-board-sync-key.json"
    assert env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") == "1zCKXkD7Ch8izX3CF_OwMgNb8pdrMLQOyw2clxbjF9Bg"
    assert plist.get("StandardOutPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_publish_stdout.log"
    )
    assert plist.get("StandardErrorPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_publish_stderr.log"
    )


def test_google_ops_board_size_writeback_plist_contract() -> None:
    plist = _read_plist("com.example.google-ops-board-size-writeback.plist")
    intervals = plist.get("StartCalendarInterval", [])
    env = plist.get("EnvironmentVariables", {})
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.google-ops-board-size-writeback"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"
    pairs = sorted((int(item["Hour"]), int(item["Minute"])) for item in intervals)
    assert pairs == [
        (17, 15), (17, 30), (17, 45),
        (18, 0), (18, 15),
    ]
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_google_ops_board_size_writeback_scheduler.py",
    ]
    assert env.get("ENABLE_GOOGLE_OPS_BOARD_DB_WRITE") == "1"
    assert env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") == "~/Docs/Business/S/ab-ops-board-sync-key.json"
    assert env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") == "1zCKXkD7Ch8izX3CF_OwMgNb8pdrMLQOyw2clxbjF9Bg"
    assert plist.get("StandardOutPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_size_writeback_stdout.log"
    )
    assert plist.get("StandardErrorPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_size_writeback_stderr.log"
    )


def test_google_ops_board_closeout_watch_plist_contract() -> None:
    plist = _read_plist("com.example.google-ops-board-closeout-watch.plist")
    env = plist.get("EnvironmentVariables", {})
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.google-ops-board-closeout-watch"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"
    assert plist.get("StartInterval") == 60
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_google_ops_board_closeout_watch_scheduler.py",
    ]
    assert env.get("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT") == "1"
    assert env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") == "~/Docs/Business/S/ab-ops-board-sync-key.json"
    assert env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") == "1zCKXkD7Ch8izX3CF_OwMgNb8pdrMLQOyw2clxbjF9Bg"
    assert plist.get("StandardOutPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_closeout_watch_stdout.log"
    )
    assert plist.get("StandardErrorPath") == (
        "~/Docs/Autonomous_business/runtime_logs/google_ops_board_closeout_watch_stderr.log"
    )


def test_waybill_deadline_plist_now_points_to_google_ops_closeout() -> None:
    plist = _read_plist("com.example.kaspi-waybill-deadline.plist")
    env = plist.get("EnvironmentVariables", {})
    args = plist.get("ProgramArguments", [])

    assert plist.get("Label") == "com.example.kaspi-waybill-deadline"
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_google_ops_board_closeout_scheduler.py",
    ]
    assert env.get("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT") == "1"
    assert env.get("AB_GOOGLE_SERVICE_ACCOUNT_JSON") == "~/Docs/Business/S/ab-ops-board-sync-key.json"
    assert env.get("AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID") == "1zCKXkD7Ch8izX3CF_OwMgNb8pdrMLQOyw2clxbjF9Bg"


def test_google_ops_board_contract_doc_and_installer_are_in_sync() -> None:
    doc = Path("docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md").read_text(encoding="utf-8")
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")

    assert "14:01" in doc
    assert "every 10 minutes" in doc
    assert "immediate after successful import" in doc
    assert "17:15" in doc
    assert "18:30" in doc
    assert "every `60` seconds" in doc
    assert "90" in doc
    assert "Run_Control" in doc
    assert "READY" in doc
    assert "upsert-preserve" in doc
    assert "next-day rollover" in doc
    assert "protected sheets" in doc or "managed protected sheets" in doc
    assert "com.example.google-ops-board-publish.plist" in script
    assert "com.example.google-ops-board-size-writeback.plist" in script
    assert "com.example.google-ops-board-closeout-watch.plist" in script
    assert "immediate after successful import - Google Ops Board publish" in script
    assert "14:01 to 17:11 every 10 minutes - Google Ops Board publish backstop" in script
    assert "17:15, 17:30, 17:45, 18:00, 18:15 - Google Ops Board size writeback" in script
    assert "every 60s between 11:00 and 18:29 (script-gated, 90s READY debounce) - Google Ops Board early-ready closeout watch" in script
    assert "18:30 - Google Ops Board closeout backstop" in script
