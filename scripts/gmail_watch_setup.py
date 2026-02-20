#!/usr/bin/env python3
"""Configure Gmail push watch and store historyId in DB."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.gmail_api_client import get_gmail_service
from core.transfer_ledger.repository import ensure_schema
from core.db import get_db


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get_env(*keys: str) -> str | None:
    for key in keys:
        val = os.getenv(key)
        if val:
            return val
    return None


def _normalize_topic(project_id: str, topic: str) -> str:
    if topic.startswith("projects/"):
        return topic
    return f"projects/{project_id}/topics/{topic}"


def _upsert_sync_state(email_address: str, history_id: str, labels: list[str]) -> None:
    ensure_schema()
    labels_str = ",".join(labels)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gmail_sync_state (
                email_address TEXT PRIMARY KEY,
                history_id TEXT,
                labels TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO gmail_sync_state (email_address, history_id, labels, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(email_address) DO UPDATE SET
                history_id = excluded.history_id,
                labels = excluded.labels,
                updated_at = datetime('now')
            """,
            (email_address, history_id, labels_str),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup Gmail push watch")
    parser.add_argument("--project-id", default=None, help="GCP project id")
    parser.add_argument("--topic", default=None, help="Pub/Sub topic name (or full path)")
    parser.add_argument("--labels", default=None, help="Comma-separated label names")
    parser.add_argument("--credentials", default=None, help="OAuth client JSON path")
    parser.add_argument("--token", default=None, help="OAuth token cache path")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    project_id = args.project_id or _get_env("GMAIL_PUSH_PROJECT_ID")
    topic = args.topic or _get_env("GMAIL_PUSH_TOPIC")
    labels = args.labels or _get_env("GMAIL_PUSH_LABELS", "GMAIL_LABELS")
    creds_path = args.credentials or _get_env("GMAIL_OAUTH_CLIENT_JSON")
    token_path = args.token or _get_env("GMAIL_TOKEN_PATH", "GMAIL_OAUTH_TOKEN")

    if not project_id or not topic or not creds_path:
        print("Missing required: --project-id, --topic, --credentials (or env vars)")
        return 1
    if not token_path:
        token_path = str(Path.home() / ".config" / "autonomous_business" / "gmail_token.json")

    labels_list = [s.strip() for s in (labels or "").split(",") if s.strip()]

    service = get_gmail_service(Path(creds_path), Path(token_path))
    label_ids = []
    if labels_list:
        available = service.users().labels().list(userId="me").execute()
        label_map = {l["name"]: l["id"] for l in available.get("labels", [])}
        for name in labels_list:
            if name not in label_map:
                raise SystemExit(f"Label not found in Gmail: {name}")
            label_ids.append(label_map[name])

    body = {"topicName": _normalize_topic(project_id, topic)}
    if label_ids:
        body["labelIds"] = label_ids
        body["labelFilterAction"] = "include"

    resp = service.users().watch(userId="me", body=body).execute()
    history_id = resp.get("historyId")
    email_address = resp.get("emailAddress") or "me"

    if history_id:
        _upsert_sync_state(email_address, str(history_id), labels_list)
        print(f"Watch registered. historyId={history_id}")
    else:
        print("Watch registered, but no historyId returned")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
