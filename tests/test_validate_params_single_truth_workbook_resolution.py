from __future__ import annotations

from pathlib import Path

from scripts import validate_params as vp


def test_resolve_single_truth_workbook_path_prefers_env(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / "inbound_env.xlsx"
    monkeypatch.setenv("AB_INBOUND_WORKBOOK_PATH", str(env_path))

    resolved = vp.resolve_single_truth_workbook_path(project_root=tmp_path)

    assert resolved == env_path


def test_resolve_single_truth_workbook_path_falls_back_to_anchor(tmp_path: Path) -> None:
    expected = tmp_path / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"

    resolved = vp.resolve_single_truth_workbook_path(project_root=tmp_path)

    assert resolved == expected
