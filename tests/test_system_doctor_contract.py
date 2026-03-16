from __future__ import annotations

import json
from pathlib import Path

from scripts.system_doctor import run_system_doctor


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
    assert "validate_ops_selection_parity.py" in joined
    assert "validate_scheduler_heartbeat.py" in joined
    assert "validate_kaspi_archive_pack_integrity.py --source ui" in joined
    assert "validate_sales_truth_external_reference.py" in joined
    assert "validate_sales_truth_ocean_drop_parity.py" in joined
    assert "validate_sales_engine_self_sufficient.py" in joined
    assert "build_sales_truth_drift_report.py" in joined
    assert "build_owner_pnl_report.py" in joined
    assert "triage_owner_truth_stoplines.py" in joined
    assert "triage_exceptions.py" in joined


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


def test_system_doctor_defaults_ops_selection_overflow_to_five(tmp_path: Path) -> None:
    calls: list[str] = []

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


def test_system_doctor_uses_publication_fallback_validation_dir_for_triage(tmp_path: Path) -> None:
    calls: list[str] = []

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
