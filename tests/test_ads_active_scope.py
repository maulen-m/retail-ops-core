from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from core.ads.active_scope import (
    is_store_active_on,
    resolve_active_store_codes,
    resolve_store_coverage_mode_on,
)


def _write_scope(path: Path) -> None:
    payload = {
        "version": 1,
        "default_active": False,
        "stores": {
            "STOREB": {
                "windows": [
                    {"start": "2026-03-08", "active": True, "reason": "operator_active_current"}
                ]
            },
            "ACMEWEAR": {
                "windows": [
                    {"start": "2025-01-01", "active": True, "reason": "historical_source_present"}
                ]
            },
            "UNIVERSAL": {
                "windows": [
                    {
                        "start": "2026-02-22",
                        "active": False,
                        "reason": "operator_stop_date_and_no_historical_source",
                    },
                ]
            },
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_resolve_active_store_codes_uses_effective_date(tmp_path: Path) -> None:
    scope_path = tmp_path / "ads_active_scope.yaml"
    _write_scope(scope_path)

    historical = resolve_active_store_codes(date(2026, 2, 21), config_path=scope_path)
    current = resolve_active_store_codes(date(2026, 3, 8), config_path=scope_path)

    assert historical == {"ACMEWEAR"}
    assert current == {"STOREB", "ACMEWEAR"}


def test_is_store_active_on_respects_universal_stop_date(tmp_path: Path) -> None:
    scope_path = tmp_path / "ads_active_scope.yaml"
    _write_scope(scope_path)

    assert is_store_active_on("UNIVERSAL", date(2026, 2, 21), config_path=scope_path) is False
    assert is_store_active_on("UNIVERSAL", date(2026, 2, 22), config_path=scope_path) is False


def test_is_store_active_on_defaults_unlisted_store_to_inactive(tmp_path: Path) -> None:
    scope_path = tmp_path / "ads_active_scope.yaml"
    _write_scope(scope_path)

    assert is_store_active_on("11KZ", date(2026, 3, 8), config_path=scope_path) is False


def test_storeb_manual_stop_keeps_stop_day_active_and_next_day_inactive(tmp_path: Path) -> None:
    scope_path = tmp_path / "ads_active_scope.yaml"
    payload = {
        "version": 2,
        "default_active": False,
        "default_coverage_mode": "all_sold_skus",
        "stores": {
            "STOREB": {
                "windows": [
                    {
                        "start": "2026-03-08",
                        "end": "2026-05-20",
                        "active": True,
                        "coverage_mode": "advertised_products_only",
                        "reason": "operator_active_until_manual_stop_day",
                    },
                    {
                        "start": "2026-05-21",
                        "active": False,
                        "coverage_mode": "advertised_products_only",
                        "reason": "owner_manual_storeb_ads_campaign_stop_2026-05-20T09:46:41+05",
                    },
                ]
            },
        },
    }
    scope_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert is_store_active_on("STOREB", date(2026, 5, 20), config_path=scope_path) is True
    assert is_store_active_on("STOREB", date(2026, 5, 21), config_path=scope_path) is False


def test_acmewear_post_may4_uses_advertised_products_only_scope(tmp_path: Path) -> None:
    scope_path = tmp_path / "ads_active_scope.yaml"
    payload = {
        "version": 2,
        "default_active": False,
        "default_coverage_mode": "all_sold_skus",
        "stores": {
            "ACMEWEAR": {
                "windows": [
                    {
                        "start": "2025-01-01",
                        "end": "2026-05-04",
                        "active": True,
                        "coverage_mode": "all_sold_skus",
                        "reason": "historical_full_sold_sku_source_present_through_2026-05-04",
                    },
                    {
                        "start": "2026-05-05",
                        "active": True,
                        "coverage_mode": "advertised_products_only",
                        "reason": "post_2026-05-04_exact_campaign_product_source_only",
                    },
                ]
            },
        },
    }
    scope_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert is_store_active_on("ACMEWEAR", date(2026, 5, 4), config_path=scope_path) is True
    assert resolve_store_coverage_mode_on("ACMEWEAR", date(2026, 5, 4), config_path=scope_path) == "all_sold_skus"
    assert is_store_active_on("ACMEWEAR", date(2026, 5, 5), config_path=scope_path) is True
    assert (
        resolve_store_coverage_mode_on("ACMEWEAR", date(2026, 5, 5), config_path=scope_path)
        == "advertised_products_only"
    )
