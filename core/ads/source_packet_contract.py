from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SOURCE_CONTRACT_VERSION = "ads_web_source_packet.v1"

ALLOWED_STATUSES = frozenset(
    {
        "FRESH",
        "STALE",
        "MISSING",
        "PARTIAL",
        "GAP",
        "NO_AUTH",
        "ERROR",
        "BLOCKED",
        "OK",
    }
)

REQUIRED_SOURCE_TABLES = {
    "campaign_daily",
    "campaign_product_daily",
}

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

FORBIDDEN_SECRET_MARKERS = (
    ".env",
    "cookie",
    "cookies",
    "storage_state",
    "storagestate",
    "browser_profile",
    "profile",
    "credential",
    "credentials",
    "session",
    "token",
    "secret",
)


class AdsSourcePacketContractError(RuntimeError):
    """Raised when a Web_automation ads packet is not safe for AB proof use."""


@dataclass(frozen=True)
class AdsSourcePacketValidation:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    manifest_path: str | None
    packet_root: str | None
    source_contract_version: str | None
    business_store_code: str | None
    access_store_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "manifest_path": self.manifest_path,
            "packet_root": self.packet_root,
            "source_contract_version": self.source_contract_version,
            "business_store_code": self.business_store_code,
            "access_store_code": self.access_store_code,
        }


def load_ads_source_packet_manifest(manifest_path: Path) -> dict[str, Any]:
    candidate = Path(manifest_path).expanduser()
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AdsSourcePacketContractError(f"manifest is not valid JSON: {candidate}") from exc


def validate_ads_source_packet_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    require_existing_files: bool = False,
) -> AdsSourcePacketValidation:
    errors: list[str] = []
    warnings: list[str] = []

    version = _as_text(manifest.get("source_contract_version"))
    if version != SOURCE_CONTRACT_VERSION:
        errors.append(
            f"source_contract_version must be {SOURCE_CONTRACT_VERSION!r}, got {version!r}"
        )

    packet_root = _as_text(manifest.get("packet_root"))
    if not packet_root:
        errors.append("packet_root is required")
    packet_root_path = Path(packet_root).expanduser() if packet_root else None
    if require_existing_files and packet_root_path is not None and not packet_root_path.exists():
        errors.append(f"packet_root does not exist: {packet_root_path}")

    file_list = _as_list(manifest.get("file_list"))
    if not file_list:
        errors.append("file_list must contain at least one packet file")
    _validate_no_secret_paths(file_list, errors)
    normalized_file_list = _normalize_packet_members(file_list, "file_list", errors)
    if len(normalized_file_list) != len(set(normalized_file_list)):
        errors.append("file_list must not contain duplicate paths")

    raw_payload_files = _as_list(manifest.get("raw_payload_files"))
    if not raw_payload_files:
        errors.append("raw_payload_files must contain at least one source payload file")
    _validate_no_secret_paths(raw_payload_files, errors)
    normalized_raw_payload_files = _normalize_packet_members(
        raw_payload_files,
        "raw_payload_files",
        errors,
    )
    for raw_payload_file in normalized_raw_payload_files:
        if raw_payload_file not in normalized_file_list:
            errors.append(f"raw_payload_files entry is not present in file_list: {raw_payload_file}")
    if require_existing_files and packet_root_path is not None:
        _validate_packet_files_exist(normalized_file_list, packet_root_path, errors)

    if not _is_true(manifest.get("no_secrets_included")):
        errors.append("NO_SECRETS_INCLUDED=true is required")

    packet_sha_manifest = _validate_named_file_ref(
        manifest,
        "packet_sha256_manifest",
        normalized_file_list=normalized_file_list,
        packet_root_path=packet_root_path,
        errors=errors,
        require_existing_files=require_existing_files,
    )
    raw_payload_hash_manifest = _validate_named_file_ref(
        manifest,
        "raw_payload_hash_manifest",
        normalized_file_list=normalized_file_list,
        packet_root_path=packet_root_path,
        errors=errors,
        require_existing_files=require_existing_files,
    )
    redaction_manifest = _validate_named_file_ref(
        manifest,
        "redaction_manifest",
        normalized_file_list=normalized_file_list,
        packet_root_path=packet_root_path,
        errors=errors,
        require_existing_files=require_existing_files,
    )

    if require_existing_files and packet_root_path is not None:
        if packet_sha_manifest:
            _validate_packet_sha_manifest(
                packet_root_path=packet_root_path,
                packet_sha_manifest=packet_sha_manifest,
                file_list=normalized_file_list,
                errors=errors,
            )
        if raw_payload_hash_manifest:
            _validate_raw_payload_hash_manifest(
                packet_root_path=packet_root_path,
                raw_payload_hash_manifest=raw_payload_hash_manifest,
                raw_payload_files=normalized_raw_payload_files,
                errors=errors,
            )

    redaction = _as_dict(manifest.get("redaction"))
    if _int_value(
        redaction.get("forbidden_artifacts_found"),
        "redaction.forbidden_artifacts_found",
        errors,
    ) != 0:
        errors.append("redaction.forbidden_artifacts_found must be 0")
    if not _is_true(redaction.get("no_secrets_included")):
        errors.append("redaction.no_secrets_included=true is required")
    if require_existing_files and packet_root_path is not None and redaction_manifest:
        _validate_redaction_manifest_file(
            packet_root_path=packet_root_path,
            redaction_manifest=redaction_manifest,
            inline_redaction=redaction,
            errors=errors,
        )

    capture = _as_dict(manifest.get("capture"))
    for field in ("run_id", "captured_at", "finished_at", "timezone", "date_start", "date_end", "ab_as_of"):
        if not _as_text(capture.get(field)):
            errors.append(f"capture.{field} is required")
    if capture.get("date_window_inclusive") is not True:
        errors.append("capture.date_window_inclusive must be true")
    if _float_value(capture.get("max_age_hours"), "capture.max_age_hours", errors) <= 0:
        errors.append("capture.max_age_hours must be positive")
    _validate_iso_datetime(capture.get("captured_at"), "capture.captured_at", errors)
    _validate_iso_datetime(capture.get("finished_at"), "capture.finished_at", errors)
    if _as_text(capture.get("date_start")) and _as_text(capture.get("date_end")):
        if _as_text(capture.get("date_start")) > _as_text(capture.get("date_end")):
            errors.append("capture.date_start must be <= capture.date_end")

    identity = _as_dict(manifest.get("store_identity"))
    business_store_code = _as_text(identity.get("business_store_code")).upper()
    access_store_code = _as_text(identity.get("access_store_code")).upper()
    adapter_store_code = _as_text(identity.get("adapter_output_store_code")).upper()
    if not business_store_code:
        errors.append("store_identity.business_store_code is required")
    if not access_store_code:
        errors.append("store_identity.access_store_code is required")
    if not adapter_store_code:
        errors.append("store_identity.adapter_output_store_code is required")
    if business_store_code and adapter_store_code and adapter_store_code != business_store_code:
        errors.append("ADS_STORE_IDENTITY_CONFLICT: adapter output store_code must equal business_store_code")

    source_db = _as_dict(manifest.get("source_db"))
    for field in ("path", "sha256", "schema_hash"):
        if not _as_text(source_db.get(field)):
            errors.append(f"source_db.{field} is required")
    top_source_db_sha = _as_text(manifest.get("source_db_sha256"))
    source_db_sha = _as_text(source_db.get("sha256"))
    if not top_source_db_sha:
        errors.append("source_db_sha256 is required")
    elif not _is_sha256(top_source_db_sha):
        errors.append("source_db_sha256 must be a valid SHA-256 hex digest")
    if source_db_sha and not _is_sha256(source_db_sha):
        errors.append("source_db.sha256 must be a valid SHA-256 hex digest")
    if top_source_db_sha and source_db_sha and top_source_db_sha.lower() != source_db_sha.lower():
        errors.append("source_db_sha256 must equal source_db.sha256")
    tables = _as_dict(source_db.get("tables"))
    missing_tables = sorted(REQUIRED_SOURCE_TABLES - set(tables))
    if missing_tables:
        errors.append(f"source_db.tables missing required tables: {', '.join(missing_tables)}")
    for table_name, table in tables.items():
        _validate_source_table(str(table_name), _as_dict(table), errors)

    status = _as_dict(manifest.get("status"))
    for field in ("source_status", "heartbeat_status", "gap_status", "adapter_status"):
        value = _as_text(status.get(field)).upper()
        if value not in ALLOWED_STATUSES:
            errors.append(f"status.{field} must be one of {sorted(ALLOWED_STATUSES)}, got {value!r}")
    if _is_true(status.get("allow_stale_used")) and _is_true(status.get("ads_source_stale_cleared_by_allow_stale")):
        errors.append("allow-stale must not clear ADS_SOURCE_STALE")
    if _is_true(status.get("freshness_truth_rewritten")):
        errors.append("freshness truth must not be rewritten")

    spend = _as_dict(manifest.get("spend_semantics"))
    if _as_text(spend.get("currency")).upper() != "KZT":
        errors.append("spend_semantics.currency must be KZT")
    if _is_true(spend.get("missing_rows_are_zero_spend")):
        errors.append("missing source rows must not be treated as zero spend")
    if not _is_true(spend.get("zero_spend_requires_source_backed_row")):
        errors.append("zero spend requires a source-backed row or explicit source-backed zero")

    adapter = _as_dict(manifest.get("adapter_output"))
    if _as_text(adapter.get("target_db_mode")).lower() not in {"copied_db", "temp_db", "copied_temp_db"}:
        errors.append("adapter_output.target_db_mode must be copied_db, temp_db, or copied_temp_db")
    if _is_true(adapter.get("production_db_touched")):
        errors.append("adapter proof must not touch production db/app.db")
    if not _is_true(adapter.get("validator_outputs_under_evidence_root")):
        errors.append("validator outputs must stay under the proof evidence root")
    if not _as_text(adapter.get("evidence_root")):
        errors.append("adapter_output.evidence_root is required")
    adapter_tables = _as_dict(adapter.get("tables"))
    _validate_adapter_table(
        adapter_tables,
        "ads_campaign_product_daily",
        required_lineage={
            "source_run_id",
            "source_contract_version",
            "captured_at",
            "source_db_sha",
            "payload_hash",
            "coverage_status",
        },
        errors=errors,
    )
    _validate_adapter_table(
        adapter_tables,
        "ads_source_refresh_runs",
        required_lineage={
            "status",
            "source_freshness_age_hours",
            "max_age_hours",
            "heartbeat_status",
            "gap_status",
            "packet_sha256",
        },
        errors=errors,
    )

    replay = _as_dict(manifest.get("validator_replay"))
    for validator in ("ads_sidecar_readiness", "ads_offer_universe_coverage"):
        validator_payload = _as_dict(replay.get(validator))
        if not validator_payload:
            errors.append(f"validator_replay.{validator} is required")
            continue
        if not _as_text(validator_payload.get("before_status")):
            errors.append(f"validator_replay.{validator}.before_status is required")
        if not _as_text(validator_payload.get("after_status")):
            errors.append(f"validator_replay.{validator}.after_status is required")
    stale_status = _as_text(_as_dict(replay.get("ads_sidecar_readiness")).get("ads_source_stale_status")).upper()
    if stale_status not in {"CLEARED_BY_SOURCE_FRESH_PACKET", "STILL_VISIBLE", "RECLASSIFIED_TO_GAP"}:
        errors.append("validator_replay.ads_sidecar_readiness.ads_source_stale_status has unsupported value")

    warnings_payload = _as_dict(manifest.get("warning_cohorts"))
    if _int_value(
        warnings_payload.get("product_identity_quarantine"),
        "warning_cohorts.product_identity_quarantine",
        errors,
        default=-1,
    ) != 23:
        errors.append("warning_cohorts.product_identity_quarantine must remain 23")
    if _int_value(
        warnings_payload.get("header_only_source_gap"),
        "warning_cohorts.header_only_source_gap",
        errors,
        default=-1,
    ) != 252:
        errors.append("warning_cohorts.header_only_source_gap must remain 252")
    if not _is_true(warnings_payload.get("preserved")):
        errors.append("warning_cohorts.preserved=true is required")

    return AdsSourcePacketValidation(
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        manifest_path=str(manifest_path) if manifest_path is not None else None,
        packet_root=packet_root or None,
        source_contract_version=version or None,
        business_store_code=business_store_code or None,
        access_store_code=access_store_code or None,
    )


def validate_ads_source_packet_file(
    manifest_path: Path,
    *,
    require_existing_files: bool = False,
    strict: bool = False,
) -> AdsSourcePacketValidation:
    manifest = load_ads_source_packet_manifest(manifest_path)
    validation = validate_ads_source_packet_manifest(
        manifest,
        manifest_path=Path(manifest_path).expanduser(),
        require_existing_files=require_existing_files,
    )
    if strict and not validation.ok:
        raise AdsSourcePacketContractError("; ".join(validation.errors))
    return validation


def _validate_source_table(name: str, table: dict[str, Any], errors: list[str]) -> None:
    if not _as_list(table.get("expected_columns")):
        errors.append(f"source_db.tables.{name}.expected_columns is required")
    if _int_value(table.get("row_count"), f"source_db.tables.{name}.row_count", errors) < 0:
        errors.append(f"source_db.tables.{name}.row_count must be >= 0")
    if not _as_list(table.get("unique_key")):
        errors.append(f"source_db.tables.{name}.unique_key is required")
    if _int_value(
        table.get("duplicate_key_count"),
        f"source_db.tables.{name}.duplicate_key_count",
        errors,
    ) != 0:
        errors.append(f"source_db.tables.{name}.duplicate_key_count must be 0")


def _validate_adapter_table(
    tables: dict[str, Any],
    table_name: str,
    *,
    required_lineage: set[str],
    errors: list[str],
) -> None:
    table = _as_dict(tables.get(table_name))
    if not table:
        errors.append(f"adapter_output.tables.{table_name} is required")
        return
    if _int_value(table.get("row_count"), f"adapter_output.tables.{table_name}.row_count", errors) < 0:
        errors.append(f"adapter_output.tables.{table_name}.row_count must be >= 0")
    lineage = {str(v).strip() for v in _as_list(table.get("lineage_fields")) if str(v).strip()}
    missing = sorted(required_lineage - lineage)
    if missing:
        errors.append(
            f"adapter_output.tables.{table_name}.lineage_fields missing: {', '.join(missing)}"
        )


def _validate_named_file_ref(
    manifest: dict[str, Any],
    field: str,
    *,
    normalized_file_list: list[str],
    packet_root_path: Path | None,
    errors: list[str],
    require_existing_files: bool,
) -> str | None:
    value = _as_text(manifest.get(field))
    if not value:
        errors.append(f"{field} is required")
        return None
    _validate_no_secret_paths([value], errors)
    normalized = _normalize_packet_member(value, field, errors)
    if normalized and normalized_file_list and normalized not in normalized_file_list:
        errors.append(f"{field} must be listed in file_list: {normalized}")
    if require_existing_files and packet_root_path is not None and normalized:
        candidate = _packet_member_path(packet_root_path, normalized)
        if not candidate.exists():
            errors.append(f"{field} does not exist: {candidate}")
        elif not candidate.is_file():
            errors.append(f"{field} must be a file: {candidate}")
    return normalized


def _validate_packet_files_exist(
    file_list: list[str],
    packet_root_path: Path,
    errors: list[str],
) -> None:
    for relative_path in file_list:
        candidate = _packet_member_path(packet_root_path, relative_path)
        if not _is_relative_to(candidate.resolve(strict=False), packet_root_path.resolve(strict=False)):
            errors.append(f"file_list entry resolves outside packet_root: {relative_path}")
            continue
        if not candidate.exists():
            errors.append(f"file_list entry does not exist: {relative_path}")
        elif not candidate.is_file():
            errors.append(f"file_list entry must be a file: {relative_path}")


def _validate_packet_sha_manifest(
    *,
    packet_root_path: Path,
    packet_sha_manifest: str,
    file_list: list[str],
    errors: list[str],
) -> None:
    manifest_path = _packet_member_path(packet_root_path, packet_sha_manifest)
    entries = _parse_hash_manifest(manifest_path, "packet_sha256_manifest", errors)
    _validate_hash_manifest_coverage(
        entries=entries,
        expected_paths=file_list,
        label="packet_sha256_manifest",
        errors=errors,
    )
    for relative_path, expected_hash in entries.items():
        if relative_path == packet_sha_manifest:
            continue
        candidate = _packet_member_path(packet_root_path, relative_path)
        if candidate.exists() and candidate.is_file():
            actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual_hash.lower() != expected_hash.lower():
                errors.append(f"packet_sha256_manifest hash mismatch for {relative_path}")


def _validate_raw_payload_hash_manifest(
    *,
    packet_root_path: Path,
    raw_payload_hash_manifest: str,
    raw_payload_files: list[str],
    errors: list[str],
) -> None:
    manifest_path = _packet_member_path(packet_root_path, raw_payload_hash_manifest)
    entries = _parse_hash_manifest(manifest_path, "raw_payload_hash_manifest", errors)
    if not entries:
        errors.append("raw_payload_hash_manifest must contain at least one payload hash")
        return
    _validate_hash_manifest_coverage(
        entries=entries,
        expected_paths=raw_payload_files,
        label="raw_payload_hash_manifest",
        errors=errors,
    )
    for relative_path in raw_payload_files:
        expected_hash = entries.get(relative_path)
        if not expected_hash:
            continue
        candidate = _packet_member_path(packet_root_path, relative_path)
        if candidate.exists() and candidate.is_file():
            actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual_hash.lower() != expected_hash.lower():
                errors.append(f"raw_payload_hash_manifest hash mismatch for {relative_path}")


def _validate_hash_manifest_coverage(
    *,
    entries: dict[str, str],
    expected_paths: list[str],
    label: str,
    errors: list[str],
) -> None:
    missing = sorted(set(expected_paths) - set(entries))
    extra = sorted(set(entries) - set(expected_paths))
    if missing:
        errors.append(f"{label} missing entries for: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} contains unexpected entries: {', '.join(extra)}")


def _validate_redaction_manifest_file(
    *,
    packet_root_path: Path,
    redaction_manifest: str,
    inline_redaction: dict[str, Any],
    errors: list[str],
) -> None:
    path = _packet_member_path(packet_root_path, redaction_manifest)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"redaction_manifest is not readable: {redaction_manifest} ({exc})")
        return
    except json.JSONDecodeError:
        errors.append(f"redaction_manifest is not valid JSON: {redaction_manifest}")
        return
    if not isinstance(payload, dict):
        errors.append("redaction_manifest must contain a JSON object")
        return
    file_no_secrets = _is_true(payload.get("no_secrets_included"))
    file_forbidden_count = _int_value(
        payload.get("forbidden_artifacts_found"),
        "redaction_manifest.forbidden_artifacts_found",
        errors,
    )
    forbidden_artifacts = _as_list(payload.get("forbidden_artifacts"))
    if not file_no_secrets:
        errors.append("redaction_manifest.no_secrets_included=true is required")
    if file_forbidden_count != 0:
        errors.append("redaction_manifest.forbidden_artifacts_found must be 0")
    if forbidden_artifacts:
        errors.append("redaction_manifest.forbidden_artifacts must be empty")
    if _is_true(inline_redaction.get("no_secrets_included")) != file_no_secrets:
        errors.append("redaction manifest file must agree with inline no_secrets_included")
    inline_forbidden_count = _int_value(
        inline_redaction.get("forbidden_artifacts_found"),
        "redaction.forbidden_artifacts_found",
        errors,
    )
    if inline_forbidden_count != file_forbidden_count:
        errors.append("redaction manifest file must agree with inline forbidden_artifacts_found")


def _parse_hash_manifest(path: Path, label: str, errors: list[str]) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{label} is not readable: {path} ({exc})")
        return {}
    if path.suffix.lower() == ".json":
        return _parse_json_hash_manifest(text, label, errors)
    return _parse_text_hash_manifest(text, label, errors)


def _parse_json_hash_manifest(text: str, label: str, errors: list[str]) -> dict[str, str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        errors.append(f"{label} is not valid JSON")
        return {}
    rows: list[Any]
    if isinstance(payload, dict) and isinstance(payload.get("files"), list):
        rows = payload["files"]
    elif isinstance(payload, dict) and isinstance(payload.get("payloads"), list):
        rows = payload["payloads"]
    elif isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        entries: dict[str, str] = {}
        for raw_path, raw_hash in payload.items():
            _add_hash_manifest_entry(entries, raw_path, raw_hash, label, errors)
        return entries
    else:
        errors.append(f"{label} must contain a JSON object or list")
        return {}
    entries = {}
    for row in rows:
        row_dict = _as_dict(row)
        raw_path = row_dict.get("path") or row_dict.get("file") or row_dict.get("payload")
        raw_hash = row_dict.get("sha256") or row_dict.get("hash")
        _add_hash_manifest_entry(entries, raw_path, raw_hash, label, errors)
    return entries


def _parse_text_hash_manifest(text: str, label: str, errors: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part for part in re.split(r"[\t, ]+", line, maxsplit=1) if part]
        if len(parts) != 2:
            errors.append(f"{label} line {line_number} must contain path and sha256")
            continue
        first, second = parts
        if _is_sha256(first):
            raw_hash, raw_path = first, second
        else:
            raw_path, raw_hash = first, second
        _add_hash_manifest_entry(entries, raw_path, raw_hash, label, errors)
    return entries


def _add_hash_manifest_entry(
    entries: dict[str, str],
    raw_path: Any,
    raw_hash: Any,
    label: str,
    errors: list[str],
) -> None:
    normalized_path = _normalize_packet_member(raw_path, label, errors)
    hash_text = _as_text(raw_hash)
    if not _is_sha256(hash_text):
        errors.append(f"{label} entry for {raw_path!r} must contain a valid SHA-256")
        return
    if not normalized_path:
        return
    if normalized_path in entries:
        errors.append(f"{label} contains duplicate entry for {normalized_path}")
        return
    entries[normalized_path] = hash_text


def _normalize_packet_members(raw_paths: list[Any], label: str, errors: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in raw_paths:
        candidate = _normalize_packet_member(raw_path, label, errors)
        if candidate:
            normalized.append(candidate)
    return normalized


def _normalize_packet_member(raw_path: Any, label: str, errors: list[str]) -> str | None:
    path_text = _as_text(raw_path)
    if not path_text:
        errors.append(f"{label} contains an empty path")
        return None
    candidate = Path(path_text)
    if candidate.is_absolute():
        errors.append(f"{label} path must be relative to packet_root: {path_text}")
        return None
    if any(part in {"..", ""} for part in candidate.parts):
        errors.append(f"{label} path must not contain path traversal: {path_text}")
        return None
    return candidate.as_posix()


def _packet_member_path(packet_root_path: Path, relative_path: str) -> Path:
    return packet_root_path / relative_path


def _validate_no_secret_paths(paths: list[Any], errors: list[str]) -> None:
    for raw in paths:
        path = str(raw or "").strip().lower()
        if any(marker in path for marker in FORBIDDEN_SECRET_MARKERS):
            errors.append(f"secret-like artifact path is forbidden in packet: {raw}")


def _validate_iso_datetime(value: Any, label: str, errors: list[str]) -> None:
    raw = _as_text(value)
    if not raw:
        return
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be ISO-8601 datetime")


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_sha256(value: str) -> bool:
    return bool(SHA256_RE.fullmatch(value.strip()))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _int_value(value: Any, label: str, errors: list[str], *, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        errors.append(f"{label} must be an integer")
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be an integer")
        return default


def _float_value(value: Any, label: str, errors: list[str], *, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        errors.append(f"{label} must be a number")
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a number")
        return default


def _is_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False
