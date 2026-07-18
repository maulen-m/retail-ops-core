from __future__ import annotations

import importlib.util
from pathlib import Path
import plistlib

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_scheduler_module():
    scheduler_path = (
        PROJECT_ROOT / "scripts" / "run_operational_stock_daily_truth_scheduler.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_operational_stock_daily_truth_scheduler_contract",
        scheduler_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    environment = plist.get("EnvironmentVariables", {})
    assert "TELEGRAM_BOT_TOKEN" not in environment
    assert "TELEGRAM_CHAT_ID" not in environment


def test_operational_stock_daily_truth_scheduler_is_fail_closed_by_default() -> None:
    scheduler = (
        PROJECT_ROOT / "scripts" / "run_operational_stock_daily_truth_scheduler.py"
    ).read_text(encoding="utf-8")

    assert "AB_OPERATIONAL_STOCK_ALLOW_GREEN_OWNER_OUTPUT" in scheduler
    assert "--allow-green-owner-output" not in scheduler
    assert "run_operational_stock_daily_truth.py" in scheduler
    assert ".venv/bin/python" in scheduler


def test_scheduler_loads_only_allowlisted_secrets_from_protected_env(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TELEGRAM_BOT_TOKEN=test-token-not-a-real-secret\n"
        "TELEGRAM_CHAT_ID=123456\n"
        "UNRELATED_SECRET=must-not-be-exported\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)
    target: dict[str, str] = {}

    loaded = module._load_scheduler_secrets(env_path=env_path, environ=target)

    assert loaded == ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    assert set(target) == {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
    assert "UNRELATED_SECRET" not in target


def test_scheduler_rejects_group_or_world_readable_secret_env(tmp_path: Path) -> None:
    module = _load_scheduler_module()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TELEGRAM_BOT_TOKEN=test-token-not-a-real-secret\n",
        encoding="utf-8",
    )
    env_path.chmod(0o644)
    target: dict[str, str] = {}

    with pytest.raises(RuntimeError, match="must have mode 0600"):
        module._load_scheduler_secrets(env_path=env_path, environ=target)

    assert target == {}


def test_scheduler_secret_loader_never_prints_values(tmp_path: Path, capsys) -> None:
    module = _load_scheduler_module()
    env_path = tmp_path / ".env"
    sentinel = "test-token-must-never-appear"
    env_path.write_text(
        f"TELEGRAM_BOT_TOKEN={sentinel}\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)

    module._load_scheduler_secrets(env_path=env_path, environ={})

    captured = capsys.readouterr()
    assert sentinel not in captured.out
    assert sentinel not in captured.err
