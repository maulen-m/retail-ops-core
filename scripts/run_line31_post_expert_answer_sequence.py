#!/usr/bin/env python3
"""Run the local no-write LINE31 post-expert answer sequence.

Sequence:
1. Classify the Oracle pack Answer/ folder.
2. Refresh the canonical LINE31 current status.
3. Refresh the active-goal completion audit.
4. Write a compact sequence packet with the next safe action.

No Meta, website, Kaspi, DB, workbook, scheduler, cash, stock, price, supplier,
PO, or owner-publication write is attempted by this helper.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import ingest_line31_expert_launch_answer  # noqa: E402
from scripts.audit_line31_active_goal_completion import (  # noqa: E402
    DEFAULT_MARKDOWN_OUTPUT,
    _markdown as audit_markdown,
    build_completion_audit,
)
from scripts.ingest_line31_expert_launch_answer import (  # noqa: E402
    DEFAULT_ORACLE_PACK,
    DEFAULT_OUTPUT_ROOT,
)
from scripts.write_line31_current_launch_status import (  # noqa: E402
    DEFAULT_JSON_PATH as DEFAULT_STATUS_JSON_PATH,
    DEFAULT_MD_PATH as DEFAULT_STATUS_MD_PATH,
    write_current_status,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_SEQUENCE_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# LINE31 Post-Expert Answer Sequence",
        "",
        "## Sequence State",
        "",
        f"- Expert intake gate: `{payload['expert_intake']['gate']}`",
        f"- Expert decision: `{payload['expert_intake']['decision']}`",
        f"- Current status: `{payload['current_status']['status']}`",
        f"- Current status owner gate: `{payload['current_status']['owner_facing_publish_status']}`",
        f"- Completion audit gate: `{payload['completion_audit']['gate']}`",
        f"- Completion audit complete: `{str(payload['completion_audit']['complete']).lower()}`",
        "",
        "## Next Safe Action",
        "",
        payload["next_safe_action"],
        "",
        "## Evidence",
        "",
        f"- Expert intake manifest: `{payload['expert_intake']['manifest_path']}`",
        f"- Current status JSON: `{payload['current_status']['json_path']}`",
        f"- Current status Markdown: `{payload['current_status']['markdown_path']}`",
        f"- Completion audit Markdown: `{payload['completion_audit']['markdown_path']}`",
        f"- Sequence manifest: `{payload['manifest_path']}`",
        "",
        "## Safety",
        "",
        "- External writes attempted: `false`",
        "- Meta writes attempted: `false`",
        "- Website deploy attempted: `false`",
        "- Production DB/workbook writes attempted: `false`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_next_action(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# Next Safe Action",
        "",
        payload["next_safe_action"],
        "",
        "Use this sequence again after changing the Oracle `Answer/` folder or after any scoped pre-start repair.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gate_for(intake: dict[str, Any], audit: dict[str, Any]) -> str:
    intake_gate = str(intake.get("gate") or "")
    if intake_gate.startswith("RED"):
        return "RED_LINE31_POST_EXPERT_SEQUENCE_STOPPED_NO_WRITE"
    if audit.get("complete") is True:
        return "GREEN_LINE31_POST_EXPERT_SEQUENCE_COMPLETE_AUDIT_READY_NO_WRITE"
    if intake.get("decision") == "PENDING_ANSWER":
        return "YELLOW_LINE31_POST_EXPERT_SEQUENCE_WAITING_FOR_ANSWER_NO_WRITE"
    if intake.get("decision") == "START_AS_IS":
        return "YELLOW_LINE31_POST_EXPERT_SEQUENCE_START_AS_IS_NEEDS_ACTIVATION_NO_WRITE"
    if intake.get("decision") == "CHANGE_BEFORE_START":
        return "YELLOW_LINE31_POST_EXPERT_SEQUENCE_CHANGES_REQUIRED_NO_WRITE"
    if intake.get("decision") == "HOLD_PAUSED":
        return "YELLOW_LINE31_POST_EXPERT_SEQUENCE_HOLD_PAUSED_NO_WRITE"
    return "YELLOW_LINE31_POST_EXPERT_SEQUENCE_UNCLASSIFIED_NO_WRITE"


def run(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now(ALMATY_TZ)
    run_id = args.run_id or f"line31_post_expert_answer_sequence_{now.strftime('%Y%m%d_%H%M%S')}"
    output_dir = args.output_root.expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    intake_args = argparse.Namespace(
        oracle_pack=args.oracle_pack,
        output_root=args.output_root,
        final_start_manifest=args.final_start_manifest,
        run_id=f"{run_id}__expert_intake",
        json=False,
    )
    expert_intake = ingest_line31_expert_launch_answer.run(intake_args)
    current_status = write_current_status(
        json_path=args.status_json_path.expanduser().resolve(),
        markdown_path=args.status_markdown_path.expanduser().resolve(),
    )
    completion_audit = build_completion_audit()
    audit_markdown_path = args.audit_markdown_path.expanduser().resolve()
    audit_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    audit_markdown_path.write_text(audit_markdown(completion_audit), encoding="utf-8")

    gate = _gate_for(expert_intake, completion_audit)
    payload: dict[str, Any] = {
        "gate": gate,
        "generated_at": now.isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "oracle_pack": str(args.oracle_pack.expanduser().resolve()),
        "expert_intake": {
            "gate": expert_intake.get("gate"),
            "decision": expert_intake.get("decision"),
            "decision_confidence": expert_intake.get("decision_confidence"),
            "manifest_path": expert_intake.get("manifest_path"),
            "summary_md": expert_intake.get("summary_md"),
            "next_safe_action_md": expert_intake.get("next_safe_action_md"),
            "answer_dir": expert_intake.get("answer_dir"),
            "answer_path": expert_intake.get("answer_path"),
            "next_safe_action": expert_intake.get("next_safe_action", {}),
        },
        "current_status": {
            "status": current_status.get("status"),
            "owner_facing_publish_status": current_status.get("owner_facing_publish_status"),
            "ready_to_publish": current_status.get("ready_to_publish"),
            "missing_or_pending": current_status.get("missing_or_pending", []),
            "json_path": current_status.get("json_path"),
            "markdown_path": current_status.get("markdown_path"),
        },
        "completion_audit": {
            "gate": completion_audit.get("gate"),
            "complete": completion_audit.get("complete"),
            "ready_to_publish": completion_audit.get("ready_to_publish"),
            "next_action": completion_audit.get("next_action"),
            "markdown_path": str(audit_markdown_path),
        },
        "next_safe_action": completion_audit.get("next_action") or str(
            (expert_intake.get("next_safe_action") or {}).get("action") or ""
        ),
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "website_write_attempted": False,
        "production_db_or_workbook_write_attempted": False,
    }
    manifest_path = output_dir / "post_expert_answer_sequence_manifest.json"
    summary_path = output_dir / "post_expert_answer_sequence_summary.md"
    next_action_path = output_dir / "NEXT_SAFE_ACTION.md"
    payload["manifest_path"] = str(manifest_path)
    payload["summary_md"] = str(summary_path)
    payload["next_safe_action_md"] = str(next_action_path)
    _write_summary(summary_path, payload)
    _write_next_action(next_action_path, payload)
    _write_json(manifest_path, payload)

    # Leave the stable operator pointer aware of the sequence packet just written.
    refreshed_status = write_current_status(
        json_path=args.status_json_path.expanduser().resolve(),
        markdown_path=args.status_markdown_path.expanduser().resolve(),
    )
    payload["current_status"] = {
        "status": refreshed_status.get("status"),
        "owner_facing_publish_status": refreshed_status.get(
            "owner_facing_publish_status"
        ),
        "ready_to_publish": refreshed_status.get("ready_to_publish"),
        "missing_or_pending": refreshed_status.get("missing_or_pending", []),
        "json_path": refreshed_status.get("json_path"),
        "markdown_path": refreshed_status.get("markdown_path"),
    }
    _write_summary(summary_path, payload)
    _write_json(manifest_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-pack", type=Path, default=DEFAULT_ORACLE_PACK)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_SEQUENCE_OUTPUT_ROOT)
    parser.add_argument("--final-start-manifest", type=Path)
    parser.add_argument("--status-json-path", type=Path, default=DEFAULT_STATUS_JSON_PATH)
    parser.add_argument("--status-markdown-path", type=Path, default=DEFAULT_STATUS_MD_PATH)
    parser.add_argument("--audit-markdown-path", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 2 if str(payload["gate"]).startswith("RED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
