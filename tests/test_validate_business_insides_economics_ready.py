from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_business_insides_economics_ready import (
    validate_business_insides_economics_ready,
)


def _write_snapshot(path: Path, as_of: str, *, cogs=None, profit=None) -> None:
    payload = {
        "as_of": as_of,
        "performance": {
            "avg_30d_cogs_kzt": cogs,
            "avg_30d_profit_kzt": profit,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_economics_ready_passes_when_gaps_are_volatile_and_locked(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    metrics = {
        "economics_missing_days": ["2026-02-26"],
        "economics_missing_nonvolatile_days": [],
        "economics_volatility_days": 14,
        "profit_publication_locked": True,
    }
    report = validate_business_insides_economics_ready(
        db_path=tmp_path / "app.db",
        as_of=as_of,
        output_root=tmp_path / "out",
        business_dir=business_dir,
        snapshot_json_path=snapshot_json,
        strict=True,
        metrics_override=metrics,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_economics_ready_fails_when_missing_days_not_locked(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=10.0, profit=20.0)

    metrics = {
        "economics_missing_days": ["2026-02-26"],
        "economics_missing_nonvolatile_days": [],
        "economics_volatility_days": 14,
        "profit_publication_locked": False,
    }
    with pytest.raises(RuntimeError, match="economics readiness failed"):
        validate_business_insides_economics_ready(
            db_path=tmp_path / "app.db",
            as_of=as_of,
            output_root=tmp_path / "out",
            business_dir=business_dir,
            snapshot_json_path=snapshot_json,
            strict=True,
            metrics_override=metrics,
        )


def test_economics_ready_fails_on_nonvolatile_gaps_even_if_locked(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    metrics = {
        "economics_missing_days": ["2026-02-10"],
        "economics_missing_nonvolatile_days": ["2026-02-10"],
        "economics_volatility_days": 14,
        "profit_publication_locked": True,
    }
    with pytest.raises(RuntimeError, match="economics readiness failed"):
        validate_business_insides_economics_ready(
            db_path=tmp_path / "app.db",
            as_of=as_of,
            output_root=tmp_path / "out",
            business_dir=business_dir,
            snapshot_json_path=snapshot_json,
            strict=True,
            metrics_override=metrics,
        )


def test_economics_ready_uses_strict_sales_metrics_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    captured: dict[str, object] = {}

    def _fake_compute_sales_metrics(**kwargs):
        captured.update(kwargs)
        return {
            "economics_missing_days": [],
            "economics_missing_nonvolatile_days": [],
            "economics_volatility_days": 14,
            "profit_publication_locked": False,
        }

    monkeypatch.setattr(
        "scripts.validate_business_insides_economics_ready.compute_sales_metrics",
        _fake_compute_sales_metrics,
    )

    report = validate_business_insides_economics_ready(
        db_path=tmp_path / "app.db",
        as_of=as_of,
        output_root=tmp_path / "out",
        business_dir=business_dir,
        snapshot_json_path=snapshot_json,
        strict=True,
    )
    assert report["ok"] is True
    assert captured.get("allow_completed_revenue_fallback") is False


def test_economics_ready_fails_on_nonvolatile_missing_sku_identity(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    metrics = {
        "economics_missing_days": [],
        "economics_missing_nonvolatile_days": [],
        "economics_volatility_days": 14,
        "profit_publication_locked": False,
    }
    line_quality = {
        "missing_sku_rows_total": 1,
        "missing_sku_rows_nonvolatile": 1,
        "missing_unit_cost_rows_total": 0,
        "missing_unit_cost_rows_nonvolatile": 0,
        "missing_sku_days_nonvolatile": ["2026-02-10"],
        "missing_unit_cost_days_nonvolatile": [],
    }
    with pytest.raises(RuntimeError, match="economics readiness failed"):
        validate_business_insides_economics_ready(
            db_path=tmp_path / "app.db",
            as_of=as_of,
            output_root=tmp_path / "out",
            business_dir=business_dir,
            snapshot_json_path=snapshot_json,
            strict=True,
            metrics_override=metrics,
            line_quality_override=line_quality,
        )


def test_economics_ready_fails_on_nonvolatile_missing_unit_cost(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    metrics = {
        "economics_missing_days": [],
        "economics_missing_nonvolatile_days": [],
        "economics_volatility_days": 14,
        "profit_publication_locked": False,
    }
    line_quality = {
        "missing_sku_rows_total": 0,
        "missing_sku_rows_nonvolatile": 0,
        "missing_unit_cost_rows_total": 3,
        "missing_unit_cost_rows_nonvolatile": 3,
        "missing_sku_days_nonvolatile": [],
        "missing_unit_cost_days_nonvolatile": ["2026-02-09"],
    }
    with pytest.raises(RuntimeError, match="economics readiness failed"):
        validate_business_insides_economics_ready(
            db_path=tmp_path / "app.db",
            as_of=as_of,
            output_root=tmp_path / "out",
            business_dir=business_dir,
            snapshot_json_path=snapshot_json,
            strict=True,
            metrics_override=metrics,
            line_quality_override=line_quality,
        )


def test_economics_ready_allows_missing_unit_cost_in_volatile_window(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    business_dir = tmp_path / "business"
    business_dir.mkdir(parents=True)
    snapshot_json = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    _write_snapshot(snapshot_json, as_of, cogs=None, profit=None)

    metrics = {
        "economics_missing_days": [],
        "economics_missing_nonvolatile_days": [],
        "economics_volatility_days": 14,
        "profit_publication_locked": False,
    }
    line_quality = {
        "missing_sku_rows_total": 2,
        "missing_sku_rows_nonvolatile": 0,
        "missing_unit_cost_rows_total": 2,
        "missing_unit_cost_rows_nonvolatile": 0,
        "missing_sku_days_nonvolatile": [],
        "missing_unit_cost_days_nonvolatile": [],
    }
    report = validate_business_insides_economics_ready(
        db_path=tmp_path / "app.db",
        as_of=as_of,
        output_root=tmp_path / "out",
        business_dir=business_dir,
        snapshot_json_path=snapshot_json,
        strict=True,
        metrics_override=metrics,
        line_quality_override=line_quality,
    )
    assert report["ok"] is True
