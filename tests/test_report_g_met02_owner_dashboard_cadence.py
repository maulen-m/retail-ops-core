from __future__ import annotations

import json
from pathlib import Path

from scripts.report_g_met02_owner_dashboard_cadence import build_owner_dashboard_cadence_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_scoreboard(path: Path, states: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["gate_id,state,evidence,dated"]
    for gate_id, state in states.items():
        rows.append(f"{gate_id},{state},fixture,20260618")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_config(path: Path, *, root: Path, scoreboard: Path, history_glob: str) -> None:
    payload = {
        "contract_id": "OWNER_DASHBOARD_CADENCE_V1",
        "gate_id": "G-MET-02",
        "scoreboard_path": str(scoreboard),
        "history_glob": history_glob,
        "required_history_days_for_green": 7,
        "cadences": ["daily", "weekly", "monthly"],
        "items": [
            {
                "cadence": "daily",
                "item_id": "automation",
                "label": "Automation",
                "source_type": "latest_json",
                "path_glob": str(root / "daily" / "*" / "automation.json"),
                "source_date_fields": ["status.generated_at", "generated_at", "as_of"],
                "max_age_days": 2,
                "allowed_statuses": ["OK", "GREEN"],
                "pass_when_ok_true": True,
            },
            {
                "cadence": "daily",
                "item_id": "cash",
                "label": "Cash",
                "source_type": "scoreboard_gate",
                "gate_ids": ["G-CASH-02"],
                "allowed_statuses": ["GREEN"],
            },
            {
                "cadence": "weekly",
                "item_id": "release_velocity",
                "label": "Release velocity",
                "source_type": "latest_json",
                "path_glob": str(root / "weekly" / "*" / "release.json"),
                "source_date_fields": ["as_of", "generated_at"],
                "max_age_days": 7,
                "allowed_statuses": ["GREEN"],
            },
            {
                "cadence": "monthly",
                "item_id": "ppch",
                "label": "PPCH",
                "source_type": "latest_json",
                "path_glob": str(root / "monthly" / "*" / "ppch.json"),
                "source_date_fields": ["as_of", "generated_at"],
                "max_age_days": 31,
                "allowed_statuses": ["GREEN", "ARMED"],
            },
        ],
    }
    _write_json(path, payload)


def _write_green_sources(root: Path) -> None:
    _write_json(
        root / "daily" / "20260618" / "automation.json",
        {"ok": True, "status": {"generated_at": "2026-06-18T10:00:00+05:00"}},
    )
    _write_json(root / "weekly" / "20260618" / "release.json", {"gate": "GREEN", "as_of": "2026-06-18"})
    _write_json(root / "monthly" / "20260618" / "ppch.json", {"gate": "GREEN", "as_of": "2026-06-18"})


def _write_history(root: Path, dates: list[str]) -> None:
    for value in dates:
        _write_json(root / value / "owner_dashboard_cadence_report.json", {"as_of_date": value})


def test_missing_item_and_short_history_are_armed(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    history = tmp_path / "history"
    _write_scoreboard(scoreboard, {"G-CASH-02": "GREEN"})
    _write_config(config, root=tmp_path, scoreboard=scoreboard, history_glob=str(history / "*" / "*.json"))
    _write_json(
        tmp_path / "daily" / "20260618" / "automation.json",
        {"ok": True, "status": {"generated_at": "2026-06-18T10:00:00+05:00"}},
    )
    _write_json(tmp_path / "monthly" / "20260618" / "ppch.json", {"gate": "ARMED", "as_of": "2026-06-18"})

    report = build_owner_dashboard_cadence_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:30:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert report["cadence_history_day_count"] == 1
    assert any("release_velocity" in blocker for blocker in report["cadence_blockers"])
    assert any("cadence_history_days" in blocker for blocker in report["measurement_blockers"])


def test_all_current_items_and_mature_history_are_green(tmp_path: Path) -> None:
    scoreboard = tmp_path / "scoreboard.csv"
    config = tmp_path / "config.json"
    history = tmp_path / "history"
    _write_scoreboard(scoreboard, {"G-CASH-02": "GREEN"})
    _write_config(config, root=tmp_path, scoreboard=scoreboard, history_glob=str(history / "*" / "*.json"))
    _write_green_sources(tmp_path)
    _write_history(history, [f"2026-06-{day:02d}" for day in range(12, 18)])

    report = build_owner_dashboard_cadence_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:30:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["cadence_history_day_count"] == 7
    assert report["cadence_blockers"] == []
    assert report["measurement_blockers"] == []


def test_bad_config_is_red(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    _write_json(config, {"contract_id": "WRONG", "gate_id": "G-MET-02", "items": []})

    report = build_owner_dashboard_cadence_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-18T18:30:00+05:00",
    )

    assert report["gate"] == "RED"
    assert any("config_identity" in blocker for blocker in report["blockers"])
