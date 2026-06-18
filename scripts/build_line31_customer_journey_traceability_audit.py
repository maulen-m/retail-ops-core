#!/usr/bin/env python3
"""Audit the LINE31 Meta CTA -> landing -> Kaspi offer traceability chain."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_STATUS = PROJECT_ROOT / "docs/current/LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation"

REQUIRED_UTM = {
    "utm_source": "meta",
    "utm_medium": "paid_social",
    "utm_campaign": "line31_countrywide",
}
REQUIRED_TRACKED_PARAMS = [
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_placement",
]
REQUIRED_BROWSER_EVENTS = [
    "PageView",
    "ViewContent",
    "ColorSelect",
    "QualifiedVisit",
    "KaspiClick",
    "HighIntentKaspiClick",
]
REQUIRED_REDIRECT_SLUGS = [
    "starry-black",
    "ivory-white-starry-black",
    "misty-blue",
    "cardamom-green-olive-green",
    "espresso",
]
EXPECTED_PREFLIGHT_APPROVAL_ERRORS = [
    "publish_authority.approved must be true",
    "publish_authority.approval_evidence_path is required",
]
EXPECTED_CURRENT_META_GATE_PREFIX = "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED"
EXPECTED_LIVE_LABEL_GATE = "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"


class AuditError(RuntimeError):
    """Raised when required audit input is missing or malformed."""


def _run_id() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuditError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AuditError(f"invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditError(f"JSON root must be an object: {path}")
    return payload


def _required_existing_path(value: str | None, label: str) -> Path:
    if not value:
        raise AuditError(f"{label} is missing")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise AuditError(f"{label} does not exist: {path}")
    return path


def _status_manifest_path(status: dict[str, Any], section: str, label: str) -> Path:
    payload = status.get(section)
    if not isinstance(payload, dict):
        raise AuditError(f"current status missing {section}")
    return _required_existing_path(str(payload.get("manifest") or ""), label)


def _check(rows: list[dict[str, str]], name: str, ok: bool, detail: str) -> None:
    rows.append(
        {
            "check": name,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
        }
    )


def _single_query_value(parsed: dict[str, list[str]], key: str) -> str:
    values = parsed.get(key) or []
    return values[0] if values else ""


def _audit_mapping(
    *,
    rows: list[dict[str, str]],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    assets = mapping.get("assets")
    assets_ok = isinstance(assets, list) and len(assets) == 3
    _check(rows, "mapping_has_three_creatives", assets_ok, f"assets={len(assets) if isinstance(assets, list) else 'missing'}")
    if not isinstance(assets, list):
        assets = []

    creative_ids = [str(item.get("creative_id") or "") for item in assets if isinstance(item, dict)]
    _check(
        rows,
        "mapping_creative_ids_unique",
        len(creative_ids) == len(set(creative_ids)) == 3,
        ",".join(creative_ids),
    )

    per_asset: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            _check(rows, f"asset_{index}_is_object", False, "asset row is not object")
            continue
        creative_id = str(asset.get("creative_id") or "")
        landing = str(asset.get("landing_url") or "")
        kaspi_cta = str(asset.get("kaspi_marketplace_cta_url") or "")
        parsed = urlparse(landing)
        query = parse_qs(parsed.query)
        landing_ok = (
            parsed.scheme == "https"
            and parsed.netloc == "acmewear.pro"
            and parsed.path == "/line31"
        )
        _check(rows, f"asset_{index}_landing_route", landing_ok, landing)
        for key, expected in REQUIRED_UTM.items():
            actual = _single_query_value(query, key)
            _check(rows, f"asset_{index}_{key}", actual == expected, f"{actual}")
        _check(
            rows,
            f"asset_{index}_utm_content_matches_creative_id",
            _single_query_value(query, "utm_content") == creative_id,
            f"utm_content={_single_query_value(query, 'utm_content')} creative_id={creative_id}",
        )
        _check(
            rows,
            f"asset_{index}_utm_placement_present",
            bool(_single_query_value(query, "utm_placement")),
            _single_query_value(query, "utm_placement"),
        )
        _check(
            rows,
            f"asset_{index}_cta_uses_redirect_route",
            kaspi_cta.startswith("https://acmewear.pro/go/"),
            kaspi_cta,
        )
        per_asset.append(
            {
                "creative_id": creative_id,
                "landing_url": landing,
                "kaspi_marketplace_cta_url": kaspi_cta,
            }
        )

    tracking = mapping.get("tracking_redirect_qa")
    tracking_gate = tracking.get("gate") if isinstance(tracking, dict) else None
    _check(rows, "mapping_tracking_qa_green", tracking_gate == "GREEN", str(tracking_gate))
    return {"assets": per_asset}


def _audit_live_qa(rows: list[dict[str, str]], qa: dict[str, Any]) -> dict[str, Any]:
    _check(rows, "live_qa_gate_green", qa.get("gate") == "GREEN", str(qa.get("gate")))
    _check(rows, "live_qa_scope_postdeploy", qa.get("qa_scope") == "live_postdeploy", str(qa.get("qa_scope")))
    _check(rows, "live_qa_target_acmewear", qa.get("target_base_url") == "https://acmewear.pro", str(qa.get("target_base_url")))

    landing = qa.get("landing")
    landing = landing if isinstance(landing, dict) else {}
    _check(rows, "landing_path_line31", landing.get("path") == "/line31", str(landing.get("path")))
    _check(rows, "landing_status_200", landing.get("status") == 200, str(landing.get("status")))
    tracked = landing.get("tracked_params_in_runtime_config")
    tracked = tracked if isinstance(tracked, list) else []
    for key in REQUIRED_TRACKED_PARAMS:
        _check(rows, f"landing_tracks_{key}", key in tracked, ",".join(str(item) for item in tracked))
    _check(rows, "landing_missing_expected_utm_empty", landing.get("missing_expected_utm_params") == [], str(landing.get("missing_expected_utm_params")))
    _check(rows, "landing_primary_cta_starry_black", landing.get("primary_cta_route") == "/go/starry-black", str(landing.get("primary_cta_route")))
    _check(rows, "landing_fallback_wib", landing.get("chooser_fallback_cta_route") == "/go/ivory-white-starry-black", str(landing.get("chooser_fallback_cta_route")))
    _check(rows, "landing_has_no_raw_kaspi_href", landing.get("raw_kaspi_href_in_landing_html") is False, str(landing.get("raw_kaspi_href_in_landing_html")))

    event_rows = qa.get("browser_events")
    event_rows = event_rows if isinstance(event_rows, list) else []
    event_map = {str(row.get("event_name") or ""): row for row in event_rows if isinstance(row, dict)}
    for event in REQUIRED_BROWSER_EVENTS:
        row = event_map.get(event, {})
        _check(
            rows,
            f"browser_event_{event}_stored",
            row.get("api_status") == 204 and row.get("stored") is True,
            json.dumps(row, ensure_ascii=False, sort_keys=True),
        )

    redirect_rows = qa.get("redirect_routes")
    redirect_rows = redirect_rows if isinstance(redirect_rows, list) else []
    redirect_map = {str(row.get("slug") or ""): row for row in redirect_rows if isinstance(row, dict)}
    for slug in REQUIRED_REDIRECT_SLUGS:
        row = redirect_map.get(slug, {})
        _check(rows, f"redirect_{slug}_present", bool(row), json.dumps(row, ensure_ascii=False, sort_keys=True))
        if row:
            _check(rows, f"redirect_{slug}_302", row.get("http_status") == 302, str(row.get("http_status")))
            _check(rows, f"redirect_{slug}_registry_match", row.get("destination_route_matches_registry") is True, str(row.get("destination_route_matches_registry")))
            _check(rows, f"redirect_{slug}_utm_preserved", row.get("tracked_utm_keys_missing_or_wrong") == [], str(row.get("tracked_utm_keys_missing_or_wrong")))
            _check(rows, f"redirect_{slug}_landing_color_preserved", row.get("landing_color_preserved") is True, str(row.get("landing_color_preserved")))
            _check(rows, f"redirect_{slug}_landing_source_preserved", row.get("landing_source_preserved") is True, str(row.get("landing_source_preserved")))

    fail_closed = qa.get("fail_closed_checks")
    fail_closed = fail_closed if isinstance(fail_closed, dict) else {}
    _check(rows, "unknown_color_404", fail_closed.get("unknown_color_status") == 404, str(fail_closed.get("unknown_color_status")))
    _check(rows, "spoofed_redirect_400", fail_closed.get("browser_spoofed_kaspi_redirect_status") == 400, str(fail_closed.get("browser_spoofed_kaspi_redirect_status")))
    _check(rows, "fake_purchase_400", fail_closed.get("fake_purchase_status") == 400, str(fail_closed.get("fake_purchase_status")))

    no_fake = qa.get("no_fake_ecommerce_events")
    no_fake = no_fake if isinstance(no_fake, dict) else {}
    _check(rows, "fake_purchase_rejected", no_fake.get("fake_purchase_rejected") is True, str(no_fake.get("fake_purchase_rejected")))
    forbidden = no_fake.get("forbidden_events_checked")
    forbidden = forbidden if isinstance(forbidden, list) else []
    for event in ["Purchase", "AddToCart", "InitiateCheckout", "AddPaymentInfo"]:
        _check(rows, f"forbidden_event_{event}_checked", event in forbidden, ",".join(str(item) for item in forbidden))
    return {
        "redirect_slugs": sorted(redirect_map),
        "browser_events": sorted(event_map),
    }


def _audit_preflight(rows: list[dict[str, str]], preflight: dict[str, Any]) -> None:
    shape = preflight.get("launch_shape")
    shape = shape if isinstance(shape, dict) else {}
    _check(rows, "meta_preflight_three_ads", shape.get("ad_count") == 3, str(shape.get("ad_count")))
    _check(rows, "meta_preflight_budget_15000", shape.get("daily_budget_kzt") == 15000, str(shape.get("daily_budget_kzt")))
    _check(rows, "meta_preflight_hard_cap_20000", shape.get("hard_cap_kzt") == 20000, str(shape.get("hard_cap_kzt")))
    _check(rows, "meta_preflight_landing_url_line31", shape.get("landing_url") == "https://acmewear.pro/line31", str(shape.get("landing_url")))
    _check(rows, "meta_preflight_active_publish_status", shape.get("publish_status") == "ACTIVE", str(shape.get("publish_status")))
    errors = preflight.get("errors")
    errors = errors if isinstance(errors, list) else []
    write_gate = preflight.get("write_gate")
    write_gate = write_gate if isinstance(write_gate, dict) else {}
    owner_phrase_gated = (
        preflight.get("gate") == "GREEN_META_LINE31_PUBLISH_PREFLIGHT_READY_NO_WRITE"
        and errors == []
        and write_gate.get("ok") is False
        and "owner approval text is empty" in [
            str(item) for item in (write_gate.get("reasons") or [])
        ]
    )
    old_approval_shape = sorted(str(item) for item in errors) == sorted(
        EXPECTED_PREFLIGHT_APPROVAL_ERRORS
    )
    _check(
        rows,
        "meta_preflight_only_approval_blocked",
        old_approval_shape or owner_phrase_gated,
        (
            "legacy approval errors: "
            + "; ".join(str(item) for item in errors)
            if errors
            else f"gate={preflight.get('gate')} write_gate={json.dumps(write_gate, ensure_ascii=False, sort_keys=True)}"
        ),
    )


def _audit_current_meta_snapshot(rows: list[dict[str, str]], snapshot: dict[str, Any]) -> None:
    gate = str(snapshot.get("gate") or "")
    summary = snapshot.get("current_state_summary")
    summary = summary if isinstance(summary, dict) else {}
    retained = snapshot.get("retained_ui_only_gaps")
    retained = retained if isinstance(retained, list) else []
    _check(rows, "meta_current_snapshot_gate_green", gate.startswith(EXPECTED_CURRENT_META_GATE_PREFIX), gate)
    _check(rows, "meta_current_snapshot_no_failed_checks", snapshot.get("checks_failed") == 0, str(snapshot.get("checks_failed")))
    _check(rows, "meta_current_campaign_paused_prestart", summary.get("campaign_status") == "PAUSED", str(summary.get("campaign_status")))
    _check(rows, "meta_current_adset_paused_prestart", summary.get("adset_status") == "PAUSED", str(summary.get("adset_status")))
    _check(rows, "meta_current_adset_budget_3093", str(summary.get("adset_daily_budget") or "") == "3093", str(summary.get("adset_daily_budget") or ""))
    _check(rows, "meta_current_three_ads_exist", summary.get("ads_by_adset_count") == 3, str(summary.get("ads_by_adset_count")))
    _check(rows, "meta_current_copy_gift_bag", summary.get("customer_visible_message") == "Женский комплект AcmeWear 3в1. Закажи на Каспи и получи сумку в подарок!", str(summary.get("customer_visible_message")))
    _check(rows, "meta_current_cta_order_now", summary.get("customer_visible_cta") == "ORDER_NOW", str(summary.get("customer_visible_cta")))
    _check(rows, "meta_current_landing_line31", summary.get("landing_url") == "https://acmewear.pro/line31", str(summary.get("landing_url")))
    _check(
        rows,
        "meta_current_multi_advertiser_ui_evidence",
        "multi_advertiser_ads_off_not_verified_by_graph_api" not in retained,
        ",".join(str(item) for item in retained),
    )


def _audit_live_customer_label(rows: list[dict[str, str]], probe: dict[str, Any]) -> None:
    summary = probe.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    _check(rows, "live_label_probe_green", probe.get("gate") == EXPECTED_LIVE_LABEL_GATE, str(probe.get("gate")))
    _check(rows, "live_label_required_label_present", summary.get("contains_required_customer_label") is True, str(summary.get("contains_required_customer_label")))
    _check(rows, "live_label_forbidden_line31_absent", summary.get("contains_forbidden_customer_label") is False, str(summary.get("contains_forbidden_customer_label")))
    _check(rows, "live_label_raw_kaspi_href_absent", summary.get("contains_raw_kaspi_product_href") is False, str(summary.get("contains_raw_kaspi_product_href")))
    _check(rows, "live_label_no_failed_checks", probe.get("checks_failed") == 0, str(probe.get("checks_failed")))


def _audit_manifest(rows: list[dict[str, str]], manifest: dict[str, Any]) -> None:
    shape = manifest.get("campaign_shape")
    shape = shape if isinstance(shape, dict) else {}
    _check(rows, "asset_manifest_campaign_three_ads", shape.get("ad_count") == 3, str(shape.get("ad_count")))
    _check(rows, "asset_manifest_budget_15000", shape.get("daily_budget_kzt") == 15000, str(shape.get("daily_budget_kzt")))
    _check(rows, "asset_manifest_hard_cap_20000", shape.get("hard_cap_kzt") == 20000, str(shape.get("hard_cap_kzt")))
    _check(rows, "asset_manifest_landing_url_line31", shape.get("landing_url") == "https://acmewear.pro/line31", str(shape.get("landing_url")))
    priority = manifest.get("landing_cta_priority")
    priority = priority if isinstance(priority, list) else []
    expected = ["starry_black", "wib_mixed_color_set", "blue_misty", "olive_green"]
    _check(rows, "cta_priority_core_order", priority[:4] == expected, " -> ".join(str(item) for item in priority))
    _check(rows, "cta_priority_espresso_last", bool(priority) and priority[-1] == "espresso_last", " -> ".join(str(item) for item in priority))


def _audit_bridge_and_monitoring(
    rows: list[dict[str, str]],
    bridge: dict[str, Any],
    monitoring: dict[str, Any],
) -> None:
    _check(rows, "publish_bridge_green", bridge.get("gate") == "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE", str(bridge.get("gate")))
    _check(rows, "publish_bridge_no_external_write", bridge.get("external_write_attempted") is False, str(bridge.get("external_write_attempted")))
    _check(rows, "publish_bridge_no_meta_write", bridge.get("meta_write_attempted") is False, str(bridge.get("meta_write_attempted")))
    _check(rows, "publish_bridge_has_line31_owner_paste_file", bool(bridge.get("owner_paste_file")), str(bridge.get("owner_paste_file") or ""))
    _check(rows, "publish_bridge_has_meta_live_write_paste_file", bool(bridge.get("meta_api_live_write_approval_file")), str(bridge.get("meta_api_live_write_approval_file") or ""))

    _check(rows, "monitoring_packet_green", monitoring.get("gate") == "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE", str(monitoring.get("gate")))
    _check(rows, "monitoring_packet_no_external_write", monitoring.get("external_write_attempted") is False, str(monitoring.get("external_write_attempted")))
    _check(rows, "monitoring_packet_no_meta_write", monitoring.get("meta_write_attempted") is False, str(monitoring.get("meta_write_attempted")))
    contract = monitoring.get("truth_separation_contract")
    contract = contract if isinstance(contract, list) else []
    joined = " ".join(str(item) for item in contract)
    for phrase in ["Meta traffic truth", "Website truth", "Redirect truth", "Kaspi order truth", "Attribution truth"]:
        _check(rows, f"monitoring_contract_has_{phrase.split()[0].lower()}", phrase in joined, joined)


def _write_checks(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "detail"])
        writer.writeheader()
        writer.writerows(rows)


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status.expanduser().resolve()
    status = _load_json(status_path)
    mapping_path = _required_existing_path(str(status.get("mapping_path") or ""), "mapping")
    mapping = _load_json(mapping_path)
    final_manifest_path = _status_manifest_path(status, "latest_final_creative_assets", "final creative asset manifest")
    final_manifest = _load_json(final_manifest_path)
    preflight_path = _status_manifest_path(status, "latest_meta_line31_publish_preflight", "Meta publish preflight manifest")
    preflight = _load_json(preflight_path)
    current_meta_path = _status_manifest_path(status, "latest_meta_current_readonly_snapshot", "current Meta read-only snapshot manifest")
    current_meta = _load_json(current_meta_path)
    live_label_path = _status_manifest_path(status, "latest_line31_live_customer_label_probe", "live customer label probe manifest")
    live_label = _load_json(live_label_path)
    monitoring_path = _status_manifest_path(status, "latest_post_publish_monitoring_packet", "post-publish monitoring manifest")
    monitoring = _load_json(monitoring_path)
    bridge_path = _status_manifest_path(status, "latest_meta_publish_bridge", "Meta publish bridge manifest")
    bridge = _load_json(bridge_path)

    tracking = mapping.get("tracking_redirect_qa")
    if not isinstance(tracking, dict):
        raise AuditError("mapping missing tracking_redirect_qa object")
    live_qa_path = _required_existing_path(str(tracking.get("evidence_path") or ""), "live tracking QA evidence")
    live_qa = _load_json(live_qa_path)

    rows: list[dict[str, str]] = []
    mapping_summary = _audit_mapping(rows=rows, mapping=mapping)
    live_summary = _audit_live_qa(rows, live_qa)
    _audit_preflight(rows, preflight)
    _audit_current_meta_snapshot(rows, current_meta)
    _audit_live_customer_label(rows, live_label)
    _audit_manifest(rows, final_manifest)
    _audit_bridge_and_monitoring(rows, bridge, monitoring)

    failed = [row for row in rows if row["status"] != "PASS"]
    gate = (
        "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
        if not failed
        else "YELLOW_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_REVIEW_REQUIRED_NO_WRITE"
    )
    output_dir = args.output_root.expanduser().resolve() / f"line31_customer_journey_traceability_audit_{args.run_id or _run_id()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    checks_path = output_dir / "checks.csv"
    _write_checks(checks_path, rows)

    payload = {
        "gate": gate,
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "status_path": str(status_path),
        "mapping_path": str(mapping_path),
        "final_creative_manifest": str(final_manifest_path),
        "live_tracking_qa": str(live_qa_path),
        "meta_publish_preflight_manifest": str(preflight_path),
        "meta_current_readonly_snapshot_manifest": str(current_meta_path),
        "live_customer_label_probe_manifest": str(live_label_path),
        "meta_publish_bridge_manifest": str(bridge_path),
        "post_publish_monitoring_manifest": str(monitoring_path),
        "checks_csv": str(checks_path),
        "checks_total": len(rows),
        "checks_failed": len(failed),
        "failed_checks": failed,
        "mapping_summary": mapping_summary,
        "live_qa_summary": live_summary,
        "journey_chain": [
            "Meta ad CTA uses final 3 creative mapping and UTM-tagged https://acmewear.pro/line31 landing URLs.",
            "Live /line31 route serves a LINE31 page with no raw Kaspi product hrefs in landing HTML.",
            "Landing CTA uses /go/:color routes, preserving UTM, landing_color, and landing_source into Kaspi redirects.",
            "Website events store PageView, ViewContent, ColorSelect, QualifiedVisit, KaspiClick, and HighIntentKaspiClick.",
            "Kaspi order truth remains separate from website click truth; attribution stays directional until order matching proves it.",
        ],
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "output_dir": str(output_dir),
    }
    manifest_path = output_dir / "traceability_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "closeout.md").write_text(_render_closeout(payload), encoding="utf-8")
    return payload


def _render_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Customer Journey Traceability Audit",
        "",
        f"Gate: {payload['gate']}",
        "",
        "## Boundary",
        "",
        "- External write attempted: `False`",
        "- Meta write attempted: `False`",
        "- This audit reads existing local evidence and writes local audit files only.",
        "",
        "## Journey Chain",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["journey_chain"])
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Mapping: `{payload['mapping_path']}`",
            f"- Final creative manifest: `{payload['final_creative_manifest']}`",
            f"- Live tracking QA: `{payload['live_tracking_qa']}`",
            f"- Meta publish preflight: `{payload['meta_publish_preflight_manifest']}`",
            f"- Current Meta read-only snapshot: `{payload['meta_current_readonly_snapshot_manifest']}`",
            f"- Live customer label probe: `{payload['live_customer_label_probe_manifest']}`",
            f"- Meta publish bridge: `{payload['meta_publish_bridge_manifest']}`",
            f"- Post-publish monitoring: `{payload['post_publish_monitoring_manifest']}`",
            f"- Checks CSV: `{payload['checks_csv']}`",
            "",
            "## Result",
            "",
            f"- Checks total: `{payload['checks_total']}`",
            f"- Checks failed: `{payload['checks_failed']}`",
            "",
        ]
    )
    if payload["failed_checks"]:
        lines.append("## Failed Checks")
        lines.append("")
        for row in payload["failed_checks"]:
            lines.append(f"- `{row['check']}`: {row['detail']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_audit(args)
    except AuditError as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
