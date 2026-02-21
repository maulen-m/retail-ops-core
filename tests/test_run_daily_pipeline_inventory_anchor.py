from __future__ import annotations

from pathlib import Path

import pytest

from scripts import run_daily_pipeline


def test_step_ingest_inventory_prefers_stock_anchor_over_legacy_glob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "repo"
    project.mkdir(parents=True, exist_ok=True)
    (project / "excel").mkdir(parents=True, exist_ok=True)
    (project / "config" / "anchors").mkdir(parents=True, exist_ok=True)

    legacy = project / "excel" / "Current_stock_2026-02-01.xlsx"
    legacy.write_bytes(b"legacy")
    stock = project / "excel" / "stock_snapshot_19.2.2026.xlsx"
    stock.write_bytes(b"stock")
    (project / "config" / "anchors" / "STOCK_SNAPSHOT_LATEST.xlsx").symlink_to(stock)

    captured: dict = {}

    def _fake_ingest_inventory(*, filepath: str, snapshot_date: str, dry_run: bool, verbose: bool):
        captured["filepath"] = filepath
        captured["snapshot_date"] = snapshot_date
        captured["dry_run"] = dry_run
        captured["verbose"] = verbose
        return {"ok": True}

    monkeypatch.chdir(project)
    monkeypatch.setattr("scripts.ingest_inventory_snapshot.ingest_inventory", _fake_ingest_inventory)

    result = run_daily_pipeline.step_ingest_inventory(
        inventory_file=None,
        date="2026-02-19",
        dry_run=True,
        verbose=False,
    )

    assert result == {"ok": True}
    assert captured["filepath"] == "config/anchors/STOCK_SNAPSHOT_LATEST.xlsx"
    assert captured["snapshot_date"] == "2026-02-19"
