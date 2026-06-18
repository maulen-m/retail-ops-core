#!/usr/bin/env python3
"""Report G-PRICE-05 fresh Repricer price-backlog disposition."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_price05_fresh_backlog"


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _as_bool(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _as_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(float(str(value).strip() or "0"))
    except ValueError:
        return 0


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _counter_rows(counter: Counter[str], key_name: str, value_name: str = "count") -> list[dict[str, Any]]:
    return [
        {key_name: key, value_name: value}
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _summarize_actions(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_store: dict[str, Counter[str]] = defaultdict(Counter)
    by_operation = Counter[str]()
    by_target_field = Counter[str]()
    by_source_rule = Counter[str]()
    vintage_fail_reasons = Counter[str]()
    stale_anchor_guard_rows = 0
    live_price_raise_rows = 0
    live_price_update_rows = 0
    min_update_rows = 0
    max_update_rows = 0
    live_price_down_reset_rows = 0
    min_down_reset_rows = 0
    vintage_ok_rows = 0

    for row in rows:
        store = row.get("store_name") or row.get("store_id") or "UNKNOWN"
        operation = row.get("operation") or "UNKNOWN"
        target_field = row.get("target_field") or "UNKNOWN"
        source_rule = row.get("source_rule") or "UNKNOWN"
        by_store[store][operation] += 1
        by_operation[operation] += 1
        by_target_field[target_field] += 1
        by_source_rule[source_rule] += 1
        if _as_bool(row.get("vintage_ok")):
            vintage_ok_rows += 1
        else:
            vintage_fail_reasons[row.get("vintage_fail_reason") or "missing_or_false"] += 1
        stale_anchor_guard_rows += int(_as_bool(row.get("stale_anchor_guard_applied")))
        live_price_update = _as_bool(row.get("need_live_price"))
        live_price_update_rows += int(live_price_update)
        min_update_rows += int(_as_bool(row.get("need_min")))
        max_update_rows += int(_as_bool(row.get("need_max")))
        live_price_target = _as_int(row.get("live_price_target") or row.get("target_value"))
        live_price_raise_rows += int(live_price_update and live_price_target > _as_int(row.get("current_price")))
        live_price_down_reset_rows += int(_as_bool(row.get("live_reset_down")))
        min_down_reset_rows += int(_as_bool(row.get("min_reset_down")))

    return {
        "planned_action_rows": len(rows),
        "by_store": {store: dict(counter) for store, counter in sorted(by_store.items())},
        "by_operation": dict(by_operation),
        "by_target_field": dict(by_target_field),
        "top_source_rules": _counter_rows(by_source_rule, "source_rule")[:30],
        "stale_anchor_guard_rows": stale_anchor_guard_rows,
        "min_update_rows": min_update_rows,
        "max_update_rows": max_update_rows,
        "live_price_update_rows": live_price_update_rows,
        "live_price_raise_rows": live_price_raise_rows,
        "live_price_down_reset_rows": live_price_down_reset_rows,
        "min_down_reset_rows": min_down_reset_rows,
        "vintage_ok_rows": vintage_ok_rows,
        "vintage_fail_reasons": dict(vintage_fail_reasons),
    }


def build_report(
    run_dir: Path,
    *,
    disposition: str,
    output_dir: Path,
    applied_evidence: str = "",
) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    planned_actions_path = run_dir / "planned_actions.csv"
    vintage_log_path = run_dir / "price_write_vintage_log.csv"

    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    for label, path in (
        ("summary_json", summary_path),
        ("planned_actions_csv", planned_actions_path),
        ("price_write_vintage_log_csv", vintage_log_path),
    ):
        ok = path.exists()
        checks.append({"check": label, "ok": ok, "path": str(path)})
        if not ok:
            blockers.append(f"missing {label}: {path}")

    summary: dict[str, Any] = {}
    rows: list[dict[str, str]] = []
    vintage_rows: list[dict[str, str]] = []
    if summary_path.exists():
        summary = _load_json(summary_path)
    if planned_actions_path.exists():
        rows = _load_csv(planned_actions_path)
    if vintage_log_path.exists():
        vintage_rows = _load_csv(vintage_log_path)

    dry_run = bool(summary.get("dry_run"))
    verify = bool(summary.get("verify"))
    errors = _as_int(summary.get("errors"))
    api_sets_attempted = sum(_as_int(store.get("api_sets_attempted")) for store in (summary.get("stores") or {}).values())
    api_sets_succeeded = sum(_as_int(store.get("api_sets_succeeded")) for store in (summary.get("stores") or {}).values())
    summary_planned_path = str(summary.get("planned_actions_csv") or "")
    summary_vintage_rows = _as_int(summary.get("price_write_vintage_logged_rows"))

    if not dry_run:
        blockers.append("source run is not a dry-run")
    if not verify:
        blockers.append("source run did not run verify mode")
    if errors:
        blockers.append(f"source run reported errors={errors}")
    if api_sets_attempted or api_sets_succeeded:
        blockers.append(
            f"dry-run expected zero API set calls, got attempted={api_sets_attempted}, succeeded={api_sets_succeeded}"
        )
    if summary_planned_path and Path(summary_planned_path).name != planned_actions_path.name:
        warnings.append(f"summary planned_actions_csv points to {summary_planned_path}")
    if summary_vintage_rows != len(rows):
        blockers.append(
            f"vintage logged row count {summary_vintage_rows} does not match planned action rows {len(rows)}"
        )
    if vintage_rows and len(vintage_rows) != len(rows):
        blockers.append(f"vintage log csv rows {len(vintage_rows)} do not match planned action rows {len(rows)}")

    action_summary = _summarize_actions(rows)
    if action_summary["vintage_fail_reasons"]:
        blockers.append(f"vintage failures present: {action_summary['vintage_fail_reasons']}")

    disposition = disposition.strip()
    if disposition not in {"open_backlog", "applied_from_fresh_scan", "formal_drop_approved"}:
        blockers.append(f"unknown disposition={disposition}")
    if len(rows) > 0 and disposition == "open_backlog":
        blockers.append(f"fresh backlog remains open with {len(rows)} planned actions")
    if disposition == "applied_from_fresh_scan" and not applied_evidence:
        blockers.append("applied_from_fresh_scan disposition requires applied evidence")
    if disposition == "formal_drop_approved" and not applied_evidence:
        blockers.append("formal_drop_approved disposition requires approval/drop evidence")

    gate = "GREEN" if not blockers else "RED"
    report = {
        "gate_id": "G-PRICE-05",
        "gate": gate,
        "ok": gate == "GREEN",
        "generated_at": _now_almaty(),
        "run_dir": str(run_dir),
        "summary_path": str(summary_path),
        "planned_actions_path": str(planned_actions_path),
        "price_write_vintage_log_path": str(vintage_log_path),
        "disposition": disposition,
        "applied_evidence": applied_evidence,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "source_run": {
            "run_id": summary.get("run_id"),
            "dry_run": dry_run,
            "verify": verify,
            "errors": errors,
            "api_requests": _as_int(summary.get("api_requests")),
            "api_sets_attempted": api_sets_attempted,
            "api_sets_succeeded": api_sets_succeeded,
            "price_write_vintage_version": summary.get("price_write_vintage_version"),
            "price_write_vintage_source_basis": summary.get("price_write_vintage_source_basis"),
            "summary_price_write_vintage_logged_rows": summary_vintage_rows,
            "remaining_live_price_mismatches": _as_int(summary.get("remaining_live_price_mismatches")),
        },
        "action_summary": action_summary,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "g_price05_fresh_backlog_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "g_price05_fresh_backlog_report.md").write_text(
        _render_markdown(report),
        encoding="utf-8",
    )
    _write_csv(
        output_dir / "g_price05_store_operation_counts.csv",
        [
            {"store_name": store, "operation": operation, "count": count}
            for store, counter in sorted(action_summary["by_store"].items())
            for operation, count in sorted(counter.items())
        ],
        ["store_name", "operation", "count"],
    )
    _write_csv(
        output_dir / "g_price05_top_source_rules.csv",
        action_summary["top_source_rules"],
        ["source_rule", "count"],
    )
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-PRICE-05 Fresh Backlog Disposition",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"Run dir: `{report['run_dir']}`",
        f"Disposition: `{report['disposition']}`",
        "",
        "## Summary",
        "",
        f"- Planned action rows: {report['action_summary']['planned_action_rows']}",
        f"- Vintage OK rows: {report['action_summary']['vintage_ok_rows']}",
        f"- Stale-anchor guard rows: {report['action_summary']['stale_anchor_guard_rows']}",
        f"- Min update rows: {report['action_summary']['min_update_rows']}",
        f"- Max update rows: {report['action_summary']['max_update_rows']}",
        f"- Live price update rows: {report['action_summary']['live_price_update_rows']}",
        f"- Live price raise rows: {report['action_summary']['live_price_raise_rows']}",
        f"- Live price down-reset rows: {report['action_summary']['live_price_down_reset_rows']}",
        f"- Min down-reset rows: {report['action_summary']['min_down_reset_rows']}",
        f"- Dry-run: {report['source_run']['dry_run']}",
        f"- Verify: {report['source_run']['verify']}",
        f"- Errors: {report['source_run']['errors']}",
        f"- API set calls attempted/succeeded: {report['source_run']['api_sets_attempted']}/{report['source_run']['api_sets_succeeded']}",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Store Operation Counts", ""])
    for store, counter in report["action_summary"]["by_store"].items():
        counts = ", ".join(f"{operation}={count}" for operation, count in sorted(counter.items()))
        lines.append(f"- {store}: {counts}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--disposition",
        choices=["open_backlog", "applied_from_fresh_scan", "formal_drop_approved"],
        default="open_backlog",
    )
    parser.add_argument("--applied-evidence", default="")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S"))
    report = build_report(
        run_dir,
        disposition=args.disposition,
        output_dir=output_dir,
        applied_evidence=args.applied_evidence,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {output_dir / 'g_price05_fresh_backlog_report.json'}")
        print(f"Planned action rows: {report['action_summary']['planned_action_rows']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] != "GREEN" else 0


if __name__ == "__main__":
    raise SystemExit(main())
