#!/usr/bin/env python3
"""Fail-closed, layered system diagnostics for daily operations."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
Runner = Callable[[str, Path], tuple[int, str]]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_as_of_date import resolve_as_of_date
from scripts.run_owner_truth_daily import (
    _default_webui_ledger_root,
    _resolve_default_download_run_id,
    _resolve_pack_root_from_ledger,
)


def _run_shell(cmd: str, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return int(proc.returncode), output


def _summarize_output(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    for key in ("error_code=", "status=", "blocked_layer="):
        for line in lines:
            if line.startswith(key):
                return line
    return lines[-1]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _publication_validation_dir(root: Path, as_of: str) -> Path | None:
    publication_path = root / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json"
    payload = _load_json(publication_path)
    if not isinstance(payload, dict):
        return None
    gates = payload.get("gates") or {}
    if not isinstance(gates, dict):
        return None
    candidates: list[Path] = []
    for gate in gates.values():
        if not isinstance(gate, dict):
            continue
        raw_path = gate.get("path")
        if not raw_path:
            continue
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = root / candidate
        parent = candidate.parent.resolve()
        if parent.exists():
            candidates.append(parent)
    if not candidates:
        return None
    counts: dict[Path, int] = {}
    for candidate in candidates:
        counts[candidate] = counts.get(candidate, 0) + 1
    return sorted(counts.items(), key=lambda item: (item[1], str(item[0])))[-1][0]


def _resolve_required_workbook_anchor(root: Path) -> Path:
    raw = os.environ.get("AB_CRM_WORKBOOK_PATH", "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        if candidate.exists():
            return candidate.resolve()
        raise RuntimeError(f"AB_CRM_WORKBOOK_PATH does not exist: {candidate}")

    anchored = root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    if anchored.exists():
        return anchored.resolve()

    raise RuntimeError(
        "AB_CRM_WORKBOOK_PATH is required for strict owner-truth doctor runs; "
        "missing config/anchors/SALES_KSP_CRM_LATEST.xlsx"
    )


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# System Doctor Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- project_root: `{report['project_root']}`",
        f"- entry_point: `{report['entry_point']}`",
        f"- status: `{report['status']}`",
        f"- blocked_layer: `{report.get('blocked_layer') or 'none'}`",
        "",
        "## Layers",
        "",
        "| layer | status | checks_run | checks_failed |",
        "|---|---:|---:|---:|",
    ]
    for layer in report["layers"]:
        status = "GREEN" if layer["ok"] else "RED"
        lines.append(
            f"| `{layer['layer']}` | {status} | {layer['checks_run']} | {layer['checks_failed']} |"
        )

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| layer | check | rc | status | duration_sec | summary |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for check in report["checks"]:
        status = "OK" if check["ok"] else "FAIL"
        lines.append(
            f"| `{check['layer']}` | `{check['check']}` | {check['rc']} | {status} | "
            f"{check['duration_sec']} | {check['summary']} |"
        )
    return "\n".join(lines) + "\n"


def _doctor_checks(
    *,
    root: Path,
    as_of: str,
    truth_source: str = "db",
    validation_dir: Path | None = None,
    pack_root: Path | None = None,
    ledger_root: Path | None = None,
    download_run_id: str | None = None,
    workbook_anchor: Path | None = None,
) -> list[dict[str, str]]:
    quoted_root = shlex.quote(str(root))
    quoted_as_of = shlex.quote(as_of)
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError:
        as_of_date = date.today()
    historical_future_allowance = max(0, (date.today() - as_of_date).days)
    env_future_allowance = int(os.environ.get("AB_CRM_WORKBOOK_MAX_FUTURE_CONTENT_DAYS", "0"))
    max_future_content_days = max(env_future_allowance, historical_future_allowance)
    report_path = shlex.quote(str(root / "exports" / "daily" / as_of / "daily_ops_report.json"))
    exceptions_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions.json"))
    triage_json_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.json"))
    triage_md_path = shlex.quote(str(root / "exports" / "exceptions" / as_of / "exceptions_triage.md"))
    economics_since_raw = date.fromisoformat(os.environ.get("AB_ECONOMICS_PARITY_SINCE", "2025-06-06"))
    economics_since = shlex.quote(str(economics_since_raw.isoformat()))
    statusdate_cutover = shlex.quote(str(os.environ.get("AB_STATUSDATE_CUTOVER", "2026-02-27")))
    ops_selection_overflow = int(os.environ.get("AB_OPS_SELECTION_MAX_IMPORT_OVERFLOW", "5"))
    include_ops_selection_parity = os.environ.get("AB_INCLUDE_OPS_SELECTION_PARITY", "").strip() == "1"
    include_scheduler_heartbeat = os.environ.get("AB_INCLUDE_SCHEDULER_HEARTBEAT", "").strip() == "1"
    identity_validation_root = root / "exports" / "validation" / "identity_stabilization"
    identity_reference_csv = shlex.quote(
        str(identity_validation_root / as_of / "offer_identity_reference.csv")
    )
    quoted_truth_source = shlex.quote(truth_source)
    if validation_dir is not None:
        resolved_validation_dir = validation_dir
    elif truth_source == "webui_archive":
        resolved_validation_dir = root / "exports" / "validation" / "webui_archive_single_truth" / as_of
    else:
        default_validation_dir = root / "exports" / "validation" / "crm_north_star_restate" / as_of
        resolved_validation_dir = default_validation_dir if default_validation_dir.exists() else (
            _publication_validation_dir(root, as_of) or default_validation_dir
        )
    resolved_ledger_root = ledger_root or _default_webui_ledger_root(root)
    resolved_pack_root = (
        pack_root
        or _resolve_pack_root_from_ledger(resolved_ledger_root, root)
        or (root / "exports" / "webui_archive_packs" / "webui_archive_seed_20260306")
    )
    resolved_download_run_id = (
        str(download_run_id.resolve())
        if isinstance(download_run_id, Path)
        else (download_run_id or _resolve_default_download_run_id(root, resolved_pack_root))
    )
    validation_dir_path = Path(resolved_validation_dir)
    quoted_validation_dir = shlex.quote(str(validation_dir_path))
    quoted_pack_root = shlex.quote(str(resolved_pack_root))
    quoted_ledger_root = shlex.quote(str(resolved_ledger_root))
    quoted_download_run_id = shlex.quote(str(resolved_download_run_id))
    workbook_env_prefix = ""
    if workbook_anchor is not None:
        workbook_env_prefix = f"AB_CRM_WORKBOOK_PATH={shlex.quote(str(workbook_anchor))} "

    checks = [
        {
            "layer": "runtime",
            "check": "scheduler_validate_only",
            "cmd": "bash scripts/install_single_truth_ops_scheduler.sh --validate-only",
        },
        {
            "layer": "runtime",
            "check": "anchor_health",
            "cmd": (
                "python3 scripts/check_anchor_health.py "
                f"--project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--max-future-content-days {max_future_content_days}"
            ),
        },
        {
            "layer": "runtime",
            "check": "ops_status",
            "cmd": f"python3 scripts/ops_status.py --project-root {quoted_root}",
        },
        {
            "layer": "truth",
            "check": "validate_params_strict",
            "cmd": workbook_env_prefix + f"python3 scripts/validate_params.py --strict --as-of {quoted_as_of}",
        },
        {
            "layer": "truth",
            "check": "validate_single_truth_system",
            "cmd": "python3 scripts/validate_single_truth_system.py",
        },
        {
            "layer": "truth",
            "check": "validate_schema",
            "cmd": "python3 scripts/validate_schema.py --json",
        },
        {
            "layer": "truth",
            "check": "validate_dashboard_plan_real_contract",
            "cmd": "python3 scripts/validate_dashboard_plan_real_contract.py --strict",
        },
        {
            "layer": "truth",
            "check": "validate_daily_ops_report",
            "cmd": f"python3 scripts/validate_daily_ops_report.py --strict --path {report_path}",
        },
        {
            "layer": "domain",
            "check": "build_domain_scorecards",
            "cmd": (
                "python3 scripts/build_domain_scorecards.py "
                f"--strict --as-of {quoted_as_of} "
                f"--project-root {quoted_root} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "domain",
            "check": "validate_cashfloor",
            "cmd": (
                "python3 scripts/validate_cashfloor.py "
                f"--strict --as-of {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "domain",
            "check": "translate_transfer_ledger_to_cashflow",
            "cmd": (
                "python3 scripts/translate_transfer_ledger_to_cashflow.py "
                f"--strict --as-of {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "execution",
            "check": "build_daily_ops_timings",
            "cmd": (
                "python3 scripts/build_daily_ops_timings.py "
                f"--strict --as-of {quoted_as_of} "
                f"--project-root {quoted_root} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'perf'))}"
            ),
        },
        {
            "layer": "execution",
            "check": "daily_ops_timing_artifact",
            "cmd": f"python3 scripts/validate_daily_ops_timing_artifact.py exports/perf/{as_of}/daily_ops_timings.json --strict",
        },
        {
            "layer": "governance",
            "check": "validate_reference_freshness",
            "cmd": (
                "python3 scripts/validate_reference_freshness.py "
                f"--as-of {quoted_as_of} "
                f"--reference-root {shlex.quote(str(root / 'exports' / 'sales_archive_statusdate_mapped'))} "
                f"--output-root {shlex.quote(str(identity_validation_root))} "
                "--max-delivery-lag-days 7 "
                f"--statusdate-cutover {statusdate_cutover} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "import_web_automation_offer_identity",
            "cmd": (
                "python3 scripts/import_web_automation_offer_identity.py "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(identity_validation_root))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_external_snapshot_parity",
            "cmd": (
                "python3 scripts/validate_external_snapshot_parity.py "
                f"--as-of {quoted_as_of} "
                f"--reference-csv {identity_reference_csv} "
                f"--output-root {shlex.quote(str(identity_validation_root))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_recent_identity_coverage",
            "cmd": (
                "python3 scripts/validate_recent_identity_coverage.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(identity_validation_root))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_order_entries_freshness",
            "cmd": (
                "python3 scripts/validate_order_entries_freshness.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(identity_validation_root))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_exceptions_schema",
            "cmd": f"python3 scripts/validate_exceptions_schema.py {exceptions_path} --strict",
        },
        {
            "layer": "governance",
            "check": "validate_as_of_consistency",
            "cmd": (
                "python3 scripts/validate_as_of_consistency.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'diagnostics'))}"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_vs_waybill_parity",
            "cmd": (
                "python3 scripts/validate_sales_vs_waybill_parity.py "
                f"--strict --project-root {quoted_root} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))}"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_shipped_truth_crm_waybill",
            "cmd": (
                "python3 scripts/validate_shipped_truth_crm_waybill.py "
                f"--project-root {quoted_root} "
                f"--since {quoted_as_of} "
                f"--until {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'shipped_truth_crm_waybill'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_business_insides_shipped_truth",
            "cmd": (
                "python3 scripts/validate_business_insides_shipped_truth.py "
                f"--since {quoted_as_of} "
                f"--until {quoted_as_of} "
                f"--shipped-summary {shlex.quote(str(root / 'exports' / 'validation' / 'shipped_truth_crm_waybill' / f'{as_of}_to_{as_of}' / 'summary.json'))} "
                f"--business-dir {shlex.quote(str(root / 'config' / 'business_insides'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'business_insides_shipped_truth'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_business_insides_economics_ready",
            "cmd": (
                "python3 scripts/validate_business_insides_economics_ready.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'business_insides_economics'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_ads_sidecar_readiness",
            "cmd": (
                "python3 scripts/validate_ads_sidecar_readiness.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'ads_sidecar_readiness'))} "
                "--readiness-mode live "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_opex_readiness",
            "cmd": (
                "python3 scripts/validate_opex_readiness.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'opex_readiness'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_returns_economics_audit",
            "cmd": (
                "python3 scripts/validate_returns_economics_audit.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--since {economics_since} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'returns_economics'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_monthly_cash_reconciliation",
            "cmd": (
                "python3 scripts/validate_monthly_cash_reconciliation.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--since {economics_since} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'cash_reconciliation'))} "
                f"--statusdate-cutover {statusdate_cutover} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_archive_statusdate_mapped",
            "cmd": (
                "python3 scripts/validate_sales_archive_statusdate_mapped.py "
                f"--since {economics_since} "
                f"--until {quoted_as_of} "
                f"--data-root {shlex.quote(str(root / 'exports' / 'sales_archive_statusdate_mapped'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'economics_parity'))} "
                f"--strict-statusdate-required-since {statusdate_cutover} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_monthly_economics_parity",
            "cmd": (
                "python3 scripts/validate_monthly_economics_parity.py "
                f"--since {economics_since} "
                f"--until {quoted_as_of} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--mapped-root {shlex.quote(str(root / 'exports' / 'sales_archive_statusdate_mapped'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'economics_parity'))} "
                f"--statusdate-cutover {statusdate_cutover} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "build_owner_pnl_report",
            "cmd": (
                "python3 scripts/build_owner_pnl_report.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--since {economics_since} "
                f"--mapped-root {shlex.quote(str(root / 'exports' / 'sales_archive_statusdate_mapped'))} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'owner_pnl'))} "
                f"--parity-output-root {shlex.quote(str(root / 'exports' / 'validation' / 'economics_parity'))} "
                f"--statusdate-cutover {statusdate_cutover} "
                f"--truth-source {quoted_truth_source} "
                f"--validation-dir {quoted_validation_dir} "
                + (
                    f"--ledger-root {quoted_ledger_root} "
                    if truth_source == "webui_archive"
                    else ""
                )
                + "--include-store-breakdown "
                + "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_business_insides_ocean_drop_alignment",
            "cmd": (
                "python3 scripts/validate_business_insides_ocean_drop_alignment.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'business_insides_ocean_drop_alignment'))} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "triage_owner_truth_stoplines",
            "cmd": (
                "python3 scripts/triage_owner_truth_stoplines.py "
                f"--as-of {quoted_as_of} "
                f"--project-root {quoted_root} "
                f"--truth-source {quoted_truth_source} "
                f"--validation-dir {quoted_validation_dir} "
                + (
                    f"--pack-root {quoted_pack_root} "
                    f"--ledger-root {quoted_ledger_root} "
                    f"--download-run-id {quoted_download_run_id} "
                    if truth_source == "webui_archive"
                    else ""
                )
                + "--allow-missing-publication-readiness "
                + "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_truth_external_reference",
            "cmd": (
                "python3 scripts/validate_sales_truth_external_reference.py "
                f"--project-root {quoted_root} "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                "--strict-if-configured"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_truth_ocean_drop_parity",
            "cmd": (
                "python3 scripts/validate_sales_truth_ocean_drop_parity.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_ocean_drop_parity'))} "
                "--window-days 14 "
                "--volatility-days 14 "
                "--strict-if-configured --strict"
            ),
        },
        {
            "layer": "governance",
            "check": "validate_sales_engine_self_sufficient",
            "cmd": (
                "python3 scripts/validate_sales_engine_self_sufficient.py "
                f"--db {shlex.quote(str(root / 'db' / 'app.db'))} "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_engine_self_sufficient'))} "
                "--strict-if-configured --strict"
            ),
        },
        {
            "layer": "governance",
            "check": "build_sales_truth_drift_report",
            "cmd": (
                "python3 scripts/build_sales_truth_drift_report.py "
                f"--as-of {quoted_as_of} "
                f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                f"--parity-root {shlex.quote(str(root / 'exports' / 'validation' / 'sales_ocean_drop_parity'))} "
                "--lookback-days 14 "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "triage_exceptions",
            "cmd": (
                "python3 scripts/triage_exceptions.py "
                f"--exceptions {exceptions_path} "
                "--playbook docs/ops/EXCEPTION_PLAYBOOK.md "
                "--allowlist config/exceptions_allowlist.json "
                f"--output-json {triage_json_path} "
                f"--output-md {triage_md_path} "
                "--strict"
            ),
        },
        {
            "layer": "governance",
            "check": "lint_docs",
            "cmd": "bash scripts/lint_docs.sh",
        },
        {
            "layer": "governance",
            "check": "lint_docs_active_scope",
            "cmd": f"python3 scripts/lint_docs_active_scope.py --strict --project-root {quoted_root}",
        },
    ]

    if truth_source == "webui_archive":
        webui_checks = [
            {
                "layer": "governance",
                "check": "validate_webui_archive_pack_integrity",
                "cmd": (
                    "python3 scripts/validate_webui_archive_pack_integrity.py "
                    f"--pack-root {quoted_pack_root} --strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_status_ledger_continuity",
                "cmd": (
                    "python3 scripts/validate_status_ledger_continuity.py "
                    f"--ledger-root {quoted_ledger_root} "
                    "--start 2026-01-01 --end 2026-02-29 --strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_webui_crm_shipped_day_authority",
                "cmd": (
                    "python3 scripts/validate_webui_crm_shipped_day_authority.py "
                    "--start 2026-01-01 --end 2026-02-29 "
                    f"--output-dir {quoted_validation_dir} "
                    "--strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_sales_against_workbook",
                "cmd": (
                    "python3 scripts/validate_sales_against_workbook.py "
                    "--start 2026-01-01 --end 2026-02-29 "
                    f"--output-dir {quoted_validation_dir} "
                    "--strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_webui_archive_vs_current_db",
                "cmd": (
                    "python3 scripts/validate_webui_archive_vs_current_db.py "
                    "--start 2026-01-01 --end 2026-02-29 "
                    f"--ledger-root {quoted_ledger_root} "
                    f"--output-dir {quoted_validation_dir} "
                    "--strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_webui_archive_vs_current_db_full_range",
                "cmd": (
                    "python3 scripts/validate_webui_archive_vs_current_db.py "
                    f"--start {shlex.quote(economics_since_raw.isoformat())} "
                    f"--end {quoted_as_of} "
                    f"--ledger-root {quoted_ledger_root} "
                    f"--output-dir {shlex.quote(str(validation_dir_path / 'full_range_db_gate'))} "
                    "--range-policy full_range_owner_truth "
                    f"--statusdate-cutover {statusdate_cutover} "
                    "--strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_playwright_archive_downloads",
                "cmd": (
                    "python3 scripts/validate_playwright_archive_downloads.py "
                    f"--run-id {quoted_download_run_id} --strict"
                ),
            },
            {
                "layer": "governance",
                "check": "validate_order_status_audit_history",
                "cmd": (
                    "python3 scripts/validate_order_status_audit_history.py "
                    f"--as-of {quoted_as_of} --strict"
                ),
            },
        ]
        insert_at = next(
            i for i, item in enumerate(checks) if item["check"] == "build_owner_pnl_report"
        )
        for offset, item in enumerate(webui_checks):
            checks.insert(insert_at + offset, item)
    else:
        checks.append(
            {
                "layer": "governance",
                "check": "validate_kaspi_archive_pack_integrity_ui",
                "cmd": (
                    "python3 scripts/validate_kaspi_archive_pack_integrity.py "
                    "--source ui "
                    "--strict"
                ),
            }
        )

    if include_ops_selection_parity:
        insert_at = next(
            i for i, item in enumerate(checks) if item["check"] == "triage_owner_truth_stoplines"
        )
        checks.insert(
            insert_at,
            {
                "layer": "governance",
                "check": "validate_ops_selection_parity",
                "cmd": (
                    "python3 scripts/validate_ops_selection_parity.py "
                    f"--as-of {quoted_as_of} "
                    f"--output-root {shlex.quote(str(root / 'exports' / 'validation' / 'ops_selection_parity'))} "
                    f"--max-import-overflow {ops_selection_overflow} "
                    "--strict"
                ),
            },
        )

    if include_scheduler_heartbeat:
        insert_at = next(
            i for i, item in enumerate(checks) if item["check"] == "triage_owner_truth_stoplines"
        )
        checks.insert(
            insert_at,
            {
                "layer": "governance",
                "check": "validate_scheduler_heartbeat",
                "cmd": (
                    "python3 scripts/validate_scheduler_heartbeat.py "
                    f"--as-of {quoted_as_of} "
                    f"--output-root {shlex.quote(str(root / 'exports' / 'daily'))} "
                    "--strict"
                ),
            },
        )

    return checks


def run_system_doctor(
    *,
    project_root: Path,
    as_of: str,
    output_dir: Path,
    strict: bool,
    entry_point: str = "all",
    runtime_mode: str = "live",
    truth_source: str = "db",
    validation_dir: Path | None = None,
    pack_root: Path | None = None,
    ledger_root: Path | None = None,
    download_run_id: str | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    run = runner or _run_shell
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    required_workbook_anchor = None
    if strict:
        try:
            required_workbook_anchor = _resolve_required_workbook_anchor(root)
        except RuntimeError as exc:
            generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            check_rows = [
                {
                    "layer": "truth",
                    "check": "workbook_anchor_required",
                    "cmd": "resolve_workbook_anchor",
                    "rc": 1,
                    "ok": False,
                    "duration_sec": 0.0,
                    "summary": "error_code=WORKBOOK_ANCHOR_REQUIRED",
                    "output": str(exc),
                }
            ]
            report = {
                "generated_at": generated_at,
                "as_of": as_of,
                "project_root": str(root),
                "entry_point": entry_point,
                "runtime_mode": runtime_mode,
                "truth_source": truth_source,
                "ok": False,
                "status": "RED",
                "blocked_layer": "truth",
                "exit_code": 1,
                "layers": [
                    {"layer": "runtime", "ok": False, "checks_run": 0, "checks_failed": 0},
                    {"layer": "truth", "ok": False, "checks_run": 1, "checks_failed": 1},
                    {"layer": "domain", "ok": False, "checks_run": 0, "checks_failed": 0},
                    {"layer": "execution", "ok": False, "checks_run": 0, "checks_failed": 0},
                    {"layer": "governance", "ok": False, "checks_run": 0, "checks_failed": 0},
                ],
                "checks": check_rows,
            }
            checks_path = output / "system_health_checks.json"
            json_path = output / "system_health.json"
            md_path = output / "system_health.md"
            checks_path.write_text(json.dumps(check_rows, ensure_ascii=False, indent=2), encoding="utf-8")
            json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path.write_text(_render_markdown(report), encoding="utf-8")
            report["checks_path"] = str(checks_path)
            report["json_path"] = str(json_path)
            report["md_path"] = str(md_path)
            return report

    checks = _doctor_checks(
        root=root,
        as_of=as_of,
        truth_source=truth_source,
        validation_dir=validation_dir,
        pack_root=pack_root,
        ledger_root=ledger_root,
        download_run_id=download_run_id,
        workbook_anchor=required_workbook_anchor,
    )
    layer_order = ["runtime", "truth", "domain", "execution", "governance"]

    check_rows: list[dict[str, Any]] = []
    blocked_layer: str | None = None
    overall_ok = True

    for layer in layer_order:
        layer_checks = [row for row in checks if row["layer"] == layer]
        for row in layer_checks:
            started = time.perf_counter()
            rc, out = run(row["cmd"], root)
            duration = round(time.perf_counter() - started, 3)
            summary = _summarize_output(out)
            ok = rc == 0
            check_rows.append(
                {
                    "layer": layer,
                    "check": row["check"],
                    "cmd": row["cmd"],
                    "rc": int(rc),
                    "ok": bool(ok),
                    "duration_sec": duration,
                    "summary": summary,
                    "output": out,
                }
            )
            if not ok:
                overall_ok = False
                blocked_layer = layer
                break
        if not overall_ok:
            break

    layer_rows: list[dict[str, Any]] = []
    for layer in layer_order:
        rows = [row for row in check_rows if row["layer"] == layer]
        failed = [row for row in rows if not row["ok"]]
        layer_rows.append(
            {
                "layer": layer,
                "ok": len(failed) == 0 and len(rows) > 0,
                "checks_run": len(rows),
                "checks_failed": len(failed),
            }
        )

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    report = {
        "generated_at": generated_at,
        "as_of": as_of,
        "project_root": str(root),
        "entry_point": entry_point,
        "runtime_mode": runtime_mode,
        "truth_source": truth_source,
        "ok": overall_ok,
        "status": "GREEN" if overall_ok else "RED",
        "blocked_layer": blocked_layer,
        "exit_code": 0 if overall_ok else 1,
        "layers": layer_rows,
        "checks": check_rows,
    }

    checks_path = output / "system_health_checks.json"
    json_path = output / "system_health.json"
    md_path = output / "system_health.md"
    checks_path.write_text(json.dumps(check_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    report["checks_path"] = str(checks_path)
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    if strict and not overall_ok:
        report["exit_code"] = 1
    elif not strict:
        report["exit_code"] = 0
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fail-closed layered diagnostics (System Doctor)")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--entry-point",
        choices=["all", "po", "cashflow", "inventory", "api", "docs"],
        default="all",
    )
    parser.add_argument("--runtime-mode", choices=["live", "replay"], default="live")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="webui_archive")
    parser.add_argument("--validation-dir", type=Path, default=None)
    parser.add_argument("--pack-root", type=Path, default=None)
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--download-run-id", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    resolution = resolve_as_of_date(
        project_root=args.project_root.resolve(),
        explicit_as_of=args.as_of,
        strict=bool(args.strict),
        daily_root=args.project_root.resolve() / "exports" / "daily",
    )
    as_of = resolution.as_of
    output_dir = args.output_dir or (args.project_root / "exports" / "diagnostics" / as_of)
    report = run_system_doctor(
        project_root=args.project_root,
        as_of=as_of,
        output_dir=output_dir,
        strict=bool(args.strict),
        entry_point=args.entry_point,
        runtime_mode=str(args.runtime_mode),
        truth_source=str(args.truth_source),
        validation_dir=args.validation_dir,
        pack_root=args.pack_root,
        ledger_root=args.ledger_root,
        download_run_id=args.download_run_id,
    )

    print(f"system_health_json={report['json_path']}")
    print(f"system_health_md={report['md_path']}")
    print(f"system_health_checks={report['checks_path']}")
    print(f"as_of_source={resolution.source}")
    print(f"status={report['status']}")
    if report["blocked_layer"]:
        print(f"blocked_layer={report['blocked_layer']}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
