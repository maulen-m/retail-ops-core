from pathlib import Path


def test_exchange_import_scheduler_is_6h():
    plist = Path("config/com.example.exchange-import.plist").read_text(encoding="utf-8")
    assert "<key>StartInterval</key>" in plist
    assert "<integer>21600</integer>" in plist


def test_exchange_import_runner_uses_autopilot_and_bank_sync():
    script = Path("scripts/run_exchange_imports.sh").read_text(encoding="utf-8")
    assert "scripts/transfer_ledger_autopilot.py" in script
    assert "--skip-emails" in script
    assert "--report-days 0" in script
    assert "scripts/sync_universal_usdt_balance.py" in script


def test_exchange_import_runner_loads_env():
    script = Path("scripts/run_exchange_imports.sh").read_text(encoding="utf-8")
    assert "scripts/load_dotenv.sh" in script
    assert "load_dotenv \"$ROOT_DIR/.env\"" in script
