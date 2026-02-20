from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from scripts.build_ops_drift_pack import build_ops_drift_pack


def test_build_ops_drift_pack_delegates_to_single_truth_pack_builder(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _fake_builder(**kwargs):
        called.update(kwargs)
        out_dir = tmp_path / "exports" / "validation" / kwargs["as_of"]
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "single_truth_drift_pack.json"
        markdown_path = out_dir / "single_truth_drift_pack.md"
        json_path.write_text("{}", encoding="utf-8")
        markdown_path.write_text("# stub", encoding="utf-8")
        return {"json_path": str(json_path), "markdown_path": str(markdown_path)}

    monkeypatch.setattr("scripts.build_ops_drift_pack.build_single_truth_drift_pack", _fake_builder)

    result = build_ops_drift_pack(
        db_path=tmp_path / "app.db",
        as_of="2026-02-20",
        output_root=tmp_path / "exports" / "validation",
        max_lag_days=2,
    )

    assert called["as_of"] == "2026-02-20"
    assert called["max_lag_days"] == 2
    assert result["json_path"].endswith("/2026-02-20/single_truth_drift_pack.json")
    assert result["markdown_path"].endswith("/2026-02-20/single_truth_drift_pack.md")


def test_build_ops_drift_pack_cli_runs_from_external_cwd_without_module_error(tmp_path: Path) -> None:
    script = Path("scripts/build_ops_drift_pack.py").resolve()
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--as-of",
            "2026-02-20",
            "--output-root",
            str(tmp_path / "exports" / "validation"),
            "--db",
            str(tmp_path / "app.db"),
        ],
        cwd=str(outside_cwd),
        text=True,
        capture_output=True,
        check=False,
    )

    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode != 127
    assert completed.returncode != 2
    assert "ModuleNotFoundError" not in output
