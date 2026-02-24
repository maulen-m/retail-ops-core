from __future__ import annotations

import json
from pathlib import Path

from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops


def test_multistore_red_store_forces_nonzero_and_keeps_partial_artifacts(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "--store STOREB" in cmd:
            return 1, "store fail"
        return 0, "ok"

    report = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=fake_runner,
    )

    assert report["exit_code"] == 1
    assert report["ok"] is False
    assert report["red_stores"] == ["STOREB"]

    summary_json = Path(report["summary_json"])
    summary_md = Path(report["summary_md"])
    assert summary_json.exists()
    assert summary_md.exists()

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["red_stores"] == ["STOREB"]
    assert payload["store_results"]["STOREB"]["ok"] is False
    # partial artifacts must include successful stores too
    assert payload["store_results"]["UNIVERSAL"]["ok"] is True
