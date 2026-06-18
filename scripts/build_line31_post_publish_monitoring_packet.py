#!/usr/bin/env python3
"""Build a no-write LINE31 post-publish monitoring packet."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_STATUS = PROJECT_ROOT / "docs/current/LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation"
FACEBOOK_ADS_ROOT = Path("~/Docs/Business_3/Facebook_ads")
ACMEWEAR_WEB_ROOT = Path("~/Docs/acmewear_web_v2")


class PacketError(RuntimeError):
    """Raised when a packet cannot be built."""


def _run_id() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PacketError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PacketError(f"invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PacketError(f"JSON root must be an object: {path}")
    return payload


def _shell(path_or_text: Path | str) -> str:
    text = str(path_or_text)
    return "'" + text.replace("'", "'\\''") + "'"


def _path_exists(path: str | None) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def _status_live_qa_green(status: dict[str, Any]) -> bool:
    live_qa = (status.get("latest_deploy_liveqa_sequence") or {}).get("live_qa")
    if not isinstance(live_qa, dict):
        return False
    payload = live_qa.get("payload")
    return isinstance(payload, dict) and payload.get("gate") == "GREEN"


def _status_route_ready(status: dict[str, Any]) -> bool:
    probe = (status.get("latest_deploy_liveqa_sequence") or {}).get("live_route_probe")
    return isinstance(probe, dict) and probe.get("route_ready_for_postdeploy_qa") is True


def _bridge(status: dict[str, Any]) -> dict[str, Any]:
    bridge = status.get("latest_meta_publish_bridge")
    return bridge if isinstance(bridge, dict) else {}


def _bridge_commands(status: dict[str, Any]) -> dict[str, str]:
    commands = _bridge(status).get("commands")
    if not isinstance(commands, dict):
        return {}
    return {str(key): str(value) for key, value in commands.items()}


def _synthetic_qa_approval_phrase(output_dir: Path) -> str:
    return (
        "I approve LINE31_POST_PUBLISH_SYNTHETIC_TRACKING_QA for the LINE31 countrywide Meta launch, "
        "limited to synthetic live tracking/redirect QA against https://acmewear.pro/line31 and "
        "https://acmewear.pro/go/:color, using website /api/signal test events and local evidence "
        f"capture under {output_dir}. No Meta publish/update, Kaspi/WebUI/API writes, campaign/bid/"
        "budget/state changes, price changes, stock changes, cash/PO/supplier actions, DB/workbook "
        "writes, scheduler/source-pointer changes, owner publication, or internal Kaspi campaign pause "
        "are approved."
    )


def _build_commands(
    *,
    status: dict[str, Any],
    output_dir: Path,
) -> list[dict[str, str]]:
    bridge = _bridge(status)
    commands = _bridge_commands(status)
    owner_mapping = str(bridge.get("owner_approved_mapping") or "")
    synthetic_qa_dir = output_dir / "post_publish_synthetic_tracking_qa"
    today = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d")

    rows = [
        {
            "stage": "pre_owner_approval",
            "safety": "local_no_write",
            "name": "regenerate_bridge_packet",
            "command": "cd ~/Docs/Autonomous_business && python3 scripts/plan_line31_meta_publish_bridge.py --json",
            "expected_evidence": "fresh line31_meta_publish_bridge_* packet",
            "success_gate": "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE",
        },
        {
            "stage": "after_line31_owner_publish_phrase",
            "safety": "local_no_write",
            "name": "record_line31_owner_publish_approval",
            "command": commands.get("record_line31_owner_publish_approval", ""),
            "expected_evidence": str(bridge.get("owner_approval_evidence") or ""),
            "success_gate": "approval evidence exists and SHA is referenced by approved mapping",
        },
        {
            "stage": "after_line31_owner_publish_phrase",
            "safety": "local_no_write",
            "name": "write_owner_approved_mapping",
            "command": commands.get("write_owner_approved_mapping", ""),
            "expected_evidence": owner_mapping,
            "success_gate": "strict LINE31 mapping readiness has no approval blocker",
        },
        {
            "stage": "after_line31_owner_publish_phrase",
            "safety": "local_no_write",
            "name": "validate_owner_approved_mapping",
            "command": commands.get("validate_owner_approved_mapping", ""),
            "expected_evidence": owner_mapping,
            "success_gate": "validate_line31_launch_readiness is GREEN",
        },
        {
            "stage": "after_line31_owner_publish_phrase",
            "safety": "local_no_write_meta_plan_only",
            "name": "green_meta_publish_preflight_no_write",
            "command": commands.get("green_meta_publish_preflight_no_write", ""),
            "expected_evidence": "Facebook_ads/exports/validation/line31_meta_publish_preflight_*/preflight_evidence_lock.json",
            "success_gate": "GREEN preflight creates exact META_API_LIVE_WRITE phrase",
        },
        {
            "stage": "after_exact_meta_api_live_write_phrase",
            "safety": "meta_live_write_exact_approval_required",
            "name": "execute_meta_publish",
            "command": commands.get("execute_meta_publish_after_exact_meta_api_live_write_approval", ""),
            "expected_evidence": "Facebook_ads line31_meta_publish_preflight_* publish results",
            "success_gate": "created campaign/adset/3 ads match locked plan",
        },
        {
            "stage": "immediate_post_publish",
            "safety": "external_readonly",
            "name": "meta_primary_readonly_verification",
            "command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/preflight_meta_api_primary.py --live-readonly --json"
            ),
            "expected_evidence": "Facebook_ads/exports/validation/meta_api_primary_preflight_*",
            "success_gate": "Meta account is readable and write gate still requires exact approval",
        },
        {
            "stage": "immediate_post_publish",
            "safety": "external_readonly",
            "name": "meta_launch_identity_readonly_verification",
            "command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/discover_meta_launch_identity.py --live-readonly --json"
            ),
            "expected_evidence": "Facebook_ads/exports/validation/meta_launch_identity_discovery_*",
            "success_gate": "page/pixel identity remains evidence-backed",
        },
        {
            "stage": "immediate_post_publish",
            "safety": "website_synthetic_write_exact_approval_required",
            "name": "post_publish_synthetic_tracking_qa",
            "command": (
                "cd ~/Docs/acmewear_web_v2 && "
                "node scripts/probe_line31_tracking_qa.mjs --base-url https://acmewear.pro "
                "--allow-live-signal-writes "
                f"--evidence-dir {_shell(synthetic_qa_dir)}"
            ),
            "expected_evidence": str(synthetic_qa_dir / "line31_tracking_redirect_qa.json"),
            "success_gate": "GREEN live_postdeploy QA with stored PageView/ViewContent/ColorSelect/KaspiClick/HighIntentKaspiClick",
        },
        {
            "stage": "same_day_monitoring",
            "safety": "external_readonly_no_telegram",
            "name": "meta_only_ads_monitoring_today",
            "command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                f"PYTHONPATH=. python3 scripts/run_ads_monitoring.py --date {today} "
                "--skip-kaspi --skip-order-truth --no-telegram"
            ),
            "expected_evidence": "Business_3/Facebook_ads data/exports for today's Meta monitoring",
            "success_gate": "Meta traffic truth rows exist; no Telegram send",
        },
        {
            "stage": "same_day_monitoring",
            "safety": "external_readonly",
            "name": "acmewear_live_orders_readonly_today",
            "command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                f"PYTHONPATH=. python3 scripts/sync_live_orders_acmewear.py --date {today}"
            ),
            "expected_evidence": "ACMEWEAR live order sync evidence and LINE31 mapping candidates",
            "success_gate": "Kaspi order truth captured read-only; attribution remains directional",
        },
        {
            "stage": "same_day_monitoring",
            "safety": "local_db_refresh_from_captured_sources",
            "name": "dashboard_local_refresh_today",
            "command": (
                "cd ~/Docs/Business_3/Facebook_ads && "
                "PYTHONPATH=. python3 scripts/sync_dashboard_local.py --period today"
            ),
            "expected_evidence": "local dashboard SQLite/HTML snapshot",
            "success_gate": "dashboard separates Meta traffic, website intent, redirects, and LINE31 order truth",
        },
    ]
    return rows


def _write_commands_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "stage",
                "safety",
                "name",
                "command",
                "expected_evidence",
                "success_gate",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_packet(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status.expanduser().resolve()
    status = _load_json(status_path)
    output_root = args.output_root.expanduser().resolve()
    output_dir = output_root / f"line31_post_publish_monitoring_packet_{args.run_id or _run_id()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    bridge = _bridge(status)
    mapping_path = str(status.get("mapping_path") or "")
    synthetic_phrase = _synthetic_qa_approval_phrase(output_dir)
    commands = _build_commands(status=status, output_dir=output_dir)
    commands_path = output_dir / "commands.tsv"
    _write_commands_tsv(commands_path, commands)

    checks = {
        "current_status_exists": status_path.is_file(),
        "pending_mapping_exists": _path_exists(mapping_path),
        "deploy_liveqa_sequence_green": (
            (status.get("latest_deploy_liveqa_sequence") or {}).get("gate")
            == "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE"
        ),
        "live_tracking_qa_green": _status_live_qa_green(status),
        "live_route_ready": _status_route_ready(status),
        "meta_publish_bridge_green": bridge.get("gate")
        == "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE",
        "bridge_owner_paste_file_declared": bool(bridge.get("owner_paste_file")),
        "bridge_later_meta_live_write_file_declared": bool(
            bridge.get("meta_api_live_write_approval_file")
        ),
        "latest_meta_preflight_blocked_only_by_approval": sorted(
            (status.get("latest_meta_line31_publish_preflight") or {}).get("errors") or []
        )
        == sorted(
            [
                "publish_authority.approved must be true",
                "publish_authority.approval_evidence_path is required",
            ]
        ),
    }
    gate = (
        "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
        if all(checks.values())
        else "YELLOW_LINE31_POST_PUBLISH_MONITORING_PLAN_REVIEW_REQUIRED_NO_WRITE"
    )

    synthetic_phrase_path = output_dir / "NEXT_POST_PUBLISH_SYNTHETIC_TRACKING_QA_APPROVAL_PHRASE.txt"
    synthetic_phrase_path.write_text(synthetic_phrase + "\n", encoding="utf-8")

    payload = {
        "gate": gate,
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "status_path": str(status_path),
        "mapping_path": mapping_path,
        "latest_meta_publish_bridge": bridge,
        "checks": checks,
        "commands_tsv": str(commands_path),
        "commands": commands,
        "future_synthetic_tracking_qa_approval_phrase_path": str(
            synthetic_phrase_path
        ),
        "truth_separation_contract": [
            "Meta traffic truth: impressions, clicks, LPV, spend, and ad delivery only.",
            "Website truth: PageView, ViewContent, ColorSelect, QualifiedVisit, KaspiClick, and HighIntentKaspiClick.",
            "Redirect truth: /go/:color 302 destination, UTM preservation, landing_color, and landing_source.",
            "Kaspi order truth: real order rows only; no purchase is inferred from Meta or website clicks.",
            "Attribution truth: directional until order matching proves stronger evidence.",
        ],
        "decision_gates": {
            "first_hour": "campaign/adset/3 ads active, no delivery errors, landing route 200, redirects 302, no fake ecommerce accepted",
            "same_day": "Meta traffic, website intent, redirect, and order truth refresh without mixing channels",
            "next_morning": "dashboard has spend, LPV, website intent, redirect, and LINE31 order rows separated by source",
        },
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "output_dir": str(output_dir),
    }

    manifest_path = output_dir / "post_publish_monitoring_manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "closeout.md").write_text(_render_closeout(payload), encoding="utf-8")
    return payload


def _render_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Post-Publish Monitoring Packet",
        "",
        f"Gate: {payload['gate']}",
        "",
        "## Boundary",
        "",
        "- External write attempted: `False`",
        "- Meta write attempted: `False`",
        "- This packet writes local planning/evidence files only.",
        "",
        "## Truth Separation",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["truth_separation_contract"])
    lines.extend(
        [
            "",
            "## Readiness Checks",
            "",
        ]
    )
    lines.extend(f"- `{key}`: `{value}`" for key, value in payload["checks"].items())
    lines.extend(
        [
            "",
            "## Future Approval Phrase For Synthetic Website QA",
            "",
            f"`{payload['future_synthetic_tracking_qa_approval_phrase_path']}`",
            "",
            "## Commands",
            "",
            f"Commands TSV: `{payload['commands_tsv']}`",
            "",
        ]
    )
    for row in payload["commands"]:
        lines.extend(
            [
                f"### {row['stage']} / {row['name']}",
                "",
                f"- Safety: `{row['safety']}`",
                f"- Expected evidence: `{row['expected_evidence']}`",
                f"- Success gate: `{row['success_gate']}`",
                "",
                "```bash",
                row["command"],
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_packet(args)
    except PacketError as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
