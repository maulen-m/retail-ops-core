#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.google_ops_board_alerts import send_owner_ops_alert  # noqa: E402
from core.integrations.google_ops_board import (  # noqa: E402
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    dump_json,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
    validate_contract_layout,
)
from core.integrations.kaspi_api_client import KaspiAPIClient, KaspiAuthError, STORE_TOKEN_MAP  # noqa: E402
from core.integrations.telegram_bot import get_waybill_telegram_config  # noqa: E402
from scripts.check_local_app_db import validate_local_db  # noqa: E402
from scripts.google_ops_board_automation_common import (  # noqa: E402
    build_workbook_fingerprint,
    ensure_kaspi_api_call_ledger_env,
    load_json_file,
    now_almaty,
    resolve_prewindow_health_report_path,
    today_almaty,
)
from scripts.import_kaspi_article_map_from_crm import (  # noqa: E402
    DEFAULT_ANCHORED_WORKBOOK,
    DEFAULT_BACKUP_ROOT,
    DEFAULT_WORKBOOK as DEFAULT_CRM_WORKBOOK,
    import_map,
)
from scripts.rebuild_kaspi_identity_map_from_crm import rebuild_identity_map  # noqa: E402
from scripts.send_waybills_whatsapp import (  # noqa: E402
    BLOCKED_CHAT_TITLES_DEFAULT,
    BROWSER_MODE_LAUNCH,
    DEFAULT_CHROME_PROFILE_DIR,
    DEFAULT_CHROME_PROFILE_NAME,
    DEFAULT_CDP_ENDPOINT,
    DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR,
    DEFAULT_WHATSAPP_CHAT_TITLE,
    WhatsAppSender,
    check_playwright,
)


DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_KASPI_STORES_CONFIG = PROJECT_ROOT / "config" / "kaspi_stores.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "google_ops_board" / "health"
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"
IDENTITY_SYNC_WRITE_ENV_GATE = "ENABLE_KASPI_WORKBOOK_MAP_SYNC"
HEALTH_PROFILE_FULL = "full"
HEALTH_PROFILE_PUBLISH = "publish"
HEALTH_PROFILE_CLOSEOUT = "closeout"
HEALTH_PROFILE_CHOICES = [
    HEALTH_PROFILE_FULL,
    HEALTH_PROFILE_PUBLISH,
    HEALTH_PROFILE_CLOSEOUT,
]
HEALTH_PROFILE_CHECKS: dict[str, dict[str, bool]] = {
    HEALTH_PROFILE_FULL: {
        "identity_sync": True,
        "store_context": True,
        "telegram_delivery_config": True,
        "whatsapp_smoke": True,
    },
    HEALTH_PROFILE_PUBLISH: {
        "identity_sync": False,
        "store_context": False,
        "telegram_delivery_config": False,
        "whatsapp_smoke": False,
    },
    HEALTH_PROFILE_CLOSEOUT: {
        "identity_sync": False,
        "store_context": True,
        "telegram_delivery_config": True,
        "whatsapp_smoke": True,
    },
}


def _require_apply_gate(apply: bool) -> None:
    if apply and str(os.environ.get(IDENTITY_SYNC_WRITE_ENV_GATE) or "").strip() != "1":
        raise RuntimeError(f"{IDENTITY_SYNC_WRITE_ENV_GATE}=1 is required with --apply")


def _resolve_target_date(value: str) -> date:
    text = str(value or "").strip().lower()
    today = today_almaty()
    if text in {"", "today"}:
        return today
    return date.fromisoformat(text)


def _resolve_workbook_path() -> Path:
    if DEFAULT_ANCHORED_WORKBOOK.exists():
        return DEFAULT_ANCHORED_WORKBOOK
    return DEFAULT_CRM_WORKBOOK


def _load_active_store_codes(config_path: Path) -> list[str]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores") or {}
    out: list[str] = []
    for store_code, info in stores.items():
        if isinstance(info, dict) and info.get("sync_enabled", True):
            out.append(str(store_code).strip().upper())
    return sorted(code for code in out if code)


def _load_repo_dotenv() -> None:
    load_dotenv(DEFAULT_DOTENV_PATH, override=False)


def _resolve_health_profile(value: str | None) -> str:
    text = str(value or HEALTH_PROFILE_FULL).strip().lower()
    if text not in HEALTH_PROFILE_CHOICES:
        raise ValueError(
            f"Unsupported Google Ops Board health profile: {text}. "
            f"Expected one of {HEALTH_PROFILE_CHOICES}."
        )
    return text


def _profile_skipped_report(*, profile: str, check_name: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "reason": f"profile={profile} excludes {check_name}",
    }


def _is_workbook_read_failure(exc: Exception) -> bool:
    detail = str(exc).strip().lower()
    return isinstance(exc, BadZipFile) or any(
        marker in detail
        for marker in (
            "file is not a zip file",
            "not a zipfile",
            "excel file format cannot be determined",
        )
    )


def _load_same_day_successful_identity_sync(
    *,
    target_date: date,
    output_root: Path,
    current_report_path: Path,
    require_apply: bool,
) -> dict[str, Any] | None:
    for profile in (HEALTH_PROFILE_FULL, HEALTH_PROFILE_PUBLISH, HEALTH_PROFILE_CLOSEOUT):
        report_path = resolve_prewindow_health_report_path(target_date, output_root, profile=profile)
        if report_path == current_report_path:
            continue
        payload = load_json_file(report_path)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("target_date") or "") != target_date.isoformat():
            continue
        if require_apply and str(payload.get("mode") or "") != "apply":
            continue
        identity_sync = ((payload.get("checks") or {}).get("identity_sync")) or {}
        if not identity_sync.get("ok"):
            continue
        reused_identity = dict(identity_sync)
        reused_identity["reused"] = True
        reused_identity["reused_from_profile"] = profile
        reused_identity["reused_from_report_path"] = str(report_path)
        reused_identity["reuse_reason"] = "same_day_identity_sync_artifact_after_workbook_read_failure"
        return reused_identity
    return None


def _build_google_layout_report(*, client: GoogleOpsBoardClient, contract) -> dict[str, Any]:
    metadata = client.get_metadata()
    sheet_names = [str(((sheet.get("properties") or {}).get("title") or "")).strip() for sheet in metadata.get("sheets", [])]
    header_rows: dict[str, list[Any]] = {}
    for tab_name in contract.tabs:
        matrix = client.get_tab_values(tab_name)
        header_rows[tab_name] = matrix[0] if matrix else []
    return validate_contract_layout(contract, sheet_names, header_rows)


def _build_store_context_report(store_codes: list[str]) -> dict[str, Any]:
    stores: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for store_code in store_codes:
        token_env = STORE_TOKEN_MAP.get(store_code, "")
        try:
            client = KaspiAPIClient(store_code=store_code)
            merchant_uid = str(getattr(client, "_merchant_uid", "") or "").strip()
            ok = bool(merchant_uid)
            item = {
                "store_code": store_code,
                "token_env": token_env,
                "merchant_uid": merchant_uid,
                "ok": ok,
                "error": "" if ok else "merchant UID missing",
            }
        except KaspiAuthError as exc:
            item = {
                "store_code": store_code,
                "token_env": token_env,
                "merchant_uid": "",
                "ok": False,
                "error": str(exc),
            }
        except Exception as exc:
            item = {
                "store_code": store_code,
                "token_env": token_env,
                "merchant_uid": "",
                "ok": False,
                "error": str(exc),
            }
        stores.append(item)
        if not item["ok"]:
            failures.append(item)
    return {
        "ok": len(failures) == 0,
        "stores": stores,
        "failure_count": len(failures),
        "failures": failures,
    }


def _build_telegram_delivery_config_report() -> dict[str, Any]:
    allowed_users_file = PROJECT_ROOT / "runtime" / "state" / "waybill_telegram_allowed_users.txt"
    allowed_user_ids = [
        line.strip()
        for line in allowed_users_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ] if allowed_users_file.exists() else []
    env_allowed = [
        value.strip()
        for value in str(os.environ.get("TELEGRAM_WAYBILL_ALLOWED_USER_IDS") or "").split(",")
        if value.strip()
    ]
    try:
        config = get_waybill_telegram_config()
        allowlist_configured = bool(allowed_user_ids or env_allowed)
        warnings = []
        if not allowlist_configured:
            warnings.append(
                {
                    "code": "telegram_control_allowlist_missing",
                    "detail": (
                        "Telegram delivery is configured, but control/recovery commands are fail-closed "
                        "until TELEGRAM_WAYBILL_ALLOWED_USER_IDS or runtime/state/waybill_telegram_allowed_users.txt is set."
                    ),
                    "blocking": False,
                }
            )
        return {
            "ok": True,
            "token_configured": bool(config.get("token")),
            "chat_id_configured": bool(config.get("chat_id")),
            "chat_id": str(config.get("chat_id") or ""),
            "allowed_user_gate_configured": allowlist_configured,
            "allowed_user_count": len(set(allowed_user_ids + env_allowed)),
            "warnings": warnings,
            "issues": [],
        }
    except Exception as exc:
        return {
            "ok": False,
            "token_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN_WAYBILL") or os.environ.get("TELEGRAM_BOT_TOKEN")),
            "chat_id_configured": bool(os.environ.get("TELEGRAM_WAYBILL_CHAT_ID")),
            "allowed_user_gate_configured": bool(allowed_user_ids or env_allowed),
            "allowed_user_count": len(set(allowed_user_ids + env_allowed)),
            "issues": [{"code": "telegram_delivery_config_missing", "detail": str(exc)}],
        }


def _run_whatsapp_smoke_check(*, verbose: bool) -> dict[str, Any]:
    if not check_playwright():
        return {
            "ok": False,
            "issues": [{"code": "playwright_unavailable", "detail": "Playwright is not installed"}],
        }
    sender = WhatsAppSender(
        chat_title=DEFAULT_WHATSAPP_CHAT_TITLE,
        user_data_dir=DEFAULT_WHATSAPP_AUTOMATION_USER_DATA_DIR,
        profile_directory=DEFAULT_CHROME_PROFILE_DIR,
        profile_name=DEFAULT_CHROME_PROFILE_NAME,
        cdp_endpoint=DEFAULT_CDP_ENDPOINT,
        browser_mode=BROWSER_MODE_LAUNCH,
        blocked_chat_titles=BLOCKED_CHAT_TITLES_DEFAULT,
        verbose=verbose,
    )
    try:
        with sender:
            sender.assert_document_send_ready()
            return {
                "ok": True,
                "issues": [],
                "active_chat_title": sender._active_chat_title(),
            }
    except Exception as exc:
        return {
            "ok": False,
            "issues": [{"code": "smoke_check_failed", "detail": str(exc)}],
        }


def _build_identity_sync_report(
    *,
    db_path: Path,
    workbook_path: Path,
    target_date: date,
    output_root: Path,
    apply: bool,
) -> dict[str, Any]:
    identity_output_root = Path(output_root).expanduser() / "identity_sync"
    catalog_report = import_map(
        db_path=db_path,
        workbook=workbook_path,
        sheet="M02_SKU_CATALOG_NC",
        store_filter=None,
        apply_changes=apply,
        as_of=target_date,
        output_root=identity_output_root,
        backup_root=DEFAULT_BACKUP_ROOT,
    )
    rebuild_report = rebuild_identity_map(
        workbook=workbook_path,
        sheet="SALES_KSP_CRM_1",
        dry_run=not apply,
        db_path=db_path,
        as_of=target_date,
        output_root=identity_output_root,
        backup_root=DEFAULT_BACKUP_ROOT,
    )
    return {
        "ok": True,
        "catalog_import": catalog_report,
        "crm_history_rebuild": rebuild_report,
        "output_root": str(identity_output_root.resolve()),
    }


def _send_health_alert(report: dict[str, Any], previous: dict[str, Any] | None) -> None:
    current_ok = bool(report.get("ok"))
    previous_ok = bool((previous or {}).get("ok"))
    previous_fp = ((previous or {}).get("workbook_fingerprint") or {}).get("sha256")
    current_fp = ((report.get("workbook_fingerprint") or {}).get("sha256"))
    if previous and previous_ok == current_ok and previous_fp == current_fp:
        return

    if current_ok:
        send_owner_ops_alert(
            title="Google Ops Board Prewindow Green",
            lines=[
                f"Target date: {report['target_date']}",
                f"Reason: {report['reason']}",
                "Health gate is green and automation is unblocked.",
                f"Report: {report['report_path']}",
            ],
        )
        return

    failures: list[str] = []
    checks = report.get("checks") or {}
    for key, payload in checks.items():
        if not payload or payload.get("ok", True) or payload.get("blocking") is False:
            continue
        if key == "db_preflight":
            failures.append(f"db_preflight: {', '.join(payload.get('errors') or [])}")
        elif key == "whatsapp_smoke":
            detail = (payload.get("issues") or [{}])[0].get("detail", "")
            failures.append(f"whatsapp_smoke: {detail}")
        elif key == "store_context":
            failures.append(f"store_context failures={payload.get('failure_count', 0)}")
        elif key == "telegram_delivery_config":
            detail = (payload.get("issues") or [{}])[0].get("detail", "")
            failures.append(f"telegram_delivery_config: {detail}")
        elif key == "google_layout":
            failures.append("google_layout failed")
        elif key == "identity_sync":
            failures.append("identity_sync failed")
    send_owner_ops_alert(
        title="Google Ops Board Prewindow Red",
        lines=[
            f"Target date: {report['target_date']}",
            f"Reason: {report['reason']}",
            *(failures or ["Health gate failed"]),
            f"Report: {report['report_path']}",
        ],
    )


def ensure_prewindow_health(
    *,
    target_date: date,
    db_path: Path,
    contract_path: Path,
    service_account_json: Path,
    spreadsheet_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    workbook_path: Path | None = None,
    stores_config_path: Path = DEFAULT_KASPI_STORES_CONFIG,
    apply: bool = False,
    reason: str = "manual",
    verbose: bool = False,
    force: bool = False,
    profile: str = HEALTH_PROFILE_FULL,
) -> dict[str, Any]:
    _load_repo_dotenv()
    ledger_env = os.environ
    ensure_kaspi_api_call_ledger_env(ledger_env, target_date=target_date, project_root=PROJECT_ROOT)
    _require_apply_gate(apply)
    resolved_profile = _resolve_health_profile(profile)
    profile_checks = HEALTH_PROFILE_CHECKS[resolved_profile]
    report_path = resolve_prewindow_health_report_path(target_date, output_root, profile=resolved_profile)
    previous_report = load_json_file(report_path)
    workbook = Path(workbook_path or _resolve_workbook_path()).expanduser()
    if profile_checks["identity_sync"]:
        fingerprint = build_workbook_fingerprint(workbook)
    else:
        fingerprint = {
            "path": str(workbook),
            "skipped": True,
            "reason": f"profile={resolved_profile} excludes identity_sync",
        }

    contract = load_ops_board_contract(contract_path)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    previous_identity_sync = (((previous_report.get("checks") or {}).get("identity_sync")) or {}) if previous_report else {}
    reuse_identity_sync = bool(
        profile_checks["identity_sync"]
        and
        not force
        and previous_report
        and str(previous_report.get("target_date") or "") == target_date.isoformat()
        and (((previous_report.get("workbook_fingerprint") or {}).get("sha256")) == fingerprint["sha256"])
        and bool(previous_identity_sync.get("ok"))
    )

    report: dict[str, Any] = {
        "target_date": target_date.isoformat(),
        "reason": reason,
        "profile": resolved_profile,
        "mode": "apply" if apply else "dry_run",
        "report_path": str(report_path),
        "workbook_path": str(workbook.resolve()),
        "workbook_fingerprint": fingerprint,
        "ran_at": now_almaty().isoformat(),
        "identity_sync_reused": reuse_identity_sync,
        "ok": False,
        "checks": {},
    }

    db_errors = validate_local_db(db_path)
    report["checks"]["db_preflight"] = {
        "ok": len(db_errors) == 0,
        "errors": db_errors,
    }

    if not profile_checks["identity_sync"]:
        report["checks"]["identity_sync"] = _profile_skipped_report(
            profile=resolved_profile,
            check_name="identity_sync",
        )
    elif report["checks"]["db_preflight"]["ok"]:
        try:
            if reuse_identity_sync:
                report["checks"]["identity_sync"] = dict(previous_identity_sync)
                report["checks"]["identity_sync"]["reused"] = True
            else:
                report["checks"]["identity_sync"] = _build_identity_sync_report(
                    db_path=db_path,
                    workbook_path=workbook,
                    target_date=target_date,
                    output_root=output_root,
                    apply=apply,
                )
        except Exception as exc:
            same_day_identity_sync = None
            if resolved_profile == HEALTH_PROFILE_CLOSEOUT and _is_workbook_read_failure(exc):
                same_day_identity_sync = _load_same_day_successful_identity_sync(
                    target_date=target_date,
                    output_root=Path(output_root).expanduser(),
                    current_report_path=report_path,
                    require_apply=apply,
                )
            if same_day_identity_sync:
                same_day_identity_sync["current_workbook_error"] = str(exc)
                same_day_identity_sync["current_workbook_fingerprint"] = fingerprint
                report["checks"]["identity_sync"] = same_day_identity_sync
                report["identity_sync_reused"] = True
                report["identity_sync_reused_reason"] = same_day_identity_sync["reuse_reason"]
            else:
                report["checks"]["identity_sync"] = {
                    "ok": False,
                    "error": str(exc),
                }
    else:
        report["checks"]["identity_sync"] = {"ok": False, "error": "skipped: db_preflight failed"}

    try:
        report["checks"]["google_layout"] = _build_google_layout_report(client=client, contract=contract)
    except Exception as exc:
        report["checks"]["google_layout"] = {"ok": False, "error": str(exc)}

    if profile_checks["store_context"]:
        try:
            store_codes = _load_active_store_codes(stores_config_path)
            report["checks"]["store_context"] = _build_store_context_report(store_codes)
        except Exception as exc:
            report["checks"]["store_context"] = {"ok": False, "error": str(exc), "failure_count": 1}
    else:
        report["checks"]["store_context"] = _profile_skipped_report(
            profile=resolved_profile,
            check_name="store_context",
        )

    if profile_checks["telegram_delivery_config"]:
        report["checks"]["telegram_delivery_config"] = _build_telegram_delivery_config_report()
    else:
        report["checks"]["telegram_delivery_config"] = _profile_skipped_report(
            profile=resolved_profile,
            check_name="telegram_delivery_config",
        )

    if profile_checks["whatsapp_smoke"]:
        whatsapp_report = _run_whatsapp_smoke_check(verbose=verbose)
        if resolved_profile == HEALTH_PROFILE_CLOSEOUT:
            whatsapp_report["blocking"] = False
            whatsapp_report["warning_only"] = True
        else:
            whatsapp_report["blocking"] = True
            whatsapp_report["warning_only"] = False
        report["checks"]["whatsapp_smoke"] = whatsapp_report
    else:
        report["checks"]["whatsapp_smoke"] = _profile_skipped_report(
            profile=resolved_profile,
            check_name="whatsapp_smoke",
        )
    report["ok"] = all(
        bool((payload or {}).get("ok"))
        for payload in report["checks"].values()
        if (payload or {}).get("blocking", True) is not False
    )
    dump_json(report_path, report)
    _send_health_alert(report, previous_report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Google Ops Board pre-window health gate.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--service-account-json", type=Path, default=None)
    parser.add_argument("--spreadsheet-id", type=str, default=None)
    parser.add_argument("--target-date", type=str, default="today")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workbook-path", type=Path, default=None)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_KASPI_STORES_CONFIG)
    parser.add_argument("--reason", type=str, default="manual")
    parser.add_argument("--profile", choices=HEALTH_PROFILE_CHOICES, default=HEALTH_PROFILE_FULL)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    contract = load_ops_board_contract(args.contract)
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    target_date = _resolve_target_date(args.target_date)

    report = ensure_prewindow_health(
        target_date=target_date,
        db_path=Path(args.db_path).expanduser(),
        contract_path=args.contract,
        service_account_json=service_account_json,
        spreadsheet_id=spreadsheet_id,
        output_root=Path(args.output_root).expanduser(),
        workbook_path=args.workbook_path,
        stores_config_path=Path(args.stores_config).expanduser(),
        apply=args.apply,
        reason=args.reason,
        verbose=args.verbose,
        force=args.force,
        profile=args.profile,
    )
    if args.json_out:
        dump_json(args.json_out, report)
    print(f"prewindow_health_report={report['report_path']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
