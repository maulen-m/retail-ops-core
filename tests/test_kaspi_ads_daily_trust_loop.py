from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.kaspi_ads_daily_trust_loop import run_daily_trust_loop


def _runner_factory(
    *,
    health_rc: int = 0,
    coverage_rc: int = 0,
    brief_rc: int = 0,
    calls: list[list[str]] | None = None,
) -> Any:
    call_log = calls if calls is not None else []

    def _runner(cmd: list[str]) -> tuple[int, str, str, dict[str, Any] | None]:
        call_log.append(cmd)
        rendered = " ".join(cmd)
        if "kaspi_ads_healthcheck.py" in rendered:
            payload = {"status": "ok" if health_rc == 0 else "error", "exit_code": health_rc}
            return health_rc, json.dumps(payload), "", payload
        if "kaspi_ads_campaign_coverage_report.py" in rendered:
            payload = {"status": "ok" if coverage_rc == 0 else "error", "exit_code": coverage_rc}
            return coverage_rc, json.dumps(payload), "", payload
        if "kaspi_ads_elasticity.py" in rendered:
            payload = {"status": "ok" if brief_rc == 0 else "error", "recommendation_rows": 1}
            return brief_rc, json.dumps(payload), "", payload
        raise AssertionError(f"Unexpected command: {cmd}")

    return _runner


def test_trust_loop_success_path_writes_summary_and_exit_zero(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    summary_out = tmp_path / "trust_loop_latest.json"
    coverage_out = tmp_path / "coverage_latest.json"
    brief_out_dir = tmp_path / "daily_brief"

    result = run_daily_trust_loop(
        ads_db=tmp_path / "ads.db",
        stores_config=tmp_path / "stores.yaml",
        app_db=tmp_path / "app.db",
        coverage_out=coverage_out,
        brief_out_dir=brief_out_dir,
        summary_out=summary_out,
        run_step_fn=_runner_factory(calls=calls),
    )

    assert result["status"] == "ok"
    assert result["exit_code"] == 0
    assert summary_out.exists()
    persisted = json.loads(summary_out.read_text(encoding="utf-8"))
    assert persisted["status"] == "ok"
    assert len(persisted["steps"]) == 3
    assert len(calls) == 3


def test_trust_loop_fails_when_healthcheck_fails(tmp_path: Path) -> None:
    summary_out = tmp_path / "trust_loop_latest.json"
    result = run_daily_trust_loop(
        ads_db=tmp_path / "ads.db",
        stores_config=tmp_path / "stores.yaml",
        app_db=tmp_path / "app.db",
        coverage_out=tmp_path / "coverage_latest.json",
        brief_out_dir=tmp_path / "daily_brief",
        summary_out=summary_out,
        run_step_fn=_runner_factory(health_rc=1),
    )

    assert result["status"] == "error"
    assert result["exit_code"] == 1
    assert "healthcheck" in result["failures"]


def test_trust_loop_fails_when_coverage_fails(tmp_path: Path) -> None:
    result = run_daily_trust_loop(
        ads_db=tmp_path / "ads.db",
        stores_config=tmp_path / "stores.yaml",
        app_db=tmp_path / "app.db",
        coverage_out=tmp_path / "coverage_latest.json",
        brief_out_dir=tmp_path / "daily_brief",
        summary_out=tmp_path / "trust_loop_latest.json",
        run_step_fn=_runner_factory(coverage_rc=2),
    )

    assert result["status"] == "error"
    assert result["exit_code"] == 1
    assert "coverage" in result["failures"]


def test_trust_loop_fails_when_brief_generation_fails(tmp_path: Path) -> None:
    result = run_daily_trust_loop(
        ads_db=tmp_path / "ads.db",
        stores_config=tmp_path / "stores.yaml",
        app_db=tmp_path / "app.db",
        coverage_out=tmp_path / "coverage_latest.json",
        brief_out_dir=tmp_path / "daily_brief",
        summary_out=tmp_path / "trust_loop_latest.json",
        run_step_fn=_runner_factory(brief_rc=3),
    )

    assert result["status"] == "error"
    assert result["exit_code"] == 1
    assert "daily_brief" in result["failures"]


def test_trust_loop_propagates_ads_db_and_output_paths(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    ads_db = tmp_path / "ads.db"
    stores_config = tmp_path / "stores.yaml"
    app_db = tmp_path / "app.db"
    coverage_out = tmp_path / "trust_loop" / "coverage_latest.json"
    brief_out_dir = tmp_path / "brief"
    summary_out = tmp_path / "trust_loop" / "summary_latest.json"

    run_daily_trust_loop(
        ads_db=ads_db,
        stores_config=stores_config,
        app_db=app_db,
        coverage_out=coverage_out,
        brief_out_dir=brief_out_dir,
        summary_out=summary_out,
        run_step_fn=_runner_factory(calls=calls),
    )

    rendered = [" ".join(cmd) for cmd in calls]
    assert len(rendered) == 3
    assert any(f"--ads-db {ads_db}" in line for line in rendered)
    assert any(f"--stores-config {stores_config}" in line for line in rendered)
    assert any(f"--out {coverage_out}" in line for line in rendered)
    assert any(f"--app-db {app_db}" in line for line in rendered)
    assert any(f"--out-dir {brief_out_dir}" in line for line in rendered)
