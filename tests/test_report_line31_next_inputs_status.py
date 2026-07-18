from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.report_line31_next_inputs_status import build_status


def _write_status(
    path: Path,
    asset_dir: Path,
    approval_file: Path,
    *,
    multi_manifest: Path | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T21:30:00+05:00",
                "status": "GREEN_EXCEPT_CREATIVE",
                "strict_gate": "YELLOW",
                "ready_to_publish": False,
                "latest_drop_intake": {
                    "asset_dir": str(asset_dir),
                    "approval_text_file": str(approval_file),
                    "checklist_path": str(asset_dir.parent / "FINAL_CREATIVE_DROP_CHECKLIST.json"),
                    "one_shot_command": "python3 scripts/prepare_line31_launch_readiness_from_assets.py --json",
                },
                "latest_final_creative_assets": {
                    "exists": bool(multi_manifest),
                    "dir": str(multi_manifest.parent if multi_manifest else ""),
                    "manifest": str(multi_manifest or ""),
                    "assets_count": 3 if multi_manifest else 0,
                },
            }
        ),
        encoding="utf-8",
    )


def _make_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    asset_dir = tmp_path / "drop" / "final_assets"
    asset_dir.mkdir(parents=True)
    approval_file = tmp_path / "drop" / "approval" / "approval.txt"
    approval_file.parent.mkdir(parents=True)
    approval_file.write_text(
        "Paste the exact LINE31 owner Meta publish approval phrase here only after mapping.\n",
        encoding="utf-8",
    )
    status_path = tmp_path / "status.json"
    _write_status(status_path, asset_dir, approval_file)
    answer_dir = tmp_path / "Answer"
    answer_dir.mkdir()
    return status_path, answer_dir, asset_dir, approval_file


def _write_integration_markers(tmp_path: Path) -> tuple[Path, Path]:
    addendum = tmp_path / "LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md"
    addendum.write_text(
        "YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA\n",
        encoding="utf-8",
    )
    next_inputs = tmp_path / "LINE31_NEXT_INPUTS_AND_READY_TO_RUN.md"
    next_inputs.write_text(
        "\n".join(
            [
                "Expert answer file:",
                "LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md",
            ]
        ),
        encoding="utf-8",
    )
    return addendum, next_inputs


def test_next_inputs_waiting_when_no_answer_or_assets(tmp_path: Path) -> None:
    status_path, answer_dir, _, _ = _make_layout(tmp_path)

    payload = build_status(
        status_path=status_path,
        expert_answer_dir=answer_dir,
        post_expert_addendum_path=tmp_path / "missing_addendum.md",
        next_inputs_doc_path=tmp_path / "missing_next_inputs.md",
    )

    assert payload["ok"] is True
    assert payload["gate"] == "WAITING_FOR_EXPERT_ANSWER_OR_FINAL_CREATIVE"
    assert payload["expert_answer_file_count"] == 0
    assert payload["video_count"] == 0
    assert payload["thumbnail_count"] == 0


def test_next_inputs_ready_to_ingest_answer_when_answer_present(tmp_path: Path) -> None:
    status_path, answer_dir, _, _ = _make_layout(tmp_path)
    (answer_dir / "expert_answer.md").write_text("answer", encoding="utf-8")

    payload = build_status(
        status_path=status_path,
        expert_answer_dir=answer_dir,
        post_expert_addendum_path=tmp_path / "missing_addendum.md",
        next_inputs_doc_path=tmp_path / "missing_next_inputs.md",
    )

    assert payload["gate"] == "READY_TO_INGEST_EXPERT_ANSWER"
    assert payload["expert_answer_file_count"] == 1
    assert payload["expert_answer_integrated"] is False


def test_next_inputs_integrated_answer_still_not_ready_to_publish(tmp_path: Path) -> None:
    status_path, answer_dir, _, _ = _make_layout(tmp_path)
    (answer_dir / "expert_answer.md").write_text("answer", encoding="utf-8")
    addendum, next_inputs = _write_integration_markers(tmp_path)

    payload = build_status(
        status_path=status_path,
        expert_answer_dir=answer_dir,
        post_expert_addendum_path=addendum,
        next_inputs_doc_path=next_inputs,
    )

    assert payload["gate"] == "POST_EXPERT_INTEGRATED_WAITING_FOR_FINAL_CREATIVE"
    assert payload["expert_answer_file_count"] == 1
    assert payload["expert_answer_integrated"] is True
    assert payload["ready_to_publish"] is False
    assert payload["strict_gate"] == "YELLOW"
    assert (
        payload["owner_facing_publish_status"]
        == "YELLOW_STRICT_PUBLISH__PENDING_CREATIVE_APPROVAL_AND_LIVE_QA"
    )


def test_next_inputs_ready_for_urls_when_assets_present(tmp_path: Path) -> None:
    status_path, answer_dir, asset_dir, _ = _make_layout(tmp_path)
    (asset_dir / "final.mp4").write_bytes(b"video")
    (asset_dir / "thumb.png").write_bytes(b"thumb")

    payload = build_status(status_path=status_path, expert_answer_dir=answer_dir)

    assert payload["gate"] == "READY_FOR_FINAL_URLS_AND_OWNER_APPROVAL"
    assert payload["video_count"] == 1
    assert payload["thumbnail_count"] == 1


def test_next_inputs_accepts_multi_asset_manifest_as_current_creative_source(
    tmp_path: Path,
) -> None:
    status_path, answer_dir, asset_dir, approval_file = _make_layout(tmp_path)
    multi_dir = tmp_path / "line31_final_creative_assets_20260603_154442"
    video_dir = multi_dir / "source_videos"
    thumb_dir = multi_dir / "thumbnails"
    video_dir.mkdir(parents=True)
    thumb_dir.mkdir(parents=True)
    assets = []
    for creative_id in ("line31_cw_a", "line31_cw_b", "line31_cw_c"):
        video = video_dir / f"{creative_id}.mp4"
        thumb = thumb_dir / f"{creative_id}.jpg"
        video.write_bytes(b"video")
        thumb.write_bytes(b"thumb")
        assets.append(
            {
                "creative_id": creative_id,
                "local_video_path": str(video),
                "thumbnail_path": str(thumb),
            }
        )
    manifest = multi_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "gate": "LOCAL_FINAL_CREATIVE_ASSETS_STAGED_PENDING_MAPPING_TRACKING_QA_APPROVAL",
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )
    _write_status(status_path, asset_dir, approval_file, multi_manifest=manifest)

    payload = build_status(status_path=status_path, expert_answer_dir=answer_dir)

    assert payload["ok"] is True
    assert payload["gate"] == "FINAL_MULTI_CREATIVES_STAGED_PENDING_TRACKING_QA_AND_OWNER_APPROVAL"
    assert payload["asset_dir"] == str(multi_dir)
    assert payload["video_count"] == 3
    assert payload["thumbnail_count"] == 3
    assert payload["latest_multi_asset_manifest"] == str(manifest)
    assert payload["latest_multi_asset_gate"] == (
        "LOCAL_FINAL_CREATIVE_ASSETS_STAGED_PENDING_MAPPING_TRACKING_QA_APPROVAL"
    )


def test_next_inputs_ready_for_one_shot_when_assets_and_approval_present(
    tmp_path: Path,
) -> None:
    status_path, answer_dir, asset_dir, approval_file = _make_layout(tmp_path)
    (asset_dir / "final.mp4").write_bytes(b"video")
    (asset_dir / "thumb.png").write_bytes(b"thumb")
    approval_file.write_text("Exact owner phrase pasted later.\n", encoding="utf-8")

    payload = build_status(status_path=status_path, expert_answer_dir=answer_dir)

    assert payload["gate"] == "READY_FOR_ONE_SHOT_LOCAL_BRIDGE"
    assert payload["approval_text_present"] is True


def test_next_inputs_flags_ambiguous_assets(tmp_path: Path) -> None:
    status_path, answer_dir, asset_dir, _ = _make_layout(tmp_path)
    (asset_dir / "final_a.mp4").write_bytes(b"video")
    (asset_dir / "final_b.mov").write_bytes(b"video")
    (asset_dir / "thumb.png").write_bytes(b"thumb")

    payload = build_status(status_path=status_path, expert_answer_dir=answer_dir)

    assert payload["ok"] is False
    assert payload["gate"] == "AMBIGUOUS_CREATIVE_ASSETS"


def test_next_inputs_command_outputs_json() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/report_line31_next_inputs_status.py", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["current_status"].startswith("YELLOW_")
    assert payload["ready_to_publish"] is False
    assert payload["strict_gate"] == "YELLOW"
    assert payload["gate"] in {
        "WAITING_FOR_EXPERT_ANSWER_OR_FINAL_CREATIVE",
        "READY_TO_INGEST_EXPERT_ANSWER",
        "POST_EXPERT_INTEGRATED_WAITING_FOR_FINAL_CREATIVE",
        "FINAL_MULTI_CREATIVES_STAGED_PENDING_TRACKING_QA_AND_OWNER_APPROVAL",
        "READY_FOR_FINAL_URLS_AND_OWNER_APPROVAL",
        "READY_FOR_ONE_SHOT_LOCAL_BRIDGE",
    }
    assert payload["no_external_writes_performed"] is True
