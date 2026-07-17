import json
from datetime import date
from pathlib import Path

import pytest

from core.ops import google_board_day_state as day_state
from core.ops.waybill_shipping_obligations import KNOWN_STORE_CODES


TARGET_DATE = date(2026, 7, 18)


def test_absent_section_is_all_pending_without_creating_checkpoint(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "2026-07-18" / "closeout_checkpoint.json"

    assert day_state.load_store_day_states(
        TARGET_DATE,
        checkpoint_path=checkpoint_path,
    ) == {}
    effective = day_state.effective_store_states(
        TARGET_DATE,
        checkpoint_path=checkpoint_path,
    )

    assert set(effective) == KNOWN_STORE_CODES
    assert {record["state"] for record in effective.values()} == {"PENDING"}
    assert not checkpoint_path.exists()


def test_set_state_creates_minimal_additive_section_and_normalizes_store(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "2026-07-18" / "closeout_checkpoint.json"

    record = day_state.set_store_day_state(
        TARGET_DATE,
        "STORE-B",
        "manual_fulfilled",
        reason="owner completed the store manually",
        set_by="owner",
        checkpoint_path=checkpoint_path,
    )

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["target_date"] == "2026-07-18"
    assert set(payload) == {"target_date", "store_day_states"}
    assert payload["store_day_states"]["schema_version"] == 1
    assert payload["store_day_states"]["stores"]["STOREB"] == record
    assert record["state"] == "MANUAL_FULFILLED"
    assert record["postponed_to"] == ""
    assert not list(checkpoint_path.parent.glob(".*.tmp"))


def test_set_state_final_reread_preserves_completed_closeout_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "closeout_checkpoint.json"
    first = {"target_date": "2026-07-18", "stages": {}}
    latest = {
        "target_date": "2026-07-18",
        "stages": {"shipping": {"status": "ok"}},
    }
    reads = iter([first, latest])
    monkeypatch.setattr(
        day_state,
        "_read_checkpoint",
        lambda _path: next(reads),
    )

    day_state.set_store_day_state(
        TARGET_DATE,
        "Universal",
        "POSTPONED",
        postponed_to="2026-07-19",
        reason="courier pickup moved",
        set_by="operator",
        checkpoint_path=checkpoint_path,
    )

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert payload["stages"] == {"shipping": {"status": "ok"}}
    assert payload["store_day_states"]["stores"]["UNIVERSAL"]["state"] == "POSTPONED"


def test_postponed_requires_valid_destination_and_metadata(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "closeout_checkpoint.json"

    with pytest.raises(ValueError, match="requires postponed_to"):
        day_state.set_store_day_state(
            TARGET_DATE,
            "UNIVERSAL",
            "POSTPONED",
            reason="later",
            set_by="operator",
            checkpoint_path=checkpoint_path,
        )
    with pytest.raises(ValueError, match="reason is required"):
        day_state.set_store_day_state(
            TARGET_DATE,
            "UNIVERSAL",
            "MANUAL_FULFILLED",
            reason="",
            set_by="operator",
            checkpoint_path=checkpoint_path,
        )
