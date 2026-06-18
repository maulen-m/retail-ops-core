#!/usr/bin/env python3
"""Validate the final LINE31 Meta creative mapping before publish."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAPPING = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_goal_stock_dashboard_repair_20260601_133438"
    / "final_creative_asset_mapping_template.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_FENCE_RE = re.compile(
    r"## Required Owner Approval Phrase.*?```text\s*(.*?)\s*```",
    re.DOTALL,
)
PLACEHOLDER_URI_MARKERS = (
    "...",
    "<",
    ">",
    "example",
    "placeholder",
    "replace-with",
    "replace_with",
)
PLACEHOLDER_URI_HOST_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".example.test",
    ".invalid",
)
REQUIRED_TRACKING_EVENTS = (
    "PageView",
    "ViewContent",
    "ColorSelect",
    "KaspiClick",
    "HighIntentKaspiClick",
)
REQUIRED_TRACKING_UTM_KEYS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_placement",
)
FORBIDDEN_FAKE_ECOMMERCE_EVENTS = (
    "Purchase",
    "AddToCart",
    "InitiateCheckout",
    "AddPaymentInfo",
)


@dataclass(frozen=True)
class CreativeMappingResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    metrics: dict[str, Any]


def _project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return data


def _is_remote_uri(value: str) -> bool:
    scheme = urlparse(value).scheme.lower()
    return scheme in {"http", "https", "s3", "gs", "ipfs"}


def _is_placeholder_uri(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in PLACEHOLDER_URI_MARKERS):
        return True
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    return any(host.endswith(suffix) for suffix in PLACEHOLDER_URI_HOST_SUFFIXES)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_owner_approval_phrase(path: Path) -> str:
    resolved = _project_path(str(path))
    text = resolved.read_text(encoding="utf-8")
    match = APPROVAL_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    plain = text.strip()
    if plain.startswith("I approve "):
        return plain
    raise ValueError(f"could not find required owner approval phrase in {resolved}")


def _require_text(
    row: dict[str, Any],
    field: str,
    index: int,
    errors: list[str],
    *,
    template_ok: bool,
) -> str:
    value = str(row.get(field) or "").strip()
    if not value and not template_ok:
        errors.append(f"assets[{index}].{field} is required")
    return value


def _validate_sha(
    value: str,
    field: str,
    index: int,
    errors: list[str],
    *,
    template_ok: bool,
) -> None:
    if not value:
        if not template_ok:
            errors.append(f"assets[{index}].{field} is required")
        return
    if not SHA256_RE.fullmatch(value):
        errors.append(f"assets[{index}].{field} must be lowercase 64-char SHA-256 hex")


def _validate_url_utm(
    url: str,
    index: int,
    required_contract: dict[str, Any],
    row: dict[str, Any],
    errors: list[str],
    *,
    template_ok: bool,
) -> None:
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} and not template_ok:
        errors.append(f"assets[{index}].landing_url must be http(s)")
        return

    query = parse_qs(parsed.query)
    for field in required_contract.get("required_fields", []):
        if field not in query and not template_ok:
            errors.append(f"assets[{index}].landing_url missing {field}")

    expected_static = {
        "utm_source": required_contract.get("utm_source"),
        "utm_medium": required_contract.get("utm_medium"),
        "utm_campaign": required_contract.get("utm_campaign"),
        "utm_content": str(row.get("utm_content") or "").strip() or None,
        "utm_placement": str(row.get("utm_placement") or "").strip() or None,
    }
    for field, expected in expected_static.items():
        if not expected or field not in query:
            continue
        values = {value.strip() for value in query[field] if value.strip()}
        if expected not in values and not template_ok:
            errors.append(
                f"assets[{index}].landing_url {field}={sorted(values)} does not include expected {expected}"
            )


def _validate_publish_uri_not_placeholder(
    value: str,
    field: str,
    index: int,
    errors: list[str],
    *,
    template_ok: bool,
) -> None:
    if template_ok or not value:
        return
    if _is_placeholder_uri(value):
        errors.append(f"assets[{index}].{field} must not be a placeholder/example URI for publish readiness")


def _tracking_landing_payload(payload: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    root = payload.get("root")
    landing = payload.get("landing")
    if isinstance(root, dict):
        return root
    if isinstance(landing, dict):
        return landing
    errors.append("tracking_redirect_qa evidence must contain root or landing object")
    return {}


def _validate_tracking_payload(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("gate") != "GREEN":
        errors.append("tracking_redirect_qa evidence gate must be GREEN")

    if payload.get("qa_scope") != "live_postdeploy":
        errors.append("tracking_redirect_qa evidence qa_scope must be live_postdeploy")
    target_base_url = str(payload.get("target_base_url") or payload.get("probe_base_url") or "").strip()
    parsed_target = urlparse(target_base_url)
    if parsed_target.scheme != "https" or parsed_target.netloc != "acmewear.pro":
        errors.append("tracking_redirect_qa evidence target_base_url must be https://acmewear.pro")

    landing = _tracking_landing_payload(payload, errors)
    if landing.get("status") != 200:
        errors.append("tracking_redirect_qa landing route must return HTTP 200")
    missing_root = landing.get("missing_expected_utm_params")
    if missing_root:
        errors.append("tracking_redirect_qa landing runtime config is missing expected UTM params")
    tracked = set(landing.get("tracked_params_in_runtime_config") or [])
    if not set(REQUIRED_TRACKING_UTM_KEYS).issubset(tracked):
        errors.append("tracking_redirect_qa landing runtime config missing required LINE31 UTM keys")

    events = payload.get("browser_events")
    if not isinstance(events, list):
        errors.append("tracking_redirect_qa browser_events must be a list")
        events = []
    by_name = {
        str(row.get("event_name")): row
        for row in events
        if isinstance(row, dict) and row.get("event_name")
    }
    for event_name in REQUIRED_TRACKING_EVENTS:
        row = by_name.get(event_name)
        if not row:
            errors.append(f"tracking_redirect_qa missing browser event {event_name}")
            continue
        if row.get("api_status") != 204 or row.get("stored") is not True:
            errors.append(f"tracking_redirect_qa browser event {event_name} must be stored with HTTP 204")

    routes = payload.get("redirect_routes")
    if not isinstance(routes, list) or not routes:
        errors.append("tracking_redirect_qa redirect_routes must be a non-empty list")
        routes = []
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must be an object")
            continue
        if route.get("http_status") != 302:
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must return HTTP 302")
        if route.get("destination_route_matches_registry") is not True:
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must match registry destination")
        if route.get("tracked_utm_keys_missing_or_wrong"):
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must preserve required UTM keys")
        if route.get("landing_color_preserved") is not True:
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must preserve selected color")
        if route.get("landing_source_preserved") is not True:
            errors.append(f"tracking_redirect_qa redirect_routes[{index}] must preserve landing source")

    fallback = payload.get("fallback_route")
    if not isinstance(fallback, dict):
        errors.append("tracking_redirect_qa fallback_route must be an object")
        fallback = {}
    if fallback.get("http_status") != 302:
        errors.append("tracking_redirect_qa fallback_route must return HTTP 302")
    if fallback.get("tracked_utm_keys_missing_or_wrong"):
        errors.append("tracking_redirect_qa fallback_route must preserve required UTM keys")
    if fallback.get("landing_color_preserved") is not True:
        errors.append("tracking_redirect_qa fallback_route must preserve selected color")
    if fallback.get("landing_source_preserved") is not True:
        errors.append("tracking_redirect_qa fallback_route must preserve landing source")

    fail_closed = payload.get("fail_closed_checks")
    if not isinstance(fail_closed, dict):
        errors.append("tracking_redirect_qa fail_closed_checks must be an object")
        fail_closed = {}
    if fail_closed.get("browser_spoofed_kaspi_redirect_status") != 400:
        errors.append("tracking_redirect_qa must reject browser-spoofed KaspiRedirect")
    if fail_closed.get("fake_purchase_status") != 400:
        errors.append("tracking_redirect_qa must reject fake Purchase")
    if fail_closed.get("unknown_color_status") != 404:
        errors.append("tracking_redirect_qa must reject invalid /go/:color routes")

    no_fake = payload.get("no_fake_ecommerce_events")
    if not isinstance(no_fake, dict):
        errors.append("tracking_redirect_qa no_fake_ecommerce_events must be an object")
        no_fake = {}
    if no_fake.get("fake_purchase_rejected") is not True:
        errors.append("tracking_redirect_qa must prove fake ecommerce events are rejected")
    forbidden_checked = set(no_fake.get("forbidden_events_checked") or [])
    if not set(FORBIDDEN_FAKE_ECOMMERCE_EVENTS).issubset(forbidden_checked):
        errors.append("tracking_redirect_qa must check all forbidden fake ecommerce events")
    if payload.get("failure_summary"):
        errors.append("tracking_redirect_qa failure_summary must be empty")


def _validate_tracking_redirect_qa(
    data: dict[str, Any],
    errors: list[str],
    *,
    template_ok: bool,
) -> int:
    qa = data.get("tracking_redirect_qa")
    if not isinstance(qa, dict):
        if not template_ok:
            errors.append("tracking_redirect_qa must be an object")
        return 0

    if qa.get("required") is False and not template_ok:
        errors.append("tracking_redirect_qa.required must remain true")

    gate = str(qa.get("gate") or "").strip()
    evidence_path_raw = str(qa.get("evidence_path") or "").strip()
    evidence_sha = str(qa.get("evidence_sha256") or "").strip()

    if not template_ok:
        if not gate:
            errors.append("tracking_redirect_qa.gate is required")
        elif gate != "GREEN":
            errors.append("tracking_redirect_qa.gate must be GREEN")
        if not evidence_path_raw:
            errors.append("tracking_redirect_qa.evidence_path is required")
        if not evidence_sha:
            errors.append("tracking_redirect_qa.evidence_sha256 is required")

    if evidence_sha and not SHA256_RE.fullmatch(evidence_sha):
        errors.append("tracking_redirect_qa.evidence_sha256 must be lowercase 64-char SHA-256 hex")

    if not evidence_path_raw:
        return 0

    evidence_path = _project_path(evidence_path_raw)
    if not evidence_path.exists():
        errors.append(f"tracking_redirect_qa.evidence_path does not exist: {evidence_path}")
        return 0
    if not evidence_path.is_file():
        errors.append(f"tracking_redirect_qa.evidence_path is not a file: {evidence_path}")
        return 0

    if evidence_sha and SHA256_RE.fullmatch(evidence_sha):
        actual = _file_sha256(evidence_path)
        if actual != evidence_sha:
            errors.append(
                "tracking_redirect_qa.evidence_sha256 mismatch "
                f"for {evidence_path}: expected {evidence_sha}, actual {actual}"
            )

    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"tracking_redirect_qa evidence must be valid JSON: {exc}")
        return 0
    if not isinstance(payload, dict):
        errors.append("tracking_redirect_qa evidence root must be a JSON object")
        return 0
    _validate_tracking_payload(payload, errors)
    return 1


def validate_mapping(path: Path, *, template_ok: bool = False) -> CreativeMappingResult:
    errors: list[str] = []
    warnings: list[str] = []
    data = _read_json(path)

    if data.get("purpose") != "LINE31 countrywide Meta launch final creative mapping intake template":
        errors.append("purpose must identify LINE31 countrywide Meta creative mapping")

    if not template_ok and not data.get("creative_ready_declaration_received"):
        errors.append("creative_ready_declaration_received must be true for publish readiness")

    policy = str(data.get("internal_kaspi_line31_campaigns_policy") or "")
    if "KEEP_ON" not in policy:
        errors.append("internal_kaspi_line31_campaigns_policy must preserve internal Kaspi campaigns")

    publish = data.get("publish_authority")
    if not isinstance(publish, dict):
        errors.append("publish_authority must be an object")
    else:
        if not publish.get("owner_approval_required"):
            errors.append("publish_authority.owner_approval_required must be true")
        if not template_ok and not publish.get("approved"):
            errors.append("publish_authority.approved must be true for publish readiness")
        if not template_ok and publish.get("approved"):
            approval_phrase_path_raw = str(publish.get("approval_phrase_path") or "").strip()
            approval_evidence_path_raw = str(publish.get("approval_evidence_path") or "").strip()
            approval_evidence_sha = str(publish.get("approval_evidence_sha256") or "").strip()

            if not approval_phrase_path_raw:
                errors.append("publish_authority.approval_phrase_path is required")
            if not approval_evidence_path_raw:
                errors.append("publish_authority.approval_evidence_path is required when approved=true")
            if not approval_evidence_sha:
                errors.append("publish_authority.approval_evidence_sha256 is required when approved=true")
            elif not SHA256_RE.fullmatch(approval_evidence_sha):
                errors.append("publish_authority.approval_evidence_sha256 must be lowercase 64-char SHA-256 hex")

            if approval_phrase_path_raw and approval_evidence_path_raw:
                phrase_path = _project_path(approval_phrase_path_raw)
                evidence_path = _project_path(approval_evidence_path_raw)
                if not phrase_path.exists():
                    errors.append(f"publish_authority.approval_phrase_path does not exist: {phrase_path}")
                if phrase_path.resolve() == evidence_path.resolve():
                    errors.append("publish_authority.approval_evidence_path must be separate from approval_phrase_path")
                if not evidence_path.exists():
                    errors.append(f"publish_authority.approval_evidence_path does not exist: {evidence_path}")
                elif approval_evidence_sha and SHA256_RE.fullmatch(approval_evidence_sha):
                    actual = _file_sha256(evidence_path)
                    if actual != approval_evidence_sha:
                        errors.append(
                            "publish_authority.approval_evidence_sha256 mismatch "
                            f"for {evidence_path}: expected {approval_evidence_sha}, actual {actual}"
                        )
                    if phrase_path.exists():
                        try:
                            phrase = required_owner_approval_phrase(phrase_path)
                        except ValueError as exc:
                            errors.append(str(exc))
                        else:
                            evidence_text = evidence_path.read_text(encoding="utf-8")
                            if phrase not in evidence_text:
                                errors.append(
                                    "publish_authority.approval_evidence_path does not contain exact required owner approval phrase"
                                )

    tracking = data.get("landing_tracking_contract")
    if not isinstance(tracking, dict):
        errors.append("landing_tracking_contract must be an object")
        tracking = {}
    else:
        for field, expected in {
            "utm_source": "meta",
            "utm_medium": "paid_social",
            "utm_campaign": "line31_countrywide",
        }.items():
            if tracking.get(field) != expected:
                errors.append(f"landing_tracking_contract.{field} must be {expected!r}")
        required_fields = tracking.get("required_fields")
        if not isinstance(required_fields, list) or not {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_placement",
        }.issubset(set(required_fields)):
            errors.append("landing_tracking_contract.required_fields missing required UTM fields")

    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty list")
        assets = []

    seen_ids: set[str] = set()
    local_video_hashes_checked = 0
    local_thumbnail_hashes_checked = 0
    remote_assets = 0
    approval_evidence_checked = 0
    tracking_redirect_qa_checked = _validate_tracking_redirect_qa(
        data,
        errors,
        template_ok=template_ok,
    )

    if isinstance(publish, dict) and not template_ok and publish.get("approved"):
        evidence_path_raw = str(publish.get("approval_evidence_path") or "").strip()
        evidence_sha = str(publish.get("approval_evidence_sha256") or "").strip()
        if evidence_path_raw and evidence_sha and SHA256_RE.fullmatch(evidence_sha):
            evidence_path = _project_path(evidence_path_raw)
            if evidence_path.exists():
                approval_evidence_checked = 1

    for index, raw_row in enumerate(assets):
        if not isinstance(raw_row, dict):
            errors.append(f"assets[{index}] must be an object")
            continue
        row: dict[str, Any] = raw_row

        creative_id = _require_text(row, "creative_id", index, errors, template_ok=template_ok)
        if creative_id:
            if creative_id in seen_ids:
                errors.append(f"assets[{index}].creative_id duplicates {creative_id}")
            seen_ids.add(creative_id)

        final_uri = _require_text(row, "final_asset_uri", index, errors, template_ok=template_ok)
        thumbnail_uri = _require_text(row, "thumbnail_path_or_uri", index, errors, template_ok=template_ok)
        video_sha = str(row.get("video_sha256") or "").strip()
        thumbnail_sha = str(row.get("thumbnail_sha256") or "").strip()
        landing_url = _require_text(row, "landing_url", index, errors, template_ok=template_ok)
        kaspi_marketplace_cta_url = ""

        for field in (
            "aspect_ratio",
            "language",
            "primary_cta",
            "utm_content",
            "utm_placement",
            "kaspi_marketplace_cta_url",
        ):
            value = _require_text(row, field, index, errors, template_ok=template_ok)
            if field == "kaspi_marketplace_cta_url":
                kaspi_marketplace_cta_url = value

        _validate_publish_uri_not_placeholder(
            final_uri,
            "final_asset_uri",
            index,
            errors,
            template_ok=template_ok,
        )
        _validate_publish_uri_not_placeholder(
            landing_url,
            "landing_url",
            index,
            errors,
            template_ok=template_ok,
        )
        _validate_publish_uri_not_placeholder(
            kaspi_marketplace_cta_url,
            "kaspi_marketplace_cta_url",
            index,
            errors,
            template_ok=template_ok,
        )
        if thumbnail_uri and _is_remote_uri(thumbnail_uri):
            _validate_publish_uri_not_placeholder(
                thumbnail_uri,
                "thumbnail_path_or_uri",
                index,
                errors,
                template_ok=template_ok,
            )

        duration = row.get("duration_seconds")
        if duration in (None, ""):
            if not template_ok:
                errors.append(f"assets[{index}].duration_seconds is required")
        else:
            try:
                if float(duration) <= 0:
                    errors.append(f"assets[{index}].duration_seconds must be > 0")
            except (TypeError, ValueError):
                errors.append(f"assets[{index}].duration_seconds must be numeric")

        _validate_sha(video_sha, "video_sha256", index, errors, template_ok=template_ok)
        if thumbnail_sha:
            _validate_sha(thumbnail_sha, "thumbnail_sha256", index, errors, template_ok=template_ok)

        local_file_raw = str(row.get("local_file_path") or "").strip()
        if local_file_raw:
            local_file = _project_path(local_file_raw)
            if not local_file.exists():
                errors.append(f"assets[{index}].local_file_path does not exist: {local_file}")
            elif video_sha and SHA256_RE.fullmatch(video_sha):
                actual = _file_sha256(local_file)
                local_video_hashes_checked += 1
                if actual != video_sha:
                    errors.append(
                        f"assets[{index}].video_sha256 mismatch for {local_file}: expected {video_sha}, actual {actual}"
                    )
        elif final_uri and _is_remote_uri(final_uri):
            remote_assets += 1
        elif final_uri and not template_ok:
            errors.append(f"assets[{index}].local_file_path required when final_asset_uri is not remote")

        if thumbnail_uri:
            if _is_remote_uri(thumbnail_uri):
                if not thumbnail_sha:
                    warnings.append(f"assets[{index}].thumbnail_sha256 missing for remote thumbnail")
            else:
                thumb_path = _project_path(thumbnail_uri)
                if not thumb_path.exists():
                    errors.append(f"assets[{index}].thumbnail_path_or_uri does not exist: {thumb_path}")
                elif thumbnail_sha and SHA256_RE.fullmatch(thumbnail_sha):
                    actual = _file_sha256(thumb_path)
                    local_thumbnail_hashes_checked += 1
                    if actual != thumbnail_sha:
                        errors.append(
                            f"assets[{index}].thumbnail_sha256 mismatch for {thumb_path}: expected {thumbnail_sha}, actual {actual}"
                        )
                elif not template_ok:
                    errors.append(f"assets[{index}].thumbnail_sha256 is required for local thumbnail")

        _validate_url_utm(landing_url, index, tracking, row, errors, template_ok=template_ok)

    return CreativeMappingResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        metrics={
            "assets_count": len(assets),
            "local_video_hashes_checked": local_video_hashes_checked,
            "local_thumbnail_hashes_checked": local_thumbnail_hashes_checked,
            "remote_assets": remote_assets,
            "approval_evidence_checked": approval_evidence_checked,
            "tracking_redirect_qa_checked": tracking_redirect_qa_checked,
            "template_ok": template_ok,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument(
        "--template-ok",
        action="store_true",
        help="Validate schema and policy for a pending template without requiring final creative fields.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable result JSON.")
    args = parser.parse_args(argv)

    result = validate_mapping(args.mapping, template_ok=args.template_ok)
    payload = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "metrics": result.metrics,
        "mapping": str(args.mapping),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if result.ok else "FAIL"
        print(f"{status}: LINE31 final creative mapping validation")
        for warning in result.warnings:
            print(f"WARN: {warning}")
        for error in result.errors:
            print(f"ERROR: {error}")
        print(json.dumps(result.metrics, ensure_ascii=False, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
