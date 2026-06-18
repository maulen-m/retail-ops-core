#!/usr/bin/env python3
"""Record exact LINE31 owner publish approval as local evidence."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_MAPPING,
    required_owner_approval_phrase,
    validate_mapping,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_APPROVAL_PATH = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_goal_stock_dashboard_repair_20260601_133438"
    / "final_creative_publish_intake_and_approval.md"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_goal_stock_dashboard_repair_20260601_133438"
    / "owner_publish_approval_evidence"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_approval_text(args: argparse.Namespace) -> str:
    if args.approval_text_file and args.from_stdin:
        raise ValueError("choose only one input: --approval-text-file or --from-stdin")
    if args.approval_text_file:
        path = args.approval_text_file.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"approval text file does not exist: {path}")
        return path.read_text(encoding="utf-8")
    if args.from_stdin:
        return sys.stdin.read()
    raise ValueError("approval input required: pass --approval-text-file or --from-stdin")


def _validate_exact_phrase(input_text: str, required_phrase: str) -> None:
    if required_phrase not in input_text:
        raise ValueError("approval input does not contain the exact required LINE31 owner approval phrase")


def _validate_mapping_ready_for_approval(mapping_path: Path) -> dict[str, object]:
    resolved = mapping_path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"mapping file does not exist: {resolved}")
    result = validate_mapping(resolved, template_ok=False)
    approval_only_errors = {
        "publish_authority.approved must be true for publish readiness",
    }
    blocking_errors = [error for error in result.errors if error not in approval_only_errors]
    if blocking_errors:
        raise ValueError(
            "mapping is not ready for owner approval; fill and validate final creative "
            "mapping before recording standalone approval evidence: "
            + "; ".join(blocking_errors)
        )
    return {
        "mapping_ready_for_approval": True,
        "mapping_validation_allowed_pending_errors": [
            error for error in result.errors if error in approval_only_errors
        ],
        "mapping_validation_metrics": result.metrics,
    }


def _write_atomic(path: Path, text: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ValueError(f"output exists; pass --overwrite to replace it: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
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


def record_approval(args: argparse.Namespace) -> dict[str, object]:
    approval_path = args.approval_phrase_path.expanduser().resolve()
    required_phrase = required_owner_approval_phrase(approval_path)
    input_text = _read_approval_text(args)
    _validate_exact_phrase(input_text, required_phrase)
    mapping_ready_result: dict[str, object] | None = None
    if getattr(args, "require_mapping_ready", False):
        mapping_ready_result = _validate_mapping_ready_for_approval(args.mapping)

    timestamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir.expanduser().resolve()
    output_path = args.output or output_dir / f"line31_owner_publish_approval_{timestamp}.md"
    output_path = output_path.expanduser().resolve()

    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    body = "\n".join(
        [
            "# LINE31 Owner Publish Approval Evidence",
            "",
            f"Recorded: {generated_at}",
            "",
            "Purpose: exact owner approval evidence for LINE31 countrywide Meta publish readiness.",
            "",
            "Approval phrase source:",
            f"`{approval_path}`",
            "",
            "Mapping file intended for strict validation:",
            f"`{args.mapping}`",
            "",
            "Mapping readiness guard:",
            (
                "`--require-mapping-ready` passed; final creative mapping was populated "
                "and validated except for the expected pending owner-approval boolean."
                if mapping_ready_result
                else "Not required for this evidence record. Use `--require-mapping-ready` for the standalone manual approval route."
            ),
            "",
            "## Exact Owner Approval Phrase",
            "",
            "```text",
            required_phrase,
            "```",
            "",
            "## Raw Input Containing Phrase",
            "",
            "```text",
            input_text.strip(),
            "```",
            "",
        ]
    )
    _write_atomic(output_path, body, overwrite=args.overwrite)
    digest = _sha256(output_path)
    return {
        "ok": True,
        "approval_evidence_path": str(output_path),
        "approval_evidence_sha256": digest,
        "approval_phrase_path": str(approval_path),
        "mapping": str(args.mapping),
        "mapping_ready_for_approval_required": bool(getattr(args, "require_mapping_ready", False)),
        "mapping_ready_for_approval": bool(mapping_ready_result),
        "generated_at": generated_at,
        "next_mapping_flags": [
            "--owner-approved",
            "--approval-evidence-file",
            str(output_path),
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--approval-text-file",
        type=Path,
        help="File containing the exact owner approval phrase.",
    )
    input_group.add_argument(
        "--from-stdin",
        action="store_true",
        help="Read approval text from stdin.",
    )
    parser.add_argument("--approval-phrase-path", type=Path, default=DEFAULT_APPROVAL_PATH)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument(
        "--require-mapping-ready",
        action="store_true",
        help=(
            "Require --mapping to be populated and strict-valid except for the expected "
            "pending owner-approval boolean before recording standalone approval evidence. "
            "Use this for the manual two-step launch route; the one-shot helper records "
            "approval while generating the mapping."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = record_approval(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("LINE31 owner approval evidence recorded")
        print(result["approval_evidence_path"])
        print(f"sha256={result['approval_evidence_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
