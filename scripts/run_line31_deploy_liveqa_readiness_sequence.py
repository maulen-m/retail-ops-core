#!/usr/bin/env python3
"""Run or plan the approved LINE31 website deploy -> live QA -> readiness sequence.

Default behavior is evidence-only planning. External writes happen only with
--execute-approved-deploy-liveqa and an approval file containing the exact phrase
from the current deploy/live-QA approval packet.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shlex
import ssl
import subprocess
import sys
from typing import Any
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = Path("~/Docs/acmewear_web_v2")
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_STATUS_PATH = PROJECT_ROOT / "docs/current/LINE31_LAUNCH_CURRENT_STATUS.json"
DEFAULT_MAPPING_PATH = (
    PROJECT_ROOT
    / "exports/validation/line31_final_creative_assets_20260603_154442/"
    / "final_creative_asset_mapping_3ads_pending_publish.json"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation"
EXPECTED_LIVE_QA_SCOPE = "live_postdeploy"
EXPECTED_LIVE_QA_BASE_URL = "https://acmewear.pro"
LIVE_ROUTE_PROBE_PATHS = ("/line31", "/line31/")


class SequenceError(RuntimeError):
    """Raised when the launch sequence cannot safely continue."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SequenceError(f"{path} root must be a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_id() -> str:
    return datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")


def _load_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SequenceError(f"LINE31 current status does not exist: {path}")
    return _read_json(path)


def _load_deploy_manifest(status: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    packet = status.get("latest_web_deploy_approval_packet")
    if not isinstance(packet, dict) or not packet.get("manifest"):
        raise SequenceError("current status is missing latest_web_deploy_approval_packet.manifest")
    manifest_path = Path(str(packet["manifest"])).expanduser().resolve()
    if not manifest_path.exists():
        raise SequenceError(f"deploy/live-QA manifest does not exist: {manifest_path}")
    return manifest_path, _read_json(manifest_path)


def _load_wrangler_dryrun(status: dict[str, Any]) -> dict[str, Any]:
    dryrun = status.get("latest_web_wrangler_dryrun")
    if not isinstance(dryrun, dict):
        return {"exists": False}
    result = dict(dryrun)
    result["closeout_exists"] = bool(dryrun.get("closeout")) and Path(str(dryrun.get("closeout"))).is_file()
    result["log_exists"] = bool(dryrun.get("log_path")) and Path(str(dryrun.get("log_path"))).is_file()
    result["bundle_index_exists"] = bool(dryrun.get("bundle_index_path")) and Path(
        str(dryrun.get("bundle_index_path"))
    ).is_file()
    result["ready_for_deploy_package"] = (
        dryrun.get("gate") == "GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY"
        and result["closeout_exists"]
        and result["log_exists"]
        and result["bundle_index_exists"]
        and bool(dryrun.get("log_sha256"))
        and bool(dryrun.get("bundle_index_sha256"))
    )
    return result


def _approval_text(path: Path | None) -> str:
    if path is None:
        return ""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SequenceError(f"approval text file does not exist: {resolved}")
    if not resolved.is_file():
        raise SequenceError(f"approval text path is not a file: {resolved}")
    return resolved.read_text(encoding="utf-8").strip()


def _evaluate_deploy_approval(
    *,
    manifest: dict[str, Any],
    approval_text: str,
    execute: bool,
) -> dict[str, Any]:
    required = str(
        manifest.get("exact_owner_deploy_approval_phrase")
        or manifest.get("exact_owner_deploy_and_liveqa_approval_phrase")
        or ""
    ).strip()
    reasons: list[str] = []
    if not required:
        reasons.append("deploy/live-QA manifest has no exact owner approval phrase")
    if execute and not approval_text:
        reasons.append("approval text is required for --execute-approved-deploy-liveqa")
    if approval_text and required and approval_text != required:
        reasons.append("approval text does not exactly match current deploy/live-QA approval phrase")
    return {
        "ok": not reasons,
        "required_phrase": required,
        "approval_text_present": bool(approval_text),
        "execute_requested": execute,
        "reasons": reasons,
    }


def _validate_live_qa(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SequenceError(f"live QA JSON does not exist: {resolved}")
    payload = _read_json(resolved)
    errors: list[str] = []
    if payload.get("gate") != "GREEN":
        errors.append("live QA gate must be GREEN")
    if payload.get("qa_scope") != EXPECTED_LIVE_QA_SCOPE:
        errors.append(f"live QA qa_scope must be {EXPECTED_LIVE_QA_SCOPE}")
    if payload.get("target_base_url") != EXPECTED_LIVE_QA_BASE_URL:
        errors.append(f"live QA target_base_url must be {EXPECTED_LIVE_QA_BASE_URL}")
    if errors:
        raise SequenceError("; ".join(errors))
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "payload": payload,
    }


def _run_command(
    command: list[str] | str,
    *,
    cwd: Path,
    shell: bool = False,
) -> dict[str, Any]:
    rendered = command if isinstance(command, str) else " ".join(shlex.quote(part) for part in command)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        shell=shell,
        check=False,
    )
    return {
        "command": rendered,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "ok": completed.returncode == 0,
    }


def _extract_title(html: str) -> str:
    lower = html.lower()
    start = lower.find("<title>")
    end = lower.find("</title>", start + len("<title>"))
    if start == -1 or end == -1:
        return ""
    return html[start + len("<title>") : end].strip()[:200]


def _probe_live_line31_routes(*, timeout_seconds: int = 15) -> dict[str, Any]:
    """Read-only production route probe; does not post tracking events."""

    context = ssl._create_unverified_context()
    results: list[dict[str, Any]] = []
    for route in LIVE_ROUTE_PROBE_PATHS:
        url = f"{EXPECTED_LIVE_QA_BASE_URL}{route}"
        entry: dict[str, Any] = {"url": url, "route": route}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Codex-LINE31-readiness-probe/1.0"})
            with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
                body_bytes = response.read()
                html = body_bytes.decode("utf-8", errors="replace")
                entry.update(
                    {
                        "ok": True,
                        "http_status": int(response.status),
                        "final_url": response.geturl(),
                        "bytes": len(body_bytes),
                        "sha256": hashlib.sha256(body_bytes).hexdigest(),
                        "title": _extract_title(html),
                        "has_line31_go_starry_black": "/go/starry-black" in html,
                        "has_line31_go_wib": "/go/ivory-white-starry-black" in html,
                        "has_raw_kaspi_product_href": "kaspi.kz/shop/p/" in html,
                        "has_404_title_or_body": "404: Not Found" in html or _extract_title(html) == "404: Not Found",
                        "has_meta_pixel_code": "fbq(" in html,
                        "has_gtag_code": "gtag(" in html,
                    }
                )
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            html = body_bytes.decode("utf-8", errors="replace")
            entry.update(
                {
                    "ok": False,
                    "http_status": int(exc.code),
                    "final_url": exc.geturl(),
                    "bytes": len(body_bytes),
                    "sha256": hashlib.sha256(body_bytes).hexdigest(),
                    "title": _extract_title(html),
                    "has_404_title_or_body": "404: Not Found" in html or _extract_title(html) == "404: Not Found",
                    "error": "HTTPError",
                }
            )
        except Exception as exc:  # pragma: no cover - non-fatal evidence capture.
            entry.update({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        results.append(entry)

    route_ready = any(
        item.get("http_status") == 200
        and item.get("has_line31_go_starry_black")
        and item.get("has_line31_go_wib")
        and not item.get("has_raw_kaspi_product_href")
        and not item.get("has_404_title_or_body")
        for item in results
    )
    return {
        "target_base_url": EXPECTED_LIVE_QA_BASE_URL,
        "checked_paths": list(LIVE_ROUTE_PROBE_PATHS),
        "route_ready_for_postdeploy_qa": route_ready,
        "results": results,
        "note": (
            "Read-only route probe only. It does not post synthetic QA events and "
            "does not replace live post-deploy tracking QA."
        ),
    }


def _mapping_command(
    *,
    asset_manifest: Path,
    live_qa_json: Path,
    output_mapping: Path,
) -> list[str]:
    return [
        sys.executable,
        "scripts/prepare_line31_multi_creative_mapping.py",
        "--asset-manifest",
        str(asset_manifest),
        "--landing-url",
        "https://acmewear.pro/line31",
        "--kaspi-marketplace-cta-url",
        "https://acmewear.pro/go/starry-black",
        "--creative-ready-declared",
        "--tracking-qa-evidence-file",
        str(live_qa_json),
        "--output",
        str(output_mapping),
        "--overwrite",
        "--json",
    ]


def _validate_mapping_result(path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "scripts/validate_line31_final_creative_mapping.py",
        "--mapping",
        str(path),
        "--json",
    ]
    result = _run_command(command, cwd=PROJECT_ROOT)
    try:
        payload = json.loads(result["stdout_tail"])
    except json.JSONDecodeError:
        payload = {}
    errors = payload.get("errors") if isinstance(payload, dict) else []
    expected_pending_only = errors == [
        "publish_authority.approved must be true for publish readiness"
    ]
    result["validator_payload"] = payload
    result["expected_pending_meta_approval_only"] = expected_pending_only
    return result


def _meta_publish_phrase(*, mapping_path: Path, tracking_qa_path: Path) -> str:
    return (
        "I approve LINE31_COUNTRYWIDE_META_PUBLISH for the final validated 3-creative mapping "
        f"{mapping_path.resolve()} / sha256={_sha256(mapping_path.resolve())}, using one LINE31 countrywide "
        "campaign/adset with three ads, daily budget 15,000 KZT, hard cap 20,000 KZT, "
        "landing URL https://acmewear.pro/line31, CTA color priority starry black -> WIB mixed color set -> "
        "blue misty -> olive green -> remaining colors -> espresso last, and current tracking QA evidence "
        f"{tracking_qa_path.resolve()} / sha256={_sha256(tracking_qa_path.resolve())}. "
        "No other Meta, Kaspi, WebUI, website, price, stock, cash, supplier, PO, scheduler, workbook, "
        "database, internal Kaspi campaign pause, or owner-publication changes are approved."
    )


def run_sequence(args: argparse.Namespace) -> dict[str, Any]:
    status = _load_status(args.status)
    deploy_manifest_path, deploy_manifest = _load_deploy_manifest(status)
    wrangler_dryrun = _load_wrangler_dryrun(status)
    approval_gate = _evaluate_deploy_approval(
        manifest=deploy_manifest,
        approval_text=_approval_text(args.approval_text_file),
        execute=args.execute_approved_deploy_liveqa,
    )
    if args.execute_approved_deploy_liveqa and not approval_gate["ok"]:
        raise SequenceError("; ".join(approval_gate["reasons"]))

    run_id = args.run_id or _run_id()
    output_dir = args.output_root / f"line31_deploy_liveqa_readiness_sequence_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    live_qa_path: Path | None = args.live_qa_json
    steps: list[dict[str, Any]] = []
    external_write_attempted = False
    live_route_probe = None
    if not args.skip_live_route_probe:
        live_route_probe = _probe_live_line31_routes(timeout_seconds=args.live_route_probe_timeout_seconds)

    if args.execute_approved_deploy_liveqa:
        deploy_command = str(deploy_manifest.get("deploy_command_if_approved") or "").strip()
        live_qa_command = str(deploy_manifest.get("postdeploy_live_qa_command_if_approved") or "").strip()
        expected_live_qa = str(deploy_manifest.get("postdeploy_live_qa_expected_json") or "").strip()
        if not deploy_command or not live_qa_command or not expected_live_qa:
            raise SequenceError("deploy/live-QA manifest is missing execute commands or expected QA path")
        external_write_attempted = True
        deploy_result = _run_command(deploy_command, cwd=PROJECT_ROOT, shell=True)
        steps.append({"name": "cloudflare_deploy", **deploy_result})
        if not deploy_result["ok"]:
            raise SequenceError("Cloudflare deploy command failed; see output manifest")
        live_result = _run_command(live_qa_command, cwd=PROJECT_ROOT, shell=True)
        steps.append({"name": "postdeploy_live_tracking_qa", **live_result})
        if not live_result["ok"]:
            raise SequenceError("post-deploy live QA command failed; see output manifest")
        live_qa_path = Path(expected_live_qa)

    live_qa_result: dict[str, Any] | None = None
    mapping_result: dict[str, Any] | None = None
    mapping_validation: dict[str, Any] | None = None
    meta_publish_approval_phrase = ""
    if live_qa_path is not None:
        live_qa_result = _validate_live_qa(live_qa_path)
        command = _mapping_command(
            asset_manifest=args.asset_manifest,
            live_qa_json=Path(live_qa_result["path"]),
            output_mapping=args.output_mapping,
        )
        mapping_result = _run_command(command, cwd=PROJECT_ROOT)
        steps.append({"name": "wire_live_qa_into_multi_creative_mapping", **mapping_result})
        if not mapping_result["ok"]:
            raise SequenceError("multi-creative mapping wire command failed; see output manifest")
        mapping_validation = _validate_mapping_result(args.output_mapping)
        steps.append({"name": "validate_multi_creative_mapping_pending_meta_approval", **mapping_validation})
        if not mapping_validation["expected_pending_meta_approval_only"]:
            raise SequenceError("mapping validation did not narrow to only pending Meta approval")
        meta_publish_approval_phrase = _meta_publish_phrase(
            mapping_path=args.output_mapping,
            tracking_qa_path=Path(live_qa_result["path"]),
        )

    gate = (
        "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE"
        if live_qa_result and mapping_validation
        else "YELLOW_WAITING_FOR_EXACT_DEPLOY_LIVEQA_APPROVAL_NO_EXTERNAL_WRITE"
    )
    payload = {
        "gate": gate,
        "generated_at": datetime.now(ALMATY_TZ).isoformat(timespec="seconds"),
        "run_id": run_id,
        "status_path": str(args.status.resolve()),
        "deploy_manifest_path": str(deploy_manifest_path),
        "wrangler_dryrun": wrangler_dryrun,
        "deploy_approval_gate": approval_gate,
        "asset_manifest": str(args.asset_manifest.resolve()),
        "output_mapping": str(args.output_mapping.resolve()),
        "live_qa": live_qa_result,
        "live_route_probe": live_route_probe,
        "mapping_validation": mapping_validation,
        "meta_publish_approval_phrase": meta_publish_approval_phrase,
        "steps": steps,
        "external_write_attempted": external_write_attempted,
        "meta_write_attempted": False,
        "boundary": (
            "This script does not perform Meta publish. Without --execute-approved-deploy-liveqa it performs "
            "no external writes at all."
        ),
        "output_dir": str(output_dir),
    }
    _write_json(output_dir / "sequence_manifest.json", payload)
    (output_dir / "closeout.md").write_text(_render_closeout(payload), encoding="utf-8")
    if meta_publish_approval_phrase:
        (output_dir / "NEXT_META_PUBLISH_APPROVAL_PHRASE.txt").write_text(
            meta_publish_approval_phrase + "\n",
            encoding="utf-8",
        )
    return payload


def _render_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# LINE31 Deploy Live-QA Readiness Sequence",
        "",
        f"Gate: {payload['gate']}",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "## Boundary",
        "",
        payload["boundary"],
        "",
        f"- External write attempted: `{payload['external_write_attempted']}`",
        f"- Meta write attempted: `{payload['meta_write_attempted']}`",
        "",
        "## Current Inputs",
        "",
        f"- Deploy manifest: `{payload['deploy_manifest_path']}`",
        f"- Wrangler dry-run ready: `{bool(payload.get('wrangler_dryrun', {}).get('ready_for_deploy_package'))}`",
        f"- Wrangler dry-run closeout: `{payload.get('wrangler_dryrun', {}).get('closeout', '')}`",
        f"- Asset manifest: `{payload['asset_manifest']}`",
        f"- Output mapping: `{payload['output_mapping']}`",
        "",
        "## Read-Only Live Route Probe",
        "",
        f"- Route ready for postdeploy QA: `{bool((payload.get('live_route_probe') or {}).get('route_ready_for_postdeploy_qa'))}`",
    ]
    if payload.get("live_route_probe"):
        for item in payload["live_route_probe"].get("results", []):
            lines.append(
                f"- `{item.get('route')}` status `{item.get('http_status', 'n/a')}` "
                f"title `{item.get('title', '')}` starry-route "
                f"`{item.get('has_line31_go_starry_black', False)}` 404 "
                f"`{item.get('has_404_title_or_body', False)}`"
            )
    lines.extend(
        [
            "",
        "## Deploy Approval Gate",
        "",
        f"- Approval text present: `{payload['deploy_approval_gate']['approval_text_present']}`",
        f"- Execute requested: `{payload['deploy_approval_gate']['execute_requested']}`",
        f"- Approval gate ok: `{payload['deploy_approval_gate']['ok']}`",
        ]
    )
    reasons = payload["deploy_approval_gate"].get("reasons") or []
    if reasons:
        lines.extend(["", "Reasons:", *[f"- `{reason}`" for reason in reasons]])
    if payload.get("live_qa"):
        lines.extend(
            [
                "",
                "## Live QA",
                "",
                f"- Path: `{payload['live_qa']['path']}`",
                f"- SHA256: `{payload['live_qa']['sha256']}`",
            ]
        )
    if payload.get("mapping_validation"):
        lines.extend(
            [
                "",
                "## Mapping Validation",
                "",
                f"- Expected only pending Meta approval: `{payload['mapping_validation']['expected_pending_meta_approval_only']}`",
            ]
        )
    if payload.get("meta_publish_approval_phrase"):
        lines.extend(
            [
                "",
                "## Next Exact Meta Publish Approval Phrase",
                "",
                "```text",
                payload["meta_publish_approval_phrase"],
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS_PATH)
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        default=PROJECT_ROOT / "exports/validation/line31_final_creative_assets_20260603_154442/manifest.json",
    )
    parser.add_argument("--output-mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--approval-text-file", type=Path, default=None)
    parser.add_argument("--skip-live-route-probe", action="store_true")
    parser.add_argument("--live-route-probe-timeout-seconds", type=int, default=15)
    parser.add_argument(
        "--live-qa-json",
        type=Path,
        default=None,
        help="Already-generated live postdeploy tracking QA JSON to wire into mapping.",
    )
    parser.add_argument(
        "--execute-approved-deploy-liveqa",
        action="store_true",
        help=(
            "Run the external deploy and live QA commands. Requires exact deploy/live-QA "
            "approval text in --approval-text-file."
        ),
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = run_sequence(args)
    except SequenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
