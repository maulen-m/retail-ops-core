from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from core.ads.sidecar_contract import resolve_ads_db_path, validate_ads_source


def test_resolve_ads_db_path_fails_closed_when_env_path_missing(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing_ads.db"
    monkeypatch.setenv("AB_ADS_DB_PATH", str(missing))

    with pytest.raises(RuntimeError):
        resolve_ads_db_path(require_exists=True)


def test_validate_ads_source_flags_stale_file(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    ads_db.write_text("stub", encoding="utf-8")
    old_epoch = time.time() - (72 * 3600)
    os.utime(ads_db, (old_epoch, old_epoch))

    report = validate_ads_source(ads_db, max_age_hours=36)
    assert report["ok"] is False
    assert report["reason"] == "stale"


def test_validate_ads_source_passes_for_fresh_file(tmp_path: Path) -> None:
    ads_db = tmp_path / "ads.db"
    ads_db.write_text("stub", encoding="utf-8")

    report = validate_ads_source(ads_db, max_age_hours=36)
    assert report["ok"] is True
    assert report["reason"] == "ok"
