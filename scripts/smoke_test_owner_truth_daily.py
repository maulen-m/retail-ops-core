#!/usr/bin/env python3
"""Cold-start smoke and idempotence harness for owner-truth daily strict runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOLATILE_KEYS = {"generated_at", "duration_sec", "started_at", "finished_at"}


def normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_payload(inner)
            for key, inner in sorted(value.items())
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [normalize_payload(item) for item in value]
    return value


def _run_owner_truth_daily(*, project_root: Path, as_of: str, strict: bool) -> dict[str, Any]:
    cmd = [str(project_root / ".venv" / "bin" / "python"), "scripts/run_owner_truth_daily.py", "--as-of", as_of]
    if strict:
        cmd.append("--strict")
    proc = subprocess.run(
        cmd,
        cwd=str(project_root),
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    return {
        "rc": int(proc.returncode),
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "cmd": " ".join(cmd),
    }


def _target_files(project_root: Path, as_of: str) -> list[Path]:
    return [
        project_root / "exports" / "daily" / as_of / "owner_truth_summary.json",
        project_root / "exports" / "daily" / as_of / "owner_truth_summary.md",
        project_root / "exports" / "daily" / as_of / "daily_ops_report.json",
        project_root / "exports" / "daily" / as_of / "daily_ops_report.md",
        project_root / "exports" / "exceptions" / as_of / "exceptions.json",
        project_root / "exports" / "exceptions" / as_of / "exceptions.md",
        project_root / "exports" / "exceptions" / as_of / "exceptions_triage.json",
        project_root / "exports" / "exceptions" / as_of / "exceptions_triage.md",
        project_root / "exports" / "validation" / "owner_truth_daily" / as_of / "full_run_transcript.md",
        project_root / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json",
        project_root / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json",
        project_root / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json",
        project_root / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.md",
        project_root / "config" / "business_insides" / "snapshots" / f"BUSINESS_INSIDES_{as_of}.json",
        project_root / "config" / "business_insides" / "snapshots" / f"BUSINESS_INSIDES_{as_of}.md",
    ]


def _purge_for_cold_start(project_root: Path, as_of: str) -> list[str]:
    removed: list[str] = []
    for path in _target_files(project_root, as_of):
        if path.exists():
            path.unlink()
            removed.append(str(path.relative_to(project_root)))
    return removed


def _json_artifact_paths(project_root: Path, as_of: str) -> dict[str, Path]:
    return {
        "owner_truth_summary": project_root / "exports" / "daily" / as_of / "owner_truth_summary.json",
        "daily_ops_report": project_root / "exports" / "daily" / as_of / "daily_ops_report.json",
        "exceptions": project_root / "exports" / "exceptions" / as_of / "exceptions.json",
        "publication_readiness": project_root / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json",
        "owner_pnl": project_root / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json",
    }


def _load_normalized_jsons(project_root: Path, as_of: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for name, path in _json_artifact_paths(project_root, as_of).items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        normalized[name] = normalize_payload(payload)
    return normalized


def _write_run_md(path: Path, *, run_no: int, as_of: str, result: dict[str, Any], removed: list[str]) -> None:
    cmd = str(result.get("cmd") or "")
    lines = [
        f"# Cold Start Smoke Run {run_no}",
        "",
        f"- as_of: `{as_of}`",
        f"- rc: `{result['rc']}`",
        f"- command: `{cmd}`",
        "",
        "## Cold-start cleanup",
        "",
    ]
    if removed:
        lines.extend([f"- `{item}`" for item in removed])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Stdout",
            "",
            "```text",
            str(result.get("stdout", "")),
            "```",
            "",
            "## Stderr",
            "",
            "```text",
            str(result.get("stderr", "")),
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_smoke_test(*, project_root: Path, as_of: str, strict: bool) -> dict[str, Any]:
    root = project_root.resolve()
    release_root = root / "exports" / "validation" / "owner_truth_release" / as_of
    release_root.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    run_md_paths: list[Path] = []
    for run_no in (1, 2):
        removed = _purge_for_cold_start(root, as_of)
        result = _run_owner_truth_daily(project_root=root, as_of=as_of, strict=strict)
        run_md_path = release_root / f"cold_start_smoke_run_{run_no}.md"
        _write_run_md(run_md_path, run_no=run_no, as_of=as_of, result=result, removed=removed)
        run_md_paths.append(run_md_path)
        run_record = {
            "run": run_no,
            "rc": result["rc"],
            "cmd": str(result.get("cmd") or ""),
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "removed": removed,
            "run_md": str(run_md_path),
        }
        runs.append(run_record)
        if result["rc"] == 0:
            snapshots.append(_load_normalized_jsons(root, as_of))
        else:
            snapshots.append({})

    diffs: list[dict[str, Any]] = []
    if len(snapshots) == 2 and snapshots[0] and snapshots[1]:
        all_keys = sorted(set(snapshots[0]) | set(snapshots[1]))
        for key in all_keys:
            if snapshots[0].get(key) != snapshots[1].get(key):
                diffs.append(
                    {
                        "artifact": key,
                        "run_1": snapshots[0].get(key),
                        "run_2": snapshots[1].get(key),
                    }
                )

    ok = all(run["rc"] == 0 for run in runs) and not diffs
    idempotence_report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "volatile_keys": sorted(VOLATILE_KEYS),
        "compared_artifacts": sorted(_json_artifact_paths(root, as_of).keys()),
        "runs": [
            {
                "run": run["run"],
                "rc": run["rc"],
                "run_md": run["run_md"],
            }
            for run in runs
        ],
        "diffs": diffs,
    }
    idempotence_path = release_root / "idempotence_report.json"
    idempotence_path.write_text(json.dumps(idempotence_report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "exit_code": 0 if (ok or not strict) else 1,
        "runs": runs,
        "idempotence": idempotence_report,
        "idempotence_path": str(idempotence_path),
        "run_paths": [str(path) for path in run_md_paths],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run cold-start owner-truth daily smoke + idempotence check")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_smoke_test(project_root=args.project_root, as_of=args.as_of, strict=bool(args.strict))
    print(f"cold_start_smoke_run_1={report['run_paths'][0]}")
    print(f"cold_start_smoke_run_2={report['run_paths'][1]}")
    print(f"idempotence_report_json={report['idempotence_path']}")
    print(f"status={report['status']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
