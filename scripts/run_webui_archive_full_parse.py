#!/usr/bin/env python3
"""Run a full-range WebUI archive parse across stores with immutable 90-day blocks."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import openpyxl
import pandas as pd
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_kaspi_archive_ui_history import WINDOW_DAYS, plan_windows
from scripts.normalize_kaspi_webui_archive_pack import normalize_kaspi_webui_archive_pack
from scripts.playwright.download_kaspi_archive_webui import (
    DEFAULT_ARCHIVE_URL,
    DEFAULT_DOTENV_PATH,
    DEFAULT_SESSION_STATE,
    _load_env,
    _resolve_store_credentials,
    download_kaspi_archive_webui,
)
from scripts.validate_webui_archive_pack_integrity import validate_webui_archive_pack_integrity
from scripts.webui_archive_truth_utils import DEFAULT_STORES_CONFIG, load_enabled_stores, load_pack_rows

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "webui_archive_full_parse_runs"
DEFAULT_DOWNLOAD_RUNS_ROOT = PROJECT_ROOT / "exports" / "webui_archive_download_runs"


class FullWebuiArchiveParseError(RuntimeError):
    """Raised when the full WebUI archive parse cannot complete successfully."""


def _default_run_id() -> str:
    return f"webui_archive_full_parse_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _resolve_target_stores(stores_config: Path, store_codes: list[str] | None) -> list[str]:
    enabled_stores = load_enabled_stores(stores_config)
    if not store_codes:
        return enabled_stores
    selected = [str(value).strip().upper() for value in store_codes if str(value).strip()]
    selected = list(dict.fromkeys(selected))
    invalid = [store for store in selected if store not in enabled_stores]
    if invalid:
        raise FullWebuiArchiveParseError(f"store_code not enabled or unknown: {', '.join(invalid)}")
    return selected


def plan_full_parse_blocks(*, stores: list[str], since: date, until: date) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for store_code in stores:
        for window_since, window_until in plan_windows(since, until, WINDOW_DAYS):
            blocks.append(
                {
                    "store_code": str(store_code).strip().upper(),
                    "window_since": window_since.isoformat(),
                    "window_until": window_until.isoformat(),
                }
            )
    return blocks


def _atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    frame.to_csv(tmp_path, index=False, encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(path)
    pd.read_csv(path, dtype=object, keep_default_na=False)


def _atomic_write_xlsx(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.stem}.tmp{path.suffix}")
    with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="archive")
    tmp_path.replace(path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    wb.close()


def _copy_raw_backup(source_file: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = backup_path.with_name(f".{backup_path.name}.tmp")
    shutil.copy2(source_file, tmp_path)
    tmp_path.replace(backup_path)


def _build_merged_outputs(*, pack_root: Path, run_root: Path) -> dict[str, Any]:
    rows = load_pack_rows(pack_root)
    sort_cols = [
        column
        for column in ["store_code", "order_id", "status_change_at", "created_at", "source_file", "source_row_number"]
        if column in rows.columns
    ]
    if sort_cols and not rows.empty:
        rows = rows.sort_values(sort_cols, na_position="last").reset_index(drop=True)

    per_store_root = run_root / "per_store_merged"
    final_root = run_root / "final_merged"
    per_store_outputs: dict[str, dict[str, str]] = {}
    for store_code in sorted({str(value).strip().upper() for value in rows.get("store_code", pd.Series(dtype=object)).tolist() if str(value).strip()}):
        store_rows = rows[rows["store_code"].astype(str).str.upper() == store_code].reset_index(drop=True)
        store_dir = per_store_root / f"store_{store_code}"
        csv_path = store_dir / f"ArchiveOrders_WEBUI_MERGED_{store_code}.csv"
        xlsx_path = store_dir / f"ArchiveOrders_WEBUI_MERGED_{store_code}.xlsx"
        _atomic_write_csv(store_rows, csv_path)
        _atomic_write_xlsx(store_rows, xlsx_path)
        per_store_outputs[store_code] = {
            "merged_csv": str(csv_path),
            "merged_xlsx": str(xlsx_path),
            "row_count": int(len(store_rows)),
        }

    final_csv = final_root / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv"
    final_xlsx = final_root / "ArchiveOrders_WEBUI_MERGED_ALL_STORES.xlsx"
    _atomic_write_csv(rows, final_csv)
    _atomic_write_xlsx(rows, final_xlsx)
    return {
        "per_store_outputs": per_store_outputs,
        "final_merged_csv": str(final_csv),
        "final_merged_xlsx": str(final_xlsx),
        "final_row_count": int(len(rows)),
    }


def _store_session_state_path(base_session_state: Path, store_code: str) -> Path:
    suffix = base_session_state.suffix or ".json"
    return base_session_state.with_name(f"{base_session_state.stem}_{store_code}{suffix}")


def _store_has_auth_material(store_code: str, env: dict[str, str], session_state: Path) -> bool:
    if session_state.exists() and session_state.stat().st_size > 0:
        return True
    credentials = _resolve_store_credentials(store_code, env)
    has_email_login = bool(credentials.get("email")) and bool(credentials.get("email_password"))
    has_phone_login = bool(credentials.get("phone")) and bool(credentials.get("phone_password"))
    return has_email_login or has_phone_login


def _load_full_parse_env(dotenv_path: Path | None) -> dict[str, str]:
    path = dotenv_path.expanduser().resolve() if dotenv_path is not None else DEFAULT_DOTENV_PATH
    if dotenv_path is not None and path != DEFAULT_DOTENV_PATH.expanduser().resolve():
        return {
            str(key): str(value)
            for key, value in dotenv_values(path).items()
            if key and value is not None
        }
    return _load_env(dotenv_path)


def run_webui_archive_full_parse(
    *,
    since: date,
    until: date,
    run_id: str | None,
    output_root: Path,
    download_runs_root: Path,
    stores_config: Path,
    session_state: Path,
    strict: bool,
    store_codes: list[str] | None = None,
    headful: bool = False,
    manual_login: bool = False,
    login_timeout: float = 300.0,
    download_timeout: float = 240.0,
    archive_url: str = DEFAULT_ARCHIVE_URL,
    dotenv_path: Path | None = DEFAULT_DOTENV_PATH,
    allow_manual_download: bool = False,
    write_child_anchors: bool = True,
) -> dict[str, Any]:
    if until < since:
        raise FullWebuiArchiveParseError("until must be >= since")

    stores_config = stores_config.expanduser().resolve()
    download_runs_root = download_runs_root.expanduser().resolve()
    session_state = session_state.expanduser().resolve()
    run_root = output_root.expanduser().resolve() / str(run_id or _default_run_id())
    run_root.mkdir(parents=True, exist_ok=True)
    raw_backups_root = run_root / "raw_backups"
    raw_backups_root.mkdir(parents=True, exist_ok=True)

    target_stores = _resolve_target_stores(stores_config, store_codes)
    blocks = plan_full_parse_blocks(stores=target_stores, since=since, until=until)
    block_results: list[dict[str, Any]] = []
    env = _load_full_parse_env(dotenv_path)

    store_session_paths = {
        store_code: _store_session_state_path(session_state, store_code)
        for store_code in target_stores
    }
    stores_missing_auth = {
        store_code
        for store_code, store_session_state in store_session_paths.items()
        if not _store_has_auth_material(store_code, env, store_session_state)
    }

    for block in blocks:
        store_code = str(block["store_code"])
        window_since = str(block["window_since"])
        window_until = str(block["window_until"])
        backup_path = raw_backups_root / f"store_{store_code}" / f"ArchiveOrders_{store_code}_{window_since}_to_{window_until}.xlsx"
        child_run_id = f"{run_root.name}__{store_code}__{window_since}_to_{window_until}"
        store_session_state = store_session_paths[store_code]
        if backup_path.exists():
            block_results.append(
                {
                    **block,
                    "status": "PASS",
                    "copied_file": str(backup_path),
                    "child_run_id": child_run_id,
                    "reused_backup": True,
                    "session_state_path": str(store_session_state),
                }
            )
            continue

        if store_code in stores_missing_auth:
            block_results.append(
                {
                    **block,
                    "status": "FAIL",
                    "error": "CREDENTIALS_MISSING",
                    "child_run_id": child_run_id,
                    "reused_backup": False,
                    "session_state_path": str(store_session_state),
                }
            )
            continue

        try:
            child_report = download_kaspi_archive_webui(
                mode="live-download",
                run_id=child_run_id,
                output_root=download_runs_root,
                stores_config=stores_config,
                session_state=store_session_state,
                source_root=None,
                strict=True,
                store_codes=[store_code],
                headful=bool(headful),
                manual_login=bool(manual_login),
                login_timeout=float(login_timeout),
                download_timeout=float(download_timeout),
                archive_url=str(archive_url),
                dotenv_path=dotenv_path,
                allow_manual_download=bool(allow_manual_download),
                since=date.fromisoformat(window_since),
                until=date.fromisoformat(window_until),
                write_anchor=bool(write_child_anchors),
            )
        except Exception as exc:
            block_results.append(
                {
                    **block,
                    "status": "FAIL",
                    "error": "DOWNLOAD_EXCEPTION",
                    "error_message": str(exc),
                    "child_run_id": child_run_id,
                    "reused_backup": False,
                    "session_state_path": str(store_session_state),
                }
            )
            continue
        store_results = child_report.get("store_results") or []
        success_row = next(
            (
                row
                for row in store_results
                if str(row.get("store_code") or "").upper() == store_code and str(row.get("status") or "").upper() == "PASS"
            ),
            None,
        )
        if success_row is None:
            block_results.append(
                {
                    **block,
                    "status": "FAIL",
                    "error": "DOWNLOAD_BLOCK_FAILED",
                    "child_run_id": child_run_id,
                    "child_run_manifest_json": child_report.get("run_manifest_json"),
                    "session_state_path": str(store_session_state),
                }
            )
            continue

        source_file = Path(str(success_row["copied_file"])).resolve()
        _copy_raw_backup(source_file, backup_path)
        block_results.append(
            {
                **block,
                "status": "PASS",
                "copied_file": str(backup_path),
                "child_run_id": child_run_id,
                "child_run_manifest_json": child_report.get("run_manifest_json"),
                "reused_backup": False,
                "session_state_path": str(store_session_state),
            }
        )

    successful_blocks = [row for row in block_results if str(row.get("status")).upper() == "PASS"]
    pack_report = normalize_kaspi_webui_archive_pack(
        source_root=raw_backups_root,
        pack_id=f"{run_root.name}_pack",
        output_root=run_root / "pack_outputs",
        stores_config=stores_config,
        strict=False,
    )
    pack_root = Path(str(pack_report["pack_root"])).resolve()
    pack_integrity = validate_webui_archive_pack_integrity(
        pack_root=pack_root,
        stores_config=stores_config,
        strict=False,
    )
    merged_outputs = _build_merged_outputs(pack_root=pack_root, run_root=run_root)

    ok = len(successful_blocks) == len(blocks) and bool(pack_integrity.get("ok"))
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_root.name,
        "run_root": str(run_root),
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "strict": bool(strict),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "window_days": WINDOW_DAYS,
        "stores_config": str(stores_config),
        "target_stores": target_stores,
        "write_child_anchors": bool(write_child_anchors),
        "block_count": len(blocks),
        "successful_block_count": len(successful_blocks),
        "failed_block_count": len(blocks) - len(successful_blocks),
        "raw_backups_root": str(raw_backups_root),
        "blocks": block_results,
        "pack_root": str(pack_root),
        "pack_integrity_json": str(pack_root / "integrity_report.json"),
        "pack_integrity_ok": bool(pack_integrity.get("ok")),
        "pack_integrity_errors": list(pack_integrity.get("errors") or []),
        **merged_outputs,
    }

    manifest_path = run_root / "run_manifest.json"
    summary_path = run_root / "run_summary.md"
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Full WebUI Archive Parse",
        "",
        f"- run_id: `{run_root.name}`",
        f"- status: `{report['status']}`",
        f"- strict: `{str(bool(strict)).lower()}`",
        f"- since: `{since.isoformat()}`",
        f"- until: `{until.isoformat()}`",
        f"- target_stores: `{', '.join(target_stores)}`",
        f"- block_count: `{len(blocks)}`",
        f"- successful_block_count: `{len(successful_blocks)}`",
        f"- pack_integrity_ok: `{str(bool(pack_integrity.get('ok'))).lower()}`",
        "",
        "| store_code | window_since | window_until | status | reused_backup | copied_file | error |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in block_results:
        lines.append(
            f"| `{row.get('store_code', '')}` | `{row.get('window_since', '')}` | `{row.get('window_until', '')}` | "
            f"`{row.get('status', '')}` | `{str(bool(row.get('reused_backup'))).lower()}` | "
            f"`{row.get('copied_file', '')}` | `{row.get('error', '')}` |"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report["run_manifest_json"] = str(manifest_path)
    report["run_summary_md"] = str(summary_path)
    if strict and not ok:
        raise FullWebuiArchiveParseError(
            "full WebUI archive parse failed: "
            f"failed_blocks={report['failed_block_count']} pack_integrity_ok={str(bool(pack_integrity.get('ok'))).lower()}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full-range WebUI archive parse across stores")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--download-runs-root", type=Path, default=DEFAULT_DOWNLOAD_RUNS_ROOT)
    parser.add_argument("--stores-config", type=Path, default=DEFAULT_STORES_CONFIG)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--store-code", action="append", default=None)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--login-timeout", type=float, default=300.0)
    parser.add_argument("--download-timeout", type=float, default=240.0)
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument("--dotenv-path", type=Path, default=DEFAULT_DOTENV_PATH)
    parser.add_argument("--allow-manual-download", action="store_true")
    parser.add_argument("--no-child-anchor-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = run_webui_archive_full_parse(
            since=date.fromisoformat(str(args.since)),
            until=date.fromisoformat(str(args.until)),
            run_id=args.run_id,
            output_root=args.output_root,
            download_runs_root=args.download_runs_root,
            stores_config=args.stores_config,
            session_state=args.session_state,
            strict=bool(args.strict),
            store_codes=list(args.store_code or []),
            headful=bool(args.headful),
            manual_login=bool(args.manual_login),
            login_timeout=float(args.login_timeout),
            download_timeout=float(args.download_timeout),
            archive_url=str(args.archive_url),
            dotenv_path=args.dotenv_path,
            allow_manual_download=bool(args.allow_manual_download),
            write_child_anchors=not bool(args.no_child_anchor_write),
        )
    except FullWebuiArchiveParseError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_ARCHIVE_FULL_PARSE_FAIL")
        print(f"message={exc}")
        return 1

    print(f"run_manifest_json={report['run_manifest_json']}")
    print(f"run_summary_md={report['run_summary_md']}")
    print(f"final_merged_csv={report['final_merged_csv']}")
    print(f"final_merged_xlsx={report['final_merged_xlsx']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
