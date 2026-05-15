import hashlib
import json
import zipfile
from pathlib import Path

from scripts.validate_agent750_review_pack import (
    REQUIRED_PROMPT_TERMS,
    UPLOAD_ZIP_NAMES,
    current_answer_readme_pointer_terms,
    current_status_pointer_terms,
    load_status_pointer_terms,
    validate_pack,
)


def write_valid_answer_readme(pack: Path, prompt_sha: str) -> None:
    (pack / "Answer" / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md").write_text(
        "\n".join(
            [
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
                prompt_sha,
                *current_answer_readme_pointer_terms(),
            ]
        ),
        encoding="utf-8",
    )


def complete_send_readme(pack: Path, prompt_sha: str) -> None:
    readme = pack / "00_SEND_TO_CODECAPTAIN_FIRST.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n"
        + "\n".join([prompt_sha, *current_status_pointer_terms()])
        + "\n",
        encoding="utf-8",
    )


def make_pack(root: Path) -> Path:
    pack = root / "review"
    answer = pack / "Answer"
    answer.mkdir(parents=True)
    (answer / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md").write_text("save answer here\n", encoding="utf-8")
    (pack / "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md").write_text(
        "\n".join(["# Review", *REQUIRED_PROMPT_TERMS]),
        encoding="utf-8",
    )
    (pack / "00_SEND_TO_CODECAPTAIN_FIRST.md").write_text(
        "\n".join(
            [
                "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md",
                "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv",
                "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE",
                "YELLOW_FIX_BEFORE_VALIDATE_ONLY_WAVE",
                "RED_DO_NOT_LAUNCH_VALIDATE_ONLY_WAVE",
                "YELLOW/non-RED answer is not launch authority",
                "scripts/validate_agent750_review_pack.py",
            ]
        ),
        encoding="utf-8",
    )
    (pack / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv").write_text(
        "pack_id,store_code,order_id,status_internal,net_rev_kzt,row_fingerprint\n"
        "p,ACMEWEAR,1,DELIVERED,100,abc\n",
        encoding="utf-8",
    )
    return pack


def write_upload_zip_and_manifest(pack: Path, *, stale_prompt: bool = False) -> Path:
    zip_path = pack.with_name(f"{pack.name}_UPLOAD_ONLY.zip")
    manifest_path = pack.with_name(f"{pack.name}_UPLOAD_ONLY_MANIFEST.md")
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name in UPLOAD_ZIP_NAMES:
            if stale_prompt and name.endswith("validate-only-plan-review.md"):
                archive.writestr(name, "stale prompt\n")
            else:
                archive.writestr(name, (pack / name).read_bytes())
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_size = zip_path.stat().st_size
    manifest_path.write_text(
        "\n".join(
            [
                "# Agent750 Upload ZIP Manifest",
                "",
                "Status: `OPTIONAL_UPLOAD_ARTIFACT`",
                "",
                f"`{pack}/`",
                "",
                f"`{zip_path}`",
                "",
                f"`{zip_sha}`",
                "",
                f"`{zip_size}` bytes",
                "",
                "Included files:",
                *(f"- `{name}`" for name in UPLOAD_ZIP_NAMES),
                "",
                "Excluded on purpose:",
                "",
                "- `Answer/`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return zip_path


def test_validate_pack_accepts_complete_waiting_review_pack(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)

    result = validate_pack(pack)

    assert result["ok"] is True
    assert result["answer_state"] == "waiting_for_codecaptain_answer"
    assert result["prompt"]["sha256"]
    assert result["send_readme"]["sha256"]
    assert result["answer_readme"]["sha256"]
    assert result["answer_readme_pointer_terms"] == current_answer_readme_pointer_terms()
    assert result["archive_csv"]["row_count"] == 1
    assert result["archive_csv"]["required_columns_present"] is True
    assert result["optional_upload_zip"]["status"] == "not_present"


def test_validate_pack_accepts_optional_upload_zip_when_it_matches_sources(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    zip_path = write_upload_zip_and_manifest(pack)

    result = validate_pack(pack)

    assert result["ok"] is True
    assert result["optional_upload_zip"]["status"] == "present"
    assert result["optional_upload_zip"]["path"] == str(zip_path)
    assert result["optional_upload_zip"]["sha256"] == hashlib.sha256(
        zip_path.read_bytes()
    ).hexdigest()
    assert result["optional_upload_zip"]["entries"] == UPLOAD_ZIP_NAMES
    assert result["optional_upload_zip"]["entry_order_matches"] is True
    assert result["optional_upload_zip"]["source_bytes_match"] is True
    assert result["optional_upload_zip"]["manifest_missing_required_terms"] == []


def test_validate_pack_rejects_optional_upload_zip_that_drifts_from_sources(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    write_upload_zip_and_manifest(pack, stale_prompt=True)

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "optional_upload_zip_source_mismatch" in result["errors"]
    assert result["optional_upload_zip"]["source_mismatched_entries"] == [
        "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md"
    ]


def test_validate_pack_rejects_missing_decision_token(tmp_path):
    pack = make_pack(tmp_path)
    prompt = pack / "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md"
    prompt.write_text("Agent751 Agent752 Agent753\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "prompt_missing_required_terms" in result["errors"]


def test_validate_pack_rejects_stale_non_red_launch_authority(tmp_path):
    pack = make_pack(tmp_path)
    prompt = pack / "224907_TASK-000_codecaptain-agent750-validate-only-plan-review.md"
    prompt.write_text(
        "\n".join(
            [
                *REQUIRED_PROMPT_TERMS,
                "If CodeCaptain returns non-RED, launch Agent751.",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "prompt_contains_stale_non_red_launch_authority" in result["errors"]
    assert result["prompt"]["forbidden_prompt_phrases"] == [
        "If CodeCaptain returns non-RED"
    ]


def test_validate_pack_rejects_bad_csv_header(tmp_path):
    pack = make_pack(tmp_path)
    (pack / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "archive_csv_missing_required_columns" in result["errors"]


def test_validate_pack_rejects_missing_or_stale_send_readme(tmp_path):
    pack = make_pack(tmp_path)
    (pack / "00_SEND_TO_CODECAPTAIN_FIRST.md").write_text("stale\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "send_readme_missing_required_terms" in result["errors"]
    assert "GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE" in result[
        "send_readme"
    ]["missing_required_terms"]


def test_validate_pack_rejects_unexpected_top_level_files(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    (pack / ".DS_Store").write_text("metadata\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "unexpected_top_level_pack_files" in result["errors"]
    assert result["top_level"]["unexpected_entries"] == [".DS_Store"]


def test_validate_pack_rejects_unexpected_answer_dir_files(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    (pack / "Answer" / "notes.txt").write_text("not an answer\n", encoding="utf-8")

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "unexpected_answer_dir_files" in result["errors"]
    assert result["answer_dir_info"]["unexpected_entries"] == ["notes.txt"]


def test_validate_pack_rejects_multiple_codecaptain_answers(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    (pack / "Answer" / "Code_Captain_answer.md").write_text(
        "Gate: GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE\n",
        encoding="utf-8",
    )
    (pack / "Answer" / "CodeCaptain_second.md").write_text(
        "Gate: GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE\n",
        encoding="utf-8",
    )

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "multiple_codecaptain_answer_files_found" in result["errors"]
    assert result["answer_dir_info"]["answer_count"] == 2


def test_validate_pack_rejects_stale_answer_readme(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)

    result = validate_pack(pack)

    assert result["ok"] is False
    assert "answer_readme_missing_required_terms" in result["errors"]
    assert "check_agent750_launch_readiness.py" in result["answer_readme"][
        "missing_required_terms"
    ]


def test_validate_pack_rejects_missing_status_completion_audit_pointer(tmp_path):
    pack = make_pack(tmp_path)
    status_path = tmp_path / "current_status.json"
    latest_audit = "/tmp/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_CURRENT.md"
    status_path.write_text(
        json.dumps({"latest_completion_audit": latest_audit}),
        encoding="utf-8",
    )
    prompt_sha = validate_pack(pack, status_path=status_path)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)

    result = validate_pack(pack, status_path=status_path)

    assert result["ok"] is False
    assert result["status_pointer_terms"] == [latest_audit]
    assert "send_readme_missing_required_terms" in result["errors"]
    assert "answer_readme_missing_required_terms" in result["errors"]
    assert latest_audit in result["send_readme"]["missing_required_terms"]
    assert latest_audit in result["answer_readme"]["missing_required_terms"]


def test_validate_pack_rejects_missing_answer_readme_stopline_triage_pointer(tmp_path):
    pack = make_pack(tmp_path)
    status_path = tmp_path / "current_status.json"
    latest_audit = "/tmp/ACTIVE_OBJECTIVE_COMPLETION_AUDIT_CURRENT.md"
    latest_triage = "/tmp/STOPLINE_TRIAGE_NEXT_BEST_STEP_AGENT750_CURRENT.md"
    status_path.write_text(
        json.dumps(
            {
                "latest_completion_audit": latest_audit,
                "latest_stopline_triage": latest_triage,
            }
        ),
        encoding="utf-8",
    )
    prompt_sha = validate_pack(pack, status_path=status_path)["prompt"]["sha256"]
    send_readme = pack / "00_SEND_TO_CODECAPTAIN_FIRST.md"
    send_readme.write_text(
        send_readme.read_text(encoding="utf-8") + f"\n{prompt_sha}\n{latest_audit}\n",
        encoding="utf-8",
    )
    write_valid_answer_readme(pack, prompt_sha)
    answer_readme = pack / "Answer" / "README_SAVE_CODECAPTAIN_ANSWER_HERE.md"
    answer_readme.write_text(
        answer_readme.read_text(encoding="utf-8").replace(latest_triage, ""),
        encoding="utf-8",
    )

    result = validate_pack(pack, status_path=status_path)

    assert result["ok"] is False
    assert result["status_pointer_terms"] == [latest_audit]
    assert result["answer_readme_pointer_terms"] == [latest_audit, latest_triage]
    assert result["answer_readme_pointer_error"] is None
    assert "send_readme_missing_required_terms" not in result["errors"]
    assert "answer_readme_missing_required_terms" in result["errors"]
    assert latest_triage in result["answer_readme"]["missing_required_terms"]


def test_validate_pack_rejects_unavailable_status_pointer_source(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    missing_status = tmp_path / "missing_status.json"

    result = validate_pack(pack, status_path=missing_status)

    assert result["ok"] is False
    assert "status_pointer_terms_unavailable" in result["errors"]
    assert result["status_pointer_source"] == str(missing_status)
    assert result["status_pointer_terms"] == []
    assert result["status_pointer_error"] == "status_path_missing"


def test_validate_pack_rejects_malformed_status_pointer_source(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    malformed_status = tmp_path / "malformed_status.json"
    malformed_status.write_text("{not-json", encoding="utf-8")

    result = validate_pack(pack, status_path=malformed_status)

    assert result["ok"] is False
    assert "status_pointer_terms_unavailable" in result["errors"]
    assert result["status_pointer_source"] == str(malformed_status)
    assert result["status_pointer_terms"] == []
    assert result["status_pointer_error"] == "status_json_invalid"


def test_status_pointer_loader_reports_missing_completion_audit(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text(json.dumps({"status": "WAITING"}), encoding="utf-8")

    terms, error = load_status_pointer_terms(status_path)

    assert terms == []
    assert error == "latest_completion_audit_missing"


def test_status_pointer_loader_reports_json_not_object(tmp_path):
    status_path = tmp_path / "current_status.json"
    status_path.write_text("[]", encoding="utf-8")

    terms, error = load_status_pointer_terms(status_path)

    assert terms == []
    assert error == "status_json_not_object"


def test_validate_pack_detects_existing_answer(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    (pack / "Answer" / "Code_Captain_answer.md").write_text(
        "Gate: GREEN_TO_LAUNCH_AGENT751_752_753_VALIDATE_ONLY_WAVE\n",
        encoding="utf-8",
    )

    result = validate_pack(pack)

    assert result["ok"] is True
    assert result["answer_state"] == "codecaptain_answer_present"
    assert result["answer_files"] == [str(pack / "Answer" / "Code_Captain_answer.md")]


def test_validate_pack_can_write_manifest_when_requested(tmp_path):
    pack = make_pack(tmp_path)
    prompt_sha = validate_pack(pack)["prompt"]["sha256"]
    complete_send_readme(pack, prompt_sha)
    write_valid_answer_readme(pack, prompt_sha)
    out = tmp_path / "manifest.json"

    result = validate_pack(pack, manifest_out=out)

    assert result["ok"] is True
    assert out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["ok"] is True
