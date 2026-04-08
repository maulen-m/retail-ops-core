import json
from datetime import date
from pathlib import Path

import pytest

from scripts.send_waybills_whatsapp import (
    SOURCE_MERGED,
    run_sender_smoke_check,
    load_send_batch_manifest,
    load_send_ledger,
    resolve_unsure_ledger_entry,
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


def _write_three_entry_batch_manifest(today_root: Path) -> tuple[Path, dict]:
    batch_root = today_root / "MERGED" / "SEND" / "10.03.26_MERGED_qnt3"
    pdf_dir = batch_root / "NORMAL_singles"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    filenames = ["confirmed.pdf", "unsure.pdf", "pending.pdf"]
    pdf_bytes = b"%PDF-1.4\nmanifest-test\n"
    for name in filenames:
        (pdf_dir / name).write_bytes(pdf_bytes)

    payload = {
        "schema_version": 2,
        "batch_label": batch_root.name,
        "target_date": "2026-03-10",
        "source_root": str(batch_root),
        "batch_hash": "batchhash-3",
        "counts": {"pdfs": 3, "orders": 3, "overdue_orders": 0},
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "terminal_orders_excluded": True,
        "entries": [
            {
                "pdf_key": "pdfkey-1",
                "relative_output_path": "NORMAL_singles/confirmed.pdf",
                "filename": "confirmed.pdf",
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": "placeholder-1",
                "file_size": len(pdf_bytes),
                "mtime": "2026-03-10T00:00:00",
                "order_ids": ["1001"],
                "order_counts_by_store": {"Universal": 1},
                "source_row_ids": ["1001@2026-03-10#1"],
                "items_detail": ["confirmed-L-1"],
                "send_sequence": 1,
            },
            {
                "pdf_key": "pdfkey-2",
                "relative_output_path": "NORMAL_singles/unsure.pdf",
                "filename": "unsure.pdf",
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": "placeholder-2",
                "file_size": len(pdf_bytes),
                "mtime": "2026-03-10T00:00:00",
                "order_ids": ["1002"],
                "order_counts_by_store": {"Universal": 1},
                "source_row_ids": ["1002@2026-03-10#1"],
                "items_detail": ["unsure-L-1"],
                "send_sequence": 2,
            },
            {
                "pdf_key": "pdfkey-3",
                "relative_output_path": "NORMAL_singles/pending.pdf",
                "filename": "pending.pdf",
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": "placeholder-3",
                "file_size": len(pdf_bytes),
                "mtime": "2026-03-10T00:00:00",
                "order_ids": ["1003"],
                "order_counts_by_store": {"Universal": 1},
                "source_row_ids": ["1003@2026-03-10#1"],
                "items_detail": ["pending-L-1"],
                "send_sequence": 3,
            },
        ],
    }
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return batch_root, payload


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


def test_resolve_unsure_ledger_entry_to_confirmed_keeps_only_later_pending_resumable(
    tmp_path: Path,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, manifest_payload = _write_three_entry_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-1", "confirmed")
    transition_send_ledger_entry(ledger, "pdfkey-2", "unsure")

    resolved_key = resolve_unsure_ledger_entry(
        manifest_payload,
        ledger,
        filename="unsure.pdf",
        resolution="confirmed",
    )

    resumable = select_manifest_entries_for_send(manifest_payload, ledger, allow_unsure_resume=False)

    assert resolved_key == "pdfkey-2"
    assert ledger["entries"]["pdfkey-2"]["state"] == "confirmed"
    assert [entry["pdf_key"] for entry in resumable] == ["pdfkey-3"]


def test_resolve_unsure_ledger_entry_to_pending_keeps_confirmed_entries_skipped(
    tmp_path: Path,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, manifest_payload = _write_three_entry_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-1", "confirmed")
    transition_send_ledger_entry(ledger, "pdfkey-2", "unsure")

    resolved_key = resolve_unsure_ledger_entry(
        manifest_payload,
        ledger,
        filename="unsure.pdf",
        resolution="pending",
    )

    resumable = select_manifest_entries_for_send(manifest_payload, ledger, allow_unsure_resume=False)

    assert resolved_key == "pdfkey-2"
    assert ledger["entries"]["pdfkey-2"]["state"] == "pending"
    assert [entry["pdf_key"] for entry in resumable] == ["pdfkey-2", "pdfkey-3"]


def test_load_send_batch_manifest_recovers_after_filename_rename_using_pdf_key(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root, pdf_path, _ = _write_batch_manifest(today_root)
    renamed_path = pdf_path.with_name("renamed.pdf")
    pdf_path.rename(renamed_path)

    manifest = load_send_batch_manifest(today_root, source_mode=SOURCE_MERGED)

    assert manifest["entries"][0]["pdf_key"] == "pdfkey-1"
    assert manifest["entries"][0]["path"] == renamed_path


def test_load_send_batch_manifest_prefers_latest_send_batch_revision(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    old_batch_root, _, payload = _write_batch_manifest(today_root)
    new_batch_root = old_batch_root.with_name(f"{old_batch_root.name}_r2")
    new_batch_root.mkdir(parents=True, exist_ok=True)
    pdf_dir = new_batch_root / "NORMAL_singles"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "newer.pdf"
    pdf_bytes = b"%PDF-1.4\nnewer\n"
    pdf_path.write_bytes(pdf_bytes)
    newer_payload = dict(payload)
    newer_payload["batch_label"] = new_batch_root.name
    newer_payload["batch_hash"] = "batchhash-2"
    newer_payload["entries"] = [
        {
            **payload["entries"][0],
            "pdf_key": "pdfkey-2",
            "relative_output_path": "NORMAL_singles/newer.pdf",
            "filename": "newer.pdf",
            "sha256": "placeholder-newer",
            "file_size": len(pdf_bytes),
        }
    ]
    (new_batch_root / "send_batch_manifest.json").write_text(
        json.dumps(newer_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = load_send_batch_manifest(today_root, source_mode=SOURCE_MERGED)

    assert Path(manifest["batch_root"]) == new_batch_root
    assert manifest["entries"][0]["filename"] == "newer.pdf"


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


def test_verify_send_batch_preflight_fails_when_batch_target_date_is_stale(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    preflight = verify_send_batch_preflight(
        today_root,
        source_mode=SOURCE_MERGED,
        expected_target_date=date(2026, 3, 11),
    )

    assert preflight["ok"] is False
    assert any(issue["code"] == "target_date_mismatch" for issue in preflight["issues"])


def test_verify_send_batch_preflight_allows_expected_stale_batch_with_override(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    preflight = verify_send_batch_preflight(
        today_root,
        source_mode=SOURCE_MERGED,
        expected_target_date=date(2026, 3, 11),
        allow_stale_batch=True,
    )

    assert preflight["ok"] is True


def test_run_sender_stops_on_stale_batch_before_opening_whatsapp(tmp_path: Path, monkeypatch) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    class _ShouldNotStartSender:
        def __init__(self, *args, **kwargs):
            raise AssertionError("WhatsApp sender should not start for stale batch")

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _ShouldNotStartSender)

    results = run_sender(
        today_folder=today_root,
        chat_title="Заказы",
        dry_run=False,
        resume=True,
        bundle_source=SOURCE_MERGED,
        status_messages=True,
        fail_fast=True,
        verbose=False,
        expected_target_date=date(2026, 3, 11),
    )

    assert results["sent"] == 0
    assert results["halted"] is True
    assert results["halt_reason"] == "PREFLIGHT_RED"


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


def test_run_sender_fails_closed_before_pre_status_when_document_controls_are_not_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, _ = _write_batch_manifest(today_root)

    class _FakeSender:
        status_attempted = False

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def assert_document_send_ready(self) -> None:
            raise RuntimeError("Document upload controls not ready in target chat")

        def send_text_message(self, text: str) -> None:
            _FakeSender.status_attempted = True

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)

    results = run_sender(
        today_folder=today_root,
        chat_title="Заказы",
        dry_run=False,
        resume=True,
        bundle_source=SOURCE_MERGED,
        status_messages=True,
        fail_fast=True,
        verbose=False,
    )

    ledger = json.loads((batch_root / "send_ledger.json").read_text(encoding="utf-8"))
    assert _FakeSender.status_attempted is False
    assert results["sent"] == 0
    assert results["halted"] is True
    assert results["halt_reason"] == "RUNTIME_ERROR"
    assert ledger["entries"]["pdfkey-1"]["state"] == "pending"


def test_run_sender_smoke_check_fails_closed_and_returns_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, _ = _write_batch_manifest(today_root)

    class _FakeSender:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def assert_document_send_ready(self) -> None:
            raise RuntimeError("Document upload controls not ready in target chat")

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)
    monkeypatch.setattr(
        "scripts.send_waybills_whatsapp.capture_sender_failure_diagnostics",
        lambda *args, **kwargs: {
            "diagnostics_dir": str(today_root / "whatsapp_diagnostics" / "fake"),
            "recovery_ladder": [{"code": "playwright_retry"}],
        },
    )

    result = run_sender_smoke_check(
        today_folder=today_root,
        chat_title="Заказы",
        bundle_source=SOURCE_MERGED,
        chrome_user_data_dir=Path("/tmp/chrome"),
        chrome_profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
        expected_target_date=date(2026, 3, 10),
        allow_stale_batch=False,
        verbose=False,
    )

    assert result["ok"] is False
    assert result["issues"][0]["code"] == "smoke_check_failed"
    assert result["batch_root"] == str(batch_root)
    assert result["diagnostics_dir"].endswith("/whatsapp_diagnostics/fake")
    assert result["recovery_ladder"][0]["code"] == "playwright_retry"


def test_run_sender_fail_fast_writes_stopline_with_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, _ = _write_batch_manifest(today_root)

    class _FakeSender:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def assert_document_send_ready(self) -> None:
            return None

        def prepare_document(self, pdf_path: Path) -> None:
            raise RuntimeError("document menu item missing")

        def send_text_message(self, text: str) -> None:
            return None

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _FakeSender)
    monkeypatch.setattr(
        "scripts.send_waybills_whatsapp.capture_sender_failure_diagnostics",
        lambda *args, **kwargs: {
            "diagnostics_dir": str(today_root / "whatsapp_diagnostics" / "failed"),
            "recovery_ladder": [{"code": "chrome_existing_tab"}],
        },
    )

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

    stopline = json.loads((today_root / "whatsapp_send_stopline.json").read_text(encoding="utf-8"))
    assert results["halted"] is True
    assert results["halt_reason"] == "FAILED"
    assert results["diagnostics_dir"].endswith("/whatsapp_diagnostics/failed")
    assert stopline["diagnostics_dir"].endswith("/whatsapp_diagnostics/failed")
    assert stopline["recovery_ladder"][0]["code"] == "chrome_existing_tab"
    assert stopline["filename"] == "a.pdf"


def test_run_sender_can_send_only_post_status_message(tmp_path: Path, monkeypatch) -> None:
    today_root = tmp_path / "Today"
    _write_batch_manifest(today_root)

    class _FakeSender:
        status_payloads = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def send_text_message(self, text: str) -> None:
            _FakeSender.status_payloads.append(text)

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
        status_messages=False,
        post_status_message_only=True,
        fail_fast=False,
        verbose=False,
    )

    assert results["sent"] == 1
    assert len(_FakeSender.status_payloads) == 1
    assert "Orders Sent" in _FakeSender.status_payloads[0]


def test_run_sender_post_status_includes_prior_confirmed_entries_on_resume(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, manifest_payload = _write_three_entry_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)

    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-1", "confirmed")
    transition_send_ledger_entry(ledger, "pdfkey-2", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-2", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-2", "confirmed")
    save_send_ledger(ledger_path, ledger)

    class _FakeSender:
        status_payloads = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def send_text_message(self, text: str) -> None:
            _FakeSender.status_payloads.append(text)

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
        status_messages=False,
        post_status_message_only=True,
        fail_fast=False,
        verbose=False,
    )

    assert results["sent"] == 1
    assert results["skipped"] == 2
    assert len(_FakeSender.status_payloads) == 1
    assert "| TOTAL     | 3" in _FakeSender.status_payloads[0]
    assert "Bundles: target=3, sent=3" in _FakeSender.status_payloads[0]


def test_run_sender_post_status_only_can_emit_corrected_summary_when_batch_is_already_complete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)
    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-1", "confirmed")
    save_send_ledger(ledger_path, ledger)

    class _FakeSender:
        status_payloads = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def send_text_message(self, text: str) -> None:
            _FakeSender.status_payloads.append(text)

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
        status_messages=False,
        post_status_message_only=True,
        fail_fast=False,
        verbose=False,
    )

    assert results["sent"] == 0
    assert results["skipped"] == 1
    assert len(_FakeSender.status_payloads) == 1
    assert "Orders Sent" in _FakeSender.status_payloads[0]
    assert "Bundles: target=1, sent=1" in _FakeSender.status_payloads[0]


def test_run_sender_already_complete_batch_skips_implicit_post_status_rerun(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    batch_root, _, manifest_payload = _write_batch_manifest(today_root)
    ledger_path = batch_root / "send_ledger.json"
    ledger = load_send_ledger(ledger_path, manifest_payload)
    transition_send_ledger_entry(ledger, "pdfkey-1", "opened")
    transition_send_ledger_entry(ledger, "pdfkey-1", "clicked")
    transition_send_ledger_entry(ledger, "pdfkey-1", "confirmed")
    save_send_ledger(ledger_path, ledger)

    class _ShouldNotStartSender:
        def __init__(self, *args, **kwargs):
            raise AssertionError("WhatsApp sender should not start for a no-op complete rerun")

    monkeypatch.setattr("scripts.send_waybills_whatsapp.check_playwright", lambda: True)
    monkeypatch.setattr("scripts.send_waybills_whatsapp.WhatsAppSender", _ShouldNotStartSender)

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

    assert results["sent"] == 0
    assert results["skipped"] == 1
    assert results["status_message_failed"] == 0
    assert results["status_message_failures"] == 0


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


def test_run_sender_can_limit_live_run_to_one_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    today_root = tmp_path / "Today"
    _write_three_entry_batch_manifest(today_root)

    class _FakeSender:
        prepared = []
        confirmed = []

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            return None

        def _outgoing_message_count(self) -> int:
            return 0

        def prepare_document(self, pdf_path: Path) -> None:
            _FakeSender.prepared.append(pdf_path.name)

        def click_document_send(self) -> None:
            return None

        def confirm_document_sent(self, expected_filename: str, previous_outgoing: int | None = None) -> None:
            _FakeSender.confirmed.append(expected_filename)

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
        max_pdfs=1,
        verbose=False,
    )

    assert results["sent"] == 1
    assert results["skipped"] == 2
    assert _FakeSender.prepared == ["confirmed.pdf"]
    assert _FakeSender.confirmed == ["confirmed.pdf"]
