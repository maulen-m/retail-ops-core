from __future__ import annotations

from pathlib import Path

from scripts import validate_single_truth_system as sts


def test_resolve_workbook_path_prefers_explicit_argument(monkeypatch) -> None:
    explicit = Path("/tmp/explicit.xlsx")
    monkeypatch.setenv("AB_INBOUND_WORKBOOK_PATH", "/tmp/env.xlsx")

    resolved = sts.resolve_workbook_path(explicit)

    assert resolved == explicit


def test_resolve_workbook_path_uses_env_when_explicit_missing(monkeypatch) -> None:
    monkeypatch.setenv("AB_INBOUND_WORKBOOK_PATH", "/tmp/inbound_env.xlsx")

    resolved = sts.resolve_workbook_path(None)

    assert resolved == Path("/tmp/inbound_env.xlsx")


def test_default_workbook_points_to_inbound_anchor() -> None:
    assert str(sts.DEFAULT_WORKBOOK).endswith("config/anchors/INBOUND_CALENDAR_LATEST.xlsx")
