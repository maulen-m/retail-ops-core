from __future__ import annotations

from pathlib import Path
import json

from scripts.build_daily_ops_timings import build_daily_ops_timings


def test_daily_ops_result_parity_contract(tmp_path: Path) -> None:
    seq = {"n": 0}

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        seq["n"] += 1
        # deterministic output by command text, not call order
        return 0, f"ok::{cmd}"

    report = build_daily_ops_timings(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path,
        profile="today-fast",
        repeats=2,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    runs = report["payload"]["runs"]
    assert len(runs) == 2

    first_steps = {row["step"]: row["summary"] for row in runs[0]["steps"]}
    second_steps = {row["step"]: row["summary"] for row in runs[1]["steps"]}
    assert first_steps == second_steps


def test_daily_ops_timings_prefers_frozen_summary_when_present(tmp_path: Path) -> None:
    as_of = "2026-03-08"
    frozen_summary = tmp_path / "exports" / "validation" / "board_v8_runtime" / as_of / "daily_ops_summary.json"
    frozen_summary.parent.mkdir(parents=True, exist_ok=True)
    frozen_summary.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T17:29:57Z",
                "as_of": as_of,
                "profile": "catch-up",
                "ok": True,
                "exit_code": 0,
                "total_duration_sec": 52.39,
                "steps": [
                    {"step": "validate_schema", "rc": 0, "ok": True, "summary": "OK", "duration_sec": 0.047},
                    {"step": "shipment_preflight", "rc": 0, "ok": True, "summary": "PASS", "duration_sec": 22.538},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_daily_ops_timings(
        project_root=tmp_path,
        as_of=as_of,
        output_root=tmp_path / "exports" / "perf",
        profile="today-fast",
        repeats=2,
        strict=True,
    )

    assert report["ok"] is True
    payload = report["payload"]
    assert payload["source"] == "frozen_summary"
    assert payload["runs"][0]["summary_json"] == str(frozen_summary)
    assert payload["runs"][1]["summary_json"] == str(frozen_summary)
