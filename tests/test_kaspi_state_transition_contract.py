from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_kaspi_state_transition import validate_kaspi_state_transition


def _event(*, confirmed: bool, http_success: bool, pre_state: str, post_state: str) -> dict:
    return {
        "order_code": "ORDER-1",
        "action": "assemble",
        "http_success": http_success,
        "confirmed": confirmed,
        "pre_state": pre_state,
        "post_state": post_state,
    }


def test_state_transition_validator_passes_on_confirmed_transition(tmp_path: Path) -> None:
    payload = {"as_of": "2026-02-26", "events": [_event(confirmed=True, http_success=True, pre_state="PENDING", post_state="AWAITING_COURIER")]}
    src = tmp_path / "events.json"
    src.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_kaspi_state_transition(input_path=src, as_of="2026-02-26", output_root=tmp_path, strict=True)
    assert report["ok"] is True
    assert report["http_only_success_count"] == 0


def test_state_transition_validator_fails_http_only_success(tmp_path: Path) -> None:
    payload = {"as_of": "2026-02-26", "events": [_event(confirmed=False, http_success=True, pre_state="PENDING", post_state="PENDING")]}
    src = tmp_path / "events.json"
    src.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_kaspi_state_transition(input_path=src, as_of="2026-02-26", output_root=tmp_path, strict=False)
    assert report["ok"] is False
    assert report["http_only_success_count"] == 1
    with pytest.raises(RuntimeError):
        validate_kaspi_state_transition(input_path=src, as_of="2026-02-26", output_root=tmp_path, strict=True)


def test_state_transition_validator_fails_when_post_state_not_changed(tmp_path: Path) -> None:
    payload = {"as_of": "2026-02-26", "events": [_event(confirmed=True, http_success=True, pre_state="PENDING", post_state="PENDING")]}
    src = tmp_path / "events.json"
    src.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_kaspi_state_transition(input_path=src, as_of="2026-02-26", output_root=tmp_path, strict=False)
    assert report["ok"] is False
    assert any("post_state" in err for err in report["errors"])
