#!/usr/bin/env python3
"""Read-only WebUI ArchiveOrders source refresh wrapper.

This command is an operator-safe front door around the existing WebUI archive
download, normalization, integrity, and full-parse scripts. It never mutates the
production DB, workbook, scheduler, or external business state.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.normalize_kaspi_webui_archive_pack import (
    WebuiPackNormalizeError,
    normalize_kaspi_webui_archive_pack,
)
from scripts.playwright.download_kaspi_archive_webui import (
    DEFAULT_ARCHIVE_URL,
    DEFAULT_DOTENV_PATH,
    DEFAULT_OUTPUT_ROOT as DEFAULT_DOWNLOAD_RUNS_ROOT,
    DEFAULT_SESSION_STATE,
    WebuiArchiveDownloadError,
    download_kaspi_archive_webui,
)
from scripts.run_webui_archive_full_parse import (
    DEFAULT_OUTPUT_ROOT as DEFAULT_FULL_PARSE_ROOT,
    FullWebuiArchiveParseError,
    _build_merged_outputs,
    run_webui_archive_full_parse,
)
from scripts.validate_playwright_archive_downloads import (
    PlaywrightArchiveDownloadValidationError,
    validate_playwright_archive_downloads,
)
from scripts.validate_webui_archive_pack_integrity import (
    WebuiPackIntegrityError,
    validate_webui_archive_pack_integrity,
)
from scripts.webui_archive_truth_utils import DEFAULT_STORES_CONFIG


DEFAULT_SOURCE_REFRESH_ROOT = PROJECT_ROOT / "exports" / "webui_archive_source_refresh_runs"


class WebuiArchiveSourceRefreshError(RuntimeError):
    """Raised when a read-only WebUI archive source refresh fails."""


def _default_run_id() -> str:
    return f"webui_archive_source_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _parse_store_codes(store_code: list[str] | None, stores: str | None) -> list[str] | None:
    values: list[str] = []
    for raw in store_code or []:
        values.extend(part.strip() for part in str(raw).split(","))
    if stores:
        values.extend(part.strip() for part in str(stores).split(","))
    selected = [value.upper() for value in values if value]
    return list(dict.fromkeys(selected)) or None


def _choose_auto_mode(source_root: Path | None, session_state: Path, manual_login: bool) -> str:
    if source_root is not None and source_root.expanduser().exists():
        return "import-existing"
    if session_state.expanduser().exists():
        return "live-headless"
    if manual_login:
        return "headful-manual-login"
    return "live-headless"


def _scoped_stores_config(stores_config: Path, store_codes: list[str] | None, run_root: Path) -> Path:
    stores_config = stores_config.expanduser().resolve()
    if not store_codes:
        return stores_config
    payload = yaml.safe_load(stores_config.read_text(encoding="utf-8")) or {}
    stores = payload.get("stores", {}) or {}
    selected: dict[str, Any] = {}
    missing: list[str] = []
    for store_code in store_codes:
        key = str(store_code).strip().upper()
        if key not in stores:
            missing.append(key)
            continue
        selected[key] = stores[key]
    if missing:
        raise WebuiArchiveSourceRefreshError(
            f"store_code not configured: {', '.join(missing)}"
        )
    scoped = {**payload, "stores": selected}
    scoped_path = run_root / "target_stores_config.yaml"
    scoped_path.write_text(yaml.safe_dump(scoped, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return scoped_path


def _write_summary(report: dict[str, Any], summary_path: Path) -> None:
    lines = [
        "# WebUI Archive Source Refresh",
        "",
        f"- run_id: `{report['run_id']}`",
        f"- status: `{report['status']}`",
        f"- requested_mode: `{report['requested_mode']}`",
        f"- effective_mode: `{report['effective_mode']}`",
        f"- since: `{report.get('since') or ''}`",
        f"- until: `{report.get('until') or ''}`",
        f"- target_stores: `{', '.join(report.get('target_stores') or [])}`",
        f"- read_only: `{str(report['read_only']).lower()}`",
        f"- production_db_modified: `{str(report['production_db_modified']).lower()}`",
        f"- workbook_modified: `{str(report['workbook_modified']).lower()}`",
        f"- scheduler_modified: `{str(report['scheduler_modified']).lower()}`",
        f"- external_writes: `{str(report['external_writes']).lower()}`",
        "",
        "## Outputs",
        "",
        f"- run_manifest_json: `{report.get('run_manifest_json', '')}`",
        f"- source_refresh_summary_md: `{report.get('source_refresh_summary_md', '')}`",
        f"- child_run_manifest_json: `{report.get('child_run_manifest_json', '')}`",
        f"- pack_root: `{report.get('pack_root', '')}`",
        f"- pack_integrity_json: `{report.get('pack_integrity_json', '')}`",
        f"- final_merged_csv: `{report.get('final_merged_csv', '')}`",
        f"- final_merged_xlsx: `{report.get('final_merged_xlsx', '')}`",
        "",
        "## Block Results",
        "",
        "| store_code | window_since | window_until | status | error |",
        "|---|---|---|---|---|",
    ]
    for row in report.get("blocks") or report.get("store_results") or []:
        lines.append(
            f"| `{row.get('store_code', '')}` | `{row.get('window_since', '')}` | "
            f"`{row.get('window_until', '')}` | `{row.get('status', '')}` | `{row.get('error', '')}` |"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report(run_root: Path, report: dict[str, Any]) -> dict[str, Any]:
    manifest_path = run_root / "run_manifest.json"
    summary_path = run_root / "run_summary.md"
    report["run_manifest_json"] = str(manifest_path)
    report["source_refresh_summary_md"] = str(summary_path)
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_summary(report, summary_path)
    return report


def _base_report(
    *,
    run_root: Path,
    requested_mode: str,
    effective_mode: str,
    since: date,
    until: date,
    strict: bool,
    target_stores: list[str] | None,
    stores_config: Path,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_root.name,
        "run_root": str(run_root),
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "strict": bool(strict),
        "target_stores": target_stores or [],
        "stores_config": str(stores_config),
        "read_only": True,
        "production_db_modified": False,
        "workbook_modified": False,
        "scheduler_modified": False,
        "external_writes": False,
        "authorized_scope": "read_only_webui_archive_source_refresh",
        "not_authorized": [
            "production_db_apply",
            "workbook_mutation",
            "scheduler_mutation",
            "external_account_write",
            "price_change",
            "stock_change",
            "ads_write",
            "cash_movement",
            "po_commitment",
            "owner_publication",
        ],
    }


def _run_import_existing(
    *,
    run_root: Path,
    source_root: Path,
    since: date,
    until: date,
    strict: bool,
    target_stores: list[str] | None,
    stores_config: Path,
    download_runs_root: Path,
) -> dict[str, Any]:
    download_run_id = f"{run_root.name}__import_existing"
    download_report = download_kaspi_archive_webui(
        mode="import-existing",
        run_id=download_run_id,
        output_root=download_runs_root,
        stores_config=stores_config,
        session_state=DEFAULT_SESSION_STATE,
        source_root=source_root,
        strict=strict,
        store_codes=target_stores,
        since=since,
        until=until,
    )
    download_validation = validate_playwright_archive_downloads(
        run_id=str(download_report["run_root"]),
        output_root=download_runs_root,
        stores_config=stores_config,
        strict=strict,
    )
    pack_report = normalize_kaspi_webui_archive_pack(
        source_root=Path(download_report["run_root"]) / "downloads",
        pack_id=f"{run_root.name}_pack",
        output_root=run_root / "pack_outputs",
        stores_config=stores_config,
        strict=strict,
    )
    pack_root = Path(str(pack_report["pack_root"])).resolve()
    pack_integrity = validate_webui_archive_pack_integrity(
        pack_root=pack_root,
        stores_config=stores_config,
        strict=strict,
    )
    merged_outputs = _build_merged_outputs(pack_root=pack_root, run_root=run_root)
    ok = bool(download_report.get("ok")) and bool(download_validation.get("ok")) and bool(pack_integrity.get("ok"))
    return {
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "source_root": str(source_root),
        "child_run_manifest_json": download_report.get("run_manifest_json"),
        "download_validation_json": download_validation.get("download_validation_json"),
        "store_results": download_report.get("store_results") or [],
        "pack_root": str(pack_root),
        "pack_integrity_json": str(pack_root / "integrity_report.json"),
        "pack_integrity_ok": bool(pack_integrity.get("ok")),
        "pack_integrity_errors": list(pack_integrity.get("errors") or []),
        **merged_outputs,
    }


def _run_live(
    *,
    run_root: Path,
    effective_mode: str,
    since: date,
    until: date,
    strict: bool,
    target_stores: list[str] | None,
    stores_config: Path,
    session_state: Path,
    full_parse_root: Path,
    download_runs_root: Path,
    dotenv_path: Path | None,
    archive_url: str,
    login_timeout: float,
    download_timeout: float,
    allow_manual_download: bool,
) -> dict[str, Any]:
    headful = effective_mode in {"live-headful", "headful-manual-login"}
    manual_login = effective_mode == "headful-manual-login"
    full_parse_report = run_webui_archive_full_parse(
        since=since,
        until=until,
        run_id=f"{run_root.name}__full_parse",
        output_root=full_parse_root,
        download_runs_root=download_runs_root,
        stores_config=stores_config,
        session_state=session_state,
        strict=strict,
        store_codes=target_stores,
        headful=headful,
        manual_login=manual_login,
        login_timeout=login_timeout,
        download_timeout=download_timeout,
        archive_url=archive_url,
        dotenv_path=dotenv_path,
        allow_manual_download=allow_manual_download,
    )
    return {
        "status": str(full_parse_report.get("status") or "FAIL"),
        "ok": bool(full_parse_report.get("ok")),
        "child_run_manifest_json": full_parse_report.get("run_manifest_json"),
        "child_run_summary_md": full_parse_report.get("run_summary_md"),
        "blocks": full_parse_report.get("blocks") or [],
        "pack_root": full_parse_report.get("pack_root"),
        "pack_integrity_json": full_parse_report.get("pack_integrity_json"),
        "pack_integrity_ok": bool(full_parse_report.get("pack_integrity_ok")),
        "pack_integrity_errors": list(full_parse_report.get("pack_integrity_errors") or []),
        "per_store_outputs": full_parse_report.get("per_store_outputs") or {},
        "final_merged_csv": full_parse_report.get("final_merged_csv"),
        "final_merged_xlsx": full_parse_report.get("final_merged_xlsx"),
    }


def run_webui_archive_source_refresh(
    *,
    since: date,
    until: date,
    requested_mode: str,
    run_id: str | None,
    output_root: Path,
    source_root: Path | None,
    stores_config: Path,
    session_state: Path,
    full_parse_root: Path,
    download_runs_root: Path,
    dotenv_path: Path | None,
    archive_url: str,
    strict: bool,
    store_codes: list[str] | None,
    manual_login: bool,
    login_timeout: float,
    download_timeout: float,
    allow_manual_download: bool,
) -> dict[str, Any]:
    if until < since:
        raise WebuiArchiveSourceRefreshError("until must be >= since")
    effective_mode = (
        _choose_auto_mode(source_root, session_state, manual_login)
        if requested_mode == "auto"
        else requested_mode
    )
    if effective_mode == "chrome-cdp-attach":
        raise WebuiArchiveSourceRefreshError(
            "chrome-cdp-attach is not yet supported by the repo-owned archive downloader; "
            "use import-existing, live-headless, or headful-manual-login"
        )

    run_root = output_root.expanduser().resolve() / str(run_id or _default_run_id())
    run_root.mkdir(parents=True, exist_ok=True)
    effective_stores_config = _scoped_stores_config(stores_config, store_codes, run_root)
    report = _base_report(
        run_root=run_root,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        since=since,
        until=until,
        strict=strict,
        target_stores=store_codes,
        stores_config=effective_stores_config,
    )
    report["original_stores_config"] = str(stores_config.expanduser().resolve())

    if effective_mode == "session-check":
        child = download_kaspi_archive_webui(
            mode="session-check",
            run_id=f"{run_root.name}__session_check",
            output_root=download_runs_root,
            stores_config=effective_stores_config,
            session_state=session_state,
            source_root=None,
            strict=strict,
            store_codes=store_codes,
            since=since,
            until=until,
        )
        report.update(
            {
                "status": str(child.get("status") or "FAIL"),
                "ok": bool(child.get("ok")),
                "child_run_manifest_json": child.get("run_manifest_json"),
                "store_results": child.get("store_results") or [],
            }
        )
    elif effective_mode == "import-existing":
        if source_root is None:
            raise WebuiArchiveSourceRefreshError("--source-root is required for import-existing mode")
        report.update(
            _run_import_existing(
                run_root=run_root,
                source_root=source_root.expanduser().resolve(),
                since=since,
                until=until,
                strict=strict,
                target_stores=store_codes,
                stores_config=effective_stores_config,
                download_runs_root=download_runs_root,
            )
        )
    elif effective_mode in {"live-headless", "live-headful", "headful-manual-login"}:
        report.update(
            _run_live(
                run_root=run_root,
                effective_mode=effective_mode,
                since=since,
                until=until,
                strict=strict,
                target_stores=store_codes,
                stores_config=effective_stores_config,
                session_state=session_state,
                full_parse_root=full_parse_root,
                download_runs_root=download_runs_root,
                dotenv_path=dotenv_path,
                archive_url=archive_url,
                login_timeout=login_timeout,
                download_timeout=download_timeout,
                allow_manual_download=allow_manual_download,
            )
        )
    else:
        raise WebuiArchiveSourceRefreshError(f"unsupported mode: {effective_mode}")

    if strict and not bool(report.get("ok")):
        _write_report(run_root, report)
        raise WebuiArchiveSourceRefreshError(f"source refresh failed in strict mode: {report.get('status')}")
    return _write_report(run_root, report)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only WebUI ArchiveOrders source refresh")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "auto",
            "import-existing",
            "live-headless",
            "live-headful",
            "headful-manual-login",
            "session-check",
            "chrome-cdp-attach",
        ],
        default="auto",
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_SOURCE_REFRESH_ROOT)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--full-parse-root", type=Path, default=DEFAULT_FULL_PARSE_ROOT)
    parser.add_argument("--download-runs-root", type=Path, default=DEFAULT_DOWNLOAD_RUNS_ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=DEFAULT_DOTENV_PATH)
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--store-code", action="append", default=None)
    parser.add_argument("--stores", default=None, help="Comma-separated store list")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--download-timeout", type=float, default=240.0)
    parser.add_argument("--allow-manual-download", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = run_webui_archive_source_refresh(
            since=date.fromisoformat(str(args.since)),
            until=date.fromisoformat(str(args.until)),
            requested_mode=str(args.mode),
            run_id=args.run_id,
            output_root=args.output_root,
            source_root=args.source_root,
            stores_config=args.stores_config,
            session_state=args.session_state,
            full_parse_root=args.full_parse_root,
            download_runs_root=args.download_runs_root,
            dotenv_path=args.dotenv_path,
            archive_url=str(args.archive_url),
            strict=bool(args.strict),
            store_codes=_parse_store_codes(args.store_code, args.stores),
            manual_login=bool(args.manual_login),
            login_timeout=float(args.login_timeout),
            download_timeout=float(args.download_timeout),
            allow_manual_download=bool(args.allow_manual_download),
        )
    except (
        WebuiArchiveSourceRefreshError,
        WebuiArchiveDownloadError,
        FullWebuiArchiveParseError,
        WebuiPackNormalizeError,
        WebuiPackIntegrityError,
        PlaywrightArchiveDownloadValidationError,
    ) as exc:
        print("status=FAIL")
        print("error_code=WEBUI_ARCHIVE_SOURCE_REFRESH_FAIL")
        print(f"message={exc}")
        return 1

    print(f"run_manifest_json={report['run_manifest_json']}")
    print(f"source_refresh_summary_md={report['source_refresh_summary_md']}")
    if report.get("final_merged_csv"):
        print(f"final_merged_csv={report['final_merged_csv']}")
    if report.get("final_merged_xlsx"):
        print(f"final_merged_xlsx={report['final_merged_xlsx']}")
    print(f"status={report['status']}")
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
