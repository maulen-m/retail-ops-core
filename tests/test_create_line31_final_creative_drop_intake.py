from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.validate_line31_final_creative_mapping import required_owner_approval_phrase


def test_create_line31_final_creative_drop_intake(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/create_line31_final_creative_drop_intake.py",
            "--output-root",
            str(tmp_path),
            "--run-id",
            "test",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    intake_dir = Path(payload["intake_dir"])
    asset_dir = Path(payload["asset_dir"])
    approval_text_file = Path(payload["approval_text_file"])
    checklist_path = Path(payload["checklist_path"])

    assert intake_dir == tmp_path / "line31_final_creative_drop_intake_test"
    assert asset_dir.is_dir()
    assert approval_text_file.is_file()
    assert checklist_path.is_file()
    assert (intake_dir / "README.md").is_file()
    assert (intake_dir / "line31_final_creative_drop_intake_manifest.json").is_file()
    assert payload["publish_authority_granted"] is False
    assert payload["no_external_writes_performed"] is True
    assert payload["commands_contain_placeholders"] is True
    assert payload["replace_placeholders_before_launch"] is True
    assert "--asset-dir" in payload["mapping_only_command"]
    assert "--approval-text-file" in payload["one_shot_command"]
    assert "--tracking-qa-evidence-file" in payload["mapping_only_command"]
    assert "--tracking-qa-evidence-file" in payload["one_shot_command"]
    assert "validate_line31_final_creative_drop_intake.py" in payload["drop_validator_command"]
    assert "REPLACE_WITH_FINAL_VIDEO" in payload["drop_validator_command"]
    assert (
        "python3 scripts/validate_line31_owner_objective_source_freshness.py --json"
        in payload["final_check_commands"]
    )
    assert "python3 scripts/validate_params.py --strict" not in payload[
        "final_check_commands"
    ]
    assert "python3 scripts/validate_params.py --strict" in payload[
        "advisory_repo_health_commands"
    ]

    readme = (intake_dir / "README.md").read_text(encoding="utf-8")
    assert "Replace Before Running" in readme
    assert "Do not run" in readme
    assert "strict validators reject placeholder/demo URLs" in readme
    assert "--tracking-qa-evidence-file" in readme
    assert "validate_line31_owner_objective_source_freshness.py --json" in readme
    assert "Launch-Blocking Final Checks" in readme
    assert "Advisory Repo Health Checks" in readme
    assert "scope=line31_launch_blocking" in readme
    assert "FINAL_CREATIVE_DROP_CHECKLIST.json" in readme
    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
    assert checklist["gate"] == "PENDING_FINAL_CREATIVE_ASSETS"
    assert checklist["required_asset_files"]["video"]["count"] == "exactly_one"
    assert "assets[0].video_sha256" in checklist["required_mapping_fields"]
    assert "tracking_redirect_qa.evidence_sha256" in checklist["required_mapping_fields"]
    assert checklist["safety_boundaries"]["publishes_meta"] is False
    assert checklist["approval_policy"]["standalone_approval_requires_mapping_ready"] is True
    assert checklist["approval_policy"]["strict_publish_requires_tracking_redirect_qa"] is True
    phrase = required_owner_approval_phrase(
        Path(
            "exports/validation/line31_goal_stock_dashboard_repair_20260601_133438/"
            "final_creative_publish_intake_and_approval.md"
        )
    )
    assert phrase not in approval_text_file.read_text(encoding="utf-8")


def test_create_line31_final_creative_drop_intake_refuses_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    base_command = [
        sys.executable,
        "scripts/create_line31_final_creative_drop_intake.py",
        "--output-root",
        str(tmp_path),
        "--run-id",
        "dupe",
        "--json",
    ]
    first = subprocess.run(base_command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr

    second = subprocess.run(base_command, capture_output=True, text=True, check=False)
    assert second.returncode == 2
    assert "pass --overwrite" in second.stderr
