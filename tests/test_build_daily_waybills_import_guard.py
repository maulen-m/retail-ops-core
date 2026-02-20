from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_build_daily_waybills_import_has_no_cli_side_effects() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "print('pre', flush=True)\n"
                "import scripts.build_daily_waybills  # noqa: F401\n"
                "print('post', flush=True)\n"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = completed.stdout.strip().splitlines()
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "pre" in stdout
    assert "post" in stdout, "import should not execute CLI path or terminate early"
