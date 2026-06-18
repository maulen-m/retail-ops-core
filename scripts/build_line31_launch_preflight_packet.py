#!/usr/bin/env python3
"""Build a read-only LINE31 final launch preflight evidence packet."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.report_line31_next_launch_action import (  # noqa: E402
    DEFAULT_APPROVAL_PATH,
    build_report,
)
from scripts.build_line31_current_noncreative_gate_matrix import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT as DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
    build_matrix as build_current_noncreative_matrix,
)
from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_MAPPING,
    validate_mapping,
)
from scripts.validate_line31_launch_readiness import (  # noqa: E402
    DEFAULT_EVIDENCE_ROOT,
    validate_launch_readiness,
)
from scripts.validate_line31_owner_objective_source_freshness import (  # noqa: E402
    DEFAULT_OWNER_FACTS_PATH,
    validate_owner_objective_source_freshness,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
PROTECTED_SURFACES = (
    PROJECT_ROOT / "db" / "app.db",
    PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx",
)
REFERENCE_FILES = (
    PROJECT_ROOT / "docs" / "validation" / "LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md",
    PROJECT_ROOT
    / "docs"
    / "parallel_runs"
    / "2026-06-01_line31_final_creative_meta_publish"
    / "PLAN.md",
    PROJECT_ROOT
    / "docs"
    / "agent_handoffs"
    / "LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS"
    / "01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, *, required: bool = True) -> dict[str, Any]:
    exists = path.exists()
    record: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "required": required,
    }
    if exists and path.is_file():
        record["sha256"] = _sha256(path)
        record["bytes"] = path.stat().st_size
    return record


def _result_payload(result: Any) -> dict[str, Any]:
    payload = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "metrics": result.metrics,
    }
    if hasattr(result, "gate"):
        payload["gate"] = result.gate
    return payload


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text_atomic(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _packet_gate(
    pending: Any,
    strict: Any,
    owner_source_freshness: dict[str, Any],
) -> str:
    if owner_source_freshness.get("ok") is not True:
        return "YELLOW_OWNER_SOURCE_FRESHNESS_BLOCKERS"
    if strict.ok:
        return "GREEN_LAUNCH_READY_FOR_OWNER_APPROVED_META_PUBLISH"
    if pending.ok:
        return "GREEN_EXCEPT_CREATIVE"
    return "YELLOW_NON_CREATIVE_READINESS_BLOCKERS"


def build_packet(
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    mapping_path: Path | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    run_id: str | None = None,
    refresh_noncreative_matrix: bool = True,
    noncreative_output_root: Path = DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
    owner_facts_path: Path = DEFAULT_OWNER_FACTS_PATH,
) -> dict[str, Any]:
    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    run_id = run_id or datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    packet_dir = output_root / f"line31_final_launch_preflight_{run_id}"
    if packet_dir.exists():
        raise ValueError(f"packet output already exists: {packet_dir}")
    packet_dir.mkdir(parents=True)

    current_noncreative_matrix: dict[str, Any] | None = None
    if refresh_noncreative_matrix:
        current_noncreative_matrix = build_current_noncreative_matrix(
            output_root=noncreative_output_root,
            run_id=run_id,
        )
    owner_source_freshness = validate_owner_objective_source_freshness(owner_facts_path)
    owner_source_freshness_ok = owner_source_freshness.get("ok") is True
    source_freshness_blockers = list(owner_source_freshness.get("errors", []))

    mapping = mapping_path or evidence_root / DEFAULT_MAPPING.name
    pending = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=True,
        mapping_path=mapping,
    )
    strict = validate_launch_readiness(
        evidence_root,
        allow_pending_creative=False,
        mapping_path=mapping,
    )
    template = validate_mapping(mapping, template_ok=True)
    creative_strict = validate_mapping(mapping, template_ok=False)
    next_action = build_report(
        evidence_root=evidence_root,
        mapping_path=mapping,
        approval_path=evidence_root / DEFAULT_APPROVAL_PATH.name,
    )
    gate = _packet_gate(pending, strict, owner_source_freshness)
    packet_next_action = next_action["next_action"]
    if source_freshness_blockers:
        packet_next_action = (
            "Repair owner objective source freshness before final creative publish "
            "readiness can be trusted."
        )
    packet_next_action_payload = {
        **next_action,
        "next_action": packet_next_action,
        "source_freshness_blockers": source_freshness_blockers,
        "owner_source_freshness_ok": owner_source_freshness_ok,
    }

    protected = [_file_record(path) for path in PROTECTED_SURFACES]
    references = [
        _file_record(evidence_root / "closeout.md"),
        _file_record(mapping),
        _file_record(evidence_root / "final_creative_publish_intake_and_approval.md"),
        *[_file_record(path, required=False) for path in REFERENCE_FILES],
    ]

    pending_payload = _result_payload(pending)
    strict_payload = _result_payload(strict)
    template_payload = _result_payload(template)
    creative_strict_payload = _result_payload(creative_strict)

    _write_json(packet_dir / "readiness_pending_creative_allowed.json", pending_payload)
    _write_json(packet_dir / "readiness_strict_publish.json", strict_payload)
    _write_json(packet_dir / "creative_template_validation.json", template_payload)
    _write_json(packet_dir / "creative_strict_validation.json", creative_strict_payload)
    _write_json(packet_dir / "next_launch_action.json", packet_next_action_payload)
    _write_json(
        packet_dir / "owner_objective_source_freshness.json",
        owner_source_freshness,
    )

    protected_lines = ["path\tsha256\tbytes\texists"]
    for row in protected:
        protected_lines.append(
            "\t".join(
                [
                    str(row["path"]),
                    str(row.get("sha256", "")),
                    str(row.get("bytes", "")),
                    str(row["exists"]).lower(),
                ]
            )
        )
    _write_text_atomic(packet_dir / "protected_surface_hashes.tsv", "\n".join(protected_lines) + "\n")

    commands = "\n".join(next_action["commands_to_close"]) + "\n"
    _write_text_atomic(packet_dir / "commands_to_close.txt", commands)

    summary = _summary_markdown(
        generated_at=generated_at,
        gate=gate,
        next_action=packet_next_action_payload,
        pending=pending_payload,
        strict=strict_payload,
        current_noncreative_matrix=current_noncreative_matrix,
        owner_source_freshness=owner_source_freshness,
        protected=protected,
        references=references,
    )
    _write_text_atomic(packet_dir / "line31_launch_preflight_summary.md", summary)

    outputs = sorted(
        [path.name for path in packet_dir.iterdir()]
        + ["line31_launch_preflight_manifest.json"]
    )
    manifest = {
        "generated_at": generated_at,
        "gate": gate,
        "packet_dir": str(packet_dir),
        "evidence_root": str(evidence_root),
        "mapping": str(mapping),
        "pending_ok": pending.ok,
        "strict_ok": strict.ok,
        "ready_to_publish": strict.ok and owner_source_freshness_ok,
        "current_noncreative_matrix_refreshed": refresh_noncreative_matrix,
        "current_noncreative_matrix": current_noncreative_matrix,
        "owner_objective_source_freshness": owner_source_freshness,
        "protected_surfaces": protected,
        "references": references,
        "outputs": outputs,
        "next_action": packet_next_action,
        "missing_or_pending": packet_next_action_payload["missing_or_pending"],
        "noncreative_blockers": packet_next_action_payload["noncreative_blockers"],
        "source_freshness_blockers": source_freshness_blockers,
        "owner_source_freshness_ok": owner_source_freshness_ok,
        "approval_evidence_requirement": next_action["approval_evidence_requirement"],
        "standalone_approval_recorder_example_command": next_action[
            "standalone_approval_recorder_example_command"
        ],
        "standalone_approval_guard": next_action["standalone_approval_guard"],
        "starter_prompt": next_action["starter_prompt"],
        "no_external_writes_performed": True,
    }
    _write_json(packet_dir / "line31_launch_preflight_manifest.json", manifest)
    return manifest


def _summary_markdown(
    *,
    generated_at: str,
    gate: str,
    next_action: dict[str, Any],
    pending: dict[str, Any],
    strict: dict[str, Any],
    current_noncreative_matrix: dict[str, Any] | None,
    owner_source_freshness: dict[str, Any],
    protected: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> str:
    lines = [
        "# LINE31 Final Launch Preflight Packet",
        "",
        f"Generated: {generated_at}",
        "",
        f"Gate: `{gate}`",
        f"Ready to publish: `{str(strict['ok'] and owner_source_freshness.get('ok') is True).lower()}`",
        "",
        "## Next Action",
        "",
        next_action["next_action"],
        "",
        "## Readiness",
        "",
        f"- Pending-creative mode: `{'PASS' if pending['ok'] else 'FAIL'}` / `{pending.get('gate', '')}`",
        f"- Strict publish mode: `{'PASS' if strict['ok'] else 'FAIL'}` / `{strict.get('gate', '')}`",
        "",
    ]
    if current_noncreative_matrix:
        lines.extend(
            [
                "## Current Non-Creative Matrix",
                "",
                f"- Overall gate: `{current_noncreative_matrix['overall_gate']}`",
                f"- Can use GREEN_EXCEPT_CREATIVE: `{str(current_noncreative_matrix['can_use_green_except_creative']).lower()}`",
                f"- Evidence root: `{current_noncreative_matrix['evidence_root']}`",
                f"- Retained LINE31 non-creative blockers: `{current_noncreative_matrix.get('retained_noncreative_blockers', [])}`",
                f"- Advisory repo-health blockers: `{current_noncreative_matrix.get('advisory_repo_blockers', [])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Owner Objective Source Freshness",
            "",
            f"- Gate: `{owner_source_freshness.get('gate', 'UNKNOWN')}`",
            f"- Cash workbook: `{owner_source_freshness.get('cash_and_shr', {}).get('workbook_path', '')}`",
            f"- Cash timestamp: `{owner_source_freshness.get('cash_and_shr', {}).get('latest_cash_balance_timestamp', '')}`",
            f"- SHR #18 base-log row: `{str(owner_source_freshness.get('cash_and_shr', {}).get('shr_payment_18_base_log_present')).lower()}`",
            f"- SHR #18 ledger row: `{str(owner_source_freshness.get('cash_and_shr', {}).get('shr_payment_18_ledger_present')).lower()}`",
            f"- Protected reserve: `expected_min_kzt={owner_source_freshness.get('protected_reserve', {}).get('expected_min_kzt')}`, `owner_fact_min_kzt={owner_source_freshness.get('protected_reserve', {}).get('owner_fact_min_kzt')}`, `ok={str(owner_source_freshness.get('protected_reserve', {}).get('ok')).lower()}`",
            f"- LINE31 stock source packet: `{owner_source_freshness.get('line31_stock', {}).get('source_packet', '')}`",
            f"- LINE31 stock gates: manifest `{owner_source_freshness.get('line31_stock', {}).get('manifest_gate', '')}`, validation `{owner_source_freshness.get('line31_stock', {}).get('validation_gate', '')}`",
            "",
        ]
    )
    if next_action["missing_or_pending"]:
        lines.extend(["## Missing Or Pending", ""])
        lines.extend(f"- `{item}`" for item in next_action["missing_or_pending"])
        lines.append("")
    if next_action["noncreative_blockers"]:
        lines.extend(["## Non-Creative Blockers", ""])
        lines.extend(f"- {item}" for item in next_action["noncreative_blockers"])
        lines.append("")
    if next_action.get("source_freshness_blockers"):
        lines.extend(["## Source Freshness Blockers", ""])
        lines.extend(f"- {item}" for item in next_action["source_freshness_blockers"])
        lines.append("")

    lines.extend(
        [
            "## Approval Evidence Requirement",
            "",
            next_action["approval_evidence_requirement"],
            "",
            "## Standalone Approval Recorder Command",
            "",
            next_action["standalone_approval_guard"],
            "",
            "```bash",
            next_action["standalone_approval_recorder_example_command"],
            "```",
            "",
            "## Protected Surface Hashes",
            "",
            "| surface | sha256 | exists |",
            "| --- | --- | --- |",
        ]
    )
    for row in protected:
        lines.append(f"| `{row['path']}` | `{row.get('sha256', '')}` | `{row['exists']}` |")

    lines.extend(["", "## Reference Files", "", "| file | sha256 | exists |", "| --- | --- | --- |"])
    for row in references:
        lines.append(f"| `{row['path']}` | `{row.get('sha256', '')}` | `{row['exists']}` |")

    lines.extend(
        [
            "",
            "## Starter Prompt",
            "",
            "```text",
            next_action["starter_prompt"],
            "```",
            "",
            "## Safety",
            "",
            "This packet is read-only/local evidence. It does not perform DB, workbook, scheduler, source-pointer, Web_automation, Kaspi/API/WebUI/Meta, campaign, price, stock, cash, PO, supplier, or publication writes.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--mapping", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--noncreative-output-root",
        type=Path,
        default=DEFAULT_NONCREATIVE_MATRIX_OUTPUT_ROOT,
        help="Output root for the current non-creative validator matrix refresh.",
    )
    parser.add_argument(
        "--owner-facts",
        type=Path,
        default=DEFAULT_OWNER_FACTS_PATH,
        help="Owner-facts JSON used by the source-freshness proof.",
    )
    parser.add_argument(
        "--skip-noncreative-refresh",
        action="store_true",
        help="Do not refresh current non-creative validators before building packet.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = build_packet(
            evidence_root=args.evidence_root,
            mapping_path=args.mapping,
            output_root=args.output_root,
            run_id=args.run_id,
            refresh_noncreative_matrix=not args.skip_noncreative_refresh,
            noncreative_output_root=args.noncreative_output_root,
            owner_facts_path=args.owner_facts,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"LINE31 launch preflight packet: {manifest['gate']}")
        print(manifest["packet_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
