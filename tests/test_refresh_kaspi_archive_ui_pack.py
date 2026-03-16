from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import scripts.refresh_kaspi_archive_ui_pack as mod
from scripts.refresh_kaspi_archive_ui_pack import UiPackRefreshError, refresh_kaspi_archive_ui_pack


def test_refresh_kaspi_archive_ui_pack_requires_seed(tmp_path: Path) -> None:
    anchor = tmp_path / "anchor.json"
    with pytest.raises(UiPackRefreshError):
        refresh_kaspi_archive_ui_pack(
            as_of=date(2026, 3, 4),
            since=date(2025, 6, 6),
            output_root=tmp_path / "exports",
            validation_root=tmp_path / "validation",
            anchor_path=anchor,
            seed_root=None,
            strict=True,
            apply=False,
        )


def test_refresh_kaspi_archive_ui_pack_updates_anchor_in_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir(parents=True, exist_ok=True)
    (seed_root / "UNIVERSAL.xlsx").write_text("xlsx", encoding="utf-8")

    def fake_export(**kwargs):
        out = tmp_path / "exports" / "kaspi_archive_ui_history_2025-06-06_to_2026-03-04_111111"
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps({"since": "2025-06-06", "until": "2026-03-04"}), encoding="utf-8")
        return {"output_dir": str(out)}

    def fake_validate(**kwargs):
        return {"status": "PASS", "ok": True}

    monkeypatch.setattr(mod, "export_kaspi_archive_ui_history", fake_export)
    monkeypatch.setattr(mod, "validate_kaspi_archive_pack_integrity", fake_validate)
    monkeypatch.setenv("ENABLE_ANCHOR_APPLY", "1")

    anchor = tmp_path / "anchor.json"
    report = refresh_kaspi_archive_ui_pack(
        as_of=date(2026, 3, 4),
        since=date(2025, 6, 6),
        output_root=tmp_path / "exports",
        validation_root=tmp_path / "validation",
        anchor_path=anchor,
        seed_root=seed_root,
        strict=True,
        apply=True,
    )
    assert report["status"] == "PASS"
    assert report["anchor_updated"] is True
    payload = json.loads(anchor.read_text(encoding="utf-8"))
    assert payload["pack_root"]
