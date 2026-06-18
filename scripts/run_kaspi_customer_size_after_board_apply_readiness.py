#!/usr/bin/env python3
"""Build the local readiness bridge after Google Board MY_SIZE apply.

This helper is intentionally no-write. It accepts the Google Board apply
manifest, proves the board patch is actually applied/already-current with
readback, runs or consumes the size-writeback dry-run, checks the closeout
readiness conditions, and emits the exact next handoff for the existing Google
Ops Board closeout runner.

It never writes Google Board, DB, Kaspi, waybills, Telegram/WhatsApp, workbook,
price, stock, cash, supplier, PO, or scheduler state.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.integrations.google_ops_board import (
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.ops.customer_size_request import sha256_file
from scripts.run_google_ops_board_closeout import build_readiness_report
from scripts.sync_google_ops_board_sizes_to_db import main as size_writeback_main


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "exports" / "validation"

GREEN_APPLY_GATES = {
    "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_APPLIED_AND_READBACK_VERIFIED",
    "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_ALREADY_CURRENT_NO_WRITE",
}
GREEN_GATE = "GREEN_AFTER_GOOGLE_BOARD_MY_SIZE_APPLY_CLOSEOUT_RESUME_READY_NO_WRITE"
YELLOW_GATE = "YELLOW_AFTER_GOOGLE_BOARD_MY_SIZE_APPLY_CLOSEOUT_RESUME_BLOCKED_NO_WRITE"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _parse_date(value: str | None) -> date:
    text = str(value or "").strip().lower()
    if text in ("", "today"):
        return date.today()
    if text == "tomorrow":
        return date.today() + timedelta(days=1)
    return date.fromisoformat(text)


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"kaspi_customer_size_after_board_apply_readiness_{target_date.isoformat()}_{stamp}"


def _latest_board_apply_manifest() -> Path | None:
    candidates = sorted(
        DEFAULT_OUTPUT_ROOT.glob("kaspi_customer_size_google_board_my_size_apply_*/manifest.json")
    )
    return candidates[-1] if candidates else None


def _board_apply_blockers(manifest: dict[str, Any]) -> list[str]:
    gate = str(manifest.get("gate") or "")
    blockers: list[str] = []
    if gate not in GREEN_APPLY_GATES:
        blockers.append(f"google_board_apply_gate={gate or 'MISSING'}")
        return blockers
    if bool(manifest.get("google_board_write_performed")) and not bool(
        manifest.get("post_apply_readback_verified")
    ):
        blockers.append("google_board_apply_readback_not_verified")
    if gate == "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_APPLIED_AND_READBACK_VERIFIED":
        if not bool(manifest.get("google_board_write_performed")):
            blockers.append("google_board_apply_green_without_write_flag")
        if not bool(manifest.get("post_apply_readback_verified")):
            blockers.append("google_board_apply_green_without_readback_flag")
    if gate == "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_ALREADY_CURRENT_NO_WRITE":
        if not bool(manifest.get("post_apply_readback_verified")):
            blockers.append("google_board_already_current_without_readback_flag")
        if not bool(manifest.get("live_board_readback")):
            blockers.append("google_board_already_current_without_live_readback")
    return blockers


def _run_size_writeback_dry_run(
    *,
    output_dir: Path,
    db_path: Path,
    target_date: date,
    lookback_days: int,
    contract_path: Path,
    service_account_json: Path | None,
    spreadsheet_id: str | None,
    existing_report: Path | None,
) -> tuple[int, dict[str, Any], Path]:
    if existing_report:
        report_path = existing_report.resolve()
        return 0, _read_json(report_path), report_path

    report_path = output_dir / "size_writeback_dry_run.json"
    args = [
        "--db",
        str(db_path),
        "--contract",
        str(contract_path),
        "--target-date",
        target_date.isoformat(),
        "--lookback-days",
        str(lookback_days),
        "--output-json",
        str(report_path),
    ]
    if service_account_json:
        args.extend(["--service-account-json", str(service_account_json)])
    if spreadsheet_id:
        args.extend(["--spreadsheet-id", spreadsheet_id])
    rc = size_writeback_main(args)
    report = _read_json(report_path) if report_path.exists() else {}
    return rc, report, report_path


def _size_writeback_blockers(report: dict[str, Any], rc: int) -> list[str]:
    blockers: list[str] = []
    if rc != 0:
        blockers.append(f"size_writeback_dry_run_rc={rc}")
    if bool(report.get("apply")):
        blockers.append("size_writeback_report_is_apply_mode")
    if int(report.get("invalid_rows_count") or 0) != 0:
        blockers.append(f"size_writeback_invalid_rows={report.get('invalid_rows_count')}")
    if int(report.get("updates_applied") or 0) != 0:
        blockers.append("size_writeback_report_applied_updates")
    if report.get("db_backup_path"):
        blockers.append("size_writeback_report_created_db_backup")
    return blockers


def _redact_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    blank_rows = []
    for row in readiness.get("blank_size_rows") or []:
        blank_rows.append(
            {
                "_db_row_id": row.get("_db_row_id"),
                "Status": row.get("Status"),
                "Date": row.get("Date"),
                "STORE_NAME": row.get("STORE_NAME"),
                "raw_order_id_exported": False,
            }
        )
    invalid_rows = []
    for row in readiness.get("invalid_size_rows") or []:
        invalid_rows.append(
            {
                "target_key": row.get("target_key"),
                "product_type": row.get("product_type"),
                "store_code": row.get("store_code"),
                "raw_order_id_exported": False,
            }
        )
    return {
        "target_date": readiness.get("target_date"),
        "ready": bool(readiness.get("ready")),
        "run_control_target_match": bool(readiness.get("run_control_target_match")),
        "run_control_ready_value": readiness.get("run_control_ready_value"),
        "run_control_ready_ok": bool(readiness.get("run_control_ready_ok")),
        "salesraw_row_count": int(readiness.get("salesraw_row_count") or 0),
        "blank_size_count": int(readiness.get("blank_size_count") or 0),
        "invalid_size_count": int(readiness.get("invalid_size_count") or 0),
        "pending_db_writeback_count": int(readiness.get("pending_db_writeback_count") or 0),
        "blank_size_rows_redacted": blank_rows,
        "invalid_size_rows_redacted": invalid_rows,
        "raw_order_id_exported": False,
    }


def _load_or_build_readiness(
    *,
    db_path: Path,
    target_date: date,
    lookback_days: int,
    contract_path: Path,
    service_account_json: Path | None,
    spreadsheet_id: str | None,
    existing_report: Path | None,
) -> tuple[dict[str, Any], str]:
    if existing_report:
        return _read_json(existing_report.resolve()), str(existing_report.resolve())

    contract = load_ops_board_contract(contract_path)
    service_account = resolve_service_account_json(service_account_json, contract=contract)
    resolved_spreadsheet_id = resolve_spreadsheet_id(spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(resolved_spreadsheet_id, service_account)
    readiness = build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=target_date,
        lookback_days=lookback_days,
    )
    return readiness, "live_google_board_redacted_summary"


def _readiness_blockers(readiness_summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not bool(readiness_summary.get("run_control_target_match")):
        blockers.append("run_control_target_mismatch")
    if not bool(readiness_summary.get("run_control_ready_ok")):
        blockers.append(f"run_control_ready_value={readiness_summary.get('run_control_ready_value')}")
    if int(readiness_summary.get("blank_size_count") or 0) != 0:
        blockers.append(f"blank_size_rows={readiness_summary.get('blank_size_count')}")
    if int(readiness_summary.get("invalid_size_count") or 0) != 0:
        blockers.append(f"closeout_invalid_size_rows={readiness_summary.get('invalid_size_count')}")
    if not bool(readiness_summary.get("ready")):
        blockers.append("closeout_readiness_ready_false")
    return blockers


def _approval_phrase(
    *,
    board_apply_manifest: Path,
    board_apply_sha: str | None,
    size_report: Path,
    size_report_sha: str | None,
    readiness_summary: Path,
    readiness_summary_sha: str | None,
    target_date: date,
    lookback_days: int,
) -> str:
    return (
        "I approve KASPI_CUSTOMER_SIZE_AFTER_BOARD_APPLY_CLOSEOUT_RESUME: run the existing "
        "Google Ops Board closeout runner for customer-size completion after verified Board "
        f"MY_SIZE apply, target_date={target_date.isoformat()}, lookback_days={lookback_days}, "
        "allowing only the existing fail-closed closeout stages: DB size writeback from Google "
        "Board MY_SIZE, DB-first shipping, waybill download/build, delivery send through the "
        "configured waybill channel, and shipped-truth sync. Board apply manifest: "
        f"{board_apply_manifest} / sha256={board_apply_sha}. Size-writeback dry-run: "
        f"{size_report} / sha256={size_report_sha}. Closeout readiness summary: "
        f"{readiness_summary} / sha256={readiness_summary_sha}. No Kaspi customer chat sends/"
        "reads, no unrelated Google Board edits, no price/stock/cash/supplier/PO changes, no "
        "workbook manual edits, no scheduler/source-pointer changes, no unrelated DB writes, "
        "and no owner-publication actions are approved."
    )


def _handoff(
    *,
    manifest: dict[str, Any],
    approval_phrase: str,
    closeout_command: str,
) -> str:
    return "\n".join(
        [
            "# Kaspi Customer Size After Board Apply Closeout Resume Handoff",
            "",
            f"Gate: {manifest['gate']}",
            "",
            "## Mission",
            "",
            "After the owner provides the exact approval phrase, run the existing Google Ops Board closeout path so the Board MY_SIZE truth can flow into DB size assignment and the normal waybill/delivery workflow can resume.",
            "",
            "## Required Exact Owner Approval",
            "",
            "```text",
            approval_phrase,
            "```",
            "",
            "## Command",
            "",
            "```bash",
            closeout_command,
            "```",
            "",
            "## Safety",
            "",
            "- This handoff performed no write.",
            "- The future command must rely on the existing repo gates and fail closed if readiness drifts.",
            "- Do not run if the Board apply manifest, size dry-run, or readiness summary SHA differs from this packet.",
            "",
        ]
    )


def _closeout(manifest: dict[str, Any]) -> str:
    lines = [
        "# Kaspi Customer Size After Board Apply Readiness",
        "",
        f"Gate: {manifest['gate']}",
        "",
        "## Evidence",
        "",
        f"- Google Board apply manifest: `{manifest.get('google_board_apply_manifest_path')}`",
        f"- Size writeback dry-run: `{manifest.get('size_writeback_dry_run_report_path')}`",
        f"- Closeout readiness summary: `{manifest.get('closeout_readiness_summary_path')}`",
        "",
        "## Safety",
        "",
        "- Google Board write performed by this helper: false",
        "- Production DB write performed by this helper: false",
        "- Kaspi shipping/write performed by this helper: false",
        "- Waybill build/send performed by this helper: false",
        "- Telegram/WhatsApp send performed by this helper: false",
        "- Customer chat send/read performed by this helper: false",
        "- Raw order IDs exported: false",
        "",
        "## Next Action",
        "",
        f"- {manifest.get('exact_next_action')}",
        "",
    ]
    blockers = manifest.get("blockers") or []
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in blockers)
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--google-board-apply-manifest", type=Path)
    parser.add_argument("--size-writeback-report", type=Path)
    parser.add_argument("--closeout-readiness-report", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--service-account-json", type=Path)
    parser.add_argument("--spreadsheet-id")
    parser.add_argument("--target-date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=5)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = (args.output_dir or _default_output_dir(target_date)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db.resolve()
    contract_path = args.contract.resolve()
    apply_manifest_path = (args.google_board_apply_manifest or _latest_board_apply_manifest())

    blockers: list[str] = []
    if apply_manifest_path is None or not Path(apply_manifest_path).is_file():
        apply_manifest = {}
        apply_manifest_path_str = str(apply_manifest_path or "")
        blockers.append("google_board_apply_manifest_missing")
    else:
        apply_manifest_path = Path(apply_manifest_path).resolve()
        apply_manifest_path_str = str(apply_manifest_path)
        apply_manifest = _read_json(apply_manifest_path)
        blockers.extend(_board_apply_blockers(apply_manifest))

    size_rc = 1
    size_report: dict[str, Any] = {}
    size_report_path = output_dir / "size_writeback_dry_run.json"
    if not blockers:
        try:
            size_rc, size_report, size_report_path = _run_size_writeback_dry_run(
                output_dir=output_dir,
                db_path=db_path,
                target_date=target_date,
                lookback_days=args.lookback_days,
                contract_path=contract_path,
                service_account_json=args.service_account_json.resolve() if args.service_account_json else None,
                spreadsheet_id=args.spreadsheet_id,
                existing_report=args.size_writeback_report,
            )
            blockers.extend(_size_writeback_blockers(size_report, size_rc))
        except Exception as exc:
            blockers.append(f"size_writeback_dry_run_failed:{type(exc).__name__}")

    readiness_summary: dict[str, Any] = {}
    readiness_source = ""
    if not blockers:
        try:
            readiness, readiness_source = _load_or_build_readiness(
                db_path=db_path,
                target_date=target_date,
                lookback_days=args.lookback_days,
                contract_path=contract_path,
                service_account_json=args.service_account_json.resolve() if args.service_account_json else None,
                spreadsheet_id=args.spreadsheet_id,
                existing_report=args.closeout_readiness_report,
            )
            readiness_summary = _redact_readiness(readiness)
            blockers.extend(_readiness_blockers(readiness_summary))
        except Exception as exc:
            blockers.append(f"closeout_readiness_failed:{type(exc).__name__}")

    readiness_summary_path = output_dir / "closeout_readiness_summary_redacted.json"
    _write_json(readiness_summary_path, readiness_summary)

    gate = GREEN_GATE if not blockers else YELLOW_GATE
    approval_path = output_dir / "REQUIRED_EXACT_CLOSEOUT_RESUME_AFTER_BOARD_APPLY_APPROVAL_PHRASE.txt"
    handoff_path = output_dir / "KASPI_CUSTOMER_SIZE_AFTER_BOARD_APPLY_CLOSEOUT_RESUME_HANDOFF.md"
    closeout_report_path = output_dir / "google_ops_board_closeout_after_customer_size_report.json"
    closeout_command = "\n".join(
        [
            "cd ~/Docs/Autonomous_business",
            "ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT=1 \\",
            "PYTHONPATH=. .venv/bin/python scripts/run_google_ops_board_closeout.py \\",
            f"  --target-date {target_date.isoformat()} \\",
            f"  --lookback-days {args.lookback_days} \\",
            "  --resume \\",
            "  --apply \\",
            f"  --json-out {closeout_report_path}",
        ]
    )

    approval = ""
    if gate == GREEN_GATE and apply_manifest_path is not None:
        approval = _approval_phrase(
            board_apply_manifest=Path(apply_manifest_path_str),
            board_apply_sha=_safe_sha(Path(apply_manifest_path_str)),
            size_report=size_report_path,
            size_report_sha=_safe_sha(size_report_path),
            readiness_summary=readiness_summary_path,
            readiness_summary_sha=_safe_sha(readiness_summary_path),
            target_date=target_date,
            lookback_days=args.lookback_days,
        )
        _write_text(approval_path, approval)
        _write_text(handoff_path, _handoff(manifest={"gate": gate}, approval_phrase=approval, closeout_command=closeout_command))

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "db_path": str(db_path),
        "db_write_performed": False,
        "google_board_write_performed_by_this_helper": False,
        "kaspi_shipping_write_performed": False,
        "waybill_build_or_send_performed": False,
        "telegram_send_performed": False,
        "customer_chat_send_or_read_performed": False,
        "google_board_apply_manifest_path": apply_manifest_path_str,
        "google_board_apply_manifest_sha256": _safe_sha(Path(apply_manifest_path_str))
        if apply_manifest_path_str
        else None,
        "google_board_apply_gate": apply_manifest.get("gate"),
        "size_writeback_dry_run_return_code": size_rc,
        "size_writeback_dry_run_report_path": str(size_report_path),
        "size_writeback_dry_run_report_sha256": _safe_sha(size_report_path),
        "size_writeback_pending_updates_count": int(size_report.get("updates_count") or 0),
        "size_writeback_invalid_rows_count": int(size_report.get("invalid_rows_count") or 0),
        "closeout_readiness_source": readiness_source,
        "closeout_readiness_summary_path": str(readiness_summary_path),
        "closeout_readiness_summary_sha256": _safe_sha(readiness_summary_path),
        "closeout_ready": bool(readiness_summary.get("ready")),
        "approval_phrase_path": str(approval_path) if approval else "",
        "handoff_path": str(handoff_path) if approval else "",
        "closeout_command_preview": closeout_command if approval else "",
        "blockers": blockers,
        "approval_phrase_generated": bool(approval),
        "exact_next_action": (
            "Use the generated exact approval phrase and handoff to run the existing Google Ops Board closeout resume path."
            if gate == GREEN_GATE
            else "Fix the retained blocker before DB size writeback or waybill/Telegram closeout resume."
        ),
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "closeout.md", _closeout(manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if gate == GREEN_GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
