from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.integrations.google_ops_board import load_ops_board_contract
from scripts import google_ops_board_automation_common as common_mod
from scripts.waybill_delivery_completion import delivery_completion_state


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])


def _write_manifest(today_root: Path, *, batch_hash: str = "batchhash-1") -> Path:
    batch_root = today_root / "MERGED" / "SEND" / "21.04.26_MERGED_qnt2"
    batch_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "batch_label": batch_root.name,
        "target_date": "2026-04-21",
        "source_root": str(batch_root),
        "batch_hash": batch_hash,
        "counts": {"pdfs": 2, "orders": 2},
        "entries": [
            {"pdf_key": "pdf-a", "filename": "a.pdf", "order_ids": ["1001"]},
            {"pdf_key": "pdf-b", "filename": "b.pdf", "order_ids": ["1002"]},
        ],
    }
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_root


def _write_telegram_ledger(batch_root: Path, states: dict[str, str], *, batch_hash: str = "batchhash-1") -> None:
    payload = {
        "schema_version": 1,
        "channel": "telegram",
        "batch_hash": batch_hash,
        "entries": {
            pdf_key: {"state": state, "history": []}
            for pdf_key, state in states.items()
        },
    }
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_closeout_completion_requires_confirmed_delivery_ledger(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-21", "READY", "adil", "", "", "", "run-1", "OK"],
            ]
        }
    )
    batch_root = _write_manifest(tmp_path)

    missing = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
    )
    assert missing["completed"] is False
    assert missing["delivery_status"] == "TELEGRAM_LEDGER_MISSING"

    _write_telegram_ledger(batch_root, {"pdf-a": "confirmed", "pdf-b": "pending"})
    partial = common_mod.closeout_completion_state(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 21),
        today_folder=tmp_path,
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
    )
    assert complete["completed"] is True
    assert complete["delivery_channel"] == "telegram"
    assert complete["delivery_confirmed_count"] == 2


def test_whatsapp_completion_requires_explicit_delivery_report(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-21", "READY", "adil", "", "", "", "run-1", "OK"],
            ]
        }
    )
    batch_root = _write_manifest(tmp_path)
    (batch_root / "send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "batch_hash": "batchhash-1",
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
        run_root=tmp_path / "workflow_runs",
    )
    assert without_report["completed"] is False
    assert without_report["delivery_status"] == "TELEGRAM_LEDGER_MISSING"

    run_dir = tmp_path / "workflow_runs" / "2026-04-21" / "run-1"
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
        run_root=tmp_path / "workflow_runs",
    )
    assert with_report["completed"] is True
    assert with_report["delivery_channel"] == "whatsapp"


def test_whatsapp_completion_accepts_explicit_in_memory_delivery_proof(tmp_path: Path) -> None:
    batch_root = _write_manifest(tmp_path)
    (batch_root / "send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "batch_hash": "batchhash-1",
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
    assert strict["status"] == "TELEGRAM_LEDGER_MISSING"

    explicit = delivery_completion_state(
        today_folder=tmp_path,
        target_date=date(2026, 4, 21),
        run_root=tmp_path / "workflow_runs",
        explicit_delivery_channel="whatsapp",
        explicit_delivery_ok=True,
    )
    assert explicit["completed"] is True
    assert explicit["channel"] == "whatsapp"
    assert explicit["status"] == "WHATSAPP_CONFIRMED"
    assert explicit["delivery_report_path"] == "explicit:send_waybills_delivery"
