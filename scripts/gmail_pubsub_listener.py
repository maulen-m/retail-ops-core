#!/usr/bin/env python3
"""Pull Pub/Sub messages for Gmail push and trigger Gmail history sync."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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


def _sub_path(project_id: str, sub: str) -> str:
    if sub.startswith("projects/"):
        return sub
    return f"projects/{project_id}/subscriptions/{sub}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Listen to Gmail Pub/Sub notifications")
    parser.add_argument("--project-id", default=None, help="GCP project id")
    parser.add_argument("--subscription", default=None, help="Pub/Sub subscription")
    parser.add_argument("--max-messages", type=int, default=10, help="Max messages per pull")
    parser.add_argument("--timeout", type=int, default=60, help="Pull timeout seconds")
    args = parser.parse_args()

    _load_env_file(PROJECT_ROOT / ".env")

    project_id = args.project_id or _get_env("GMAIL_PUSH_PROJECT_ID")
    subscription = args.subscription or _get_env("GMAIL_PUSH_SUBSCRIPTION")
    if not project_id or not subscription:
        print("Missing --project-id/--subscription (or env vars)")
        return 1

    try:
        from google.cloud import pubsub_v1
    except Exception as exc:
        raise RuntimeError(
            "Missing Pub/Sub dependency. Install: pip install google-cloud-pubsub"
        ) from exc

    subscriber = pubsub_v1.SubscriberClient()
    sub_path = _sub_path(project_id, subscription)

    while True:
        response = subscriber.pull(
            request={
                "subscription": sub_path,
                "max_messages": args.max_messages,
                "timeout": args.timeout,
            }
        )
        if not response.received_messages:
            continue

        ack_ids = []
        for received in response.received_messages:
            ack_ids.append(received.ack_id)
            try:
                payload = json.loads(received.message.data.decode("utf-8"))
                print(f"Push: {payload.get('emailAddress')} historyId={payload.get('historyId')}")
            except Exception:
                pass

        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "gmail_sync_history.py")], check=False)
        subscriber.acknowledge(request={"subscription": sub_path, "ack_ids": ack_ids})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
