from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import run_backup_push_nightly as nightly


def _prepare_helper(tmp_path: Path, monkeypatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "backup_push.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(nightly, "PROJECT_ROOT", tmp_path)


def test_backup_push_failure_enqueues_local_only_warn(tmp_path: Path, monkeypatch) -> None:
    _prepare_helper(tmp_path, monkeypatch)
    monkeypatch.setattr(
        nightly.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=3,
            stdout="",
            stderr="push failed\n",
        ),
    )
    alerts: list[dict] = []
    monkeypatch.setattr(
        nightly,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or True,
    )

    result = nightly.run_backup_push("nightly test")

    assert result == 3
    assert alerts[0]["severity"] == "WARN"
    assert alerts[0]["local_only"] is True
    assert alerts[0]["dedup_key"] == "git_governance:nightly_backup_push_failed"


def test_backup_push_success_does_not_warn(tmp_path: Path, monkeypatch) -> None:
    _prepare_helper(tmp_path, monkeypatch)
    monkeypatch.setattr(
        nightly.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="pushed\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        nightly,
        "enqueue_alert",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected alert")),
    )

    assert nightly.run_backup_push("nightly test") == 0
