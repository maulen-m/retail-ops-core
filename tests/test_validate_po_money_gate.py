from __future__ import annotations

from pathlib import Path

from scripts.validate_po_money_gate import GateCheck, run_po_money_gate, summarize_gate_checks


def _runner_factory(rc_by_script: dict[str, int]):
    def _runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        script_name = Path(cmd[1]).name
        rc = int(rc_by_script.get(script_name, 0))
        stdout = f"{script_name} rc={rc}"
        stderr = "" if rc == 0 else f"{script_name} failed"
        return rc, stdout, stderr

    return _runner


def test_summarize_gate_checks_blocks_on_required_failure() -> None:
    checks = [
        GateCheck(name="anchor_health", required=True, command="check_anchor_health.py", ok=True, exit_code=0),
        GateCheck(name="offer_linkage", required=False, command="validate_offer_linkage.py", ok=False, exit_code=1),
        GateCheck(name="single_truth_system", required=True, command="validate_single_truth_system.py", ok=False, exit_code=1),
    ]
    report = summarize_gate_checks(checks)
    assert report["ok"] is False
    assert report["required_failed"] == ["single_truth_system"]
    assert report["optional_failed"] == ["offer_linkage"]


def test_run_po_money_gate_offer_linkage_non_blocking_by_default(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "config" / "anchors").mkdir(parents=True)
    workbook = project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
    workbook.write_bytes(b"fake")

    runner = _runner_factory({"validate_offer_linkage.py": 1})
    report = run_po_money_gate(
        project_root=project_root,
        db_path=project_root / "db" / "app.db",
        require_offer_linkage_strict=False,
        command_runner=runner,
    )
    assert report["ok"] is True
    assert report["optional_failed"] == ["offer_linkage"]
    assert report["required_failed"] == []


def test_run_po_money_gate_offer_linkage_blocks_when_strict(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "config" / "anchors").mkdir(parents=True)
    workbook = project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
    workbook.write_bytes(b"fake")

    runner = _runner_factory({"validate_offer_linkage.py": 1})
    report = run_po_money_gate(
        project_root=project_root,
        db_path=project_root / "db" / "app.db",
        require_offer_linkage_strict=True,
        command_runner=runner,
    )
    assert report["ok"] is False
    assert "offer_linkage" in report["required_failed"]


def test_run_po_money_gate_passes_copied_temp_contract_flags(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "config" / "anchors").mkdir(parents=True)
    workbook = project_root / "config" / "anchors" / "INBOUND_CALENDAR_LATEST.xlsx"
    workbook.write_bytes(b"fake")
    scope_contract = tmp_path / "po_scope.tsv"
    unit_cogs = tmp_path / "unit_cogs.csv"
    dashboard = tmp_path / "dashboard.json"
    system_dashboard = tmp_path / "system_dashboard.json"
    seen: list[list[str]] = []

    def runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        seen.append(cmd)
        return 0, "", ""

    report = run_po_money_gate(
        project_root=project_root,
        db_path=project_root / "db" / "app.db",
        allow_accepted_shortages_for_copied_temp=True,
        po_part_scope_contract=scope_contract,
        unit_cogs_evidence_csv=unit_cogs,
        single_truth_system_dashboard=system_dashboard,
        single_truth_alignment_input=dashboard,
        command_runner=runner,
    )

    assert report["ok"] is True
    commands = [" ".join(cmd) for cmd in seen]
    assert any("--allow-accepted-shortages-for-copied-temp" in cmd for cmd in commands)
    assert any("--po-part-scope-contract" in cmd and str(scope_contract) in cmd for cmd in commands)
    assert any("--unit-cogs-evidence-csv" in cmd and str(unit_cogs) in cmd for cmd in commands)
    assert any("--dashboard" in cmd and str(system_dashboard) in cmd for cmd in commands)
    assert any("--input" in cmd and str(dashboard) in cmd for cmd in commands)
