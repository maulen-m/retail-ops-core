from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from core.ops.waybill_send_batch import compute_manifest_batch_hash
from scripts.verify_daily_shipping_closeout import (
    CloseoutEvidenceError,
    verify_closeout_evidence,
)


TARGET_DATE = "2026-07-14"
RUN_ID = "20260714_173000_2026-07-14_closeout"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _green_closeout(project: Path, *, states: tuple[str, ...] = ("confirmed", "confirmed")) -> Path:
    batch_root = (
        project
        / "excel_ui"
        / "Kaspi_orders"
        / "Today"
        / "MERGED"
        / "SEND"
        / "14.07.26_MERGED_qnt2"
    )
    manifest = {
        "schema_version": 4,
        "batch_label": batch_root.name,
        "target_date": TARGET_DATE,
        "ready_set_at": "2026-07-14T17:00:00+05:00",
        "request_identity": {
            "target_date": TARGET_DATE,
            "ready_set_at": "2026-07-14T17:00:00+05:00",
        },
        "source_root": str(batch_root),
        "expected_orders_sha256": "e" * 64,
        "obligation_scope_hash": "o" * 64,
        "line_scope_hash": "l" * 64,
        "terminal_orders_excluded": True,
        "send_order_ids": ["private-order-1001", "private-order-1002"],
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "batch_hash": "",
        "counts": {"pdfs": 2, "orders": 2},
        "entries": [
            {"pdf_key": "pdf-a", "filename": "a.pdf", "order_ids": ["private-order-1001"]},
            {"pdf_key": "pdf-b", "filename": "b.pdf", "order_ids": ["private-order-1002"]},
        ],
    }
    manifest["batch_hash"] = compute_manifest_batch_hash(manifest)
    manifest_path = _write_json(batch_root / "send_batch_manifest.json", manifest)
    telegram_ledger_path = _write_json(
        batch_root / "telegram_send_ledger.json",
        {
            "schema_version": 1,
            "channel": "telegram",
            "batch_hash": manifest["batch_hash"],
            "telegram_chat_id": "private-chat-id",
            "entries": {
                key: {
                    "state": state,
                    "telegram_chat_id": "private-chat-id" if state == "confirmed" else "",
                }
                for key, state in zip(("pdf-a", "pdf-b"), states, strict=True)
            },
        },
    )
    assembly_ledger_path = _write_json(
        batch_root / "send_ledger.json",
        {
            "schema_version": 1,
            "batch_hash": manifest["batch_hash"],
            "manifest_path": str(manifest_path.resolve()),
            "entries": {
                key: {"state": state}
                for key, state in zip(("pdf-a", "pdf-b"), states, strict=True)
            },
        },
    )
    run_dir = (
        project
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / TARGET_DATE
        / RUN_ID
    )
    completion = {
        "completed": all(state == "confirmed" for state in states),
        "status": "TELEGRAM_CONFIRMED"
        if all(state == "confirmed" for state in states)
        else "TELEGRAM_LEDGER_INCOMPLETE",
        "channel": "telegram",
        "target_date": TARGET_DATE,
        "manifest_path": str(manifest_path.resolve()),
        "ledger_path": str(telegram_ledger_path.resolve()),
        "manifest_count": 2,
        "confirmed_count": sum(state == "confirmed" for state in states),
        "pending_count": sum(state != "confirmed" for state in states),
    }
    _write_json(
        run_dir / "delivery_send_report.json",
        {
            "ok": completion["completed"],
            "expected_target_date": TARGET_DATE,
            "delivery_channel": "telegram",
            "delivery_completion": completion,
        },
    )
    _write_json(
        run_dir / "shipping_report.json",
        {
            "target_date": TARGET_DATE,
            "required_count": 2,
            "required_pending_before": 2,
            "required_satisfied_before": 0,
            "shipped": 2,
            "skipped": 0,
            "errors": [],
            "remaining_pending": 0,
            "remaining_overdue_pending": 0,
            "health_code": "ok",
            "health_exit_code": 0,
            "selection_status": "PINNED_REQUIRED_ORDERS",
        },
    )
    _write_json(
        run_dir / "expected_order_manifest_gate.json",
        {"ok": True, "target_date": TARGET_DATE, "manifest_count": 2},
    )
    _write_json(
        run_dir / "shipped_truth_sync_report.json",
        {"ok": True, "target_date": TARGET_DATE},
    )
    steps = [
        {"name": name, "ok": True, "returncode": 0}
        for name in (
            "size_writeback",
            "shipping",
            "download_waybills",
            "build_waybills",
            "delivery_send",
            "shipped_truth_sync",
        )
    ]
    for step in steps:
        _write_json(run_dir / f"step_{step['name']}.json", step)
    return _write_json(
        run_dir / "closeout_report.json",
        {
            "ok": True,
            "mode": "apply",
            "target_date": TARGET_DATE,
            "run_id": RUN_ID,
            "zero_order_noop": False,
            "expected_closeout_order_count": 2,
            "expected_order_manifest_gate_ok": True,
            "expected_order_manifest_gate_path": str(
                (run_dir / "expected_order_manifest_gate.json").resolve()
            ),
            "ready": True,
            "halt_barrier_gate": {"blocked": False, "reason": "NO_HALT_BARRIER"},
            "steps": steps,
            "pinned_delivery_artifacts": {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": _sha256(manifest_path),
                "ledger_path": str(assembly_ledger_path.resolve()),
                "batch_hash": manifest["batch_hash"],
                "request_identity": manifest["request_identity"],
            },
            "delivery_completion_verification": {
                "completed": completion["completed"],
                "status": completion["status"],
                "confirmed_count": completion["confirmed_count"],
                "manifest_count": completion["manifest_count"],
            },
        },
    )


def _zero_order_closeout(project: Path) -> Path:
    run_dir = (
        project
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / TARGET_DATE
        / RUN_ID
    )
    expected = _write_json(
        run_dir / "expected_closeout_orders.json",
        {
            "schema_version": 3,
            "target_date": TARGET_DATE,
            "request_identity": {
                "target_date": TARGET_DATE,
                "ready_set_at": "2026-07-14T17:00:00+05:00",
            },
            "expected_order_ids": [],
            "orders": [],
            "counts": {"orders": 0, "order_lines": 0, "overdue_orders": 0},
        },
    )
    marker = _write_json(
        run_dir / "zero_order_completion.json",
        {
            "schema_version": 1,
            "completed": True,
            "mode": "apply",
            "run_id": RUN_ID,
            "target_date": TARGET_DATE,
            "request_identity": {
                "target_date": TARGET_DATE,
                "ready_set_at": "2026-07-14T17:00:00+05:00",
            },
            "required_order_count": 0,
            "required_orders_path": str(expected.resolve()),
            "required_orders_sha256": _sha256(expected),
        },
    )
    return _write_json(
        run_dir / "closeout_report.json",
        {
            "ok": True,
            "mode": "apply",
            "target_date": TARGET_DATE,
            "run_id": RUN_ID,
            "zero_order_noop": True,
            "expected_closeout_order_count": 0,
            "expected_closeout_orders_path": str(expected.resolve()),
            "zero_order_completion_path": str(marker.resolve()),
        },
    )


def test_green_closeout_recomputes_manifest_bound_telegram_ledger(tmp_path: Path) -> None:
    project = tmp_path / "project"
    report = verify_closeout_evidence(
        closeout_report_path=_green_closeout(project),
        expected_date=date.fromisoformat(TARGET_DATE),
        project_root=project,
    )

    serialized = json.dumps(report)
    assert report["gate"] == "GREEN"
    assert report["completion_kind"] == "telegram_ledger"
    assert report["manifest_count"] == 2
    assert report["confirmed_count"] == 2
    assert report["pending_count"] == 0
    assert "private-order" not in serialized
    assert "private-chat-id" not in serialized


def test_superficial_ok_closeout_without_delivery_proof_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("delivery_completion_verification")
    _write_json(path, payload)

    with pytest.raises(CloseoutEvidenceError, match="delivery verification"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_partial_ledger_is_rejected_even_when_closeout_says_ok(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project, states=("confirmed", "pending"))

    with pytest.raises(CloseoutEvidenceError, match="ledger is not complete"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_manifest_hash_drift_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = Path(payload["pinned_delivery_artifacts"]["manifest_path"])
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(CloseoutEvidenceError, match="manifest SHA-256"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_wrong_day_or_run_directory_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project)

    with pytest.raises(CloseoutEvidenceError, match="expected workflow path"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date(2026, 7, 13),
            project_root=project,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["run_id"] = "different-run"
    _write_json(path, payload)
    with pytest.raises(CloseoutEvidenceError, match="run_id"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_symlinked_ledger_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = Path(payload["pinned_delivery_artifacts"]["manifest_path"])
    ledger = manifest.parent / "telegram_send_ledger.json"
    target = ledger.with_name("real-ledger.json")
    ledger.rename(target)
    ledger.symlink_to(target)

    with pytest.raises(CloseoutEvidenceError, match="symlink"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_missing_shipping_stage_or_zero_pending_report_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _green_closeout(project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["steps"] = [
        step for step in payload["steps"] if step["name"] != "download_waybills"
    ]
    _write_json(path, payload)
    with pytest.raises(CloseoutEvidenceError, match="required closeout stage"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )

    path = _green_closeout(project)
    shipping_report = path.parent / "shipping_report.json"
    shipping = json.loads(shipping_report.read_text(encoding="utf-8"))
    shipping["remaining_pending"] = 1
    _write_json(shipping_report, shipping)
    with pytest.raises(CloseoutEvidenceError, match="zero pending"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )


def test_zero_order_requires_hashed_completion_marker(tmp_path: Path) -> None:
    project = tmp_path / "project"
    path = _zero_order_closeout(project)
    report = verify_closeout_evidence(
        closeout_report_path=path,
        expected_date=date.fromisoformat(TARGET_DATE),
        project_root=project,
    )
    assert report["gate"] == "GREEN"
    assert report["completion_kind"] == "zero_order_noop"
    assert report["manifest_count"] == 0

    payload = json.loads(path.read_text(encoding="utf-8"))
    marker = Path(payload["zero_order_completion_path"])
    marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    marker_payload["required_orders_sha256"] = "0" * 64
    _write_json(marker, marker_payload)
    with pytest.raises(CloseoutEvidenceError, match="required orders SHA-256"):
        verify_closeout_evidence(
            closeout_report_path=path,
            expected_date=date.fromisoformat(TARGET_DATE),
            project_root=project,
        )
