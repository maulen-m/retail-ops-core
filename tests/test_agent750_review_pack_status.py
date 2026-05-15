import hashlib
import json
from pathlib import Path

from scripts.agent750_review_pack_status import (
    review_pack_blocking_errors,
    review_pack_info_from_status,
    validator_manifest_status,
)


def test_review_pack_status_reports_missing_status_file(tmp_path):
    status_path = tmp_path / "missing_status.json"

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": False,
        "status_path_json_valid": False,
        "status_path_error": "status_path_missing",
    }


def test_review_pack_status_reports_malformed_status_file(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text("{not-json", encoding="utf-8")

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": True,
        "status_path_json_valid": False,
        "status_path_error": "status_json_invalid",
    }


def test_review_pack_status_reports_status_path_directory(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.mkdir()

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": True,
        "status_path_json_valid": False,
        "status_path_error": "status_path_not_file",
    }


def test_review_pack_status_reports_status_json_not_object(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text("[]", encoding="utf-8")

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": "status_json_not_object",
    }


def test_review_pack_status_reports_missing_review_pack_object(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text(json.dumps({"latest_completion_audit": "/tmp/audit.md"}), encoding="utf-8")

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": "status_review_pack_missing",
    }


def test_review_pack_status_reports_review_pack_not_object(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text(
        json.dumps({"latest_completion_audit": "/tmp/audit.md", "review_pack": []}),
        encoding="utf-8",
    )

    payload = review_pack_info_from_status(status_path)

    assert payload == {
        "status_path": str(status_path),
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": "status_review_pack_not_object",
    }


def test_validator_manifest_status_reports_invalid_json(tmp_path):
    manifest = tmp_path / "validator_manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")

    payload = validator_manifest_status(
        manifest,
        expected_zip_sha="abc",
        expected_completion_audit="/tmp/audit.md",
    )

    assert payload["latest_validator_manifest_json_valid"] is False
    assert payload["latest_validator_manifest_ok"] is None
    assert payload["latest_validator_manifest_errors"] == [
        "validator_manifest_json_invalid"
    ]
    assert payload["latest_validator_manifest_status_pointer_terms_match_status"] is False
    assert (
        payload["latest_validator_manifest_optional_upload_zip_sha256_matches_status"]
        is False
    )
    assert (
        payload["latest_validator_manifest_optional_upload_zip_source_bytes_match"]
        is False
    )


def test_validator_manifest_status_reports_json_not_object(tmp_path):
    manifest = tmp_path / "validator_manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    payload = validator_manifest_status(
        manifest,
        expected_zip_sha="abc",
        expected_completion_audit="/tmp/audit.md",
    )

    assert payload["latest_validator_manifest_json_valid"] is True
    assert payload["latest_validator_manifest_ok"] is None
    assert payload["latest_validator_manifest_errors"] == [
        "validator_manifest_not_object"
    ]
    assert payload["latest_validator_manifest_status_pointer_terms"] == []
    assert payload["latest_validator_manifest_status_pointer_terms_match_status"] is False
    assert (
        payload["latest_validator_manifest_optional_upload_zip_sha256_matches_status"]
        is False
    )
    assert (
        payload["latest_validator_manifest_optional_upload_zip_source_bytes_match"]
        is False
    )


def test_validator_manifest_status_reports_bad_nested_shapes(tmp_path):
    manifest = tmp_path / "validator_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "errors": "existing-error",
                "status_pointer_error": None,
                "status_pointer_terms": "not-a-list",
                "optional_upload_zip": [],
            }
        ),
        encoding="utf-8",
    )

    payload = validator_manifest_status(
        manifest,
        expected_zip_sha="abc",
        expected_completion_audit="/tmp/audit.md",
    )

    assert payload["latest_validator_manifest_json_valid"] is True
    assert payload["latest_validator_manifest_ok"] is True
    assert payload["latest_validator_manifest_errors"] == [
        "existing-error",
        "validator_manifest_optional_upload_zip_not_object",
        "validator_manifest_status_pointer_terms_not_list",
    ]
    assert payload["latest_validator_manifest_status_pointer_terms"] == []
    assert payload["latest_validator_manifest_status_pointer_terms_match_status"] is False
    assert payload["latest_validator_manifest_optional_upload_zip_sha256"] is None
    assert (
        payload["latest_validator_manifest_optional_upload_zip_sha256_matches_status"]
        is False
    )
    assert (
        payload["latest_validator_manifest_optional_upload_zip_source_bytes_match"]
        is False
    )


def test_validator_manifest_status_reports_bool_and_sha_shape_errors(tmp_path):
    latest_audit = "/tmp/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_CURRENT.md"
    manifest = tmp_path / "validator_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "ok": "true",
                "errors": [],
                "status_pointer_error": None,
                "status_pointer_terms": [latest_audit],
                "optional_upload_zip": {
                    "sha256": 123,
                    "source_bytes_match": "false",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = validator_manifest_status(
        manifest,
        expected_zip_sha="123",
        expected_completion_audit=latest_audit,
    )

    assert payload["latest_validator_manifest_json_valid"] is True
    assert payload["latest_validator_manifest_ok"] is None
    assert payload["latest_validator_manifest_errors"] == [
        "validator_manifest_optional_upload_zip_sha256_not_string",
        "validator_manifest_source_bytes_match_not_bool",
        "validator_manifest_ok_not_bool",
    ]
    assert payload["latest_validator_manifest_status_pointer_terms"] == [latest_audit]
    assert payload["latest_validator_manifest_status_pointer_terms_match_status"] is True
    assert payload["latest_validator_manifest_optional_upload_zip_sha256"] is None
    assert (
        payload["latest_validator_manifest_optional_upload_zip_sha256_matches_status"]
        is False
    )
    assert (
        payload["latest_validator_manifest_optional_upload_zip_source_bytes_match"]
        is False
    )


def test_review_pack_status_reports_bad_review_pack_field_shapes(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text(
        json.dumps(
            {
                "latest_completion_audit": "/tmp/audit.md",
                "review_pack": {
                    "optional_upload_zip": None,
                    "optional_upload_zip_sha256": 123,
                    "optional_upload_zip_manifest": [],
                    "latest_validator_manifest": {},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = review_pack_info_from_status(status_path)

    assert payload["status_path_json_valid"] is True
    assert payload["status_path_error"] is None
    assert payload["status_review_pack_errors"] == [
        "status_review_pack_optional_upload_zip_not_string",
        "status_review_pack_optional_upload_zip_sha256_not_string",
        "status_review_pack_optional_upload_zip_manifest_not_string",
        "status_review_pack_latest_validator_manifest_not_string",
    ]
    assert payload["optional_upload_zip_exists"] is False
    assert payload["optional_upload_zip_actual_sha256"] is None
    assert payload["optional_upload_zip_sha256_matches"] is False
    assert payload["optional_upload_zip_manifest_exists"] is False
    assert payload["latest_validator_manifest_exists"] is False
    assert payload["latest_validator_manifest_json_valid"] is False
    assert payload["latest_validator_manifest_errors"] == []


def test_review_pack_blocking_errors_accepts_current_healthy_payload(tmp_path):
    latest_audit = "/tmp/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_CURRENT.md"
    zip_path = tmp_path / "review_UPLOAD_ONLY.zip"
    zip_path.write_bytes(b"zip-bytes")
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_manifest = tmp_path / "review_UPLOAD_ONLY_MANIFEST.md"
    zip_manifest.write_text("manifest\n", encoding="utf-8")
    validator_manifest = tmp_path / "validator_manifest.json"
    validator_manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "errors": [],
                "status_pointer_error": None,
                "status_pointer_terms": [latest_audit],
                "optional_upload_zip": {
                    "sha256": zip_sha,
                    "source_bytes_match": True,
                },
            }
        ),
        encoding="utf-8",
    )
    status_path = tmp_path / "current_status.json"
    status_path.write_text(
        json.dumps(
            {
                "latest_completion_audit": latest_audit,
                "review_pack": {
                    "optional_upload_zip": str(zip_path),
                    "optional_upload_zip_sha256": zip_sha,
                    "optional_upload_zip_manifest": str(zip_manifest),
                    "latest_validator_manifest": str(validator_manifest),
                },
            }
        ),
        encoding="utf-8",
    )

    payload = review_pack_info_from_status(status_path)

    assert review_pack_blocking_errors(payload) == []


def test_review_pack_blocking_errors_reports_all_unhealthy_evidence():
    payload = {
        "status_path_exists": True,
        "status_path_json_valid": True,
        "status_path_error": None,
        "status_review_pack_errors": ["status_review_pack_optional_upload_zip_not_string"],
        "optional_upload_zip_exists": False,
        "optional_upload_zip_sha256_matches": False,
        "optional_upload_zip_manifest_exists": False,
        "latest_validator_manifest_exists": False,
        "latest_validator_manifest_json_valid": False,
        "latest_validator_manifest_ok": None,
        "latest_validator_manifest_errors": ["validator_manifest_source_bytes_match_not_bool"],
        "latest_validator_manifest_status_pointer_error": "status_pointer_source_missing",
        "latest_validator_manifest_status_pointer_terms_match_status": False,
        "latest_validator_manifest_optional_upload_zip_sha256_matches_status": False,
        "latest_validator_manifest_optional_upload_zip_source_bytes_match": False,
    }

    assert review_pack_blocking_errors(payload) == [
        "latest_validator_manifest_json_invalid",
        "latest_validator_manifest_missing",
        "latest_validator_manifest_not_ok",
        "latest_validator_manifest_optional_upload_zip_sha256_mismatch",
        "latest_validator_manifest_optional_upload_zip_source_bytes_mismatch",
        "latest_validator_manifest_status_pointer_terms_mismatch",
        "optional_upload_zip_manifest_missing",
        "optional_upload_zip_missing",
        "optional_upload_zip_sha256_mismatch",
        "status_pointer_source_missing",
        "status_review_pack_optional_upload_zip_not_string",
        "validator_manifest_source_bytes_match_not_bool",
    ]


def test_review_pack_status_reports_validator_manifest_health(tmp_path):
    latest_audit = "/tmp/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_CURRENT.md"
    zip_path = tmp_path / "review_UPLOAD_ONLY.zip"
    zip_path.write_bytes(b"zip-bytes")
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_manifest = tmp_path / "review_UPLOAD_ONLY_MANIFEST.md"
    zip_manifest.write_text("manifest\n", encoding="utf-8")
    validator_manifest = tmp_path / "validator_manifest.json"
    validator_manifest.write_text(
        json.dumps(
            {
                "ok": True,
                "errors": [],
                "status_pointer_error": None,
                "status_pointer_terms": [latest_audit],
                "optional_upload_zip": {
                    "sha256": zip_sha,
                    "source_bytes_match": True,
                },
            }
        ),
        encoding="utf-8",
    )
    status_path = tmp_path / "current_status.json"
    status_path.write_text(
        json.dumps(
            {
                "latest_completion_audit": latest_audit,
                "review_pack": {
                    "path": "/tmp/review/",
                    "prompt_sha256": "prompt-sha",
                    "optional_upload_zip": str(zip_path),
                    "optional_upload_zip_sha256": zip_sha,
                    "optional_upload_zip_manifest": str(zip_manifest),
                    "latest_validator_manifest": str(validator_manifest),
                },
            }
        ),
        encoding="utf-8",
    )

    payload = review_pack_info_from_status(status_path)

    assert payload["status_path"] == str(status_path)
    assert payload["status_path_exists"] is True
    assert payload["status_path_json_valid"] is True
    assert payload["status_path_error"] is None
    assert payload["optional_upload_zip_exists"] is True
    assert payload["optional_upload_zip_actual_sha256"] == zip_sha
    assert payload["optional_upload_zip_sha256_matches"] is True
    assert payload["optional_upload_zip_manifest_exists"] is True
    assert payload["latest_validator_manifest_exists"] is True
    assert payload["latest_validator_manifest_json_valid"] is True
    assert payload["latest_validator_manifest_ok"] is True
    assert payload["latest_validator_manifest_errors"] == []
    assert payload["latest_validator_manifest_status_pointer_error"] is None
    assert payload["latest_validator_manifest_status_pointer_terms"] == [latest_audit]
    assert payload["latest_validator_manifest_status_pointer_terms_match_status"] is True
    assert payload["latest_validator_manifest_optional_upload_zip_sha256"] == zip_sha
    assert (
        payload["latest_validator_manifest_optional_upload_zip_sha256_matches_status"]
        is True
    )
    assert (
        payload["latest_validator_manifest_optional_upload_zip_source_bytes_match"]
        is True
    )
