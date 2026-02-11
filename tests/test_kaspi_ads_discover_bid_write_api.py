from __future__ import annotations

from scripts.kaspi_ads_discover_bid_write_api import (
    build_candidate_record,
    sanitize_headers,
)


def test_sanitize_headers_redacts_sensitive_values() -> None:
    headers = {
        "cookie": "abc=1",
        "authorization": "Bearer token",
        "x-xsrf-token": "secret",
        "content-type": "application/json",
    }
    sanitized = sanitize_headers(headers)
    assert sanitized["cookie"] == "<redacted>"
    assert sanitized["authorization"] == "<redacted>"
    assert sanitized["x-xsrf-token"] == "<redacted>"
    assert sanitized["content-type"] == "application/json"


def test_build_candidate_record_detects_bid_write_and_parses_json() -> None:
    record = build_candidate_record(
        method="PATCH",
        url="https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/campaign/2380614/products/bid",
        headers={"content-type": "application/json", "x-xsrf-token": "token"},
        post_data='{"sku":"19796919b","bid":35}',
    )
    assert record is not None
    assert record["method"] == "PATCH"
    assert record["is_bid_write_candidate"] is True
    assert record["post_json"]["bid"] == 35
    assert record["headers"]["x-xsrf-token"] == "<redacted>"


def test_build_candidate_record_skips_non_write_methods() -> None:
    record = build_candidate_record(
        method="GET",
        url="https://marketing.kaspi.kz/advertising/products/api/v5/merchant/759051/campaign/2380614/products",
        headers={},
        post_data=None,
    )
    assert record is None
