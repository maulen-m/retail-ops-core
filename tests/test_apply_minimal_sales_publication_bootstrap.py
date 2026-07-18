from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "apply_minimal_sales_publication_bootstrap.py"


def test_direct_script_help_works_outside_repo(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "minimal sales source-entry projection schema" in result.stdout
    assert "--expected-pre-sha256" in result.stdout
    assert "ENABLE_COPIED_MINIMAL_SALES_PUBLICATION_BOOTSTRAP_WRITE=1" in result.stdout
