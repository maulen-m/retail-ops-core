#!/usr/bin/env python3
"""Fail-closed disk runway guard for copied-temp validation waves."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GIB = 1024**3


def build_runway_report(path: Path, min_free_gib: float) -> dict[str, object]:
    if not path.exists():
        min_free_bytes = int(min_free_gib * GIB)
        return {
            "ok": False,
            "path": str(path),
            "path_exists": False,
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "free_gib": 0.0,
            "min_free_gib": min_free_gib,
            "min_free_bytes": min_free_bytes,
            "status": "FAIL_RUNWAY_PATH_MISSING",
        }
    usage = shutil.disk_usage(path)
    min_free_bytes = int(min_free_gib * GIB)
    ok = usage.free >= min_free_bytes
    return {
        "ok": ok,
        "path": str(path),
        "path_exists": True,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_gib": round(usage.free / GIB, 3),
        "min_free_gib": min_free_gib,
        "min_free_bytes": min_free_bytes,
        "status": "PASS" if ok else "FAIL_LOW_DISK_RUNWAY",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check free disk before copied-temp DB validation waves"
    )
    parser.add_argument("--path", default=str(PROJECT_ROOT))
    parser.add_argument("--min-free-gib", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.path).resolve()
    report = build_runway_report(path, args.min_free_gib)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif report["ok"]:
        print("VALIDATION_DISK_RUNWAY PASS")
        print(f"free_gib={report['free_gib']}")
        print(f"min_free_gib={report['min_free_gib']}")
    else:
        print("VALIDATION_DISK_RUNWAY FAIL_LOW_DISK_RUNWAY")
        print(f"free_gib={report['free_gib']}")
        print(f"min_free_gib={report['min_free_gib']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
