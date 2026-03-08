from __future__ import annotations

from pathlib import Path

from scripts.check_release_hygiene import check_release_hygiene


def test_release_hygiene_passes_for_repo_relative_docs_and_generic_scripts(tmp_path: Path) -> None:
    docs = [
        tmp_path / "docs" / "validation" / "OWNER_PNL_PUBLICATION_CONTRACT.md",
        tmp_path / "docs" / "validation" / "WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md",
    ]
    scripts = [
        tmp_path / "scripts" / "run_owner_truth_daily.py",
        tmp_path / "scripts" / "generate_ops_selection_artifacts.py",
    ]
    for path in docs + scripts:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("repo-relative only\n", encoding="utf-8")

    report = check_release_hygiene(
        project_root=tmp_path,
        active_docs=[Path("docs/validation/OWNER_PNL_PUBLICATION_CONTRACT.md"), Path("docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md")],
        active_scripts=[Path("scripts/run_owner_truth_daily.py"), Path("scripts/generate_ops_selection_artifacts.py")],
    )

    assert report["status"] == "PASS"
    assert report["errors"] == []


def test_release_hygiene_flags_absolute_paths_and_closeout_dates(tmp_path: Path) -> None:
    doc_path = tmp_path / "docs" / "DAILY_SOP.md"
    script_path = tmp_path / "scripts" / "run_owner_truth_daily.py"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("~/Docs/Autonomous_business\n", encoding="utf-8")
    script_path.write_text("AS_OF = '2026-03-08'\n", encoding="utf-8")

    report = check_release_hygiene(
        project_root=tmp_path,
        active_docs=[Path("docs/DAILY_SOP.md")],
        active_scripts=[Path("scripts/run_owner_truth_daily.py")],
    )

    assert report["status"] == "FAIL"
    assert any("Autonomous_business" in err for err in report["errors"])
    assert any("2026-03-08" in err for err in report["errors"])


def test_release_hygiene_catches_scheduler_absolute_repo_path(tmp_path: Path) -> None:
    scheduler_path = tmp_path / "scripts" / "run_kaspi_import_scheduler.py"
    scheduler_path.parent.mkdir(parents=True, exist_ok=True)
    scheduler_path.write_text(
        'PROJECT_ROOT = Path("~/Docs/Autonomous_business")\n',
        encoding="utf-8",
    )

    report = check_release_hygiene(
        project_root=tmp_path,
        active_docs=[],
        active_scripts=[Path("scripts/run_kaspi_import_scheduler.py")],
    )

    assert report["status"] == "FAIL"
    assert report["errors"] == [
        "scripts/run_kaspi_import_scheduler.py: banned token `~/Docs/Autonomous_business`"
    ]
