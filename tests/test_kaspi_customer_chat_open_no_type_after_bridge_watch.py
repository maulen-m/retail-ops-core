import json
from argparse import Namespace
from pathlib import Path

from scripts import run_kaspi_customer_chat_open_no_type_after_bridge_watch as watch


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _bridge_manifest(tmp_path: Path, **overrides) -> Path:
    approval = tmp_path / "packet" / "REQUIRED_EXACT_APPROVAL.txt"
    approval.parent.mkdir(parents=True, exist_ok=True)
    approval.write_text("approved\n", encoding="utf-8")
    payload = {
        "gate": watch.BRIDGE_READY_GATE,
        "approval_phrase_path": str(approval),
        "heartbeat_path": str(tmp_path / "heartbeat.json"),
        "message_sent": False,
        "message_text_typed": False,
    }
    payload.update(overrides)
    return _write_json(tmp_path / "bridge" / "manifest.json", payload)


def _workflow_manifest(tmp_path: Path) -> Path:
    payload = {
        "source_manifests": {
            "resident_heartbeat_manifest": str(tmp_path / "heartbeat.json"),
            "live_send_approval_manifest": str(tmp_path / "approval" / "manifest.json"),
            "live_send_execution_preflight_manifest": str(tmp_path / "preflight" / "manifest.json"),
        }
    }
    return _write_json(tmp_path / "workflow" / "manifest.json", payload)


def _args(tmp_path: Path, *, bridge: Path, workflow: Path) -> Namespace:
    return Namespace(
        bridge_manifest=bridge,
        source_workflow_manifest=workflow,
        output_dir=tmp_path / "out",
        live_send_approval_manifest=None,
        live_send_preflight_manifest=None,
        resident_heartbeat_manifest=None,
    )


def _patch_child_builders(monkeypatch, *, post_gate: str, workflow_rc: int = 1, dashboard_rc: int = 0):
    def fake_post_open(args):
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(args.output_dir / "manifest.json", {"gate": post_gate})
        _write_json(args.output_dir / "open_chat_no_type_result_validation.json", {"gate": post_gate})
        return {"gate": post_gate}

    def fake_workflow(argv):
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        _write_json(output_dir / "manifest.json", {"gate": "YELLOW_WORKFLOW_READY_WITH_RETAINED_BLOCKERS"})
        return workflow_rc

    def fake_dashboard(argv):
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        _write_json(output_dir / "manifest.json", {"gate": "GREEN_OWNER_DASHBOARD_READY"})
        return dashboard_rc

    monkeypatch.setattr(watch, "post_open_build_report", fake_post_open)
    monkeypatch.setattr(watch, "workflow_readiness_main", fake_workflow)
    monkeypatch.setattr(watch, "owner_dashboard_main", fake_dashboard)


def test_after_bridge_watch_green_when_bridge_and_post_open_gate_are_ready(tmp_path, monkeypatch):
    _patch_child_builders(monkeypatch, post_gate=watch.POST_OPEN_GREEN_GATE)

    report = watch.run(
        _args(
            tmp_path,
            bridge=_bridge_manifest(tmp_path),
            workflow=_workflow_manifest(tmp_path),
        )
    )

    assert report["gate"] == watch.GREEN_GATE
    assert report["customer_send_performed"] is False
    assert report["message_sent"] is False
    assert (tmp_path / "out" / "manifest.json").exists()


def test_after_bridge_watch_yellow_when_post_open_gate_is_not_green(tmp_path, monkeypatch):
    _patch_child_builders(monkeypatch, post_gate="YELLOW_OPEN_CHAT_RESULT_MISSING")

    report = watch.run(
        _args(
            tmp_path,
            bridge=_bridge_manifest(tmp_path),
            workflow=_workflow_manifest(tmp_path),
        )
    )

    assert report["gate"] == watch.YELLOW_GATE
    assert "post_open_gate_not_green:YELLOW_OPEN_CHAT_RESULT_MISSING" in report["blockers"]
    assert report["message_sent"] is False


def test_after_bridge_watch_red_when_bridge_sent_message(tmp_path, monkeypatch):
    _patch_child_builders(monkeypatch, post_gate=watch.POST_OPEN_GREEN_GATE)

    report = watch.run(
        _args(
            tmp_path,
            bridge=_bridge_manifest(tmp_path, message_sent=True),
            workflow=_workflow_manifest(tmp_path),
        )
    )

    assert report["gate"] == watch.RED_GATE
    assert "bridge_message_sent_not_false" in report["unsafe_blockers"]
