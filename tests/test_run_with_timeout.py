from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "run_with_timeout.py"


def test_run_with_timeout_completes_before_deadline():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--timeout",
            "5",
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 0
    assert "ok" in proc.stdout


def test_run_with_timeout_kills_slow_command():
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--timeout",
            "1",
            "--",
            sys.executable,
            "-u",
            "-c",
            "import time; print('start'); time.sleep(5)",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 124
    assert "start" in proc.stdout
    assert "exceeded timeout" in proc.stderr.lower()
