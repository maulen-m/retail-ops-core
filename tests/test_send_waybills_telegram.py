import json
import hashlib
from datetime import date
from pathlib import Path

import pytest

from scripts import send_waybills_telegram as telegram_mod
from scripts.send_waybills_whatsapp import SOURCE_MERGED, _manifest_batch_hash
from core.integrations import telegram_bot as telegram_bot_mod
from core.integrations.telegram_bot import get_waybill_telegram_config


def _write_manifest(
    today_root: Path,
    entries: list[dict],
    *,
    target_date: str = "2026-04-21",
    ready_set_at: str | None = None,
    batch_label: str = "21.04.26_MERGED_qnt2",
    store_counts_by_pdf_key: dict[str, dict[str, int]] | None = None,
) -> Path:
    batch_root = today_root / "MERGED" / "SEND" / batch_label
    pdf_dir = batch_root / "NORMAL_singles"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = b"%PDF-1.4\ntelegram-test\n"
    ready_identity = ready_set_at or f"{target_date}T17:00:00+05:00"
    for entry in entries:
        (pdf_dir / entry["filename"]).write_bytes(pdf_bytes)

    payload_entries = []
    for entry in entries:
        order_ids = list(entry.get("order_ids") or [entry["order_id"]])
        payload_entries.append(
            {
                "pdf_key": entry["pdf_key"],
                "relative_output_path": f"NORMAL_singles/{entry['filename']}",
                "filename": entry["filename"],
                "category": "NORMAL_singles",
                "logical_group_type": "NORMAL",
                "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "file_size": len(pdf_bytes),
                "mtime": "2026-04-21T00:00:00+05:00",
                "order_ids": order_ids,
                "order_counts_by_store": dict(
                    (store_counts_by_pdf_key or {}).get(
                        entry["pdf_key"],
                        {"Universal": 1},
                    )
                ),
                "source_row_ids": [
                    f"{order_id}@2026-04-21#1" for order_id in order_ids
                ],
                "items_detail": [entry["filename"]],
                "send_sequence": entry["send_sequence"],
            }
        )
    payload = {
        "schema_version": 4,
        "batch_label": batch_root.name,
        "target_date": target_date,
        "ready_set_at": ready_identity,
        "request_identity": {
            "target_date": target_date,
            "ready_set_at": ready_identity,
        },
        "expected_orders_sha256": "b" * 64,
        "obligation_scope_hash": "c" * 64,
        "line_scope_hash": "d" * 64,
        "source_root": str(batch_root),
        "batch_hash": "",
        "counts": {
            "pdfs": len(entries),
            "orders": sum(
                len(entry.get("order_ids") or [entry["order_id"]])
                for entry in entries
            ),
            "overdue_orders": 0,
        },
        "overdue_order_ids": [],
        "missing_overdue_order_ids": [],
        "send_order_ids": sorted(
            order_id
            for entry in entries
            for order_id in (entry.get("order_ids") or [entry["order_id"]])
        ),
        "terminal_orders_excluded": True,
        "entries": payload_entries,
    }
    payload["batch_hash"] = _manifest_batch_hash(payload)
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return batch_root


def _batch_hash(batch_root: Path) -> str:
    return json.loads(
        (batch_root / "send_batch_manifest.json").read_text(encoding="utf-8")
    )["batch_hash"]


def _write_telegram_ledger(
    batch_root: Path,
    *,
    state: str,
    chat_id: str = "-1001",
) -> Path:
    manifest = json.loads(
        (batch_root / "send_batch_manifest.json").read_text(encoding="utf-8")
    )
    manifest_entry = manifest["entries"][0]
    ledger_entry = {
        **telegram_mod._default_ledger_entry(manifest_entry),
        "state": state,
    }
    if state == "confirmed":
        ledger_entry.update(
            {
                "last_updated": "2026-04-21T17:01:00+05:00",
                "history": [
                    {
                        "state": "confirmed",
                        "at": "2026-04-21T17:01:00+05:00",
                        "note": "test fixture",
                    }
                ],
                "telegram_chat_id": chat_id,
                "telegram_message_id": "message-1",
            }
        )
    ledger_path = batch_root / "telegram_send_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": manifest["batch_hash"],
                "batch_label": manifest["batch_label"],
                "telegram_chat_id": chat_id,
                "created_at": "2026-04-21T17:00:00+05:00",
                "updated_at": "2026-04-21T17:01:00+05:00",
                "entries": {manifest_entry["pdf_key"]: ledger_entry},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger_path


@pytest.fixture(autouse=True)
def _avoid_real_handover_watch_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        telegram_mod,
        "arm_passive_handover_watch",
        lambda **_kwargs: {"armed": False},
        raising=False,
    )
    real_run_sender = telegram_mod.run_sender

    def _identity_pinned_run_sender(*args, **kwargs):
        if not bool(kwargs.get("dry_run")) and kwargs.get("manifest_path") is None:
            today_folder = Path(kwargs.get("today_folder") or args[0])
            manifests = sorted(
                (today_folder / "MERGED" / "SEND").glob("*/send_batch_manifest.json")
            )
            if len(manifests) == 1:
                kwargs["manifest_path"] = manifests[0]
                kwargs["expected_manifest_sha256"] = hashlib.sha256(
                    manifests[0].read_bytes()
                ).hexdigest()
        return real_run_sender(*args, **kwargs)

    monkeypatch.setattr(telegram_mod, "run_sender", _identity_pinned_run_sender)
    monkeypatch.setattr(
        telegram_mod,
        "CLOSEOUT_HALT_BARRIER_PATH",
        tmp_path / "closeout_halt_barrier.json",
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


def test_store_filter_dry_run_selects_only_store_pure_entries_without_ledger_write(
    tmp_path: Path,
) -> None:
    entries = [
        {"pdf_key": "pdf-a", "filename": "a.pdf", "order_id": "A", "send_sequence": 1},
        {"pdf_key": "pdf-b", "filename": "b.pdf", "order_id": "B", "send_sequence": 2},
        {"pdf_key": "pdf-c", "filename": "c.pdf", "order_id": "C", "send_sequence": 3},
    ]
    batch_root = _write_manifest(
        tmp_path,
        entries,
        store_counts_by_pdf_key={
            "pdf-a": {"Universal": 1},
            "pdf-b": {"AcmeWear": 1},
            "pdf-c": {"30000001_PP1": 1},
        },
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token",
        chat_id="-1001",
        dry_run=True,
        status_messages=False,
        stores=["UNIVERSAL"],
    )

    assert report["ok"] is True
    assert report["store_filter_codes"] == ["UNIVERSAL"]
    assert report["manifest_total"] == 3
    assert report["total"] == 2
    assert report["sent"] == 2
    assert not (batch_root / "telegram_send_ledger.json").exists()


def test_store_filter_fails_closed_on_mixed_entry_before_any_send(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch_root = _write_manifest(
        tmp_path,
        [
            {
                "pdf_key": "pdf-mixed",
                "filename": "mixed.pdf",
                "order_id": "MIXED",
                "order_ids": ["MIXED-UNIVERSAL", "MIXED-ACMEWEAR"],
                "send_sequence": 1,
            }
        ],
        store_counts_by_pdf_key={
            "pdf-mixed": {"Universal": 1, "AcmeWear": 1},
        },
    )
    sends: list[dict] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **kwargs: sends.append(kwargs) or {"success": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token",
        chat_id="-1001",
        dry_run=True,
        status_messages=False,
        stores=["UNIVERSAL"],
    )

    assert report["ok"] is False
    assert report["halt_reason"] == "TELEGRAM_STORE_SCOPE_MIXED"
    assert report["mixed_entries"] == [
        {
            "pdf_key": "pdf-mixed",
            "filename": "mixed.pdf",
            "store_codes": ["ACMEWEAR", "UNIVERSAL"],
        }
    ]
    assert sends == []
    assert not (batch_root / "telegram_send_ledger.json").exists()


def test_sender_without_store_filter_keeps_full_manifest_behavior(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "a.pdf", "order_id": "A", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "b.pdf", "order_id": "B", "send_sequence": 2},
        ],
        store_counts_by_pdf_key={
            "pdf-a": {"Universal": 1},
            "pdf-b": {"AcmeWear": 1},
        },
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token",
        chat_id="-1001",
        dry_run=True,
        status_messages=False,
    )

    assert report["ok"] is True
    assert report["total"] == 2
    assert report["sent"] == 2
    assert "store_filter_codes" not in report


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


def test_telegram_sender_halt_after_first_pdf_leaves_second_pending(
    monkeypatch,
    tmp_path: Path,
):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
            {"pdf_key": "pdf-b", "filename": "second.pdf", "order_id": "1002", "send_sequence": 2},
        ],
    )
    halt_path = tmp_path / "closeout_halt_barrier.json"
    sent_filenames: list[str] = []
    status_messages: list[str] = []

    def _fake_send_document(*, token, chat_id, document_path, caption, timeout_seconds):
        sent_filenames.append(Path(document_path).name)
        if len(sent_filenames) == 1:
            halt_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_date": "2026-04-21",
                        "halt_requested_at": "2026-04-21T17:01:00+05:00",
                        "source": "test:/halt",
                        "halt_request_key": "telegram_update:1",
                        "state": "PENDING_HOLD",
                        "blocks_automation": True,
                        "updated_at": "2026-04-21T17:01:00+05:00",
                    }
                ),
                encoding="utf-8",
            )
        return {
            "success": True,
            "message_id": f"msg-{len(sent_filenames)}",
            "chat_id": chat_id,
        }

    def _fake_send_message(**kwargs):
        status_messages.append(str(kwargs["text"]))
        return {
            "success": True,
            "message_id": f"status-{len(status_messages)}",
            "chat_id": kwargs["chat_id"],
        }

    monkeypatch.setattr(telegram_mod, "send_document", _fake_send_document)
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

    assert report["ok"] is False
    assert report["halted"] is True
    assert report["halt_reason"] == "TELEGRAM_HALT_BARRIER"
    assert report["halt_gate_reason"] == "REQUEST_HALTED"
    assert report["fallback_allowed"] is False
    assert report["sent"] == 1
    assert report["confirmed_total"] == 1
    assert sent_filenames == ["first.pdf"]
    assert len(status_messages) == 1
    assert report["pre_status_sent"] is True
    assert report["final_status_sent"] is False

    ledger = json.loads((batch_root / "telegram_send_ledger.json").read_text(encoding="utf-8"))
    assert ledger["entries"]["pdf-a"]["state"] == "confirmed"
    assert [item["state"] for item in ledger["entries"]["pdf-a"]["history"]] == [
        "api_started",
        "confirmed",
    ]
    assert ledger["entries"]["pdf-b"]["state"] == "pending"
    assert ledger["entries"]["pdf-b"]["history"] == []


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


def test_telegram_sender_dry_run_leaves_existing_ledger_bytes_identical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    ledger_path = _write_telegram_ledger(batch_root, state="pending")
    sha_before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: pytest.fail("dry-run must not call Telegram"),
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        dry_run=True,
    )

    assert report["ok"] is True
    assert report["sent"] == 1
    assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() == sha_before


def test_telegram_sender_all_confirmed_resume_leaves_ledger_bytes_identical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    ledger_path = _write_telegram_ledger(batch_root, state="confirmed")
    sha_before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: pytest.fail("confirmed entry must not be resent"),
    )

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
    assert report["sent"] == 0
    assert report["skipped"] == 1
    assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() == sha_before


def test_telegram_sender_pending_to_confirmed_transition_persists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    ledger_path = _write_telegram_ledger(batch_root, state="pending")
    sha_before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: {
            "success": True,
            "message_id": "message-confirmed",
            "chat_id": "-1001",
        },
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["sent"] == 1
    assert persisted["entries"]["pdf-a"]["state"] == "confirmed"
    assert [item["state"] for item in persisted["entries"]["pdf-a"]["history"]] == [
        "api_started",
        "confirmed",
    ]
    assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() != sha_before


def test_telegram_sender_read_only_ledger_noop_succeeds_without_write_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    ledger_path = _write_telegram_ledger(batch_root, state="confirmed")
    ledger_path.chmod(0o444)
    sha_before = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        telegram_mod,
        "save_telegram_ledger",
        lambda *_args, **_kwargs: pytest.fail("no-op sender attempted a ledger write"),
    )

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
    assert report["sent"] == 0
    assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() == sha_before


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
                "batch_hash": _batch_hash(batch_root),
                "telegram_chat_id": "-1001",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "history": [],
                        "telegram_chat_id": "-1001",
                    },
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


def test_telegram_sender_refuses_resume_to_a_different_chat(monkeypatch, tmp_path: Path):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": _batch_hash(batch_root),
                "telegram_chat_id": "-2002",
                "entries": {
                    "pdf-a": {"state": "failed", "history": [{"event": "api_started"}]},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: sent.append("sent") or {"success": True},
    )

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
    assert report["halt_reason"] == "TELEGRAM_LEDGER_IDENTITY"
    assert report["fallback_allowed"] is False
    assert sent == []


def test_confirmed_telegram_ledger_entry_is_immutable() -> None:
    ledger = {"entries": {"pdf-a": {"state": "confirmed", "history": []}}}

    with pytest.raises(RuntimeError, match="immutable"):
        telegram_mod._set_entry_state(ledger, "pdf-a", "pending")

    assert ledger["entries"]["pdf-a"]["state"] == "confirmed"


def test_telegram_sender_blocks_july_10_manifest_before_any_send(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [{"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1}],
        target_date="2026-07-10",
    )
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **kwargs: sent.append(str(kwargs["document_path"])) or {"success": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 7, 10),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
    )

    assert report["ok"] is False
    assert report["halt_reason"] == "TARGET_DATE_SEND_EXCLUDED"
    assert sent == []


def test_telegram_final_table_is_blocked_for_july_10(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [{"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1}],
        target_date="2026-07-10",
    )
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_message",
        lambda **kwargs: sent.append(str(kwargs["text"])) or {"success": True},
    )

    report = telegram_mod.send_final_status_table(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 7, 10),
        token="token-1",
        chat_id="-1001",
    )

    assert report["ok"] is False
    assert "TARGET_DATE_SEND_EXCLUDED" in report["error"]
    assert sent == []


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
                "batch_hash": _batch_hash(batch_root),
                "telegram_chat_id": "-1001",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "history": [],
                        "telegram_chat_id": "-1001",
                    },
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
    lock_path = batch_root.parent / ".telegram_send.lock"
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


def test_telegram_sender_blocks_same_date_sibling_with_missing_ledger(
    monkeypatch,
    tmp_path: Path,
):
    sibling_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-old", "filename": "old.pdf", "order_id": "1000", "send_sequence": 1},
        ],
        ready_set_at="2026-04-21T16:00:00+05:00",
        batch_label="21.04.26_MERGED_old",
    )
    current_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-new", "filename": "new.pdf", "order_id": "1001", "send_sequence": 1},
        ],
        ready_set_at="2026-04-21T17:00:00+05:00",
        batch_label="21.04.26_MERGED_new",
    )
    current_manifest = current_root / "send_batch_manifest.json"
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **kwargs: sent.append(str(kwargs["document_path"])) or {"success": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        manifest_path=current_manifest,
        expected_manifest_sha256=hashlib.sha256(current_manifest.read_bytes()).hexdigest(),
    )

    assert report["ok"] is False
    assert report["halt_reason"] == "TELEGRAM_PRIOR_REQUEST_ATTEMPT"
    assert "missing_same_target_date_sibling_telegram_ledger" in report["error"]
    assert report["fallback_allowed"] is False
    assert sent == []
    assert not (sibling_root / "telegram_send_ledger.json").exists()
    assert not (current_root / "telegram_send_ledger.json").exists()


def test_telegram_sender_blocks_attempted_same_date_sibling_with_different_ready_identity(
    monkeypatch,
    tmp_path: Path,
):
    sibling_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-old", "filename": "old.pdf", "order_id": "1000", "send_sequence": 1},
        ],
        ready_set_at="2026-04-21T16:00:00+05:00",
        batch_label="21.04.26_MERGED_old",
    )
    (sibling_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": _batch_hash(sibling_root),
                "telegram_chat_id": "-1001",
                "entries": {
                    "pdf-old": {
                        "state": "failed",
                        "history": [{"state": "api_started", "at": "2026-04-21T16:01:00+05:00"}],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    current_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-new", "filename": "new.pdf", "order_id": "1001", "send_sequence": 1},
        ],
        ready_set_at="2026-04-21T17:00:00+05:00",
        batch_label="21.04.26_MERGED_new",
    )
    current_manifest = current_root / "send_batch_manifest.json"
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **kwargs: sent.append(str(kwargs["document_path"])) or {"success": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        manifest_path=current_manifest,
        expected_manifest_sha256=hashlib.sha256(current_manifest.read_bytes()).hexdigest(),
    )

    assert report["ok"] is False
    assert report["halt_reason"] == "TELEGRAM_PRIOR_REQUEST_ATTEMPT"
    assert "same_target_date_attempt_in_other_batch" in report["error"]
    assert report["fallback_allowed"] is False
    assert sent == []
    assert not (current_root / "telegram_send_ledger.json").exists()


def test_telegram_sender_allows_resume_of_complete_current_batch_ledger(
    monkeypatch,
    tmp_path: Path,
):
    batch_root = _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "telegram",
                "batch_hash": _batch_hash(batch_root),
                "telegram_chat_id": "-1001",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "history": [{"state": "confirmed", "at": "2026-04-21T17:01:00+05:00"}],
                        "telegram_chat_id": "-1001",
                        "telegram_message_id": "message-1",
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    manifest_path = batch_root / "send_batch_manifest.json"
    sent: list[str] = []
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **kwargs: sent.append(str(kwargs["document_path"])) or {"success": True},
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        manifest_path=manifest_path,
        expected_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )

    assert report["ok"] is True
    assert report["sent"] == 0
    assert report["skipped"] == 1
    assert report["confirmed_total"] == 1
    assert sent == []


def test_telegram_sender_no_resume_never_reselects_confirmed_entries(monkeypatch, tmp_path: Path):
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
                "batch_hash": _batch_hash(batch_root),
                "telegram_chat_id": "-1001",
                "entries": {
                    "pdf-a": {
                        "state": "confirmed",
                        "history": [],
                        "telegram_chat_id": "-1001",
                    },
                    "pdf-b": {
                        "state": "confirmed",
                        "history": [],
                        "telegram_chat_id": "-1001",
                    },
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
    assert report["sent"] == 0
    assert report["skipped"] == 2
    assert report["confirmed_total"] == 2
    assert captions == []


def test_ordered_full_resend_is_permanently_disabled(monkeypatch, tmp_path: Path):
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

    assert report["ok"] is False
    assert report["halted"] is True
    assert report["halt_reason"] == "ORDERED_FULL_RESEND_DISABLED"
    assert sent_filenames == []
    assert not (batch_root / "telegram_send_ledger.json").exists()


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
    ]

    monkeypatch.setattr(telegram_mod.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(telegram_mod, "send_document", lambda **_kwargs: {"success": True, "message_id": "doc-1", "chat_id": "-1001"})
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


def test_telegram_sender_does_not_post_returns_pickup_after_final_status(monkeypatch, tmp_path: Path):
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
    assert report["returns_pickup_sent"] is False
    assert len(status_texts) == 2
    assert all("Returns Pickup Ready" not in text for text in status_texts)


def test_telegram_sender_arms_passive_handover_watch_after_successful_status_messages(monkeypatch, tmp_path: Path):
    _write_manifest(
        tmp_path,
        [
            {"pdf_key": "pdf-a", "filename": "first.pdf", "order_id": "1001", "send_sequence": 1},
        ],
    )
    armed_calls: list[dict[str, object]] = []
    message_ids = iter(["pre-status", "final-status"])

    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: {"success": True, "message_id": "doc-1", "chat_id": "-1001"},
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
