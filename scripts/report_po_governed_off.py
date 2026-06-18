#!/usr/bin/env python3
"""Report whether auto-PO is deliberately governed OFF under OD-009."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "po_governed_off_gates.json"
DEFAULT_OWNER_DECISIONS = PROJECT_ROOT / "docs" / "plan" / "green_path_2026-06" / "OWNER_DECISIONS_RECORDED.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "po_governed_off"
DEFAULT_LAUNCHAGENT_DIR = Path.home() / "Library" / "LaunchAgents"

EXPECTED_STOP_BUY_GATES = {
    "frozen_cover_gt_180d",
    "size_overstock",
    "return_qc_telemetry",
    "ppch_v1_gate",
    "cash_truth_gate",
    "ads_crr_gate",
}
EXPECTED_RESTART_REQUIRES = {
    "cogs_green_30d",
    "stock_green_30d",
    "cash_green",
    "fx_floor_vintage_green",
    "priors_7of7_tests",
    "forecast_backtest_pass_threshold_set_at_acceptance",
    "owner_approval",
}
PO_TABLES = ("fact_po_draft", "fact_po_draft_lines", "fact_po_execution")


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _count_rows(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table):
        return None
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _max_fact_sku_metrics(conn: sqlite3.Connection) -> str | None:
    if not _table_exists(conn, "fact_sku_metrics"):
        return None
    row = conn.execute("SELECT MAX(computed_at) FROM fact_sku_metrics").fetchone()
    return str(row[0]) if row and row[0] is not None else None


def _validate_gate_config(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    if not path.exists():
        return {}, [_check(False, "gate_config_present", f"missing: {path}")]
    payload = _load_json(path)
    checks.append(_check(True, "gate_config_present", str(path)))
    stop_buy_ids = {str(row.get("id", "")).strip() for row in payload.get("stop_buy_gates", [])}
    restart_requires = {str(row).strip() for row in payload.get("restart_requires", [])}
    missing_stop = sorted(EXPECTED_STOP_BUY_GATES - stop_buy_ids)
    missing_restart = sorted(EXPECTED_RESTART_REQUIRES - restart_requires)
    checks.append(
        _check(
            not missing_stop,
            "stop_buy_gates_encoded",
            "missing=" + (",".join(missing_stop) if missing_stop else "none"),
            stop_buy_gate_ids=sorted(stop_buy_ids),
        )
    )
    checks.append(
        _check(
            not missing_restart,
            "restart_criteria_encoded",
            "missing=" + (",".join(missing_restart) if missing_restart else "none"),
            restart_requires=sorted(restart_requires),
        )
    )
    checks.append(
        _check(
            payload.get("mode") == "governed_off"
            and payload.get("auto_po_restart_permitted") is False
            and payload.get("auto_draft_creation_allowed") is False,
            "governed_off_flags",
            f"mode={payload.get('mode')} restart={payload.get('auto_po_restart_permitted')} draft={payload.get('auto_draft_creation_allowed')}",
        )
    )
    checks.append(
        _check(
            payload.get("proposal_artifacts_are_advisory_only") is True
            and payload.get("manual_po_gate_mode") == "advisory",
            "advisory_only_flags",
            f"proposal_advisory={payload.get('proposal_artifacts_are_advisory_only')} manual_mode={payload.get('manual_po_gate_mode')}",
        )
    )
    return payload, checks


def _validate_owner_decision(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _check(False, "owner_decision_od_009_recorded", f"missing: {path}")
    text = path.read_text(encoding="utf-8")
    required_tokens = [
        "id: OD-009",
        "auto_po_governed_off",
        "cogs_green_30d",
        "stock_green_30d",
        "cash_green",
        "fx_floor_vintage_green",
        "priors_7of7_tests",
        "forecast_backtest_pass_threshold_set_at_acceptance",
        "owner_approval",
        "stop_buy_gates_advisory_on_manual_pos: true",
    ]
    missing = [token for token in required_tokens if token not in text]
    return _check(
        not missing,
        "owner_decision_od_009_recorded",
        "missing=" + (",".join(missing) if missing else "none"),
        owner_decisions_path=str(path),
    )


def _find_auto_po_launchagents(launchagent_dir: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not launchagent_dir.exists():
        return findings
    for path in sorted(launchagent_dir.glob("*.plist")):
        try:
            raw = path.read_bytes()
            payload = plistlib.loads(raw)
        except Exception:
            raw = path.read_text(encoding="utf-8", errors="ignore").encode("utf-8")
            payload = {}
        label = str(payload.get("Label") or path.stem)
        program_bits = []
        program = payload.get("Program")
        if program:
            program_bits.append(str(program))
        args = payload.get("ProgramArguments")
        if isinstance(args, list):
            program_bits.extend(str(arg) for arg in args)
        haystack = " ".join([label, str(path), " ".join(program_bits), raw.decode("utf-8", errors="ignore")]).lower()
        if "run_auto_po.py" in haystack or "auto-po" in haystack or "auto_po" in haystack:
            findings.append({"label": label, "path": str(path), "program": " ".join(program_bits)})
    return findings


def _run_launchctl_labels() -> list[str]:
    proc = subprocess.run(["launchctl", "list"], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    labels: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts:
            labels.append(parts[-1])
    return labels


def _run_subvalidators(*, as_of: str, db_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    from scripts.generate_po_proposals import generate_po_proposals
    from scripts.validate_po_capital_protection import validate_po_capital_protection
    from scripts.validate_po_money_gate import run_po_money_gate
    from scripts import validate_po_contract

    proposals = generate_po_proposals(
        db_path=db_path,
        as_of=as_of,
        output_root=PROJECT_ROOT / "exports" / "po",
        strict=True,
    )
    artifacts["po_proposals_json"] = proposals["json_path"]
    artifacts["po_proposals_md"] = proposals["md_path"]
    checks.append(
        _check(
            bool(proposals.get("ok")),
            "advisory_po_proposals_generated",
            f"status={proposals.get('status')} proposal_count={proposals.get('proposal_count')}",
            total_capital_at_risk_kzt=proposals.get("total_capital_at_risk_kzt"),
        )
    )

    capital = validate_po_capital_protection(
        as_of=as_of,
        proposals_json=Path(str(proposals["json_path"])),
        output_root=PROJECT_ROOT / "exports" / "validation" / "po_capital_protection",
        strict=True,
    )
    artifacts["capital_protection_json"] = capital["json_path"]
    artifacts["capital_protection_md"] = capital["md_path"]
    checks.append(
        _check(
            bool(capital.get("ok")),
            "capital_protection_validator",
            f"status={capital.get('status')}",
        )
    )

    money = run_po_money_gate(project_root=PROJECT_ROOT, db_path=db_path)
    artifacts["po_money_gate_report"] = money
    checks.append(
        _check(
            bool(money.get("ok")),
            "po_money_gate_required_checks",
            "required_failed=" + (",".join(money.get("required_failed", [])) or "none"),
            optional_failed=money.get("optional_failed", []),
        )
    )

    contract = validate_po_contract.run_contract()
    artifacts["po_contract_result"] = contract
    checks.append(
        _check(
            bool(contract.get("ok")),
            "po_contract_golden_fixtures",
            f"failures={len(contract.get('failures', []))}",
        )
    )
    return checks, artifacts


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# PO Governed-Off Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- db_path: `{report['db_path']}`",
        f"- fact_sku_metrics_max_computed_at: `{report.get('fact_sku_metrics_max_computed_at')}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.extend(["", "## PO Table Counts", ""])
    for name, count in report["po_table_counts"].items():
        lines.append(f"- `{name}`: `{count}`")
    if report["auto_po_launchagent_findings"]:
        lines.extend(["", "## Auto-PO LaunchAgent Findings", ""])
        for finding in report["auto_po_launchagent_findings"]:
            lines.append(f"- `{finding['label']}` at `{finding['path']}`")
    if report.get("artifacts"):
        lines.extend(["", "## Artifacts", ""])
        for key, value in report["artifacts"].items():
            if isinstance(value, str):
                lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def build_po_governed_off_report(
    *,
    as_of: str,
    db_path: Path = DEFAULT_DB,
    config_path: Path = DEFAULT_CONFIG,
    owner_decisions_path: Path = DEFAULT_OWNER_DECISIONS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    launchagent_dir: Path = DEFAULT_LAUNCHAGENT_DIR,
    run_subvalidators: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    config, config_checks = _validate_gate_config(config_path)
    checks.extend(config_checks)
    checks.append(_validate_owner_decision(owner_decisions_path))

    po_table_counts: dict[str, int | None] = {}
    fact_sku_metrics_max: str | None = None
    with _connect_ro(db_path) as conn:
        for table in PO_TABLES:
            po_table_counts[table] = _count_rows(conn, table)
        fact_sku_metrics_max = _max_fact_sku_metrics(conn)
    missing_tables = sorted(name for name, count in po_table_counts.items() if count is None)
    nonzero_tables = {name: count for name, count in po_table_counts.items() if count not in (0, None)}
    checks.append(
        _check(
            not missing_tables and not nonzero_tables,
            "po_draft_tables_empty",
            f"missing={','.join(missing_tables) if missing_tables else 'none'} nonzero={nonzero_tables or 'none'}",
            po_table_counts=po_table_counts,
        )
    )
    checks.append(
        _check(
            bool(config.get("auto_po_restart_permitted") is False),
            "restart_blocked_until_criteria_and_owner_approval",
            f"fact_sku_metrics_max_computed_at={fact_sku_metrics_max}",
        )
    )

    auto_po_findings = _find_auto_po_launchagents(launchagent_dir)
    loaded_labels = _run_launchctl_labels()
    loaded_auto_po_labels = [
        label for label in loaded_labels if "auto-po" in label.lower() or "auto_po" in label.lower()
    ]
    checks.append(
        _check(
            not auto_po_findings and not loaded_auto_po_labels,
            "auto_po_launchagent_absent",
            f"installed_findings={len(auto_po_findings)} loaded_auto_po_labels={len(loaded_auto_po_labels)}",
            loaded_auto_po_labels=loaded_auto_po_labels,
        )
    )

    if run_subvalidators:
        sub_checks, sub_artifacts = _run_subvalidators(as_of=as_of, db_path=db_path)
        checks.extend(sub_checks)
        artifacts.update(sub_artifacts)

    ok = all(row["ok"] for row in checks)
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "GREEN" if ok else "RED",
        "ok": bool(ok),
        "db_path": str(db_path.resolve()),
        "config_path": str(config_path.resolve()),
        "owner_decisions_path": str(owner_decisions_path.resolve()),
        "run_subvalidators": bool(run_subvalidators),
        "fact_sku_metrics_max_computed_at": fact_sku_metrics_max,
        "po_table_counts": po_table_counts,
        "auto_po_launchagent_findings": auto_po_findings,
        "checks": checks,
        "artifacts": artifacts,
    }
    json_path = out_dir / "po_governed_off_report.json"
    md_path = out_dir / "po_governed_off_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report G-PO-01 governed-off auto-PO state")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--owner-decisions", type=Path, default=DEFAULT_OWNER_DECISIONS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--launchagent-dir", type=Path, default=DEFAULT_LAUNCHAGENT_DIR)
    parser.add_argument("--run-subvalidators", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_po_governed_off_report(
        as_of=str(args.as_of),
        db_path=args.db,
        config_path=args.config,
        owner_decisions_path=args.owner_decisions,
        output_root=args.output_root,
        launchagent_dir=args.launchagent_dir,
        run_subvalidators=bool(args.run_subvalidators),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"po_governed_off_json={report['json_path']}")
        print(f"po_governed_off_md={report['md_path']}")
        print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
