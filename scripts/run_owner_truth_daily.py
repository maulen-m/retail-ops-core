#!/usr/bin/env python3
"""Run owner-truth daily strict pipeline with fail-closed stopline behavior."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.resolve_owner_truth_runtime_mode import RuntimeModeError, resolve_owner_truth_runtime_mode
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "owner_truth_daily"
DEFAULT_SUMMARY_ROOT = PROJECT_ROOT / "exports" / "daily"


class OwnerTruthDailyError(RuntimeError):
    """Raised when owner truth daily run fails."""


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


def _resolve_validation_dir(root: Path, *, truth_source: str, as_of: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    publication_fallback = _publication_validation_dir(root, as_of)
    if truth_source == "webui_archive":
        closeout = root / "exports" / "validation" / "ads_scope_closeout" / as_of
        if closeout.exists():
            return closeout
        if publication_fallback is not None:
            return publication_fallback
        default = root / "exports" / "validation" / "webui_archive_single_truth" / as_of
    else:
        default = root / "exports" / "validation" / "crm_north_star_restate" / as_of
    if default.exists():
        return default
    if publication_fallback is not None:
        return publication_fallback
    return default


def _resolve_live_workbook_anchor(root: Path) -> Path:
    raw = os.environ.get("AB_CRM_WORKBOOK_PATH", "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        if candidate.exists():
            return candidate.resolve()
        raise OwnerTruthDailyError(f"AB_CRM_WORKBOOK_PATH does not exist: {candidate}")

    anchored = root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    if anchored.exists():
        return anchored.resolve()

    raise OwnerTruthDailyError(
        "AB_CRM_WORKBOOK_PATH is required for live owner-truth runs; "
        "missing config/anchors/SALES_KSP_CRM_LATEST.xlsx"
    )


def _default_webui_ledger_root(root: Path) -> Path:
    full_parse = root / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    if full_parse.exists():
        return full_parse
    return root / "exports" / "order_status_ledger" / "webui_status_ledger_20260306"


def _resolve_pack_root_from_ledger(ledger_root: Path, project_root: Path) -> Path | None:
    manifest = _load_json(ledger_root / "ledger_manifest.json")
    if not isinstance(manifest, dict):
        return None
    pack_roots = manifest.get("pack_roots")
    project_root = project_root.resolve()
    local_exports_root = project_root / "exports"

    if isinstance(pack_roots, list):
        for raw_path in pack_roots:
            candidate = Path(str(raw_path)).expanduser().resolve()
            if candidate.exists() and str(candidate).startswith(str(project_root)):
                return candidate

    pack_ids = manifest.get("pack_ids")
    if not isinstance(pack_ids, list):
        return None

    for raw_pack_id in pack_ids:
        pack_id = str(raw_pack_id).strip()
        if not pack_id:
            continue
        local_matches = sorted((local_exports_root / "webui_archive_full_parse_runs").glob(f"*/pack_outputs/{pack_id}"))
        for candidate in local_matches:
            if candidate.exists():
                return candidate.resolve()

    if not isinstance(pack_roots, list):
        return None
    for raw_path in pack_roots:
        candidate = Path(str(raw_path)).expanduser().resolve()
        if "exports" not in candidate.parts:
            continue
        parts = list(candidate.parts)
        exports_idx = parts.index("exports")
        relative = Path(*parts[exports_idx + 1 :])
        local_candidate = (local_exports_root / relative).resolve()
        if local_candidate.exists():
            return local_candidate
        if candidate.exists():
            return candidate
    return None


def _infer_project_root_from_exports_path(path: Path) -> Path | None:
    candidate = path.expanduser().resolve()
    if "exports" not in candidate.parts:
        return None
    parts = list(candidate.parts)
    exports_idx = parts.index("exports")
    if exports_idx == 0:
        return None
    return Path(*parts[:exports_idx]).resolve()


def _resolve_default_download_run_id(project_root: Path, pack_root: Path | None) -> str:
    local_download_root = project_root / "exports" / "webui_archive_download_runs"
    local_canonical = local_download_root / "webui_archive_download_20260306"
    if local_canonical.exists():
        return str(local_canonical.resolve())

    if pack_root is not None:
        source_root = _infer_project_root_from_exports_path(pack_root)
        if source_root is not None:
            external_canonical = source_root / "exports" / "webui_archive_download_runs" / "webui_archive_download_20260306"
            if external_canonical.exists():
                return str(external_canonical.resolve())

    return "webui_archive_download_20260306"


def _run(cmd: str, *, cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    started = time.perf_counter()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as capture:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            shell=True,
            text=True,
            stdout=capture,
            stderr=subprocess.STDOUT,
            capture_output=False,
            env=env,
        )
        capture.seek(0)
        output = capture.read().strip()
    duration = round(time.perf_counter() - started, 3)
    return int(proc.returncode), output, duration


def _parse_backup_path(output: str, cwd: Path) -> str | None:
    for line in output.splitlines():
        txt = line.strip()
        if txt.startswith("Backup created:"):
            candidate = txt.split(":", 1)[1].strip()
            p = Path(candidate)
            if not p.is_absolute():
                p = (cwd / candidate).resolve()
            return str(p)
    return None


def run_owner_truth_daily(
    *,
    as_of: date,
    since: date,
    north_star_start: date,
    north_star_end: date,
    project_root: Path,
    output_root: Path,
    summary_root: Path,
    strict: bool,
    apply: bool,
    truth_source: str = "webui_archive",
    validation_dir: Path | None = None,
    pack_root: Path | None = None,
    ledger_root: Path | None = None,
    download_run_id: str | None = None,
    runtime_mode: str = "live",
) -> dict[str, Any]:
    root = project_root.resolve()
    as_of_str = as_of.isoformat()
    north_star_start_str = north_star_start.isoformat()
    north_star_end_str = north_star_end.isoformat()
    out_dir = output_root.resolve() / as_of_str
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / "full_run_transcript.md"

    if apply and os.environ.get("ENABLE_OWNER_TRUTH_APPLY") != "1":
        raise OwnerTruthDailyError("ENABLE_OWNER_TRUTH_APPLY=1 is required when using --apply")

    steps: list[dict[str, Any]] = []
    stopline_code = None
    backup_path = None

    def _record(name: str, cmd: str, rc: int, output: str, duration: float) -> None:
        steps.append(
            {
                "step": name,
                "cmd": cmd,
                "rc": rc,
                "ok": rc == 0,
                "duration_sec": duration,
                "output": output,
            }
        )

    if apply:
        backup_cmd = "python3 scripts/backup_db.py --db db/app.db --dest runtime/backups --keep-days 30"
        rc, out, dur = _run(backup_cmd, cwd=root)
        _record("backup_db", backup_cmd, rc, out, dur)
        backup_path = _parse_backup_path(out, root)
        if rc != 0:
            stopline_code = "DB_BACKUP_FAILED"
    resolved_validation_dir = _resolve_validation_dir(
        root,
        truth_source=truth_source,
        as_of=as_of_str,
        explicit=validation_dir,
    )
    resolved_ledger_root = (ledger_root.resolve() if ledger_root is not None else _default_webui_ledger_root(root))
    resolved_pack_root = (
        pack_root.resolve()
        if pack_root is not None
        else (
            _resolve_pack_root_from_ledger(resolved_ledger_root, root)
            or (root / "exports" / "webui_archive_packs" / "webui_archive_seed_20260306")
        )
    )
    resolved_download_run_id = (
        str(download_run_id.resolve())
        if isinstance(download_run_id, Path)
        else (download_run_id or _resolve_default_download_run_id(root, resolved_pack_root))
    )
    resolved_workbook = (
        root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
        if (root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx").exists()
        else root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    )
    resolved_workbook_map_output = root / "exports" / "validation" / "workbook_catalog_offer_map_sync"
    identity_validation_root = root / "exports" / "validation" / "identity_stabilization"
    identity_replay_output_root = root / "exports" / "validation" / "identity_replay_anchor"
    try:
        runtime_mode_report = resolve_owner_truth_runtime_mode(
            project_root=root,
            as_of=as_of_str,
            mode=runtime_mode,
            strict=bool(strict),
        )
    except RuntimeModeError as exc:
        raise OwnerTruthDailyError(str(exc)) from exc
    live_workbook_env = None
    if runtime_mode_report["mode"] == "live":
        live_workbook_env = {
            **os.environ,
            "AB_CRM_WORKBOOK_PATH": str(_resolve_live_workbook_anchor(root)),
        }

    daily_ops_summary_json = Path(str(runtime_mode_report["daily_ops_summary_json"]))
    ops_selection_seed_json = Path(str(runtime_mode_report["ops_selection_seed_json"]))
    daily_ops_output_dir = summary_root.resolve() / as_of_str
    exceptions_output_dir = root / "exports" / "exceptions" / as_of_str
    step_cmds: list[tuple[str, str, dict[str, str] | None]] = [
        (
            "export_sales_archive_statusdate_mapped",
            (
                "python3 scripts/export_sales_archive_statusdate_mapped.py "
                f"--since {shlex.quote(since.isoformat())} "
                f"--until {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "generate_business_insides",
            (
                "python3 scripts/generate_business_insides.py "
                f"--as-of {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "generate_daily_ops_report",
            (
                "python3 scripts/generate_daily_ops_report.py "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--summary-json {shlex.quote(str(daily_ops_summary_json))} "
                f"--output-dir {shlex.quote(str(daily_ops_output_dir))}"
            ),
            None,
        ),
        (
            "validate_daily_ops_report",
            (
                "python3 scripts/validate_daily_ops_report.py "
                f"--strict --path {shlex.quote(str(daily_ops_output_dir / 'daily_ops_report.json'))}"
            ),
            None,
        ),
        (
            "validate_reference_freshness",
            (
                "python3 scripts/validate_reference_freshness.py "
                f"--as-of {shlex.quote(as_of_str)} "
                "--max-delivery-lag-days 7 "
                f"--statusdate-cutover {shlex.quote(os.environ.get('AB_STATUSDATE_CUTOVER', '2026-02-27'))} "
                "--strict"
            ),
            None,
        ),
        (
            "import_web_automation_offer_identity",
            (
                "python3 scripts/import_web_automation_offer_identity.py "
                f"--as-of {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "import_kaspi_article_map_from_crm",
            (
                "python3 scripts/import_kaspi_article_map_from_crm.py "
                f"--workbook {shlex.quote(str(resolved_workbook))} "
                f"--sheet M02_SKU_CATALOG_NC "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--output-root {shlex.quote(str(resolved_workbook_map_output))}"
                + (" --apply" if apply else "")
            ),
            ({**os.environ, "ENABLE_KASPI_WORKBOOK_MAP_SYNC": "1"} if apply else None),
        ),
        (
            "validate_external_snapshot_parity",
            (
                "python3 scripts/validate_external_snapshot_parity.py "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--reference-csv {shlex.quote(str(identity_validation_root / as_of_str / 'offer_identity_reference.csv'))} "
                "--strict"
            ),
            None,
        ),
        (
            "validate_recent_identity_coverage",
            (
                "python3 scripts/validate_recent_identity_coverage.py "
                f"--as-of {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "validate_order_entries_freshness",
            (
                "python3 scripts/validate_order_entries_freshness.py "
                f"--as-of {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "sync_ads_sidecar",
            (
                "python3 scripts/sync_ads_sidecar.py "
                f"--since {shlex.quote(since.isoformat())} --until {shlex.quote(as_of_str)}"
                + (" --apply" if apply else "")
            ),
            ({**os.environ, "ENABLE_CASHFLOW_WRITE": "1"} if apply else None),
        ),
        (
            "validate_ads_sidecar_readiness",
            (
                "python3 scripts/validate_ads_sidecar_readiness.py "
                f"--as-of {shlex.quote(as_of_str)} --readiness-mode live --strict"
            ),
            None,
        ),
        (
            "validate_opex_readiness",
            (
                "python3 scripts/validate_opex_readiness.py "
                f"--as-of {shlex.quote(as_of_str)} --strict"
            ),
            None,
        ),
        (
            "validate_returns_economics_audit",
            (
                "python3 scripts/validate_returns_economics_audit.py "
                f"--as-of {shlex.quote(as_of_str)} --since {shlex.quote(since.isoformat())} --strict"
            ),
            None,
        ),
        (
            "validate_monthly_cash_reconciliation",
            (
                "python3 scripts/validate_monthly_cash_reconciliation.py "
                f"--as-of {shlex.quote(as_of_str)} --since {shlex.quote(since.isoformat())} --strict"
            ),
            None,
        ),
        (
            "system_doctor",
            (
                "python3 scripts/system_doctor.py --strict --project-root . "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--truth-source {shlex.quote(truth_source)} "
                f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                + (
                    f"--pack-root {shlex.quote(str(resolved_pack_root))} "
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    f"--download-run-id {shlex.quote(str(resolved_download_run_id))}"
                    if truth_source == "webui_archive"
                    else ""
                )
            ),
            live_workbook_env,
        ),
        (
            "build_owner_pnl_report",
            (
                "python3 scripts/build_owner_pnl_report.py "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--since {shlex.quote(since.isoformat())} "
                f"--truth-source {shlex.quote(truth_source)} "
                f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                + (
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    if truth_source == "webui_archive"
                    else ""
                )
                + "--include-store-breakdown --strict"
            ),
            None,
        ),
        (
            "triage_owner_truth_stoplines",
            (
                "python3 scripts/triage_owner_truth_stoplines.py "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--truth-source {shlex.quote(truth_source)} "
                f"--runtime-mode {shlex.quote(str(runtime_mode_report['mode']))} "
                f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                + (
                    f"--pack-root {shlex.quote(str(resolved_pack_root))} "
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    f"--download-run-id {shlex.quote(str(resolved_download_run_id))} "
                    if truth_source == "webui_archive"
                    else ""
                )
                + "--strict"
            ),
            None,
        ),
    ]
    if runtime_mode_report["mode"] == "replay":
        step_cmds = [
            (
                "export_sales_archive_statusdate_mapped",
                (
                    "python3 scripts/export_sales_archive_statusdate_mapped.py "
                    f"--since {shlex.quote(since.isoformat())} "
                    f"--until {shlex.quote(as_of_str)} --strict"
                ),
                None,
            ),
            (
                "generate_business_insides",
                (
                    "python3 scripts/generate_business_insides.py "
                    f"--as-of {shlex.quote(as_of_str)} --strict"
                ),
                None,
            ),
            (
                "generate_daily_ops_report",
                (
                    "python3 scripts/generate_daily_ops_report.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--summary-json {shlex.quote(str(daily_ops_summary_json))} "
                    f"--output-dir {shlex.quote(str(daily_ops_output_dir))}"
                ),
                None,
            ),
            (
                "generate_owner_truth_exceptions",
                (
                    "python3 scripts/generate_owner_truth_exceptions.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--daily-report-json {shlex.quote(str(daily_ops_output_dir / 'daily_ops_report.json'))} "
                    f"--output-dir {shlex.quote(str(exceptions_output_dir))} "
                    "--strict"
                ),
                None,
            ),
            (
                "validate_identity_replay_anchor",
                (
                    "python3 scripts/validate_identity_replay_anchor.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--identity-root {shlex.quote(str(identity_validation_root))} "
                    f"--output-root {shlex.quote(str(identity_replay_output_root))} "
                    "--strict"
                ),
                None,
            ),
            (
                "build_owner_pnl_report",
                (
                    "python3 scripts/build_owner_pnl_report.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--since {shlex.quote(since.isoformat())} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--include-store-breakdown --strict"
                ),
                None,
            ),
            (
                "build_north_star_owner_review",
                (
                    "python3 scripts/build_north_star_owner_review.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                    f"--owner-pnl-json {shlex.quote(str(root / 'exports' / 'owner_pnl' / as_of_str / 'OWNER_PNL.json'))} "
                    f"--output-dir {shlex.quote(str(root / 'exports' / 'north_star_owner_review' / as_of_str))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
            (
                "triage_owner_truth_stoplines",
                (
                    "python3 scripts/triage_owner_truth_stoplines.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--runtime-mode {shlex.quote(str(runtime_mode_report['mode']))} "
                    f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--pack-root {shlex.quote(str(resolved_pack_root))} "
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        f"--download-run-id {shlex.quote(str(resolved_download_run_id))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        ]
        if bool(runtime_mode_report["use_ops_selection_seed"]):
            step_cmds.insert(
                1,
                (
                    "generate_ops_selection_artifacts",
                    (
                        "python3 scripts/generate_ops_selection_artifacts.py "
                        f"--as-of {shlex.quote(as_of_str)} "
                        f"--seed-json {shlex.quote(str(ops_selection_seed_json))} "
                        "--strict"
                    ),
                    None,
                ),
            )
    else:
        if bool(runtime_mode_report["run_kaspi_daily_ops"]):
            step_cmds.insert(
                2,
            (
                "run_kaspi_daily_ops",
                (
                    "python3 scripts/run_kaspi_daily_ops.py "
                    f"--as-of {shlex.quote(as_of_str)}"
                ),
                live_workbook_env,
            ),
        )

        if bool(runtime_mode_report["use_ops_selection_seed"]):
            step_cmds.insert(
                3,
                (
                    "generate_ops_selection_artifacts",
                    (
                        "python3 scripts/generate_ops_selection_artifacts.py "
                        f"--as-of {shlex.quote(as_of_str)} "
                        f"--seed-json {shlex.quote(str(ops_selection_seed_json))} "
                        "--strict"
                    ),
                    None,
                ),
            )

        step_cmds.insert(
            next(i for i, existing in enumerate(step_cmds) if existing[0] == "validate_reference_freshness"),
            (
                "generate_owner_truth_exceptions",
                (
                    "python3 scripts/generate_owner_truth_exceptions.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--daily-report-json {shlex.quote(str(daily_ops_output_dir / 'daily_ops_report.json'))} "
                    f"--output-dir {shlex.quote(str(exceptions_output_dir))} "
                    "--strict"
                ),
                None,
            ),
        )

    if runtime_mode_report["mode"] != "replay" and truth_source == "webui_archive":
        step_cmds[6:6] = [
            (
                "validate_webui_archive_pack_integrity",
                (
                    "python3 scripts/validate_webui_archive_pack_integrity.py "
                    f"--pack-root {shlex.quote(str(resolved_pack_root))} --strict"
                ),
                None,
            ),
            (
                "validate_status_ledger_continuity",
                (
                    "python3 scripts/validate_status_ledger_continuity.py "
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} --strict"
                ),
                None,
            ),
            (
                "validate_webui_crm_shipped_day_authority",
                (
                    "python3 scripts/validate_webui_crm_shipped_day_authority.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    "--strict"
                ),
                None,
            ),
            (
                "validate_sales_against_workbook",
                (
                    "python3 scripts/validate_sales_against_workbook.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    "--strict"
                ),
                None,
            ),
            (
                "validate_webui_archive_vs_current_db",
                (
                    "python3 scripts/validate_webui_archive_vs_current_db.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    "--strict"
                ),
                None,
            ),
            (
                "validate_webui_archive_vs_current_db_full_range",
                (
                    "python3 scripts/validate_webui_archive_vs_current_db.py "
                    f"--start {shlex.quote(since.isoformat())} "
                    f"--end {shlex.quote(as_of_str)} "
                    f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir / 'full_range_db_gate'))} "
                    "--range-policy full_range_owner_truth "
                    f"--statusdate-cutover {shlex.quote(os.environ.get('AB_STATUSDATE_CUTOVER', '2026-02-27'))} "
                    "--strict"
                ),
                None,
            ),
            (
                "validate_playwright_archive_downloads",
                (
                    "python3 scripts/validate_playwright_archive_downloads.py "
                    f"--run-id {shlex.quote(str(resolved_download_run_id))} --strict"
                ),
                None,
            ),
            (
                "validate_order_status_audit_history",
                (
                    "python3 scripts/validate_order_status_audit_history.py "
                    f"--as-of {shlex.quote(as_of_str)} --strict"
                ),
                None,
            ),
        ]
    elif runtime_mode_report["mode"] != "replay":
        step_cmds.insert(
            6,
            (
                "validate_sales_against_workbook",
                (
                    "python3 scripts/validate_sales_against_workbook.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    "--strict"
                ),
                None,
            ),
        )

    if not apply:
        step_cmds = [item for item in step_cmds if item[0] != "sync_ads_sidecar"]

    def _insert_after(step_name: str, item: tuple[str, str, dict[str, str] | None]) -> None:
        idx = next(i for i, existing in enumerate(step_cmds) if existing[0] == step_name)
        step_cmds.insert(idx + 1, item)

    ads_dependency_step = (
        "validate_webui_archive_vs_current_db" if truth_source == "webui_archive" else "validate_sales_against_workbook"
    )

    if runtime_mode_report["mode"] != "replay":
        _insert_after(
            ads_dependency_step,
            (
                "validate_ads_offer_universe_coverage",
                (
                    "python3 scripts/validate_ads_offer_universe_coverage.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        )
        _insert_after(
            "validate_ads_offer_universe_coverage",
            (
                "validate_ads_spend_reality",
                (
                    "python3 scripts/validate_ads_spend_reality.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        )
        _insert_after(
            "validate_ads_spend_reality",
            (
                "validate_cogs_completeness_by_month",
                (
                    "python3 scripts/validate_cogs_completeness_by_month.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        )
        _insert_after(
            "validate_cogs_completeness_by_month",
            (
                "validate_cogs_realism_vs_forensic",
                (
                    "python3 scripts/validate_cogs_realism_vs_forensic.py "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--output-dir {shlex.quote(str(resolved_validation_dir))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        )
        triage_idx = next(i for i, item in enumerate(step_cmds) if item[0] == "triage_owner_truth_stoplines")
        step_cmds.insert(
            triage_idx,
            (
                "build_north_star_owner_review",
                (
                    "python3 scripts/build_north_star_owner_review.py "
                    f"--as-of {shlex.quote(as_of_str)} "
                    f"--start {shlex.quote(north_star_start_str)} "
                    f"--end {shlex.quote(north_star_end_str)} "
                    f"--truth-source {shlex.quote(truth_source)} "
                    f"--validation-dir {shlex.quote(str(resolved_validation_dir))} "
                    f"--owner-pnl-json {shlex.quote(str(root / 'exports' / 'owner_pnl' / as_of_str / 'OWNER_PNL.json'))} "
                    f"--output-dir {shlex.quote(str(root / 'exports' / 'north_star_owner_review' / as_of_str))} "
                    + (
                        f"--ledger-root {shlex.quote(str(resolved_ledger_root))} "
                        if truth_source == "webui_archive"
                        else ""
                    )
                    + "--strict"
                ),
                None,
            ),
        )

    allowed_after_failure: set[str] = set()
    if stopline_code is None:
        for name, cmd, env in step_cmds:
            if stopline_code is not None and name not in allowed_after_failure:
                break
            rc, out, dur = _run(cmd, cwd=root, env=env)
            _record(name, cmd, rc, out, dur)
            if stopline_code is not None and name in allowed_after_failure:
                if rc == 0:
                    allowed_after_failure.discard(name)
                else:
                    allowed_after_failure.clear()
                continue
            if rc != 0:
                stopline_code = f"{name.upper()}_FAIL"
                if name == "run_kaspi_daily_ops":
                    allowed_after_failure = {"generate_daily_ops_report", "validate_daily_ops_report"}
                    continue
                break

    overall_ok = stopline_code is None
    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_str,
        "since": since.isoformat(),
        "status": "PASS" if overall_ok else "FAIL",
        "ok": overall_ok,
        "error_code": stopline_code,
        "runtime_mode": runtime_mode_report["mode"],
        "runtime_mode_report": runtime_mode_report,
        "apply": bool(apply),
        "backup_path": backup_path,
        "steps": [{k: v for k, v in row.items() if k != "output"} for row in steps],
        "failed_step": next((row["step"] for row in steps if not row["ok"]), None),
    }

    summary_dir = summary_root.resolve() / as_of_str
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "owner_truth_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Owner Truth Daily Run Transcript",
        "",
        f"- as_of: `{as_of_str}`",
        f"- since: `{since.isoformat()}`",
        f"- status: `{summary['status']}`",
        f"- error_code: `{summary.get('error_code') or 'none'}`",
        f"- runtime_mode: `{runtime_mode_report['mode']}`",
        f"- apply: `{str(bool(apply)).lower()}`",
        f"- backup_path: `{backup_path or 'n/a'}`",
        "",
    ]
    for row in steps:
        md_lines.append(f"## {row['step']}")
        md_lines.append("")
        md_lines.append(f"- cmd: `{row['cmd']}`")
        md_lines.append(f"- rc: `{row['rc']}`")
        md_lines.append(f"- duration_sec: `{row['duration_sec']}`")
        md_lines.append("")
        md_lines.append("```text")
        md_lines.append(row["output"])
        md_lines.append("```")
        md_lines.append("")
    transcript_path.write_text("\n".join(md_lines), encoding="utf-8")

    summary["summary_path"] = str(summary_path)
    summary["transcript_path"] = str(transcript_path)

    if strict and not overall_ok:
        raise OwnerTruthDailyError(f"owner truth daily failed: {stopline_code}")
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run owner truth daily strict autopilot")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--since", default="2025-06-06")
    parser.add_argument("--north-star-start", default="2026-01-01")
    parser.add_argument("--north-star-end", default="2026-02-28")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--summary-root", type=Path, default=DEFAULT_SUMMARY_ROOT)
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="webui_archive")
    parser.add_argument("--validation-dir", type=Path, default=None)
    parser.add_argument("--pack-root", type=Path, default=None)
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--download-run-id", default=None)
    parser.add_argument("--mode", choices=["live", "replay"], default="live")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        summary = run_owner_truth_daily(
            as_of=date.fromisoformat(str(args.as_of)),
            since=date.fromisoformat(str(args.since)),
            north_star_start=date.fromisoformat(str(args.north_star_start)),
            north_star_end=date.fromisoformat(str(args.north_star_end)),
            project_root=args.project_root,
            output_root=args.output_root,
            summary_root=args.summary_root,
            strict=bool(args.strict),
            apply=bool(args.apply),
            truth_source=str(args.truth_source),
            validation_dir=args.validation_dir,
            pack_root=args.pack_root,
            ledger_root=args.ledger_root,
            download_run_id=args.download_run_id,
            runtime_mode=str(args.mode),
        )
    except OwnerTruthDailyError as exc:
        print("status=FAIL")
        print("error_code=OWNER_TRUTH_DAILY_FAIL")
        print(f"message={exc}")
        return 1

    print(f"owner_truth_daily_summary={summary['summary_path']}")
    print(f"owner_truth_daily_transcript={summary['transcript_path']}")
    print(f"status={summary['status']}")
    if summary.get("error_code"):
        print(f"error_code={summary['error_code']}")
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
