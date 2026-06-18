#!/usr/bin/env python3
"""Build the LINE31 final pre-start owner/expert decision packet.

This packet is intentionally no-write externally. It consolidates the current
Meta readback, live landing/redirect proof, activation preflight, and monitoring
plan into one operator-facing decision surface.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_STATUS_PATH = PROJECT_ROOT / "docs" / "current" / "LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_ORACLE_PACK = Path(
    "~/Docs/Oracle/oracle_packs/Instagram_funnel_packs/"
    "line31_countrywide_three_day_meta_resume_truth_oracle_pack_v2_UNDER20_FLAT__20260530_GMT5"
)
EXPECTED_STATUS = "YELLOW_META_CURRENT_SETUP_PAUSED_PRESTART_REVIEW_REQUIRED"
EXPECTED_OWNER_STATUS = "YELLOW_META_SETUP_READY_PAUSED__PENDING_FINAL_START_DECISION"
EXPECTED_META_GATE = "GREEN_META_LINE31_CURRENT_API_STATE_VERIFIED_NO_WRITE"
EXPECTED_ACTIVATION_GATE = "GREEN_LINE31_META_ACTIVATE_ONLY_PREFLIGHT_READY_NO_WRITE"
EXPECTED_TRACEABILITY_GATE = "GREEN_LINE31_CUSTOMER_JOURNEY_TRACEABILITY_READY_PENDING_APPROVAL_NO_WRITE"
EXPECTED_LABEL_GATE = "GREEN_LINE31_LIVE_CUSTOMER_LABEL_VERIFIED_NO_WRITE"
EXPECTED_MONITORING_GATE = "GREEN_LINE31_POST_PUBLISH_MONITORING_PLAN_READY_NO_WRITE"
EXPECTED_AD_IDS = {
    "120245492808400641",
    "120245488532270641",
    "120245492808390641",
}
EXPECTED_COPY = "Женский комплект AcmeWear 3в1. Закажи на Каспи и получи сумку в подарок!"


class DecisionPacketError(RuntimeError):
    """Raised when packet input is unusable."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DecisionPacketError(f"missing JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DecisionPacketError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionPacketError(f"JSON root must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _path(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value)).expanduser()


def _read_text_if_file(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _exists(value: object) -> bool:
    path = _path(value)
    return bool(path and path.exists())


def _add_check(
    rows: list[dict[str, str]],
    *,
    check: str,
    ok: bool,
    evidence: str,
    detail: str,
) -> None:
    rows.append(
        {
            "check": check,
            "status": "PASS" if ok else "FAIL",
            "evidence": evidence,
            "detail": detail,
        }
    )


def _section(status: dict[str, Any], key: str) -> dict[str, Any]:
    value = status.get(key)
    return value if isinstance(value, dict) else {}


def _all_multi_advertiser_off(summary: dict[str, Any]) -> bool:
    statuses = summary.get("multi_advertiser_ads_enroll_statuses")
    if not isinstance(statuses, dict) or set(statuses) != EXPECTED_AD_IDS:
        return False
    return all(str(value) == "OPT_OUT" for value in statuses.values())


def _current_meta_checks(
    *,
    rows: list[dict[str, str]],
    current_meta: dict[str, Any],
) -> dict[str, Any]:
    summary = current_meta.get("current_state_summary")
    summary = summary if isinstance(summary, dict) else {}
    manifest = str(current_meta.get("manifest") or "")
    gate = str(current_meta.get("gate") or "")
    ad_ids = {str(item) for item in summary.get("ad_ids") or []}
    _add_check(
        rows,
        check="current_meta_snapshot_green",
        ok=gate == EXPECTED_META_GATE,
        evidence=manifest,
        detail=gate,
    )
    _add_check(
        rows,
        check="current_meta_snapshot_zero_failed_review",
        ok=current_meta.get("checks_failed") == 0 and current_meta.get("checks_review") == 0,
        evidence=manifest,
        detail=f"failed={current_meta.get('checks_failed')} review={current_meta.get('checks_review')}",
    )
    _add_check(
        rows,
        check="current_meta_snapshot_manifest_exists",
        ok=_exists(manifest),
        evidence=manifest,
        detail="manifest path must exist locally",
    )
    _add_check(
        rows,
        check="campaign_adset_paused",
        ok=summary.get("campaign_status") == "PAUSED" and summary.get("adset_status") == "PAUSED",
        evidence=manifest,
        detail=f"campaign={summary.get('campaign_status')} adset={summary.get('adset_status')}",
    )
    _add_check(
        rows,
        check="exact_three_ads_source_verified",
        ok=summary.get("ads_by_adset_count") == 3 and ad_ids == EXPECTED_AD_IDS,
        evidence=manifest,
        detail=f"count={summary.get('ads_by_adset_count')} ids={','.join(sorted(ad_ids))}",
    )
    _add_check(
        rows,
        check="budget_minor_units_3093",
        ok=str(summary.get("adset_daily_budget") or "") == "3093",
        evidence=manifest,
        detail=f"daily_budget={summary.get('adset_daily_budget')}",
    )
    _add_check(
        rows,
        check="customer_visible_copy_cta_title_landing",
        ok=(
            summary.get("customer_visible_message") == EXPECTED_COPY
            and summary.get("customer_visible_cta") == "ORDER_NOW"
            and summary.get("customer_visible_title") == "AcmeWear 3в1"
            and summary.get("landing_url") == "https://acmewear.pro/line31"
        ),
        evidence=manifest,
        detail=(
            f"title={summary.get('customer_visible_title')} "
            f"cta={summary.get('customer_visible_cta')} "
            f"landing={summary.get('landing_url')}"
        ),
    )
    _add_check(
        rows,
        check="multi_advertiser_ads_opt_out_all_three",
        ok=_all_multi_advertiser_off(summary),
        evidence=manifest,
        detail=json.dumps(summary.get("multi_advertiser_ads_enroll_statuses", {}), ensure_ascii=False, sort_keys=True),
    )
    _add_check(
        rows,
        check="no_retained_meta_ui_gaps",
        ok=current_meta.get("retained_ui_only_gaps") == [],
        evidence=manifest,
        detail=json.dumps(current_meta.get("retained_ui_only_gaps", []), ensure_ascii=False),
    )
    return summary


def build_decision_payload(
    *,
    status: dict[str, Any],
    status_path: Path,
    oracle_pack: Path,
    generated_at: str,
) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    current_meta = _section(status, "latest_meta_current_readonly_snapshot")
    activation = _section(status, "latest_meta_current_activation_preflight")
    traceability = _section(status, "latest_customer_journey_traceability_audit")
    label = _section(status, "latest_line31_live_customer_label_probe")
    monitoring = _section(status, "latest_post_publish_monitoring_packet")
    summary = _current_meta_checks(rows=rows, current_meta=current_meta)

    _add_check(
        rows,
        check="current_status_is_paused_prestart",
        ok=status.get("status") == EXPECTED_STATUS and status.get("owner_facing_publish_status") == EXPECTED_OWNER_STATUS,
        evidence=str(status_path),
        detail=f"status={status.get('status')} owner={status.get('owner_facing_publish_status')}",
    )
    _add_check(
        rows,
        check="noncreative_blockers_empty",
        ok=status.get("noncreative_blockers") == [],
        evidence=str(status_path),
        detail=json.dumps(status.get("noncreative_blockers", []), ensure_ascii=False),
    )
    _add_check(
        rows,
        check="missing_only_paused_and_final_decision",
        ok=status.get("missing_or_pending") == [
            "LINE31 Meta campaign, ad set, and exactly three ads are source-verified but still PAUSED",
            "final launch/start decision remains pending before activation",
        ],
        evidence=str(status_path),
        detail=json.dumps(status.get("missing_or_pending", []), ensure_ascii=False),
    )
    activation_manifest = str(activation.get("manifest") or "")
    phrase_path = _path(activation.get("required_meta_write_phrase_path"))
    phrase_text = _read_text_if_file(phrase_path)
    _add_check(
        rows,
        check="activate_only_preflight_green",
        ok=activation.get("gate") == EXPECTED_ACTIVATION_GATE and activation.get("apply_requested") is False and activation.get("meta_write_attempted") is False,
        evidence=activation_manifest,
        detail=f"gate={activation.get('gate')} apply={activation.get('apply_requested')} meta_write={activation.get('meta_write_attempted')}",
    )
    _add_check(
        rows,
        check="activate_only_phrase_file_exists",
        ok=bool(phrase_path and phrase_path.is_file() and phrase_text.startswith("I approve META_API_LIVE_WRITE: activate only existing LINE31")),
        evidence=str(phrase_path or ""),
        detail="exact activation phrase must be tied to the latest preflight evidence lock",
    )
    _add_check(
        rows,
        check="live_customer_label_green",
        ok=label.get("gate") == EXPECTED_LABEL_GATE and label.get("checks_failed") == 0,
        evidence=str(label.get("manifest") or ""),
        detail=f"gate={label.get('gate')} failed={label.get('checks_failed')}",
    )
    _add_check(
        rows,
        check="traceability_chain_green",
        ok=traceability.get("gate") == EXPECTED_TRACEABILITY_GATE and traceability.get("checks_failed") == 0,
        evidence=str(traceability.get("manifest") or ""),
        detail=f"gate={traceability.get('gate')} failed={traceability.get('checks_failed')}",
    )
    _add_check(
        rows,
        check="post_publish_monitoring_plan_green",
        ok=monitoring.get("gate") == EXPECTED_MONITORING_GATE and monitoring.get("meta_write_attempted") is False,
        evidence=str(monitoring.get("manifest") or ""),
        detail=f"gate={monitoring.get('gate')} meta_write={monitoring.get('meta_write_attempted')}",
    )
    _add_check(
        rows,
        check="oracle_pack_answer_folder_ready",
        ok=oracle_pack.is_dir() and (oracle_pack / "Answer").is_dir() and not any((oracle_pack / "Answer").iterdir()),
        evidence=str(oracle_pack),
        detail="external expert pack exists and Answer folder is empty",
    )

    failed = [row for row in rows if row["status"] != "PASS"]
    gate = (
        "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"
        if not failed
        else "RED_LINE31_FINAL_START_DECISION_PACKET_INCOMPLETE_NO_WRITE"
    )
    activation_lock = activation.get("preflight_evidence_lock")
    activation_lock = activation_lock if isinstance(activation_lock, dict) else {}
    activation_command = (
        "cd ~/Docs/Business_3/Facebook_ads && "
        "PYTHONPATH=. python3 scripts/preflight_line31_current_meta_activation.py "
        f"--approved-preflight-lock '{activation_lock.get('path', '')}' "
        "--approval-text-file '/absolute/path/to/OWNER_PASTED_EXACT_LINE31_META_ACTIVATION_APPROVAL.txt' "
        "--execute-approved-activation --json"
    )
    return {
        "gate": gate,
        "generated_at": generated_at,
        "status_path": str(status_path),
        "oracle_pack": str(oracle_pack),
        "checks_total": len(rows),
        "checks_failed": len(failed),
        "requirements_matrix": rows,
        "current_decision_state": {
            "campaign_id": summary.get("campaign_id"),
            "adset_id": summary.get("adset_id"),
            "ad_ids": sorted(summary.get("ad_ids") or []),
            "status": "PAUSED_PRESTART_READY_FOR_OWNER_EXPERT_DECISION" if not failed else "NOT_READY",
            "daily_budget_minor_units": summary.get("adset_daily_budget"),
            "landing_url": summary.get("landing_url"),
            "copy": summary.get("customer_visible_message"),
            "cta": summary.get("customer_visible_cta"),
            "title": summary.get("customer_visible_title"),
        },
        "decision_options": [
            {
                "option": "START_AS_IS",
                "allowed_only_if": "external expert or owner decides no pre-start changes are required",
                "requires_exact_phrase_path": str(phrase_path or ""),
                "activation_command_template": activation_command,
            },
            {
                "option": "CHANGE_BEFORE_START",
                "use_when": "expert/owner wants budget, creative-feature, internal-Kaspi, placement, or copy changes before spend",
                "note": "Any change requires a fresh scoped approval, fresh readback, and a new activate-only preflight.",
            },
            {
                "option": "HOLD_PAUSED",
                "use_when": "expert answer is not available or risk remains unclear",
                "note": "Keeping the current campaign/adset/ads paused is the safe no-write default.",
            },
        ],
        "no_write_refresh_commands": [
            "cd ~/Docs/Business_3/Facebook_ads && PYTHONPATH=. python3 scripts/snapshot_line31_current_meta_state.py --json",
            "cd ~/Docs/Business_3/Facebook_ads && PYTHONPATH=. python3 scripts/preflight_line31_current_meta_activation.py --json",
            "cd ~/Docs/Autonomous_business && python3 scripts/write_line31_current_launch_status.py --json",
            "cd ~/Docs/Autonomous_business && python3 scripts/build_line31_customer_journey_traceability_audit.py --json",
        ],
        "post_activation_monitoring": {
            "packet_manifest": monitoring.get("manifest"),
            "truth_contract": monitoring.get("truth_separation_contract", []),
            "decision_gates": monitoring.get("decision_gates", {}),
        },
        "workflow_repair_requirement": {
            "owner_note": "The almost-24-hour LINE31 Meta setup cycle is treated as a launch-system failure to fix before the next campaign lanes.",
            "future_goal": "API-first campaign factory; Ads Manager UI control by agents only as last resort; bounded human UI fallback when faster and safer.",
            "expert_pack_path": str(oracle_pack),
        },
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "goal_complete": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check", "status", "evidence", "detail"])
        writer.writeheader()
        writer.writerows(rows)


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    rows = payload["requirements_matrix"]
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# LINE31 Final Start Decision Packet",
        "",
        "## Plain-English State",
        "",
        "- The LINE31 Meta campaign, ad set, and three ads are configured and source-verified.",
        "- They remain paused; this packet does not start spend.",
        "- The only intended remaining decision is whether the owner/expert starts as-is, changes first, or holds paused.",
        "- Activation remains an exact-phrase gated Meta write.",
        "",
        "## Current Objects",
        "",
        f"- Campaign ID: `{payload['current_decision_state'].get('campaign_id')}`",
        f"- Ad set ID: `{payload['current_decision_state'].get('adset_id')}`",
        f"- Ad IDs: `{', '.join(payload['current_decision_state'].get('ad_ids') or [])}`",
        f"- Daily budget minor units: `{payload['current_decision_state'].get('daily_budget_minor_units')}`",
        f"- Landing URL: `{payload['current_decision_state'].get('landing_url')}`",
        f"- CTA: `{payload['current_decision_state'].get('cta')}`",
        f"- Title: `{payload['current_decision_state'].get('title')}`",
        "",
        "## Decision Options",
        "",
    ]
    for item in payload["decision_options"]:
        lines.append(f"- `{item['option']}`: {item.get('allowed_only_if') or item.get('use_when')}")
    lines.extend(
        [
            "",
            "## Requirements Matrix",
            "",
            "| Check | Status | Detail |",
            "| --- | --- | --- |",
        ]
    )
    for row in rows:
        detail = row["detail"].replace("|", "\\|")
        lines.append(f"| `{row['check']}` | `{row['status']}` | {detail} |")
    lines.extend(
        [
            "",
            "## Exact Activation Boundary",
            "",
            f"- Exact phrase path: `{payload['decision_options'][0]['requires_exact_phrase_path']}`",
            "- Do not run activation until the owner/expert final-start decision explicitly chooses START_AS_IS.",
            "",
            "```bash",
            payload["decision_options"][0]["activation_command_template"],
            "```",
            "",
            "## Workflow Repair Requirement",
            "",
            "- The almost-24-hour Meta setup cycle is recorded as a launch-system failure.",
            "- Future campaign creation should become API-first with bounded manual fallback, not slow UI agent control by default.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_owner_action(path: Path, payload: dict[str, Any]) -> None:
    option = payload["decision_options"][0]
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# Next Owner Action",
        "",
        "If expert/owner decision is `START_AS_IS`, paste the exact phrase from:",
        "",
        f"`{option['requires_exact_phrase_path']}`",
        "",
        "Then run the activation command only after saving that exact phrase into the approval text file path used by the command template in `final_start_decision_summary.md`.",
        "",
        "If the expert recommends any change first, do not activate. Make the scoped change with a new exact approval, then rerun read-only Meta snapshot and activate-only preflight.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    status_path = args.status_path.expanduser().resolve()
    oracle_pack = args.oracle_pack.expanduser().resolve()
    status = _load_json(status_path)
    now = datetime.now(ALMATY_TZ)
    run_id = args.run_id or f"line31_final_start_decision_packet_{now.strftime('%Y%m%d_%H%M%S')}"
    output_dir = args.output_root.expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_decision_payload(
        status=status,
        status_path=status_path,
        oracle_pack=oracle_pack,
        generated_at=now.isoformat(timespec="seconds"),
    )
    payload["output_dir"] = str(output_dir)
    manifest_path = output_dir / "final_start_decision_manifest.json"
    matrix_path = output_dir / "requirements_matrix.csv"
    summary_path = output_dir / "final_start_decision_summary.md"
    owner_action_path = output_dir / "NEXT_OWNER_ACTION.md"
    payload["requirements_matrix_csv"] = str(matrix_path)
    payload["summary_md"] = str(summary_path)
    payload["next_owner_action_md"] = str(owner_action_path)
    _write_matrix(matrix_path, payload["requirements_matrix"])
    _write_summary(summary_path, payload)
    _write_owner_action(owner_action_path, payload)
    _write_json(manifest_path, payload)
    payload["manifest_path"] = str(manifest_path)
    _write_json(manifest_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--oracle-pack", type=Path, default=DEFAULT_ORACLE_PACK)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0 if payload["gate"].startswith("YELLOW") else 1


if __name__ == "__main__":
    raise SystemExit(main())
