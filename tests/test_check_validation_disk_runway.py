from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/check_validation_disk_runway.py")


def test_check_validation_disk_runway_passes_with_zero_threshold() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--min-free-gib", "0", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["status"] == "PASS"
    assert payload["min_free_gib"] == 0.0


def test_check_validation_disk_runway_fails_with_impossibly_high_threshold() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--min-free-gib", "999999", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "FAIL_LOW_DISK_RUNWAY"
    assert payload["free_bytes"] < payload["min_free_bytes"]


def test_check_validation_disk_runway_human_output() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--min-free-gib", "0"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "VALIDATION_DISK_RUNWAY PASS" in completed.stdout
    assert "free_gib=" in completed.stdout


def test_check_validation_disk_runway_missing_path_fails(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(missing), "--min-free-gib", "0", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["path_exists"] is False
    assert payload["status"] == "FAIL_RUNWAY_PATH_MISSING"
