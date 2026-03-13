from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.system_doctor as doctor_mod
from scripts.system_doctor import _build_parser, run_system_doctor


def _seed_crm_anchor(project_root: Path) -> Path:
    anchor = project_root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text("anchor", encoding="utf-8")
    return anchor


def test_system_doctor_run_shell_uses_file_backed_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeProc:
        returncode = 0

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        stdout = kwargs["stdout"]
        stdout.write("doctor stdout\n")
        return FakeProc()

    monkeypatch.setattr(doctor_mod.subprocess, "run", fake_run)

    rc, output = doctor_mod._run_shell("python3 -V", tmp_path)

    assert rc == 0
    assert output == "doctor stdout"
    kwargs = seen["kwargs"]
    assert kwargs["capture_output"] is False
    assert kwargs["stderr"] == doctor_mod.subprocess.STDOUT
    assert kwargs["stdout"] is not None


def test_system_doctor_fails_closed_on_runtime_layer() -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        if "install_single_truth_ops_scheduler.sh" in cmd:
            return 1, "validate-only fail"
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_dir=Path("exports/diagnostics/2026-02-25"),
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is False
    assert report["blocked_layer"] == "runtime"
    assert report["exit_code"] == 1
    assert all(
        "validate_params.py --strict" not in cmd
        for cmd in calls
    ), "truth layer must not run after runtime failure"


def test_system_doctor_writes_required_artifacts(tmp_path: Path) -> None:
    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_dir=tmp_path,
        strict=True,
        runner=lambda _cmd, _cwd: (0, "ok"),
    )

    assert report["ok"] is True
    assert report["exit_code"] == 0

    system_health = tmp_path / "system_health.json"
    system_health_md = tmp_path / "system_health.md"
    system_checks = tmp_path / "system_health_checks.json"
    assert system_health.exists()
    assert system_health_md.exists()
    assert system_checks.exists()

    payload = json.loads(system_health.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["status"] == "GREEN"
    assert payload["as_of"] == "2026-02-25"


def test_system_doctor_includes_v10_contract_checks() -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_dir=Path("exports/diagnostics/2026-02-25"),
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    joined = "\n".join(calls)
    assert "validate_schema.py" in joined
    assert "validate_dashboard_plan_real_contract.py" in joined
    assert "validate_cashfloor.py" in joined
    assert "translate_transfer_ledger_to_cashflow.py" in joined
    assert "validate_exceptions_schema.py" in joined
    assert "validate_as_of_consistency.py" in joined
    assert "validate_sales_vs_waybill_parity.py" in joined
    assert "validate_shipped_truth_crm_waybill.py" in joined
    assert "validate_business_insides_shipped_truth.py" in joined
    assert "validate_business_insides_economics_ready.py" in joined
    assert "validate_ads_sidecar_readiness.py" in joined
    assert "validate_opex_readiness.py" in joined
    assert "validate_returns_economics_audit.py" in joined
    assert "validate_monthly_cash_reconciliation.py" in joined
    assert "validate_reference_freshness.py" in joined
    assert "import_web_automation_offer_identity.py" in joined
    assert "validate_external_snapshot_parity.py" in joined
    assert "validate_recent_identity_coverage.py" in joined
    assert "validate_order_entries_freshness.py" in joined
    assert "validate_scheduler_heartbeat.py" not in joined
    assert "validate_kaspi_archive_pack_integrity.py --source ui" in joined
    assert "validate_sales_truth_external_reference.py" in joined
    assert "validate_sales_truth_ocean_drop_parity.py" in joined
    assert "validate_sales_engine_self_sufficient.py" in joined
    assert "build_sales_truth_drift_report.py" in joined
    assert "build_owner_pnl_report.py" in joined
    assert "triage_owner_truth_stoplines.py" in joined
    assert "triage_exceptions.py" in joined


def test_system_doctor_uses_live_ads_readiness_mode(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    ads_cmd = next(cmd for cmd in calls if "validate_ads_sidecar_readiness.py" in cmd)
    assert "--readiness-mode live" in ads_cmd


def test_system_doctor_cli_defaults_to_webui_archive_truth_source() -> None:
    parser = _build_parser()
    args = parser.parse_args([])
    assert args.truth_source == "webui_archive"


def test_system_doctor_summary_prefers_error_code_line(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "install_single_truth_ops_scheduler.sh" in cmd:
            return 1, "status=FAIL\nerror_code=REFERENCE_STALE\nmessage=reference stale"
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is False
    first = report["checks"][0]
    assert first["summary"] == "error_code=REFERENCE_STALE"


def test_system_doctor_webui_mode_includes_webui_checks(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-06",
        output_dir=tmp_path,
        strict=True,
        runtime_mode="live",
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runner=fake_runner,
    )
    assert report["ok"] is True
    joined = "\n".join(calls)
    assert "validate_webui_archive_pack_integrity.py" in joined
    assert "validate_status_ledger_continuity.py" in joined
    assert "validate_webui_crm_shipped_day_authority.py" in joined
    assert "validate_sales_against_workbook.py" in joined
    assert "validate_order_status_audit_history.py" in joined
    assert "triage_owner_truth_stoplines.py" in joined


def test_system_doctor_webui_mode_includes_full_range_db_gate_before_owner_pnl(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runtime_mode="live",
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runner=fake_runner,
    )
    assert report["ok"] is True
    full_range_cmd = next(
        cmd
        for cmd in calls
        if "validate_webui_archive_vs_current_db.py" in cmd and "full_range_db_gate" in cmd
    )
    assert "--start 2025-06-06" in full_range_cmd
    assert "--end 2026-03-09" in full_range_cmd
    assert "--range-policy full_range_owner_truth" in full_range_cmd
    assert "--statusdate-cutover 2026-02-27" in full_range_cmd
    full_range_idx = calls.index(full_range_cmd)
    pnl_idx = next(i for i, cmd in enumerate(calls) if "build_owner_pnl_report.py" in cmd)
    assert full_range_idx < pnl_idx


def test_system_doctor_resolves_pack_root_and_external_download_run_from_full_parse_ledger(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    pack_id = "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack"
    ledger_root = tmp_path / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    ledger_root.mkdir(parents=True, exist_ok=True)
    external_root = tmp_path / "external_repo"
    external_pack_root = (
        external_root
        / "exports"
        / "webui_archive_full_parse_runs"
        / "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211"
        / "pack_outputs"
        / pack_id
    )
    external_pack_root.mkdir(parents=True, exist_ok=True)
    external_download_root = external_root / "exports" / "webui_archive_download_runs" / "webui_archive_download_20260306"
    external_download_root.mkdir(parents=True, exist_ok=True)
    (external_download_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps(
            {
                "pack_roots": [str(external_pack_root)],
                "pack_ids": [pack_id],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=tmp_path,
        as_of="2026-03-09",
        output_dir=tmp_path / "exports" / "diagnostics" / "2026-03-09",
        strict=True,
        truth_source="webui_archive",
        runner=fake_runner,
    )

    assert report["ok"] is True
    joined = "\n".join(calls)
    assert str(ledger_root) in joined
    assert str(external_pack_root) in joined
    assert str(external_download_root) in joined


def test_system_doctor_records_runtime_mode_in_report(tmp_path: Path) -> None:
    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-07",
        output_dir=tmp_path,
        strict=True,
        runtime_mode="replay",
        runner=lambda _cmd, _cwd: (0, "ok"),
    )

    assert report["ok"] is True
    assert report["runtime_mode"] == "replay"


def test_system_doctor_passes_statusdate_cutover_to_reference_freshness(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-07",
        output_dir=tmp_path,
        strict=True,
        truth_source="webui_archive",
        runner=fake_runner,
    )

    assert report["ok"] is True
    reference_cmd = next(cmd for cmd in calls if "validate_reference_freshness.py" in cmd)
    assert "--statusdate-cutover 2026-02-27" in reference_cmd


def test_system_doctor_defaults_ops_selection_overflow_to_five(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("AB_INCLUDE_OPS_SELECTION_PARITY", "1")

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-07",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    ops_cmd = next(cmd for cmd in calls if "validate_ops_selection_parity.py" in cmd)
    assert "--max-import-overflow 5" in ops_cmd


def test_system_doctor_skips_ops_selection_parity_by_default(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    assert not any("validate_ops_selection_parity.py" in cmd for cmd in calls)


def test_system_doctor_includes_ops_selection_parity_when_opted_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("AB_INCLUDE_OPS_SELECTION_PARITY", "1")

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    ops_cmd = next(cmd for cmd in calls if "validate_ops_selection_parity.py" in cmd)
    assert "--max-import-overflow 5" in ops_cmd


def test_system_doctor_skips_scheduler_heartbeat_by_default(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    assert not any("validate_scheduler_heartbeat.py" in cmd for cmd in calls)


def test_system_doctor_includes_scheduler_heartbeat_when_opted_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("AB_INCLUDE_SCHEDULER_HEARTBEAT", "1")

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-09",
        output_dir=tmp_path,
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    heartbeat_cmd = next(cmd for cmd in calls if "validate_scheduler_heartbeat.py" in cmd)
    assert "--as-of 2026-03-09" in heartbeat_cmd


def test_system_doctor_uses_publication_fallback_validation_dir_for_triage(tmp_path: Path) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    publication_dir = tmp_path / "exports" / "north_star_owner_review" / "2026-03-07"
    publication_dir.mkdir(parents=True, exist_ok=True)
    fallback_validation = tmp_path / "exports" / "validation" / "ads_scope_closeout" / "2026-03-08"
    fallback_validation.mkdir(parents=True, exist_ok=True)
    (fallback_validation / "sales_against_workbook_report.json").write_text(
        json.dumps({"status": "PASS", "ok": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (publication_dir / "publication_readiness.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ok": True,
                "truth_source": "webui_archive",
                "gates": {
                    "workbook_chronology_anchor": {
                        "status": "PASS",
                        "ok": True,
                        "path": str(fallback_validation / "sales_against_workbook_report.json"),
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = run_system_doctor(
        project_root=tmp_path,
        as_of="2026-03-07",
        output_dir=tmp_path / "exports" / "diagnostics" / "2026-03-07",
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    triage_cmd = next(cmd for cmd in calls if "triage_owner_truth_stoplines.py" in cmd)
    assert "ads_scope_closeout/2026-03-08" in triage_cmd
    assert "--allow-missing-publication-readiness" in triage_cmd


def test_system_doctor_prefixes_validate_params_with_workbook_anchor(tmp_path: Path) -> None:
    calls: list[str] = []
    anchor = _seed_crm_anchor(tmp_path)

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=tmp_path,
        as_of="2026-03-09",
        output_dir=tmp_path / "exports" / "diagnostics" / "2026-03-09",
        strict=True,
        runner=fake_runner,
    )

    assert report["ok"] is True
    validate_cmd = next(cmd for cmd in calls if "validate_params.py --strict" in cmd)
    assert "AB_CRM_WORKBOOK_PATH=" in validate_cmd
    assert str(anchor.resolve()) in validate_cmd


def test_system_doctor_fails_closed_when_workbook_anchor_missing(tmp_path: Path) -> None:
    report = run_system_doctor(
        project_root=tmp_path,
        as_of="2026-03-09",
        output_dir=tmp_path / "exports" / "diagnostics" / "2026-03-09",
        strict=True,
        runner=lambda _cmd, _cwd: (0, "ok"),
    )

    assert report["ok"] is False
    assert report["blocked_layer"] == "truth"
    assert report["checks"][0]["check"] == "workbook_anchor_required"
    assert report["checks"][0]["summary"] == "error_code=WORKBOOK_ANCHOR_REQUIRED"


def test_system_doctor_uses_frozen_ui_pack_integrity_check_in_db_mode(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-07",
        output_dir=tmp_path,
        strict=True,
        truth_source="db",
        runner=fake_runner,
    )

    assert report["ok"] is True
    ui_cmd = next(cmd for cmd in calls if "validate_kaspi_archive_pack_integrity.py --source ui" in cmd)
    assert "--as-of" not in ui_cmd


def test_system_doctor_validates_generated_daily_ops_and_exceptions_before_triage(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-03-08",
        output_dir=tmp_path,
        strict=True,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runner=fake_runner,
    )

    assert report["ok"] is True
    daily_idx = next(i for i, cmd in enumerate(calls) if "validate_daily_ops_report.py" in cmd)
    exceptions_idx = next(i for i, cmd in enumerate(calls) if "validate_exceptions_schema.py" in cmd)
    triage_idx = next(i for i, cmd in enumerate(calls) if "triage_exceptions.py" in cmd)
    assert daily_idx < exceptions_idx < triage_idx
