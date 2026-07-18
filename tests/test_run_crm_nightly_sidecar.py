from __future__ import annotations

from pathlib import Path
import plistlib

from scripts import run_crm_nightly_sidecar as sidecar


def _touch_required(monkeypatch, tmp_path: Path) -> None:
    for name in ("python", "import.py", "timeout.py", "ActiveOrders.xlsx", "CRM.xlsx"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(sidecar, "PYTHON", tmp_path / "python")
    monkeypatch.setattr(sidecar, "IMPORT_SCRIPT", tmp_path / "import.py")
    monkeypatch.setattr(sidecar, "TIMEOUT_SCRIPT", tmp_path / "timeout.py")
    monkeypatch.setattr(sidecar, "ACTIVEORDERS_PATH", tmp_path / "ActiveOrders.xlsx")
    monkeypatch.setattr(sidecar, "CRM_WORKBOOK_PATH", tmp_path / "CRM.xlsx")
    monkeypatch.setattr(sidecar, "SUMMARY_PATH", tmp_path / "summary.json")


def test_apply_requires_explicit_environment_gate(monkeypatch, tmp_path: Path) -> None:
    _touch_required(monkeypatch, tmp_path)
    monkeypatch.delenv(sidecar.APPLY_ENV_GATE, raising=False)
    monkeypatch.setattr(sidecar.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    assert sidecar.main(["--apply"]) == 78


def test_dry_run_is_crm_only_and_never_uses_shipping_or_google_commands(monkeypatch, tmp_path: Path) -> None:
    _touch_required(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    class Result:
        returncode = 0

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return Result()

    monkeypatch.setattr(sidecar.subprocess, "run", fake_run)

    assert sidecar.main([]) == 0
    assert len(calls) == 2
    assert calls[0][-1] == "--excel-session-preflight-only"
    assert "--dry-run" in calls[1]
    joined = " ".join(calls[1])
    assert "sync_google_ops_board" not in joined
    assert "sync_crm_to_db" not in joined
    assert "telegram" not in joined.lower()


def test_apply_runs_guarded_writer_without_dry_run(monkeypatch, tmp_path: Path) -> None:
    _touch_required(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    class Result:
        returncode = 0

    monkeypatch.setenv(sidecar.APPLY_ENV_GATE, "1")
    monkeypatch.setattr(
        sidecar.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(list(command)) or Result(),
    )

    assert sidecar.main(["--apply", "--timeout-seconds", "90"]) == 0
    assert "--dry-run" not in calls[1]
    assert calls[1][calls[1].index("--timeout") + 1] == "90"


def test_default_timeout_covers_bounded_full_workbook_readback(monkeypatch, tmp_path: Path) -> None:
    _touch_required(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    class Result:
        returncode = 0

    monkeypatch.setattr(
        sidecar.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(list(command)) or Result(),
    )

    assert sidecar.main([]) == 0
    assert sidecar.DEFAULT_TIMEOUT_SECONDS == 2700
    assert calls[1][calls[1].index("--timeout") + 1] == "2700"


def test_crm_nightly_sidecar_plist_is_isolated_and_guarded() -> None:
    payload = plistlib.loads(Path("config/com.example.kaspi-crm-nightly-sidecar.plist").read_bytes())
    assert payload["Label"] == "com.example.kaspi-crm-nightly-sidecar"
    assert payload["StartCalendarInterval"] == {"Hour": 0, "Minute": 30}
    assert payload["ProgramArguments"][-1] == "--apply"
    assert payload["EnvironmentVariables"][sidecar.APPLY_ENV_GATE] == "1"
    assert not any("GOOGLE" in key or "TELEGRAM" in key for key in payload["EnvironmentVariables"])
