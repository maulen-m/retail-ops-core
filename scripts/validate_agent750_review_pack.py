#!/usr/bin/env python3
"""Validate the external CodeCaptain Agent750 review pack without side effects."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK_ROOT = Path(
    "~/Docs/Oracle/Autonomous_business/2026-05-09/"
    "224907_TASK-000_codecaptain-agent750-validate-only-plan-review"
)
DEFAULT_STATUS_PATH = (
    REPO_ROOT
    / "docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/"
    "current_gate_status_agent750_waiting_codecaptain.json"
)
PROMPT_NAME = "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md"
ARCHIVE_NAME = "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
ANSWER_DIR_NAME = "Answer"
ANSWER_README_NAME = "README_SAVE_CODECAPTAIN_ANSWER_HERE.md"
README_NAME = "00_SEND_TO_CODECAPTAIN_FIRST.md"
ALLOWED_TOP_LEVEL_NAMES = {
    PROMPT_NAME,
    ARCHIVE_NAME,
    ANSWER_DIR_NAME,
    README_NAME,
}

REQUIRED_PROMPT_TERMS = [
    "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE",
    "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE",
    "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE",
    "Agent751",
    "Agent752",
    "Agent753",
    "dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64",
    "3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c",
    "config/tmux_orchestrator_visibility_disabled.flag",
    "config/tmux_orchestrator_pings_disabled.flag",
    "tmux_visibility_kill_switch",
    "tmux_visibility_kill_switch_exists",
    "tmux_completion_ping_kill_switch",
    "tmux_completion_ping_kill_switch_exists",
    "_orchestrator_ping_skipped.json",
    "monitor-only routing",
    "full focused Agent750/751 guard suite: `122 passed`",
    "tmux-agent-orchestrator Option D suite: `22 passed`",
]
FORBIDDEN_PROMPT_PHRASES = [
    "After Agent750 and CodeCaptain non-RED review",
    "After Agent750 plus CodeCaptain non-RED review",
    "accepted as non-RED",
    "receive non-RED CodeCaptain review",
    "If CodeCaptain returns non-RED",
    "Agent750 is reviewed non-RED and the Agent750 CodeCaptain review pack is reviewed non-RED",
]
REQUIRED_ARCHIVE_COLUMNS = [
    "pack_id",
    "store_code",
    "order_id",
    "status_internal",
    "net_rev_kzt",
    "row_fingerprint",
]
UPLOAD_ZIP_NAMES = [
    README_NAME,
    PROMPT_NAME,
    ARCHIVE_NAME,
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def load_status_pointer_terms(
    status_path: Path = DEFAULT_STATUS_PATH,
) -> tuple[list[str], str | None]:
    """Return current pointer values plus a fail-closed loading error, if any."""
    path = status_path.expanduser()
    if not path.exists():
        return [], "status_path_missing"
    if not path.is_file():
        return [], "status_path_not_file"
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], "status_json_invalid"
    if not isinstance(status, dict):
        return [], "status_json_not_object"
    latest_completion_audit = status.get("latest_completion_audit")
    if not latest_completion_audit:
        return [], "latest_completion_audit_missing"
    return [str(latest_completion_audit)], None


def load_answer_readme_pointer_terms(
    status_path: Path = DEFAULT_STATUS_PATH,
) -> tuple[list[str], str | None]:
    """Return pointer values required on the mutable Answer README surface."""
    terms, error = load_status_pointer_terms(status_path)
    if error:
        return terms, error
    path = status_path.expanduser()
    status = json.loads(path.read_text(encoding="utf-8"))
    latest_stopline_triage = status.get("latest_stopline_triage")
    if not latest_stopline_triage:
        return terms, "latest_stopline_triage_missing"
    return [*terms, str(latest_stopline_triage)], None


def current_status_pointer_terms(status_path: Path = DEFAULT_STATUS_PATH) -> list[str]:
    """Return current pointer values that human pack surfaces must carry."""
    terms, _error = load_status_pointer_terms(status_path)
    return terms


def current_answer_readme_pointer_terms(status_path: Path = DEFAULT_STATUS_PATH) -> list[str]:
    """Return current pointer values that the mutable Answer README must carry."""
    terms, _error = load_answer_readme_pointer_terms(status_path)
    return terms


def _codecaptain_answer_files(answer_dir: Path) -> list[Path]:
    if not answer_dir.exists():
        return []
    return sorted(
        path
        for path in answer_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".md"
        and path.name.lower().startswith(("code_captain", "codecaptain"))
    )


def _answer_dir_info(answer_dir: Path, answer_files: list[Path], errors: list[str]) -> dict:
    info = {
        "path": str(answer_dir),
        "exists": answer_dir.exists(),
        "entries": [],
        "unexpected_entries": [],
        "answer_count": len(answer_files),
    }
    if not answer_dir.exists():
        errors.append("answer_dir_missing")
        return info
    entries = sorted(path.name for path in answer_dir.iterdir())
    allowed_names = {ANSWER_README_NAME, *(path.name for path in answer_files)}
    unexpected_entries = [name for name in entries if name not in allowed_names]
    if unexpected_entries:
        errors.append("unexpected_answer_dir_files")
    if len(answer_files) > 1:
        errors.append("multiple_codecaptain_answer_files_found")
    info.update(
        {
            "entries": entries,
            "unexpected_entries": unexpected_entries,
            "allowed_entries": sorted(allowed_names),
            "answer_count": len(answer_files),
        }
    )
    return info


def _answer_readme_info(
    answer_dir: Path,
    prompt_info: dict,
    status_pointer_terms: list[str],
    errors: list[str],
) -> dict:
    readme = answer_dir / ANSWER_README_NAME
    info = {"path": str(readme), "exists": readme.exists()}
    if not readme.exists():
        errors.append("answer_readme_missing")
        return info

    text = readme.read_text(encoding="utf-8", errors="replace")
    required_terms = [
        "Save exactly one real CodeCaptain Agent750 review answer in this folder.",
        "Code_Captain",
        "CodeCaptain",
        "ingest_agent750_codecaptain_answer.py",
        "check_agent750_launch_readiness.py",
        "report_agent750_next_action.py",
        "wait_for_agent750_codecaptain_answer.py",
        "resume_agent750_to_753.py",
        "list_agent751_753_candidate_panes.py",
        "launch_agent751_753_after_agent750.py",
        "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE",
        "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE",
        "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE",
        "line value must be exactly one token and nothing else",
        "YELLOW/non-RED answer is not launch authority",
        "monitor-only completion routing",
        "Do not add `--visibility-pane LIVE`",
        "orchestrator_ping_mode=chat",
        *status_pointer_terms,
    ]
    prompt_sha = prompt_info.get("sha256")
    if prompt_sha:
        required_terms.append(str(prompt_sha))
    missing_terms = [term for term in required_terms if term not in text]
    if missing_terms:
        errors.append("answer_readme_missing_required_terms")
    info.update(
        {
            "sha256": sha256(readme),
            "size_bytes": readme.stat().st_size,
            "line_count": line_count(readme),
            "missing_required_terms": missing_terms,
        }
    )
    return info


def _top_level_info(root: Path, errors: list[str]) -> dict:
    if not root.exists() or not root.is_dir():
        return {"path": str(root), "entries": [], "unexpected_entries": []}
    entries = sorted(path.name for path in root.iterdir())
    unexpected_entries = [name for name in entries if name not in ALLOWED_TOP_LEVEL_NAMES]
    if unexpected_entries:
        errors.append("unexpected_top_level_pack_files")
    return {
        "path": str(root),
        "entries": entries,
        "unexpected_entries": unexpected_entries,
        "allowed_entries": sorted(ALLOWED_TOP_LEVEL_NAMES),
    }


def _prompt_info(prompt: Path, errors: list[str]) -> dict:
    info = {"path": str(prompt), "exists": prompt.exists()}
    if not prompt.exists():
        errors.append("prompt_missing")
        return info
    text = prompt.read_text(encoding="utf-8", errors="replace")
    missing_terms = [term for term in REQUIRED_PROMPT_TERMS if term not in text]
    forbidden_phrases = [phrase for phrase in FORBIDDEN_PROMPT_PHRASES if phrase in text]
    if missing_terms:
        errors.append("prompt_missing_required_terms")
    if forbidden_phrases:
        errors.append("prompt_contains_stale_non_red_launch_authority")
    info.update(
        {
            "sha256": sha256(prompt),
            "size_bytes": prompt.stat().st_size,
            "line_count": line_count(prompt),
            "missing_required_terms": missing_terms,
            "forbidden_prompt_phrases": forbidden_phrases,
        }
    )
    return info


def _archive_info(archive: Path, errors: list[str]) -> dict:
    info = {"path": str(archive), "exists": archive.exists()}
    if not archive.exists():
        errors.append("archive_csv_missing")
        return info
    with archive.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        row_count = sum(1 for _ in reader)
    missing_columns = [column for column in REQUIRED_ARCHIVE_COLUMNS if column not in header]
    if missing_columns:
        errors.append("archive_csv_missing_required_columns")
    if row_count <= 0:
        errors.append("archive_csv_has_no_data_rows")
    info.update(
        {
            "sha256": sha256(archive),
            "size_bytes": archive.stat().st_size,
            "line_count": row_count + (1 if header else 0),
            "row_count": row_count,
            "header": header,
            "missing_required_columns": missing_columns,
            "required_columns_present": not missing_columns,
        }
    )
    return info


def _readme_info(
    readme: Path,
    prompt_info: dict,
    status_pointer_terms: list[str],
    errors: list[str],
) -> dict:
    info = {"path": str(readme), "exists": readme.exists()}
    if not readme.exists():
        errors.append("send_readme_missing")
        return info

    text = readme.read_text(encoding="utf-8", errors="replace")
    required_terms = [
        PROMPT_NAME,
        ARCHIVE_NAME,
        "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE",
        "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE",
        "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE",
        "YELLOW/non-RED answer is not launch authority",
        "scripts/validate_agent750_review_pack.py",
        *status_pointer_terms,
    ]
    prompt_sha = prompt_info.get("sha256")
    if prompt_sha:
        required_terms.append(str(prompt_sha))
    missing_terms = [term for term in required_terms if term not in text]
    if missing_terms:
        errors.append("send_readme_missing_required_terms")
    info.update(
        {
            "sha256": sha256(readme),
            "size_bytes": readme.stat().st_size,
            "line_count": line_count(readme),
            "missing_required_terms": missing_terms,
        }
    )
    return info


def _upload_zip_info(root: Path, errors: list[str]) -> dict:
    zip_path = root.with_name(f"{root.name}_UPLOAD_ONLY.zip")
    manifest_path = root.with_name(f"{root.name}_UPLOAD_ONLY_MANIFEST.md")
    info = {
        "path": str(zip_path),
        "manifest_path": str(manifest_path),
        "exists": zip_path.exists(),
        "manifest_exists": manifest_path.exists(),
        "status": "not_present",
    }
    if not zip_path.exists() and not manifest_path.exists():
        return info
    if not zip_path.exists():
        errors.append("optional_upload_zip_missing")
        info["status"] = "missing_zip"
        return info
    if not manifest_path.exists():
        errors.append("optional_upload_zip_manifest_missing")
        info["status"] = "missing_manifest"
        return info

    zip_sha = sha256(zip_path)
    zip_size = zip_path.stat().st_size
    mismatched_entries: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            missing_entries = [name for name in UPLOAD_ZIP_NAMES if name not in names]
            unexpected_entries = [name for name in names if name not in UPLOAD_ZIP_NAMES]
            order_matches = names == UPLOAD_ZIP_NAMES
            for name in UPLOAD_ZIP_NAMES:
                source = root / name
                if name not in names or not source.exists():
                    continue
                if archive.read(name) != source.read_bytes():
                    mismatched_entries.append(name)
    except zipfile.BadZipFile:
        errors.append("optional_upload_zip_bad_zip")
        info.update(
            {
                "status": "bad_zip",
                "sha256": zip_sha,
                "size_bytes": zip_size,
            }
        )
        return info

    manifest_text = manifest_path.read_text(encoding="utf-8", errors="replace")
    required_manifest_terms = [
        "OPTIONAL_UPLOAD_ARTIFACT",
        str(root) + "/",
        str(zip_path),
        zip_sha,
        f"`{zip_size}` bytes",
        *(f"`{name}`" for name in UPLOAD_ZIP_NAMES),
        "`Answer/`",
    ]
    missing_manifest_terms = [
        term for term in required_manifest_terms if term not in manifest_text
    ]
    if missing_entries:
        errors.append("optional_upload_zip_missing_entries")
    if unexpected_entries:
        errors.append("optional_upload_zip_unexpected_entries")
    if not order_matches:
        errors.append("optional_upload_zip_entry_order_mismatch")
    if mismatched_entries:
        errors.append("optional_upload_zip_source_mismatch")
    if missing_manifest_terms:
        errors.append("optional_upload_zip_manifest_missing_required_terms")

    info.update(
        {
            "status": "present",
            "sha256": zip_sha,
            "size_bytes": zip_size,
            "entries": names,
            "expected_entries": UPLOAD_ZIP_NAMES,
            "missing_entries": missing_entries,
            "unexpected_entries": unexpected_entries,
            "entry_order_matches": order_matches,
            "source_mismatched_entries": mismatched_entries,
            "source_bytes_match": not mismatched_entries and not missing_entries,
            "manifest_missing_required_terms": missing_manifest_terms,
        }
    )
    return info


def validate_pack(
    pack_root: Path = DEFAULT_PACK_ROOT,
    *,
    manifest_out: Path | None = None,
    status_path: Path = DEFAULT_STATUS_PATH,
) -> dict:
    root = pack_root.expanduser()
    errors: list[str] = []
    if not root.exists():
        errors.append("pack_root_missing")
    elif not root.is_dir():
        errors.append("pack_root_not_directory")

    prompt = root / PROMPT_NAME
    archive = root / ARCHIVE_NAME
    readme = root / README_NAME
    answer_dir = root / ANSWER_DIR_NAME
    answer_files = _codecaptain_answer_files(answer_dir)
    answer_state = "codecaptain_answer_present" if answer_files else "waiting_for_codecaptain_answer"
    status_pointer_terms, status_pointer_error = load_status_pointer_terms(status_path)
    answer_readme_pointer_terms, answer_readme_pointer_error = load_answer_readme_pointer_terms(
        status_path
    )
    if status_pointer_error:
        errors.append("status_pointer_terms_unavailable")
    if answer_readme_pointer_error:
        errors.append("answer_readme_pointer_terms_unavailable")

    prompt_info = _prompt_info(prompt, errors)
    payload = {
        "ok": False,
        "pack_root": str(root),
        "errors": errors,
        "top_level": _top_level_info(root, errors),
        "prompt": prompt_info,
        "archive_csv": _archive_info(archive, errors),
        "send_readme": _readme_info(readme, prompt_info, status_pointer_terms, errors),
        "optional_upload_zip": _upload_zip_info(root, errors),
        "answer_dir_info": _answer_dir_info(answer_dir, answer_files, errors),
        "answer_readme": _answer_readme_info(
            answer_dir,
            prompt_info,
            answer_readme_pointer_terms,
            errors,
        ),
        "answer_dir": str(answer_dir),
        "answer_state": answer_state,
        "answer_files": [str(path) for path in answer_files],
        "expected_answer_state_for_launch": "codecaptain_answer_present_with_green_token",
        "status_pointer_source": str(status_path.expanduser()),
        "status_pointer_terms": status_pointer_terms,
        "status_pointer_error": status_pointer_error,
        "answer_readme_pointer_terms": answer_readme_pointer_terms,
        "answer_readme_pointer_error": answer_readme_pointer_error,
        "read_only": True,
    }
    payload["ok"] = not errors

    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return payload


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate the Agent750 external CodeCaptain review pack")
    p.add_argument("--pack-root", type=Path, default=DEFAULT_PACK_ROOT)
    p.add_argument("--status-path", type=Path, default=DEFAULT_STATUS_PATH)
    p.add_argument("--manifest-out", type=Path)
    p.add_argument("--json-only", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = validate_pack(
        args.pack_root,
        manifest_out=args.manifest_out,
        status_path=args.status_path,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
