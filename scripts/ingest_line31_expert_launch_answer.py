#!/usr/bin/env python3
"""Classify the LINE31 external expert launch answer into the next safe action.

This is intentionally no-write externally. It reads the Oracle pack Answer/
folder, classifies exactly one expert answer, and writes a local evidence packet
that tells the operator whether to activate as-is, change first, or hold paused.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_ORACLE_PACK = Path(
    "~/Docs/Oracle/oracle_packs/Instagram_funnel_packs/"
    "line31_countrywide_three_day_meta_resume_truth_oracle_pack_v2_UNDER20_FLAT__20260530_GMT5"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
FINAL_START_DECISION_PREFIX = "line31_final_start_decision_packet_"
FINAL_START_DECISION_MANIFEST = "final_start_decision_manifest.json"
EXPECTED_FINAL_START_GATE = "YELLOW_LINE31_FINAL_START_DECISION_PACKET_READY_NO_WRITE"

DECISION_START_AS_IS = "START_AS_IS"
DECISION_CHANGE_BEFORE_START = "CHANGE_BEFORE_START"
DECISION_HOLD_PAUSED = "HOLD_PAUSED"
DECISION_UNCLASSIFIED = "UNCLASSIFIED"
DECISION_PENDING = "PENDING_ANSWER"

SAFE_DECISION_ALIASES = {
    "START_AFTER_CHANGES": DECISION_CHANGE_BEFORE_START,
}

ANSWER_SUFFIXES = {".md", ".markdown", ".txt"}
EXPLICIT_DECISION_RE = re.compile(
    r"(?im)^\s*(?:decision|verdict|recommendation|launch[_ -]?decision)\s*[:=-]\s*"
    r"(START_AS_IS|CHANGE_BEFORE_START|START_AFTER_CHANGES|HOLD_PAUSED)\b"
)
TOKEN_RE = re.compile(r"\b(START_AS_IS|CHANGE_BEFORE_START|START_AFTER_CHANGES|HOLD_PAUSED)\b")

PHRASE_HINTS: dict[str, tuple[str, ...]] = {
    DECISION_START_AS_IS: (
        "start as-is",
        "start as is",
        "launch as-is",
        "launch as is",
        "start now as-is",
        "approve launch as-is",
        "green to start as-is",
        "green to launch as-is",
        "ready to start as-is",
        "ready to launch as-is",
    ),
    DECISION_CHANGE_BEFORE_START: (
        "change before start",
        "change before launch",
        "changes before start",
        "changes before launch",
        "adjust before launch",
        "fix before launch",
        "start with changes",
        "start after changes",
        "launch with changes",
        "launch after changes",
        "do not start until",
        "do not launch until",
    ),
    DECISION_HOLD_PAUSED: (
        "hold paused",
        "keep paused",
        "stay paused",
        "do not start",
        "do not launch",
        "delay launch",
        "not ready to launch",
        "not ready to start",
    ),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_answer_candidate(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.startswith("."):
        return False
    if path.name.upper().startswith("README"):
        return False
    return path.suffix.lower() in ANSWER_SUFFIXES


def _answer_folder_state(answer_dir: Path) -> dict[str, Any]:
    if not answer_dir.exists():
        return {
            "ok": False,
            "error": "answer_folder_missing",
            "candidates": [],
            "unexpected_items": [],
        }
    if not answer_dir.is_dir():
        return {
            "ok": False,
            "error": "answer_path_not_directory",
            "candidates": [],
            "unexpected_items": [],
        }

    candidates: list[Path] = []
    unexpected: list[Path] = []
    for item in sorted(answer_dir.rglob("*")):
        try:
            relative_parts = item.relative_to(answer_dir).parts
        except ValueError:
            relative_parts = item.parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if not item.is_file():
            continue
        if _is_answer_candidate(item):
            candidates.append(item)
        elif not item.name.upper().startswith("README"):
            unexpected.append(item)
    return {
        "ok": True,
        "error": "",
        "candidates": candidates,
        "unexpected_items": unexpected,
    }


def _classify_answer(text: str) -> dict[str, Any]:
    explicit = EXPLICIT_DECISION_RE.findall(text)
    explicit_decisions = [SAFE_DECISION_ALIASES.get(token, token) for token in explicit]
    if len(set(explicit_decisions)) == 1:
        return {
            "decision": explicit_decisions[0],
            "confidence": "HIGH",
            "method": "explicit_decision_line",
            "matched": explicit,
        }
    if len(set(explicit_decisions)) > 1:
        return {
            "decision": DECISION_UNCLASSIFIED,
            "confidence": "LOW",
            "method": "conflicting_explicit_decision_lines",
            "matched": explicit,
        }

    tokens = TOKEN_RE.findall(text)
    token_decisions = [SAFE_DECISION_ALIASES.get(token, token) for token in tokens]
    if len(set(token_decisions)) == 1:
        return {
            "decision": token_decisions[0],
            "confidence": "HIGH",
            "method": "single_uppercase_decision_token",
            "matched": tokens,
        }
    if len(set(token_decisions)) > 1:
        return {
            "decision": DECISION_UNCLASSIFIED,
            "confidence": "LOW",
            "method": "conflicting_uppercase_decision_tokens",
            "matched": tokens,
        }

    lowered = text.lower()
    phrase_matches: dict[str, list[str]] = {}
    for decision, phrases in PHRASE_HINTS.items():
        hits = [phrase for phrase in phrases if phrase in lowered]
        if hits:
            phrase_matches[decision] = hits
    if len(phrase_matches) == 1:
        decision = next(iter(phrase_matches))
        return {
            "decision": decision,
            "confidence": "MEDIUM",
            "method": "single_phrase_family",
            "matched": phrase_matches[decision],
        }
    if len(phrase_matches) > 1:
        return {
            "decision": DECISION_UNCLASSIFIED,
            "confidence": "LOW",
            "method": "conflicting_phrase_families",
            "matched": phrase_matches,
        }

    return {
        "decision": DECISION_UNCLASSIFIED,
        "confidence": "LOW",
        "method": "no_clear_decision_found",
        "matched": [],
    }


def _latest_final_start_manifest(output_root: Path) -> Path | None:
    if not output_root.exists():
        return None
    candidates = []
    for path in output_root.glob(f"{FINAL_START_DECISION_PREFIX}*/{FINAL_START_DECISION_MANIFEST}"):
        if path.is_file():
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.parent.name)


def _final_start_packet_state(path: Path | None, output_root: Path) -> dict[str, Any]:
    manifest_path = path.expanduser().resolve() if path else _latest_final_start_manifest(output_root)
    if not manifest_path:
        return {
            "ok": False,
            "manifest_path": "",
            "gate": "",
            "checks_failed": None,
            "activation_phrase_path": "",
            "activation_command_template": "",
            "error": "final_start_decision_manifest_missing",
        }
    payload = _load_json(manifest_path)
    option = {}
    decision_options = payload.get("decision_options")
    if isinstance(decision_options, list) and decision_options:
        option = decision_options[0] if isinstance(decision_options[0], dict) else {}
    phrase_path = str(option.get("requires_exact_phrase_path") or "")
    command = str(option.get("activation_command_template") or "")
    ok = (
        payload.get("gate") == EXPECTED_FINAL_START_GATE
        and payload.get("checks_failed") == 0
        and payload.get("meta_write_attempted") is False
        and bool(phrase_path)
        and bool(command)
    )
    return {
        "ok": ok,
        "manifest_path": str(manifest_path),
        "gate": str(payload.get("gate") or ""),
        "checks_failed": payload.get("checks_failed"),
        "activation_phrase_path": phrase_path,
        "activation_command_template": command,
        "error": "" if ok else "final_start_decision_manifest_not_activation_ready",
    }


def _next_safe_action(decision: str, final_packet: dict[str, Any]) -> dict[str, Any]:
    if decision == DECISION_START_AS_IS:
        if final_packet.get("ok"):
            return {
                "action": "SAVE_EXACT_OWNER_APPROVAL_AND_ACTIVATE_ONLY_WITH_EXISTING_COMMAND",
                "activation_allowed_after_exact_owner_phrase": True,
                "activation_phrase_path": final_packet["activation_phrase_path"],
                "activation_command_template": final_packet["activation_command_template"],
                "notes": [
                    "Do not edit campaign/adset/ad fields before this activation.",
                    "Save the exact owner approval phrase first, then run the command template.",
                ],
            }
        return {
            "action": "RERUN_PREFLIGHT_BEFORE_ANY_ACTIVATION",
            "activation_allowed_after_exact_owner_phrase": False,
            "activation_phrase_path": "",
            "activation_command_template": "",
            "notes": [
                "Expert decision is start-as-is, but current activation preflight evidence is missing or stale.",
                "Rerun current Meta snapshot, activation preflight, and LINE31 current status before asking for activation.",
            ],
        }
    if decision == DECISION_CHANGE_BEFORE_START:
        return {
            "action": "DO_NOT_ACTIVATE__SCOPE_CHANGES_AND_RERUN_PREFLIGHT",
            "activation_allowed_after_exact_owner_phrase": False,
            "activation_phrase_path": "",
            "activation_command_template": "",
            "notes": [
                "Keep the campaign paused.",
                "Turn the expert changes into bounded tasks with exact approvals, then rerun read-only Meta snapshot and activation preflight.",
            ],
        }
    if decision == DECISION_HOLD_PAUSED:
        return {
            "action": "DO_NOT_ACTIVATE__KEEP_PAUSED",
            "activation_allowed_after_exact_owner_phrase": False,
            "activation_phrase_path": "",
            "activation_command_template": "",
            "notes": [
                "Keep campaign, adset, and ads paused.",
                "Use the answer as a retained blocker source for the next plan.",
            ],
        }
    if decision == DECISION_PENDING:
        return {
            "action": "WAIT_FOR_EXPERT_ANSWER",
            "activation_allowed_after_exact_owner_phrase": False,
            "activation_phrase_path": "",
            "activation_command_template": "",
            "notes": [
                "Oracle pack can be sent now; put the expert answer into the pack Answer/ folder.",
                "Rerun this intake after the answer lands.",
            ],
        }
    return {
        "action": "DO_NOT_ACTIVATE__ANSWER_NEEDS_HUMAN_REVIEW",
        "activation_allowed_after_exact_owner_phrase": False,
        "activation_phrase_path": "",
        "activation_command_template": "",
        "notes": [
            "The answer text did not contain a single clear launch decision.",
            "Ask the expert or owner to restate one of: START_AS_IS, CHANGE_BEFORE_START, HOLD_PAUSED.",
        ],
    }


def _gate_for(
    *,
    answer_state: dict[str, Any],
    decision: str,
    final_packet: dict[str, Any],
) -> str:
    if not answer_state.get("ok"):
        return "RED_LINE31_EXPERT_ANSWER_INTAKE_INPUT_MISSING_NO_WRITE"
    candidates = answer_state["candidates"]
    if len(candidates) == 0:
        return "YELLOW_LINE31_EXPERT_ANSWER_PENDING_NO_WRITE"
    if len(candidates) > 1:
        return "RED_LINE31_EXPERT_ANSWER_AMBIGUOUS_NO_WRITE"
    if decision == DECISION_START_AS_IS:
        if final_packet.get("ok"):
            return "GREEN_LINE31_EXPERT_START_AS_IS_READY_NO_WRITE"
        return "YELLOW_LINE31_EXPERT_START_AS_IS_PREFLIGHT_REFRESH_REQUIRED_NO_WRITE"
    if decision == DECISION_CHANGE_BEFORE_START:
        return "YELLOW_LINE31_EXPERT_CHANGE_BEFORE_START_NO_WRITE"
    if decision == DECISION_HOLD_PAUSED:
        return "YELLOW_LINE31_EXPERT_HOLD_PAUSED_NO_WRITE"
    return "YELLOW_LINE31_EXPERT_DECISION_UNCLASSIFIED_NO_WRITE"


def build_payload(
    *,
    oracle_pack: Path,
    output_root: Path,
    final_start_manifest: Path | None,
    generated_at: str,
) -> dict[str, Any]:
    answer_dir = oracle_pack / "Answer"
    answer_state = _answer_folder_state(answer_dir)
    candidates = answer_state["candidates"]
    unexpected = answer_state["unexpected_items"]
    answer_path = candidates[0] if len(candidates) == 1 else None
    classification = {
        "decision": DECISION_PENDING if len(candidates) == 0 else DECISION_UNCLASSIFIED,
        "confidence": "NONE" if len(candidates) == 0 else "LOW",
        "method": "answer_missing" if len(candidates) == 0 else "answer_count_not_exactly_one",
        "matched": [],
    }
    answer_text = ""
    if answer_path:
        answer_text = answer_path.read_text(encoding="utf-8", errors="replace")
        classification = _classify_answer(answer_text)

    final_packet = _final_start_packet_state(final_start_manifest, output_root)
    decision = str(classification["decision"])
    gate = _gate_for(answer_state=answer_state, decision=decision, final_packet=final_packet)
    next_action = _next_safe_action(decision, final_packet)
    return {
        "gate": gate,
        "generated_at": generated_at,
        "oracle_pack": str(oracle_pack),
        "answer_dir": str(answer_dir),
        "answer_path": str(answer_path) if answer_path else "",
        "answer_sha256": _sha256(answer_path) if answer_path else "",
        "answer_bytes": answer_path.stat().st_size if answer_path else 0,
        "answer_candidates": [str(path) for path in candidates],
        "unexpected_answer_items": [str(path) for path in unexpected],
        "decision": decision,
        "decision_confidence": classification["confidence"],
        "decision_method": classification["method"],
        "decision_matches": classification["matched"],
        "final_start_packet": final_packet,
        "next_safe_action": next_action,
        "external_write_attempted": False,
        "meta_write_attempted": False,
        "website_write_attempted": False,
        "goal_complete": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# LINE31 Expert Launch Answer Intake",
        "",
        "## State",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Confidence: `{payload['decision_confidence']}`",
        f"- Method: `{payload['decision_method']}`",
        f"- Answer path: `{payload['answer_path'] or 'not yet present'}`",
        f"- Answer SHA256: `{payload['answer_sha256'] or 'not yet present'}`",
        f"- Final start packet: `{payload['final_start_packet'].get('manifest_path') or 'missing'}`",
        "",
        "## Next Safe Action",
        "",
        f"- Action: `{payload['next_safe_action']['action']}`",
        f"- Activation allowed after exact owner phrase: `{str(payload['next_safe_action']['activation_allowed_after_exact_owner_phrase']).lower()}`",
    ]
    phrase_path = payload["next_safe_action"].get("activation_phrase_path")
    if phrase_path:
        lines.append(f"- Exact phrase path: `{phrase_path}`")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            *[f"- {note}" for note in payload["next_safe_action"].get("notes", [])],
            "",
            "## Safety",
            "",
            "- No Meta write was attempted.",
            "- No website deploy was attempted.",
            "- No Kaspi/WebUI/API, DB, workbook, scheduler, cash, stock, price, supplier, or PO action was attempted.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_next_action(path: Path, payload: dict[str, Any]) -> None:
    action = payload["next_safe_action"]
    lines = [
        f"Gate: {payload['gate']}",
        "",
        "# Next Safe Action",
        "",
        f"`{action['action']}`",
        "",
    ]
    if action.get("activation_command_template"):
        lines.extend(
            [
                "If the owner chooses to proceed, save the exact approval phrase from:",
                "",
                f"`{action['activation_phrase_path']}`",
                "",
                "Then run:",
                "",
                "```bash",
                action["activation_command_template"],
                "```",
            ]
        )
    else:
        lines.extend(action.get("notes", []))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    oracle_pack = args.oracle_pack.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    final_start_manifest = args.final_start_manifest.expanduser().resolve() if args.final_start_manifest else None
    now = datetime.now(ALMATY_TZ)
    run_id = args.run_id or f"line31_expert_launch_answer_intake_{now.strftime('%Y%m%d_%H%M%S')}"
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(
        oracle_pack=oracle_pack,
        output_root=output_root,
        final_start_manifest=final_start_manifest,
        generated_at=now.isoformat(timespec="seconds"),
    )
    manifest_path = output_dir / "expert_answer_intake_manifest.json"
    summary_path = output_dir / "expert_answer_summary.md"
    next_action_path = output_dir / "NEXT_SAFE_ACTION.md"
    payload["output_dir"] = str(output_dir)
    payload["manifest_path"] = str(manifest_path)
    payload["summary_md"] = str(summary_path)
    payload["next_safe_action_md"] = str(next_action_path)
    _write_summary(summary_path, payload)
    _write_next_action(next_action_path, payload)
    _write_json(manifest_path, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-pack", type=Path, default=DEFAULT_ORACLE_PACK)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--final-start-manifest", type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{payload['gate']} evidence={payload['output_dir']}")
    return 2 if payload["gate"].startswith("RED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
