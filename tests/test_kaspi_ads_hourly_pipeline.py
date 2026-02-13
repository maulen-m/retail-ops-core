from __future__ import annotations

from pathlib import Path

from scripts.kaspi_ads_hourly_pipeline import load_store_targets


def test_load_store_targets_returns_enabled_entries(tmp_path: Path) -> None:
    config_path = tmp_path / "stores.yaml"
    config_path.write_text(
        "\n".join(
            [
                "version: 1",
                "stores:",
                "  - store_code: ACMEWEAR",
                "    merchant_id: '759051'",
                "    credential_profile: default",
                "    profile_dir: '~/Library/Application Support/ChromePlaywrightProfile4'",
                "    enabled: true",
                "  - store_code: UNIVERSAL",
                "    merchant_id: '761413'",
                "    credential_profile: universal",
                "    profile_dir: '~/Library/Application Support/ChromePlaywrightProfile4_universal'",
                "    enabled: true",
                "  - store_code: DISABLED",
                "    merchant_id: '123456'",
                "    credential_profile: default",
                "    enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    targets = load_store_targets(config_path)
    assert targets == [
        {
            "store_code": "ACMEWEAR",
            "merchant_id": "759051",
            "credential_profile": "default",
            "profile_dir": "~/Library/Application Support/ChromePlaywrightProfile4",
        },
        {
            "store_code": "UNIVERSAL",
            "merchant_id": "761413",
            "credential_profile": "universal",
            "profile_dir": "~/Library/Application Support/ChromePlaywrightProfile4_universal",
        },
    ]


def test_load_store_targets_handles_missing_file(tmp_path: Path) -> None:
    targets = load_store_targets(tmp_path / "missing.yaml")
    assert targets == []
