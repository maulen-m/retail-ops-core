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
from urllib.parse import urlencode, urlparse
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


def _strip_wrapped_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _read_dotenv_value(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[7:].strip()
        if "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        if k.strip() != key:
            continue
        return _strip_wrapped_quotes(v)
    return ""


def _resolve_credentials(env_file: Path) -> tuple[str, str]:
    login_value = os.environ.get("Kaspi_marketing_login") or os.environ.get("KASPI_MARKETING_LOGIN") or ""
    password_value = os.environ.get("Kaspi_marketing_Password") or os.environ.get("KASPI_MARKETING_PASSWORD") or ""
    if login_value and password_value:
        return login_value, password_value

    for login_key in ("Kaspi_marketing_login", "KASPI_MARKETING_LOGIN"):
        if not login_value:
            login_value = _read_dotenv_value(env_file, login_key)
    for password_key in ("Kaspi_marketing_Password", "KASPI_MARKETING_PASSWORD"):
        if not password_value:
            password_value = _read_dotenv_value(env_file, password_key)
    return login_value, password_value


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
    is_marketing_write = "/advertising/products/api/" in (parsed.path or "")
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
        "is_marketing_write_request": bool(is_marketing_write),
        "is_bid_write_candidate": bool(is_bid_candidate),
    }
    if record["post_json"] is None and post_data:
        record["post_data"] = post_data[:5000]

    return record if (is_bid_candidate or is_marketing_write) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Kaspi bid-write API endpoint via manual UI action")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--profile-dir", default=os.environ.get("KASPI_MARKETING_PROFILE_DIR", DEFAULT_PROFILE_DIR))
    parser.add_argument("--merchant-id", default=os.environ.get("KASPI_MARKETING_MERCHANT_ID", DEFAULT_MERCHANT_ID))
    parser.add_argument("--campaign-id", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--target-url", default="")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--max-candidates", type=int, default=50)
    return parser.parse_args()


def _campaign_url(
    merchant_id: str,
    campaign_id: str,
    *,
    start_date: str = "",
    end_date: str = "",
    target_url: str = "",
) -> str:
    if target_url:
        return target_url
    if campaign_id:
        base = f"https://marketing.kaspi.kz/advertising/campaigns/{campaign_id}"
        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if params:
            return f"{base}?{urlencode(params)}"
        return base
    return "https://marketing.kaspi.kz/advertising/campaigns?tab=campaigns"


def _candidate_score(candidate: Mapping[str, Any]) -> int:
    score = 0
    path = str(candidate.get("path", "") or "").lower()
    method = str(candidate.get("method", "") or "").upper()
    post_json = candidate.get("post_json")

    if method in {"PUT", "PATCH"}:
        score += 30
    if "update-bid" in path:
        score += 100
    if "/campaign/" in path and "/products/" in path:
        score += 20
    if "average-bid" in path:
        score -= 60
    if isinstance(post_json, dict):
        if "skuList" in post_json and "bid" in post_json:
            score += 80
        elif "bid" in post_json:
            score += 20
    if bool(candidate.get("is_bid_write_candidate")):
        score += 10
    return score


def _pick_preferred_candidate(captured: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not captured:
        return None
    ranked = sorted(captured, key=_candidate_score, reverse=True)
    return ranked[0]


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

    login_value, password_value = _resolve_credentials(args.env_file)

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
                print("Auto-login failed. Fallback: complete login manually in opened browser, then press Enter.")
                page.goto("https://marketing.kaspi.kz/sign-in", wait_until="domcontentloaded")
                input()
                if not ensure_login(
                    page,
                    login_value or "",
                    password_value or "",
                    manual_login=True,
                    login_timeout=args.login_timeout,
                ):
                    print(json.dumps({"status": "login_failed"}, ensure_ascii=False))
                    return 1

            target_url = _campaign_url(
                args.merchant_id,
                args.campaign_id,
                start_date=args.start_date,
                end_date=args.end_date,
                target_url=args.target_url,
            )
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            print("Manual step required:")
            print(f"1) In the opened browser ({target_url}), change one bid value and save.")
            print("2) Return here and press Enter to finish capture.")
            input()
            page.wait_for_timeout(1500)
        finally:
            context.close()

    selected = _pick_preferred_candidate(captured)

    payload = {
        "captured_at": datetime.now(ALMATY_TZ).isoformat(),
        "merchant_id": str(args.merchant_id),
        "campaign_id": str(args.campaign_id or ""),
        "candidates_found": len(captured),
        "bid_candidate_found": bool(any(bool(c.get("is_bid_write_candidate")) for c in captured)),
        "candidates": captured,
        "notes": [
            "Headers are sanitized; sensitive auth/cookie tokens are redacted.",
            "Use this file as shape reference only; do not hardcode transient headers.",
        ],
    }
    if selected is not None:
        payload["method"] = selected.get("method")
        payload["url"] = selected.get("url")
        payload["path"] = selected.get("path")
        payload["query"] = selected.get("query")
        payload["post_json"] = selected.get("post_json")

    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "candidates_found": len(captured),
                "bid_candidate_found": payload["bid_candidate_found"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
