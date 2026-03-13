from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(
    "Oracle_listings/skills/autonomous-business-oracle-pack/scripts/build_oracle_pack.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("ab_oracle_pack_helper", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_dir_uses_canonical_repo_bucket() -> None:
    mod = load_module()
    out_dir = mod.build_output_dir(
        output_root=Path("/tmp/oracle-root"),
        task_id="TASK-000",
        slug="demo-pack",
        timestamp=mod.dt.datetime(2026, 3, 11, 15, 13, 45),
    )
    assert out_dir == Path(
        "/tmp/oracle-root/2026-03-11/151345_TASK-000_demo-pack"
    )


def test_select_sidecars_keeps_mandatory_csv_and_caps_at_nineteen(tmp_path: Path) -> None:
    mod = load_module()
    mandatory = tmp_path / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
    mandatory.write_text("x", encoding="utf-8")
    reports = []
    extras = []
    for idx in range(30):
        p = tmp_path / f"extra_{idx:02d}.json"
        p.write_text("{}", encoding="utf-8")
        extras.append(p)

    selected = mod.select_sidecars(
        mandatory_csv=mandatory,
        priority_reports=reports,
        sidecar_files=extras,
    )

    assert len(selected) == 19
    assert selected[0] == mandatory
    assert mandatory in selected


def test_select_sidecars_prioritizes_reports_before_other_sidecars(tmp_path: Path) -> None:
    mod = load_module()
    mandatory = tmp_path / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
    mandatory.write_text("x", encoding="utf-8")
    report_a = tmp_path / "report_a.md"
    report_b = tmp_path / "report_b.md"
    report_a.write_text("a", encoding="utf-8")
    report_b.write_text("b", encoding="utf-8")
    other = tmp_path / "zeta.json"
    other.write_text("{}", encoding="utf-8")

    selected = mod.select_sidecars(
        mandatory_csv=mandatory,
        priority_reports=[report_b, report_a],
        sidecar_files=[other],
    )

    assert selected[:4] == [mandatory, report_a, report_b, other]


def test_plan_bundle_inputs_moves_only_priority_reports_when_overflow(tmp_path: Path) -> None:
    mod = load_module()
    keep_md = tmp_path / "keep.md"
    keep_md.write_text("k", encoding="utf-8")
    report_md = tmp_path / "report.md"
    report_md.write_text("r", encoding="utf-8")

    plan = mod.plan_bundle_inputs(
        bundle_markdown=[keep_md, report_md],
        priority_report_markdown=[report_md],
        estimated_bundle_size_bytes=mod.BUNDLE_SIZE_LIMIT_BYTES + 1,
    )

    assert plan.bundle_markdown == [keep_md]
    assert plan.sidecar_reports == [report_md]


def test_plan_bundle_inputs_fails_closed_if_non_report_markdown_alone_exceeds_limit(
    tmp_path: Path,
) -> None:
    mod = load_module()
    keep_md = tmp_path / "keep.md"
    keep_md.write_text("k", encoding="utf-8")

    with pytest.raises(ValueError, match="bundle size exceeds limit"):
        mod.plan_bundle_inputs(
            bundle_markdown=[keep_md],
            priority_report_markdown=[],
            estimated_bundle_size_bytes=mod.BUNDLE_SIZE_LIMIT_BYTES + 1,
        )


def test_open_finder_on_success_invokes_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mod = load_module()
    calls = []

    def fake_run(cmd, check):  # noqa: ANN001
        calls.append((cmd, check))

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod.open_in_finder(tmp_path)

    assert calls == [(["open", str(tmp_path)], True)]


def test_canonical_output_root_is_external_oracle_dir() -> None:
    mod = load_module()
    assert mod.CANONICAL_OUTPUT_ROOT == Path("~/Docs/Oracle/Autonomous_business")


def test_parse_args_rejects_no_open_finder_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_oracle_pack.py",
            "--repo",
            ".",
            "--slug",
            "demo-pack",
            "--prompt",
            "plain prompt",
            "--bundle-file",
            "docs/README.md",
            "--no-open-finder",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.parse_args()

    assert exc.value.code == 2


def test_parse_args_rejects_output_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_oracle_pack.py",
            "--repo",
            ".",
            "--slug",
            "demo-pack",
            "--prompt",
            "plain prompt",
            "--bundle-file",
            "docs/README.md",
            "--output-root",
            "/tmp/override",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.parse_args()

    assert exc.value.code == 2
