#!/usr/bin/env python3
"""Discover Kaspi bid-write API requests via manual Playwright capture.

This script is intentionally operator-assisted: it opens Kaspi ads UI, waits for
manual bid change in browser, and stores sanitized request candidates.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ALMATY_TZ = ZoneInfo("Asia/Almaty")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "docs" / "marketing" / "bid_api_discovery.json"
DEFAULT_PROFILE_DIR = "~/Library/Application Support/ChromePlaywrightProfile4"
DEFAULT_MERCHANT_ID = "759051"

SENSITIVE_HEADER_KEYS = {
    "cookie",
    "authorization",
    "x-xsrf-token",
    "x-csrf-token",
    "set-cookie",
    "proxy-authorization",
}
BID_KEYWORDS = ("bid", "cpc", "ставк", "ставка")
WRITE_METHODS = {"POST", "PUT", "PATCH"}


def sanitize_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        key_txt = str(key).strip()
        lower_key = key_txt.lower()
        if lower_key in SENSITIVE_HEADER_KEYS:
            out[lower_key] = "<redacted>"
        else:
            out[lower_key] = str(value)
    return out


def _is_bid_signal(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in BID_KEYWORDS)


def _parse_post_json(post_data: str | None) -> dict[str, Any] | None:
    if not post_data:
        return None
    payload = post_data.strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def build_candidate_record(
    *,
    method: str,
    url: str,
    headers: Mapping[str, Any],
    post_data: str | None,
) -> dict[str, Any] | None:
    method_up = method.upper().strip()
    if method_up not in WRITE_METHODS:
        return None

    parsed = urlparse(url)
    if not parsed.netloc.endswith("kaspi.kz"):
        return None

    text_probe = f"{url}\n{post_data or ''}"
    is_bid_candidate = _is_bid_signal(text_probe)

    record = {
        "captured_at": datetime.now(ALMATY_TZ).isoformat(),
        "method": method_up,
        "url": url,
        "path": parsed.path,
        "query": parsed.query,
        "headers": sanitize_headers(headers),
        "post_json": _parse_post_json(post_data),
        "post_data": None,
        "is_bid_write_candidate": bool(is_bid_candidate),
    }
    if record["post_json"] is None and post_data:
        record["post_data"] = post_data[:5000]

    return record if is_bid_candidate else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Kaspi bid-write API endpoint via manual UI action")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--profile-dir", default=os.environ.get("KASPI_MARKETING_PROFILE_DIR", DEFAULT_PROFILE_DIR))
    parser.add_argument("--merchant-id", default=os.environ.get("KASPI_MARKETING_MERCHANT_ID", DEFAULT_MERCHANT_ID))
    parser.add_argument("--campaign-id", default="")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--max-candidates", type=int, default=50)
    return parser.parse_args()


def _campaign_url(merchant_id: str, campaign_id: str) -> str:
    if campaign_id:
        return (
            "https://marketing.kaspi.kz/advertising/campaigns"
            f"?merchantId={merchant_id}&campaignId={campaign_id}&tab=campaigns"
        )
    return "https://marketing.kaspi.kz/advertising/campaigns?tab=campaigns"


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is required. Install via: pip install playwright") from exc

    try:
        from scripts.kaspi_marketing_scrape import ensure_login
    except ModuleNotFoundError:
        from kaspi_marketing_scrape import ensure_login  # type: ignore

    login_value = os.environ.get("Kaspi_marketing_login") or os.environ.get("KASPI_MARKETING_LOGIN")
    password_value = os.environ.get("Kaspi_marketing_Password") or os.environ.get("KASPI_MARKETING_PASSWORD")

    captured: list[dict[str, Any]] = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir,
            channel="chrome",
            headless=False,
        )
        try:
            def on_request(request) -> None:  # noqa: ANN001
                if len(captured) >= max(1, args.max_candidates):
                    return
                rec = build_candidate_record(
                    method=request.method,
                    url=request.url,
                    headers=request.headers,
                    post_data=request.post_data,
                )
                if rec is not None:
                    captured.append(rec)

            context.on("request", on_request)
            page = context.new_page()
            if not ensure_login(
                page,
                login_value or "",
                password_value or "",
                manual_login=args.manual_login,
                login_timeout=args.login_timeout,
            ):
                print(json.dumps({"status": "login_failed"}, ensure_ascii=False))
                return 1

            target_url = _campaign_url(args.merchant_id, args.campaign_id)
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            print("Manual step required:")
            print("1) In the opened browser, change one bid value and save.")
            print("2) Return here and press Enter to finish capture.")
            input()
            page.wait_for_timeout(1500)
        finally:
            context.close()

    payload = {
        "captured_at": datetime.now(ALMATY_TZ).isoformat(),
        "merchant_id": str(args.merchant_id),
        "campaign_id": str(args.campaign_id or ""),
        "candidates_found": len(captured),
        "candidates": captured,
        "notes": [
            "Headers are sanitized; sensitive auth/cookie tokens are redacted.",
            "Use this file as shape reference only; do not hardcode transient headers.",
        ],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(args.output), "candidates_found": len(captured)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
