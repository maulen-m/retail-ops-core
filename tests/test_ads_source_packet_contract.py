from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.ads.source_packet_contract import (
    SOURCE_CONTRACT_VERSION,
    validate_ads_source_packet_manifest,
)


def _valid_manifest(tmp_path: Path) -> dict[str, object]:
    packet_root = tmp_path / "packet"
    return {
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "packet_root": str(packet_root),
        "packet_sha256_manifest": "packet_sha256_manifest.tsv",
        "file_list": [
            "packet_sha256_manifest.tsv",
            "redaction_manifest.json",
            "raw_payload_hash_manifest.tsv",
            "kaspi_marketing.sqlite",
        ],
        "raw_payload_files": ["kaspi_marketing.sqlite"],
        "source_db_sha256": "b" * 64,
        "raw_payload_hash_manifest": "raw_payload_hash_manifest.tsv",
        "redaction_manifest": "redaction_manifest.json",
        "no_secrets_included": True,
        "redaction": {
            "no_secrets_included": True,
            "forbidden_artifacts_found": 0,
        },
        "capture": {
            "run_id": "web-ads-20260510",
            "captured_at": "2026-05-10T22:00:00+05:00",
            "finished_at": "2026-05-10T22:05:00+05:00",
            "timezone": "Asia/Almaty",
            "date_start": "2026-05-04",
            "date_end": "2026-05-04",
            "date_window_inclusive": True,
            "ab_as_of": "2026-05-04",
            "max_age_hours": 36,
        },
        "store_identity": {
            "business_store_code": "STOREB",
            "access_store_code": "UNIVERSAL_SWITCHER_FOR_STOREB",
            "adapter_output_store_code": "STOREB",
        },
        "source_db": {
            "path": "kaspi_marketing.sqlite",
            "sha256": "b" * 64,
            "schema_hash": "c" * 64,
            "tables": {
                "campaign_daily": {
                    "expected_columns": ["date", "store_code", "campaign_id", "cost"],
                    "row_count": 1,
                    "unique_key": ["date", "business_store_code", "access_store_code", "campaign_id"],
                    "duplicate_key_count": 0,
                },
                "campaign_product_daily": {
                    "expected_columns": [
                        "date",
                        "store_code",
                        "campaign_id",
                        "sku_key",
                        "cost",
                    ],
                    "row_count": 1,
                    "unique_key": [
                        "date",
                        "business_store_code",
                        "access_store_code",
                        "campaign_id",
                        "sku_key",
                    ],
                    "duplicate_key_count": 0,
                },
            },
        },
        "status": {
            "source_status": "FRESH",
            "heartbeat_status": "OK",
            "gap_status": "OK",
            "adapter_status": "OK",
            "allow_stale_used": False,
            "ads_source_stale_cleared_by_allow_stale": False,
            "freshness_truth_rewritten": False,
        },
        "spend_semantics": {
            "currency": "KZT",
            "cost_unit": "KZT",
            "missing_rows_are_zero_spend": False,
            "zero_spend_requires_source_backed_row": True,
        },
        "adapter_output": {
            "target_db_mode": "copied_temp_db",
            "evidence_root": str(tmp_path / "evidence"),
            "validator_outputs_under_evidence_root": True,
            "production_db_touched": False,
            "tables": {
                "ads_campaign_product_daily": {
                    "row_count": 1,
                    "lineage_fields": [
                        "source_run_id",
                        "source_contract_version",
                        "captured_at",
                        "source_db_sha",
                        "payload_hash",
                        "coverage_status",
                    ],
                },
                "ads_source_refresh_runs": {
                    "row_count": 1,
                    "lineage_fields": [
                        "status",
                        "source_freshness_age_hours",
                        "max_age_hours",
                        "heartbeat_status",
                        "gap_status",
                        "packet_sha256",
                    ],
                },
            },
        },
        "validator_replay": {
            "ads_sidecar_readiness": {
                "before_status": "PASS_WITH_ADS_SOURCE_STALE_WARNING",
                "after_status": "PASS",
                "ads_source_stale_status": "CLEARED_BY_SOURCE_FRESH_PACKET",
            },
            "ads_offer_universe_coverage": {
                "before_status": "PASS",
                "after_status": "PASS",
            },
        },
        "warning_cohorts": {
            "product_identity_quarantine": 23,
            "header_only_source_gap": 252,
            "preserved": True,
        },
    }


def _write_valid_packet_files(manifest: dict[str, object]) -> None:
    packet_root = Path(str(manifest["packet_root"]))
    packet_root.mkdir()
    source_db = packet_root / "kaspi_marketing.sqlite"
    source_db.write_text("source-payload", encoding="utf-8")
    redaction_manifest = packet_root / "redaction_manifest.json"
    redaction_manifest.write_text(
        json.dumps(
            {
                "no_secrets_included": True,
                "forbidden_artifacts_found": 0,
                "forbidden_artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    raw_payload_hash_manifest = packet_root / "raw_payload_hash_manifest.tsv"
    raw_payload_hash_manifest.write_text(
        f"{_sha256(source_db)}\tkaspi_marketing.sqlite\n",
        encoding="utf-8",
    )
    packet_sha_manifest = packet_root / "packet_sha256_manifest.tsv"
    packet_sha_manifest.write_text(
        "\n".join(
            [
                f"{'0' * 64}\tpacket_sha256_manifest.tsv",
                f"{_sha256(redaction_manifest)}\tredaction_manifest.json",
                f"{_sha256(raw_payload_hash_manifest)}\traw_payload_hash_manifest.tsv",
                f"{_sha256(source_db)}\tkaspi_marketing.sqlite",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_valid_ads_source_packet_contract_accepts_reviewed_packet_shape(tmp_path: Path) -> None:
    result = validate_ads_source_packet_manifest(_valid_manifest(tmp_path))

    assert result.ok is True
    assert result.business_store_code == "STOREB"
    assert result.access_store_code == "UNIVERSAL_SWITCHER_FOR_STOREB"


def test_existing_ads_source_packet_contract_accepts_hashed_packet(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    _write_valid_packet_files(manifest)

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is True


def test_ads_source_packet_contract_rejects_secret_artifacts(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["file_list"] = ["packet_sha256_manifest.tsv", ".env", "cookies.json"]

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert any("secret-like artifact path" in error for error in result.errors)


def test_ads_source_packet_contract_rejects_store_identity_conflict(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["store_identity"]["adapter_output_store_code"] = "UNIVERSAL"

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert "ADS_STORE_IDENTITY_CONFLICT" in "\n".join(result.errors)


def test_ads_source_packet_contract_rejects_duplicate_source_keys(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["source_db"]["tables"]["campaign_product_daily"]["duplicate_key_count"] = 1

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert any("duplicate_key_count must be 0" in error for error in result.errors)


def test_ads_source_packet_contract_rejects_missing_rows_as_zero_spend(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["spend_semantics"]["missing_rows_are_zero_spend"] = True

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert "missing source rows must not be treated as zero spend" in result.errors


def test_ads_source_packet_contract_rejects_allow_stale_clearing_freshness(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["status"]["allow_stale_used"] = True
    manifest["status"]["ads_source_stale_cleared_by_allow_stale"] = True

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert "allow-stale must not clear ADS_SOURCE_STALE" in result.errors


def test_ads_source_packet_contract_preserves_warning_cohorts(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["warning_cohorts"]["header_only_source_gap"] = 0

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert any("header_only_source_gap must remain 252" in error for error in result.errors)


def test_ads_source_packet_contract_rejects_malformed_numbers_without_crashing(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["capture"]["max_age_hours"] = "not-a-number"
    manifest["source_db"]["tables"]["campaign_daily"]["row_count"] = "many"
    manifest["source_db"]["tables"]["campaign_product_daily"]["duplicate_key_count"] = "many"

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert "capture.max_age_hours must be a number" in result.errors
    assert "source_db.tables.campaign_daily.row_count must be an integer" in result.errors
    assert (
        "source_db.tables.campaign_product_daily.duplicate_key_count must be an integer"
        in result.errors
    )


def test_ads_source_packet_contract_rejects_missing_listed_file_when_required(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    _write_valid_packet_files(manifest)
    (Path(str(manifest["packet_root"])) / "kaspi_marketing.sqlite").unlink()

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is False
    assert "file_list entry does not exist: kaspi_marketing.sqlite" in result.errors


def test_ads_source_packet_contract_rejects_file_list_path_escape(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["file_list"] = [
        "packet_sha256_manifest.tsv",
        "redaction_manifest.json",
        "raw_payload_hash_manifest.tsv",
        "../escape.sqlite",
    ]
    manifest["raw_payload_files"] = ["../escape.sqlite"]

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is False
    assert any("path must not contain path traversal" in error for error in result.errors)


def test_ads_source_packet_contract_rejects_packet_sha_manifest_missing_listed_file(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    _write_valid_packet_files(manifest)
    packet_root = Path(str(manifest["packet_root"]))
    (packet_root / "packet_sha256_manifest.tsv").write_text(
        "\n".join(
            [
                f"{'0' * 64}\tpacket_sha256_manifest.tsv",
                f"{_sha256(packet_root / 'redaction_manifest.json')}\tredaction_manifest.json",
                f"{_sha256(packet_root / 'raw_payload_hash_manifest.tsv')}\traw_payload_hash_manifest.tsv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is False
    assert any("packet_sha256_manifest missing entries" in error for error in result.errors)


def test_ads_source_packet_contract_rejects_empty_raw_payload_hash_manifest(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    _write_valid_packet_files(manifest)
    (Path(str(manifest["packet_root"])) / "raw_payload_hash_manifest.tsv").write_text(
        "",
        encoding="utf-8",
    )

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is False
    assert "raw_payload_hash_manifest must contain at least one payload hash" in result.errors


def test_ads_source_packet_contract_rejects_redaction_manifest_contradiction(
    tmp_path: Path,
) -> None:
    manifest = _valid_manifest(tmp_path)
    _write_valid_packet_files(manifest)
    (Path(str(manifest["packet_root"])) / "redaction_manifest.json").write_text(
        json.dumps(
            {
                "no_secrets_included": False,
                "forbidden_artifacts_found": 1,
                "forbidden_artifacts": ["cookies.json"],
            }
        ),
        encoding="utf-8",
    )

    result = validate_ads_source_packet_manifest(manifest, require_existing_files=True)

    assert result.ok is False
    assert "redaction_manifest.no_secrets_included=true is required" in result.errors
    assert "redaction manifest file must agree with inline no_secrets_included" in result.errors


def test_ads_source_packet_contract_rejects_source_db_sha_mismatch(tmp_path: Path) -> None:
    manifest = _valid_manifest(tmp_path)
    manifest["source_db_sha256"] = "a" * 64

    result = validate_ads_source_packet_manifest(manifest)

    assert result.ok is False
    assert "source_db_sha256 must equal source_db.sha256" in result.errors
