#!/usr/bin/env python3
"""Build deterministic Kaspi UI archive pack (status-change-date capable)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import shutil
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WINDOW_DAYS = 90
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports"
DEFAULT_STORES = ["UNIVERSAL", "ACMEWEAR", "11KZ", "MELVIS", "STOREB"]

WAREHOUSE_STORE_MAP = {
    "30000001_PP1": "UNIVERSAL",
    "30137883_PP1": "ACMEWEAR",
    "30290083_PP1": "11KZ",
    "30362323_PP1": "MELVIS",
    "30000002_PP1": "STOREB",
    "30000002_PP2": "STOREB",
}
COMPLETED_STATUSES = {"ВЫДАН", "ЗАВЕРШЕН"}
REQUIRED_COLUMNS = {
    "№ заказа",
    "Дата поступления заказа",
    "Дата изменения статуса",
    "Статус",
    "Количество",
    "Сумма",
    "Склад передачи КД",
}


def plan_windows(since: date, until: date, window_days: int = WINDOW_DAYS) -> list[tuple[date, date]]:
    if until < since:
        raise RuntimeError("until must be >= since")
    if window_days <= 0:
        raise RuntimeError("window_days must be > 0")
    windows: list[tuple[date, date]] = []
    cursor = since
    while cursor <= until:
        end = min(cursor + timedelta(days=window_days - 1), until)
        windows.append((cursor, end))
        cursor = end + timedelta(days=1)
    return windows


def _parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_store(value: str) -> str:
    text = str(value or "").strip().upper()
    if text in DEFAULT_STORES:
        return text
    return WAREHOUSE_STORE_MAP.get(text, "")


def _resolve_pack_dir(output_root: Path, since: date, until: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_root / f"kaspi_archive_ui_history_{since.isoformat()}_to_{until.isoformat()}_{stamp}"


def _load_seed_frame(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise RuntimeError(f"{path}: missing required columns: {', '.join(missing)}")
    return df.fillna("")


def _build_from_seed_files(
    *,
    seed_files: list[Path],
    since: date,
    until: date,
    output_dir: Path,
    strict: bool,
    stores: list[str],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    windows = plan_windows(since, until, WINDOW_DAYS)

    rows_by_store: dict[str, list[dict[str, Any]]] = {store: [] for store in stores}
    input_manifest: list[dict[str, Any]] = []

    for file_path in seed_files:
        df = _load_seed_frame(file_path)
        warehouses = sorted({str(v).strip().upper() for v in df["Склад передачи КД"].tolist() if str(v).strip()})
        mapped = {_normalize_store(v) for v in warehouses if _normalize_store(v)}
        if len(mapped) != 1:
            raise RuntimeError(f"{file_path}: expected exactly one store mapping, got {sorted(mapped)} from warehouses={warehouses}")
        store_code = sorted(mapped)[0]

        raw_dir = output_dir / f"store_{store_code}" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_copy = raw_dir / file_path.name
        shutil.copy2(file_path, raw_copy)

        input_manifest.append(
            {
                "path": str(file_path.resolve()),
                "sha256": _sha256(file_path),
                "rows": int(len(df)),
                "store_code": store_code,
            }
        )

        for _, row in df.iterrows():
            created = _parse_date(str(row.get("Дата поступления заказа") or ""))
            if created is None:
                continue
            if created < since or created > until:
                continue
            row_dict = {col: str(row.get(col) or "") for col in df.columns}
            rows_by_store[store_code].append(row_dict)

    results: list[dict[str, Any]] = []
    for store_code in stores:
        store_dir = output_dir / f"store_{store_code}"
        store_dir.mkdir(parents=True, exist_ok=True)
        store_rows = rows_by_store.get(store_code, [])
        frame = pd.DataFrame(store_rows) if store_rows else pd.DataFrame(columns=sorted(REQUIRED_COLUMNS))
        frame.to_csv(
            store_dir / f"ArchiveOrders_{store_code}.csv",
            index=False,
            encoding="utf-8",
        )

        completed = frame["Статус"].astype(str).str.strip().str.upper().isin(COMPLETED_STATUSES) if not frame.empty else pd.Series(dtype=bool)
        missing_status = (
            completed
            & frame["Дата изменения статуса"].astype(str).str.strip().eq("")
            if not frame.empty
            else pd.Series(dtype=bool)
        )
        missing_count = int(missing_status.sum()) if not frame.empty else 0
        if strict and missing_count > 0:
            raise RuntimeError(
                f"store={store_code}: completed rows missing status-change date={missing_count}"
            )

        windows_rows = []
        for ws, we in windows:
            count = 0
            if not frame.empty:
                created = pd.to_datetime(frame["Дата поступления заказа"], dayfirst=True, errors="coerce")
                count = int(((created.dt.date >= ws) & (created.dt.date <= we)).sum())
            windows_rows.append(
                {
                    "since": ws.isoformat(),
                    "until": we.isoformat(),
                    "status": "ok",
                    "rows": count,
                }
            )
        pd.DataFrame(windows_rows).to_csv(store_dir / "windows.csv", index=False, encoding="utf-8")

        results.append(
            {
                "store_code": store_code,
                "success": True,
                "rows_exported": int(len(frame)),
                "windows_total": int(len(windows)),
                "windows_ok": int(len(windows)),
                "completed_missing_status_change_date": missing_count,
                "output_dir": str(store_dir.resolve()),
            }
        )

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "window_days": WINDOW_DAYS,
        "source": "ui_seed_files",
        "stores": stores,
        "results": results,
        "inputs": input_manifest,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run_summary = output_dir / "run_summary.md"
    summary_lines = [
        "# Kaspi UI Archive Export Summary",
        "",
        f"- Range: `{since.isoformat()} -> {until.isoformat()}`",
        f"- Source mode: `ui_seed_files`",
        f"- Stores: `{', '.join(stores)}`",
        "",
        "| Store | Rows | Windows OK / Total | Missing status-change date (completed) |",
        "|---|---:|---:|---:|",
    ]
    for row in results:
        summary_lines.append(
            f"| {row['store_code']} | {row['rows_exported']} | {row['windows_ok']}/{row['windows_total']} | {row['completed_missing_status_change_date']} |"
        )
    run_summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return {
        "output_dir": str(output_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "run_summary_path": str(run_summary.resolve()),
        "results": results,
    }


def export_kaspi_archive_ui_history(
    *,
    since: date,
    until: date,
    output_root: Path,
    strict: bool,
    stores: list[str],
    seed_xlsx_files: list[Path],
    resume_manifest: Path | None,
) -> dict[str, Any]:
    if resume_manifest is not None and resume_manifest.exists():
        payload = json.loads(resume_manifest.read_text(encoding="utf-8"))
        if payload.get("since") == since.isoformat() and payload.get("until") == until.isoformat():
            out_dir = resume_manifest.parent
            if all((out_dir / f"store_{s}" / f"ArchiveOrders_{s}.csv").exists() for s in stores):
                return {
                    "output_dir": str(out_dir.resolve()),
                    "manifest_path": str(resume_manifest.resolve()),
                    "run_summary_path": str((out_dir / "run_summary.md").resolve()),
                    "results": payload.get("results") or [],
                    "resumed": True,
                }

    if not seed_xlsx_files:
        raise RuntimeError(
            "no seed xlsx files provided. For strict runs, prepare per-store ArchiveOrders xlsx files "
            "or run browser automation mode separately."
        )

    out_dir = _resolve_pack_dir(output_root.resolve(), since, until)
    return _build_from_seed_files(
        seed_files=seed_xlsx_files,
        since=since,
        until=until,
        output_dir=out_dir,
        strict=strict,
        stores=stores,
    )


def _parse_date_arg(value: str) -> date:
    return date.fromisoformat(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Kaspi UI archive history pack")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--store",
        action="append",
        default=None,
        help="Store code filter (repeatable). Default: all stores",
    )
    parser.add_argument(
        "--seed-xlsx",
        action="append",
        default=None,
        help="Path(s) to already-downloaded UI archive xlsx files (repeatable)",
    )
    parser.add_argument("--resume-manifest", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    since = _parse_date_arg(args.since)
    until = _parse_date_arg(args.until)
    stores = [str(v).strip().upper() for v in (args.store or DEFAULT_STORES) if str(v).strip()]
    seed_files = [Path(p).expanduser().resolve() for p in (args.seed_xlsx or [])]
    report = export_kaspi_archive_ui_history(
        since=since,
        until=until,
        output_root=args.output_root.resolve(),
        strict=bool(args.strict),
        stores=stores,
        seed_xlsx_files=seed_files,
        resume_manifest=args.resume_manifest.resolve() if args.resume_manifest else None,
    )
    print(f"ui_archive_output_dir={report['output_dir']}")
    print(f"ui_archive_manifest={report['manifest_path']}")
    print(f"ui_archive_run_summary={report['run_summary_path']}")
    print(f"resumed={str(bool(report.get('resumed'))).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
