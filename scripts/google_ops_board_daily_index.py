#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKFLOW_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "workflow_runs"
DEFAULT_HEALTH_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "health"
DEFAULT_SOURCE_SNAPSHOT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "source_snapshots"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "daily_index"
DEFAULT_KASPI_API_LEDGER_ROOT = PROJECT_ROOT / "runtime" / "api_ledger"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _target_date_text(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": int(path.stat().st_size) if path.exists() else 0,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else "",
    }


def _closeout_attempts(workflow_root: Path, target: str) -> list[dict[str, Any]]:
    day_root = Path(workflow_root) / target
    attempts: list[dict[str, Any]] = []
    for report_path in sorted(day_root.glob("*/closeout_report.json")):
        payload = _load_json(report_path)
        if not payload:
            continue
        attempts.append(
            {
                "run_id": str(payload.get("run_id") or report_path.parent.name),
                "ok": bool(payload.get("ok")),
                "failure_stage": str(payload.get("failure_stage") or ""),
                "failure_reason": str(payload.get("failure_reason") or ""),
                "started_at": str(payload.get("started_at") or ""),
                "completed_at": str(payload.get("completed_at") or ""),
                "report_path": str(report_path),
                "run_dir": str(report_path.parent),
                "mtime": report_path.stat().st_mtime,
                "steps": list(payload.get("steps") or []),
            }
        )
    attempts.sort(key=lambda item: (item["mtime"], item["run_id"]))
    return attempts


def _stage_durations(attempt: dict[str, Any] | None) -> dict[str, float]:
    if not attempt:
        return {}
    durations: dict[str, float] = {}
    for step in attempt.get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name") or "")
        if not name:
            continue
        try:
            durations[name] = float(step.get("duration_sec") or 0)
        except (TypeError, ValueError):
            durations[name] = 0.0
    return durations


def _latest_health(health_root: Path, target: str) -> dict[str, Any]:
    day_root = Path(health_root) / target
    reports = [_artifact(path) for path in sorted(day_root.glob("*.json"))]
    latest = max(reports, key=lambda item: item["mtime"], default=None)
    return {
        "latest_report_path": latest["path"] if latest else "",
        "reports": reports,
    }


def _source_snapshot(source_snapshot_root: Path, target: str) -> dict[str, Any]:
    path = Path(source_snapshot_root) / target / "source_snapshot.json"
    payload = _load_json(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "payload": payload,
    }


def _api_call_counts(target: str, ledger_root: Path = DEFAULT_KASPI_API_LEDGER_ROOT) -> dict[str, Any]:
    path = Path(ledger_root) / f"kaspi_api_{target}.jsonl"
    counts: Counter[str] = Counter()
    total = 0
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            total += 1
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                counts["parse_error"] += 1
                continue
            counts[str(row.get("store_code") or "unknown")] += 1
    return {
        "ledger_path": str(path),
        "total": total,
        "by_store": dict(sorted(counts.items())),
    }


def build_daily_index(
    *,
    target_date: str | date,
    workflow_root: Path = DEFAULT_WORKFLOW_ROOT,
    health_root: Path = DEFAULT_HEALTH_ROOT,
    source_snapshot_root: Path = DEFAULT_SOURCE_SNAPSHOT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    target = _target_date_text(target_date)
    attempts = _closeout_attempts(Path(workflow_root), target)
    failures = Counter(
        str(attempt.get("failure_stage") or "unknown")
        for attempt in attempts
        if not attempt.get("ok")
    )
    latest_success = next((attempt for attempt in reversed(attempts) if attempt.get("ok")), None)
    latest_attempt = attempts[-1] if attempts else None
    delivery_report_path = Path(str((latest_success or latest_attempt or {}).get("run_dir") or "")) / "delivery_send_report.json"
    delivery_report = _load_json(delivery_report_path)
    return {
        "target_date": target,
        "generated_at": datetime.now().isoformat(),
        "output_root": str(output_root),
        "closeout": {
            "attempt_count": len(attempts),
            "failure_counts_by_stage": dict(sorted(failures.items())),
            "latest_attempt_run_id": str((latest_attempt or {}).get("run_id") or ""),
            "latest_success_run_id": str((latest_success or {}).get("run_id") or ""),
            "stage_durations_sec": _stage_durations(latest_success or latest_attempt),
            "attempts": [
                {
                    key: value
                    for key, value in attempt.items()
                    if key not in {"steps", "mtime"}
                }
                for attempt in attempts
            ],
        },
        "delivery": {
            "channel": str(delivery_report.get("delivery_channel") or delivery_report.get("channel") or ""),
            "ok": bool(delivery_report.get("ok")),
            "report_path": str(delivery_report_path) if delivery_report_path.name else "",
            "state": delivery_report.get("delivery_completion") or {},
        },
        "health": _latest_health(Path(health_root), target),
        "source_snapshot": _source_snapshot(Path(source_snapshot_root), target),
        "api_call_counts": _api_call_counts(target),
    }


def write_daily_index(
    *,
    target_date: str | date,
    workflow_root: Path = DEFAULT_WORKFLOW_ROOT,
    health_root: Path = DEFAULT_HEALTH_ROOT,
    source_snapshot_root: Path = DEFAULT_SOURCE_SNAPSHOT_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    target = _target_date_text(target_date)
    path = Path(output_root) / f"{target}.json"
    index = build_daily_index(
        target_date=target,
        workflow_root=workflow_root,
        health_root=health_root,
        source_snapshot_root=source_snapshot_root,
        output_root=output_root,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a compact daily index for Google Ops Board automation artifacts.")
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--workflow-root", type=Path, default=DEFAULT_WORKFLOW_ROOT)
    parser.add_argument("--health-root", type=Path, default=DEFAULT_HEALTH_ROOT)
    parser.add_argument("--source-snapshot-root", type=Path, default=DEFAULT_SOURCE_SNAPSHOT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    path = write_daily_index(
        target_date=args.target_date,
        workflow_root=args.workflow_root,
        health_root=args.health_root,
        source_snapshot_root=args.source_snapshot_root,
        output_root=args.output_root,
    )
    print(f"daily_index={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
