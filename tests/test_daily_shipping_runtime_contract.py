from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest
import yaml

from scripts.validate_daily_shipping_runtime import (
    build_plist_payload,
    build_recovery_plist_payload,
    build_recovery_retention_plist_payload,
    load_manifest,
    render_runtime_markdown,
    validate_daily_shipping_runtime,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "config" / "daily_shipping_runtime.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_canonical_manifest_matches_repo_runtime_surfaces() -> None:
    report = validate_daily_shipping_runtime(
        manifest_path=MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        check_installed=False,
    )

    assert report["ok"] is True, report["errors"]
    assert report["active_stores"] == ["STOREB", "ACMEWEAR", "UNIVERSAL"]
    assert report["archived_stores"] == ["11KZ", "MELVIS"]
    assert report["scheduler_count"] == 10


def test_generated_markdown_is_exactly_manifest_derived() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    expected = render_runtime_markdown(manifest)
    actual = (PROJECT_ROOT / manifest["generated_doc"]).read_text(encoding="utf-8")

    assert actual == expected
    assert "09:00 to 24:00" in actual
    assert "17:00 Asia/Almaty" in actual


def test_generated_paths_use_manifest_runtime_home() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["runtime_home"] = "/opt/shipping-owner"
    publisher = next(
        item
        for item in manifest["schedulers"]
        if item["label"] == "com.example.google-ops-board-publish"
    )

    publisher_plist = build_plist_payload(manifest, publisher, PROJECT_ROOT)
    recovery_plist = build_recovery_plist_payload(manifest)

    assert publisher_plist["EnvironmentVariables"][
        "AB_GOOGLE_SERVICE_ACCOUNT_JSON"
    ].startswith("/opt/shipping-owner/")
    assert recovery_plist["ProgramArguments"][-1].startswith(
        "/opt/shipping-owner/"
    )


def test_watch_constants_are_checked_against_manifest(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["watch"]["ready_debounce_seconds"] = 61
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        check_installed=False,
        check_generated_doc=False,
    )

    assert report["ok"] is False
    assert any("READY_DEBOUNCE_SECONDS" in item for item in report["errors"])


def test_stage_timeouts_are_checked_against_manifest(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["workflow"]["stage_timeouts_seconds"]["shipping"] = 1199
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        check_installed=False,
        check_generated_doc=False,
    )

    assert report["ok"] is False
    assert "workflow stage timeout drift: STAGE_TIMEOUT_SECONDS" in report["errors"]


def test_store_roster_drift_fails_closed(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    (project / "config").mkdir(parents=True)
    manifest = load_manifest(MANIFEST_PATH)
    manifest["store_sources"] = ["config/stores.yaml"]
    manifest_path = project / "config" / "daily_shipping_runtime.json"
    _write_json(manifest_path, manifest)
    (project / "config" / "stores.yaml").write_text(
        yaml.safe_dump(
            {
                "stores": {
                    "STOREB": {"active": True},
                    "ACMEWEAR": {"active": True},
                    "UNIVERSAL": {"active": False},
                    "11KZ": {"active": False, "lifecycle_status": "ARCHIVED"},
                    "MELVIS": {"active": False, "lifecycle_status": "ARCHIVED"},
                }
            }
        ),
        encoding="utf-8",
    )

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=project,
        check_installed=False,
        check_repo_plists=False,
        check_watch_constants=False,
        check_automation_scope=False,
        check_generated_doc=False,
    )

    assert report["ok"] is False
    assert any("UNIVERSAL" in item for item in report["errors"])


def test_installed_plist_with_embedded_credential_name_fails_without_value_leak(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["schedulers"] = [manifest["schedulers"][0]]
    scheduler = manifest["schedulers"][0]
    installed = tmp_path / "LaunchAgents"
    installed.mkdir()
    payload = build_plist_payload(manifest, scheduler, PROJECT_ROOT)
    payload["EnvironmentVariables"] = dict(payload.get("EnvironmentVariables") or {})
    payload["EnvironmentVariables"]["TELEGRAM_BOT_TOKEN"] = "must-not-appear"
    (installed / f"{scheduler['label']}.plist").write_bytes(plistlib.dumps(payload))
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        installed_dir=installed,
        check_installed=True,
        check_repo_plists=False,
        check_watch_constants=False,
        check_automation_scope=False,
        check_generated_doc=False,
        check_credentials=False,
    )
    serialized = json.dumps(report)

    assert report["ok"] is False
    assert "TELEGRAM_BOT_TOKEN" in serialized
    assert "must-not-appear" not in serialized


def test_installed_plist_semantic_drift_is_reported(tmp_path: Path) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["schedulers"] = [manifest["schedulers"][0]]
    scheduler = manifest["schedulers"][0]
    installed = tmp_path / "LaunchAgents"
    installed.mkdir()
    payload = build_plist_payload(manifest, scheduler, PROJECT_ROOT)
    payload["StartInterval"] = 999
    (installed / f"{scheduler['label']}.plist").write_bytes(plistlib.dumps(payload))
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        installed_dir=installed,
        check_installed=True,
        check_repo_plists=False,
        check_watch_constants=False,
        check_automation_scope=False,
        check_generated_doc=False,
        check_credentials=False,
    )

    assert report["ok"] is False
    assert any("StartInterval" in item for item in report["errors"])


def test_candidate_recovery_scheduler_cannot_be_installed_before_activation(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    installed = tmp_path / "LaunchAgents"
    installed.mkdir()
    for scheduler in manifest["schedulers"]:
        payload = build_plist_payload(manifest, scheduler, PROJECT_ROOT)
        (installed / f"{scheduler['label']}.plist").write_bytes(plistlib.dumps(payload))
    recovery = build_recovery_plist_payload(manifest)
    (installed / f"{recovery['Label']}.plist").write_bytes(plistlib.dumps(recovery))
    retention = build_recovery_retention_plist_payload(manifest)
    (installed / f"{retention['Label']}.plist").write_bytes(plistlib.dumps(retention))

    report = validate_daily_shipping_runtime(
        manifest_path=MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        installed_dir=installed,
        check_installed=True,
        check_credentials=False,
    )

    assert report["ok"] is False
    assert "recovery candidate installed before canonical activation" in report["errors"]
    assert (
        "recovery retention candidate installed before canonical activation"
        in report["errors"]
    )


def test_global_installed_scan_catches_credentials_outside_shipping_cluster(
    tmp_path: Path,
) -> None:
    manifest = load_manifest(MANIFEST_PATH)
    manifest["schedulers"] = [manifest["schedulers"][0]]
    scheduler = manifest["schedulers"][0]
    installed = tmp_path / "LaunchAgents"
    installed.mkdir()
    expected = build_plist_payload(manifest, scheduler, PROJECT_ROOT)
    (installed / f"{scheduler['label']}.plist").write_bytes(plistlib.dumps(expected))
    unrelated = {
        "Label": "com.example.unrelated",
        "EnvironmentVariables": {"API_SECRET": "must-not-appear"},
    }
    (installed / "com.example.unrelated.plist").write_bytes(plistlib.dumps(unrelated))
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        installed_dir=installed,
        check_installed=True,
        check_repo_plists=False,
        check_watch_constants=False,
        check_automation_scope=False,
        check_generated_doc=False,
        check_credentials=False,
    )
    serialized = json.dumps(report)

    assert report["ok"] is False
    assert report["installed_plists_scanned"] == 2
    assert "com.example.unrelated" in serialized
    assert "API_SECRET" in serialized
    assert "must-not-appear" not in serialized


@pytest.mark.parametrize("mode", [0o644, 0o666])
def test_credential_file_permissions_above_0600_fail(tmp_path: Path, mode: int) -> None:
    credential = tmp_path / "service-account.json"
    credential.write_text("{}", encoding="utf-8")
    credential.chmod(mode)
    manifest = load_manifest(MANIFEST_PATH)
    manifest["credential_files"] = [
        {"path": str(credential), "required": True, "max_mode": "0600"}
    ]
    manifest_path = tmp_path / "manifest.json"
    _write_json(manifest_path, manifest)

    report = validate_daily_shipping_runtime(
        manifest_path=manifest_path,
        project_root=PROJECT_ROOT,
        check_installed=False,
        check_repo_plists=False,
        check_watch_constants=False,
        check_automation_scope=False,
        check_generated_doc=False,
        check_store_roster=False,
        check_credentials=True,
    )

    assert report["ok"] is False
    assert any("mode" in item for item in report["errors"])
