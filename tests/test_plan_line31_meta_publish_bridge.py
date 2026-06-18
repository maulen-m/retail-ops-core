from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fixture_status(tmp_path: Path) -> Path:
    mapping = _write_json(tmp_path / "mapping.json", {"status": "FINAL_CREATIVE_READY"})
    asset_manifest = _write_json(tmp_path / "asset_manifest.json", {"assets": []})
    live_qa = _write_json(tmp_path / "live_qa.json", {"gate": "GREEN"})
    phrase = tmp_path / "NEXT_META_PUBLISH_APPROVAL_PHRASE.txt"
    phrase.write_text(
        "I approve LINE31_COUNTRYWIDE_META_PUBLISH for exact fixture mapping.\n",
        encoding="utf-8",
    )
    sequence_manifest = _write_json(
        tmp_path / "sequence_manifest.json",
        {
            "gate": "GREEN_READY_FOR_EXACT_META_PUBLISH_APPROVAL_NO_META_WRITE",
            "output_mapping": str(mapping),
            "asset_manifest": str(asset_manifest),
            "live_qa": {"path": str(live_qa)},
            "mapping_validation": {
                "expected_pending_meta_approval_only": True,
            },
        },
    )
    return _write_json(
        tmp_path / "status.json",
        {
            "latest_deploy_liveqa_sequence": {
                "manifest": str(sequence_manifest),
                "next_meta_publish_approval_phrase_path": str(phrase),
            },
        },
    )


def test_bridge_writes_no_write_two_stage_publish_packet(tmp_path: Path) -> None:
    status = _fixture_status(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plan_line31_meta_publish_bridge.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "bridge_test",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE"
    assert payload["external_write_attempted"] is False
    assert payload["meta_write_attempted"] is False
    assert Path(payload["required_line31_meta_publish_phrase_copy"]).read_text(
        encoding="utf-8"
    ).startswith("I approve LINE31_COUNTRYWIDE_META_PUBLISH")
    assert "OWNER_PASTED_EXACT_LINE31_META_PUBLISH_APPROVAL.txt" in payload["owner_paste_file"]
    assert "OWNER_PASTED_EXACT_META_API_LIVE_WRITE_APPROVAL.txt" in payload[
        "meta_api_live_write_approval_file"
    ]
    assert "--execute-approved-meta-publish" in payload["commands"][
        "execute_meta_publish_after_exact_meta_api_live_write_approval"
    ]
    assert payload["commands"]["green_meta_publish_preflight_no_write"].endswith("--json")

    closeout = Path(payload["output_dir"]) / "closeout.md"
    manifest = Path(payload["output_dir"]) / "bridge_manifest.json"
    assert closeout.exists()
    assert manifest.exists()
    assert "Gate: GREEN_LINE31_META_APPROVAL_BRIDGE_READY_NO_WRITE" in closeout.read_text(
        encoding="utf-8"
    )


def test_bridge_fails_closed_without_deploy_liveqa_sequence(tmp_path: Path) -> None:
    status = _write_json(tmp_path / "status.json", {})

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plan_line31_meta_publish_bridge.py",
            "--status",
            str(status),
            "--output-root",
            str(tmp_path),
            "--run-id",
            "missing_sequence",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "latest_deploy_liveqa_sequence" in completed.stdout
    assert not (tmp_path / "line31_meta_publish_bridge_missing_sequence").exists()
