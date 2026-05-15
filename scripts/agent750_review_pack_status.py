#!/usr/bin/env python3
"""Shared read-only review-pack evidence helpers for the Agent750 gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _validator_manifest_unhealthy_payload(
    *,
    json_valid: bool,
    errors: list[str],
) -> dict:
    return {
        "latest_validator_manifest_json_valid": json_valid,
        "latest_validator_manifest_ok": None,
        "latest_validator_manifest_errors": errors,
        "latest_validator_manifest_status_pointer_error": None,
        "latest_validator_manifest_status_pointer_terms": [],
        "latest_validator_manifest_status_pointer_terms_match_status": False,
        "latest_validator_manifest_optional_upload_zip_sha256": None,
        "latest_validator_manifest_optional_upload_zip_sha256_matches_status": False,
        "latest_validator_manifest_optional_upload_zip_source_bytes_match": False,
    }


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validator_manifest_status(
    validator_manifest: Path,
    *,
    expected_zip_sha: str | None,
    expected_completion_audit: str | None,
) -> dict:
    if not validator_manifest.exists() or not validator_manifest.is_file():
        return _validator_manifest_unhealthy_payload(json_valid=False, errors=[])
    try:
        manifest = json.loads(validator_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _validator_manifest_unhealthy_payload(
            json_valid=False,
            errors=["validator_manifest_json_invalid"],
        )
    if not isinstance(manifest, dict):
        return _validator_manifest_unhealthy_payload(
            json_valid=True,
            errors=["validator_manifest_not_object"],
        )

    manifest_errors_raw = manifest.get("errors")
    if manifest_errors_raw is None:
        manifest_errors = []
    elif isinstance(manifest_errors_raw, list):
        manifest_errors = list(manifest_errors_raw)
    else:
        manifest_errors = [str(manifest_errors_raw)]
    optional_zip_raw = manifest.get("optional_upload_zip")
    if optional_zip_raw is None:
        optional_zip = {}
    elif isinstance(optional_zip_raw, dict):
        optional_zip = optional_zip_raw
    else:
        manifest_errors.append("validator_manifest_optional_upload_zip_not_object")
        optional_zip = {}
    manifest_zip_sha = optional_zip.get("sha256")
    if manifest_zip_sha is not None and not isinstance(manifest_zip_sha, str):
        manifest_errors.append("validator_manifest_optional_upload_zip_sha256_not_string")
        manifest_zip_sha = None
    source_bytes_match_raw = optional_zip.get("source_bytes_match")
    if source_bytes_match_raw is None:
        source_bytes_match = False
    elif isinstance(source_bytes_match_raw, bool):
        source_bytes_match = source_bytes_match_raw
    else:
        manifest_errors.append("validator_manifest_source_bytes_match_not_bool")
        source_bytes_match = False
    manifest_ok = manifest.get("ok")
    if manifest_ok is not None and not isinstance(manifest_ok, bool):
        manifest_errors.append("validator_manifest_ok_not_bool")
        manifest_ok = None
    status_pointer_terms_raw = manifest.get("status_pointer_terms")
    if status_pointer_terms_raw is None:
        status_pointer_terms = []
    elif isinstance(status_pointer_terms_raw, list):
        status_pointer_terms = status_pointer_terms_raw
    else:
        manifest_errors.append("validator_manifest_status_pointer_terms_not_list")
        status_pointer_terms = []
    return {
        "latest_validator_manifest_json_valid": True,
        "latest_validator_manifest_ok": manifest_ok,
        "latest_validator_manifest_errors": manifest_errors,
        "latest_validator_manifest_status_pointer_error": manifest.get("status_pointer_error"),
        "latest_validator_manifest_status_pointer_terms": status_pointer_terms,
        "latest_validator_manifest_status_pointer_terms_match_status": (
            bool(expected_completion_audit)
            and str(expected_completion_audit) in status_pointer_terms
        ),
        "latest_validator_manifest_optional_upload_zip_sha256": manifest_zip_sha,
        "latest_validator_manifest_optional_upload_zip_sha256_matches_status": (
            bool(expected_zip_sha) and manifest_zip_sha == expected_zip_sha
        ),
        "latest_validator_manifest_optional_upload_zip_source_bytes_match": (
            source_bytes_match
        ),
    }


def review_pack_blocking_errors(review_pack: dict) -> list[str]:
    """Return fail-closed errors for review-pack evidence required before launch."""
    if not isinstance(review_pack, dict):
        return ["review_pack_not_object"]

    errors: list[str] = []
    if not review_pack.get("status_path_exists"):
        errors.append("status_path_missing")
    if not review_pack.get("status_path_json_valid"):
        errors.append("status_json_invalid")
    status_path_error = review_pack.get("status_path_error")
    if status_path_error:
        errors.append(str(status_path_error))

    status_review_pack_errors = review_pack.get("status_review_pack_errors") or []
    if isinstance(status_review_pack_errors, list):
        errors.extend(str(error) for error in status_review_pack_errors)
    else:
        errors.append("status_review_pack_errors_not_list")

    if not review_pack.get("optional_upload_zip_exists"):
        errors.append("optional_upload_zip_missing")
    if not review_pack.get("optional_upload_zip_sha256_matches"):
        errors.append("optional_upload_zip_sha256_mismatch")
    if not review_pack.get("optional_upload_zip_manifest_exists"):
        errors.append("optional_upload_zip_manifest_missing")

    if not review_pack.get("latest_validator_manifest_exists"):
        errors.append("latest_validator_manifest_missing")
    if not review_pack.get("latest_validator_manifest_json_valid"):
        errors.append("latest_validator_manifest_json_invalid")
    if review_pack.get("latest_validator_manifest_ok") is not True:
        errors.append("latest_validator_manifest_not_ok")

    validator_errors = review_pack.get("latest_validator_manifest_errors") or []
    if isinstance(validator_errors, list):
        errors.extend(str(error) for error in validator_errors)
    else:
        errors.append("latest_validator_manifest_errors_not_list")

    status_pointer_error = review_pack.get("latest_validator_manifest_status_pointer_error")
    if status_pointer_error:
        errors.append(str(status_pointer_error))
    if not review_pack.get("latest_validator_manifest_status_pointer_terms_match_status"):
        errors.append("latest_validator_manifest_status_pointer_terms_mismatch")
    if not review_pack.get("latest_validator_manifest_optional_upload_zip_sha256_matches_status"):
        errors.append("latest_validator_manifest_optional_upload_zip_sha256_mismatch")
    if not review_pack.get("latest_validator_manifest_optional_upload_zip_source_bytes_match"):
        errors.append("latest_validator_manifest_optional_upload_zip_source_bytes_mismatch")

    return sorted(set(errors))


def review_pack_info_from_status(status_path: Path) -> dict:
    if not status_path.exists():
        return {
            "status_path": str(status_path),
            "status_path_exists": False,
            "status_path_json_valid": False,
            "status_path_error": "status_path_missing",
        }
    if not status_path.is_file():
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": False,
            "status_path_error": "status_path_not_file",
        }

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": False,
            "status_path_error": "status_json_invalid",
        }
    if not isinstance(status, dict):
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": "status_json_not_object",
        }
    if "review_pack" not in status:
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": "status_review_pack_missing",
        }
    review_pack_raw = status.get("review_pack")
    if not isinstance(review_pack_raw, dict):
        return {
            "status_path": str(status_path),
            "status_path_exists": True,
            "status_path_json_valid": True,
            "status_path_error": "status_review_pack_not_object",
        }
    review_pack = dict(review_pack_raw)
    review_pack["status_path"] = str(status_path)
    review_pack["status_path_exists"] = True
    review_pack["status_path_json_valid"] = True
    review_pack["status_path_error"] = None
    review_pack_errors: list[str] = []
    zip_path_raw = review_pack.get("optional_upload_zip")
    if isinstance(zip_path_raw, str):
        zip_path = Path(zip_path_raw)
    else:
        review_pack_errors.append("status_review_pack_optional_upload_zip_not_string")
        zip_path = None
    zip_sha = review_pack.get("optional_upload_zip_sha256")
    if zip_sha is not None and not isinstance(zip_sha, str):
        review_pack_errors.append("status_review_pack_optional_upload_zip_sha256_not_string")
        zip_sha = None
    actual_zip_sha = file_sha256(zip_path) if zip_path else None
    review_pack["status_review_pack_errors"] = review_pack_errors
    review_pack["optional_upload_zip_exists"] = bool(zip_path and zip_path.exists())
    review_pack["optional_upload_zip_actual_sha256"] = actual_zip_sha
    review_pack["optional_upload_zip_sha256_matches"] = (
        bool(zip_sha) and actual_zip_sha == zip_sha
    )

    zip_manifest_raw = review_pack.get("optional_upload_zip_manifest")
    if isinstance(zip_manifest_raw, str):
        zip_manifest = Path(zip_manifest_raw)
    else:
        review_pack_errors.append("status_review_pack_optional_upload_zip_manifest_not_string")
        zip_manifest = None
    validator_manifest_raw = review_pack.get("latest_validator_manifest")
    if isinstance(validator_manifest_raw, str):
        validator_manifest = Path(validator_manifest_raw)
    else:
        review_pack_errors.append("status_review_pack_latest_validator_manifest_not_string")
        validator_manifest = None
    review_pack["optional_upload_zip_manifest_exists"] = bool(
        zip_manifest and zip_manifest.exists()
    )
    review_pack["latest_validator_manifest_exists"] = bool(
        validator_manifest and validator_manifest.exists()
    )
    if validator_manifest:
        review_pack.update(
            validator_manifest_status(
                validator_manifest,
                expected_zip_sha=zip_sha,
                expected_completion_audit=status.get("latest_completion_audit"),
            )
        )
    else:
        review_pack.update(_validator_manifest_unhealthy_payload(json_valid=False, errors=[]))
    return review_pack
