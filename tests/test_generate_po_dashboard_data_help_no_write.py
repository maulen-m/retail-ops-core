from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/generate_po_dashboard_data.py")
MONITORED_PATHS = [
    Path("exports/po_dashboard_data.json"),
    Path("exports/demand_diagnostics.csv"),
    Path("exports/stock_rebuild_diagnostics.csv"),
    Path("exports/po_supplier_export"),
    Path("exports/po_supplier_summary"),
]


def _file_state(path: Path) -> tuple[str, int, int, str] | None:
    if not path.exists():
        return None
    if path.is_dir():
        rows: list[str] = []
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(path).as_posix()
            rows.append(f"{rel}:{child.stat().st_size}:{hashlib.sha256(child.read_bytes()).hexdigest()}")
        digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
        stat = path.stat()
        return ("dir", stat.st_mtime_ns, len(rows), digest)
    stat = path.stat()
    return ("file", stat.st_mtime_ns, stat.st_size, hashlib.sha256(path.read_bytes()).hexdigest())


def _snapshot() -> dict[str, tuple[str, int, int, str] | None]:
    return {str(path): _file_state(path) for path in MONITORED_PATHS}


def test_generate_po_dashboard_data_help_is_no_write() -> None:
    before = _snapshot()
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    after = _snapshot()

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "usage:" in completed.stdout
    assert "--db" in completed.stdout
    assert "--output" in completed.stdout
    assert "--plan0-anchor-message-date" in completed.stdout
    assert "Generated:" not in completed.stdout
    assert after == before
