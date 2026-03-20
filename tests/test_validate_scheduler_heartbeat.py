from __future__ import annotations

from datetime import datetime
from pathlib import Path
import plistlib

import pytest

from scripts.validate_scheduler_heartbeat import validate_scheduler_heartbeat


def _write_import_plist(path: Path) -> None:
    payload = {
        "Label": "com.example.kaspi-import-v2",
        "StartCalendarInterval": [{"Hour": 11, "Minute": 0}, {"Hour": 16, "Minute": 3}],
    }
    path.write_bytes(plistlib.dumps(payload))


def _write_single_plist(path: Path, label: str, hour: int, minute: int) -> None:
    payload = {
        "Label": label,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
    }
    path.write_bytes(plistlib.dumps(payload))


def _write_docs(path: Path) -> None:
    path.write_text("11:00\n16:03\n18:30\n19:10\n", encoding="utf-8")


def test_scheduler_heartbeat_pass(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    import_plist = tmp_path / "import.plist"
    waybill_plist = tmp_path / "waybill.plist"
    report_plist = tmp_path / "report.plist"
    _write_import_plist(import_plist)
    _write_single_plist(waybill_plist, "com.example.kaspi-waybill-deadline", 18, 30)
    _write_single_plist(report_plist, "com.example.kaspi-daily-ops-report", 19, 10)

    import_log = tmp_path / "import.log"
    import_log.write_text(
        f"Time: {as_of} 11:01:10\n"
        f"Time: {as_of} 16:04:00\n",
        encoding="utf-8",
    )
    waybill_log = tmp_path / "waybill.log"
    waybill_log.write_text(f"Time: {as_of} 18:30:21\n", encoding="utf-8")
    report_log = tmp_path / "report.log"
    report_log.write_text("", encoding="utf-8")

    contract_doc = tmp_path / "contract.md"
    daily_sop_doc = tmp_path / "daily_sop.md"
    _write_docs(contract_doc)
    _write_docs(daily_sop_doc)

    report = validate_scheduler_heartbeat(
        as_of=as_of,
        output_root=tmp_path / "out",
        import_plist=import_plist,
        waybill_plist=waybill_plist,
        report_plist=report_plist,
        import_log=import_log,
        waybill_log=waybill_log,
        report_log=report_log,
        contract_doc=contract_doc,
        daily_sop_doc=daily_sop_doc,
        tolerance_minutes=10,
        require_report_job=False,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["ok"] is True


def test_scheduler_heartbeat_fails_on_import_schedule_drift(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    import_plist = tmp_path / "import.plist"
    # Drifted second slot minute.
    payload = {
        "Label": "com.example.kaspi-import-v2",
        "StartCalendarInterval": [{"Hour": 11, "Minute": 0}, {"Hour": 16, "Minute": 5}],
    }
    import_plist.write_bytes(plistlib.dumps(payload))
    waybill_plist = tmp_path / "waybill.plist"
    report_plist = tmp_path / "report.plist"
    _write_single_plist(waybill_plist, "com.example.kaspi-waybill-deadline", 18, 30)
    _write_single_plist(report_plist, "com.example.kaspi-daily-ops-report", 19, 10)

    import_log = tmp_path / "import.log"
    import_log.write_text(f"Time: {as_of} 11:00:00\nTime: {as_of} 16:03:00\n", encoding="utf-8")
    waybill_log = tmp_path / "waybill.log"
    waybill_log.write_text(f"Time: {as_of} 18:30:00\n", encoding="utf-8")
    report_log = tmp_path / "report.log"
    report_log.write_text("", encoding="utf-8")
    contract_doc = tmp_path / "contract.md"
    daily_sop_doc = tmp_path / "daily_sop.md"
    _write_docs(contract_doc)
    _write_docs(daily_sop_doc)

    with pytest.raises(RuntimeError, match="scheduler heartbeat validation failed"):
        validate_scheduler_heartbeat(
            as_of=as_of,
            output_root=tmp_path / "out",
            import_plist=import_plist,
            waybill_plist=waybill_plist,
            report_plist=report_plist,
            import_log=import_log,
            waybill_log=waybill_log,
            report_log=report_log,
            contract_doc=contract_doc,
            daily_sop_doc=daily_sop_doc,
            tolerance_minutes=10,
            require_report_job=False,
            strict=True,
        )


def test_scheduler_heartbeat_allows_not_due_slots_for_current_day(tmp_path: Path) -> None:
    as_of = "2026-03-04"
    import_plist = tmp_path / "import.plist"
    waybill_plist = tmp_path / "waybill.plist"
    report_plist = tmp_path / "report.plist"
    _write_import_plist(import_plist)
    _write_single_plist(waybill_plist, "com.example.kaspi-waybill-deadline", 18, 30)
    _write_single_plist(report_plist, "com.example.kaspi-daily-ops-report", 19, 10)

    import_log = tmp_path / "import.log"
    import_log.write_text(
        f"Time: {as_of} 11:01:10\n"
        f"Time: {as_of} 16:04:00\n",
        encoding="utf-8",
    )
    # No waybill/report heartbeat yet for this day.
    waybill_log = tmp_path / "waybill.log"
    waybill_log.write_text("", encoding="utf-8")
    report_log = tmp_path / "report.log"
    report_log.write_text("", encoding="utf-8")

    contract_doc = tmp_path / "contract.md"
    daily_sop_doc = tmp_path / "daily_sop.md"
    _write_docs(contract_doc)
    _write_docs(daily_sop_doc)

    report = validate_scheduler_heartbeat(
        as_of=as_of,
        output_root=tmp_path / "out",
        import_plist=import_plist,
        waybill_plist=waybill_plist,
        report_plist=report_plist,
        import_log=import_log,
        waybill_log=waybill_log,
        report_log=report_log,
        contract_doc=contract_doc,
        daily_sop_doc=daily_sop_doc,
        tolerance_minutes=10,
        require_report_job=False,
        strict=True,
        now_dt=datetime(2026, 3, 4, 17, 0, 0),
    )
    assert report["status"] == "PASS"


def test_scheduler_heartbeat_accepts_archive_fallback_when_due(tmp_path: Path) -> None:
    as_of = "2026-03-04"
    import_plist = tmp_path / "import.plist"
    waybill_plist = tmp_path / "waybill.plist"
    report_plist = tmp_path / "report.plist"
    _write_import_plist(import_plist)
    _write_single_plist(waybill_plist, "com.example.kaspi-waybill-deadline", 18, 30)
    _write_single_plist(report_plist, "com.example.kaspi-daily-ops-report", 19, 10)

    import_log = tmp_path / "import.log"
    import_log.write_text(
        f"Time: {as_of} 11:01:10\n"
        f"Time: {as_of} 16:04:00\n",
        encoding="utf-8",
    )
    waybill_log = tmp_path / "waybill.log"
    waybill_log.write_text("", encoding="utf-8")
    report_log = tmp_path / "report.log"
    report_log.write_text("", encoding="utf-8")

    archive_root = tmp_path / "Archive"
    input_dir = archive_root / f"input_{as_of}_190001"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "archive_manifest.json").write_text('{"selected_count": 1}', encoding="utf-8")

    contract_doc = tmp_path / "contract.md"
    daily_sop_doc = tmp_path / "daily_sop.md"
    _write_docs(contract_doc)
    _write_docs(daily_sop_doc)

    report = validate_scheduler_heartbeat(
        as_of=as_of,
        output_root=tmp_path / "out",
        import_plist=import_plist,
        waybill_plist=waybill_plist,
        report_plist=report_plist,
        import_log=import_log,
        waybill_log=waybill_log,
        report_log=report_log,
        contract_doc=contract_doc,
        daily_sop_doc=daily_sop_doc,
        tolerance_minutes=10,
        require_report_job=False,
        strict=True,
        now_dt=datetime(2026, 3, 4, 18, 45, 0),
        waybill_archive_root=archive_root,
    )
    assert report["status"] == "PASS"
