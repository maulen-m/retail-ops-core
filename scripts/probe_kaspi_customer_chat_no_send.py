#!/usr/bin/env python3
"""Fixture-only Kaspi customer chat selector probe.

This script never opens a browser and never clicks or sends. It validates the
known merchant UI chat trigger against saved HTML so live chat probing can stay
behind a later approval gate.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.ops.customer_size_request import inspect_chat_trigger_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a saved Kaspi order HTML fixture for chat trigger selectors."
    )
    parser.add_argument("--html-fixture", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    html = args.html_fixture.read_text(encoding="utf-8")
    result = inspect_chat_trigger_html(html)
    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "html_fixture": str(args.html_fixture.resolve()),
        "live_browser_used": False,
        "clicks_performed": 0,
        "messages_sent": 0,
        **result,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["order_chat_trigger_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
