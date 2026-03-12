from __future__ import annotations

import json
from pathlib import Path

from scripts.smoke_test_owner_truth_daily import normalize_payload, run_smoke_test


def test_normalize_payload_ignores_approved_volatile_fields() -> None:
    left = {
        "generated_at": "2026-03-08T18:00:00Z",
        "steps": [
            {"step": "alpha", "duration_sec": 0.1, "ok": True},
        ],
        "nested": {"finished_at": "2026-03-08T18:01:00Z", "value": 1},
    }
    right = {
        "generated_at": "2026-03-08T19:00:00Z",
        "steps": [
            {"step": "alpha", "duration_sec": 9.9, "ok": True},
        ],
        "nested": {"finished_at": "2026-03-08T19:01:00Z", "value": 1},
    }

    assert normalize_payload(left) == normalize_payload(right)


def test_run_smoke_test_writes_artifacts_and_confirms_idempotence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_counter = {"value": 0}

    def fake_run_owner_truth_daily(*, project_root: Path, as_of: str, strict: bool, mode: str) -> dict[str, object]:
        run_counter["value"] += 1
        daily_dir = project_root / "exports" / "daily" / as_of
        exceptions_dir = project_root / "exports" / "exceptions" / as_of
        owner_validation_dir = project_root / "exports" / "validation" / "owner_truth_daily" / as_of
        publication_dir = project_root / "exports" / "north_star_owner_review" / as_of
        owner_pnl_dir = project_root / "exports" / "owner_pnl" / as_of
        for path in (daily_dir, exceptions_dir, owner_validation_dir, publication_dir, owner_pnl_dir):
            path.mkdir(parents=True, exist_ok=True)

        stamp = f"2026-03-08T18:00:0{run_counter['value']}Z"
        (daily_dir / "owner_truth_summary.json").write_text(
            json.dumps(
                {
                    "generated_at": stamp,
                    "status": "PASS",
                    "steps": [{"step": "doctor", "duration_sec": run_counter["value"], "ok": True}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (daily_dir / "daily_ops_report.json").write_text(
            json.dumps({"generated_at": stamp, "status": "GREEN", "ok": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (exceptions_dir / "exceptions.json").write_text(
            json.dumps(
                {
                    "generated_at": stamp,
                    "as_of": as_of,
                    "status": "GREEN",
                    "ok": True,
                    "schema_version": "v1",
                    "steps": [],
                    "exceptions": [],
                    "critical_count": 0,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (owner_validation_dir / "full_run_transcript.md").write_text(
            f"# transcript {run_counter['value']}\n",
            encoding="utf-8",
        )
        (publication_dir / "publication_readiness.json").write_text(
            json.dumps({"generated_at": stamp, "status": "PASS", "ok": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (owner_pnl_dir / "OWNER_PNL.json").write_text(
            json.dumps({"generated_at": stamp, "status": "PASS", "ok": True}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"rc": 0, "stdout": f"mode={mode}\nstatus=PASS", "stderr": ""}

    monkeypatch.setattr(
        "scripts.smoke_test_owner_truth_daily._run_owner_truth_daily",
        fake_run_owner_truth_daily,
    )

    report = run_smoke_test(
        project_root=tmp_path,
        as_of="2026-03-08",
        strict=True,
    )

    assert report["ok"] is True
    assert report["runs"][0]["rc"] == 0
    assert report["runs"][1]["rc"] == 0
    assert report["idempotence"]["ok"] is True
    assert (tmp_path / "exports" / "validation" / "owner_truth_release" / "2026-03-08" / "cold_start_smoke_run_1.md").exists()
    assert (tmp_path / "exports" / "validation" / "owner_truth_release" / "2026-03-08" / "cold_start_smoke_run_2.md").exists()
    assert (tmp_path / "exports" / "validation" / "owner_truth_release" / "2026-03-08" / "idempotence_report.json").exists()
    assert all("mode=replay" in run["stdout"] for run in report["runs"])
