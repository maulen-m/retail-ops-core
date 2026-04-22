#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 11: Import Kaspi ActiveOrders to CRM (xlwings version)

Uses xlwings to write to Excel, preserving formulas and external links.
Based on legacy ~/Docs/kaspi_etl/docs/ops/kaspi/import_active_orders.py

Usage:
    python scripts/import_orders_to_crm.py --verbose
    python scripts/import_orders_to_crm.py --dry-run
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from contextlib import contextmanager
import json
import os
import posixpath
import re
import signal
import shutil
import subprocess
import sys
import time
import zipfile
from copy import copy, deepcopy
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET

import pandas as pd
from dateutil import parser as dtp
from dotenv import load_dotenv

# xlwings for Excel-safe writing (optional at import time)
try:
    import xlwings as xw
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    xw = None

# openpyxl only for reading (inspection)
from openpyxl import load_workbook
from openpyxl.formatting.formatting import ConditionalFormatting
from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import (
    coordinate_from_string,
    column_index_from_string,
    get_column_letter,
    range_boundaries,
)
from openpyxl.worksheet.cell_range import CellRange
from openpyxl.worksheet.formula import ArrayFormula

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import KaspiAPIClient, KaspiAuthError, STORE_TOKEN_MAP
from core.integrations.kaspi_order_stage import (
    classify_kaspi_order_stage,
    kaspi_order_to_russian_status,
    stage_to_crm_indicators,
)
from core.parsers.kaspi_parser import extract_sku_from_article
from core.utils.kaspi_name_core_resolver import (
    KaspiNameCoreMaps,
    iter_sku_family_candidates,
    resolve_kaspi_name_core,
)
from core.utils.kaspi_dates import parse_kaspi_date, planned_date_from_order
from core.db import get_db
from scripts.validate_crm_workbook_integrity import (
    filter_integrity_errors,
    repair_missing_shared_strings_part,
    validate_workbook_integrity,
)
from scripts.repair_crm_workbook import (
    normalize_sales_sheet_sku_key_array_formula_refs,
    prune_stale_calcchain_refs,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")

# Warehouse → Store code (for API lookup)
WAREHOUSE_STORE_MAP = {
    '30000001_PP1': 'UNIVERSAL',
    '30137883_PP1': 'ACMEWEAR',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STOREB',
    '30000002_PP1 ': 'STOREB',
    '30362323_PP1': 'MELVIS',
}

from core.paths import data_path, get_data_root


CRM_SALES_SHEET_NAME = "SALES_KSP_CRM_1"
CRM_SALES_TABLE_NAME = "tb_SalesRaw"
CRM_CANONICAL_TEMPLATE_ENV = "CRM_CANONICAL_TEMPLATE_PATH"
CRM_CANONICAL_TEMPLATE_DEFAULT = data_path("excel_ui", "templates", "SALES_KSP_CRM_V3.template.xlsx")
CRM_TEMPLATE_SHEET_EXCLUDE = {
    CRM_SALES_SHEET_NAME,
    "pivot",
    "Подсчет",
    "Claude Log",
    "📊 Workbook Summary",
    "Master_Inventory_Rules_v9.md",
    # Older workbooks may still carry the superseded compatibility sheet.
    "Master_Inventory_Rules_v8.md",
}


# ---------- CRM Backup ----------

def backup_crm(crm_path: Path) -> Path:
    """
    Create timestamped backup of CRM file before import.

    Stores backups in excel_ui/backups/, keeps last 7 days.

    Returns:
        Path to backup file
    """
    backup_dir = crm_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"CRM_backup_{timestamp}.xlsx"

    # Create backup
    shutil.copy2(crm_path, backup_path)

    # Cleanup: keep last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    for old_backup in backup_dir.glob("CRM_backup_*.xlsx"):
        try:
            # Parse timestamp from filename: CRM_backup_YYYYMMDD_HHMMSS.xlsx
            ts_str = old_backup.stem.replace("CRM_backup_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if ts < cutoff:
                old_backup.unlink()
        except (ValueError, OSError):
            pass  # Skip files that don't match pattern

    return backup_path


def _resolve_crm_template_path(explicit: Path | None = None, *, required: bool = False) -> Path | None:
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    raw_env = os.getenv(CRM_CANONICAL_TEMPLATE_ENV, "")
    if str(raw_env).strip():
        candidates.append(Path(str(raw_env).strip()).expanduser())
    candidates.append(CRM_CANONICAL_TEMPLATE_DEFAULT)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved
    if required:
        expected = ", ".join(str(p) for p in candidates)
        raise FileNotFoundError(
            "Canonical CRM template workbook not found. "
            f"Tried: {expected}"
        )
    return None


@dataclass(frozen=True)
class ExcelWorkbookSession:
    pid: int | None
    name: str
    saved: bool
    path: str = ""


class ExcelTargetConflictError(RuntimeError):
    """Raised when the CRM workbook (or another write target) is already open in Excel."""


class AppendVerificationError(RuntimeError):
    """Raised when post-append verification proves CRM write loss or corruption."""


def _is_missing_excel_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text in {"k.missing_value", "missing value", "None"}


def _normalize_excel_session_path(value: Any) -> str:
    if _is_missing_excel_value(value):
        return ""
    text = str(value).strip()
    try:
        path_obj = Path(text).expanduser()
        if path_obj.exists():
            return str(path_obj.resolve())
        return str(path_obj)
    except Exception:
        return text


def _list_excel_workbooks_via_osascript(timeout_sec: int = 10) -> List[ExcelWorkbookSession]:
    """
    Fallback workbook inventory when xlwings/appscript instance inspection is unavailable.
    """
    script = """
if application "Microsoft Excel" is running then
    tell application "Microsoft Excel"
        set wbNames to name of workbooks
        set wbSaved to saved of workbooks
        set outputLines to {}
        repeat with idx from 1 to (count of wbNames)
            set end of outputLines to (item idx of wbNames) & "|" & ((item idx of wbSaved) as string)
        end repeat
        set AppleScript's text item delimiters to linefeed
        set payload to outputLines as string
        set AppleScript's text item delimiters to ""
        return payload
    end tell
else
    return ""
end if
"""
    try:
        proc = subprocess.run(
            ["osascript", "-"],
            input=script,
            text=True,
            capture_output=True,
            timeout=max(int(timeout_sec), 1),
        )
    except FileNotFoundError:
        return []
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Excel session inspection timed out after {int(timeout_sec)}s") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"osascript rc={proc.returncode}"
        raise RuntimeError(f"Excel session inspection failed: {detail}")

    sessions: List[ExcelWorkbookSession] = []
    for line in (proc.stdout or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split("|", 1)
        name = parts[0].strip() if parts else ""
        saved_raw = parts[1].strip().lower() if len(parts) > 1 else "true"
        sessions.append(
            ExcelWorkbookSession(
                pid=None,
                name=name,
                saved=saved_raw == "true",
                path="",
            )
        )
    return sessions


def _list_excel_workbooks(timeout_sec: int = 10) -> List[ExcelWorkbookSession]:
    """
    Return currently open Microsoft Excel workbooks without launching or mutating them.

    On macOS/xlwings we prefer PID-scoped instance inspection so we can detect whether
    the canonical CRM workbook is open in another Excel instance while ignoring
    unrelated side workbooks. Path lookup is best effort because unsaved workbooks can
    fail AppleEvent path introspection.
    """
    if xw is None:
        return _list_excel_workbooks_via_osascript(timeout_sec=timeout_sec)
    if not hasattr(xw, "apps"):
        return []

    try:
        app_pids = _run_with_posix_alarm_timeout(timeout_sec, lambda: list(xw.apps.keys()))
    except Exception as exc:
        raise RuntimeError(f"Excel session inspection failed: {exc}") from exc

    sessions: List[ExcelWorkbookSession] = []
    pid_failures: List[Tuple[int, Exception]] = []
    per_call_timeout = max(min(int(timeout_sec), 5), 1)
    for pid in app_pids:
        try:
            app = _run_with_posix_alarm_timeout(per_call_timeout, lambda pid=pid: xw.apps[pid])
            books = _run_with_posix_alarm_timeout(per_call_timeout, lambda app=app: list(app.books))
        except Exception as exc:
            pid_failures.append((int(pid), exc))
            continue

        for book in books:
            try:
                name = str(_run_with_posix_alarm_timeout(per_call_timeout, lambda book=book: book.name) or "").strip()
            except Exception:
                name = ""

            try:
                saved_raw = _run_with_posix_alarm_timeout(
                    per_call_timeout,
                    lambda book=book: book.api.saved.get(),
                )
                saved = str(saved_raw).strip().lower() == "true"
            except Exception:
                # If saved-state inspection itself is inconclusive, do not block.
                saved = True

            path = ""
            try:
                full_name = _run_with_posix_alarm_timeout(per_call_timeout, lambda book=book: book.fullname)
                path = _normalize_excel_session_path(full_name)
            except Exception:
                path = ""

            sessions.append(
                ExcelWorkbookSession(
                    pid=int(pid),
                    name=name,
                    saved=saved,
                    path=path,
                )
            )

    if pid_failures and not sessions:
        return _list_excel_workbooks_via_osascript(timeout_sec=timeout_sec)

    return sessions


def _excel_session_preflight(
    crm_path: Path,
    *,
    blocked_paths: Optional[List[Path]] = None,
    verbose: bool = False,
) -> None:
    """
    Fail fast only when the CRM workbook (or another write target) is already open in
    Excel. Unrelated dirty workbooks are allowed so operators can keep side work open.
    """
    sessions = _list_excel_workbooks()
    if not sessions:
        return

    target_paths = blocked_paths or [crm_path]
    normalized_targets: List[Path] = []
    for target in target_paths:
        try:
            normalized_targets.append(target.expanduser().resolve())
        except Exception:
            normalized_targets.append(target.expanduser())
    target_path_lookup = {str(path): path for path in normalized_targets}
    target_name_lookup = {
        path.name.strip().casefold(): path
        for path in normalized_targets
        if path.name.strip()
    }

    matched_conflicts: List[Tuple[Path, ExcelWorkbookSession]] = []
    for session in sessions:
        session_path = _normalize_excel_session_path(session.path)
        matches_target: Optional[Path] = None
        if session_path:
            try:
                resolved = Path(session_path).expanduser().resolve()
                matches_target = target_path_lookup.get(str(resolved))
            except Exception:
                matches_target = target_path_lookup.get(session_path)
        if matches_target is None:
            session_name = (session.name or "").strip().casefold()
            if session_name:
                matches_target = target_name_lookup.get(session_name)
        if matches_target is not None:
            matched_conflicts.append((matches_target, session))

    if matched_conflicts:
        target_path, session = matched_conflicts[0]
        if target_path.name == crm_path.name:
            raise ExcelTargetConflictError(
                "CRM workbook is already open in Excel. Close it before import to avoid concurrent workbook sessions."
            )
        label = target_path.name or str(target_path)
        raise ExcelTargetConflictError(
            "Excel target workbook is already open in Excel: "
            f"{label}. Close it before import to avoid concurrent workbook sessions."
        )

    if verbose:
        dirty_side_count = sum(1 for session in sessions if not session.saved)
        print(
            "  Excel session guard OK "
            f"({len(sessions)} open workbook(s), target-only policy, dirty side books ignored={dirty_side_count})"
        )


def _excel_open_probe(workbook_path: Path, attempts: int = 3, timeout_sec: int = 45) -> Tuple[bool, str]:
    """
    Ask Microsoft Excel to open and close workbook_path.
    Returns (ok, diagnostic_message).
    """
    if attempts <= 0:
        attempts = 1
    workbook_path = workbook_path.expanduser().resolve()

    def _run_osascript(script_text: str, script_timeout: Optional[int] = None) -> Tuple[int, str]:
        timeout = max(int(script_timeout or timeout_sec), 1)
        try:
            proc = subprocess.run(
                ["osascript", "-"],
                input=script_text,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return 124, f"osascript timeout after {timeout}s"
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, out

    escaped = str(workbook_path).replace("\\", "\\\\").replace('"', '\\"')
    open_script = f"""
set workbookPath to POSIX file "{escaped}"
set workbookPosixPath to POSIX path of workbookPath
set workbookName to do shell script "/usr/bin/basename " & quoted form of workbookPosixPath
tell application "Microsoft Excel"
    try
        set display alerts to false
    end try
    try
        activate
        open workbookPath
        set wbList to get workbooks
        set matchedWorkbook to false
        repeat with wb in wbList
            try
                set wbName to name of wb
                if wbName is workbookName then
                    close wb saving no
                    set matchedWorkbook to true
                    exit repeat
                end if
            end try
        end repeat
        if matchedWorkbook then
            return "OK"
        end if
        return "ERR:-1728:Could not match opened workbook by full path"
    on error errMsg number errNum
        return "ERR:" & errNum & ":" & errMsg
    end try
end tell
"""
    close_script = f"""
set workbookPath to POSIX path of (POSIX file "{escaped}")
set workbookName to do shell script "/usr/bin/basename " & quoted form of workbookPath
tell application "Microsoft Excel"
    try
        set display alerts to false
    end try
    try
        set wbList to get workbooks
        repeat with wb in wbList
            try
                set wbName to name of wb
                if wbName is workbookName then
                    close wb saving no
                    exit repeat
                end if
            end try
        end repeat
    end try
end tell
"""

    last_msg = ""
    for _ in range(attempts):
        code, out = _run_osascript(open_script)
        if code == 0 and out.strip() == "OK":
            return True, "OK"
        last_msg = out or f"osascript rc={code}"
        _run_osascript(close_script, script_timeout=8)
    return False, last_msg


def _verify_candidate_workbook(
    candidate_path: Path,
    strict_excel: bool = True,
    verbose: bool = False,
    allowed_integrity_errors: Optional[set[str]] = None,
) -> None:
    """
    Validate candidate workbook before promotion.
    """
    result = validate_workbook_integrity(candidate_path)
    baseline_errors = allowed_integrity_errors or set()
    candidate_errors = list(result.errors or [])
    new_errors = [err for err in candidate_errors if err not in baseline_errors]
    if new_errors:
        sample = "; ".join(new_errors[:3])
        details = f" Examples: {sample}" if sample else ""
        raise RuntimeError(
            "Candidate workbook integrity validation failed. "
            f"Found {len(new_errors)} new errors.{details}"
        )
    if verbose and baseline_errors and candidate_errors:
        inherited = [err for err in candidate_errors if err in baseline_errors]
        if inherited:
            print(
                "  WARNING: candidate workbook retained baseline integrity errors "
                f"({len(inherited)} inherited)."
            )
    if verbose and result.warnings:
        for msg in result.warnings:
            print(f"  WARNING: candidate integrity warning: {msg}")

    if strict_excel:
        ok, detail = _excel_open_probe(candidate_path, attempts=2, timeout_sec=35)
        if not ok:
            detail_lower = (detail or "").lower()
            if "timeout" in detail_lower:
                if verbose:
                    print(
                        "  WARNING: candidate Excel open probe timed out; "
                        "continuing after integrity pass."
                    )
            else:
                raise RuntimeError(f"Excel open probe failed for candidate workbook: {detail}")


def _workbook_external_link_targets(workbook_path: Path) -> Tuple[str, ...]:
    workbook_path = Path(workbook_path).expanduser()
    try:
        with zipfile.ZipFile(workbook_path, "r") as zf:
            rel_payload = zf.read("xl/_rels/workbook.xml.rels")
    except Exception:
        return tuple()

    try:
        rels_root = ET.fromstring(rel_payload)
    except Exception:
        return tuple()

    rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    external_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink"
    targets: List[str] = []
    for rel in rels_root.findall(f"{rel_ns}Relationship"):
        if rel.attrib.get("Type") != external_type:
            continue
        target = str(rel.attrib.get("Target") or "").strip()
        if target:
            normalized = target.replace("\\", "/").strip()
            if normalized.startswith("/"):
                normalized = normalized[1:]
            if normalized.startswith("xl/"):
                normalized = normalized[3:]
            normalized = posixpath.normpath(normalized)
            targets.append(normalized)
    return tuple(sorted(targets))


def _prefer_excel_native_postprocess(workbook_path: Path) -> bool:
    """
    On macOS, keep post-append processing inside Excel for workbooks that carry
    external-link relationships. Read-only verification remains safe.
    """
    return sys.platform == "darwin" and bool(_workbook_external_link_targets(workbook_path))


def _candidate_source_requires_template_normalization(
    source_path: Path,
    *,
    template_path: Path | None = None,
) -> bool:
    source_path = Path(source_path).expanduser().resolve()
    result = validate_workbook_integrity(source_path)
    blocking_errors, _allowed_errors = filter_integrity_errors(
        result.errors,
        allow_exact=KNOWN_BASELINE_INTEGRITY_ERRORS,
        allow_prefix=RUNTIME_ALLOWED_INTEGRITY_ERROR_PREFIXES,
    )
    if blocking_errors:
        return True
    for err in result.errors or []:
        if str(err or "").startswith("CRM sales sheet contains self-externalized formulas:"):
            return True
    return False


def _candidate_workbook_path(source_path: Path, candidate_dir: Path) -> Path:
    source_path = Path(source_path).expanduser()
    candidate_dir = Path(candidate_dir).expanduser()
    return candidate_dir / f"{source_path.stem}.candidate{source_path.suffix}"


def _prepare_candidate_workbook(source_path: Path, candidate_dir: Path, verbose: bool = False) -> Path:
    """
    Create the stable transactional candidate workbook.

    Keep the Excel-facing candidate path stable on macOS so Excel does not get
    pointed at a fresh hidden filename every run, which can trigger repeated
    file-access prompts. The workbook contents are still rebuilt atomically from
    the source on each run.
    """
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = _candidate_workbook_path(source_path, candidate_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_candidate_path = candidate_dir / f"{source_path.stem}.candidate_tmp_{ts}{source_path.suffix}"
    if _candidate_source_requires_template_normalization(source_path):
        try:
            restore_stats = restore_crm_workbook_from_template(
                workbook_path=source_path,
                output_path=temp_candidate_path,
                verbose=verbose,
            )
            os.replace(str(temp_candidate_path), str(candidate_path))
            if verbose:
                print(f"  Candidate workbook created: {candidate_path}")
                print(
                    "  Candidate template-restore stats: "
                    f"rows={restore_stats.get('sales_rows_preserved', 0)}, "
                    f"formulas={restore_stats.get('sales_formulas_restored', 0)}, "
                    f"styles={restore_stats.get('sales_styles_restored', 0)}, "
                    f"externalized_cleared={restore_stats.get('sales_externalized_formulas_cleared', 0)}"
                )
            return candidate_path
        finally:
            if temp_candidate_path.exists():
                temp_candidate_path.unlink()

    try:
        shutil.copy2(source_path, temp_candidate_path)
        os.replace(str(temp_candidate_path), str(candidate_path))
    finally:
        if temp_candidate_path.exists():
            temp_candidate_path.unlink()
    if verbose:
        print(f"  Candidate workbook created: {candidate_path}")
        print("  Candidate fast-path: direct copy (source workbook already matches canonical contract)")
    return candidate_path


def _promote_candidate_workbook(
    source_path: Path,
    candidate_path: Path,
    failed_dir: Path,
    strict_excel: bool = True,
    verbose: bool = False,
) -> None:
    """
    Promote candidate workbook into production path only after validation passes.
    On failure, move candidate into failed_dir and leave source untouched.
    """
    if not candidate_path.exists():
        raise FileNotFoundError(f"Candidate workbook not found: {candidate_path}")

    baseline_errors: set[str] = set()
    try:
        source_integrity = validate_workbook_integrity(source_path)
        baseline_errors = set(source_integrity.errors or [])
    except Exception as source_exc:
        # Preserve transactional safety for candidate promotion tests and
        # fallback paths where source integrity cannot be probed.
        if verbose:
            print(
                "  WARNING: source workbook integrity baseline unavailable; "
                f"continuing with empty baseline ({source_exc})"
            )

    probe_promoted_source = (
        bool(strict_excel)
        and sys.platform == "darwin"
        and _is_transactional_candidate_target(candidate_path, source_path)
    )

    try:
        _verify_candidate_workbook(
            candidate_path,
            strict_excel=(False if probe_promoted_source else strict_excel),
            verbose=verbose,
            allowed_integrity_errors=baseline_errors,
        )
    except Exception as exc:
        failed_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        failed_path = failed_dir / f"{candidate_path.stem}.failed_{ts}{candidate_path.suffix}"
        if candidate_path.exists():
            shutil.move(str(candidate_path), str(failed_path))
        raise RuntimeError(
            f"Candidate workbook verification failed: {exc}. "
            "Source workbook left unchanged. "
            f"Failed candidate saved at: {failed_path}"
        ) from exc

    os.replace(str(candidate_path), str(source_path))
    if probe_promoted_source:
        ok, detail = _excel_open_probe(source_path, attempts=2, timeout_sec=35)
        if not ok:
            detail_lower = (detail or "").lower()
            if "timeout" not in detail_lower:
                raise RuntimeError(f"Promoted workbook Excel open probe failed: {detail}")
            if verbose:
                print(
                    "  WARNING: promoted workbook Excel open probe timed out; "
                    "continuing after integrity pass."
                )
    if verbose:
        print(f"  Candidate promoted: {source_path.name}")


# ---------- Configuration ----------

STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
    '30362323_PP1': 'Store-C',
}

DEFAULT_STATUS = 'Ожидает передачи курьеру'
DEFAULT_SIGNATURE = 'Не требуется'

# Public constants used by tests (legacy aliases)
READY_STATUS = DEFAULT_STATUS
NO_SIGNATURE = DEFAULT_SIGNATURE

# Raw Kaspi column mapping (Y-AZ)
RAW_KASPI_COLUMNS = {
    "№ заказа": "Y",
    "Статус": "Z",
    "Дата изменения статуса": "AA",
    "Требуется подписание": "AB",
    "Плановая дата передачи курьеру": "AC",
    "Название товара в Kaspi Магазине": "AD",
    "Название в системе продавца": "AE",
    "Артикул": "AF",
    "Склад передачи КД": "AG",
    "Телефон": "AH",
    "Количество": "AI",
    "Цена": "AJ",
    "Сумма": "AK",
    "Адрес доставки": "AL",
    "ФИО": "AM",
    "Комментарий": "AN",
    "Способ доставки": "AO",
    "Дата создания": "AP",
    "Код товара": "AQ",
    "Kaspi_Offer_ID": "AR",
    "SKU_key": "AS",
    "SKU_ID": "AT",
    "MY_SIZE": "AU",
    "STORE_NAME": "AV",
    "KASPI_NAME_CORE": "AW",
    "Warehouse": "AX",
    "Seller_name": "AY",
    "Internal_Status": "AZ",
}

PROTECTED_HUMAN_COLUMNS = {
    "MY_SIZE",
}

KNOWN_BASELINE_INTEGRITY_ERRORS = {
    "named range contains #REF!: B",
    "named range contains #REF!: B_DAYS",
    "named range contains #REF!: D",
    "named range contains #REF!: D_AFTER",
    "named range contains #REF!: L",
    "named range contains #REF!: L_DAYS",
    "named range contains #REF!: SS_TOTAL",
    "named range contains #REF!: T_POST",
    "named range contains #REF!: TV",
    "named range contains #REF!: TV_FLOOR",
    "named range contains #REF!: Z",
    "named range contains #REF!: Z_LEVEL",
}

KNOWN_BASELINE_INTEGRITY_ERROR_PREFIXES = (
    # Legacy date-scoped names can be regenerated by Excel as broken refs.
    # They do not affect CRM import data integrity and are already allowed
    # by the canonical wrapper command.
    "named range contains #REF!: _",
)

RUNTIME_ALLOWED_INTEGRITY_ERROR_PREFIXES = (
    *KNOWN_BASELINE_INTEGRITY_ERROR_PREFIXES,
    # Older operator-approved CRM baselines can contain self-externalized
    # formulas in pre-existing sales rows. Treat that as a tolerated source
    # baseline for candidate/preflight decisions, but still block any new
    # append-region regressions via _verify_appended_rows_integrity().
    "CRM sales sheet contains self-externalized formulas:",
)


def _default_candidate_dirs_for_workbook(workbook_path: Path) -> Tuple[Path, Path]:
    workbook_path = Path(workbook_path).expanduser()
    base_dir = workbook_path.parent
    return (
        base_dir,
        base_dir / ".crm_failed_candidates",
    )


def _allow_openpyxl_backfill_fallback() -> bool:
    """
    Openpyxl saves can rewrite workbook package internals on complex files.
    Keep this fallback disabled unless explicitly enabled via env.
    """
    raw = os.getenv("CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _allow_openpyxl_append_fallback() -> bool:
    """
    Enable openpyxl append fallback only when explicitly requested.
    """
    raw = os.getenv("CRM_OPENPYXL_APPEND_FALLBACK", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _default_openpyxl_append_fallback_enabled() -> bool:
    """
    Keep openpyxl append fallback opt-in by default.
    This workbook carries external-link and package features that Excel itself
    preserves more safely than openpyxl saves do.
    """
    return False


def _default_prefer_xlwings_append() -> bool:
    """
    Prefer Excel-native writes for CRM append by default.
    """
    return True


def _use_transactional_candidate_workbook(transactional: bool) -> bool:
    """
    On macOS, Excel automation against a secondary candidate path triggers the
    system "Grant Access" chooser. Keep transactional candidate promotion for
    non-macOS paths, but use backup-first live writes on macOS.
    """
    return bool(transactional) and sys.platform != "darwin"


def _prefer_openpyxl_safe_write_path() -> bool:
    """
    Keep openpyxl write helpers opt-in on macOS. They remain available as a
    bounded fallback, but should not be the default write path for the live CRM
    workbook.
    """
    return False


def _xlwings_open_timeout_sec(default_sec: int = 25) -> int:
    """
    Wall-clock timeout passed to xlwings workbook open calls.
    """
    raw = os.getenv("CRM_XLWINGS_OPEN_TIMEOUT_SEC", "")
    if not str(raw).strip():
        return int(default_sec)
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return int(default_sec)
    return max(parsed, 5)


def _xlwings_append_timeout_sec(default_sec: int = 240) -> int:
    """
    Wall-clock timeout for xlwings append execution before falling back.
    """
    raw = os.getenv("CRM_XLWINGS_APPEND_TIMEOUT_SEC", "")
    if not str(raw).strip():
        return int(default_sec)
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return int(default_sec)
    return max(parsed, 10)


def _xlwings_refresh_timeout_sec(default_sec: int = 120) -> int:
    """
    Wall-clock timeout for the post-repair Excel recalculation/save pass.
    """
    raw = os.getenv("CRM_XLWINGS_REFRESH_TIMEOUT_SEC", "")
    if not str(raw).strip():
        return int(default_sec)
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return int(default_sec)
    return max(parsed, 10)


@contextmanager
def _temporary_manual_calculation(app: Any):
    """
    Reduce append latency by disabling auto-recalc while writing rows.
    Always restore original calculation mode on exit.
    """
    switched = False
    original_mode = None
    try:
        try:
            original_mode = getattr(app, "calculation")
            setattr(app, "calculation", "manual")
            switched = True
        except Exception:
            switched = False
        yield
    finally:
        if not switched:
            return
        try:
            recalc = getattr(app, "calculate", None)
            if callable(recalc):
                recalc()
        except Exception:
            pass
        try:
            setattr(app, "calculation", original_mode)
        except Exception:
            pass


def _run_with_posix_alarm_timeout(timeout_sec: int, func, *args, **kwargs):
    """
    Execute callable with SIGALRM timeout on POSIX; no-op timeout on other OSes.
    """
    if os.name != "posix" or not hasattr(signal, "SIGALRM"):
        return func(*args, **kwargs)

    safe_timeout = max(int(timeout_sec), 1)

    def _alarm_handler(_signum, _frame):
        raise TimeoutError(f"operation timed out after {safe_timeout}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _alarm_handler)
    previous_alarm = signal.alarm(safe_timeout)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_alarm > 0:
            signal.alarm(previous_alarm)


def _safe_close_xlwings_book(book: Any, *, context: str) -> None:
    if book is None:
        return
    try:
        book.close()
    except Exception as exc:
        print(f"  WARNING: failed to close Excel workbook ({context}): {exc}")


def _safe_quit_xlwings_app(app: Any, *, context: str) -> None:
    if app is None:
        return
    try:
        app.quit()
        return
    except Exception as exc:
        print(f"  WARNING: failed to quit Excel app ({context}): {exc}")

    kill = getattr(app, "kill", None)
    if callable(kill):
        try:
            kill()
            print(f"  WARNING: Excel app force-killed ({context})")
        except Exception as kill_exc:
            print(f"  WARNING: failed to force-kill Excel app ({context}): {kill_exc}")


def _is_xlwings_table_access_failure(exc: Exception) -> bool:
    """
    Detect the macOS Excel/appscript failure class where table/list-object access
    becomes unavailable even though the workbook itself opened successfully.
    """
    if isinstance(exc, KeyError):
        return False
    message = str(exc)
    lowered = message.lower()
    return (
        "-1728" in message
        or "count(each=k.list_object)" in message
        or "object you are trying to access does not exist" in lowered
    )


def _create_temporary_workbook_snapshot(workbook_path: Path) -> Path:
    workbook_path = Path(workbook_path)
    snapshot_path = workbook_path.parent / (
        f".{workbook_path.name}.pre_append_snapshot.{os.getpid()}.{time.time_ns()}"
    )
    shutil.copy2(workbook_path, snapshot_path)
    return snapshot_path


def _restore_workbook_snapshot(snapshot_path: Path, workbook_path: Path) -> None:
    workbook_path = Path(workbook_path)
    snapshot_path = Path(snapshot_path)
    restore_tmp = workbook_path.parent / (
        f".{workbook_path.name}.restore.{os.getpid()}.{time.time_ns()}"
    )
    try:
        shutil.copy2(snapshot_path, restore_tmp)
        os.replace(restore_tmp, workbook_path)
    finally:
        try:
            if restore_tmp.exists():
                restore_tmp.unlink()
        except OSError:
            pass


def _cleanup_temporary_workbook_snapshot(snapshot_path: Path | None) -> None:
    if snapshot_path is None:
        return
    try:
        Path(snapshot_path).unlink(missing_ok=True)
    except OSError:
        pass


def _refresh_formula_caches_xlwings(workbook_path: Path, *, verbose: bool = False) -> None:
    """
    Re-open the workbook in Excel and save after recalculation so formula
    result caches are repopulated. This avoids the "empty rows" symptom caused
    by openpyxl save clearing cached formula values on the live CRM workbook.
    """
    def _refresh() -> None:
        _require_xlwings()

        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False
        wb = None
        previous_mode = None

        try:
            wb = _open_workbook_xlwings(app, workbook_path, update_links=False, read_only=False)
            try:
                previous_mode = getattr(app, "calculation")
                setattr(app, "calculation", "automatic")
            except Exception:
                previous_mode = None

            recalc = getattr(app, "calculate", None)
            if callable(recalc):
                recalc()
            try:
                api = getattr(app, "api", None)
                if api is not None:
                    calculate_full = getattr(api, "calculate_full", None)
                    if callable(calculate_full):
                        calculate_full()
            except Exception:
                pass

            wb.save()
            if verbose:
                print("  Formula caches refreshed via Excel save")
        finally:
            if previous_mode is not None:
                try:
                    setattr(app, "calculation", previous_mode)
                except Exception:
                    pass
            if wb is not None:
                _safe_close_xlwings_book(wb, context="formula-cache-refresh")
            _safe_quit_xlwings_app(app, context="formula-cache-refresh")

    _run_with_posix_alarm_timeout(_xlwings_refresh_timeout_sec(), _refresh)


def _is_transactional_candidate_target(workbook_path: Path, source_path: Path) -> bool:
    try:
        return Path(workbook_path).expanduser().resolve() != Path(source_path).expanduser().resolve()
    except Exception:
        return str(Path(workbook_path).expanduser()) != str(Path(source_path).expanduser())


def _is_expected_xlwings_timeout(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True

    msg = str(exc or "").lower()
    if not msg:
        return False

    timeout_markers = (
        "apple event timed out",
        "oserror: -1712",
        "(-1712)",
        "operation timed out",
        "xlwings workbook open timed out",
    )
    return any(marker in msg for marker in timeout_markers)


_ORDER_ID_HEADER_ALIASES = {"orderid", "номерзаказа", "заказ", "№заказа", "заказа"}


def _coerce_order_id_numeric(value: Any) -> Any:
    cleaned = clean_order_id(value)
    if cleaned:
        try:
            return int(cleaned)
        except (TypeError, ValueError):
            return cleaned
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        try:
            return int(text)
        except (TypeError, ValueError):
            return text
    return text


def _coerce_phone_numeric(value: Any) -> Any:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""

    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits

    try:
        return int(digits)
    except (TypeError, ValueError):
        return digits


def _clear_my_size_range(
    sheet: Any,
    top_row: int,
    bottom_row: int,
    my_size_col_abs: int,
) -> None:
    """
    Clear MY_SIZE cells with resilient fallbacks.

    Primary path uses clear_contents (small AppleEvent payload).
    Falls back to bulk write, then row-by-row writes only on expected timeout
    conditions to avoid aborting an otherwise successful append.
    """
    target = sheet.range((top_row, my_size_col_abs), (bottom_row, my_size_col_abs))

    clear_contents = getattr(target, "clear_contents", None)
    if callable(clear_contents):
        try:
            clear_contents()
            return
        except Exception as exc:
            if not _is_expected_xlwings_timeout(exc):
                raise

    try:
        target.value = [[None] for _ in range(bottom_row - top_row + 1)]
        return
    except Exception as exc:
        if not _is_expected_xlwings_timeout(exc):
            raise

    # Last resort: row-by-row write with tiny retry backoff.
    for row_idx in range(top_row, bottom_row + 1):
        for attempt in range(2):
            try:
                cell = sheet.range((row_idx, my_size_col_abs), (row_idx, my_size_col_abs))
                cell.value = [[None]]
                break
            except Exception as exc:
                if not _is_expected_xlwings_timeout(exc):
                    raise
                if attempt == 1:
                    raise
                time.sleep(0.2)


def _write_single_column_updates_xlwings(
    sheet: Any,
    col_abs: int,
    updates: List[Tuple[int, Any]],
) -> None:
    """
    Write sparse single-column updates via contiguous range assignments.

    This keeps AppleEvent traffic low on macOS Excel while still recovering
    gracefully if a larger batch times out.
    """
    if not updates:
        return

    ordered = sorted((int(row_num), value) for row_num, value in updates)

    def _write_batch(batch: List[Tuple[int, Any]]) -> None:
        if not batch:
            return
        start_row = batch[0][0]
        end_row = batch[-1][0]
        target = sheet.range((start_row, col_abs), (end_row, col_abs))
        payload: Any
        if len(batch) == 1:
            payload = batch[0][1]
        else:
            payload = [[value] for _row_num, value in batch]
        try:
            target.value = payload
            return
        except Exception as exc:
            if len(batch) == 1 or not _is_expected_xlwings_timeout(exc):
                raise

        mid = max(len(batch) // 2, 1)
        _write_batch(batch[:mid])
        _write_batch(batch[mid:])

    current_batch: List[Tuple[int, Any]] = [ordered[0]]
    for row_num, value in ordered[1:]:
        if row_num == current_batch[-1][0] + 1:
            current_batch.append((row_num, value))
            continue
        _write_batch(current_batch)
        current_batch = [(row_num, value)]
    _write_batch(current_batch)


def _open_workbook_xlwings_without_timeout_kwarg(
    app: Any,
    workbook_path: Path,
    open_kwargs: Dict[str, Any],
    timeout_sec: int,
) -> Any:
    """
    Open workbook via xlwings when timeout kwarg is unavailable.
    On POSIX, enforce wall-clock timeout via SIGALRM.
    """
    kwargs = dict(open_kwargs)
    if os.name != "posix" or not hasattr(signal, "SIGALRM"):
        return app.books.open(str(workbook_path), **kwargs)

    safe_timeout = max(int(timeout_sec), 1)

    def _alarm_handler(_signum, _frame):
        raise TimeoutError(f"xlwings workbook open timed out after {safe_timeout}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _alarm_handler)
    previous_alarm = signal.alarm(safe_timeout)
    try:
        return app.books.open(str(workbook_path), **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_alarm > 0:
            signal.alarm(previous_alarm)


def _open_workbook_xlwings(
    app: Any,
    workbook_path: Path,
    *,
    update_links: bool = False,
    read_only: bool = False,
) -> Any:
    """
    Open workbook via xlwings with explicit wall-clock timeout to avoid indefinite hangs.
    """
    timeout_sec = _xlwings_open_timeout_sec()

    if sys.platform == "darwin":
        # macOS Excel automation is materially more reliable with the minimal open
        # contract, but still needs a hard wall-clock guard so operator runs fail
        # fast instead of hanging inside Excel open for many minutes.
        return _open_workbook_xlwings_without_timeout_kwarg(
            app,
            workbook_path,
            {},
            timeout_sec,
        )

    open_kwargs: Dict[str, Any] = {
        "update_links": update_links,
        "read_only": read_only,
        "timeout": timeout_sec,
    }
    try:
        return app.books.open(str(workbook_path), **open_kwargs)
    except TypeError as exc:
        # Older xlwings releases on macOS do not expose timeout kwarg.
        if "timeout" in str(exc).lower():
            open_kwargs.pop("timeout", None)
            return _open_workbook_xlwings_without_timeout_kwarg(
                app,
                workbook_path,
                open_kwargs,
                timeout_sec,
            )
        raise


def _workbook_integrity_preflight(crm_path: Path, verbose: bool = False) -> None:
    """
    Validate workbook package integrity before any write path is attempted.
    """
    result = validate_workbook_integrity(crm_path)
    blocking_errors, allowed_errors = filter_integrity_errors(
        result.errors,
        allow_exact=KNOWN_BASELINE_INTEGRITY_ERRORS,
        allow_prefix=RUNTIME_ALLOWED_INTEGRITY_ERROR_PREFIXES,
    )
    if blocking_errors:
        sample = "; ".join(blocking_errors[:3])
        details = f" Examples: {sample}" if sample else ""
        raise RuntimeError(
            "Workbook integrity preflight failed. "
            f"Found {len(blocking_errors)} integrity errors.{details}"
        )
    if verbose and allowed_errors:
        print(
            "  WARNING: workbook integrity preflight retained baseline errors "
            f"({len(allowed_errors)} allowed)."
        )
    if verbose and result.warnings:
        for msg in result.warnings:
            print(f"  WARNING: integrity check: {msg}")


def _excel_automation_preflight(
    crm_path: Path,
    strict_excel: bool = True,
    verbose: bool = False,
    transactional: bool = True,
    candidate_dir: Optional[Path] = None,
    allow_open_probe_fallback: bool = False,
) -> None:
    """
    Validate that Excel automation can safely control the workbook before writes.
    Excel session guard always runs; strict mode adds workbook-open probing.
    """
    blocked_paths = [crm_path]
    if _use_transactional_candidate_workbook(transactional) and candidate_dir is not None:
        blocked_paths.append(_candidate_workbook_path(crm_path, candidate_dir))
    _excel_session_preflight(crm_path, blocked_paths=blocked_paths, verbose=verbose)

    if not strict_excel:
        return
    lock_file = crm_path.parent / f"~${crm_path.name}"
    if lock_file.exists():
        age_seconds = datetime.now().timestamp() - lock_file.stat().st_mtime
        if age_seconds < 30 * 60:
            raise ExcelTargetConflictError(
                f"Excel lock file detected ({lock_file.name}). Close workbook and retry."
            )
        if verbose:
            print(
                "  WARNING: stale Excel lock file detected; ignoring "
                f"({lock_file.name}, age={int(age_seconds)}s)"
            )

    _workbook_integrity_preflight(crm_path, verbose=verbose)

    skip_source_open_probe = (
        _use_transactional_candidate_workbook(transactional)
        and _candidate_source_requires_template_normalization(crm_path)
    )
    if skip_source_open_probe:
        if verbose:
            print(
                "  WARNING: skipping source workbook Excel open probe on macOS; "
                "transactional candidate normalization will verify the candidate workbook instead."
            )
        return

    def _run_open_probe_fallback() -> None:
        ok, detail = _excel_open_probe(crm_path, attempts=2, timeout_sec=35)
        if ok:
            if verbose:
                print("  Strict Excel preflight OK (Excel open probe)")
            return
        detail_lower = (detail or "").lower()
        if "timeout" in detail_lower:
            if verbose:
                print(
                    "  WARNING: Excel open probe timed out after workbook/session preflight; "
                    "continuing."
                )
            return
        raise RuntimeError(f"Excel open probe failed: {detail}")

    if sys.platform == "darwin":
        _run_open_probe_fallback()
        return

    if xw is None:
        if allow_open_probe_fallback:
            _run_open_probe_fallback()
            return
        raise RuntimeError("xlwings is required for strict Excel mode.")

    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    try:
        wb = _open_workbook_xlwings(
            app,
            crm_path,
            update_links=False,
            read_only=True,
        )
        wb.close()
        if verbose:
            print("  Strict Excel preflight OK")
    except Exception as exc:
        if allow_open_probe_fallback:
            if verbose:
                print(
                    "  WARNING: xlwings strict preflight open failed; "
                    "retrying via Excel open probe."
                )
            _run_open_probe_fallback()
            return
        raise RuntimeError(
            "Excel automation preflight failed (macOS Automation/Excel state issue). "
            "Grant python automation access to Excel and close all open workbook sessions."
        ) from exc
    finally:
        _safe_quit_xlwings_app(app, context="strict preflight")


LINE61_CANONICAL_SKU_KEY = "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
LINE61_CANONICAL_CORE = "6в1_Черный_+Сумка"

FIXED_APPEND_COLUMNS = [
    "STORE_NAME",
    "Quantity",
    "Kaspi_name_core",
    "KASPI_OFFER_NAME",
    "SKU_key",
    "Sell_price_kzt",
    "Total_price",
    "Total_net_rev",
    "MODEL",
    "PLANNED_SHIPPING_DATE",
    "Product_Type",
    "Delivery_fee_kzt",
    "Total_weight",
    "SKU_ID_KSP",
    "Kaspi_name_source",
]

# For recent backfill we use the same set and still avoid human-owned columns.
FIXED_BACKFILL_COLUMNS = list(FIXED_APPEND_COLUMNS)

# Canonical header mapping
CANON = {
    "order_id": ["№заказа", "номерзаказа", "orderid", "заказа"],  # заказа is normalized from "№ заказа"
    "status": ["статус"],
    "status_change_date": ["датаизменениястатуса"],  # Phase 12 Part 6: status change timestamp
    "signature": ["требуетсяподписание"],
    "handover": ["плановаядатапередачикурьеру", "плановаядатапередачи"],
    "offer_name": ["названиетоваравkaspiмагазине"],
    "seller_name": ["названиевсистемепродавца"],
    "sku": ["артикул"],
    "warehouse": ["складпередачикд", "складпередачикурьерскойдоставки"],
    "phone": ["телефон", "phone", "cellphone"],
    "quantity": ["количество", "qty", "quantity"],
}


# ---------- Helpers ----------

def norm(s: str) -> str:
    """Normalize header for matching (lowercase, no punct, cyrillic-friendly)."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ё", "е")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s", "", s)
    return s


def normalize_article_code(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return re.sub(r"^[\d\s]+", "", text).strip()


def map_headers(df: pd.DataFrame) -> Dict[str, str]:
    """Return dict canonical_key -> actual df column name."""
    colmap = {}
    cols_norm = {norm(c): c for c in df.columns}
    for k, variants in CANON.items():
        for v in variants:
            v_norm = norm(v)
            if v_norm in cols_norm:
                colmap[k] = cols_norm[v_norm]
                break
    return colmap


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        raw = value.strip().replace(" ", "")
        if not raw:
            return default
        raw = raw.replace(",", ".")
    else:
        raw = value
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_to_float(value, float(default))))
    except (TypeError, ValueError):
        return default


def _norm_key_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _build_line_dedupe_key(
    order_id: Optional[str],
    planned_date: Optional[date],
    offer_name: Any,
    article: Any,
    quantity: Any,
) -> str:
    clean_order = clean_order_id(order_id) or ""
    planned_iso = planned_date.isoformat() if planned_date else ""
    offer_key = _norm_key_text(offer_name)
    article_key = _norm_key_text(normalize_article_code(article))
    quantity_key = str(_to_int(quantity, 0))
    return f"{clean_order}|{planned_iso}|{article_key}|{offer_key}|{quantity_key}"


@dataclass(frozen=True)
class CRMDateBlockRow:
    row_num: int
    line_key: str
    my_size: str = ""


@dataclass(frozen=True)
class CRMAppendDateReconcilePlan:
    delete_row_numbers: list[int]
    keep_keys: set[str]
    keep_rows_by_key: Dict[str, CRMDateBlockRow]
    missing_keys: list[str]


@dataclass(frozen=True)
class CRMAppendExpectation:
    line_key: str
    order_id: str


def guard_reconcile_delete_volume(
    existing_rows: List[CRMDateBlockRow],
    desired_keys: List[str],
    delete_row_numbers: List[int],
    *,
    append_date: date,
    allow_large_reconcile_delete: bool = False,
) -> None:
    """
    Fail closed when reconcile would shrink the append-date block too aggressively.

    Small duplicate trimming is allowed. Large stale-key deletes require an explicit
    operator override because they can erase most of a day's CRM history if the
    import source is partial.
    """
    if allow_large_reconcile_delete or not delete_row_numbers or not existing_rows:
        return

    desired_key_set = set(desired_keys)
    delete_row_set = set(int(row_num) for row_num in delete_row_numbers)
    deleted_rows = [row for row in existing_rows if row.row_num in delete_row_set]
    stale_deleted_rows = [row for row in deleted_rows if row.line_key not in desired_key_set]
    if not stale_deleted_rows:
        return

    total_existing = len(existing_rows)
    stale_delete_count = len(stale_deleted_rows)
    stale_delete_fraction = stale_delete_count / total_existing if total_existing else 0.0
    stale_manual_count = sum(1 for row in stale_deleted_rows if str(row.my_size or "").strip())

    if stale_delete_count >= 5 and stale_delete_fraction >= 0.20:
        sample = ", ".join(str(row.row_num) for row in stale_deleted_rows[:5])
        raise RuntimeError(
            "Refusing destructive CRM reconcile delete for "
            f"Date {append_date.isoformat()}: would delete {stale_delete_count} stale row(s) "
            f"out of {total_existing} existing append-date row(s) "
            f"({stale_delete_fraction:.0%}), including {stale_manual_count} row(s) with MY_SIZE. "
            f"Sample row numbers: {sample}. Re-run only with explicit --allow-large-reconcile-delete "
            "if this shrink is intentional."
        )


def augment_desired_keys_with_existing_rollovers(
    desired_keys: List[str],
    existing_rows: List[CRMDateBlockRow],
    existing_rollover_keys: set[str],
) -> List[str]:
    """
    Preserve already-imported carry-forward rows on same-day reruns.

    Once an overdue pending row has been intentionally carried into today's CRM
    append-date block, later smaller pending snapshots should not try to delete
    it just because the current API view narrowed. We only top up the desired
    multiplicity to match existing rollover rows already present today.
    """
    if not existing_rows or not existing_rollover_keys:
        return list(desired_keys)

    augmented = list(desired_keys)
    desired_counts = Counter(augmented)
    rollover_counts = Counter(
        row.line_key for row in existing_rows if row.line_key in existing_rollover_keys
    )
    for key, count in rollover_counts.items():
        missing = max(int(count) - int(desired_counts.get(key, 0)), 0)
        if missing > 0:
            augmented.extend([key] * missing)
    return augmented


def plan_append_date_reconcile(
    existing_rows: List[CRMDateBlockRow],
    desired_keys: List[str],
) -> CRMAppendDateReconcilePlan:
    """
    Reconcile append-date CRM rows against the desired pending line-key universe.

    Keeps at most the desired multiplicity for each key, preferring rows with
    operator-entered MY_SIZE so manual work survives repeated imports.
    """
    desired_counts = Counter(desired_keys)
    rows_by_key: Dict[str, List[CRMDateBlockRow]] = {}
    for row in existing_rows:
        rows_by_key.setdefault(row.line_key, []).append(row)

    keep_rows_by_key: Dict[str, CRMDateBlockRow] = {}
    delete_row_numbers: list[int] = []

    for key, rows in rows_by_key.items():
        keep_count = max(int(desired_counts.get(key, 0)), 0)
        ranked_rows = sorted(
            rows,
            key=lambda row: (0 if str(row.my_size or "").strip() else 1, row.row_num),
        )
        keep_rows = ranked_rows[:keep_count]
        if keep_rows:
            keep_rows_by_key[key] = keep_rows[0]
        delete_row_numbers.extend(row.row_num for row in ranked_rows[keep_count:])

    delete_row_numbers = sorted(set(delete_row_numbers), reverse=True)
    keep_keys = set(keep_rows_by_key.keys())

    # Existing duplicates trimmed above count as present; missing keys are
    # whatever the desired universe still lacks after keep/delete selection.
    final_existing_counts = Counter(row.line_key for row in existing_rows) - Counter(
        row.line_key for row in existing_rows if row.row_num in set(delete_row_numbers)
    )
    missing_keys = []
    for key, desired_count in desired_counts.items():
        missing = max(int(desired_count) - int(final_existing_counts.get(key, 0)), 0)
        if missing <= 0:
            continue
        missing_keys.extend([key] * missing)

    return CRMAppendDateReconcilePlan(
        delete_row_numbers=delete_row_numbers,
        keep_keys=keep_keys,
        keep_rows_by_key=keep_rows_by_key,
        missing_keys=missing_keys,
    )


def build_append_expectations(
    df: pd.DataFrame,
    *,
    colmap: Dict[str, str],
) -> list[CRMAppendExpectation]:
    """Build semantic append expectations for the rows we intend to append."""
    expectations: list[CRMAppendExpectation] = []
    order_col = colmap.get("order_id")
    handover_col = colmap.get("handover")
    offer_col = colmap.get("offer_name")
    sku_col = colmap.get("sku")
    qty_col = colmap.get("quantity")

    for _, row in df.iterrows():
        order_id = clean_order_id(row.get(order_col) if order_col else "")
        line_key = _coerce_str(row.get("_okey"))
        if not line_key:
            line_key = _build_line_dedupe_key(
                order_id,
                parse_date(row.get(handover_col)) if handover_col else None,
                row.get(offer_col) if offer_col else "",
                row.get(sku_col) if sku_col else "",
                row.get(qty_col) if qty_col else 0,
            )
        expectations.append(CRMAppendExpectation(line_key=line_key, order_id=order_id))

    return expectations


def find_missing_append_expectations(
    expectations: List[CRMAppendExpectation],
    actual_counts: Dict[str, int],
) -> list[CRMAppendExpectation]:
    """
    Compare intended append line keys against the live append-date CRM block.

    Multiplicity matters. If Excel silently drops one row from an otherwise
    duplicated key set, we still want the specific missing row surfaced.
    """
    remaining = Counter({str(k): int(v) for k, v in (actual_counts or {}).items()})
    missing: list[CRMAppendExpectation] = []
    for expectation in expectations:
        if remaining.get(expectation.line_key, 0) > 0:
            remaining[expectation.line_key] -= 1
            continue
        missing.append(expectation)
    return missing


def verify_expected_append_rows(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    *,
    append_date: date,
    expectations: List[CRMAppendExpectation],
) -> list[CRMAppendExpectation]:
    """Reload CRM and confirm the intended append-date rows actually exist."""
    if not expectations:
        return []
    snapshot = load_crm_snapshot(
        crm_path,
        sheet_name,
        table_name,
        append_date=append_date,
    )
    return find_missing_append_expectations(expectations, snapshot.append_date_key_counts)


def _load_article_identity_for_articles(articles: List[str]) -> Dict[str, Dict[str, str]]:
    clean_articles = sorted(
        {
            str(a).strip()
            for a in articles
            for a in (a, normalize_article_code(a))
            if str(a).strip()
        }
    )
    if not clean_articles:
        return {}
    mapped: Dict[str, Dict[str, str]] = {}
    chunk_size = 800
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone():
            return {}
        for i in range(0, len(clean_articles), chunk_size):
            batch = clean_articles[i : i + chunk_size]
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT kaspi_article, sku_key, sku_id, kaspi_name_core
                FROM dim_kaspi_article_map
                WHERE active_flag = 1
                  AND kaspi_article IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                batch,
            ).fetchall()
            for row in rows:
                article = str(row["kaspi_article"] or "").strip()
                if not article or article in mapped:
                    continue
                mapped[article] = {
                    "sku_key": str(row["sku_key"] or "").strip(),
                    "sku_id": str(row["sku_id"] or "").strip(),
                    "kaspi_name_core": str(row["kaspi_name_core"] or "").strip(),
                }
    return mapped


def _load_seller_delivery_fees_from_db(order_ids: List[str]) -> Dict[str, float]:
    clean_order_ids = sorted({clean_order_id(v) for v in order_ids if clean_order_id(v)})
    clean_order_ids = [oid for oid in clean_order_ids if oid]
    if not clean_order_ids:
        return {}

    seller_fee_by_order: Dict[str, float] = {}
    chunk_size = 800
    with get_db() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone():
            return {}
        for i in range(0, len(clean_order_ids), chunk_size):
            batch = clean_order_ids[i : i + chunk_size]
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"""
                SELECT order_id, delivery_cost_for_seller
                FROM fact_orders_kaspi
                WHERE order_id IN ({placeholders})
                  AND delivery_cost_for_seller IS NOT NULL
                  AND delivery_cost_for_seller != 0
                """,
                batch,
            ).fetchall()
            for row in rows:
                order_id = clean_order_id(row["order_id"])
                if not order_id or order_id in seller_fee_by_order:
                    continue
                seller_fee_by_order[order_id] = float(row["delivery_cost_for_seller"])
    return seller_fee_by_order


def overlay_missing_seller_delivery_fees_from_db(df: pd.DataFrame) -> int:
    """Fill missing/zero seller delivery fee values in-place from DB truth."""
    if df.empty:
        return 0

    colmap = map_headers(df)
    order_col = colmap.get("order_id")
    seller_col = None
    for col in df.columns:
        if norm(col) == "стоимостьдоставкидляпродавца":
            seller_col = col
            break

    if not order_col or not seller_col:
        return 0

    seller_fee_by_order = _load_seller_delivery_fees_from_db(df[order_col].tolist())
    if not seller_fee_by_order:
        return 0

    updated = 0
    for idx, raw_order_id in df[order_col].items():
        order_id = clean_order_id(raw_order_id)
        if not order_id:
            continue
        db_fee = seller_fee_by_order.get(order_id)
        if db_fee is None or db_fee == 0:
            continue
        current_fee = _to_float(df.at[idx, seller_col], 0.0)
        if current_fee != 0.0:
            continue
        df.at[idx, seller_col] = db_fee
        updated += 1

    return updated


def _derive_identity_from_raw_row(
    raw_row: Dict[str, Any],
    article_identity_by_article: Optional[Dict[str, Dict[str, str]]] = None,
    valid_sku_keys: Optional[set[str]] = None,
) -> Dict[str, Optional[str]]:
    article_raw = str(
        raw_row.get("Артикул")
        or raw_row.get("SKU_ID_KSP")
        or raw_row.get("Kaspi_article")
        or ""
    ).strip()
    article = normalize_article_code(article_raw) or article_raw
    offer_name = str(
        raw_row.get("Название товара в Kaspi Магазине")
        or raw_row.get("KASPI_OFFER_NAME")
        or raw_row.get("Kaspi_offer")
        or ""
    ).strip()
    sku_key = str(raw_row.get("SKU_key") or "").strip() or None
    my_size = str(raw_row.get("MY_SIZE") or "").strip() or None
    product_type = str(raw_row.get("Product_Type") or "").strip() or None

    article_identity = (
        (article_identity_by_article or {}).get(article_raw)
        or (article_identity_by_article or {}).get(article)
        or (article_identity_by_article or {}).get(article.upper())
        or {}
    )
    if valid_sku_keys and sku_key and sku_key not in valid_sku_keys:
        sku_key = None
        my_size = None

    parsed = extract_sku_from_article(article, offer_name)
    parsed_sku_key = parsed.get("sku_key")
    parsed_my_size = parsed.get("my_size")
    parsed_product_type = parsed.get("product_type")
    if valid_sku_keys and parsed_sku_key and parsed_sku_key not in valid_sku_keys:
        parsed_sku_key = None
        parsed_my_size = None

    # Prefer deterministic article parser output first; DB article map is fallback
    # for legacy/unparseable article strings.
    if not sku_key and parsed_sku_key:
        sku_key = parsed_sku_key
    if not my_size and parsed_my_size:
        my_size = parsed_my_size
    if not product_type and parsed_product_type:
        product_type = parsed_product_type

    mapped_sku_key = str(article_identity.get("sku_key") or "").strip() or None
    mapped_sku_id = str(article_identity.get("sku_id") or "").strip() or None
    if mapped_sku_key and (not valid_sku_keys or mapped_sku_key in valid_sku_keys):
        if not sku_key:
            sku_key = mapped_sku_key
        if not my_size and mapped_sku_id and "_" in mapped_sku_id:
            my_size = mapped_sku_id.rsplit("_", 1)[-1]

    if sku_key and my_size:
        if not product_type and "_" in sku_key:
            product_type = sku_key.split("_", 1)[0]
        return {"sku_key": sku_key, "my_size": my_size, "product_type": product_type}

    if not sku_key:
        sku_key = parsed_sku_key
    if not my_size:
        my_size = parsed_my_size
    if not product_type:
        product_type = parsed_product_type
    if not product_type and sku_key and "_" in sku_key:
        product_type = sku_key.split("_", 1)[0]
    return {"sku_key": sku_key, "my_size": my_size, "product_type": product_type}


def _load_sku_meta_for_keys(sku_keys: List[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], set[str]]:
    clean_keys = sorted({str(k).strip() for k in sku_keys if str(k).strip()})
    sku_meta: Dict[str, Dict[str, Any]] = {}
    kaspi_core: Dict[str, str] = {}
    valid_sku_keys: set[str] = set()
    candidate_keys = sorted(
        {
            candidate
            for sku_key in clean_keys
            for candidate in iter_sku_family_candidates(sku_key)
        }
    )

    with get_db() as conn:
        has_dim_sku = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_sku'"
        ).fetchone()
        if clean_keys and has_dim_sku:
            placeholders = ",".join("?" for _ in clean_keys)
            rows = conn.execute(
                f"""
                SELECT sku_key, model, product_type, weight_kg
                FROM dim_sku
                WHERE sku_key IN ({placeholders})
                """,
                clean_keys,
            ).fetchall()
        else:
            rows = []
        for row in rows:
            sku_meta[row["sku_key"]] = {
                "model": row["model"],
                "product_type": row["product_type"],
                "weight_kg": row["weight_kg"],
            }
            valid_sku_keys.add(row["sku_key"])

        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
        ).fetchone() and candidate_keys:
            placeholders = ",".join("?" for _ in candidate_keys)
            core_rows = conn.execute(
                f"""
                SELECT sku_key, kaspi_name_core
                FROM dim_kaspi_article_map
                WHERE active_flag = 1
                  AND kaspi_name_core IS NOT NULL
                  AND TRIM(kaspi_name_core) <> ''
                  AND sku_key IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                candidate_keys,
            ).fetchall()
            for row in core_rows:
                if row["sku_key"] not in kaspi_core:
                    kaspi_core[row["sku_key"]] = str(row["kaspi_name_core"]).strip()

    return sku_meta, kaspi_core, valid_sku_keys


def compute_fixed_value_columns(
    raw_row: Dict[str, Any],
    sku_meta_by_key: Optional[Dict[str, Dict[str, Any]]] = None,
    kaspi_core_by_key: Optional[Dict[str, str]] = None,
    article_identity_by_article: Optional[Dict[str, Dict[str, str]]] = None,
    valid_sku_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """
    Compute trivial formula columns as fixed values.

    SKU_ID is intentionally excluded; it stays formula-driven in workbook.
    """
    sku_meta_by_key = sku_meta_by_key or {}
    kaspi_core_by_key = kaspi_core_by_key or {}
    identity = _derive_identity_from_raw_row(
        raw_row,
        article_identity_by_article=article_identity_by_article,
        valid_sku_keys=valid_sku_keys,
    )
    sku_key = identity.get("sku_key") or ""
    my_size = identity.get("my_size") or ""
    sku_meta = sku_meta_by_key.get(sku_key, {})

    quantity = _to_int(raw_row.get("Количество", raw_row.get("Quantity", 0)), 0)
    total_price = _to_float(raw_row.get("Сумма", raw_row.get("Total_price", 0.0)), 0.0)
    sell_price = (total_price / quantity) if quantity else 0.0

    delivery_fee = _to_float(raw_row.get("Стоимость доставки для продавца"), 0.0)
    # Mirror current workbook formula semantics: fixed 12.5% commission and 3% VAT.
    total_net_rev = ((total_price * (1 - 0.125)) - delivery_fee) * (1 - 0.03)

    warehouse = str(raw_row.get("Склад передачи КД") or "").strip()
    store_name = STORE_MAP.get(warehouse, "")

    model = str(sku_meta.get("model") or "").strip()
    product_type = str(identity.get("product_type") or sku_meta.get("product_type") or "").strip()
    weight_kg = _to_float(sku_meta.get("weight_kg"), 0.0)
    total_weight = weight_kg * quantity

    offer_name = str(
        raw_row.get("Название товара в Kaspi Магазине")
        or raw_row.get("KASPI_OFFER_NAME")
        or ""
    ).strip()
    article = str(
        raw_row.get("Артикул")
        or raw_row.get("SKU_ID_KSP")
        or raw_row.get("Kaspi_article")
        or ""
    ).strip()
    article_identity = (article_identity_by_article or {}).get(article) or {}
    mapped_core = str(article_identity.get("kaspi_name_core") or "").strip()
    store_code = WAREHOUSE_STORE_MAP.get(warehouse, "")
    kaspi_name_core = resolve_kaspi_name_core(
        store_code=store_code,
        kaspi_offer_name=offer_name,
        sku_key=sku_key,
        sku_id=article,
        maps=KaspiNameCoreMaps(by_store_offer={}, by_sku_key=kaspi_core_by_key or {}),
        preferred_core=mapped_core,
        preferred_source="article_identity",
    ).core
    if sku_key == LINE61_CANONICAL_SKU_KEY or article.upper().startswith("OF_SUIT-61_BLK_"):
        kaspi_name_core = LINE61_CANONICAL_CORE

    return {
        "STORE_NAME": store_name,
        "Quantity": quantity,
        "Kaspi_name_core": kaspi_name_core,
        "KASPI_OFFER_NAME": offer_name,
        "SKU_key": sku_key,
        "MY_SIZE": my_size,
        "Sell_price_kzt": sell_price,
        "Total_price": total_price,
        "Total_net_rev": total_net_rev,
        "MODEL": model,
        "PLANNED_SHIPPING_DATE": raw_row.get("Плановая дата передачи курьеру"),
        "Product_Type": product_type,
        "Delivery_fee_kzt": delivery_fee,
        "Total_weight": total_weight,
        "SKU_ID_KSP": str(raw_row.get("Артикул") or "").strip(),
        "Kaspi_name_source": str(raw_row.get("Название в системе продавца") or "").strip(),
    }


def _row_in_backfill_window(
    row_date: Optional[date],
    date_from: Optional[date],
    date_to: Optional[date],
) -> bool:
    if not row_date or not date_from or not date_to:
        return False
    return date_from <= row_date <= date_to


def _resolve_backfill_window(
    days: int,
    date_from: Optional[date],
    date_to: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    if days <= 0 and not date_from and not date_to:
        return (None, None)
    if not date_from and not date_to:
        date_to = today_local()
        date_from = date_to - timedelta(days=max(days - 1, 0))
    elif date_from and not date_to:
        date_to = date_from
    elif date_to and not date_from:
        date_from = date_to
    if not date_from or not date_to:
        return (None, None)
    if date_from > date_to:
        raise ValueError(f"fixed-value backfill date range invalid: {date_from} > {date_to}")
    return (date_from, date_to)


def build_fixed_value_payload(df_filt: pd.DataFrame) -> List[Dict[str, Any]]:
    rows = df_filt.to_dict(orient="records")
    articles = [str(r.get("Артикул") or r.get("SKU_ID_KSP") or "").strip() for r in rows]
    article_identity = _load_article_identity_for_articles(articles)
    identities = [
        _derive_identity_from_raw_row(
            r,
            article_identity_by_article=article_identity,
        )
        for r in rows
    ]
    sku_keys = [x.get("sku_key") for x in identities if x.get("sku_key")]
    sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys([str(k) for k in sku_keys])
    return [
        compute_fixed_value_columns(
            row,
            sku_meta,
            kaspi_core,
            article_identity_by_article=article_identity,
            valid_sku_keys=valid_sku_keys,
        )
        for row in rows
    ]


def build_resolved_my_size_by_key(
    df_filt: pd.DataFrame,
    latest_my_size_by_key: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Resolve a deterministic MY_SIZE for each line key.

    Precedence:
    1. Existing non-empty CRM MY_SIZE already seen for the same line key
    2. Deterministic identity parsing / DB-backed fixed-value derivation
    """
    if df_filt.empty:
        return {}

    work = df_filt.copy()
    colmap = map_headers(work)
    required = {"order_id", "handover", "offer_name", "sku", "quantity"}
    if "_okey" not in work.columns and required.issubset(colmap):
        work["_okey"] = work.apply(
            lambda row: _build_line_dedupe_key(
                row.get(colmap["order_id"]),
                parse_kz_date(row.get(colmap["handover"])),
                row.get(colmap["offer_name"]),
                row.get(colmap["sku"]),
                row.get(colmap["quantity"]),
            ),
            axis=1,
        )

    fixed_payload = build_fixed_value_payload(work)
    latest_map = latest_my_size_by_key or {}
    resolved: Dict[str, str] = {}

    for idx, row_vals in zip(work.index, fixed_payload):
        key = str(work.loc[idx, "_okey"]) if "_okey" in work.columns else ""
        if not key:
            continue
        preserved = str(latest_map.get(key) or "").strip()
        parsed = str(row_vals.get("MY_SIZE") or "").strip()
        resolved[key] = preserved or parsed

    return resolved


def build_kaspi_name_core_payload(df_filt: pd.DataFrame) -> List[str]:
    """Build explicit Kaspi_name_core values for appended rows only."""
    fixed_payload = build_fixed_value_payload(df_filt)
    return [str(row.get("Kaspi_name_core") or "").strip() for row in fixed_payload]


def parse_kz_date(v) -> Optional[date]:
    """Parse various date formats from Kaspi exports."""
    if pd.isna(v):
        return None
    s = str(v).strip()
    try:
        d = dtp.parse(s, dayfirst=True, yearfirst=False).date()
        return d
    except Exception:
        try:
            if isinstance(v, pd.Timestamp):
                return v.date()
        except Exception:
            pass
        return None


def today_local() -> date:
    return datetime.now().date()


def _resolve_refresh_date(value: Optional[str], default_date: date) -> date:
    if not value:
        return default_date
    v = str(value).strip().lower()
    if v == "today":
        return today_local()
    if v == "yesterday":
        return today_local() - timedelta(days=1)
    if v == "tomorrow":
        return today_local() + timedelta(days=1)
    parsed = parse_date(v)
    if parsed is None:
        raise ValueError(f"Invalid refresh date: {value}")
    return parsed


def _plan_seller_delivery_fee_backfill_updates(
    delivery_fee_rows: list[tuple[int, Optional[date], float, float]],
    row_to_order_id: Dict[int, str],
    *,
    date_from: date,
    date_to: date,
    seller_fee_by_order: Optional[Dict[str, float]] = None,
) -> list[tuple[int, float]]:
    seller_fee_by_order = seller_fee_by_order or {}
    updates: list[tuple[int, float]] = []
    for row_num, parsed_date, seller_num, fee_num in delivery_fee_rows:
        if not parsed_date:
            continue
        if parsed_date < date_from or parsed_date > date_to:
            continue
        if seller_num != 0.0:
            continue

        order_id = clean_order_id(row_to_order_id.get(row_num))
        db_fee = seller_fee_by_order.get(order_id) if order_id else None
        if db_fee is not None and db_fee != 0:
            updates.append((row_num, float(db_fee)))
            continue
        if fee_num != 0.0:
            updates.append((row_num, fee_num))
    return updates


def backfill_seller_delivery_fee(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    date_from: date,
    date_to: date,
    dry_run: bool = False,
    verbose: bool = False,
    snapshot: Optional[CRMSnapshot] = None,
    prefer_openpyxl: bool = False,
) -> int:
    """
    Backfill seller delivery fee from DB truth first, then Delivery_fee_kzt fallback.

    Sets 'Стоимость доставки для продавца' when it is blank/0 and a better
    value is available.
    Returns number of rows updated.
    """
    updates: list[tuple[int, float]] = []
    seller_col = None
    row_to_order_id: Dict[int, str] = {}
    delivery_fee_rows: list[tuple[int, Optional[date], float, float]] = []

    if snapshot and snapshot.delivery_fee_rows and snapshot.seller_fee_col:
        seller_col = snapshot.seller_fee_col
        row_to_order_id = {row_num: order_id for order_id, row_num in snapshot.order_rows.items()}
        seller_fee_by_order = _load_seller_delivery_fees_from_db(
            [row_to_order_id[row_num] for row_num, _parsed_date, seller_num, _fee_num in snapshot.delivery_fee_rows
             if row_num in row_to_order_id and seller_num == 0.0]
        )
        updates = _plan_seller_delivery_fee_backfill_updates(
            snapshot.delivery_fee_rows,
            row_to_order_id,
            date_from=date_from,
            date_to=date_to,
            seller_fee_by_order=seller_fee_by_order,
        )
    else:
        wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
        try:
            ws = wb[sheet_name]
            table = _resolve_table(ws, table_name)
            start_col, start_row, end_col, end_row = _table_bounds(table)

            header_row = list(ws.iter_rows(min_row=start_row, max_row=start_row,
                                           min_col=start_col, max_col=end_col))[0]
            col_map: Dict[str, int] = {}
            for i, cell in enumerate(header_row):
                header = str(cell.value or "").strip()
                if header:
                    col_map[header] = start_col + i

            date_col = col_map.get("Date") or col_map.get("Дата поступления заказа")
            fee_col = col_map.get("Delivery_fee_kzt") or col_map.get("Delivery_fee")
            seller_col = col_map.get("Стоимость доставки для продавца")
            order_col = col_map.get("№ заказа") or col_map.get("OrderID")

            if not date_col or not fee_col or not seller_col:
                if verbose:
                    print("  Delivery fee backfill skipped: required columns not found")
                return 0

            for row_num in range(start_row + 1, end_row + 1):
                row_date = ws.cell(row=row_num, column=date_col).value
                parsed_date = parse_date(row_date)
                if not parsed_date:
                    continue
                if parsed_date < date_from or parsed_date > date_to:
                    continue

                if order_col:
                    order_id = clean_order_id(ws.cell(row=row_num, column=order_col).value)
                    if order_id:
                        row_to_order_id[row_num] = order_id

                seller_val = ws.cell(row=row_num, column=seller_col).value
                fee_val = ws.cell(row=row_num, column=fee_col).value

                try:
                    seller_num = float(seller_val) if seller_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    seller_num = 0.0
                try:
                    fee_num = float(fee_val) if fee_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    fee_num = 0.0

                delivery_fee_rows.append((row_num, parsed_date, seller_num, fee_num))
        finally:
            wb.close()

        seller_fee_by_order = _load_seller_delivery_fees_from_db(row_to_order_id.values())
        updates = _plan_seller_delivery_fee_backfill_updates(
            delivery_fee_rows,
            row_to_order_id,
            date_from=date_from,
            date_to=date_to,
            seller_fee_by_order=seller_fee_by_order,
        )

    if verbose:
        print(f"  Delivery fee backfill candidates: {len(updates)} rows")

    if dry_run or not updates or seller_col is None:
        return len(updates)

    if prefer_openpyxl:
        preserved_package_parts = _snapshot_preserved_package_parts(crm_path)
        tmp_path = crm_path.with_name(f"{crm_path.stem}.seller_fee_tmp{crm_path.suffix}")
        wb = load_workbook(filename=str(crm_path), read_only=False, data_only=False)
        try:
            ws = wb[sheet_name]
            for row_num, value in updates:
                ws.cell(row=row_num, column=seller_col).value = value
            wb.save(str(tmp_path))
        finally:
            wb.close()

        try:
            _restore_preserved_package_parts(tmp_path, preserved_package_parts)
            os.replace(str(tmp_path), str(crm_path))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        return len(updates)

    _require_xlwings()
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    book = None
    try:
        book = _open_workbook_xlwings(app, crm_path, update_links=False, read_only=False)
        sheet = book.sheets[sheet_name]
        with _temporary_manual_calculation(app):
            _write_single_column_updates_xlwings(sheet, seller_col, updates)
        book.save()
    finally:
        _safe_close_xlwings_book(book, context="delivery-fee backfill")
        _safe_quit_xlwings_app(app, context="delivery-fee backfill")

    return len(updates)


# ---------- Legacy helpers (for tests/backward compatibility) ----------

def parse_date(v) -> Optional[date]:
    """Parse dates from CRM/Kaspi exports (supports Excel serials)."""
    if isinstance(v, (int, float)) and 40000 <= float(v) <= 60000:
        base = datetime(1899, 12, 30)
        return (base + timedelta(days=int(float(v)))).date()
    parsed = parse_kaspi_date(v)
    if parsed is not None:
        return parsed
    if isinstance(v, pd.Timestamp):
        return v.date()
    return None


def clean_value(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s else None


def _coerce_str(v: Any) -> str:
    cleaned = clean_value(v)
    return str(cleaned) if cleaned is not None else ""


def clean_order_id(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s.isdigit():
        return None
    if len(s) < 9 or len(s) > 12:
        return None
    return s


def _timestamp_to_ddmmyyyy(ts_ms: Optional[int]) -> Optional[str]:
    """Convert milliseconds timestamp to DD.MM.YYYY (Asia/Almaty)."""
    if not ts_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=ALMATY_TZ)
        return dt.strftime('%d.%m.%Y')
    except Exception:
        return None


def _extract_delivery_costs(order: dict) -> tuple[Optional[float], Optional[float]]:
    attrs = order.get('attributes', {}) if isinstance(order, dict) else {}
    delivery = attrs.get('kaspiDelivery', {}) if isinstance(attrs.get('kaspiDelivery', {}), dict) else {}
    buyer_cost = delivery.get('customerDeliveryCost')
    if buyer_cost is None:
        buyer_cost = attrs.get('deliveryCost')
    seller_cost = attrs.get('deliveryCostForSeller')
    if seller_cost is None:
        seller_cost = delivery.get('deliveryCostForSeller')
    return buyer_cost, seller_cost


def _order_to_update_fields(order: dict, *, store_code: Optional[str] = None) -> Dict[str, object]:
    attrs = order.get('attributes', {})
    delivery = attrs.get('kaspiDelivery', {})
    stage = classify_kaspi_order_stage(order)
    russian_status = kaspi_order_to_russian_status(order)
    indicators = stage_to_crm_indicators(stage)
    planned_date_obj = planned_date_from_order(order, store_code=store_code)
    planned_date = planned_date_obj.strftime('%d.%m.%Y') if planned_date_obj else None
    status_change_date = _timestamp_to_ddmmyyyy(attrs.get('statusChangeDate'))
    buyer_cost, seller_cost = _extract_delivery_costs(order)
    comp = delivery.get('deliveryCostCompensation', 0)

    data = {
        'Статус': russian_status,
        'Дата изменения статуса': status_change_date,
        'Принял': indicators['Принял'],
        'Выдал': indicators['Выдал'],
        'Отменил': indicators['Отменил'],
        'Плановая дата передачи курьеру': planned_date,
        'Стоимость доставки для покупателя': buyer_cost,
        'Стоимость доставки для продавца': seller_cost,
        'Компенсация за доставку': comp,
    }
    return {k: v for k, v in data.items() if v is not None}


def read_crm_pending_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
) -> List[Dict[str, Optional[str]]]:
    """Read CRM pending orders (planned date == target_date, status READY)."""
    header_df = pd.read_excel(crm_path, sheet_name=sheet_name, nrows=0)
    cols = header_df.columns.tolist()

    order_col = None
    for name in ("OrderID", "№ заказа"):
        if name in cols:
            order_col = name
            break
    status_col = "Статус" if "Статус" in cols else None
    planned_cols = []
    for name in ("PLANNED_SHIPPING_DATE", "Плановая дата передачи курьеру"):
        if name in cols:
            planned_cols.append(name)
    warehouse_col = None
    for name in ("Склад передачи КД", "Warehouse"):
        if name in cols:
            warehouse_col = name
            break

    if not order_col or not status_col or not planned_cols:
        return []

    usecols = [order_col, status_col] + planned_cols
    if warehouse_col:
        usecols.append(warehouse_col)

    df = pd.read_excel(crm_path, sheet_name=sheet_name, usecols=usecols)

    pending = []
    for _, row in df.iterrows():
        order_id = clean_order_id(row.get(order_col))
        if not order_id:
            continue
        planned = None
        for pcol in planned_cols:
            planned = parse_date(row.get(pcol))
            if planned:
                break
        if planned != target_date:
            continue
        status = str(row.get(status_col) or "").strip()
        if status != READY_STATUS:
            continue
        warehouse = str(row.get(warehouse_col) or "").strip() if warehouse_col else ""
        store_code = WAREHOUSE_STORE_MAP.get(warehouse)
        pending.append({"order_id": order_id, "store_code": store_code})

    return pending


def fetch_missing_status_updates(
    missing_orders: List[Dict[str, Optional[str]]],
    verbose: bool = False,
) -> Dict[str, Dict[str, object]]:
    """Fetch current statuses for missing orders via API (by order code)."""
    if not missing_orders:
        return {}

    load_dotenv()
    clients: Dict[str, KaspiAPIClient] = {}
    updates: Dict[str, Dict[str, object]] = {}

    for item in missing_orders:
        order_id = item.get("order_id")
        if not order_id:
            continue
        preferred_store = item.get("store_code")
        stores = [preferred_store] if preferred_store else list(STORE_TOKEN_MAP.keys())

        for store_code in stores:
            if not store_code:
                continue
            try:
                client = clients.get(store_code)
                if client is None:
                    client = KaspiAPIClient(store_code=store_code)
                    clients[store_code] = client
            except KaspiAuthError as e:
                if verbose:
                    print(f"  Skipping {store_code}: {e}")
                continue

            resp = client.get_order(order_id)
            if not resp.success or not resp.data:
                continue

            data = resp.data
            if isinstance(data, dict) and data.get('type') != 'orders':
                if 'data' in data and isinstance(data['data'], list) and data['data']:
                    data = data['data'][0]
            if isinstance(data, dict) and data.get('type') == 'orders':
                updates[order_id] = _order_to_update_fields(data, store_code=store_code)
                break

        if order_id not in updates and verbose:
            print(f"  WARN: order {order_id} not found via API")

    return updates


def summarize_order_rows(df: pd.DataFrame) -> Dict[str, int]:
    """
    Summarize orders vs rows for a filtered dataframe.

    Returns dict with keys: rows, unique_orders, multi_line_orders, max_lines_per_order
    """
    colmap = map_headers(df)
    order_col = colmap.get("order_id")
    if not order_col:
        return {}

    order_ids = df[order_col].apply(clean_order_id).dropna()
    if order_ids.empty:
        return {
            "rows": int(len(df)),
            "unique_orders": 0,
            "multi_line_orders": 0,
            "max_lines_per_order": 0,
        }

    counts = order_ids.value_counts()
    multi_line = int((counts > 1).sum())
    max_lines = int(counts.max()) if not counts.empty else 0
    return {
        "rows": int(len(df)),
        "unique_orders": int(counts.size),
        "multi_line_orders": multi_line,
        "max_lines_per_order": max_lines,
    }


def find_active_orders_files(orders_dir: Path) -> List[Path]:
    return find_active_orders(orders_dir)


def parse_orders_from_excel(orders_dir: Path) -> List[dict]:
    df, _ = read_active_orders(orders_dir)
    return df.to_dict(orient="records")


def load_existing_order_ids(crm_path: Path, sheet_name: str) -> set:
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        order_col = None
        for idx, val in enumerate(header, start=1):
            if norm(val) in {"№заказа", "номерзаказа", "заказа"}:
                order_col = idx
                break
        if order_col is None:
            return set()
        order_ids = set()
        for row in ws.iter_rows(min_row=2, min_col=order_col, max_col=order_col):
            val = row[0].value
            cleaned = clean_order_id(val)
            if cleaned:
                order_ids.add(cleaned)
        return order_ids
    finally:
        wb.close()


def deduplicate_orders(orders: List[dict], existing_ids: set) -> Tuple[List[dict], int]:
    new_orders = []
    skipped = 0
    for order in orders:
        order_id = order.get("_order_id") or order.get("order_id")
        if order_id in existing_ids:
            skipped += 1
            continue
        new_orders.append(order)
    return new_orders, skipped


def filter_orders_for_shipment(orders: List[dict], target_date: date) -> List[dict]:
    filtered = []
    for order in orders:
        status = str(order.get("Статус", "")).strip()
        signature = str(order.get("Требуется подписание", "")).strip()
        planned = parse_date(order.get("Плановая дата передачи курьеру"))
        if status != READY_STATUS:
            continue
        if signature and signature != NO_SIGNATURE:
            continue
        if planned and planned != target_date:
            continue
        filtered.append(order)
    return filtered


# ---------- Read & Filter ActiveOrders ----------

def find_active_orders(orders_dir: Path) -> List[Path]:
    """Find all ActiveOrders*.xlsx files in directory."""
    files = sorted([
        p for p in orders_dir.glob("*.xlsx")
        if p.is_file()
        and "ActiveOrders" in p.name
        and not p.name.startswith("~$")
    ])
    return files


def read_active_orders(orders_dir: Path) -> Tuple[pd.DataFrame, List[Path]]:
    """Read all ActiveOrders files and concat."""
    files = find_active_orders(orders_dir)
    if not files:
        raise SystemExit(f"No .xlsx files found in {orders_dir}")
    
    frames = []
    for p in files:
        try:
            df = pd.read_excel(p, engine="openpyxl")
            df["__source_file__"] = p.name
            frames.append(df)
            print(f"  Read {p.name}: {len(df)} rows")
        except Exception as e:
            print(f"  WARN: cannot read {p.name}: {e}")
    
    if not frames:
        raise SystemExit("No valid Excel files found")
    
    return pd.concat(frames, ignore_index=True), files


def filter_for_shipping(
    df: pd.DataFrame, 
    status_wanted: str, 
    signature_wanted: Optional[str], 
    end_date: date,
    *,
    include_overdue: bool = False,
    overdue_lookback_days: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Filter orders for shipping readiness."""
    colmap = map_headers(df)
    
    ok = pd.Series([True] * len(df))
    
    # Status filter
    if "status" in colmap:
        ok &= (df[colmap["status"]].astype(str).str.strip() == status_wanted)
    
    # Signature filter (exclude "Да" / "Требуется")
    if signature_wanted and "signature" in colmap:
        sig_col = df[colmap["signature"]].astype(str).str.strip().str.lower()
        ok &= ~sig_col.isin(['да', 'yes', 'true', '1', 'требуется'])
    
    # Date filter:
    # - default: planned_date == end_date (today-only append)
    # - include_overdue: planned_date <= end_date within optional lookback window
    if "handover" in colmap:
        handover = df[colmap["handover"]].apply(parse_kz_date)
        if include_overdue:
            min_date: Optional[date] = None
            if overdue_lookback_days is not None:
                min_date = end_date - timedelta(days=max(int(overdue_lookback_days), 0))
            ok &= handover.apply(
                lambda d: d is not None and d <= end_date and (min_date is None or d >= min_date)
            )
        else:
            ok &= handover.apply(lambda d: d is not None and d == end_date)
    
    df_filtered = df[ok].copy()
    
    stats = {
        "files_seen": len(df["__source_file__"].unique()) if "__source_file__" in df else 0,
        "rows_in_files": int(len(df)),
        "rows_after_filters": int(len(df_filtered)),
        "target_end_date": end_date.isoformat(),
        "include_overdue": bool(include_overdue),
        "overdue_lookback_days": (
            int(overdue_lookback_days) if overdue_lookback_days is not None else None
        ),
    }
    
    return df_filtered, stats


def sort_for_crm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort dataframe for CRM append order.

    Sort order (Phase 12 Part 6 - Updated):
    1. Status (cancelled/returned on top) - problematic orders first
    2. STORE_NAME / warehouse (ascending) - group by store for visual clarity
    3. OrderID (ascending) - group same orders together
    4. Quantity (ascending) - single items first
    5. KASPI_OFFER_NAME / offer_name (ascending) - alphabetical by product
    6. Date / handover (ascending) - oldest first

    This sort order groups orders by store for easier visual scanning.
    """
    colmap = map_headers(df)

    sort_cols = []
    sort_ascending = []

    # 1. Status column - cancelled/returned first (0 = top, 1 = bottom)
    if "status" in colmap:
        df = df.copy()  # Avoid SettingWithCopyWarning
        df["_status_sort"] = df[colmap["status"]].apply(
            lambda x: 0 if str(x).lower() in ['отменен', 'возвращен', 'cancelled', 'returned', 'cancelling', 'returning'] else 1
        )
        sort_cols.append("_status_sort")
        sort_ascending.append(True)

    # 2. STORE_NAME / warehouse (ascending) - group by store first
    if "warehouse" in colmap:
        sort_cols.append(colmap["warehouse"])
        sort_ascending.append(True)

    # 3. OrderID (ascending)
    if "order_id" in colmap:
        sort_cols.append(colmap["order_id"])
        sort_ascending.append(True)

    # 4. Quantity (ascending)
    if "quantity" in colmap:
        sort_cols.append(colmap["quantity"])
        sort_ascending.append(True)

    # 5. KASPI_OFFER_NAME / offer_name (ascending)
    if "offer_name" in colmap:
        sort_cols.append(colmap["offer_name"])
        sort_ascending.append(True)

    # 6. Date / handover (ascending)
    if "handover" in colmap:
        sort_cols.append(colmap["handover"])
        sort_ascending.append(True)

    if sort_cols:
        df_sorted = df.sort_values(by=sort_cols, ascending=sort_ascending, na_position='last')
        # Drop helper column
        if "_status_sort" in df_sorted.columns:
            df_sorted = df_sorted.drop(columns=["_status_sort"])
        return df_sorted.reset_index(drop=True)

    return df


def build_pending_append_mask(
    df: pd.DataFrame,
    *,
    colmap: Dict[str, str],
    existing_keys: set[str],
    existing_append_date_keys: Optional[Any],
    include_overdue: bool,
    append_date: Optional[date],
) -> tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    """
    Compute dedupe mask for CRM append rows.

    CRM append should dedupe against the current append-date operational view,
    not against historical rows. This keeps overdue still-pending orders visible
    again today while preventing duplicate today rows across repeated imports.
    """

    work = df.copy()
    order_col = colmap.get("order_id")
    handover_col = colmap.get("handover")
    offer_col = colmap.get("offer_name")
    sku_col = colmap.get("sku")
    qty_col = colmap.get("quantity")

    if not order_col:
        mask = pd.Series([True] * len(work), index=work.index)
        return work, mask, {
            "dedupe_mode": "none",
            "duplicates_skipped": 0,
            "carryforward_rows": 0,
            "carryforward_rows_to_append": 0,
        }

    work["_oid"] = work[order_col].apply(clean_order_id)
    if handover_col and handover_col in work.columns:
        work["_pdate"] = work[handover_col].apply(parse_date)
    else:
        work["_pdate"] = None

    work["_is_overdue"] = work["_pdate"].apply(
        lambda d: append_date is not None and isinstance(d, date) and d < append_date
    )
    previous_day = append_date - timedelta(days=1) if append_date is not None else None
    work["_is_prev_day_overdue"] = work["_pdate"].apply(
        lambda d: previous_day is not None and isinstance(d, date) and d == previous_day
    )
    work["_is_older_overdue"] = work["_is_overdue"] & ~work["_is_prev_day_overdue"]
    work["_okey"] = [
        _build_line_dedupe_key(
            oid,
            pdate,
            row.get(offer_col) if offer_col else "",
            row.get(sku_col) if sku_col else "",
            row.get(qty_col) if qty_col else 0,
        )
        for (_, row), oid, pdate in zip(work.iterrows(), work["_oid"], work["_pdate"])
    ]

    planned_new_mask = ~work["_okey"].isin(existing_keys)
    planned_duplicate_rows = int(((~planned_new_mask) & ~work["_is_overdue"]).sum())

    use_append_date_view = bool(append_date and existing_append_date_keys is not None)
    append_date_duplicate_rows = 0
    if use_append_date_view:
        if isinstance(existing_append_date_keys, Counter):
            append_date_counts = Counter(existing_append_date_keys)
        elif isinstance(existing_append_date_keys, dict):
            append_date_counts = Counter({str(k): int(v) for k, v in existing_append_date_keys.items()})
        else:
            append_date_counts = Counter({str(k): 1 for k in (existing_append_date_keys or set())})
        append_flags: list[bool] = []
        for key in work["_okey"].tolist():
            if append_date_counts.get(key, 0) > 0:
                append_flags.append(False)
                append_date_counts[key] -= 1
                append_date_duplicate_rows += 1
            else:
                append_flags.append(True)
        new_mask = pd.Series(append_flags, index=work.index)
        dedupe_mode = "append_date_view"
    else:
        new_mask = planned_new_mask
        dedupe_mode = "planned_date"

    carryforward_rows = int(work["_is_overdue"].sum())
    carryforward_rows_to_append = int((work["_is_overdue"] & new_mask).sum())
    stats = {
        "dedupe_mode": dedupe_mode,
        "duplicates_skipped": int((~new_mask).sum()),
        "planned_duplicate_rows": planned_duplicate_rows,
        "append_date_duplicate_rows": append_date_duplicate_rows,
        "previous_day_overdue_rows": int(work["_is_prev_day_overdue"].sum()),
        "older_overdue_rows_suppressed": 0,
        "carryforward_rows": carryforward_rows,
        "carryforward_rows_to_append": carryforward_rows_to_append,
    }
    return work, new_mask, stats


# ---------- CRM Inspection (openpyxl read-only) ----------

def inspect_crm_sheet(
    crm_path: Path,
    sheet_name: str,
    table_name: str
) -> Tuple[int, Optional[int], int, int, List[str]]:
    """
    Inspect CRM to find column positions.

    CRM structure:
    - Column B (2): Date - we write here
    - Column I (9): Phone - we write here (Phase 12)
    - Columns A-X: Formula columns (auto-calculate)
    - Columns Y-AZ (25-52): Raw Kaspi data - we write here

    Returns: (date_col, phone_col, start_col, end_col, slice_headers)
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise SystemExit(f'Sheet "{sheet_name}" not found in {crm_path}')

    ws = wb[sheet_name]
    header_vals = [c.value if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

    idx_date = None
    idx_phone = None  # Phone column (column I)
    idx_start = None  # Raw Kaspi start (№ заказа in column Y)
    idx_end = None    # Raw Kaspi end (Склад передачи КД in column AZ)

    for i, h in enumerate(header_vals, start=1):
        hnorm = norm(h)
        if idx_date is None and hnorm in {"date", "дата"}:
            idx_date = i
        # Phone column (column I in CRM)
        if idx_phone is None and hnorm in {"phone", "телефон", "cellphone"}:
            idx_phone = i
        # Look for raw Kaspi columns (Russian headers starting at Y)
        # Note: "№ заказа" normalizes to "заказа" (№ symbol stripped)
        if idx_start is None and hnorm in {"№заказа", "номерзаказа", "заказа"}:
            idx_start = i
        if hnorm in {"складпередачикд", "складпередачикурьерскойдоставки"}:
            idx_end = i  # Keep updating to get the last one

    if idx_date is None:
        raise SystemExit(f"Could not find 'Date' column. Headers: {header_vals[:10]}...")

    if idx_start is None or idx_end is None or idx_end < idx_start:
        raise SystemExit(
            f"Could not locate raw Kaspi columns (Y-AZ). Need '№ заказа' and 'Склад передачи КД'. "
            f"Headers at positions 25-30: {header_vals[24:30] if len(header_vals) >= 30 else 'N/A'}"
        )

    slice_headers = [header_vals[j-1] for j in range(idx_start, idx_end + 1)]
    wb.close()

    print(f"  Date column: {idx_date} (B)")
    if idx_phone:
        print(f"  Phone column: {idx_phone} (I)")
    else:
        print(f"  Phone column: not found (will skip phone import)")
    print(f"  Raw Kaspi columns: {idx_start}-{idx_end} (Y-AZ)")

    return idx_date, idx_phone, idx_start, idx_end, slice_headers


def _resolve_table(ws, table_name: str):
    """Find table in worksheet."""
    tables = ws.tables
    if table_name in tables:
        return tables[table_name]
    if tables:
        return next(iter(tables.values()))
    raise RuntimeError(f"No tables found on sheet {ws.title}")


def _table_bounds(table) -> Tuple[int, int, int, int]:
    """Get table bounds: (start_col, start_row, end_col, end_row)."""
    start_ref, end_ref = table.ref.split(':')
    start_col_letters, start_row = coordinate_from_string(start_ref)
    end_col_letters, end_row = coordinate_from_string(end_ref)
    start_col = column_index_from_string(start_col_letters)
    end_col = column_index_from_string(end_col_letters)
    return start_col, start_row, end_col, end_row


def _table_header_signature(ws: Any, table: Any) -> List[str]:
    start_col, header_row, end_col, _end_row = _table_bounds(table)
    return [
        norm(str(ws.cell(row=header_row, column=col).value or ""))
        for col in range(start_col, end_col + 1)
    ]


def _find_header_col(header_to_col: Dict[str, int], normalized_aliases: set[str]) -> Optional[int]:
    for name, col in header_to_col.items():
        if norm(name) in normalized_aliases:
            return col
    return None


def _has_formula_payload(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("=")
    if value is None:
        return False
    text = getattr(value, "text", None)
    return isinstance(text, str) and bool(text.strip())


def _formula_payload_text(value: Any) -> str:
    if isinstance(value, str):
        return value if value.startswith("=") else ""
    if value is None:
        return ""
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return ""


def _contains_self_external_formula_payload(value: Any) -> bool:
    text = _formula_payload_text(value)
    return bool(text and re.search(r"\[\d+\]!", text))


def _translate_formula_payload(
    value: Any,
    *,
    source_col: int,
    source_row: int,
    target_col: int,
    target_row: int,
    force_plain_formula: bool = False,
) -> Any:
    origin = f"{get_column_letter(source_col)}{source_row}"
    target = f"{get_column_letter(target_col)}{target_row}"

    if isinstance(value, str) and value.startswith("="):
        try:
            return Translator(value, origin=origin).translate_formula(target)
        except Exception:
            return value

    if isinstance(value, ArrayFormula):
        translated_text = value.text
        if isinstance(translated_text, str) and translated_text.startswith("="):
            try:
                translated_text = Translator(translated_text, origin=origin).translate_formula(target)
            except Exception:
                translated_text = value.text

        translated_ref = value.ref
        if isinstance(translated_ref, str) and translated_ref.strip():
            try:
                translated_ref = Translator.translate_range(
                    translated_ref,
                    target_row - source_row,
                    target_col - source_col,
                )
            except Exception:
                translated_ref = value.ref

        if force_plain_formula:
            if isinstance(translated_text, str) and translated_text.strip():
                return translated_text
            if isinstance(value.text, str) and value.text.strip():
                return value.text
            return translated_text

        return ArrayFormula(ref=translated_ref, text=translated_text)

    return value


def _formula_payload_equals(left: Any, right: Any) -> bool:
    if isinstance(left, ArrayFormula) and isinstance(right, ArrayFormula):
        return left.ref == right.ref and left.text == right.text
    return left == right


def _cell_style_signature(cell: Any) -> Tuple[str, str, str, str, str, str]:
    return (
        repr(copy(cell.font)),
        repr(copy(cell.fill)),
        repr(copy(cell.border)),
        repr(copy(cell.alignment)),
        str(cell.number_format or ""),
        repr(copy(cell.protection)),
    )


def _cell_styles_equivalent(left: Any, right: Any) -> bool:
    return _cell_style_signature(left) == _cell_style_signature(right)


def _formula_template_columns(header_to_col: Dict[str, int]) -> List[int]:
    formula_alias_groups = (
        {"storename", "store_name"},
        {"quantity", "количество"},
        {"kaspinamecore", "kaspi_name_core"},
        {"orderid"},
        {"probablesize", "probable_size"},
        {"kaspioffername", "kaspi_offer_name"},
        {"skukey", "sku_key"},
        {"skuid", "sku_id"},
        {"sellpricekzt", "sell_price_kzt"},
        {"totalprice", "total_price"},
        {"totalnetrev", "total_net_rev"},
        {"model"},
        {"plannedshippingdate", "planned_shipping_date", "плановаядатапередачикурьеру"},
        {"producttype", "product_type"},
        {"deliveryfeekzt", "delivery_fee_kzt"},
        {"totalweight", "total_weight"},
        {"skuidksp", "sku_id_ksp", "артикул"},
        {"kaspinamesource", "kaspi_name_source", "названиевсистемепродавца"},
    )
    cols = []
    for aliases in formula_alias_groups:
        col = _find_header_col(header_to_col, aliases)
        if col:
            cols.append(col)
    return sorted(set(cols))


def _formula_contract_plain_formula_columns(header_to_col: Dict[str, int]) -> set[int]:
    return set()


def _required_formula_cache_columns(header_to_col: Dict[str, int]) -> List[Tuple[str, int]]:
    required_alias_groups = (
        ("STORE_NAME", {"storename", "store_name"}),
        ("Quantity", {"quantity", "количество"}),
        (
            "PLANNED_SHIPPING_DATE",
            {"plannedshippingdate", "planned_shipping_date", "плановаядатапередачикурьеру"},
        ),
    )
    cols: List[Tuple[str, int]] = []
    for label, aliases in required_alias_groups:
        col = _find_header_col(header_to_col, aliases)
        if col:
            cols.append((label, col))
    return cols


def _find_template_row_for_append(
    ws: Any,
    header_row: int,
    table_end_row: int,
    formula_cols: List[int],
) -> Optional[int]:
    if table_end_row <= header_row:
        return None
    required_hits = max(1, min(4, len(formula_cols))) if formula_cols else 0
    for row_num in range(table_end_row, header_row, -1):
        if not formula_cols:
            return row_num
        hits = 0
        for col_num in formula_cols:
            if _has_formula_payload(ws.cell(row=row_num, column=col_num).value):
                hits += 1
        if hits >= required_hits:
            return row_num
    return None


def _build_cf_replacement_by_col(
    header_to_col: Dict[str, int],
    data_start_row: int,
    data_end_row: int,
) -> Dict[int, str]:
    replacements: Dict[int, str] = {}
    if data_end_row < data_start_row:
        return replacements

    single_alias_groups = (
        {"date", "дата"},
        {"storename", "store_name"},
        {"quantity", "количество"},
        {"kaspinamecore", "kaspi_name_core"},
        {"orderid", "order_id"},
        {"заказа", "номерзаказа", "№заказа"},
    )
    for aliases in single_alias_groups:
        col = _find_header_col(header_to_col, aliases)
        if not col:
            continue
        replacements[col] = f"{get_column_letter(col)}{data_start_row}:{get_column_letter(col)}{data_end_row}"

    sell_col = _find_header_col(header_to_col, {"sellpricekzt", "sell_price_kzt"})
    total_col = _find_header_col(header_to_col, {"totalprice", "total_price"})
    net_col = _find_header_col(header_to_col, {"totalnetrev", "total_net_rev"})
    if sell_col and total_col and net_col and sell_col < total_col < net_col:
        group_range = f"{get_column_letter(sell_col)}{data_start_row}:{get_column_letter(net_col)}{data_end_row}"
        for col in range(sell_col, net_col + 1):
            replacements[col] = group_range

    return replacements


def _clone_cf_rules_with_translated_formulas(
    rules: List[Any],
    *,
    source_anchor: CellRange | None = None,
    target_anchor: CellRange | None = None,
) -> List[Any]:
    cloned_rules = [deepcopy(rule) for rule in rules]
    if (
        source_anchor is None
        or target_anchor is None
        or (
            source_anchor.min_col == target_anchor.min_col
            and source_anchor.min_row == target_anchor.min_row
        )
    ):
        return cloned_rules

    origin = f"{get_column_letter(source_anchor.min_col)}{source_anchor.min_row}"
    target = f"{get_column_letter(target_anchor.min_col)}{target_anchor.min_row}"
    for rule in cloned_rules:
        formulas = getattr(rule, "formula", None)
        if not formulas:
            continue
        translated_formulas = []
        for formula in formulas:
            if not isinstance(formula, str) or not formula:
                translated_formulas.append(formula)
                continue
            try:
                translator_formula = formula if formula.startswith("=") else f"={formula}"
                translated = Translator(translator_formula, origin=origin).translate_formula(target)
                if not formula.startswith("=") and translated.startswith("="):
                    translated = translated[1:]
                translated_formulas.append(
                    translated
                )
            except Exception:
                translated_formulas.append(formula)
        rule.formula = translated_formulas
    return cloned_rules


def _normalize_conditional_formatting_ranges(
    ws: Any,
    header_row: int,
    data_end_row: int,
    header_to_col: Dict[str, int],
    verbose: bool = False,
) -> int:
    cf = ws.conditional_formatting
    if not cf._cf_rules:
        return 0

    data_start_row = header_row + 1
    replacements = _build_cf_replacement_by_col(header_to_col, data_start_row, data_end_row)
    if not replacements:
        return 0

    items = list(cf._cf_rules.items())
    new_rules: OrderedDict = OrderedDict()
    updated = 0

    for cf_obj, rules in items:
        old_sqref = str(cf_obj.sqref)
        parts = [part for part in old_sqref.split() if part]
        token_ranges: List[CellRange] = []
        for part in parts:
            try:
                token_ranges.append(CellRange(part))
            except Exception:
                token_ranges = []
                break
        if not token_ranges:
            new_cf = ConditionalFormatting(
                sqref=old_sqref,
                pivot=getattr(cf_obj, "pivot", None),
                extLst=getattr(cf_obj, "extLst", None),
            )
            new_rules[new_cf] = _clone_cf_rules_with_translated_formulas(rules)
            continue

        touched_cols: List[int] = []
        touched_ranges: List[CellRange] = []
        untouched_tokens: List[str] = []
        for cell_range in token_ranges:
            touched = False
            for col_num in range(cell_range.min_col, cell_range.max_col + 1):
                if col_num in replacements:
                    touched_cols.append(col_num)
                    touched = True
            if not touched:
                untouched_tokens.append(cell_range.coord)
            else:
                touched_ranges.append(cell_range)

        if touched_cols:
            normalized_tokens: List[str] = []
            seen = set()
            for col_num in sorted(set(touched_cols)):
                replacement = replacements[col_num]
                if replacement in seen:
                    continue
                normalized_tokens.append(replacement)
                seen.add(replacement)
            source_anchor = min(
                touched_ranges,
                key=lambda rng: (rng.min_row, rng.min_col, rng.max_row, rng.max_col),
            )
            normalized_ranges = [CellRange(token) for token in normalized_tokens]
            target_anchor = min(
                normalized_ranges,
                key=lambda rng: (rng.min_row, rng.min_col, rng.max_row, rng.max_col),
            )
            normalized_sqref = " ".join(normalized_tokens)
            if normalized_sqref != old_sqref or untouched_tokens:
                updated += 1
            normalized_cf = ConditionalFormatting(
                sqref=normalized_sqref,
                pivot=getattr(cf_obj, "pivot", None),
                extLst=getattr(cf_obj, "extLst", None),
            )
            new_rules[normalized_cf] = _clone_cf_rules_with_translated_formulas(
                rules,
                source_anchor=source_anchor,
                target_anchor=target_anchor,
            )
            if untouched_tokens:
                untouched_cf = ConditionalFormatting(
                    sqref=" ".join(untouched_tokens),
                    pivot=getattr(cf_obj, "pivot", None),
                    extLst=getattr(cf_obj, "extLst", None),
                )
                new_rules[untouched_cf] = _clone_cf_rules_with_translated_formulas(rules)
            continue

        new_cf = ConditionalFormatting(
            sqref=old_sqref,
            pivot=getattr(cf_obj, "pivot", None),
            extLst=getattr(cf_obj, "extLst", None),
        )
        new_rules[new_cf] = _clone_cf_rules_with_translated_formulas(rules)

    cf._cf_rules = new_rules
    if verbose and updated:
        print(f"  Conditional formatting ranges normalized: {updated} blocks")
    return updated


def _restore_conditional_formatting_from_template(
    ws: Any,
    template_ws: Any,
    *,
    header_row: int,
    data_end_row: int,
    template_data_end_row: int,
    verbose: bool = False,
) -> int:
    template_cf = template_ws.conditional_formatting
    if not template_cf._cf_rules:
        ws.conditional_formatting._cf_rules = OrderedDict()
        return 0

    data_start_row = header_row + 1
    new_rules: OrderedDict = OrderedDict()
    updated = 0

    for cf_obj, rules in template_cf._cf_rules.items():
        old_sqref = str(cf_obj.sqref)
        new_tokens: List[str] = []
        for part in [token for token in old_sqref.split() if token]:
            try:
                cell_range = CellRange(part)
            except Exception:
                new_tokens.append(part)
                continue

            if (
                data_end_row >= data_start_row
                and cell_range.max_row >= data_start_row
                and cell_range.max_row == template_data_end_row
                and data_end_row > template_data_end_row
            ):
                cell_range = CellRange(
                    min_col=cell_range.min_col,
                    min_row=cell_range.min_row,
                    max_col=cell_range.max_col,
                    max_row=data_end_row,
                )
            new_tokens.append(cell_range.coord)

        new_sqref = " ".join(new_tokens) if new_tokens else old_sqref
        if new_sqref != old_sqref:
            updated += 1

        new_cf = ConditionalFormatting(
            sqref=new_sqref,
            pivot=getattr(cf_obj, "pivot", None),
            extLst=getattr(cf_obj, "extLst", None),
        )
        new_rules[new_cf] = [deepcopy(rule) for rule in rules]

    ws.conditional_formatting._cf_rules = new_rules
    if verbose and updated:
        print(f"  Conditional formatting restored from template: {updated} blocks extended")
    return updated


def _restore_formula_and_style_window_from_template(
    *,
    ws: Any,
    template_ws: Any,
    header_row: int,
    target_start_row: int,
    target_end_row: int,
    start_col: int,
    end_col: int,
    formula_cols: List[int],
    template_data_end_row: int,
) -> Tuple[int, int]:
    style_cells_normalized = 0
    formula_cells_restored = 0

    source_tail_row = _find_template_row_for_append(
        ws=template_ws,
        header_row=header_row,
        table_end_row=template_data_end_row,
        formula_cols=formula_cols,
    )
    if source_tail_row is None:
        source_tail_row = template_data_end_row

    header_values = [
        ws.cell(row=header_row, column=col).value
        for col in range(start_col, end_col + 1)
    ]
    header_to_col = {
        str(name).strip(): start_col + i
        for i, name in enumerate(header_values)
        if str(name or "").strip()
    }
    formula_col_set = set(formula_cols)
    plain_formula_cols = _formula_contract_plain_formula_columns(header_to_col)
    cross_workbook = ws is not template_ws
    for row_num in range(target_start_row, target_end_row + 1):
        source_row = row_num if row_num <= template_data_end_row else source_tail_row
        for col_num in range(start_col, end_col + 1):
            src = template_ws.cell(row=source_row, column=col_num)
            dst = ws.cell(row=row_num, column=col_num)

            if src.has_style and (cross_workbook or dst._style != src._style):
                if cross_workbook:
                    dst.font = copy(src.font)
                    dst.fill = copy(src.fill)
                    dst.border = copy(src.border)
                    dst.alignment = copy(src.alignment)
                    dst.number_format = src.number_format
                    dst.protection = copy(src.protection)
                else:
                    dst._style = copy(src._style)
                style_cells_normalized += 1

            if col_num not in formula_col_set or not _has_formula_payload(src.value):
                continue

            translated_value = _translate_formula_payload(
                src.value,
                source_col=col_num,
                source_row=source_row,
                target_col=col_num,
                target_row=row_num,
                force_plain_formula=col_num in plain_formula_cols,
            )

            if not _formula_payload_equals(dst.value, translated_value):
                dst.value = translated_value
                formula_cells_restored += 1

    return style_cells_normalized, formula_cells_restored


def _sanitize_self_externalized_formula_window(
    *,
    ws: Any,
    template_ws: Any,
    header_row: int,
    target_start_row: int,
    target_end_row: int,
    start_col: int,
    end_col: int,
    formula_cols: List[int],
    template_data_end_row: int,
) -> int:
    if target_start_row > target_end_row:
        return 0

    header_values = [
        ws.cell(row=header_row, column=col).value
        for col in range(start_col, end_col + 1)
    ]
    header_to_col = {
        str(name).strip(): start_col + i
        for i, name in enumerate(header_values)
        if str(name or "").strip()
    }
    plain_formula_cols = _formula_contract_plain_formula_columns(header_to_col)
    source_tail_row = _find_template_row_for_append(
        ws=template_ws,
        header_row=header_row,
        table_end_row=template_data_end_row,
        formula_cols=formula_cols,
    )
    if source_tail_row is None:
        source_tail_row = template_data_end_row

    repaired = 0
    for row_num in range(target_start_row, target_end_row + 1):
        source_row = row_num if row_num <= template_data_end_row else source_tail_row
        for col_num in range(start_col, end_col + 1):
            dst = ws.cell(row=row_num, column=col_num)
            if not _contains_self_external_formula_payload(dst.value):
                continue
            src = template_ws.cell(row=source_row, column=col_num)
            replacement = src.value
            if _has_formula_payload(src.value):
                replacement = _translate_formula_payload(
                    src.value,
                    source_col=col_num,
                    source_row=source_row,
                    target_col=col_num,
                    target_row=row_num,
                    force_plain_formula=col_num in plain_formula_cols,
                )
            if not _formula_payload_equals(dst.value, replacement):
                dst.value = replacement
                repaired += 1
    return repaired


def _copy_sheet_values_from_source(target_ws: Any, source_ws: Any) -> int:
    max_row = max(int(getattr(target_ws, "max_row", 0) or 0), int(getattr(source_ws, "max_row", 0) or 0))
    max_col = max(int(getattr(target_ws, "max_column", 0) or 0), int(getattr(source_ws, "max_column", 0) or 0))
    copied = 0
    for row_num in range(1, max_row + 1):
        for col_num in range(1, max_col + 1):
            src_value = source_ws.cell(row=row_num, column=col_num).value
            dst = target_ws.cell(row=row_num, column=col_num)
            if dst.value != src_value:
                dst.value = src_value
                copied += 1
    return copied


def _restore_sales_sheet_from_template(
    *,
    target_ws: Any,
    source_ws: Any,
    template_ws: Any,
    table_name: str = CRM_SALES_TABLE_NAME,
    verbose: bool = False,
) -> Dict[str, int]:
    target_table = _resolve_table(target_ws, table_name)
    source_table = _resolve_table(source_ws, table_name)
    template_table = _resolve_table(template_ws, table_name)

    target_start_col, target_header_row, target_end_col, _target_end_row = _table_bounds(target_table)
    source_start_col, _source_header_row, source_end_col, source_end_row = _table_bounds(source_table)
    template_start_col, _template_header_row, template_end_col, template_end_row = _table_bounds(template_table)

    if (target_start_col, target_end_col) != (source_start_col, source_end_col):
        raise RuntimeError("CRM sales table column bounds differ between current workbook and template.")
    if (target_start_col, target_end_col) != (template_start_col, template_end_col):
        raise RuntimeError("CRM sales table column bounds differ between target workbook and canonical template.")

    header_values = [
        target_ws.cell(row=target_header_row, column=col).value
        for col in range(target_start_col, target_end_col + 1)
    ]
    header_to_col = {
        str(name).strip(): target_start_col + i
        for i, name in enumerate(header_values)
        if str(name or "").strip()
    }
    formula_cols = _formula_template_columns(header_to_col)
    formula_col_set = set(formula_cols)

    source_data_start = target_header_row + 1
    if source_end_row >= source_data_start:
        styles_restored, formulas_restored = _restore_formula_and_style_window_from_template(
            ws=target_ws,
            template_ws=template_ws,
            header_row=target_header_row,
            target_start_row=source_data_start,
            target_end_row=source_end_row,
            start_col=target_start_col,
            end_col=target_end_col,
            formula_cols=formula_cols,
            template_data_end_row=template_end_row,
        )
    else:
        styles_restored, formulas_restored = (0, 0)

    preserved_cells = 0
    for row_num in range(source_data_start, source_end_row + 1):
        for col_num in range(target_start_col, target_end_col + 1):
            if col_num in formula_col_set:
                continue
            src_value = source_ws.cell(row=row_num, column=col_num).value
            dst = target_ws.cell(row=row_num, column=col_num)
            if dst.value != src_value:
                dst.value = src_value
                preserved_cells += 1

    externalized_formulas_cleared = 0
    if source_end_row >= source_data_start:
        externalized_formulas_cleared = _sanitize_self_externalized_formula_window(
            ws=target_ws,
            template_ws=template_ws,
            header_row=target_header_row,
            target_start_row=source_data_start,
            target_end_row=source_end_row,
            start_col=target_start_col,
            end_col=target_end_col,
            formula_cols=formula_cols,
            template_data_end_row=template_end_row,
        )

    for row_num in range(source_end_row + 1, template_end_row + 1):
        for col_num in range(target_start_col, target_end_col + 1):
            target_ws.cell(row=row_num, column=col_num).value = None

    target_table.ref = (
        f"{get_column_letter(target_start_col)}{target_header_row}:"
        f"{get_column_letter(target_end_col)}{max(source_end_row, target_header_row + 1)}"
    )
    cf_blocks_restored = _restore_conditional_formatting_from_template(
        ws=target_ws,
        template_ws=template_ws,
        header_row=target_header_row,
        data_end_row=source_end_row,
        template_data_end_row=template_end_row,
        verbose=verbose,
    )

    return {
        "rows_preserved": max(source_end_row - target_header_row, 0),
        "styles_restored": styles_restored,
        "formulas_restored": formulas_restored,
        "preserved_cells": preserved_cells,
        "externalized_formulas_cleared": externalized_formulas_cleared,
        "cf_blocks_restored": cf_blocks_restored,
    }


def restore_crm_workbook_from_template(
    *,
    workbook_path: Path,
    template_path: Path | None = None,
    output_path: Path | None = None,
    verbose: bool = False,
) -> Dict[str, int]:
    workbook_path = Path(workbook_path).expanduser().resolve()
    resolved_template = _resolve_crm_template_path(template_path, required=True)
    assert resolved_template is not None

    if output_path is None:
        output_path = workbook_path
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_output = output_path.with_name(
        f".{output_path.stem}.template_restore.{os.getpid()}.{time.time_ns()}{output_path.suffix}"
    )
    shutil.copy2(resolved_template, temp_output)

    current_wb = load_workbook(filename=str(workbook_path), read_only=False, data_only=False)
    template_wb = load_workbook(filename=str(resolved_template), read_only=False, data_only=False)
    restored_wb = load_workbook(filename=str(temp_output), read_only=False, data_only=False)
    try:
        if CRM_SALES_SHEET_NAME not in current_wb.sheetnames or CRM_SALES_SHEET_NAME not in restored_wb.sheetnames:
            raise RuntimeError(f"Required sales sheet {CRM_SALES_SHEET_NAME} missing in current or template workbook.")

        sales_stats = _restore_sales_sheet_from_template(
            target_ws=restored_wb[CRM_SALES_SHEET_NAME],
            source_ws=current_wb[CRM_SALES_SHEET_NAME],
            template_ws=template_wb[CRM_SALES_SHEET_NAME],
            table_name=CRM_SALES_TABLE_NAME,
            verbose=verbose,
        )

        sheet_cells_preserved = 0
        sheet_count = 0
        for sheet_name in current_wb.sheetnames:
            if sheet_name not in restored_wb.sheetnames or sheet_name in CRM_TEMPLATE_SHEET_EXCLUDE:
                continue
            copied = _copy_sheet_values_from_source(restored_wb[sheet_name], current_wb[sheet_name])
            sheet_cells_preserved += copied
            sheet_count += 1

        restored_wb.save(str(temp_output))
    finally:
        restored_wb.close()
        template_wb.close()
        current_wb.close()

    os.replace(temp_output, output_path)

    return {
        "sales_rows_preserved": sales_stats["rows_preserved"],
        "sales_styles_restored": sales_stats["styles_restored"],
        "sales_formulas_restored": sales_stats["formulas_restored"],
        "sales_preserved_cells": sales_stats["preserved_cells"],
        "sales_externalized_formulas_cleared": sales_stats["externalized_formulas_cleared"],
        "sales_cf_blocks_restored": sales_stats["cf_blocks_restored"],
        "sheet_values_preserved": sheet_cells_preserved,
        "sheet_count_preserved": sheet_count,
    }


def _repair_appended_rows_formatting(
    workbook_path: Path,
    sheet_name: str,
    table_name: str,
    start_row: int,
    end_row: int,
    *,
    repair_cf_ranges: bool = True,
    verbose: bool = False,
) -> Dict[str, int]:
    if start_row <= 0 or end_row < start_row:
        return {"style_cells_normalized": 0, "cf_rules_normalized": 0}

    workbook_path = Path(workbook_path)
    preserved_package_parts = _snapshot_preserved_package_parts(workbook_path)
    style_cells_normalized = 0
    cf_rules_normalized = 0
    formula_cells_restored = 0
    template_wb = None
    template_ws = None
    template_end_row = None

    wb = load_workbook(filename=str(workbook_path), read_only=False, data_only=False)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        tbl_start_col, tbl_start_row, tbl_end_col, tbl_end_row = _table_bounds(table)
        if start_row < (tbl_start_row + 1) or end_row > tbl_end_row:
            raise RuntimeError(
                f"Append row window {start_row}-{end_row} is outside table bounds {tbl_start_row + 1}-{tbl_end_row}."
            )

        header_values = [
            ws.cell(row=tbl_start_row, column=col).value
            for col in range(tbl_start_col, tbl_end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): tbl_start_col + i
            for i, name in enumerate(header_values)
            if str(name or "").strip()
        }
        formula_cols = _formula_template_columns(header_to_col)
        resolved_template = None
        if sheet_name == CRM_SALES_SHEET_NAME and table_name == CRM_SALES_TABLE_NAME:
            resolved_template = _resolve_crm_template_path()
        if resolved_template is not None and resolved_template.resolve() != workbook_path.resolve():
            template_wb = load_workbook(filename=str(resolved_template), read_only=False, data_only=False)
            if sheet_name in template_wb.sheetnames:
                template_ws = template_wb[sheet_name]
                template_table = _resolve_table(template_ws, table_name)
                if _table_header_signature(ws, table) == _table_header_signature(template_ws, template_table):
                    _, _, _, template_end_row = _table_bounds(template_table)
                else:
                    template_ws = None
                    template_wb.close()
                    template_wb = None

        source_ws = template_ws or ws
        if template_end_row is None:
            template_end_row = start_row - 1
        style_cells_normalized, formula_cells_restored = _restore_formula_and_style_window_from_template(
            ws=ws,
            template_ws=source_ws,
            header_row=tbl_start_row,
            target_start_row=start_row,
            target_end_row=end_row,
            start_col=tbl_start_col,
            end_col=tbl_end_col,
            formula_cols=formula_cols,
            template_data_end_row=template_end_row,
        )
        externalized_formulas_cleared = _sanitize_self_externalized_formula_window(
            ws=ws,
            template_ws=source_ws,
            header_row=tbl_start_row,
            target_start_row=start_row,
            target_end_row=end_row,
            start_col=tbl_start_col,
            end_col=tbl_end_col,
            formula_cols=formula_cols,
            template_data_end_row=template_end_row,
        )

        if repair_cf_ranges:
            if template_ws is not None and template_end_row is not None:
                cf_rules_normalized = _restore_conditional_formatting_from_template(
                    ws=ws,
                    template_ws=template_ws,
                    header_row=tbl_start_row,
                    data_end_row=tbl_end_row,
                    template_data_end_row=template_end_row,
                    verbose=verbose,
                )
                cf_rules_normalized += _normalize_conditional_formatting_ranges(
                    ws=ws,
                    header_row=tbl_start_row,
                    data_end_row=tbl_end_row,
                    header_to_col=header_to_col,
                    verbose=verbose,
                )
            else:
                cf_rules_normalized = _normalize_conditional_formatting_ranges(
                    ws=ws,
                    header_row=tbl_start_row,
                    data_end_row=tbl_end_row,
                    header_to_col=header_to_col,
                    verbose=verbose,
                )

        wb.save(str(workbook_path))
    finally:
        wb.close()
        if template_wb is not None:
            template_wb.close()

    _restore_preserved_package_parts(workbook_path, preserved_package_parts)

    if verbose and (style_cells_normalized or cf_rules_normalized):
        print(
            "  Post-append formatting normalized: "
            f"styles={style_cells_normalized}, formulas={formula_cells_restored}, "
            f"externalized_formulas={externalized_formulas_cleared}, cf_rules={cf_rules_normalized}"
        )
    return {
        "style_cells_normalized": style_cells_normalized,
        "formula_cells_restored": formula_cells_restored,
        "externalized_formulas_cleared": externalized_formulas_cleared,
        "cf_rules_normalized": cf_rules_normalized,
    }


def _verify_formula_cache_readback(
    workbook_path: Path,
    sheet_name: str,
    table_name: str,
    start_row: int,
    end_row: int,
) -> None:
    if start_row <= 0 or end_row < start_row:
        return

    formula_wb = load_workbook(filename=str(workbook_path), read_only=False, data_only=False)
    data_wb = load_workbook(filename=str(workbook_path), read_only=False, data_only=True)
    try:
        formula_ws = formula_wb[sheet_name]
        data_ws = data_wb[sheet_name]
        table = _resolve_table(formula_ws, table_name)
        tbl_start_col, tbl_start_row, _tbl_end_col, tbl_end_row = _table_bounds(table)
        if start_row < (tbl_start_row + 1) or end_row > tbl_end_row:
            raise RuntimeError(
                f"Append row window {start_row}-{end_row} is outside table bounds {tbl_start_row + 1}-{tbl_end_row}."
            )

        header_values = [
            formula_ws.cell(row=tbl_start_row, column=col).value
            for col in range(tbl_start_col, _tbl_end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): tbl_start_col + i
            for i, name in enumerate(header_values)
            if str(name or "").strip()
        }
        required_cols = _required_formula_cache_columns(header_to_col)
        if not required_cols:
            return

        issues: List[str] = []
        max_issues = 12
        for row_num in range(start_row, end_row + 1):
            for label, col_num in required_cols:
                formula_value = formula_ws.cell(row=row_num, column=col_num).value
                if not _has_formula_payload(formula_value):
                    continue
                cached_value = data_ws.cell(row=row_num, column=col_num).value
                if _is_missing_excel_value(cached_value):
                    issues.append(f"row {row_num} {label}({get_column_letter(col_num)})")
                    if len(issues) >= max_issues:
                        break
            if len(issues) >= max_issues:
                break

        if issues:
            suffix = " ..." if len(issues) >= max_issues else ""
            raise AppendVerificationError(
                "Formula cache readback missing after Excel repair: "
                + ", ".join(issues[:max_issues])
                + suffix
            )
    finally:
        formula_wb.close()
        data_wb.close()


def _collect_cf_intervals_for_column(ws: Any, col_num: int) -> List[Tuple[int, int]]:
    intervals: List[Tuple[int, int]] = []
    for cf_obj in ws.conditional_formatting._cf_rules.keys():
        for part in str(cf_obj.sqref).split():
            try:
                cell_range = CellRange(part)
            except Exception:
                continue
            if cell_range.min_col <= col_num <= cell_range.max_col:
                intervals.append((cell_range.min_row, cell_range.max_row))
    if not intervals:
        return intervals
    intervals.sort()
    merged: List[Tuple[int, int]] = [intervals[0]]
    for start, end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _intervals_cover_range(intervals: List[Tuple[int, int]], start_row: int, end_row: int) -> bool:
    for start, end in intervals:
        if start <= start_row and end >= end_row:
            return True
    return False


def _verify_appended_rows_integrity(
    workbook_path: Path,
    sheet_name: str,
    table_name: str,
    start_row: int,
    end_row: int,
    verbose: bool = False,
) -> None:
    if start_row <= 0 or end_row < start_row:
        return

    wb = load_workbook(filename=str(workbook_path), read_only=False, data_only=False)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        tbl_start_col, tbl_start_row, tbl_end_col, tbl_end_row = _table_bounds(table)
        if start_row < (tbl_start_row + 1) or end_row > tbl_end_row:
            raise RuntimeError(
                f"Append row window {start_row}-{end_row} is outside table bounds {tbl_start_row + 1}-{tbl_end_row}."
            )

        header_values = [
            ws.cell(row=tbl_start_row, column=col).value
            for col in range(tbl_start_col, tbl_end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): tbl_start_col + i
            for i, name in enumerate(header_values)
            if str(name or "").strip()
        }

        required_cols = _formula_template_columns(header_to_col)
        raw_required_aliases = (
            {"заказа", "номерзаказа", "№заказа"},
            {"названиетоваравkaspiмагазине"},
            {"артикул"},
            {"статус"},
        )
        for aliases in raw_required_aliases:
            col = _find_header_col(header_to_col, aliases)
            if col:
                required_cols.append(col)
        required_cols = sorted(set(required_cols))

        issues: List[str] = []
        max_issues = 40
        for row_num in range(start_row, end_row + 1):
            for col_num in required_cols:
                value = ws.cell(row=row_num, column=col_num).value
                if isinstance(value, ArrayFormula):
                    expected_ref = f"{get_column_letter(col_num)}{row_num}"
                    actual_ref = str(value.ref or "").strip()
                    if actual_ref != expected_ref:
                        issues.append(
                            f"row {row_num} col {get_column_letter(col_num)} array ref {actual_ref or '<blank>'} != {expected_ref}"
                        )
                        if len(issues) >= max_issues:
                            break
                if _contains_self_external_formula_payload(value):
                    issues.append(
                        f"row {row_num} col {get_column_letter(col_num)} contains self-externalized formula"
                    )
                    if len(issues) >= max_issues:
                        break
                if value in (None, ""):
                    issues.append(f"row {row_num} col {get_column_letter(col_num)} is empty")
                    if len(issues) >= max_issues:
                        break
            if len(issues) >= max_issues:
                break

        style_reference_wb = None
        style_reference_ws = None
        style_reference_end_row = None
        reference_tail_row = None
        reference_desc = None
        try:
            resolved_template = None
            if sheet_name == CRM_SALES_SHEET_NAME and table_name == CRM_SALES_TABLE_NAME:
                resolved_template = _resolve_crm_template_path()
            if resolved_template is not None and resolved_template.resolve() != Path(workbook_path).resolve():
                style_reference_wb = load_workbook(filename=str(resolved_template), read_only=False, data_only=False)
                if sheet_name in style_reference_wb.sheetnames:
                    candidate_ws = style_reference_wb[sheet_name]
                    candidate_table = _resolve_table(candidate_ws, table_name)
                    if _table_header_signature(ws, table) == _table_header_signature(candidate_ws, candidate_table):
                        style_reference_ws = candidate_ws
                        _, _, _, style_reference_end_row = _table_bounds(candidate_table)
                        reference_tail_row = _find_template_row_for_append(
                            ws=style_reference_ws,
                            header_row=tbl_start_row,
                            table_end_row=style_reference_end_row,
                            formula_cols=required_cols,
                        )
                        if reference_tail_row is None:
                            reference_tail_row = style_reference_end_row
                        reference_desc = f"canonical template row {reference_tail_row}"
            if style_reference_ws is None:
                template_row = start_row - 1
                if template_row > tbl_start_row:
                    style_reference_ws = ws
                    style_reference_end_row = tbl_end_row
                    reference_tail_row = template_row
                    reference_desc = f"template row {template_row}"

            if style_reference_ws is not None and reference_tail_row is not None:
                for col_num in required_cols:
                    for row_num in range(start_row, end_row + 1):
                        if style_reference_ws is ws:
                            source_row = reference_tail_row
                        else:
                            source_row = (
                                row_num
                                if style_reference_end_row is not None and row_num <= style_reference_end_row
                                else reference_tail_row
                            )
                        src_cell = style_reference_ws.cell(row=source_row, column=col_num)
                        dst_cell = ws.cell(row=row_num, column=col_num)
                        if not _cell_styles_equivalent(dst_cell, src_cell):
                            issues.append(
                                f"row {row_num} col {get_column_letter(col_num)} style mismatch vs {reference_desc}"
                            )
                            break
                    if len(issues) >= max_issues:
                        break
        finally:
            if style_reference_wb is not None:
                style_reference_wb.close()

        cf_replacements = _build_cf_replacement_by_col(header_to_col, tbl_start_row + 1, tbl_end_row)
        sku_key_col = _find_header_col(header_to_col, {"skukey", "sku_key"})
        for col_num in sorted(set(cf_replacements.keys())):
            intervals = _collect_cf_intervals_for_column(ws, col_num)
            if not intervals:
                continue
            if not _intervals_cover_range(intervals, start_row, end_row):
                issues.append(
                    f"conditional formatting for column {get_column_letter(col_num)} does not cover rows {start_row}-{end_row}"
                )

        if issues:
            sample = "; ".join(issues[:8])
            raise RuntimeError(
                f"Append integrity check failed for rows {start_row}-{end_row}. "
                f"Sample issues: {sample}"
            )
        if verbose:
            print(f"  Append integrity check passed for rows {start_row}-{end_row}")
    finally:
        wb.close()


_PRESERVED_PARTS_EXACT = {
    "[Content_Types].xml",
    "docProps/custom.xml",
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/calcChain.xml",
    "xl/metadata.xml",
    "xl/sharedStrings.xml",
}
_PRESERVED_PART_PREFIXES = (
    "customXml/",
    "xl/externalLinks/",
    "xl/pivotTables/",
    "xl/pivotCache/",
)


def _should_preserve_package_part(part_name: str) -> bool:
    if part_name in _PRESERVED_PARTS_EXACT:
        return True
    return any(part_name.startswith(prefix) for prefix in _PRESERVED_PART_PREFIXES)


def _snapshot_preserved_package_parts(workbook_path: Path) -> Dict[str, bytes]:
    preserved: Dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(workbook_path, "r") as zf:
            for item in zf.infolist():
                if _should_preserve_package_part(item.filename):
                    preserved[item.filename] = zf.read(item.filename)
    except Exception:
        return {}
    return preserved


def _restore_preserved_package_parts(workbook_path: Path, preserved_parts: Dict[str, bytes]) -> None:
    if not preserved_parts:
        return

    tmp_path = workbook_path.with_suffix(f"{workbook_path.suffix}.partsrestore")
    with zipfile.ZipFile(workbook_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            existing_names = set()
            for item in zin.infolist():
                existing_names.add(item.filename)
                payload = preserved_parts.get(item.filename, zin.read(item.filename))
                zout.writestr(item, payload)

            for missing_name in sorted(set(preserved_parts.keys()) - existing_names):
                zout.writestr(missing_name, preserved_parts[missing_name])

    os.replace(str(tmp_path), str(workbook_path))
    normalize_sales_sheet_sku_key_array_formula_refs(workbook_path)
    prune_stale_calcchain_refs(workbook_path)


def _file_fingerprint(path: Path) -> str:
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    return f"{path} (size={stat.st_size} bytes, mtime={mtime})"


@dataclass
class CRMSnapshot:
    date_col: int
    phone_col: Optional[int]
    start_col: int
    end_col: int
    start_row: int
    end_row: int
    slice_headers: list[str]
    order_ids: set[str]
    order_rows: Dict[str, int]
    existing_keys: set[str]
    existing_rollover_keys: set[str]
    column_positions: Dict[str, int]
    planned_col_abs: Optional[int]
    table_date_col: Optional[int]
    delivery_fee_col: Optional[int]
    seller_fee_col: Optional[int]
    delivery_fee_rows: list[tuple[int, Optional[date], float, float]]
    append_date_keys: set[str]
    append_date_key_counts: Dict[str, int]
    append_date_rows: List[CRMDateBlockRow]
    latest_my_size_by_key: Dict[str, str]


def load_crm_snapshot(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    *,
    append_date: Optional[date] = None,
) -> CRMSnapshot:
    """Load CRM metadata in a single openpyxl session (read-only snapshot)."""
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            raise SystemExit(f'Sheet "{sheet_name}" not found in {crm_path}')

        ws = wb[sheet_name]
        header_vals = [c.value if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

        idx_date = None
        idx_phone = None
        idx_start = None
        idx_end = None

        for i, h in enumerate(header_vals, start=1):
            hnorm = norm(h)
            if idx_date is None and hnorm in {"date", "дата"}:
                idx_date = i
            if idx_phone is None and hnorm in {"phone", "телефон", "cellphone"}:
                idx_phone = i
            if idx_start is None and hnorm in {"№заказа", "номерзаказа", "заказа"}:
                idx_start = i
            if hnorm in {"складпередачикд", "складпередачикурьерскойдоставки"}:
                idx_end = i

        if idx_date is None:
            raise SystemExit(f"Could not find 'Date' column. Headers: {header_vals[:10]}...")

        if idx_start is None or idx_end is None or idx_end < idx_start:
            raise SystemExit(
                "Could not locate raw Kaspi columns (Y-AZ). Need '№ заказа' and 'Склад передачи КД'."
            )

        slice_headers = [header_vals[j - 1] for j in range(idx_start, idx_end + 1)]

        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        target_columns = {
            'Статус': None,
            'Дата изменения статуса': None,
            'Принял': None,
            'Выдал': None,
            'Отменил': None,
            'Плановая дата передачи курьеру': None,
            'Стоимость доставки для покупателя': None,
            'Стоимость доставки для продавца': None,
            'Компенсация за доставку': None,
        }

        header_row = list(
            ws.iter_rows(min_row=1, max_row=1, min_col=idx_start, max_col=idx_end)
        )[0]
        for i, cell in enumerate(header_row):
            header = str(cell.value or '').strip()
            if header in target_columns:
                target_columns[header] = idx_start + i

        planned_col_abs = target_columns.get("Плановая дата передачи курьеру")

        order_ids: set[str] = set()
        order_rows: Dict[str, int] = {}
        existing_keys: set[str] = set()
        existing_rollover_keys: set[str] = set()
        delivery_fee_rows: list[tuple[int, Optional[date], float, float]] = []

        planned_in_table = (
            planned_col_abs is not None
            and start_col <= planned_col_abs <= end_col
        )

        table_header = list(
            ws.iter_rows(min_row=start_row, max_row=start_row, min_col=start_col, max_col=end_col)
        )[0]
        table_map: Dict[str, int] = {}
        for i, cell in enumerate(table_header):
            header = str(cell.value or "").strip()
            if header:
                table_map[header] = start_col + i

        table_date_col = table_map.get("Date") or table_map.get("Дата поступления заказа")
        delivery_fee_col = table_map.get("Delivery_fee_kzt") or table_map.get("Delivery_fee")
        seller_fee_col = table_map.get("Стоимость доставки для продавца")
        offer_col_abs = table_map.get("Название товара в Kaspi Магазине")
        article_col_abs = table_map.get("Артикул")
        quantity_col_abs = table_map.get("Количество")
        my_size_col_abs = table_map.get("MY_SIZE")

        append_date_keys: set[str] = set()
        append_date_key_counts: Dict[str, int] = {}
        append_date_rows: List[CRMDateBlockRow] = []
        latest_my_size_by_key: Dict[str, str] = {}

        for row_num in range(start_row + 1, end_row + 1):
            order_val = ws.cell(row=row_num, column=idx_start).value
            if order_val in (None, ""):
                continue
            if isinstance(order_val, str) and order_val.startswith("="):
                continue
            if isinstance(order_val, float):
                order_val = int(order_val)
            order_id = str(order_val).strip()
            if not order_id:
                continue
            order_ids.add(order_id)
            order_rows[order_id] = row_num

            cleaned = clean_order_id(order_val)
            if not cleaned:
                continue

            planned_date = None
            if planned_in_table:
                planned_val = ws.cell(row=row_num, column=planned_col_abs).value
                planned_date = parse_date(planned_val)

            offer_val = ws.cell(row=row_num, column=offer_col_abs).value if offer_col_abs else ""
            article_val = ws.cell(row=row_num, column=article_col_abs).value if article_col_abs else ""
            qty_val = ws.cell(row=row_num, column=quantity_col_abs).value if quantity_col_abs else 0
            key = _build_line_dedupe_key(
                cleaned,
                planned_date,
                offer_val,
                article_val,
                qty_val,
            )
            existing_keys.add(key)

            row_date = None
            if table_date_col:
                row_date = parse_date(ws.cell(row=row_num, column=table_date_col).value)
                if row_date is not None and planned_date is not None and row_date > planned_date:
                    existing_rollover_keys.add(key)

            my_size = ""
            if my_size_col_abs:
                my_size = _coerce_str(ws.cell(row=row_num, column=my_size_col_abs).value)
                if my_size:
                    latest_my_size_by_key[key] = my_size
            if append_date is not None and row_date == append_date:
                append_date_keys.add(key)
                append_date_key_counts[key] = int(append_date_key_counts.get(key, 0)) + 1
                append_date_rows.append(
                    CRMDateBlockRow(
                        row_num=row_num,
                        line_key=key,
                        my_size=my_size,
                    )
                )

            if table_date_col and delivery_fee_col and seller_fee_col:
                parsed_date = row_date
                seller_val = ws.cell(row=row_num, column=seller_fee_col).value
                fee_val = ws.cell(row=row_num, column=delivery_fee_col).value
                try:
                    seller_num = float(seller_val) if seller_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    seller_num = 0.0
                try:
                    fee_num = float(fee_val) if fee_val not in (None, "") else 0.0
                except (TypeError, ValueError):
                    fee_num = 0.0
                delivery_fee_rows.append((row_num, parsed_date, seller_num, fee_num))

        print(f"  Date column: {idx_date} (B)")
        if idx_phone:
            print(f"  Phone column: {idx_phone} (I)")
        else:
            print("  Phone column: not found (will skip phone import)")
        print(f"  Raw Kaspi columns: {idx_start}-{idx_end} (Y-AZ)")

        return CRMSnapshot(
            date_col=idx_date,
            phone_col=idx_phone,
            start_col=idx_start,
            end_col=idx_end,
            start_row=start_row,
            end_row=end_row,
            slice_headers=slice_headers,
            order_ids=order_ids,
            order_rows=order_rows,
            existing_keys=existing_keys,
            existing_rollover_keys=existing_rollover_keys,
            column_positions=target_columns,
            planned_col_abs=planned_col_abs,
            table_date_col=table_date_col,
            delivery_fee_col=delivery_fee_col,
            seller_fee_col=seller_fee_col,
            delivery_fee_rows=delivery_fee_rows,
            append_date_keys=append_date_keys,
            append_date_key_counts=append_date_key_counts,
            append_date_rows=append_date_rows,
            latest_my_size_by_key=latest_my_size_by_key,
        )
    finally:
        wb.close()


def collect_existing_order_ids(
    crm_path: Path, 
    sheet_name: str, 
    table_name: str, 
    order_col_abs: int
) -> set:
    """Get set of existing OrderIDs from CRM."""
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)
        
        if not (start_col <= order_col_abs <= end_col):
            return set()
        
        order_ids = set()
        for row in ws.iter_rows(min_row=start_row + 1, max_row=end_row, 
                                min_col=order_col_abs, max_col=order_col_abs):
            cell = row[0]
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            order_ids.add(str(val).strip())
        return order_ids
    finally:
        wb.close()


def collect_existing_order_keys(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    order_col_abs: int,
    planned_col_abs: Optional[int],
) -> set:
    """
    Get set of existing order keys from CRM.

    Key format: "{order_id}|{YYYY-MM-DD}" if planned date exists,
    otherwise "{order_id}|" (empty planned date).
    """
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        if not (start_col <= order_col_abs <= end_col):
            return set()

        planned_in_table = (
            planned_col_abs is not None
            and start_col <= planned_col_abs <= end_col
        )

        keys = set()
        for row_num in range(start_row + 1, end_row + 1):
            order_val = ws.cell(row=row_num, column=order_col_abs).value
            if order_val in (None, ""):
                continue
            if isinstance(order_val, str) and order_val.startswith("="):
                continue
            order_id = clean_order_id(order_val)
            if not order_id:
                continue

            planned_date = None
            if planned_in_table:
                planned_val = ws.cell(row=row_num, column=planned_col_abs).value
                planned_date = parse_date(planned_val)

            if planned_date:
                key = f"{order_id}|{planned_date.isoformat()}"
            else:
                key = f"{order_id}|"
            keys.add(key)

        return keys
    finally:
        wb.close()


def collect_existing_order_rows(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    order_col_abs: int
) -> Dict[str, int]:
    """
    Get dict mapping OrderID -> row number from CRM.

    Used for updating existing orders.
    """
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        if not (start_col <= order_col_abs <= end_col):
            return {}

        order_rows = {}
        for row_num in range(start_row + 1, end_row + 1):
            cell = ws.cell(row=row_num, column=order_col_abs)
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            # Convert float to int to match API format (741866233.0 -> "741866233")
            if isinstance(val, float):
                val = int(val)
            order_id = str(val).strip()
            if order_id:
                order_rows[order_id] = row_num
        return order_rows
    finally:
        wb.close()


def find_update_column_positions(
    crm_path: Path,
    sheet_name: str,
    start_col: int,
    end_col: int
) -> Dict[str, int]:
    """
    Find column positions for update fields within the raw Kaspi columns.

    Returns dict mapping column name -> absolute column position.
    Target columns: Статус, Дата изменения статуса, Принял, Выдал, Отменил,
    Плановая дата передачи курьеру, Стоимость доставки для покупателя,
    Стоимость доставки для продавца, Компенсация за доставку
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        header_row = list(ws.iter_rows(min_row=1, max_row=1, min_col=start_col, max_col=end_col))[0]

        target_columns = {
            'Статус': None,
            'Дата изменения статуса': None,
            'Принял': None,
            'Выдал': None,
            'Отменил': None,
            'Плановая дата передачи курьеру': None,
            'Стоимость доставки для покупателя': None,
            'Стоимость доставки для продавца': None,
            'Компенсация за доставку': None,
        }

        for i, cell in enumerate(header_row):
            header = str(cell.value or '').strip()
            if header in target_columns:
                target_columns[header] = start_col + i

        return target_columns
    finally:
        wb.close()


def _require_xlwings() -> None:
    if xw is None:
        raise RuntimeError(
            "xlwings is required for Excel writes. "
            "Install with `pip install xlwings` or run with --dry-run/--no-update."
        )


def update_existing_order_columns(
    crm_path: Path,
    sheet_name: str,
    order_rows: Dict[str, int],  # order_id -> row number
    update_data: Dict[str, dict],  # order_id -> {Статус, Принял, Выдал, Отменил, ...}
    column_positions: Dict[str, int],  # column name -> absolute column position
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Update specific columns for existing orders in CRM.

    Only updates: Статус, Дата изменения статуса, Принял, Выдал, Отменил
    Does NOT touch Status column (A) or formula columns.

    Uses BATCH writes by column to avoid slow cell-by-cell operations.

    Args:
        crm_path: Path to CRM file
        sheet_name: Sheet name
        order_rows: Dict mapping order_id -> Excel row number
        update_data: Dict mapping order_id -> column values to update
        column_positions: Dict mapping column name -> absolute column position
        dry_run: If True, don't write changes
        verbose: If True, print progress

    Returns:
        Number of orders updated
    """
    if not order_rows or not update_data:
        return 0

    # Find orders that exist in both
    orders_to_update = set(order_rows.keys()) & set(update_data.keys())

    if not orders_to_update:
        if verbose:
            print("  No existing orders to update")
        return 0

    if verbose:
        print(f"  Found {len(orders_to_update)} orders to update")

    if dry_run:
        print(f"  [DRY RUN] Would update {len(orders_to_update)} orders")
        return 0

    _require_xlwings()

    # Pre-build column updates: {col_pos: [(row, value), ...]}
    # This allows us to batch writes by column instead of cell-by-cell
    column_updates: Dict[int, List[Tuple[int, any]]] = {}

    for order_id in orders_to_update:
        row = order_rows[order_id]
        data = update_data[order_id]

        for col_name, col_pos in column_positions.items():
            if col_pos is None:
                continue
            if col_name in data:
                new_value = data[col_name]
                if new_value is not None:
                    if col_pos not in column_updates:
                        column_updates[col_pos] = []
                    column_updates[col_pos].append((row, new_value))

    if verbose:
        total_cells = sum(len(v) for v in column_updates.values())
        print(f"  Preparing {total_cells} cell updates across {len(column_updates)} columns...")

    # Use xlwings for writing (preserves formulas)
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = _open_workbook_xlwings(app, crm_path, update_links=False, read_only=False)
        ws = wb.sheets[sheet_name]

        # Disable calculation during updates for speed
        original_calc = app.calculation
        app.calculation = 'manual'

        # Write updates column by column
        cols_written = 0
        for col_pos, row_values in column_updates.items():
            # Sort by row for potential range optimization
            row_values.sort(key=lambda x: x[0])

            # Write all values for this column
            for row, value in row_values:
                ws.range((row, col_pos)).value = value

            cols_written += 1
            if verbose:
                print(f"    Column {cols_written}/{len(column_updates)} updated ({len(row_values)} cells)")

        # Restore calculation and save
        app.calculation = original_calc
        wb.save()
        wb.close()

        if verbose:
            print(f"  Updated {len(orders_to_update)} orders")

        return len(orders_to_update)

    finally:
        _safe_quit_xlwings_app(app, context="existing-order updates")


def build_update_data(df: pd.DataFrame, colmap: Dict[str, str]) -> Dict[str, dict]:
    """
    Build update data dict from DataFrame.

    Extracts: order_id -> {
        Статус, Дата изменения статуса, Принял, Выдал, Отменил,
        Плановая дата передачи курьеру,
        Стоимость доставки для покупателя, Стоимость доставки для продавца, Компенсация за доставку
    }
    for updating existing orders in CRM.
    """
    update_data = {}

    # Find column names in DataFrame
    status_col = None
    status_change_col = None
    prinyal_col = None
    vydal_col = None
    otmenil_col = None
    planned_date_col = None
    buyer_cost_col = None
    seller_cost_col = None
    delivery_comp_col = None

    for col in df.columns:
        col_norm = norm(col)
        if col_norm == 'статус':
            status_col = col
        elif col_norm in {'датаизменениястатуса', 'statuschangedate'}:
            status_change_col = col
        elif col_norm == 'принял':
            prinyal_col = col
        elif col_norm == 'выдал':
            vydal_col = col
        elif col_norm == 'отменил':
            otmenil_col = col
        elif col_norm == 'плановаядатапередачикурьеру':
            planned_date_col = col
        elif col_norm == 'стоимостьдоставкидляпокупателя':
            buyer_cost_col = col
        elif col_norm == 'стоимостьдоставкидляпродавца':
            seller_cost_col = col
        elif col_norm == 'компенсациязадоставку':
            delivery_comp_col = col

    order_col = colmap.get('order_id')
    if not order_col:
        return {}

    for _, row in df.iterrows():
        order_id = str(row.get(order_col, '')).strip()
        if not order_id:
            continue

        # Convert float order_id to int string (741866233.0 -> "741866233")
        try:
            order_id = str(int(float(order_id)))
        except (ValueError, TypeError):
            pass

        data = {}
        if status_col and pd.notna(row.get(status_col)):
            data['Статус'] = str(row[status_col])
        if status_change_col and pd.notna(row.get(status_change_col)):
            data['Дата изменения статуса'] = row[status_change_col]
        if prinyal_col:
            data['Принял'] = str(row.get(prinyal_col, '') or '')
        if vydal_col:
            data['Выдал'] = str(row.get(vydal_col, '') or '')
        if otmenil_col:
            data['Отменил'] = str(row.get(otmenil_col, '') or '')
        if planned_date_col and pd.notna(row.get(planned_date_col)):
            data['Плановая дата передачи курьеру'] = row.get(planned_date_col)
        if buyer_cost_col and pd.notna(row.get(buyer_cost_col)):
            data['Стоимость доставки для покупателя'] = row.get(buyer_cost_col)
        if seller_cost_col and pd.notna(row.get(seller_cost_col)):
            data['Стоимость доставки для продавца'] = row.get(seller_cost_col)
        if delivery_comp_col and pd.notna(row.get(delivery_comp_col)):
            data['Компенсация за доставку'] = row.get(delivery_comp_col)

        if data:
            update_data[order_id] = data

    return update_data


# ---------- Build Staging Data ----------

def build_staging(df_filt: pd.DataFrame, crm_slice_headers: List[str]) -> Tuple[List[List], List[Any]]:
    """
    Build 2D list matching CRM slice columns plus phone values.

    Returns: (stage_block, phone_values)
    """
    colmap = map_headers(df_filt)

    # Series by canonical key
    S: Dict[str, pd.Series] = {}
    for k, real in colmap.items():
        S[k] = df_filt[real].astype(object)

    # Direct lookup by normalized header
    cols_norm_map = {norm(col): df_filt[col].astype(object) for col in df_filt.columns}

    n = len(df_filt)
    records = df_filt.to_dict(orient="records")
    articles = [str(r.get("Артикул") or r.get("SKU_ID_KSP") or "").strip() for r in records]
    article_identity = _load_article_identity_for_articles(articles)
    seed_sku_keys = []
    for r in records:
        maybe_key = str(r.get("SKU_key") or "").strip()
        if maybe_key:
            seed_sku_keys.append(maybe_key)
    _, _, valid_sku_keys = _load_sku_meta_for_keys(seed_sku_keys)
    derived_identity = []
    for row in records:
        derived_identity.append(
            _derive_identity_from_raw_row(
                row,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
        )
    derived_sku_key = pd.Series([d.get("sku_key") or "" for d in derived_identity], index=df_filt.index, dtype=object)

    def col_for(header_text: str) -> pd.Series:
        h = norm(header_text)

        # Map canonical keys
        # Note: "№ заказа" normalizes to "заказа"
        if h in _ORDER_ID_HEADER_ALIASES and "order_id" in S:
            col = S["order_id"].copy()
            col = col.apply(_coerce_order_id_numeric)
            return col

        if h in {"названиевсистемепродавца"} and "seller_name" in S:
            return S["seller_name"]

        if h in {"названиетоваравkaspiмагазине"} and "offer_name" in S:
            return S["offer_name"]

        if h in {"артикул"} and "sku" in S:
            return S["sku"].apply(normalize_article_code)

        if h in {"складпередачикд", "складпередачикурьерскойдоставки"} and "warehouse" in S:
            return S["warehouse"]

        if h in {"skukey", "sku_key"}:
            if h in cols_norm_map:
                source_series = cols_norm_map[h].astype(object)
                if valid_sku_keys:
                    merged = []
                    for idx in source_series.index:
                        src = str(source_series.loc[idx] or "").strip()
                        merged.append(src if src in valid_sku_keys else str(derived_sku_key.loc[idx] or "").strip())
                    return pd.Series(merged, index=df_filt.index, dtype=object)
                return source_series
            return derived_sku_key

        if h in {"mysize", "my_size"}:
            # Human-owned column: must remain blank for manual assignment.
            return pd.Series([""] * n, index=df_filt.index, dtype=object)

        if h in {"датаизменениястатуса"} and "status_change_date" in S:
            return S["status_change_date"]

        # Direct match
        if h in cols_norm_map:
            return cols_norm_map[h]

        return pd.Series([""] * n, index=df_filt.index, dtype=object)

    cols = [col_for(h) for h in crm_slice_headers]

    stage = []
    for i in range(len(df_filt)):
        row = []
        for s in cols:
            v = s.iloc[i]
            if pd.isna(v):
                v = ""
            row.append(v)
        stage.append(row)

    # Extract phone values separately as numeric MSISDN.
    phone_values = []
    if "phone" in S:
        for i in range(len(df_filt)):
            v = _coerce_phone_numeric(S["phone"].iloc[i])
            phone_values.append(v)
    else:
        phone_values = [""] * len(df_filt)

    return stage, phone_values


# ---------- Excel Append via xlwings ----------

def _build_xlwings_write_plan(
    stage_block: List[List[Any]],
    slice_headers: List[str],
) -> Tuple[List[List[Any]], List[Tuple[int, int]], List[int]]:
    """
    Build xlwings write plan that skips fully empty staged columns (so formula
    autofill columns are preserved) while minimizing AppleEvent write calls.
    """
    width = len(slice_headers)
    order_offsets = [
        idx
        for idx, header in enumerate(slice_headers)
        if norm(header) in _ORDER_ID_HEADER_ALIASES
    ]
    order_offset_set = set(order_offsets)

    col_values_by_offset: List[List[Any]] = []
    non_empty_offsets: List[int] = []
    for offset in range(width):
        col_values = [(row[offset] if offset < len(row) else "") for row in stage_block]
        if offset in order_offset_set:
            col_values = [_coerce_order_id_numeric(v) for v in col_values]
        col_values_by_offset.append(col_values)
        if not all((v is None) or (isinstance(v, str) and v == "") for v in col_values):
            non_empty_offsets.append(offset)

    write_segments: List[Tuple[int, int]] = []
    if non_empty_offsets:
        seg_start = non_empty_offsets[0]
        prev = seg_start
        for offset in non_empty_offsets[1:]:
            if offset == prev + 1:
                prev = offset
                continue
            write_segments.append((seg_start, prev))
            seg_start = offset
            prev = offset
        write_segments.append((seg_start, prev))

    return col_values_by_offset, write_segments, order_offsets


def excel_append_xlwings(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    date_col_abs: int,
    phone_col_abs: Optional[int],
    start_col_abs: int,
    end_col_abs: int,
    stage_block: List[List],
    phone_values: List[Any],
    set_date: date,
    slice_headers: List[str],
    fixed_values: Optional[List[Dict[str, Any]]] = None,
    kaspi_name_core_values: Optional[List[str]] = None,
    preserved_my_sizes: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """
    Append rows to CRM using xlwings (preserves formulas & external links).

    Args:
        phone_col_abs: Column for phone data (column I), or None to skip
        phone_values: List of phone strings to write

    Returns:
        Tuple of (start_row, end_row) where new rows were appended.
        Returns (0, 0) if no rows were appended.
    """
    n = len(stage_block)
    if n == 0:
        return (0, 0)

    _require_xlwings()

    print(f"  Opening Excel (hidden)...")
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    wb = None

    try:
        wb = _open_workbook_xlwings(app, out_wb, update_links=False, read_only=False)
        sh = wb.sheets[sheet_name]
        with _temporary_manual_calculation(app):
            # Find the table
            try:
                tbl = sh.tables[table_name]
            except KeyError:
                tables = list(sh.tables)
                if not tables:
                    raise RuntimeError(f"No table found on sheet {sheet_name}")
                tbl = tables[0]

            # Calculate where new rows go
            total_rows_before = tbl.range.rows.count
            header_row = tbl.range.row
            data_rows_before = total_rows_before - 1

            top_row = header_row + data_rows_before + 1
            bottom_row = top_row + n - 1

            print(f"  Appending {n} rows starting at row {top_row}")

            # CRITICAL: Resize table FIRST to include new rows
            # This prevents Excel table corruption (XML errors)
            tbl_start_col = tbl.range.column
            tbl_end_col = tbl.range.columns.count + tbl_start_col - 1
            new_table_range = sh.range(
                (header_row, tbl_start_col),
                (bottom_row, tbl_end_col)
            )
            tbl.resize(new_table_range)
            print(f"  Table resized to include rows up to {bottom_row}")

            # Write date column
            date_vals = [[set_date] for _ in range(n)]
            date_range = sh.range((top_row, date_col_abs), (bottom_row, date_col_abs))
            date_range.value = date_vals
            date_range.number_format = "dd.mm.yyyy"

            # Write "Новый" marker to HEIGHT column (D = 4) for visual identification
            # Phase 12 Part 3: Helps employees see which orders were added in second import
            height_col = 4  # Column D
            height_range = sh.range((top_row, height_col), (bottom_row, height_col))
            height_range.value = [["Новый"] for _ in range(n)]
            print(f"  'Новый' marker written to column D for {n} rows")

            # Write phone column (Phase 12)
            if phone_col_abs and phone_values:
                normalized_phones = [_coerce_phone_numeric(v) for v in phone_values]
                has_phones = any(v not in (None, "") for v in normalized_phones)
                if has_phones:
                    phone_range = sh.range((top_row, phone_col_abs), (bottom_row, phone_col_abs))
                    phone_range.value = [[v if v not in (None, "") else None] for v in normalized_phones]
                    phone_range.number_format = "0"
                    print(f"  Phone data written to column {phone_col_abs}")

            # Write data using contiguous segments to reduce AppleEvent round-trips.
            col_values_by_offset, write_segments, order_offsets = _build_xlwings_write_plan(
                stage_block=stage_block,
                slice_headers=slice_headers,
            )
            for seg_start, seg_end in write_segments:
                block = [
                    [col_values_by_offset[offset][row_idx] for offset in range(seg_start, seg_end + 1)]
                    for row_idx in range(n)
                ]
                target = sh.range(
                    (top_row, start_col_abs + seg_start),
                    (bottom_row, start_col_abs + seg_end),
                )
                target.value = block

            for order_offset in order_offsets:
                col_values = col_values_by_offset[order_offset]
                if all((v is None) or (isinstance(v, str) and v == "") for v in col_values):
                    continue
                order_target = sh.range(
                    (top_row, start_col_abs + order_offset),
                    (bottom_row, start_col_abs + order_offset),
                )
                order_target.number_format = "0"

            table_header = sh.range(
                (header_row, tbl_start_col),
                (header_row, tbl_end_col),
            ).value
            header_to_col = {
                str(name).strip(): tbl_start_col + i
                for i, name in enumerate(table_header or [])
                if str(name or "").strip()
            }

            # Write fixed-value columns for appended rows (excluding human-owned fields).
            if fixed_values:
                for col_name in FIXED_APPEND_COLUMNS:
                    if col_name in PROTECTED_HUMAN_COLUMNS:
                        continue
                    col_abs = header_to_col.get(col_name)
                    if not col_abs:
                        continue
                    col_vals = []
                    for row_vals in fixed_values:
                        value = row_vals.get(col_name)
                        col_vals.append([value if value is not None else ""])
                    target = sh.range((top_row, col_abs), (bottom_row, col_abs))
                    target.value = col_vals

            # MY_SIZE is human-owned; always clear for newly appended rows to
            # prevent Excel table formula autofill or parser-derived defaults
            # from writing pseudo sizes during import.
            my_size_col_abs = None
            my_size_col_abs = header_to_col.get("MY_SIZE")
            if my_size_col_abs:
                _clear_my_size_range(
                    sheet=sh,
                    top_row=top_row,
                    bottom_row=bottom_row,
                    my_size_col_abs=my_size_col_abs,
                )

            wb.save()
        wb.close()
        wb = None
        print(f"  ✅ Saved {out_wb.name}")

        return (top_row, bottom_row)

    finally:
        if wb is not None:
            _safe_close_xlwings_book(wb, context="append")
        _safe_quit_xlwings_app(app, context="append")

    return (0, 0)  # If we get here somehow


def excel_append_openpyxl(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    date_col_abs: int,
    phone_col_abs: Optional[int],
    start_col_abs: int,
    end_col_abs: int,
    stage_block: List[List],
    phone_values: List[Any],
    set_date: date,
    slice_headers: List[str],
    fixed_values: Optional[List[Dict[str, Any]]] = None,
    kaspi_name_core_values: Optional[List[str]] = None,
    preserved_my_sizes: Optional[List[str]] = None,
    *,
    repair_cf_ranges: bool = True,
    verbose: bool = False,
) -> Tuple[int, int]:
    """
    Append rows with openpyxl fallback when Excel automation is blocked.
    """
    n = len(stage_block)
    if n == 0:
        return (0, 0)

    preserved_package_parts = _snapshot_preserved_package_parts(out_wb)
    wb = load_workbook(filename=str(out_wb), read_only=False, data_only=False)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        tbl_start_col, tbl_start_row, tbl_end_col, tbl_end_row = _table_bounds(table)
        header_row = tbl_start_row
        top_row = tbl_end_row + 1
        bottom_row = top_row + n - 1
        old_table_ref = table.ref

        header_values = [
            ws.cell(row=header_row, column=col).value
            for col in range(tbl_start_col, tbl_end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): tbl_start_col + i
            for i, name in enumerate(header_values)
            if str(name or "").strip()
        }
        formula_cols = _formula_template_columns(header_to_col)
        template_wb = None
        template_ws = None
        template_end_row = tbl_end_row
        resolved_template = None
        if sheet_name == CRM_SALES_SHEET_NAME and table_name == CRM_SALES_TABLE_NAME:
            resolved_template = _resolve_crm_template_path()
        if resolved_template is not None and resolved_template.resolve() != Path(out_wb).resolve():
            template_wb = load_workbook(filename=str(resolved_template), read_only=False, data_only=False)
            if sheet_name in template_wb.sheetnames:
                template_ws = template_wb[sheet_name]
                template_table = _resolve_table(template_ws, table_name)
                if _table_header_signature(ws, table) == _table_header_signature(template_ws, template_table):
                    _, _, _, template_end_row = _table_bounds(template_table)
                else:
                    template_ws = None
                    template_wb.close()
                    template_wb = None
        _restore_formula_and_style_window_from_template(
            ws=ws,
            template_ws=template_ws or ws,
            header_row=header_row,
            target_start_row=top_row,
            target_end_row=bottom_row,
            start_col=tbl_start_col,
            end_col=tbl_end_col,
            formula_cols=formula_cols,
            template_data_end_row=template_end_row,
        )

        for row_num in range(top_row, bottom_row + 1):
            cell = ws.cell(row=row_num, column=date_col_abs, value=set_date)
            cell.number_format = "dd.mm.yyyy"
            ws.cell(row=row_num, column=4, value="Новый")

        if phone_col_abs and phone_values:
            normalized = [_coerce_phone_numeric(v) for v in phone_values]
            if any(v not in (None, "") for v in normalized):
                if len(normalized) < n:
                    normalized.extend([""] * (n - len(normalized)))
                normalized = normalized[:n]
                for idx, value in enumerate(normalized):
                    cell = ws.cell(row=top_row + idx, column=phone_col_abs)
                    if value in (None, ""):
                        cell.value = ""
                    else:
                        cell.value = value
                        cell.number_format = "0"

        width = min(len(slice_headers), max(0, end_col_abs - start_col_abs + 1))
        order_header_offsets = {
            idx for idx, header in enumerate(slice_headers[:width])
            if norm(header) in _ORDER_ID_HEADER_ALIASES
        }
        for row_offset, row_values in enumerate(stage_block):
            row_num = top_row + row_offset
            for offset in range(width):
                value = row_values[offset] if offset < len(row_values) else ""
                col_num = start_col_abs + offset
                cell = ws.cell(row=row_num, column=col_num)
                if offset in order_header_offsets:
                    coerced = _coerce_order_id_numeric(value)
                    if coerced in (None, ""):
                        cell.value = ""
                    else:
                        cell.value = coerced
                        if isinstance(coerced, int):
                            cell.data_type = "n"
                        cell.number_format = "0"
                else:
                    cell.value = "" if value is None else value

        if fixed_values:
            for col_name in FIXED_APPEND_COLUMNS:
                if col_name in PROTECTED_HUMAN_COLUMNS:
                    continue
                col_abs = header_to_col.get(col_name)
                if not col_abs:
                    continue
                for idx, row_vals in enumerate(fixed_values):
                    value = row_vals.get(col_name)
                    ws.cell(
                        row=top_row + idx,
                        column=col_abs,
                        value="" if value is None else value,
                    )

        my_size_col_abs = header_to_col.get("MY_SIZE")
        if my_size_col_abs:
            for row_num in range(top_row, bottom_row + 1):
                ws.cell(row=row_num, column=my_size_col_abs, value="")

        table.ref = (
            f"{get_column_letter(tbl_start_col)}{tbl_start_row}:"
            f"{get_column_letter(tbl_end_col)}{bottom_row}"
        )
        if repair_cf_ranges:
            if template_ws is not None:
                _restore_conditional_formatting_from_template(
                    ws=ws,
                    template_ws=template_ws,
                    header_row=header_row,
                    data_end_row=bottom_row,
                    template_data_end_row=template_end_row,
                    verbose=verbose,
                )
                _normalize_conditional_formatting_ranges(
                    ws=ws,
                    header_row=header_row,
                    data_end_row=bottom_row,
                    header_to_col=header_to_col,
                    verbose=verbose,
                )
            else:
                _normalize_conditional_formatting_ranges(
                    ws=ws,
                    header_row=header_row,
                    data_end_row=bottom_row,
                    header_to_col=header_to_col,
                    verbose=verbose,
                )
        if template_wb is not None:
            template_wb.close()
        wb.save(str(out_wb))
    finally:
        wb.close()

    _restore_preserved_package_parts(out_wb, preserved_package_parts)

    print(f"  Appending {n} rows starting at row {top_row}")
    print(f"  Table ref: {old_table_ref} -> {table.ref}")
    print(f"  ✅ Saved {out_wb.name} (openpyxl fallback)")
    return (top_row, bottom_row)


def append_orders_with_fallback(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    date_col_abs: int,
    phone_col_abs: Optional[int],
    start_col_abs: int,
    end_col_abs: int,
    stage_block: List[List],
    phone_values: List[Any],
    set_date: date,
    slice_headers: List[str],
    fixed_values: Optional[List[Dict[str, Any]]] = None,
    kaspi_name_core_values: Optional[List[str]] = None,
    preserved_my_sizes: Optional[List[str]] = None,
    *,
    allow_openpyxl_fallback: bool = False,
    prefer_xlwings: bool = True,
    repair_cf_ranges: bool = True,
    verbose: bool = False,
) -> Tuple[int, int]:
    use_openpyxl_direct = not prefer_xlwings

    if prefer_xlwings:
        snapshot_path = _create_temporary_workbook_snapshot(out_wb)
        snapshot_restored = False
        try:
            appended_rows = _run_with_posix_alarm_timeout(
                _xlwings_append_timeout_sec(),
                excel_append_xlwings,
                out_wb,
                sheet_name,
                table_name,
                date_col_abs,
                phone_col_abs,
                start_col_abs,
                end_col_abs,
                stage_block,
                phone_values,
                set_date,
                slice_headers,
                fixed_values=fixed_values,
                kaspi_name_core_values=kaspi_name_core_values,
                preserved_my_sizes=preserved_my_sizes,
            )
            append_start_row, append_end_row = appended_rows
            try:
                if repair_cf_ranges:
                    _repair_appended_rows_formatting(
                        workbook_path=out_wb,
                        sheet_name=sheet_name,
                        table_name=table_name,
                        start_row=append_start_row,
                        end_row=append_end_row,
                        repair_cf_ranges=True,
                        verbose=verbose,
                    )

                _refresh_formula_caches_xlwings(out_wb, verbose=verbose)
                _verify_formula_cache_readback(
                    workbook_path=out_wb,
                    sheet_name=sheet_name,
                    table_name=table_name,
                    start_row=append_start_row,
                    end_row=append_end_row,
                )
                _verify_appended_rows_integrity(
                    workbook_path=out_wb,
                    sheet_name=sheet_name,
                    table_name=table_name,
                    start_row=append_start_row,
                    end_row=append_end_row,
                    verbose=verbose,
                )
            except Exception as exc:
                _restore_workbook_snapshot(snapshot_path, out_wb)
                snapshot_restored = True
                raise AppendVerificationError(
                    "xlwings append post-processing failed; workbook restored from pre-append snapshot."
                ) from exc
            return appended_rows
        except Exception as exc:
            if not snapshot_restored:
                try:
                    _restore_workbook_snapshot(snapshot_path, out_wb)
                    snapshot_restored = True
                except Exception as restore_exc:
                    raise AppendVerificationError(
                        "xlwings append failed and workbook restore failed: "
                        f"{restore_exc}"
                    ) from exc
            if not allow_openpyxl_fallback:
                raise
            timeout_like = _is_expected_xlwings_timeout(exc)
            if timeout_like:
                print("  WARNING: xlwings append timed out; switching to openpyxl fallback.")
            else:
                print(f"  WARNING: xlwings append failed ({exc})")
            if verbose and not timeout_like:
                import traceback

                traceback.print_exc()
        finally:
            _cleanup_temporary_workbook_snapshot(snapshot_path)

    if not allow_openpyxl_fallback and not use_openpyxl_direct:
        raise RuntimeError("Openpyxl append fallback is disabled.")

    if use_openpyxl_direct:
        if verbose:
            print("  Using openpyxl append path.")
    else:
        print("  WARNING: using openpyxl append fallback.")
    return excel_append_openpyxl(
        out_wb,
        sheet_name,
        table_name,
        date_col_abs,
        phone_col_abs,
        start_col_abs,
        end_col_abs,
        stage_block,
        phone_values,
        set_date,
        slice_headers,
        fixed_values=fixed_values,
        kaspi_name_core_values=kaspi_name_core_values,
        preserved_my_sizes=preserved_my_sizes,
        repair_cf_ranges=repair_cf_ranges,
        verbose=verbose,
    )


def delete_crm_rows_xlwings(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    row_numbers: List[int],
) -> int:
    """Delete CRM worksheet rows bottom-up via xlwings and keep table bounds valid."""
    row_numbers = sorted({int(r) for r in row_numbers if int(r) > 0}, reverse=True)
    if not row_numbers:
        return 0

    _require_xlwings()

    print(f"  Opening Excel (hidden) for CRM reconcile delete...")
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    wb = None
    fallback_to_openpyxl = False
    fallback_exc: Exception | None = None

    try:
        wb = _open_workbook_xlwings(app, out_wb, update_links=False, read_only=False)
        sh = wb.sheets[sheet_name]
        with _temporary_manual_calculation(app):
            try:
                tbl = sh.tables[table_name]
            except KeyError:
                try:
                    tables = list(sh.tables)
                except Exception as exc:
                    if _is_xlwings_table_access_failure(exc):
                        fallback_to_openpyxl = True
                        fallback_exc = exc
                        tables = []
                    else:
                        raise
                if not tables:
                    if fallback_to_openpyxl:
                        tbl = None
                    else:
                        raise RuntimeError(f"No table found on sheet {sheet_name}")
                else:
                    tbl = tables[0]
            except Exception as exc:
                if _is_xlwings_table_access_failure(exc):
                    fallback_to_openpyxl = True
                    fallback_exc = exc
                    tbl = None
                else:
                    raise
            if not fallback_to_openpyxl:
                header_row = tbl.range.row
                tbl_start_col = tbl.range.column
                tbl_end_col = tbl.range.columns.count + tbl_start_col - 1

                for row_num in row_numbers:
                    sh.range(f"{row_num}:{row_num}").delete()

                last_data_row = sh.range((sh.cells.last_cell.row, tbl_start_col)).end("up").row
                new_bottom_row = max(header_row, int(last_data_row))
                new_table_range = sh.range(
                    (header_row, tbl_start_col),
                    (new_bottom_row, tbl_end_col),
                )
                tbl.resize(new_table_range)
                wb.save()
        if not fallback_to_openpyxl:
            wb.close()
            wb = None
            print(f"  Reconciled {len(row_numbers)} stale CRM row(s) in {out_wb.name}")
    finally:
        if wb is not None:
            _safe_close_xlwings_book(wb, context="reconcile-delete")
        _safe_quit_xlwings_app(app, context="reconcile-delete")
    if fallback_to_openpyxl:
        print(
            "  WARNING: Excel table access failed during reconcile delete; "
            "switching to openpyxl fallback."
        )
        if fallback_exc is not None:
            print(f"  WARNING: reconcile-delete xlwings table access detail: {fallback_exc}")
        deleted = delete_crm_rows_openpyxl(out_wb, sheet_name, table_name, row_numbers)
        print(f"  Reconciled {deleted} stale CRM row(s) in {out_wb.name} (openpyxl fallback)")
        return deleted
    return len(row_numbers)


def delete_crm_rows_openpyxl(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    row_numbers: List[int],
) -> int:
    """Delete CRM worksheet rows bottom-up via openpyxl and keep table bounds valid."""
    row_numbers = sorted({int(r) for r in row_numbers if int(r) > 0}, reverse=True)
    if not row_numbers:
        return 0

    preserved_package_parts = _snapshot_preserved_package_parts(out_wb)
    tmp_path = out_wb.with_name(f"{out_wb.stem}.reconcile_tmp{out_wb.suffix}")
    wb = load_workbook(filename=str(out_wb), read_only=False, data_only=False)
    try:
        sh = wb[sheet_name]
        table = _resolve_table(sh, table_name)
        header_row = table.ref and range_boundaries(table.ref)[1]
        tbl_start_col, _tbl_start_row, tbl_end_col, _tbl_end_row = _table_bounds(table)

        for row_num in row_numbers:
            sh.delete_rows(row_num, 1)

        last_data_row = header_row
        for row_num in range(int(sh.max_row or header_row), header_row, -1):
            if any(
                sh.cell(row=row_num, column=col_num).value not in (None, "")
                for col_num in range(tbl_start_col, tbl_end_col + 1)
            ):
                last_data_row = row_num
                break

        new_bottom_row = max(header_row + 1, int(last_data_row))
        table.ref = (
            f"{get_column_letter(tbl_start_col)}{header_row}:"
            f"{get_column_letter(tbl_end_col)}{new_bottom_row}"
        )
        wb.save(str(tmp_path))
    finally:
        wb.close()

    try:
        _restore_preserved_package_parts(tmp_path, preserved_package_parts)
        os.replace(str(tmp_path), str(out_wb))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    print(f"  Reconciled {len(row_numbers)} stale CRM row(s) in {out_wb.name} (openpyxl)")
    return len(row_numbers)


def backfill_append_date_my_sizes_openpyxl(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    append_date: date,
    resolved_my_size_by_key: Dict[str, str],
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Fill blank MY_SIZE cells for the append-date operational block."""
    if not resolved_my_size_by_key or append_date is None:
        return 0

    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=False)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        header_row = list(
            ws.iter_rows(min_row=start_row, max_row=start_row, min_col=start_col, max_col=end_col)
        )[0]
        header_to_col: Dict[str, int] = {}
        for i, cell in enumerate(header_row):
            header = str(cell.value or "").strip()
            if header:
                header_to_col[header] = start_col + i

        date_col = header_to_col.get("Date") or header_to_col.get("Дата поступления заказа")
        order_col = header_to_col.get("OrderID") or header_to_col.get("№ заказа")
        offer_col = header_to_col.get("KASPI_OFFER_NAME") or header_to_col.get("Название товара в Kaspi Магазине")
        article_col = header_to_col.get("Артикул") or header_to_col.get("SKU_ID_KSP")
        quantity_col = header_to_col.get("Quantity") or header_to_col.get("Количество")
        planned_col = header_to_col.get("PLANNED_SHIPPING_DATE") or header_to_col.get("Плановая дата передачи курьеру")
        my_size_col = header_to_col.get("MY_SIZE")
        if not all([date_col, order_col, offer_col, article_col, quantity_col, planned_col, my_size_col]):
            if verbose:
                print("  MY_SIZE backfill skipped: required columns not found")
            return 0

        updated = 0
        for row_num in range(start_row + 1, end_row + 1):
            row_date = parse_date(ws.cell(row=row_num, column=date_col).value)
            if row_date != append_date:
                continue
            current_size = _coerce_str(ws.cell(row=row_num, column=my_size_col).value)
            if current_size:
                continue

            order_id = clean_order_id(ws.cell(row=row_num, column=order_col).value)
            planned_date = parse_date(ws.cell(row=row_num, column=planned_col).value)
            offer_name = ws.cell(row=row_num, column=offer_col).value
            article = ws.cell(row=row_num, column=article_col).value
            quantity = ws.cell(row=row_num, column=quantity_col).value
            line_key = _build_line_dedupe_key(order_id, planned_date, offer_name, article, quantity)
            resolved_size = str(resolved_my_size_by_key.get(line_key) or "").strip()
            if not resolved_size:
                continue
            updated += 1
            if not dry_run:
                ws.cell(row=row_num, column=my_size_col, value=resolved_size)

        if updated and not dry_run:
            wb.save(str(crm_path))
        if verbose and updated:
            print(f"   MY_SIZE backfill rows updated: {updated}")
        return updated
    finally:
        wb.close()


def apply_fixed_values_backfill_xlwings(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    days: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Backfill fixed-value columns for recent rows to reduce formula churn.
    """
    date_from, date_to = _resolve_backfill_window(days, date_from, date_to)
    if not date_from or not date_to:
        return 0
    _require_xlwings()

    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    updated = 0
    try:
        wb = _open_workbook_xlwings(app, crm_path, update_links=False, read_only=False)
        sh = wb.sheets[sheet_name]
        try:
            tbl = sh.tables[table_name]
        except KeyError:
            tables = list(sh.tables)
            if not tables:
                raise RuntimeError(f"No table found on sheet {sheet_name}")
            tbl = tables[0]

        table_range = tbl.range
        header_row = table_range.row
        start_col = table_range.column
        width = table_range.columns.count
        total_rows = table_range.rows.count
        if total_rows <= 1:
            wb.close()
            return 0

        headers = sh.range((header_row, start_col), (header_row, start_col + width - 1)).value
        header_to_col = {
            str(name).strip(): start_col + i
            for i, name in enumerate(headers or [])
            if str(name or "").strip()
        }
        row_start = header_row + 1
        row_end = header_row + total_rows - 1

        date_col = header_to_col.get("Date")
        if not date_col:
            wb.close()
            return 0

        raw_headers = [
            "Склад передачи КД",
            "Артикул",
            "Название товара в Kaspi Магазине",
            "Название в системе продавца",
            "Количество",
            "Сумма",
            "Стоимость доставки для продавца",
            "Плановая дата передачи курьеру",
            "KASPI_OFFER_NAME",
            "SKU_key",
            "MY_SIZE",
            "Product_Type",
        ]

        n_rows = row_end - row_start + 1
        date_values = _coerce_column_values(
            sh.range((row_start, date_col), (row_end, date_col)).value,
            n_rows,
        )

        raw_col_values: Dict[str, List[Any]] = {}
        for key in raw_headers:
            col_num = header_to_col.get(key)
            if not col_num:
                raw_col_values[key] = [None] * n_rows
                continue
            raw_col_values[key] = _coerce_column_values(
                sh.range((row_start, col_num), (row_end, col_num)).value,
                n_rows,
            )

        target_rows: List[Tuple[int, Dict[str, Any]]] = []
        for offset in range(n_rows):
            row_num = row_start + offset
            row_date = parse_date(date_values[offset])
            if not _row_in_backfill_window(row_date, date_from, date_to):
                continue
            raw_row = {}
            for key in raw_headers:
                raw_row[key] = raw_col_values[key][offset]
            target_rows.append((row_num, raw_row))

        if not target_rows:
            wb.close()
            return 0

        articles = [str(raw.get("Артикул") or raw.get("SKU_ID_KSP") or "").strip() for _, raw in target_rows]
        article_identity = _load_article_identity_for_articles(articles)

        sku_keys: List[str] = []
        for _, raw in target_rows:
            identity = _derive_identity_from_raw_row(
                raw,
                article_identity_by_article=article_identity,
            )
            if identity.get("sku_key"):
                sku_keys.append(str(identity["sku_key"]))
        sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys(sku_keys)

        fixed_by_row: Dict[int, Dict[str, Any]] = {}
        for row_num, raw in target_rows:
            fixed_by_row[row_num] = compute_fixed_value_columns(
                raw,
                sku_meta,
                kaspi_core,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
            updated += 1

        if not dry_run:
            original_calc = app.calculation
            try:
                app.calculation = "manual"
            except Exception:
                original_calc = None

            row_numbers = sorted(fixed_by_row.keys())
            row_ranges = _iter_consecutive_ranges(row_numbers)
            for col_name in FIXED_BACKFILL_COLUMNS:
                if col_name in PROTECTED_HUMAN_COLUMNS:
                    continue
                col_num = header_to_col.get(col_name)
                if not col_num:
                    continue
                for start_row, end_row in row_ranges:
                    values = []
                    for row_num in range(start_row, end_row + 1):
                        value = fixed_by_row[row_num].get(col_name)
                        values.append([value if value is not None else ""])
                    sh.range((start_row, col_num), (end_row, col_num)).value = values

            if original_calc is not None:
                app.calculation = original_calc

        if not dry_run:
            wb.save()
        wb.close()
        if verbose:
            mode = "DRY RUN" if dry_run else "APPLY"
            print(f"  Fixed-value backfill ({mode}): {updated} rows ({date_from}..{date_to})")
    finally:
        _safe_quit_xlwings_app(app, context="fixed-values backfill")

    return updated


def apply_fixed_values_backfill_openpyxl(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    days: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Openpyxl fallback for fixed-value backfill when xlwings/Excel automation is unavailable.
    """
    date_from, date_to = _resolve_backfill_window(days, date_from, date_to)
    if not date_from or not date_to:
        return 0

    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=False)
    updated = 0
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)
        if end_row <= start_row:
            return 0

        headers = [
            ws.cell(row=start_row, column=c).value
            for c in range(start_col, end_col + 1)
        ]
        header_to_col = {
            str(name).strip(): start_col + i
            for i, name in enumerate(headers or [])
            if str(name or "").strip()
        }
        date_col = header_to_col.get("Date")
        if not date_col:
            return 0

        raw_headers = [
            "Склад передачи КД",
            "Артикул",
            "Название товара в Kaspi Магазине",
            "Название в системе продавца",
            "Количество",
            "Сумма",
            "Стоимость доставки для продавца",
            "Плановая дата передачи курьеру",
            "KASPI_OFFER_NAME",
            "SKU_key",
            "MY_SIZE",
            "Product_Type",
        ]

        target_rows: List[Tuple[int, Dict[str, Any]]] = []
        for row_num in range(start_row + 1, end_row + 1):
            row_date = parse_date(ws.cell(row=row_num, column=date_col).value)
            if not _row_in_backfill_window(row_date, date_from, date_to):
                continue
            raw_row: Dict[str, Any] = {}
            for key in raw_headers:
                col_num = header_to_col.get(key)
                raw_row[key] = ws.cell(row=row_num, column=col_num).value if col_num else None
            target_rows.append((row_num, raw_row))

        if not target_rows:
            return 0

        articles = [str(raw.get("Артикул") or raw.get("SKU_ID_KSP") or "").strip() for _, raw in target_rows]
        article_identity = _load_article_identity_for_articles(articles)

        sku_keys: List[str] = []
        for _, raw in target_rows:
            identity = _derive_identity_from_raw_row(
                raw,
                article_identity_by_article=article_identity,
            )
            if identity.get("sku_key"):
                sku_keys.append(str(identity["sku_key"]))
        sku_meta, kaspi_core, valid_sku_keys = _load_sku_meta_for_keys(sku_keys)

        fixed_by_row: Dict[int, Dict[str, Any]] = {}
        for row_num, raw in target_rows:
            fixed_by_row[row_num] = compute_fixed_value_columns(
                raw,
                sku_meta,
                kaspi_core,
                article_identity_by_article=article_identity,
                valid_sku_keys=valid_sku_keys,
            )
            updated += 1

        if not dry_run:
            for row_num, fixed in fixed_by_row.items():
                for col_name in FIXED_BACKFILL_COLUMNS:
                    if col_name in PROTECTED_HUMAN_COLUMNS:
                        continue
                    col_num = header_to_col.get(col_name)
                    if not col_num:
                        continue
                    value = fixed.get(col_name)
                    ws.cell(row=row_num, column=col_num).value = value if value is not None else ""
            wb.save(str(crm_path))
        if verbose:
            mode = "DRY RUN" if dry_run else "APPLY"
            print(f"  Fixed-value backfill ({mode}, openpyxl): {updated} rows ({date_from}..{date_to})")
        return updated
    finally:
        wb.close()


def _coerce_column_values(values: Any, n_rows: int) -> List[Any]:
    """Normalize xlwings single-column reads to a list of exactly n_rows."""
    if isinstance(values, list):
        out = list(values)
    else:
        out = [values]
    if len(out) < n_rows:
        out.extend([None] * (n_rows - len(out)))
    return out[:n_rows]


def _iter_consecutive_ranges(rows: List[int]) -> List[Tuple[int, int]]:
    """Return inclusive (start, end) ranges for sorted row numbers."""
    if not rows:
        return []
    ranges: List[Tuple[int, int]] = []
    start = rows[0]
    end = rows[0]
    for value in rows[1:]:
        if value == end + 1:
            end = value
            continue
        ranges.append((start, end))
        start = value
        end = value
    ranges.append((start, end))
    return ranges


# ---------- Archive Source Files ----------

def archive_run(orders_dir: Path, source_files: List[Path], df_filt: pd.DataFrame) -> Path:
    """Archive source files and create log."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = orders_dir / "archive_orders"
    archive_root.mkdir(parents=True, exist_ok=True)
    
    run_dir = archive_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy source files so the canonical ActiveOrders.xlsx stays available for
    # late-arrival top-up and final health gates in the wrapper workflow.
    for src in source_files:
        dest = run_dir / src.name
        try:
            shutil.copy2(src, dest)
            print(f"  Archived: {src.name}")
        except Exception as e:
            print(f"  WARN: could not archive {src.name}: {e}")
    
    # Create log CSV
    colmap = map_headers(df_filt)
    log_cols = []
    for key in ("order_id", "handover", "warehouse", "status"):
        if key in colmap:
            log_cols.append(colmap[key])
    
    if "__source_file__" in df_filt.columns:
        log_cols.append("__source_file__")
    
    if log_cols:
        df_log = df_filt[log_cols].copy()
        rename_map = {colmap[k]: k for k in colmap if colmap[k] in log_cols}
        df_log = df_log.rename(columns=rename_map)
        
        log_path = run_dir / "appended_orders.csv"
        df_log.to_csv(log_path, index=False)
    
    return run_dir


def sync_pending_orders_to_gdrive_safe(
    crm_path: Path,
    target_date: date,
    dry_run: bool = False,
) -> dict:
    print("\n4. Syncing pending orders to Google Drive...")
    try:
        from scripts.sync_to_gdrive import sync_pending_orders_to_gdrive
        stats = sync_pending_orders_to_gdrive(
            crm_path=crm_path,
            target_date=target_date,
            status_value=READY_STATUS,
            dry_run=dry_run,
            validate=not dry_run,
        )
        print(f"   Google Drive sync: {stats['rows_synced']} rows synced")
        return stats
    except Exception as e:
        print(f"   WARNING: Google Drive sync failed: {e}")
        return {"rows_synced": 0, "dry_run": dry_run, "error": str(e)}


def _finalize_result_status(result: dict) -> dict:
    if result.get("status"):
        result.setdefault("retryable_topup", result["status"] in {"success", "noop"})
        return result

    changed = any(
        int(result.get(key, 0) or 0) > 0
        for key in (
            "orders_imported",
            "orders_updated",
            "carryforward_rows_appended",
            "crm_rows_reconciled_deleted",
        )
    )
    result["status"] = "success" if changed else "noop"
    result["retryable_topup"] = result["status"] in {"success", "noop"}
    return result


def _classify_import_failure(exc: Exception) -> Tuple[str, bool]:
    if isinstance(exc, ExcelTargetConflictError):
        return ("preflight_blocked", False)
    if isinstance(exc, AppendVerificationError):
        return ("append_verification_failed", False)
    msg = str(exc or "")
    if "Append integrity check failed" in msg or "CRM semantic append verification failed" in msg:
        return ("append_verification_failed", False)
    return ("write_failed", False)


def write_import_summary(result: dict, summary_path: Path) -> None:
    """Write a small JSON summary for downstream no-op detection."""
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    finalized = _finalize_result_status(dict(result))
    payload = {
        "orders_imported": int(finalized.get("orders_imported", 0) or 0),
        "orders_updated": int(finalized.get("orders_updated", 0) or 0),
        "orders_filtered": int(finalized.get("orders_filtered", 0) or 0),
        "status": str(finalized.get("status") or "unknown"),
        "retryable_topup": bool(finalized.get("retryable_topup", False)),
        "error": str(finalized.get("error") or ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- CLI ----------

_UNSET = object()


def main(
    orders_dir=_UNSET,
    crm_path=_UNSET,
    sheet_name=_UNSET,
    table_name=_UNSET,
    date_end=_UNSET,
    append_date=_UNSET,
    include_overdue=_UNSET,
    overdue_lookback_days=_UNSET,
    status=_UNSET,
    dry_run=_UNSET,
    verbose=_UNSET,
    update_existing=_UNSET,
    no_update=_UNSET,
    fixed_values=_UNSET,
    kaspi_core_override=_UNSET,
    backfill_fixed_days=_UNSET,
    fixed_backfill_from=_UNSET,
    fixed_backfill_to=_UNSET,
    fixed_values_scope=_UNSET,
    skip_fixed_backfill=_UNSET,
    refresh_delivery_fees=_UNSET,
    refresh_fees_from=_UNSET,
    refresh_fees_to=_UNSET,
    strict_excel=_UNSET,
    transactional=_UNSET,
    openpyxl_append_fallback=_UNSET,
    prefer_xlwings_append=_UNSET,
    append_integrity_check=_UNSET,
    allow_large_reconcile_delete=_UNSET,
    repair_cf_ranges=_UNSET,
    gdrive_sync=_UNSET,
    enforce_crm_path=_UNSET,
    candidate_dir=_UNSET,
    failed_candidate_dir=_UNSET,
    excel_session_preflight_only=_UNSET,
    summary_file=_UNSET,
):
    parser = argparse.ArgumentParser(
        description="Import Kaspi ActiveOrders to CRM (xlwings, Excel-safe)"
    )
    parser.add_argument(
        "--orders-dir",
        type=Path,
        default=data_path("excel_ui", "ActiveOrders"),
        help="Directory containing ActiveOrders*.xlsx",
    )
    parser.add_argument(
        "--crm-file",
        type=Path,
        default=data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx"),
        help="CRM Excel file",
    )
    parser.add_argument(
        "--sheet", 
        default="SALES_KSP_CRM_1",
        help="CRM sheet name"
    )
    parser.add_argument(
        "--table", 
        default="tb_SalesRaw",
        help="CRM table name"
    )
    parser.add_argument(
        "--date-end",
        default="today",
        help="Exact planned delivery date to filter (today, tomorrow, or YYYY-MM-DD)"
    )
    parser.add_argument(
        "--append-date", 
        default="today",
        help="Date to stamp into CRM Date column"
    )
    parser.add_argument(
        "--include-overdue",
        action="store_true",
        help="Include overdue planned dates (<= --date-end) within --overdue-lookback-days window.",
    )
    parser.add_argument(
        "--overdue-lookback-days",
        type=int,
        default=5,
        help="Lookback window (days) for --include-overdue mode (default: 5).",
    )
    parser.add_argument(
        "--status", 
        default=DEFAULT_STATUS,
        help="Status filter"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Preview only, don't write to Excel"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        default=True,
        help="Update status columns for existing orders (default: True)"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip updating existing orders (only append new)"
    )
    parser.add_argument(
        "--fixed-values",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write fixed values for trivial formula columns on appended rows (default: off)",
    )
    parser.add_argument(
        "--kaspi-core-override",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Deprecated/no-op. CRM table formulas own Kaspi_name_core.",
    )
    parser.add_argument(
        "--backfill-fixed-days",
        type=int,
        default=14,
        help="Recompute fixed values for recent rows (default: 14 days)",
    )
    parser.add_argument(
        "--fixed-backfill-from",
        default=None,
        help="Explicit backfill window start date (YYYY-MM-DD, today, yesterday)",
    )
    parser.add_argument(
        "--fixed-backfill-to",
        default=None,
        help="Explicit backfill window end date (YYYY-MM-DD, today, yesterday)",
    )
    parser.add_argument(
        "--skip-fixed-backfill",
        action="store_true",
        help="Skip recent fixed-value backfill pass",
    )
    parser.add_argument(
        "--fixed-values-scope",
        choices=["window", "new-only"],
        default="window",
        help="window: append + recent backfill, new-only: append only (default: window)",
    )
    parser.add_argument(
        "--refresh-delivery-fees",
        action="store_true",
        help="Backfill seller delivery fee from Delivery_fee_kzt for a date range"
    )
    parser.add_argument(
        "--refresh-fees-from",
        default=None,
        help="Backfill delivery fees from date (YYYY-MM-DD, today, yesterday)"
    )
    parser.add_argument(
        "--refresh-fees-to",
        default=None,
        help="Backfill delivery fees to date (YYYY-MM-DD, today, yesterday)"
    )
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=data_path("logs", "import_orders_to_crm_latest.json"),
        help="Write JSON summary to this path (default: logs/import_orders_to_crm_latest.json)",
    )
    parser.add_argument(
        "--strict-excel",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run strict Excel automation preflight and abort if unavailable (default: on).",
    )
    parser.add_argument(
        "--transactional",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write via candidate workbook and promote only after verification (default: on).",
    )
    parser.add_argument(
        "--openpyxl-append-fallback",
        action=argparse.BooleanOptionalAction,
        default=_default_openpyxl_append_fallback_enabled(),
        help="Allow openpyxl append fallback when xlwings append is unavailable (default: off).",
    )
    parser.add_argument(
        "--prefer-xlwings-append",
        action=argparse.BooleanOptionalAction,
        default=_default_prefer_xlwings_append(),
        help="Try xlwings append first before openpyxl fallback (default: on).",
    )
    parser.add_argument(
        "--append-integrity-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Verify appended rows (formulas/styles/CF coverage) before promotion (default: on).",
    )
    parser.add_argument(
        "--allow-large-reconcile-delete",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Allow large stale-row deletes from the append-date CRM block (default: off/fail-closed).",
    )
    parser.add_argument(
        "--repair-cf-ranges",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Normalize conditional-formatting row ranges to current table end during append (default: on).",
    )
    parser.add_argument(
        "--gdrive-sync",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sync pending rows to Google Drive at end of import (default: on).",
    )
    parser.add_argument(
        "--enforce-crm-path",
        type=Path,
        default=None,
        help="Fail if --crm-file does not exactly match this canonical workbook path.",
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=None,
        help="Directory for transactional candidate workbooks. Defaults beside the target workbook.",
    )
    parser.add_argument(
        "--failed-candidate-dir",
        type=Path,
        default=None,
        help="Directory for failed transactional candidates. Defaults beside the target workbook.",
    )
    parser.add_argument(
        "--excel-session-preflight-only",
        action="store_true",
        help="Check Excel session safety only, then exit without reading ActiveOrders or writing CRM.",
    )

    if (
        orders_dir is _UNSET
        and crm_path is _UNSET
        and sheet_name is _UNSET
        and table_name is _UNSET
        and date_end is _UNSET
        and append_date is _UNSET
        and include_overdue is _UNSET
        and overdue_lookback_days is _UNSET
        and status is _UNSET
        and dry_run is _UNSET
        and verbose is _UNSET
        and update_existing is _UNSET
        and no_update is _UNSET
        and fixed_values is _UNSET
        and kaspi_core_override is _UNSET
        and backfill_fixed_days is _UNSET
        and fixed_backfill_from is _UNSET
        and fixed_backfill_to is _UNSET
        and fixed_values_scope is _UNSET
        and skip_fixed_backfill is _UNSET
        and refresh_delivery_fees is _UNSET
        and refresh_fees_from is _UNSET
        and refresh_fees_to is _UNSET
        and strict_excel is _UNSET
        and transactional is _UNSET
        and openpyxl_append_fallback is _UNSET
        and prefer_xlwings_append is _UNSET
        and append_integrity_check is _UNSET
        and allow_large_reconcile_delete is _UNSET
        and repair_cf_ranges is _UNSET
        and gdrive_sync is _UNSET
        and enforce_crm_path is _UNSET
        and candidate_dir is _UNSET
        and failed_candidate_dir is _UNSET
        and excel_session_preflight_only is _UNSET
        and summary_file is _UNSET
    ):
        args = parser.parse_args()
    else:
        args = parser.parse_args([])
        if orders_dir is not _UNSET:
            args.orders_dir = Path(orders_dir)
        if crm_path is not _UNSET:
            args.crm_file = Path(crm_path)
        if sheet_name is not _UNSET:
            args.sheet = sheet_name
        if table_name is not _UNSET:
            args.table = table_name
        if date_end is not _UNSET:
            args.date_end = date_end
        if append_date is not _UNSET:
            args.append_date = append_date
        if include_overdue is not _UNSET:
            args.include_overdue = bool(include_overdue)
        if overdue_lookback_days is not _UNSET:
            args.overdue_lookback_days = int(overdue_lookback_days)
        if status is not _UNSET:
            args.status = status
        if dry_run is not _UNSET:
            args.dry_run = bool(dry_run)
        if verbose is not _UNSET:
            args.verbose = bool(verbose)
        if update_existing is not _UNSET:
            args.update_existing = bool(update_existing)
        if no_update is not _UNSET:
            args.no_update = bool(no_update)
        if fixed_values is not _UNSET:
            args.fixed_values = bool(fixed_values)
        if kaspi_core_override is not _UNSET:
            args.kaspi_core_override = bool(kaspi_core_override)
        if backfill_fixed_days is not _UNSET:
            args.backfill_fixed_days = int(backfill_fixed_days)
        if fixed_backfill_from is not _UNSET:
            args.fixed_backfill_from = fixed_backfill_from
        if fixed_backfill_to is not _UNSET:
            args.fixed_backfill_to = fixed_backfill_to
        if fixed_values_scope is not _UNSET:
            args.fixed_values_scope = fixed_values_scope
        if skip_fixed_backfill is not _UNSET:
            args.skip_fixed_backfill = bool(skip_fixed_backfill)
        if refresh_delivery_fees is not _UNSET:
            args.refresh_delivery_fees = bool(refresh_delivery_fees)
        if refresh_fees_from is not _UNSET:
            args.refresh_fees_from = refresh_fees_from
        if refresh_fees_to is not _UNSET:
            args.refresh_fees_to = refresh_fees_to
        if strict_excel is not _UNSET:
            args.strict_excel = bool(strict_excel)
        if transactional is not _UNSET:
            args.transactional = bool(transactional)
        if openpyxl_append_fallback is not _UNSET:
            args.openpyxl_append_fallback = bool(openpyxl_append_fallback)
        if prefer_xlwings_append is not _UNSET:
            args.prefer_xlwings_append = bool(prefer_xlwings_append)
        if append_integrity_check is not _UNSET:
            args.append_integrity_check = bool(append_integrity_check)
        if allow_large_reconcile_delete is not _UNSET:
            args.allow_large_reconcile_delete = bool(allow_large_reconcile_delete)
        if repair_cf_ranges is not _UNSET:
            args.repair_cf_ranges = bool(repair_cf_ranges)
        if gdrive_sync is not _UNSET:
            args.gdrive_sync = bool(gdrive_sync)
        if enforce_crm_path is not _UNSET:
            args.enforce_crm_path = Path(enforce_crm_path) if enforce_crm_path else None
        if candidate_dir is not _UNSET:
            args.candidate_dir = Path(candidate_dir)
        if failed_candidate_dir is not _UNSET:
            args.failed_candidate_dir = Path(failed_candidate_dir)
        if args.candidate_dir is None or args.failed_candidate_dir is None:
            default_candidate_dir, default_failed_candidate_dir = _default_candidate_dirs_for_workbook(
                Path(args.crm_file)
            )
            if args.candidate_dir is None:
                args.candidate_dir = default_candidate_dir
            if args.failed_candidate_dir is None:
                args.failed_candidate_dir = default_failed_candidate_dir
        if excel_session_preflight_only is not _UNSET:
            args.excel_session_preflight_only = bool(excel_session_preflight_only)
        if summary_file is not _UNSET:
            args.summary_file = Path(summary_file)

    args.crm_file = Path(args.crm_file).expanduser().resolve()
    if args.candidate_dir is None or args.failed_candidate_dir is None:
        default_candidate_dir, default_failed_candidate_dir = _default_candidate_dirs_for_workbook(
            args.crm_file
        )
        if args.candidate_dir is None:
            args.candidate_dir = default_candidate_dir
        if args.failed_candidate_dir is None:
            args.failed_candidate_dir = default_failed_candidate_dir
    args.candidate_dir = Path(args.candidate_dir).expanduser()
    args.failed_candidate_dir = Path(args.failed_candidate_dir).expanduser()
    canonical_crm_path = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx").expanduser().resolve()
    enforced_crm_path = (
        Path(args.enforce_crm_path).expanduser().resolve()
        if getattr(args, "enforce_crm_path", None)
        else None
    )
    if enforced_crm_path and args.crm_file != enforced_crm_path:
        raise RuntimeError(
            "CRM path enforcement failed. "
            f"--crm-file resolved to {args.crm_file}, expected {enforced_crm_path}."
        )
    if getattr(args, "excel_session_preflight_only", False):
        print("=" * 60)
        print("  Excel Session Preflight")
        print("=" * 60)
        print(f"  CRM file: {args.crm_file}")
        blocked_paths = [args.crm_file]
        if _use_transactional_candidate_workbook(bool(getattr(args, "transactional", True))):
            blocked_paths.append(_candidate_workbook_path(args.crm_file, Path(args.candidate_dir)))
        _excel_session_preflight(args.crm_file, blocked_paths=blocked_paths, verbose=bool(args.verbose))
        print("  Excel session preflight OK")
        return {"excel_session_preflight": "ok"}

    result = {
        "orders_imported": 0,
        "orders_updated": 0,
        "orders_filtered": 0,
        "carryforward_rows_appended": 0,
    }
    backup_done = False
    summary_path = Path(args.summary_file) if getattr(args, "summary_file", None) else None
    candidate_state: Dict[str, Optional[Path]] = {"path": None}

    def finalize(outcome: dict) -> dict:
        finalized = _finalize_result_status(dict(outcome))
        if summary_path:
            write_import_summary(finalized, summary_path)
        return finalized

    def ensure_backup() -> None:
        nonlocal backup_done
        if args.dry_run or backup_done:
            return
        backup_path = backup_crm(args.crm_file)
        print(f"  Backup created: {backup_path.name}")
        backup_done = True

    def write_crm_path() -> Path:
        if args.dry_run:
            return args.crm_file
        ensure_backup()
        if not _use_transactional_candidate_workbook(bool(getattr(args, "transactional", True))):
            return args.crm_file
        candidate = candidate_state.get("path")
        if candidate is None:
            candidate = _prepare_candidate_workbook(
                source_path=args.crm_file,
                candidate_dir=Path(args.candidate_dir),
                verbose=bool(args.verbose),
            )
            candidate_state["path"] = candidate
        return candidate

    def load_current_snapshot_for_backfills() -> CRMSnapshot:
        return load_crm_snapshot(
            write_crm_path(),
            args.sheet,
            args.table,
            append_date=append_date,
        )

    def finalize_candidate_if_needed() -> None:
        candidate = candidate_state.get("path")
        if candidate is None:
            return
        _promote_candidate_workbook(
            source_path=args.crm_file,
            candidate_path=candidate,
            failed_dir=Path(args.failed_candidate_dir),
            strict_excel=bool(getattr(args, "strict_excel", True)),
            verbose=bool(args.verbose),
        )
        candidate_state["path"] = None

    def maybe_run_fixed_backfill() -> int:
        if not args.fixed_values:
            return 0
        if args.skip_fixed_backfill:
            return 0
        if str(getattr(args, "fixed_values_scope", "window")) == "new-only":
            return 0
        explicit_from = _resolve_refresh_date(getattr(args, "fixed_backfill_from", None), today_local()) if getattr(args, "fixed_backfill_from", None) else None
        explicit_to = _resolve_refresh_date(getattr(args, "fixed_backfill_to", None), today_local()) if getattr(args, "fixed_backfill_to", None) else None
        if int(args.backfill_fixed_days or 0) <= 0 and not (explicit_from or explicit_to):
            return 0
        target_path = write_crm_path()
        prefer_openpyxl_backfill = _prefer_openpyxl_safe_write_path()
        if xlwings_write_available and not prefer_openpyxl_backfill:
            try:
                return apply_fixed_values_backfill_xlwings(
                    crm_path=target_path,
                    sheet_name=args.sheet,
                    table_name=args.table,
                    days=max(int(args.backfill_fixed_days or 0), 0),
                    date_from=explicit_from,
                    date_to=explicit_to,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                )
            except Exception as exc:
                print(f"  WARNING: xlwings fixed-value backfill failed ({exc})")
                if args.verbose:
                    import traceback

                    traceback.print_exc()
                if not _allow_openpyxl_backfill_fallback():
                    print(
                        "  WARNING: openpyxl fallback is disabled "
                        "(set CRM_FIXED_BACKFILL_OPENPYXL_FALLBACK=1 to enable)."
                    )
                    print("  WARNING: skipping fixed-value backfill to protect workbook structure.")
                    return 0
                print("  WARNING: using openpyxl fallback for fixed-value backfill.")
        return apply_fixed_values_backfill_openpyxl(
            crm_path=target_path,
            sheet_name=args.sheet,
            table_name=args.table,
            days=max(int(args.backfill_fixed_days or 0), 0),
            date_from=explicit_from,
            date_to=explicit_to,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    
    # Parse dates
    if args.date_end.lower() == "today":
        end_date = today_local()
    elif args.date_end.lower() == "tomorrow":
        end_date = today_local() + timedelta(days=1)
    else:
        end_date = dtp.parse(args.date_end).date()
    
    if args.append_date.lower() == "today":
        append_date = today_local()
    else:
        append_date = dtp.parse(args.append_date).date()
    
    print("=" * 60)
    print("  Kaspi Order Import (xlwings)")
    print("=" * 60)
    print(f"  Data root: {get_data_root()}")
    print(f"  Orders dir: {args.orders_dir}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  CRM file fingerprint: {_file_fingerprint(args.crm_file)}")
    if args.crm_file != canonical_crm_path:
        print(
            "  WARNING: --crm-file is not the canonical automation workbook "
            f"({canonical_crm_path})"
        )
    if args.include_overdue:
        min_date = end_date - timedelta(days=max(int(args.overdue_lookback_days), 0))
        print(
            f"  Date filter: {min_date} <= planned date <= {end_date} "
            f"(include-overdue, lookback={int(args.overdue_lookback_days)}d)"
        )
    else:
        print(f"  Date filter: == {end_date} (TODAY only)")
    print(f"  Append date: {append_date}")
    if (
        not args.dry_run
        and bool(getattr(args, "transactional", True))
        and not _use_transactional_candidate_workbook(True)
    ):
        print("  Write mode: backup-first live workbook (macOS Excel candidate prompt avoidance)")
    if args.verbose and args.fixed_values:
        print(f"  Fixed append columns: {', '.join(FIXED_APPEND_COLUMNS)}")
        print(f"  Fixed backfill columns: {', '.join(FIXED_BACKFILL_COLUMNS)}")
        print(f"  Protected columns (never overwritten): {', '.join(sorted(PROTECTED_HUMAN_COLUMNS))}")
        print(f"  Fixed values scope: {args.fixed_values_scope}")
    print()

    if not args.dry_run and zipfile.is_zipfile(args.crm_file):
        repaired, repair_backup = repair_missing_shared_strings_part(
            args.crm_file,
            backup_dir=args.crm_file.parent / "backups",
        )
        if repaired:
            backup_done = True
            if repair_backup:
                print(f"  SharedStrings repair backup: {repair_backup.name}")
            print("  Repaired missing xl/sharedStrings.xml in CRM workbook package.")

    # Read and filter
    df_all, source_files = read_active_orders(args.orders_dir)
    df_filt, stats = filter_for_shipping(
        df_all,
        args.status,
        None,
        end_date,
        include_overdue=bool(args.include_overdue),
        overdue_lookback_days=int(args.overdue_lookback_days),
    )

    print(f"\nFiltered: {stats['rows_in_files']} → {stats['rows_after_filters']} rows")
    order_summary = summarize_order_rows(df_filt)
    if order_summary:
        print(
            f"Orders vs rows: {order_summary['unique_orders']} unique orders "
            f"across {order_summary['rows']} rows"
        )
        if order_summary["multi_line_orders"] > 0:
            print(
                f"  Multi-line orders: {order_summary['multi_line_orders']} "
                f"(max lines/order: {order_summary['max_lines_per_order']})"
            )

    result["orders_filtered"] = int(stats.get("rows_after_filters", 0))
    if df_filt.empty:
        print("No orders match filters. Nothing to import.")
        return finalize(result)

    # Sort for CRM append order (Phase 12 Part 6 - Updated)
    # Order: Status → STORE_NAME → OrderID → Quantity → KASPI_OFFER_NAME → Date
    df_filt = sort_for_crm(df_filt)
    print(f"Sorted by: Status (cancelled first), STORE_NAME, OrderID, Quantity, KASPI_OFFER_NAME, Date")

    # Inspect CRM structure (single openpyxl snapshot)
    snapshot = load_crm_snapshot(args.crm_file, args.sheet, args.table, append_date=append_date)
    date_abs = snapshot.date_col
    phone_abs = snapshot.phone_col
    start_abs = snapshot.start_col
    end_abs = snapshot.end_col
    slice_headers = snapshot.slice_headers

    # Get existing order IDs for dedup
    existing_ids = snapshot.order_ids
    print(f"Existing orders in CRM: {len(existing_ids)}")

    seller_fee_overlay_count = overlay_missing_seller_delivery_fees_from_db(df_filt)
    if seller_fee_overlay_count:
        print(f"  Seller delivery fee rows enriched from DB: {seller_fee_overlay_count}")

    allow_openpyxl_append_fallback = bool(
        getattr(args, "openpyxl_append_fallback", _default_openpyxl_append_fallback_enabled())
        or _allow_openpyxl_append_fallback()
    )
    xlwings_write_available = True

    if not args.dry_run:
        try:
            _excel_automation_preflight(
                crm_path=args.crm_file,
                strict_excel=bool(getattr(args, "strict_excel", True)),
                verbose=bool(args.verbose),
                transactional=bool(getattr(args, "transactional", True)),
                candidate_dir=Path(args.candidate_dir),
                allow_open_probe_fallback=bool(getattr(args, "transactional", True)),
            )
        except Exception as exc:
            if not allow_openpyxl_append_fallback:
                raise
            xlwings_write_available = False
            print(
                "  WARNING: Excel automation preflight failed; "
                f"continuing with openpyxl append fallback ({exc})"
            )

    # Update existing orders' status columns (Phase 12 Part 7)
    update_existing = args.update_existing and not args.no_update
    updated_count = 0
    column_positions = None
    # Build update source: all orders for target planned date (not just READY)
    update_df = df_all
    update_colmap = map_headers(df_all)
    if "handover" in update_colmap:
        handover = df_all[update_colmap["handover"]].apply(parse_kz_date)
        update_df = df_all[handover.apply(lambda d: d is not None and d == end_date)].copy()

    if update_existing and len(existing_ids) > 0 and xlwings_write_available:
        print("\n3. Updating existing orders' status columns...")

        # Get order rows (order_id -> row number)
        order_rows = snapshot.order_rows

        # Find column positions for update columns
        column_positions = snapshot.column_positions
        if args.verbose:
            print(f"  Update column positions: {column_positions}")

        # Build update data from source DataFrame (all statuses for target date)
        colmap = map_headers(update_df)
        update_data = build_update_data(update_df, colmap)

        # Fetch status updates for CRM-pending orders missing from ActiveOrders export
        try:
            update_ids = set()
            order_col = colmap.get("order_id")
            if order_col:
                for v in update_df[order_col].tolist():
                    oid = clean_order_id(v)
                    if oid:
                        update_ids.add(oid)

            crm_pending = read_crm_pending_orders(args.crm_file, args.sheet, end_date)
            missing = [o for o in crm_pending if o.get("order_id") not in update_ids]

            if missing:
                print(f"  Missing {len(missing)} CRM pending orders in ActiveOrders; fetching API status...")
                api_updates = fetch_missing_status_updates(missing, verbose=args.verbose)
                for oid, data in api_updates.items():
                    if not data:
                        continue
                    if oid in update_data:
                        update_data[oid].update(data)
                    else:
                        update_data[oid] = data
        except Exception as e:
            print(f"  WARNING: could not fetch missing order statuses: {e}")

        # How many orders can be updated?
        orders_to_update = set(order_rows.keys()) & set(update_data.keys())
        print(f"  Orders with status updates: {len(orders_to_update)}")

        if orders_to_update:
            try:
                updated_count = update_existing_order_columns(
                    write_crm_path(),
                    args.sheet,
                    order_rows,
                    update_data,
                    column_positions,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                )
                print(f"  Updated {updated_count} existing orders")
                result["orders_updated"] = updated_count
            except Exception as exc:
                if not allow_openpyxl_append_fallback:
                    raise
                xlwings_write_available = False
                print(
                    "  WARNING: existing-order status updates failed; "
                    f"continuing with append-only path ({exc})"
                )
    else:
        if args.no_update:
            print("\n3. Skipping existing order updates (--no-update flag)")
        elif len(existing_ids) == 0:
            print("\n3. No existing orders to update")
        elif not xlwings_write_available:
            print("\n3. Skipping existing order updates (Excel automation unavailable)")

    # Build staging data (returns tuple: stage_block, phone_values)
    stage, phone_values = build_staging(df_filt, slice_headers)
    fixed_values_payload: Optional[List[Dict[str, Any]]] = None
    reconcile_delete_count = 0
    if args.fixed_values:
        fixed_values_payload = build_fixed_value_payload(df_filt)
    elif getattr(args, "kaspi_core_override", False):
        print("  NOTE: Kaspi_name_core override ignored; CRM table formulas own that column.")

    # Dedup against existing
    colmap = map_headers(df_filt)
    append_df = df_filt.copy()
    if "order_id" in colmap:
        if column_positions is None:
            column_positions = snapshot.column_positions
        existing_keys = snapshot.existing_keys
        existing_append_date_keys = snapshot.append_date_key_counts if snapshot.table_date_col else None
        df_filt, new_mask, dedupe_stats = build_pending_append_mask(
            df_filt,
            colmap=colmap,
            existing_keys=existing_keys,
            existing_append_date_keys=existing_append_date_keys,
            include_overdue=bool(args.include_overdue),
            append_date=append_date,
        )

        desired_keys = df_filt["_okey"].tolist() if "_okey" in df_filt.columns else []
        protected_rollover_count = 0
        if bool(args.include_overdue) and bool(args.no_update):
            augmented_desired_keys = augment_desired_keys_with_existing_rollovers(
                desired_keys,
                snapshot.append_date_rows,
                snapshot.existing_rollover_keys,
            )
            protected_rollover_count = max(len(augmented_desired_keys) - len(desired_keys), 0)
            desired_keys = augmented_desired_keys
        reconcile_plan = plan_append_date_reconcile(
            snapshot.append_date_rows,
            desired_keys=desired_keys,
        )
        reconcile_delete_count = len(reconcile_plan.delete_row_numbers)
        guard_reconcile_delete_volume(
            snapshot.append_date_rows,
            desired_keys,
            reconcile_plan.delete_row_numbers,
            append_date=append_date,
            allow_large_reconcile_delete=bool(getattr(args, "allow_large_reconcile_delete", False)),
        )
        if reconcile_delete_count > 0:
            print(
                f"CRM reconcile: deleting {reconcile_delete_count} stale/duplicate row(s) "
                f"from Date {append_date.isoformat()} before append"
            )
            if not args.dry_run:
                target_crm_path = write_crm_path()
                if xlwings_write_available:
                    delete_crm_rows_xlwings(
                        target_crm_path,
                        args.sheet,
                        args.table,
                        reconcile_plan.delete_row_numbers,
                    )
                else:
                    delete_crm_rows_openpyxl(
                        target_crm_path,
                        args.sheet,
                        args.table,
                        reconcile_plan.delete_row_numbers,
                    )
            result["crm_rows_reconciled_deleted"] = reconcile_delete_count
        elif protected_rollover_count > 0:
            print(
                f"CRM reconcile: preserving {protected_rollover_count} carry-forward row(s) "
                f"already imported for Date {append_date.isoformat()}"
            )

        # Filter stage and phone values to match
        indices_to_keep = df_filt[new_mask].index.tolist()
        append_df = df_filt[new_mask].copy()
        stage_filtered = [stage[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
        phone_filtered = [phone_values[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
        fixed_filtered = (
            [fixed_values_payload[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
            if fixed_values_payload is not None
            else None
        )

        dup_count = int(dedupe_stats.get("duplicates_skipped", 0))
        planned_dup_count = int(dedupe_stats.get("planned_duplicate_rows", 0))
        append_date_duplicate_count = int(dedupe_stats.get("append_date_duplicate_rows", 0))
        if planned_dup_count > 0:
            print(
                f"Skipped {planned_dup_count} duplicates "
                f"(same order_id + planned date already in CRM)"
            )
        if append_date_duplicate_count > 0:
            print(
                f"Skipped {append_date_duplicate_count} duplicates "
                f"(same order line already present in CRM Date {append_date.isoformat()})"
            )
        residual_dup_count = dup_count - planned_dup_count - append_date_duplicate_count
        if residual_dup_count > 0:
            print(f"Skipped {residual_dup_count} duplicates (same order line already in CRM)")
        carryforward_rows = int(dedupe_stats.get("carryforward_rows_to_append", 0))
        if carryforward_rows > 0:
            print(
                f"Overdue pending rows to append: {carryforward_rows} "
                f"(still pending from previous planned dates, carried to CRM Date {append_date.isoformat()})"
            )
            result["carryforward_rows_appended"] = carryforward_rows
            result["previous_day_rollover_rows_appended"] = carryforward_rows

        stage = stage_filtered
        phone_values = phone_filtered
        fixed_values_payload = fixed_filtered

    print(f"\n4. Appending new orders...")
    new_rows_added = len(stage)
    print(f"   Orders to append: {new_rows_added}")
    append_expectations = build_append_expectations(append_df, colmap=colmap) if new_rows_added > 0 else []

    if len(stage) == 0:
        if updated_count > 0 or reconcile_delete_count > 0:
            detail_bits = []
            if updated_count > 0:
                detail_bits.append(f"updated {updated_count} existing orders")
            if reconcile_delete_count > 0:
                detail_bits.append(f"reconciled {reconcile_delete_count} stale today row(s)")
            print(f"   No new orders to append ({'; '.join(detail_bits)})")
            if args.refresh_delivery_fees:
                fee_target_path = write_crm_path()
                prefer_openpyxl_fee = (not xlwings_write_available) or _prefer_openpyxl_safe_write_path()
                refresh_from = _resolve_refresh_date(args.refresh_fees_from, today_local() - timedelta(days=1))
                refresh_to = _resolve_refresh_date(args.refresh_fees_to, today_local())
                try:
                    fee_snapshot = load_current_snapshot_for_backfills()
                    backfilled = backfill_seller_delivery_fee(
                        fee_target_path,
                        args.sheet,
                        args.table,
                        refresh_from,
                        refresh_to,
                        dry_run=args.dry_run,
                        verbose=args.verbose,
                        snapshot=fee_snapshot,
                        prefer_openpyxl=prefer_openpyxl_fee,
                    )
                    print(f"   Delivery fee backfill rows updated: {backfilled}")
                except Exception as exc:
                    if not allow_openpyxl_append_fallback or prefer_openpyxl_fee:
                        raise
                    print(f"   WARNING: delivery fee backfill failed ({exc}); continuing.")
            fixed_backfilled = maybe_run_fixed_backfill()
            if fixed_backfilled:
                print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")
            finalize_candidate_if_needed()
            if bool(getattr(args, "gdrive_sync", True)):
                sync_pending_orders_to_gdrive_safe(args.crm_file, end_date, args.dry_run)
            else:
                print("   Google Drive sync skipped (--no-gdrive-sync).")
            print(
                f"\n✅ Import complete! Updated {updated_count} orders, "
                f"reconciled {reconcile_delete_count} stale today rows, appended 0 new."
            )
            return finalize(result)
        else:
            print("   All orders already in CRM. Nothing to import or update.")
            print("   NO-OP: skipping Google Drive sync.")
            if args.refresh_delivery_fees:
                fee_target_path = write_crm_path()
                prefer_openpyxl_fee = (not xlwings_write_available) or _prefer_openpyxl_safe_write_path()
                refresh_from = _resolve_refresh_date(args.refresh_fees_from, today_local() - timedelta(days=1))
                refresh_to = _resolve_refresh_date(args.refresh_fees_to, today_local())
                try:
                    fee_snapshot = load_current_snapshot_for_backfills()
                    backfilled = backfill_seller_delivery_fee(
                        fee_target_path,
                        args.sheet,
                        args.table,
                        refresh_from,
                        refresh_to,
                        dry_run=args.dry_run,
                        verbose=args.verbose,
                        snapshot=fee_snapshot,
                        prefer_openpyxl=prefer_openpyxl_fee,
                    )
                    print(f"   Delivery fee backfill rows updated: {backfilled}")
                except Exception as exc:
                    if not allow_openpyxl_append_fallback or prefer_openpyxl_fee:
                        raise
                    print(f"   WARNING: delivery fee backfill failed ({exc}); continuing.")
            fixed_backfilled = maybe_run_fixed_backfill()
            if fixed_backfilled:
                print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")
            finalize_candidate_if_needed()
            return finalize(result)

    if args.dry_run:
        print("\n[DRY RUN] Would append but skipping.")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return finalize(result)

    # Append via xlwings with openpyxl fallback (if enabled).
    target_crm_path = write_crm_path()
    prefer_xlwings_append = (
        bool(getattr(args, "prefer_xlwings_append", _default_prefer_xlwings_append()))
        and xlwings_write_available
    )
    append_start_row, append_end_row = append_orders_with_fallback(
        target_crm_path,
        args.sheet,
        args.table,
        date_abs,
        phone_abs,
        start_abs,
        end_abs,
        stage,
        phone_values,
        append_date,
        slice_headers,
        fixed_values=fixed_values_payload,
        kaspi_name_core_values=None,
        preserved_my_sizes=None,
        allow_openpyxl_fallback=allow_openpyxl_append_fallback,
        prefer_xlwings=prefer_xlwings_append,
        repair_cf_ranges=bool(getattr(args, "repair_cf_ranges", True)),
        verbose=bool(args.verbose),
    )
    if bool(getattr(args, "append_integrity_check", True)):
        _verify_appended_rows_integrity(
            workbook_path=target_crm_path,
            sheet_name=args.sheet,
            table_name=args.table,
            start_row=append_start_row,
            end_row=append_end_row,
            verbose=bool(args.verbose),
        )
    missing_appended = verify_expected_append_rows(
        target_crm_path,
        args.sheet,
        args.table,
        append_date=append_date,
        expectations=append_expectations,
    )
    if missing_appended:
        missing_order_ids = [item.order_id for item in missing_appended if item.order_id]
        print(
            "   WARNING: CRM append readback is missing "
            f"{len(missing_appended)} expected row(s); retrying missing subset once."
        )
        if missing_order_ids:
            print(
                "   Missing order IDs after first append: "
                + ", ".join(missing_order_ids[:10])
                + (" ..." if len(missing_order_ids) > 10 else "")
            )

        missing_keys = Counter(item.line_key for item in missing_appended)
        append_df_retry = append_df.copy()
        append_df_retry["_retry_keep"] = False
        for idx, row in append_df_retry.iterrows():
            key = _coerce_str(row.get("_okey"))
            if not key or missing_keys.get(key, 0) <= 0:
                continue
            append_df_retry.at[idx, "_retry_keep"] = True
            missing_keys[key] -= 1

        retry_keep_mask = append_df_retry["_retry_keep"].astype(bool)
        retry_stage = [row for row, keep in zip(stage, retry_keep_mask.tolist()) if keep]
        retry_phone_values = [row for row, keep in zip(phone_values, retry_keep_mask.tolist()) if keep]
        retry_fixed_values = (
            [row for row, keep in zip(fixed_values_payload, retry_keep_mask.tolist()) if keep]
            if fixed_values_payload is not None
            else None
        )

        retry_start_row, retry_end_row = append_orders_with_fallback(
            target_crm_path,
            args.sheet,
            args.table,
            date_abs,
            phone_abs,
            start_abs,
            end_abs,
            retry_stage,
            retry_phone_values,
            append_date,
            slice_headers,
            fixed_values=retry_fixed_values,
            kaspi_name_core_values=None,
            preserved_my_sizes=None,
            allow_openpyxl_fallback=allow_openpyxl_append_fallback,
            prefer_xlwings=prefer_xlwings_append,
            repair_cf_ranges=bool(getattr(args, "repair_cf_ranges", True)),
            verbose=bool(args.verbose),
        )
        if bool(getattr(args, "append_integrity_check", True)):
            _verify_appended_rows_integrity(
                workbook_path=target_crm_path,
                sheet_name=args.sheet,
                table_name=args.table,
                start_row=retry_start_row,
                end_row=retry_end_row,
                verbose=bool(args.verbose),
            )

        missing_after_retry = verify_expected_append_rows(
            target_crm_path,
            args.sheet,
            args.table,
            append_date=append_date,
            expectations=append_expectations,
        )
        if missing_after_retry:
            missing_after_retry_ids = [item.order_id for item in missing_after_retry if item.order_id]
            raise AppendVerificationError(
                "CRM semantic append verification failed after retry. "
                "Missing order IDs: "
                + ", ".join(missing_after_retry_ids[:20])
            )
    fixed_backfilled = maybe_run_fixed_backfill()
    if fixed_backfilled:
        print(f"   Fixed-value backfill rows updated: {fixed_backfilled}")

    # Backfill seller delivery fee from Delivery_fee_kzt (if requested)
    if args.refresh_delivery_fees:
        fee_target_path = write_crm_path()
        prefer_openpyxl_fee = (not xlwings_write_available) or _prefer_openpyxl_safe_write_path()
        refresh_from = _resolve_refresh_date(args.refresh_fees_from, today_local() - timedelta(days=1))
        refresh_to = _resolve_refresh_date(args.refresh_fees_to, today_local())
        try:
            fee_snapshot = load_current_snapshot_for_backfills()
            backfilled = backfill_seller_delivery_fee(
                fee_target_path,
                args.sheet,
                args.table,
                refresh_from,
                refresh_to,
                dry_run=args.dry_run,
                verbose=args.verbose,
                snapshot=fee_snapshot,
                prefer_openpyxl=prefer_openpyxl_fee,
            )
            print(f"   Delivery fee backfill rows updated: {backfilled}")
        except Exception as exc:
            if not allow_openpyxl_append_fallback or prefer_openpyxl_fee:
                raise
            print(f"   WARNING: delivery fee backfill failed ({exc}); continuing.")

    finalize_candidate_if_needed()

    # Archive source files only after workbook promotion succeeded.
    archive_path = archive_run(args.orders_dir, source_files, df_filt)

    # Sync PENDING rows for target date to Google Drive (formatted copy)
    if bool(getattr(args, "gdrive_sync", True)):
        sync_pending_orders_to_gdrive_safe(args.crm_file, end_date, args.dry_run)
    else:
        print("   Google Drive sync skipped (--no-gdrive-sync).")

    print(f"\n✅ Import complete!")
    print(f"   Updated: {updated_count} existing orders")
    print(f"   Appended: {new_rows_added} new orders")
    if result.get("carryforward_rows_appended"):
        print(f"   Carry-forward overdue rows: {result['carryforward_rows_appended']}")
    print(f"   Archived: {archive_path}")
    result["orders_imported"] = new_rows_added
    result["orders_updated"] = updated_count

    # Phase 12 Part 6: Detailed statistics
    if new_rows_added > 0 and not args.dry_run:
        print("\n" + "=" * 60)
        print("  Import Statistics")
        print("=" * 60)

        # Get warehouse column for grouping
        colmap = map_headers(df_filt)
        if "warehouse" in colmap:
            store_counts = df_filt.groupby(colmap["warehouse"]).size()
            print("\n  Appended Orders by Store:")
            for store, count in sorted(store_counts.items()):
                print(f"    {store}: {count}")

        # Status summary
        if "status" in colmap:
            status_counts = df_filt.groupby(colmap["status"]).size()
            print("\n  Status Summary:")
            for status, count in sorted(status_counts.items()):
                print(f"    {status}: {count}")

        print(f"\n  Total Appended: {new_rows_added}")
        print(f"  Total in CRM (before): {len(existing_ids)}")
        print(f"  Total in CRM (after): {len(existing_ids) + new_rows_added}")
        print("=" * 60)

    return finalize(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            failure_status, retryable_topup = _classify_import_failure(exc)
            write_import_summary(
                {
                    "status": failure_status,
                    "retryable_topup": retryable_topup,
                    "error": str(exc),
                },
                data_path("logs", "import_orders_to_crm_latest.json"),
            )
        except Exception:
            pass
        raise
