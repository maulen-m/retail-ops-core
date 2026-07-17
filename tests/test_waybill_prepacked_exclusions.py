from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from core.ops.waybill_prepacked_exclusions import (
    EXPECTATION_SCHEMA_VERSION,
    SCHEMA_VERSION,
    apply_prepacked_exclusion,
    load_prepacked_exclusion_expectation,
    load_validated_prepacked_exclusion,
)


def _write_source(tmp_path: Path) -> tuple[Path, Path, str]:
    manifest = {
        "schema_version": 4,
        "target_date": "2026-07-11",
        "batch_hash": "batch-1",
        "send_order_ids": ["u1", "m1"],
        "entries": [
            {
                "pdf_key": "pdf-1",
                "source_lines": [
                    {"store_code": "UNIVERSAL", "order_id": "u1"},
                    {"store_code": "STOREB", "order_id": "m1"},
                ],
            }
        ],
    }
    manifest_path = tmp_path / "send_batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    ledger_path = tmp_path / "telegram_send_ledger.json"
    ledger_path.write_text(
        json.dumps({"batch_hash": "batch-1", "entries": {"pdf-1": {"state": "confirmed"}}}),
        encoding="utf-8",
    )
    return manifest_path, ledger_path, "batch-1"


def _write_decision(tmp_path: Path) -> Path:
    manifest_path, ledger_path, batch_hash = _write_source(tmp_path)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "authority": "human_owner",
        "target_date": "2026-07-12",
        "preserve_physical_handover_obligation": True,
        "source_target_date": "2026-07-11",
        "source_manifest_path": str(manifest_path),
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_telegram_ledger_path": str(ledger_path),
        "source_telegram_ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
        "source_batch_hash": batch_hash,
        "excluded_order_count": 2,
        "excluded_counts_by_store": {"UNIVERSAL": 1, "STOREB": 1},
        "excluded_order_ids_by_store": {"UNIVERSAL": ["u1"], "STOREB": ["m1"]},
        "expected_required_order_count": 3,
        "expected_required_counts_by_store": {"UNIVERSAL": 1, "ACMEWEAR": 1, "STOREB": 1},
    }
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_decision_excludes_only_active_declared_orders(tmp_path: Path) -> None:
    decision = load_validated_prepacked_exclusion(
        target_date=date(2026, 7, 12), path=_write_decision(tmp_path)
    )
    result = apply_prepacked_exclusion(
        {"UNIVERSAL": {"u1", "u2"}, "ACMEWEAR": {"o1"}, "STOREB": {"m1", "m2"}},
        decision,
    )

    assert result["applied"] is True
    assert result["count_assertion"] == "strict"
    assert result["required_ids_by_store"] == {
        "UNIVERSAL": {"u2"}, "ACMEWEAR": {"o1"}, "STOREB": {"m2"}
    }
    assert result["excluded_active_count"] == 2
    assert decision["decision_sha256"] == hashlib.sha256(
        Path(decision["path"]).read_bytes()
    ).hexdigest()


def test_effective_dated_expectation_loader_matches_only_requested_date(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "waybill_prepacked_exclusion_expected.json"
    marker_path.write_text(
        json.dumps(
            {
                "schema_version": EXPECTATION_SCHEMA_VERSION,
                "expectations": [
                    {
                        "target_date": "2026-07-18",
                        "decision_id": "JULY18-DECISION",
                        "decision_sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    expectation = load_prepacked_exclusion_expectation(
        target_date=date(2026, 7, 18),
        path=marker_path,
    )

    assert expectation == {
        "target_date": "2026-07-18",
        "decision_id": "JULY18-DECISION",
        "decision_sha256": "a" * 64,
        "path": str(marker_path.resolve()),
    }
    assert load_prepacked_exclusion_expectation(
        target_date=date(2026, 7, 19),
        path=marker_path,
    ) is None


def test_absent_expectation_marker_preserves_optional_behavior(tmp_path: Path) -> None:
    assert load_prepacked_exclusion_expectation(
        target_date=date(2026, 7, 18),
        path=tmp_path / "missing.json",
    ) is None


def test_decision_without_expected_counts_skips_count_assertions() -> None:
    result = apply_prepacked_exclusion(
        {"UNIVERSAL": {"u1", "u2"}, "ACMEWEAR": {"o1"}},
        {
            "excluded_order_ids_by_store": {
                "UNIVERSAL": ["u1", "u3"],
                "STOREB": ["m1"],
            }
        },
    )

    assert result["applied"] is True
    assert result["count_assertion"] == "skipped_absent_expected_counts"
    assert result["required_ids_by_store"] == {
        "UNIVERSAL": {"u2"},
        "ACMEWEAR": {"o1"},
    }
    assert result["excluded_active_ids_by_store"] == {
        "UNIVERSAL": {"u1"},
        "STOREB": set(),
    }
    assert result["inactive_declared_ids_by_store"] == {
        "UNIVERSAL": {"u3"},
        "STOREB": {"m1"},
    }


def test_no_decision_preserves_required_scope() -> None:
    result = apply_prepacked_exclusion(
        {"UNIVERSAL": {"u1"}, "ACMEWEAR": {"o1"}},
        None,
    )

    assert result == {
        "applied": False,
        "required_ids_by_store": {"UNIVERSAL": {"u1"}, "ACMEWEAR": {"o1"}},
        "excluded_active_ids_by_store": {},
        "inactive_declared_ids_by_store": {},
    }


def test_nonmatching_date_does_not_apply(tmp_path: Path) -> None:
    assert load_validated_prepacked_exclusion(
        target_date=date(2026, 7, 13), path=_write_decision(tmp_path)
    ) is None


def test_unconfirmed_source_ledger_fails_closed(tmp_path: Path) -> None:
    decision_path = _write_decision(tmp_path)
    payload = json.loads(decision_path.read_text())
    ledger_path = Path(payload["source_telegram_ledger_path"])
    ledger = json.loads(ledger_path.read_text())
    ledger["entries"]["pdf-1"]["state"] = "unsure"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    payload["source_telegram_ledger_sha256"] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    decision_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="not fully confirmed"):
        load_validated_prepacked_exclusion(target_date=date(2026, 7, 12), path=decision_path)


def test_required_scope_count_drift_fails_closed(tmp_path: Path) -> None:
    decision = load_validated_prepacked_exclusion(
        target_date=date(2026, 7, 12), path=_write_decision(tmp_path)
    )
    with pytest.raises(RuntimeError, match="counts mismatch"):
        apply_prepacked_exclusion(
            {"UNIVERSAL": {"u1"}, "ACMEWEAR": {"o1"}, "STOREB": {"m1", "m2"}},
            decision,
        )
