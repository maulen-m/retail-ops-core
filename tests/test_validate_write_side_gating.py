from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/validate_write_side_gating.py")
MANIFEST = Path("config/write_side_gating_manifest.yaml")


def test_validate_write_side_gating_script_and_manifest_exist() -> None:
    assert SCRIPT.exists(), "missing scripts/validate_write_side_gating.py"
    assert MANIFEST.exists(), "missing config/write_side_gating_manifest.yaml"


def test_validate_write_side_gating_passes_on_repo_manifest() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(MANIFEST)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_validate_write_side_gating_fails_if_manifest_entry_is_missing_apply(tmp_path: Path) -> None:
    script_path = tmp_path / "write_script.py"
    script_path.write_text(
        "import os\n"
        "if os.getenv('ENABLE_X') != '1':\n"
        "    raise SystemExit(1)\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "scripts:\n"
        f"  - path: {script_path}\n"
        "    env_gate: ENABLE_X\n"
        "    apply_flag: --apply\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "--apply" in (completed.stdout + completed.stderr)
