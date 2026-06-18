import json
from datetime import date
from pathlib import Path

import pytest

from scripts import send_waybills_telegram as telegram_mod
from scripts.send_waybills_whatsapp import SOURCE_MERGED
from core.integrations import telegram_bot as telegram_bot_mod
from core.integrations.telegram_bot import get_waybill_telegram_config


def _write_manifest(today_root: Path, entries: list[dict]) -> Path:
    batch_root = today_root / "MERGED" / "SEND" / "21.04.26_MERGED_qnt2"
    pdf_dir = batch_root / "NORMAL_singles"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = b"%PDF-1.4\ntelegram-test\n"
    for entry in entries:
        (pdf_dir / entry["filename"]).write_bytes(pdf_bytes)

    payload_entries = []
    for entry in entries:
        payload_entries.append(
            {
                "pdf_key": entry["pdf_key"],
                "relative_output_path": f"NORMAL_singles/{entry['filename']}",
                "filename": entry["filename"],
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": "placeholder",
                "file_size": len(pdf_bytes),
                "mtime": "2026-04-21T00:00:00+05:00",
                "order_ids": [entry["order_id"]],
                "order_counts_by_store": {"Universal": 1},
                "source_row_ids": [f"{entry['order_id']}@2026-04-21#1"],
                "items_detail": [entry["filename"]],
                "send_sequence": entry["send_sequence"],
            }
        )
    payload = {
        "schema_version": 2,
        "batch_label": batch_root.name,
        "target_date": "2026-04-21",
        "source_root": str(batch_root),
        "batch_hash": "batchhash-telegram",
        "counts": {"pdfs": len(entries), "orders": len(entries), "overdue_orders": 0},
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "terminal_orders_excluded": True,
        "entries": payload_entries,
    }
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_root


@pytest.fixture(autouse=True)
def _avoid_real_handover_watch_state(monkeypatch):
    monkeypatch.setattr(
        telegram_mod,
        "arm_passive_handover_watch",
        lambda **_kwargs: {"armed": False},
        raising=False,
    )


def test_waybill_telegram_config_prefers_dedicated_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "generic-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_WAYBILL", "waybill-token")
    monkeypatch.setenv("TELEGRAM_WAYBILL_CHAT_ID", "-1001")

    config = get_waybill_telegram_config()

    assert config == {"token": "waybill-token", "chat_id": "-1001"}


def test_waybill_telegram_config_loads_project_dotenv_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN_WAYBILL", raising=False)
    monkeypatch.delenv("TELEGRAM_WAYBILL_CHAT_ID", raising=False)
    monkeypatch.setattr(telegram_bot_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=generic-file-token\n"
        "TELEGRAM_BOT_TOKEN_WAYBILL=waybill-file-token\n"
        "TELEGRAM_WAYBILL_CHAT_ID=-12345\n",
        encoding="utf-8",
    )

    config = get_waybill_telegram_config()

    assert config == {"token": "waybill-file-token", "chat_id": "-12345"}


def test_waybill_telegram_config_prefers_dedicated_dotenv_over_generic_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "generic-launchd-token")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN_WAYBILL", raising=False)
    monkeypatch.delenv("TELEGRAM_WAYBILL_CHAT_ID", raising=False)
    monkeypatch.setattr(telegram_bot_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN_WAYBILL=waybill-file-token\n"
        "TELEGRAM_WAYBILL_CHAT_ID=-12345\n",
        encoding="utf-8",
    )

    config = get_waybill_telegram_config()

    assert config == {"token": "waybill-file-token", "chat_id": "-12345"}


def test_telegram_request_errors_redact_bot_token(monkeypatch):
    def _raise_request_error(*args, **kwargs):
        raise telegram_bot_mod.requests.RequestException(
            "HTTPSConnectionPool(url='https://api.telegram.org/botsecret-token/sendMessage')"
        )

    monkeypatch.setattr(telegram_bot_mod.requests, "post", _raise_request_error)

    result = telegram_bot_mod.send_message(
        token="secret-token",
        chat_id="-12345",
        text="test",
    )

    assert result["success"] is False
    assert "secret-token" not in result["error"]
    assert "<redacted-token>" in result["error"]


def test_telegram_document_rate_limit_exposes_retry_after(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "bundle.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nrate-limit\n")

    class _Response:
        ok = False
        status_code = 429
        text = "Too Many Requests"

        def json(self):
            return {
                "ok": False,
                "description": "Too Many Requests: retry after 35",
                "parameters": {"retry_after": 35},
            }

    monkeypatch.setattr(telegram_bot_mod.requests, "post", lambda *args, **kwargs: _Response())

    result = telegram_bot_mod.send_document(
        token="secret-token",
        chat_id="-12345",
        document_path=pdf_path,
    )

    assert result["success"] is False
    assert result["ambiguous"] is False
    assert result["retry_after"] == 35


def test_telegram_sender_sends_manifest_sequence_and_records_ledger(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
            {"pdf_key": "pdf-b", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    sent_filenames: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent_filenames.append(Path(document_path).name)
        return {
            "success": True,
            "message_id": f"msg-{len(sent_filenames)}",
            "chat_id": chat_id,
            "date": 1776770000 + len(sent_filenames),
        }

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["sent"] == 2
    assert report["failed"] == 0
    assert sent_filenames == ["first.pdf", "second.pdf"]

    ledger = json.loads((batch_root / "telegram_send_ledger.json").read_text(encoding="utf-8"))
    assert ledger["channel"] == "telegram"
    assert ledger["entries"]["pdf-b"]["state"] == "confirmed"
    assert ledger["entries"]["pdf-b"]["telegram_message_id"] == "msg-1"
    assert ledger["entries"]["pdf-a"]["state"] == "confirmed"
    assert ledger["entries"]["pdf-a"]["telegram_message_id"] == "msg-2"


def test_telegram_sender_retries_rate_limited_documents(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    sleeps: list[float] = []
    responses = [
        {"success": False, "error": "Too Many Requests: retry after 3", "ambiguous": False, "retry_after": 3},
        {"success": True, "message_id": "msg-1", "chat_id": "-1001"},
    ]

    monkeypatch.setattr(telegram_mod.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(telegram_mod, "send_document", lambda **_kwargs: responses.pop(0))

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        fail_fast=True,
    )

    assert report["ok"] is True
    assert report["sent"] == 1
    assert report["failed"] == 0
    assert sleeps == [3]

    ledger = json.loads((batch_root / "telegram_send_ledger.json").read_text(encoding="utf-8"))
    assert ledger["entries"]["pdf-a"]["state"] == "confirmed"
    history_states = [item["state"] for item in ledger["entries"]["pdf-a"]["history"]]
    assert history_states == ["api_started", "confirmed"]


def test_telegram_sender_resume_skips_confirmed_entries(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    sent_filenames: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent_filenames.append(Path(document_path).name)
        return {"success": True, "message_id": f"msg-{len(sent_filenames)}", "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    first = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )
    second = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    assert first["sent"] == 2
    assert second["ok"] is True
    assert second["sent"] == 0
    assert second["skipped"] == 2
    assert sent_filenames == ["first.pdf", "second.pdf"]


def test_telegram_sender_resume_sends_only_failed_entries(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    ledger_path = batch_root / "telegram_send_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": "batchhash-telegram",
                "entries": {
                    "pdf-a": {"state": "confirmed", "history": []},
                    "pdf-b": {"state": "failed", "history": []},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    sent_filenames: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent_filenames.append(Path(document_path).name)
        return {"success": True, "message_id": "msg-resume", "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["sent"] == 1
    assert report["skipped"] == 1
    assert report["confirmed_total"] == 2
    assert sent_filenames == ["second.pdf"]


def test_telegram_sender_resume_caption_preserves_manifest_sequence(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": "batchhash-telegram",
                "entries": {
                    "pdf-a": {"state": "confirmed", "history": []},
                    "pdf-b": {"state": "failed", "history": []},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    captions: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        captions.append(caption)
        return {"success": True, "message_id": "msg-resume", "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["sent"] == 1
    assert captions == ["<b>2/2</b> second.pdf\n<code>21.04.26_MERGED_qnt2</code>\nOrders: <code>1002</code>"]


def test_telegram_sender_refuses_when_batch_lock_is_held(monkeypatch, tmp_path: Path):
    import fcntl

    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    lock_path = batch_root / ".telegram_send.lock"
    lock_path.touch()
    sent: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent.append(Path(document_path).name)
        return {"success": True, "message_id": "msg-1", "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    with lock_path.open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = telegram_mod.run_sender(
            today_folder=tmp_path,
            bundle_source=SOURCE_MERGED,
            expected_target_date=date(2026, 4, 21),
            token="token-1",
            chat_id="-1001",
            status_messages=False,
            send_delay=0,
        )

    assert report["ok"] is False
    assert report["halted"] is True
    assert report["halt_reason"] == "TELEGRAM_SEND_LOCKED"
    assert report["fallback_allowed"] is False
    assert sent == []


def test_telegram_sender_no_resume_reports_current_batch_confirmations_only(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": "batchhash-telegram",
                "entries": {
                    "pdf-a": {"state": "confirmed", "history": []},
                    "pdf-b": {"state": "confirmed", "history": []},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    captions: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        captions.append(caption)
        return {"success": True, "message_id": f"resend-{len(captions)}", "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        resume=False,
    )

    assert report["ok"] is True
    assert report["sent"] == 2
    assert report["skipped"] == 0
    assert report["confirmed_total"] == 2
    assert captions[0].startswith("<b>1/2</b>")
    assert captions[1].startswith("<b>2/2</b>")


def test_ordered_full_resend_reports_sequence_proof(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    sent_filenames: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent_filenames.append(Path(document_path).name)
        return {"success": True, "message_id": str(100 + len(sent_filenames)), "chat_id": chat_id}

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_ordered_full_resend(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["sent"] == 2
    assert report["confirmed_total"] == 2
    assert sent_filenames == ["first.pdf", "second.pdf"]
    assert report["ordered_resend_proof"]["ok"] is True
    assert report["ordered_resend_proof"]["sequence_match"] is True
    assert report["ordered_resend_proof"]["message_id_min"] == 101
    assert report["ordered_resend_proof"]["message_id_max"] == 102

    ledger = json.loads((batch_root / "telegram_send_ledger.json").read_text(encoding="utf-8"))
    assert ledger["entries"]["pdf-a"]["telegram_message_id"] == "101"
    assert ledger["entries"]["pdf-b"]["telegram_message_id"] == "102"


def test_telegram_sender_retries_rate_limited_final_status_message(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    sleeps: list[float] = []
    status_results = [
        {"success": True, "message_id": "pre-status", "chat_id": "-1001"},
        {"success": False, "error": "Too Many Requests: retry after 7", "retry_after": 7, "ambiguous": False},
        {"success": True, "message_id": "final-status", "chat_id": "-1001"},
        {"success": True, "message_id": "returns-status", "chat_id": "-1001"},
    ]

    monkeypatch.setattr(telegram_mod.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(telegram_mod, "send_document", lambda **_kwargs: {"success": True, "message_id": "doc-1", "chat_id": "-1001"})
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_pickup_ready_snapshot",
        lambda **_kwargs: {"total_orders": 0, "stores": []},
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "format_returns_pickup_message",
        lambda snapshot: "<b>Returns Pickup Ready</b>\nNone",
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_returns_pickup_reply_markup",
        lambda snapshot: {"keyboard": [["Возвраты"]], "resize_keyboard": True},
    )
    monkeypatch.setattr(telegram_mod, "send_message", lambda **_kwargs: status_results.pop(0))

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=True,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["final_status_sent"] is True
    assert report["final_status_message_id"] == "final-status"
    assert report["status_message_failures"] == 0
    assert sleeps == [7]


def test_telegram_sender_posts_returns_pickup_after_final_status(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    status_texts: list[str] = []

    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: {"success": True, "message_id": "doc-1", "chat_id": "-1001"},
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_pickup_ready_snapshot",
        lambda **_kwargs: {"total_orders": 2, "stores": [{"store_code": "ACMEWEAR", "display_name": "AcmeWear"}]},
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "format_returns_pickup_message",
        lambda snapshot: "<b>Returns Pickup Ready</b>\nAcmeWear: <code>1001</code>",
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_returns_pickup_reply_markup",
        lambda snapshot: {"keyboard": [["Возвраты"], ["Забрал OF"]], "resize_keyboard": True},
    )

    def _fake_send_message(**kwargs):
        status_texts.append(kwargs["text"])
        return {"success": True, "message_id": f"msg-{len(status_texts)}", "chat_id": "-1001"}

    monkeypatch.setattr(telegram_mod, "send_message", _fake_send_message)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=True,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["final_status_sent"] is True
    assert report["returns_pickup_sent"] is True
    assert any("Returns Pickup Ready" in text for text in status_texts)
    assert "Returns Pickup Ready" in status_texts[-1]


def test_telegram_sender_arms_passive_handover_watch_after_successful_status_messages(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    armed_calls: list[dict[str, object]] = []
    message_ids = iter(["pre-status", "final-status", "returns-status"])

    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: {"success": True, "message_id": "doc-1", "chat_id": "-1001"},
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_pickup_ready_snapshot",
        lambda **_kwargs: {"total_orders": 0, "stores": []},
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "format_returns_pickup_message",
        lambda snapshot: "<b>Returns Pickup Ready</b>\nNone",
    )
    monkeypatch.setattr(
        telegram_mod.returns_pickup_report_mod,
        "build_returns_pickup_reply_markup",
        lambda snapshot: {"keyboard": [["Возвраты"]], "resize_keyboard": True},
    )
    monkeypatch.setattr(
        telegram_mod,
        "send_message",
        lambda **_kwargs: {"success": True, "message_id": next(message_ids), "chat_id": "-1001"},
    )
    monkeypatch.setattr(
        telegram_mod,
        "arm_passive_handover_watch",
        lambda **kwargs: armed_calls.append(kwargs) or {"armed": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=True,
        send_delay=0,
    )

    assert report["ok"] is True
    assert report["handover_watch_armed"] is True
    assert len(armed_calls) == 1
    assert armed_calls[0]["chat_id"] == "-1001"
    assert armed_calls[0]["target_date"] == date(2026, 4, 21)


def test_telegram_partial_ambiguous_failure_blocks_fallback(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    responses = [
        {"success": True, "message_id": "msg-1", "chat_id": "-1001"},
        {"success": False, "error": "read timeout after upload", "ambiguous": True},
    ]

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        return responses.pop(0)

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        fail_fast=True,
    )

    assert report["ok"] is False
    assert report["sent"] == 1
    assert report["failed"] == 1
    assert report["halted"] is True
    assert report["halt_reason"] == "TELEGRAM_UNSURE"
    assert report["fallback_allowed"] is False

    ledger = json.loads((batch_root / "telegram_send_ledger.json").read_text(encoding="utf-8"))
    assert ledger["entries"]["pdf-a"]["state"] == "confirmed"
    assert ledger["entries"]["pdf-b"]["state"] == "unsure"
