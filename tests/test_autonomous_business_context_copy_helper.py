from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


MODULE_PATH = Path("Oracle_listings/skills/autonomous-business-context-copy/scripts/build_context_copy.py")


def load_module():
    spec = importlib.util.spec_from_file_location("ab_context_copy_helper", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_output_dir_reuses_prefix_and_replaces_timestamp() -> None:
    mod = load_module()
    reference_dir = Path(
        "/tmp/web_ui_files/web_ui_files_20260304_144114"
    )
    out_dir = mod.build_output_dir(
        reference_dir=reference_dir,
        timestamp=mod.dt.datetime(2026, 3, 13, 23, 37, 33),
    )
    assert out_dir == Path(
        "/tmp/web_ui_files/web_ui_files_20260313_233733"
    )


def test_updated_name_uses_original_basename() -> None:
    mod = load_module()
    rel = Path("context_top20_md_20260220/files/.claude/DECISIONS.md")
    assert mod.updated_name(rel) == "DECISIONS.md"


def test_generated_context_rel_detects_top_context_folders() -> None:
    mod = load_module()
    assert mod.is_generated_context_rel(Path("context_top20_md_20260220/files/docs/DAILY_SOP.md"))
    assert mod.is_generated_context_rel(Path("context_top17_md_20260314_001500/files/docs/DAILY_SOP.md"))
    assert not mod.is_generated_context_rel(Path("append/DAILY_SOP.md"))


def test_find_previous_snapshot_chooses_latest_older_sibling(tmp_path: Path) -> None:
    mod = load_module()
    parent = tmp_path / "web_ui_files"
    parent.mkdir()
    (parent / "web_ui_files_20260220_011435").mkdir()
    expected = parent / "web_ui_files_20260304_144114"
    expected.mkdir()
    current = parent / "web_ui_files_20260313_233733"
    current.mkdir()

    previous = mod.find_previous_snapshot(current)

    assert previous == expected


def test_git_value_supports_multiple_rev_parse_args(tmp_path: Path) -> None:
    mod = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()

    import subprocess

    subprocess.run(["git", "-C", str(repo), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)

    branch = mod.git_value(repo, "--abbrev-ref", "HEAD")
    assert branch in {"master", "main", "UNKNOWN"}


def test_write_updated_delta_creates_flat_files_and_report(tmp_path: Path) -> None:
    mod = load_module()
    base_dir = tmp_path / "web_ui_files_20260304_144114"
    cur_dir = tmp_path / "web_ui_files_20260313_233733"
    base_dir.mkdir()
    cur_dir.mkdir()
    (base_dir / "append").mkdir()
    (cur_dir / "append").mkdir()
    (base_dir / "append" / "DECISIONS.md").write_text("old", encoding="utf-8")
    (cur_dir / "append" / "DECISIONS.md").write_text("new", encoding="utf-8")

    report = mod.write_updated_delta(
        current_dir=cur_dir,
        previous_dir=base_dir,
    )

    updated_dir = cur_dir / "Updated"
    assert report["changed_count"] == 1
    assert (updated_dir / "DECISIONS.md").read_text(encoding="utf-8") == "new"
    assert json.loads((updated_dir / "UPDATED_REPORT.json").read_text(encoding="utf-8"))[
        "changed_count"
    ] == 1


def test_write_updated_delta_deduplicates_same_basename_when_contents_match(tmp_path: Path) -> None:
    mod = load_module()
    base_dir = tmp_path / "web_ui_files_20260304_144114"
    cur_dir = tmp_path / "web_ui_files_20260313_233733"
    (base_dir / "append").mkdir(parents=True)
    (base_dir / "swap").mkdir(parents=True)
    (cur_dir / "append").mkdir(parents=True)
    (cur_dir / "swap").mkdir(parents=True)
    (base_dir / "append" / "DAILY_SOP.md").write_text("old-a", encoding="utf-8")
    (base_dir / "swap" / "DAILY_SOP.md").write_text("old-b", encoding="utf-8")
    (cur_dir / "append" / "DAILY_SOP.md").write_text("new-same", encoding="utf-8")
    (cur_dir / "swap" / "DAILY_SOP.md").write_text("new-same", encoding="utf-8")

    report = mod.write_updated_delta(current_dir=cur_dir, previous_dir=base_dir)

    updated_dir = cur_dir / "Updated"
    assert report["changed_count"] == 2
    assert report["materialized_file_count"] == 1
    assert (updated_dir / "DAILY_SOP.md").read_text(encoding="utf-8") == "new-same"


def test_write_updated_delta_fails_when_same_basename_has_different_contents(tmp_path: Path) -> None:
    mod = load_module()
    base_dir = tmp_path / "web_ui_files_20260304_144114"
    cur_dir = tmp_path / "web_ui_files_20260313_233733"
    (base_dir / "append").mkdir(parents=True)
    (base_dir / "swap").mkdir(parents=True)
    (cur_dir / "append").mkdir(parents=True)
    (cur_dir / "swap").mkdir(parents=True)
    (base_dir / "append" / "DAILY_SOP.md").write_text("old-a", encoding="utf-8")
    (base_dir / "swap" / "DAILY_SOP.md").write_text("old-b", encoding="utf-8")
    (cur_dir / "append" / "DAILY_SOP.md").write_text("new-a", encoding="utf-8")
    (cur_dir / "swap" / "DAILY_SOP.md").write_text("new-b", encoding="utf-8")

    try:
        mod.write_updated_delta(current_dir=cur_dir, previous_dir=base_dir)
        raised = False
    except ValueError as exc:
        raised = True
        assert "basename collision" in str(exc)
    assert raised


def test_open_in_finder_invokes_open(monkeypatch, tmp_path: Path) -> None:
    mod = load_module()
    calls = []

    def fake_run(cmd, check):  # noqa: ANN001
        calls.append((cmd, check))

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.open_in_finder(tmp_path)

    assert calls == [(["open", str(tmp_path)], True)]


def test_end_to_end_copy_uses_report_mappings_and_creates_updated(tmp_path: Path) -> None:
    mod = load_module()
    mod.CANONICAL_OUTPUT_ROOT = tmp_path
    mod.TOP17_CONTEXT_REPO_RELS = ("docs/alpha.md", ".claude/DECISIONS.md")
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "alpha.md").write_text("current-alpha", encoding="utf-8")
    (repo_root / ".claude").mkdir()
    (repo_root / ".claude" / "DECISIONS.md").write_text("current-decisions", encoding="utf-8")

    parent = tmp_path / "stack"
    reference_dir = parent / "web_ui_files_20260304_144114"
    reference_dir.mkdir(parents=True)
    previous_dir = parent / "web_ui_files_20260220_011435"
    previous_dir.mkdir()
    (previous_dir / "append").mkdir()
    (previous_dir / "append" / "DECISIONS.md").write_text("old-decisions", encoding="utf-8")
    (previous_dir / "leave").mkdir()
    (previous_dir / "leave" / "alpha.md").write_text("current-alpha", encoding="utf-8")

    report = {
        "timestamp": "20260304_144114",
        "repo_root": str(repo_root),
        "template_dir": str(previous_dir),
        "output_dir": str(reference_dir),
        "copied_count": 2,
        "skipped_count": 0,
        "copied": [
            {"rel": "append/DECISIONS.md", "repo_rel": ".claude/DECISIONS.md", "bytes": 0},
            {"rel": "leave/alpha.md", "repo_rel": "docs/alpha.md", "bytes": 0},
            {
                "rel": "context_top20_md_20260220/files/docs/old.md",
                "repo_rel": "docs/alpha.md",
                "bytes": 0,
            },
        ],
        "skipped": [],
    }
    (reference_dir / "COPY_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    out_dir = mod.run_copy(
        repo_root=repo_root,
        reference_dir=reference_dir,
        timestamp=mod.dt.datetime(2026, 3, 13, 23, 37, 33),
        open_finder_flag=False,
    )

    assert (out_dir / "append" / "DECISIONS.md").read_text(encoding="utf-8") == "current-decisions"
    assert (out_dir / "leave" / "alpha.md").read_text(encoding="utf-8") == "current-alpha"
    assert (out_dir / "Updated" / "DECISIONS.md").exists()
    assert not (out_dir / "context_top20_md_20260220").exists()
    top17_dir = out_dir / "context_top17_md_20260313_233733"
    assert (top17_dir / "alpha.md").read_text(encoding="utf-8") == "current-alpha"
    assert (top17_dir / "DECISIONS.md").read_text(encoding="utf-8") == "current-decisions"
    report_out = json.loads((out_dir / "COPY_REPORT.json").read_text(encoding="utf-8"))
    assert report_out["context_top17"]["file_count"] == 2
    assert report_out["source_branch"] in {"master", "main", "UNKNOWN"}
