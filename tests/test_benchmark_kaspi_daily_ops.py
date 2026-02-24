from __future__ import annotations

import json
from pathlib import Path

from scripts import benchmark_kaspi_daily_ops as mod


def test_benchmark_kaspi_daily_ops_writes_timing_artifacts(tmp_path: Path) -> None:
    def fake_runner(_cmd: str, _cwd: Path) -> tuple[int, str]:
        return 0, "ok"

    report = mod.run_benchmark(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_dir=tmp_path,
        repeats=1,
        profile="today-fast",
        runner=fake_runner,
    )

    json_path = tmp_path / "benchmark_timings.json"
    md_path = tmp_path / "benchmark_timings.md"
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["as_of"] == "2026-02-23"
    assert payload["profile"] == "today-fast"
    assert "runs" in payload and payload["runs"]
    assert "step_stats" in payload
    assert report["benchmark_json"] == str(json_path)
    assert report["benchmark_md"] == str(md_path)
