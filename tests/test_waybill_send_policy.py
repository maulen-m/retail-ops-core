import json
from datetime import date

import pytest

from scripts.waybill_send_policy import (
    blocked_live_action_for_manifest,
    load_waybill_send_exclusions,
)


def test_july_10_owner_decision_blocks_live_batch_actions() -> None:
    policy = load_waybill_send_exclusions()

    assert policy["decision_id"] == "WAYBILL-SEND-EXCLUSION-2026-07-10"
    decision = blocked_live_action_for_manifest(
        {"target_date": "2026-07-10"},
        action="telegram_pdf_send",
    )
    assert decision is not None
    assert decision["action"] == "never_send_or_resume"


def test_later_manifest_is_not_blocked_by_july_10_decision() -> None:
    assert (
        blocked_live_action_for_manifest(
            {
                "target_date": date(2026, 7, 11).isoformat(),
                "entries": [{"order_ids": ["992447685"]}],
            },
            action="telegram_pdf_send",
        )
        is None
    )


def test_unknown_or_missing_manifest_target_date_fails_closed() -> None:
    decision = blocked_live_action_for_manifest({}, action="telegram_pdf_send")

    assert decision is not None
    assert decision["action"] == "invalid_manifest_target_date"


def test_missing_policy_file_fails_closed(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        blocked_live_action_for_manifest(
            {"target_date": "2026-07-10"},
            action="telegram_pdf_send",
            policy_path=tmp_path / "missing.json",
        )


def test_malformed_policy_schema_fails_closed(tmp_path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps({"schema_version": "wrong", "decisions": []}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Unsupported"):
        blocked_live_action_for_manifest(
            {"target_date": "2026-07-10"},
            action="telegram_pdf_send",
            policy_path=policy_path,
        )
