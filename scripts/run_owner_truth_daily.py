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
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def _default_webui_ledger_root(root: Path) -> Path:
    full_parse = root / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    if full_parse.exists():
        return full_parse
    return root / "exports" / "order_status_ledger" / "webui_status_ledger_20260306"


def _resolve_pack_root_from_ledger(ledger_root: Path) -> Path | None:
    manifest = _load_json(ledger_root / "ledger_manifest.json")
    if not isinstance(manifest, dict):
        return None
    pack_roots = manifest.get("pack_roots")
    if not isinstance(pack_roots, list):
        return None
    for raw_path in pack_roots:
        candidate = Path(str(raw_path)).expanduser().resolve()
        if candidate.exists():
            return candidate
    return None


def _run(cmd: str, *, cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str, float]:
    started = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        shell=True,
        text=True,
        capture_output=True,
        env=env,
    )
    duration = round(time.perf_counter() - started, 3)
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
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
            _resolve_pack_root_from_ledger(resolved_ledger_root)
            or (root / "exports" / "webui_archive_packs" / "webui_archive_seed_20260306")
        )
    )
    resolved_download_run_id = download_run_id or "webui_archive_download_20260306"
    resolved_workbook = (
        root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
        if (root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx").exists()
        else root / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    )
    resolved_workbook_map_output = root / "exports" / "validation" / "workbook_catalog_offer_map_sync"

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
                f"--reference-csv {shlex.quote(str(root / 'exports' / 'validation' / 'identity_stabilization' / as_of_str / 'offer_identity_reference.csv'))} "
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
                f"--as-of {shlex.quote(as_of_str)} --strict"
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
            "triage_owner_truth_stoplines",
            (
                "python3 scripts/triage_owner_truth_stoplines.py "
                f"--as-of {shlex.quote(as_of_str)} "
                f"--truth-source {shlex.quote(truth_source)} "
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

    if truth_source == "webui_archive":
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
    else:
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

    step_cmds.insert(
        8 if truth_source == "webui_archive" else 8,
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
    step_cmds.insert(
        9 if truth_source == "webui_archive" else 9,
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
    step_cmds.insert(
        10 if truth_source == "webui_archive" else 10,
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
    step_cmds.insert(
        11 if truth_source == "webui_archive" else 11,
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

    if stopline_code is None:
        for name, cmd, env in step_cmds:
            rc, out, dur = _run(cmd, cwd=root, env=env)
            _record(name, cmd, rc, out, dur)
            if rc != 0:
                stopline_code = f"{name.upper()}_FAIL"
                break

    overall_ok = stopline_code is None
    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_str,
        "since": since.isoformat(),
        "status": "PASS" if overall_ok else "FAIL",
        "ok": overall_ok,
        "error_code": stopline_code,
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
