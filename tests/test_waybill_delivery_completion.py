from __future__ import annotations

import json
import hashlib
from datetime import date
from pathlib import Path

from core.integrations.google_ops_board import load_ops_board_contract
from core.ops.waybill_send_batch import compute_manifest_batch_hash
from scripts import google_ops_board_automation_common as common_mod
from scripts.waybill_delivery_completion import delivery_completion_state


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])


def _split_v1_client(contract, run_control_row: list[str]) -> _FakeClient:
    return _FakeClient(
        {
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers],
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                run_control_row,
            ],
        }
    )


def _write_manifest(today_root: Path) -> Path:
    batch_root = today_root / "MERGED" / "SEND" / "21.04.26_MERGED_qnt2"
    batch_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 4,
        "batch_label": batch_root.name,
        "target_date": "2026-04-21",
        "ready_set_at": "2026-04-21T17:00:00+05:00",
        "request_identity": {
            "target_date": "2026-04-21",
            "ready_source": "EMPLOYEE",
            "ready_set_at": "2026-04-21T17:00:00+05:00",
        },
        "source_root": str(batch_root),
        "expected_orders_sha256": "e" * 64,
        "obligation_scope_hash": "o" * 64,
        "line_scope_hash": "l" * 64,
        "terminal_orders_excluded": True,
        "send_order_ids": ["1001", "1002"],
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "batch_hash": "",
        "counts": {"pdfs": 2, "orders": 2},
        "entries": [
            {"pdf_key": "pdf-a", "filename": "a.pdf", "order_ids": ["1001"]},
            {"pdf_key": "pdf-b", "filename": "b.pdf", "order_ids": ["1002"]},
        ],
    }
    payload["batch_hash"] = compute_manifest_batch_hash(payload)
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_root


def _write_telegram_ledger(
    batch_root: Path,
    states: dict[str, str],
    *,
    batch_hash: str | None = None,
    chat_id: str = "-100-internal-waybills",
) -> None:
    payload = {
        "schema_version": 1,
        "channel": "telegram",
        "batch_hash": batch_hash
        or json.loads(
            (batch_root / "send_batch_manifest.json").read_text(encoding="utf-8")
        )["batch_hash"],
        "telegram_chat_id": chat_id,
        "entries": {
            pdf_key: {
                "state": state,
                "history": [],
                **({"telegram_chat_id": chat_id} if state == "confirmed" else {}),
            }
            for pdf_key, state in states.items()
        },
    }
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_apply_checkpoint(
    run_root: Path,
    manifest_path: Path,
    *,
    ready_set_at: str = "2026-04-21T17:00:00+05:00",
) -> None:
    checkpoint_path = run_root / "2026-04-21" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "apply",
                "target_date": "2026-04-21",
                "delivery_artifacts": {
                    "manifest_path": str(manifest_path.resolve()),
                    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                    "request_identity": {
                        "target_date": "2026-04-21",
                        "ready_source": "EMPLOYEE",
                        "ready_set_at": ready_set_at,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_closeout_completion_requires_confirmed_delivery_ledger(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _split_v1_client(
        contract,
        ["2026-04-21", "READY", "adil", "2026-04-21T17:00:00+05:00", "", "", "run-1", "OK"],
    )
    batch_root = _write_manifest(tmp_path)
    run_root = tmp_path / "workflow_runs"
    _write_apply_checkpoint(run_root, batch_root / "send_batch_manifest.json")

    missing = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )
    assert missing["completed"] is False
    assert missing["delivery_status"] == "TELEGRAM_LEDGER_MISSING"

    _write_telegram_ledger(batch_root, {"pdf-a": "confirmed", "pdf-b": "pending"})
    partial = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )
    assert partial["completed"] is False
    assert partial["delivery_status"] == "TELEGRAM_LEDGER_INCOMPLETE"
    assert partial["delivery_confirmed_count"] == 1
    assert partial["delivery_manifest_count"] == 2

    _write_telegram_ledger(batch_root, {"pdf-a": "confirmed", "pdf-b": "confirmed"})
    complete = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )
    assert complete["completed"] is True
    assert complete["delivery_channel"] == "telegram"
    assert complete["delivery_confirmed_count"] == 2


def test_delivery_completion_rejects_unbound_telegram_ledger(tmp_path: Path) -> None:
    batch_root = _write_manifest(tmp_path)
    run_root = tmp_path / "workflow_runs"
    _write_apply_checkpoint(run_root, batch_root / "send_batch_manifest.json")
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "telegram_chat_id": "-100-internal-waybills",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "telegram_chat_id": "-100-internal-waybills",
                    },
                    "pdf-b": {
                        "state": "confirmed",
                        "telegram_chat_id": "-100-internal-waybills",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    state = common_mod.closeout_completion_state(
        client=_split_v1_client(
            load_ops_board_contract(),
            [
                "2026-04-21",
                "READY",
                "adil",
                "2026-04-21T17:00:00+05:00",
                "",
                "",
                "run-1",
                "OK",
            ],
        ),
        contract=load_ops_board_contract(),
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )

    assert state["completed"] is False
    assert state["delivery_status"] == "TELEGRAM_LEDGER_BATCH_HASH_MISSING"


def test_zero_order_apply_marker_is_a_terminal_closeout_completion(
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    run_id = "run-zero"
    ready_set_at = "2026-04-21T17:00:00+05:00"
    client = _split_v1_client(
        contract,
        [
            "2026-04-21",
            "READY",
            "adil",
            ready_set_at,
            "",
            "",
            run_id,
            "OK",
        ],
    )
    marker_path = (
        tmp_path
        / "workflow_runs"
        / "2026-04-21"
        / run_id
        / "zero_order_completion.json"
    )
    marker_path.parent.mkdir(parents=True)
    required_path = marker_path.parent / "expected_closeout_orders.json"
    required_payload = {
        "schema_version": 3,
        "target_date": "2026-04-21",
        "request_identity": {
            "target_date": "2026-04-21",
            "ready_source": "EMPLOYEE",
            "ready_set_at": ready_set_at,
        },
        "expected_order_ids": [],
        "orders": [],
        "counts": {"orders": 0, "order_lines": 0, "overdue_orders": 0},
        "line_scope_hash": "",
    }
    required_path.write_text(json.dumps(required_payload), encoding="utf-8")
    required_sha256 = hashlib.sha256(required_path.read_bytes()).hexdigest()
    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-21" / "closeout_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "apply",
                "target_date": "2026-04-21",
                "required_orders": {
                    "path": str(required_path.resolve()),
                    "sha256": required_sha256,
                    "request_identity": required_payload["request_identity"],
                    "line_scope_hash": "",
                },
            }
        ),
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "completed": True,
                "mode": "apply",
                "run_id": run_id,
                "target_date": "2026-04-21",
                "request_identity": {
                    "target_date": "2026-04-21",
                    "ready_source": "EMPLOYEE",
                    "ready_set_at": ready_set_at,
                },
                "required_order_count": 0,
                "required_orders_path": str(required_path.resolve()),
                "required_orders_sha256": required_sha256,
            }
        ),
        encoding="utf-8",
    )

    state = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path / "Today",
        run_root=tmp_path / "workflow_runs",
    )

    assert state["completed"] is True
    assert state["zero_order_completed"] is True
    assert state["completion_kind"] == "zero_order_noop"


def test_whatsapp_completion_requires_explicit_delivery_report(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _split_v1_client(
        contract,
        ["2026-04-21", "READY", "adil", "2026-04-21T17:00:00+05:00", "", "", "run-1", "OK"],
    )
    batch_root = _write_manifest(tmp_path)
    run_root = tmp_path / "workflow_runs"
    _write_apply_checkpoint(run_root, batch_root / "send_batch_manifest.json")
    (batch_root / "send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "batch_hash": json.loads(
                    (batch_root / "send_batch_manifest.json").read_text(encoding="utf-8")
                )["batch_hash"],
                "entries": {
                    "pdf-a": {"state": "confirmed"},
                    "pdf-b": {"state": "confirmed"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    without_report = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )
    assert without_report["completed"] is False
    assert without_report["delivery_status"] == "TELEGRAM_LEDGER_MISSING"

    run_dir = run_root / "2026-04-21" / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "delivery_send_report.json").write_text(
        json.dumps({"ok": True, "delivery_channel": "whatsapp"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with_report = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )
    assert with_report["completed"] is True
    assert with_report["delivery_channel"] == "whatsapp"


def test_closeout_completion_rejects_confirmed_ledger_for_different_ready_request(
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _split_v1_client(
        contract,
        ["2026-04-21", "READY", "adil", "2026-04-21T17:01:00+05:00", "", "", "run-2", "OK"],
    )
    batch_root = _write_manifest(tmp_path)
    _write_telegram_ledger(batch_root, {"pdf-a": "confirmed", "pdf-b": "confirmed"})
    run_root = tmp_path / "workflow_runs"
    _write_apply_checkpoint(run_root, batch_root / "send_batch_manifest.json")

    state = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
        run_root=run_root,
    )

    assert state["delivery_completed"] is False
    assert state["delivery_status"] == "CHECKPOINT_REQUEST_IDENTITY_MISMATCH"
    assert state["request_identity_match"] is False
    assert state["completed"] is False


def test_whatsapp_completion_accepts_explicit_in_memory_delivery_proof(tmp_path: Path) -> None:
    batch_root = _write_manifest(tmp_path)
    (batch_root / "send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "batch_hash": json.loads(
                    (batch_root / "send_batch_manifest.json").read_text(encoding="utf-8")
                )["batch_hash"],
                "entries": {
                    "pdf-a": {"state": "confirmed"},
                    "pdf-b": {"state": "confirmed"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    strict = delivery_completion_state(
        today_folder=tmp_path,
        target_date=date(2026, 4, 21),
        run_root=tmp_path / "workflow_runs",
    )
    assert strict["completed"] is False
    assert strict["status"] == "UNPINNED_MANIFEST_DISCOVERY_ONLY"

    manifest_path = batch_root / "send_batch_manifest.json"
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    explicit = delivery_completion_state(
        today_folder=tmp_path,
        target_date=date(2026, 4, 21),
        run_root=tmp_path / "workflow_runs",
        explicit_delivery_channel="whatsapp",
        explicit_delivery_ok=True,
        manifest_path=manifest_path,
        expected_manifest_sha256=manifest_sha256,
    )
    assert explicit["completed"] is True
    assert explicit["channel"] == "whatsapp"
    assert explicit["status"] == "WHATSAPP_CONFIRMED"
    assert explicit["delivery_report_path"] == "explicit:send_waybills_delivery"


def test_delivery_completion_uses_pinned_manifest_not_newest_revision(tmp_path: Path) -> None:
    pinned_root = _write_manifest(tmp_path)
    pinned_manifest = pinned_root / "send_batch_manifest.json"
    pinned_payload = json.loads(pinned_manifest.read_text(encoding="utf-8"))
    _write_telegram_ledger(
        pinned_root,
        {"pdf-a": "confirmed", "pdf-b": "confirmed"},
        batch_hash=str(pinned_payload["batch_hash"]),
    )
    newer_root = pinned_root.with_name(f"{pinned_root.name}_r2")
    newer_root.mkdir(parents=True)
    newer_payload = json.loads(pinned_manifest.read_text(encoding="utf-8"))
    newer_payload["batch_label"] = newer_root.name
    newer_payload["batch_hash"] = compute_manifest_batch_hash(newer_payload)
    (newer_root / "send_batch_manifest.json").write_text(
        json.dumps(newer_payload),
        encoding="utf-8",
    )

    state = delivery_completion_state(
        today_folder=tmp_path,
        target_date=date(2026, 4, 21),
        manifest_path=pinned_manifest,
        expected_manifest_sha256=hashlib.sha256(pinned_manifest.read_bytes()).hexdigest(),
    )

    assert state["completed"] is True
    assert state["batch_root"] == str(pinned_root)
    assert state["manifest_path"] == str(pinned_manifest)


def test_delivery_completion_rejects_wrong_explicit_manifest_sha(tmp_path: Path) -> None:
    batch_root = _write_manifest(tmp_path)
    manifest_path = batch_root / "send_batch_manifest.json"

    state = delivery_completion_state(
        today_folder=tmp_path,
        target_date=date(2026, 4, 21),
        manifest_path=manifest_path,
        expected_manifest_sha256="0" * 64,
    )

    assert state["completed"] is False
    assert state["status"] == "PINNED_MANIFEST_SHA256_MISMATCH"
