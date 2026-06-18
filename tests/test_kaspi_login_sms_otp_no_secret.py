import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.resolve_kaspi_login_sms_otp_no_secret import (
    GREEN_READY_GATE,
    GREEN_RESOLVED_GATE,
    YELLOW_AMBIGUOUS_GATE,
    YELLOW_NO_CANDIDATE_GATE,
    apple_nanoseconds,
    main as otp_resolver_main,
)


def _make_messages_db(path: Path, *, rows: list[tuple[str, datetime, int]] | None = None) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            text TEXT,
            attributedBody BLOB,
            date INTEGER,
            is_from_me INTEGER,
            handle_id INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT,
            service TEXT
        )
        """
    )
    conn.execute("INSERT INTO handle (ROWID, id, service) VALUES (1, '+15550000000', 'SMS')")
    for idx, (text, dt, is_from_me) in enumerate(rows or [], start=1):
        conn.execute(
            """
            INSERT INTO message (ROWID, text, date, is_from_me, handle_id)
            VALUES (?, ?, ?, ?, 1)
            """,
            (idx, text, apple_nanoseconds(dt), is_from_me),
        )
    conn.commit()
    conn.close()


def test_sms_otp_resolver_prints_code_only_to_stdout_and_redacts_audit(tmp_path, capsys):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "chat.db"
    audit_path = tmp_path / "audit.json"
    _make_messages_db(
        db_path,
        rows=[("Kaspi login code: 482913", now - timedelta(minutes=1), 0)],
    )

    rc = otp_resolver_main(
        [
            "--messages-db",
            str(db_path),
            "--audit-json",
            str(audit_path),
            "--now-iso",
            now.isoformat(),
            "--print-otp-to-stdout",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 0
    assert captured.out.strip() == "482913"
    assert audit["gate"] == GREEN_RESOLVED_GATE
    assert audit["otp_printed_to_stdout"] is True
    assert audit["otp_exported_to_audit"] is False
    assert audit["raw_sms_text_exported"] is False
    assert audit["raw_sender_exported"] is False
    assert "482913" not in audit_text
    assert "Kaspi login code" not in audit_text
    assert "+15550000000" not in audit_text


def test_sms_otp_resolver_ready_without_exporting_code_when_print_not_requested(tmp_path, capsys):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "chat.db"
    audit_path = tmp_path / "audit.json"
    _make_messages_db(
        db_path,
        rows=[("Каспи код входа: 135790", now - timedelta(minutes=2), 0)],
    )

    rc = otp_resolver_main(
        [
            "--messages-db",
            str(db_path),
            "--audit-json",
            str(audit_path),
            "--now-iso",
            now.isoformat(),
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 0
    assert "135790" not in captured.out
    assert audit["gate"] == GREEN_READY_GATE
    assert audit["candidate_count"] == 1
    assert "135790" not in audit_text
    assert "Каспи код входа" not in audit_text


def test_sms_otp_resolver_fails_closed_on_ambiguous_codes(tmp_path, capsys):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "chat.db"
    audit_path = tmp_path / "audit.json"
    _make_messages_db(
        db_path,
        rows=[
            ("Kaspi login code: 111111", now - timedelta(minutes=1), 0),
            ("Kaspi login code: 222222", now - timedelta(minutes=2), 0),
        ],
    )

    rc = otp_resolver_main(
        [
            "--messages-db",
            str(db_path),
            "--audit-json",
            str(audit_path),
            "--now-iso",
            now.isoformat(),
            "--print-otp-to-stdout",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 3
    assert captured.out == ""
    assert audit["gate"] == YELLOW_AMBIGUOUS_GATE
    assert "111111" not in audit_text
    assert "222222" not in audit_text


def test_sms_otp_resolver_ignores_old_and_outgoing_messages(tmp_path, capsys):
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    db_path = tmp_path / "chat.db"
    audit_path = tmp_path / "audit.json"
    _make_messages_db(
        db_path,
        rows=[
            ("Kaspi login code: 333333", now - timedelta(minutes=60), 0),
            ("Kaspi login code: 444444", now - timedelta(minutes=1), 1),
        ],
    )

    rc = otp_resolver_main(
        [
            "--messages-db",
            str(db_path),
            "--audit-json",
            str(audit_path),
            "--now-iso",
            now.isoformat(),
            "--print-otp-to-stdout",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 3
    assert captured.out == ""
    assert audit["gate"] == YELLOW_NO_CANDIDATE_GATE
    assert "333333" not in audit_text
    assert "444444" not in audit_text
