from __future__ import annotations

import json
from pathlib import Path

from scripts.build_weekly_health_scorecard import build_weekly_health_scorecard


def test_weekly_health_scorecard_contract(tmp_path: Path) -> None:
    daily_root = tmp_path / "daily"
    diagnostics_root = tmp_path / "diagnostics"
    health_root = tmp_path / "health"

    for day, ok in [("2026-02-23", True), ("2026-02-24", False), ("2026-02-25", True)]:
        day_dir = daily_root / day
        day_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "as_of": day,
            "status": "GREEN" if ok else "RED",
            "ok": ok,
            "stores_red": 0 if ok else 1,
            "steps_failed": 0 if ok else 2,
        }
        (day_dir / "daily_ops_report.json").write_text(json.dumps(payload), encoding="utf-8")

        diag_dir = diagnostics_root / day
        diag_dir.mkdir(parents=True, exist_ok=True)
        diag_payload = {"status": "GREEN" if ok else "RED", "ok": ok}
        (diag_dir / "system_health.json").write_text(json.dumps(diag_payload), encoding="utf-8")

    report = build_weekly_health_scorecard(
        as_of="2026-02-25",
        daily_root=daily_root,
        diagnostics_root=diagnostics_root,
        output_root=health_root,
        strict=True,
    )
    assert report["ok"] is True
    assert report["week"] == "2026-W09"

    weekly_json = health_root / "weekly" / "2026-W09" / "weekly_health_scorecard.json"
    weekly_md = health_root / "weekly" / "2026-W09" / "weekly_health_scorecard.md"
    assert weekly_json.exists()
    assert weekly_md.exists()

    payload = json.loads(weekly_json.read_text(encoding="utf-8"))
    assert payload["days_evaluated"] == 3
    assert payload["green_days"] == 2
    assert payload["red_days"] == 1

