#!/usr/bin/env python3
"""Resolve one recent Kaspi login SMS OTP at runtime without persisting it.

This helper is intentionally narrow. It may scan the local macOS Messages DB
for a recent Kaspi login code, but persisted audit JSON must never contain the
OTP, SMS body, sender handle, or raw message identifiers.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
DEFAULT_MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"
DEFAULT_KEYWORDS = ("kaspi", "каспи")
DEFAULT_OTP_REGEX = r"(?<!\d)(\d{4,8})(?!\d)"

GREEN_RESOLVED_GATE = "GREEN_KASPI_LOGIN_SMS_OTP_RESOLVED_RUNTIME_ONLY_REDACTED_AUDIT"
GREEN_READY_GATE = "GREEN_KASPI_LOGIN_SMS_OTP_SINGLE_CANDIDATE_READY_NO_EXPORT"
YELLOW_NO_CANDIDATE_GATE = "YELLOW_KASPI_LOGIN_SMS_OTP_NO_CANDIDATE_NO_SECRET"
YELLOW_AMBIGUOUS_GATE = "YELLOW_KASPI_LOGIN_SMS_OTP_AMBIGUOUS_NO_SECRET"
RED_DB_UNAVAILABLE_GATE = "RED_KASPI_LOGIN_SMS_OTP_MESSAGES_DB_UNAVAILABLE_NO_SECRET"
RED_SCHEMA_GATE = "RED_KASPI_LOGIN_SMS_OTP_MESSAGES_SCHEMA_UNSUPPORTED_NO_SECRET"
RED_CLIPBOARD_GATE = "RED_KASPI_LOGIN_SMS_OTP_CLIPBOARD_FAILED_NO_SECRET"


class OtpResolverError(RuntimeError):
    def __init__(self, gate: str, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.gate = gate
        self.exit_code = exit_code


@dataclass(frozen=True)
class OtpCandidate:
    code: str
    message_date: datetime | None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def apple_nanoseconds(dt: datetime) -> int:
    """Convert a datetime to Messages.app nanoseconds since 2001-01-01 UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt.astimezone(timezone.utc) - APPLE_EPOCH
    return int(delta.total_seconds() * 1_000_000_000)


def datetime_from_apple_nanoseconds(value: int | None) -> datetime | None:
    if value is None:
        return None
    # Some older Messages DBs have second-resolution dates. Support both.
    if abs(value) < 10_000_000_000:
        return APPLE_EPOCH + timedelta(seconds=value)
    return APPLE_EPOCH + timedelta(microseconds=value / 1000)


def _available_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        raise OtpResolverError(RED_SCHEMA_GATE, f"{table} table missing")
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _text_from_row(row: sqlite3.Row) -> str:
    text = row["text"] if "text" in row.keys() else None
    if isinstance(text, str) and text.strip():
        return text
    blob = row["attributedBody"] if "attributedBody" in row.keys() else None
    if isinstance(blob, bytes):
        decoded = blob.decode("utf-8", errors="ignore")
        # attributedBody is a binary plist-ish blob. This best-effort fallback
        # is only used in memory; callers must not persist the returned text.
        return decoded
    return ""


def _keywords_match(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(keyword.casefold() in normalized for keyword in keywords)


def _extract_unique_codes(text: str, pattern: re.Pattern[str]) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        code = match.group(1)
        if code not in seen:
            codes.append(code)
            seen.add(code)
    return codes


def _scan_candidates(
    *,
    messages_db: Path,
    now: datetime,
    window_minutes: int,
    keywords: tuple[str, ...],
    otp_regex: str,
    max_scan_rows: int,
) -> tuple[list[OtpCandidate], dict[str, Any]]:
    if not messages_db.exists():
        raise OtpResolverError(RED_DB_UNAVAILABLE_GATE, "Messages DB not found")

    pattern = re.compile(otp_regex)
    lower_bound = apple_nanoseconds(now - timedelta(minutes=window_minutes))
    upper_bound = apple_nanoseconds(now + timedelta(minutes=2))

    uri = f"file:{messages_db.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        message_columns = _available_columns(conn, "message")
        required = {"date", "is_from_me"}
        if not required.issubset(message_columns) or not (
            {"text", "attributedBody"} & message_columns
        ):
            raise OtpResolverError(RED_SCHEMA_GATE, "message table lacks required columns")
        selected = ["date", "is_from_me"]
        if "text" in message_columns:
            selected.append("text")
        if "attributedBody" in message_columns:
            selected.append("attributedBody")
        rows = conn.execute(
            f"""
            SELECT {", ".join(selected)}
            FROM message
            WHERE is_from_me = 0
              AND date >= ?
              AND date <= ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (lower_bound, upper_bound, max_scan_rows),
        ).fetchall()

    candidates: list[OtpCandidate] = []
    scanned_rows = 0
    keyword_rows = 0
    code_rows = 0
    for row in rows:
        scanned_rows += 1
        text = _text_from_row(row)
        if not text:
            continue
        if keywords and not _keywords_match(text, keywords):
            continue
        keyword_rows += 1
        codes = _extract_unique_codes(text, pattern)
        if len(codes) != 1:
            if codes:
                code_rows += 1
            continue
        code_rows += 1
        candidates.append(
            OtpCandidate(
                code=codes[0],
                message_date=datetime_from_apple_nanoseconds(int(row["date"])),
            )
        )

    stats = {
        "messages_db_path": str(messages_db.expanduser()),
        "window_minutes": window_minutes,
        "max_scan_rows": max_scan_rows,
        "messages_rows_scanned": scanned_rows,
        "keyword_matched_rows": keyword_rows,
        "code_matched_rows": code_rows,
        "candidate_count": len(candidates),
    }
    if candidates and candidates[0].message_date:
        stats["latest_candidate_age_seconds"] = max(
            0,
            int((now - candidates[0].message_date.astimezone(timezone.utc)).total_seconds()),
        )
    return candidates, stats


def _copy_to_clipboard(secret: str) -> None:
    try:
        subprocess.run(["pbcopy"], input=secret, text=True, check=True)
    except Exception as exc:  # pragma: no cover - platform dependent
        raise OtpResolverError(RED_CLIPBOARD_GATE, "pbcopy failed") from exc


def _audit_base(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    return {
        "run_at": now.isoformat(timespec="seconds"),
        "otp_exported_to_audit": False,
        "raw_sms_text_exported": False,
        "raw_sender_exported": False,
        "raw_message_id_exported": False,
        "cookies_exported": False,
        "session_material_exported": False,
        "kaspi_chat_write_allowed": False,
        "customer_send_allowed": False,
        "customer_chat_opened": False,
        "customer_message_typed": False,
        "customer_message_sent": False,
        "messages_db_content_scanned_in_memory": True,
        "print_otp_to_stdout_requested": bool(args.print_otp_to_stdout),
        "copy_to_clipboard_requested": bool(args.copy_to_clipboard),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--messages-db", type=Path, default=DEFAULT_MESSAGES_DB)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--window-minutes", type=int, default=10)
    parser.add_argument("--max-scan-rows", type=int, default=50)
    parser.add_argument("--keyword", action="append", help="Case-insensitive keyword. Defaults to Kaspi/Каспи.")
    parser.add_argument("--otp-regex", default=DEFAULT_OTP_REGEX)
    parser.add_argument("--now-iso", help="Testing override, ISO timestamp.")
    parser.add_argument(
        "--print-otp-to-stdout",
        action="store_true",
        help="Print only the OTP to stdout for immediate runtime use. Never writes it to audit JSON.",
    )
    parser.add_argument(
        "--copy-to-clipboard",
        action="store_true",
        help="Copy the OTP to macOS clipboard. The OTP is never written to audit JSON.",
    )
    return parser


def resolve_runtime_otp(
    *,
    messages_db: Path = DEFAULT_MESSAGES_DB,
    window_minutes: int = 10,
    max_scan_rows: int = 50,
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS,
    otp_regex: str = DEFAULT_OTP_REGEX,
    now: datetime | None = None,
    runtime_secret_to_caller_requested: bool = False,
    copy_to_clipboard: bool = False,
) -> tuple[int, dict[str, Any], str | None]:
    """Return a runtime-only OTP to the caller while keeping audit redacted."""
    effective_now = now or datetime.now(timezone.utc)
    args = argparse.Namespace(
        print_otp_to_stdout=False,
        copy_to_clipboard=copy_to_clipboard,
    )
    audit = _audit_base(args, effective_now)
    audit["runtime_secret_to_caller_requested"] = bool(runtime_secret_to_caller_requested)
    try:
        candidates, stats = _scan_candidates(
            messages_db=messages_db,
            now=effective_now,
            window_minutes=max(1, int(window_minutes)),
            keywords=keywords,
            otp_regex=otp_regex,
            max_scan_rows=max(1, int(max_scan_rows)),
        )
        audit.update(stats)
        audit["keyword_filters_count"] = len(keywords)
        if not candidates:
            audit["gate"] = YELLOW_NO_CANDIDATE_GATE
            audit["blockers"] = ["no_recent_single_kaspi_otp_candidate"]
            return 3, audit, None
        unique_codes = {candidate.code for candidate in candidates}
        audit["unique_candidate_count"] = len(unique_codes)
        if len(unique_codes) != 1:
            audit["gate"] = YELLOW_AMBIGUOUS_GATE
            audit["blockers"] = ["multiple_recent_otp_candidates"]
            return 3, audit, None

        code = next(iter(unique_codes))
        if copy_to_clipboard:
            _copy_to_clipboard(code)
            audit["otp_copied_to_clipboard"] = True
        else:
            audit["otp_copied_to_clipboard"] = False
        audit["otp_printed_to_stdout"] = False
        audit["gate"] = GREEN_RESOLVED_GATE if (runtime_secret_to_caller_requested or copy_to_clipboard) else GREEN_READY_GATE
        return 0, audit, code if runtime_secret_to_caller_requested else None
    except OtpResolverError as exc:
        audit["gate"] = exc.gate
        audit["blockers"] = [str(exc)]
        return exc.exit_code, audit, None


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any], str | None]:
    now = _parse_now(args.now_iso)
    keywords = tuple(args.keyword) if args.keyword else DEFAULT_KEYWORDS
    exit_code, audit, code = resolve_runtime_otp(
        messages_db=args.messages_db,
        now=now,
        window_minutes=args.window_minutes,
        keywords=keywords,
        otp_regex=args.otp_regex,
        max_scan_rows=args.max_scan_rows,
        runtime_secret_to_caller_requested=bool(args.print_otp_to_stdout),
        copy_to_clipboard=bool(args.copy_to_clipboard),
    )
    audit["print_otp_to_stdout_requested"] = bool(args.print_otp_to_stdout)
    if args.print_otp_to_stdout and exit_code == 0:
        audit["otp_printed_to_stdout"] = True
    return exit_code, audit, code if args.print_otp_to_stdout else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code, audit, otp_to_stdout = run(args)
    _write_json(args.audit_json, audit)
    if otp_to_stdout:
        print(otp_to_stdout)
    elif exit_code:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
