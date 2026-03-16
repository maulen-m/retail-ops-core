import json
from pathlib import Path

import pytest

from scripts.send_waybills_whatsapp import (
    SOURCE_MERGED,
    load_send_batch_manifest,
    load_send_ledger,
    run_sender,
    save_send_ledger,
    select_manifest_entries_for_send,
    transition_send_ledger_entry,
    verify_send_batch_preflight,
)


def _write_batch_manifest(today_root: Path, *, filename: str = "a.pdf") -> tuple[Path, Path, dict]:
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt1"
    pdf_dir = batch_root / "NORMAL_singles"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / filename
    pdf_bytes = b"%PDF-1.4\nmanifest-test\n"
    pdf_path.write_bytes(pdf_bytes)

    payload = {
        "schema_version": 2,
        "batch_label": batch_root.name,
        "target_date": "2026-03-10",
        "source_root": str(batch_root),
        "batch_hash": "batchhash-1",
        "counts": {"pdfs": 1, "orders": 1, "overdue_orders": 0},
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "terminal_orders_excluded": True,
        "entries": [
            {
                "pdf_key": "pdfkey-1",
                "relative_output_path": f"NORMAL_singles/{filename}",
                "filename": filename,
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": "placeholder",
                "file_size": len(pdf_bytes),
                "mtime": "2026-03-10T00:00:00",
                "order_ids": ["1001"],
                "order_counts_by_store": {"Universal": 1},
                "source_row_ids": ["1001@2026-03-10#1"],
                "items_detail": ["Футболка_черная-L-1"],
                "send_sequence": 1,
            }
        ],
    }
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return batch_root, pdf_path, payload


def test_transition_send_ledger_entry_disallows_second_click_for_same_pdf_key(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")

    with pytest.raises(RuntimeError, match="clicked"):
        transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")


def test_select_manifest_entries_for_send_uses_pdf_key_and_allows_explicit_unsure_resume(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "unsure")
    save_send_ledger(ledger_path, ledger)

    assert select_manifest_entries_for_send(manifest_payload, ledger, allow_unsure_resume=False) == []
    entries = select_manifest_entries_for_send(manifest_payload, ledger, allow_unsure_resume=True)
    assert [entry["pdf_key"] for entry in entries] == ["pdfkey-1"]


def test_select_manifest_entries_for_send_retries_failed_pre_click_entry(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "failed")
    save_send_ledger(ledger_path, ledger)

    entries = select_manifest_entries_for_send(manifest_payload, ledger, allow_unsure_resume=False)

    assert [entry["pdf_key"] for entry in entries] == ["pdfkey-1"]


def test_transition_send_ledger_entry_allows_failed_pre_click_entry_to_reopen(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "failed")

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")

    assert ledger["entries"]["pdfkey-1"]["state"] == "opened"


def test_load_send_batch_manifest_recovers_after_filename_rename_using_pdf_key(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, pdf_path, _ = _write_batch_manifest(today_root)
    renamed_path = pdf_path.with_name("renamed.pdf")
    pdf_path.rename(renamed_path)

    manifest = load_send_batch_manifest(today_root, source_mode=SOURCE_MERGED)

    assert manifest["entries"][0]["pdf_key"] == "pdfkey-1"
    assert manifest["entries"][0]["path"] == renamed_path


def test_verify_send_batch_preflight_fails_when_overdue_orders_are_missing_from_send(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, payload = _write_batch_manifest(today_root)
    payload["overdue_order_ids"] = ["1001", "2002"]
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    preflight = verify_send_batch_preflight(today_root, source_mode=SOURCE_MERGED)

    assert preflight["ok"] is False
    assert any(issue["code"] == "overdue_missing_from_send" for issue in preflight["issues"])


def test_verify_send_batch_preflight_fails_when_entry_store_counts_exceed_unique_orders(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, payload = _write_batch_manifest(today_root)
    payload["entries"][0]["logical_group_type"] = "MULTI_LINE"
    payload["entries"][0]["order_counts_by_store"] = {"Universal": 2}
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    preflight = verify_send_batch_preflight(today_root, source_mode=SOURCE_MERGED)

    assert preflight["ok"] is False
    assert any(issue["code"] == "entry_store_order_count_mismatch" for issue in preflight["issues"])


def test_verify_send_batch_preflight_fails_when_manifest_order_total_drifts_from_entries(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, payload = _write_batch_manifest(today_root)
    payload["counts"]["orders"] = 2
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    preflight = verify_send_batch_preflight(today_root, source_mode=SOURCE_MERGED)

    assert preflight["ok"] is False
    assert any(issue["code"] == "manifest_order_total_mismatch" for issue in preflight["issues"])


def test_verify_send_batch_preflight_fails_when_send_sequence_missing(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, payload = _write_batch_manifest(today_root)
    payload["entries"][0].pop("send_sequence")
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    preflight = verify_send_batch_preflight(today_root, source_mode=SOURCE_MERGED)

    assert preflight["ok"] is False
    assert any(issue["code"] == "entry_send_sequence_missing" for issue in preflight["issues"])


def test_run_sender_marks_unsure_and_halts_without_second_send_attempt(tmp_path: Path, monkeypatch) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, _ = _write_batch_manifest(today_root)

    class _FakeSender:
        send_clicks = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def send_text_message(self, text: str) -> None:
            return None

        def prepare_document(self, pdf_path: Path) -> None:
            return None

        def _outgoing_message_count(self) -> int:
            return 0

        def click_document_send(self) -> None:
            _FakeSender.send_clicks += 1

        def confirm_document_sent(self, expected_filename: str, previous_outgoing: int | None = None) -> None:
            raise RuntimeError("UNSURE: document bubble did not confirm expected filename")

        def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
            return None

    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)

    results = run_sender(
        today_folder=today_root,
        chat_title="Заказы",
        dry_run=False,
        resume=True,
        bundle_source=SOURCE_MERGED,
        status_messages=False,
        fail_fast=False,
        verbose=False,
    )

    ledger = json.loads((batch_root / "send_ledger.json").read_text(encoding="utf-8"))
    assert _FakeSender.send_clicks == 1
    assert results["sent"] == 0
    assert results["halted"] is True
    assert results["halt_reason"] == "UNSURE"
    assert ledger["entries"]["pdfkey-1"]["state"] == "unsure"


def test_run_sender_tracks_pre_and_post_status_message_failures(tmp_path: Path, monkeypatch) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    class _FakeSender:
        status_attempts = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def send_text_message(self, text: str) -> None:
            _FakeSender.status_attempts += 1
            raise RuntimeError("text confirmation timeout")

        def prepare_document(self, pdf_path: Path) -> None:
            return None

        def _outgoing_message_count(self) -> int:
            return 0

        def click_document_send(self) -> None:
            return None

        def confirm_document_sent(self, expected_filename: str, previous_outgoing: int | None = None) -> None:
            return None

        def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
            return None

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)

    results = run_sender(
        today_folder=today_root,
        chat_title="Заказы",
        dry_run=False,
        resume=True,
        bundle_source=SOURCE_MERGED,
        status_messages=True,
        fail_fast=False,
        verbose=False,
    )

    assert results["sent"] == 1
    assert results["failed"] == 0
    assert results["status_message_failed"] == 1
    assert results["status_message_failures"] == 2
    assert results["status_message_failures_by_phase"] == {"pre": 1, "post": 1}


def test_run_sender_passes_previous_outgoing_count_to_confirm_document_sent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    class _FakeSender:
        previous_outgoing_values = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def _outgoing_message_count(self) -> int:
            return 11

        def prepare_document(self, pdf_path: Path) -> None:
            return None

        def click_document_send(self) -> None:
            return None

        def confirm_document_sent(self, expected_filename: str, previous_outgoing: int | None = None) -> None:
            _FakeSender.previous_outgoing_values.append(previous_outgoing)

        def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
            return None

    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)

    results = run_sender(
        today_folder=today_root,
        chat_title="Заказы",
        dry_run=False,
        resume=True,
        bundle_source=SOURCE_MERGED,
        status_messages=False,
        fail_fast=True,
        verbose=False,
    )

    assert results["sent"] == 1
    assert _FakeSender.previous_outgoing_values == [11]
