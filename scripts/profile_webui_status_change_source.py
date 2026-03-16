#!/usr/bin/env python3
"""Forensic profile of raw WebUI status-change timestamps."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.north_star_workbook_utils import normalize_status_internal
from scripts.webui_archive_truth_utils import find_webui_source_files, infer_store_code_from_path

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-06"
)
REQUIRED_BASE_COLUMNS = {"№ заказа", "Статус"}
STATUS_CHANGE_HEADER_ALIASES = {
    "датаизменениястатуса",
    "датаивремяизменениястатуса",
    "датавремяизменениястатуса",
    "statuschangedate",
}
SUMMARY_RECORD = "SUMMARY"
EXAMPLE_BLANK_RECORD = "EXAMPLE_DELIVERED_BLANK"
EXAMPLE_PRESENT_RECORD = "EXAMPLE_DELIVERED_PRESENT"
PROFILE_COLUMNS = [
    "record_type",
    "scope",
    "source_file",
    "absolute_source_file",
    "store_code",
    "detected_status_change_headers",
    "status_raw",
    "status_internal",
    "total_rows",
    "delivered_rows",
    "status_change_nonblank_count",
    "status_change_blank_count",
    "example_rank",
    "order_id",
    "raw_status_change_cell",
]


class RawStatusChangeProfileError(RuntimeError):
    """Raised when the raw WebUI source profile cannot be produced."""


def _canonicalize_header(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _load_raw_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=object, keep_default_na=False)
    else:
        frame = pd.read_excel(path, dtype=object)
    frame = frame.where(pd.notna(frame), "")
    missing = sorted(REQUIRED_BASE_COLUMNS - set(frame.columns))
    if missing:
        raise RawStatusChangeProfileError(
            f"{path}: missing required columns: {', '.join(missing)}"
        )
    return frame


def _detect_status_change_headers(columns: list[str]) -> list[str]:
    detected: list[str] = []
    for header in columns:
        canon = _canonicalize_header(header)
        if canon in STATUS_CHANGE_HEADER_ALIASES:
            detected.append(str(header))
            continue
        if all(token in canon for token in ("дата", "измен", "статус")):
            detected.append(str(header))
    return list(dict.fromkeys(detected))


def _resolve_input_files(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for raw_input in inputs:
        path = raw_input.expanduser().resolve()
        if not path.exists():
            raise RawStatusChangeProfileError(f"input path not found: {path}")
        if path.is_file():
            files.append(path)
            continue
        discovered = find_webui_source_files(path)
        if discovered:
            files.extend(discovered)
            continue
        for candidate in sorted(path.rglob("ArchiveOrders*")):
            if candidate.is_file() and candidate.suffix.lower() in {".xlsx", ".csv"}:
                files.append(candidate.resolve())
    resolved = sorted(dict.fromkeys(files))
    if not resolved:
        raise RawStatusChangeProfileError("no raw WebUI export files found from --input")
    return resolved


def _render_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values: list[str] = []
        for column in columns:
            value = row.get(column, "")
            if value is None or (isinstance(value, float) and pd.isna(value)):
                text = ""
            else:
                text = str(value)
            values.append(text.replace("\n", " ").replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def profile_webui_status_change_source(
    *,
    inputs: list[Path],
    store_code: str | None,
    output_dir: Path,
) -> dict[str, Any]:
    target_store = str(store_code or "").strip().upper() or None
    files = _resolve_input_files(inputs)
    if target_store is not None:
        files = [
            path
            for path in files
            if str(infer_store_code_from_path(path) or "").strip().upper() == target_store
        ]
        if not files:
            raise RawStatusChangeProfileError(
                f"no raw WebUI export files matched store_code={target_store}"
            )

    records: list[dict[str, Any]] = []
    markdown_lines = [
        "# Raw WebUI Status-Change Source Profile",
        "",
        f"- generated_at: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        f"- file_count: `{len(files)}`",
        "",
    ]

    total_delivered_rows = 0
    total_delivered_nonblank = 0

    for path in files:
        frame = _load_raw_frame(path)
        headers = [str(column) for column in frame.columns]
        status_change_headers = _detect_status_change_headers(headers)
        status_change_header_text = ", ".join(status_change_headers) if status_change_headers else "(none)"
        if status_change_headers:
            raw_status_change = frame[status_change_headers[0]].map(_stringify_cell)
        else:
            raw_status_change = pd.Series([""] * len(frame), index=frame.index, dtype=object)
        status_raw = frame["Статус"].map(_stringify_cell)
        status_internal = status_raw.map(normalize_status_internal)
        order_id = frame["№ заказа"].map(_stringify_cell)
        delivered_mask = status_internal.eq("DELIVERED")
        nonblank_mask = raw_status_change.astype(str).str.strip().ne("")

        file_store_code = str(target_store or infer_store_code_from_path(path) or "").strip().upper()
        total_delivered_rows += int(delivered_mask.sum())
        total_delivered_nonblank += int((delivered_mask & nonblank_mask).sum())

        file_total_row = {
            "record_type": SUMMARY_RECORD,
            "scope": "FILE",
            "source_file": path.name,
            "absolute_source_file": str(path),
            "store_code": file_store_code,
            "detected_status_change_headers": status_change_header_text,
            "status_raw": "__ALL__",
            "status_internal": "__ALL__",
            "total_rows": int(len(frame)),
            "delivered_rows": int(delivered_mask.sum()),
            "status_change_nonblank_count": int(nonblank_mask.sum()),
            "status_change_blank_count": int((~nonblank_mask).sum()),
            "example_rank": "",
            "order_id": "",
            "raw_status_change_cell": "",
        }
        records.append(file_total_row)

        grouped = (
            pd.DataFrame(
                {
                    "status_raw": status_raw,
                    "status_internal": status_internal,
                    "raw_status_change": raw_status_change,
                }
            )
            .groupby(["status_raw", "status_internal"], dropna=False)
            .agg(
                total_rows=("status_raw", "size"),
                delivered_rows=("status_internal", lambda s: int((s == "DELIVERED").sum())),
                status_change_nonblank_count=(
                    "raw_status_change",
                    lambda s: int(s.astype(str).str.strip().ne("").sum()),
                ),
            )
            .reset_index()
            .sort_values(["status_internal", "status_raw"], kind="stable")
        )
        grouped["status_change_blank_count"] = (
            grouped["total_rows"] - grouped["status_change_nonblank_count"]
        )
        for row in grouped.to_dict("records"):
            records.append(
                {
                    "record_type": SUMMARY_RECORD,
                    "scope": "STATUS",
                    "source_file": path.name,
                    "absolute_source_file": str(path),
                    "store_code": file_store_code,
                    "detected_status_change_headers": status_change_header_text,
                    "status_raw": row["status_raw"],
                    "status_internal": row["status_internal"],
                    "total_rows": int(row["total_rows"]),
                    "delivered_rows": int(row["delivered_rows"]),
                    "status_change_nonblank_count": int(row["status_change_nonblank_count"]),
                    "status_change_blank_count": int(row["status_change_blank_count"]),
                    "example_rank": "",
                    "order_id": "",
                    "raw_status_change_cell": "",
                }
            )

        example_frame = pd.DataFrame(
            {
                "order_id": order_id,
                "status_raw": status_raw,
                "raw_status_change_cell": raw_status_change,
                "status_internal": status_internal,
            }
        )
        delivered_blank = example_frame[delivered_mask & ~nonblank_mask].head(10).reset_index(drop=True)
        delivered_present = example_frame[delivered_mask & nonblank_mask].head(10).reset_index(drop=True)
        for idx, row in delivered_blank.iterrows():
            records.append(
                {
                    "record_type": EXAMPLE_BLANK_RECORD,
                    "scope": "DELIVERED_EXAMPLE",
                    "source_file": path.name,
                    "absolute_source_file": str(path),
                    "store_code": file_store_code,
                    "detected_status_change_headers": status_change_header_text,
                    "status_raw": row["status_raw"],
                    "status_internal": row["status_internal"],
                    "total_rows": "",
                    "delivered_rows": "",
                    "status_change_nonblank_count": "",
                    "status_change_blank_count": "",
                    "example_rank": idx + 1,
                    "order_id": row["order_id"],
                    "raw_status_change_cell": row["raw_status_change_cell"],
                }
            )
        for idx, row in delivered_present.iterrows():
            records.append(
                {
                    "record_type": EXAMPLE_PRESENT_RECORD,
                    "scope": "DELIVERED_EXAMPLE",
                    "source_file": path.name,
                    "absolute_source_file": str(path),
                    "store_code": file_store_code,
                    "detected_status_change_headers": status_change_header_text,
                    "status_raw": row["status_raw"],
                    "status_internal": row["status_internal"],
                    "total_rows": "",
                    "delivered_rows": "",
                    "status_change_nonblank_count": "",
                    "status_change_blank_count": "",
                    "example_rank": idx + 1,
                    "order_id": row["order_id"],
                    "raw_status_change_cell": row["raw_status_change_cell"],
                }
            )

        summary_rows = [
            {
                "status_raw": row["status_raw"],
                "status_internal": row["status_internal"],
                "total_rows": int(row["total_rows"]),
                "delivered_rows": int(row["delivered_rows"]),
                "status_change_nonblank_count": int(row["status_change_nonblank_count"]),
                "status_change_blank_count": int(row["status_change_blank_count"]),
            }
            for row in grouped.to_dict("records")
        ]
        blank_rows = [
            {
                "example_rank": idx + 1,
                "order_id": row["order_id"],
                "status": row["status_raw"],
                "raw_status_change_cell": row["raw_status_change_cell"],
            }
            for idx, row in delivered_blank.iterrows()
        ]
        present_rows = [
            {
                "example_rank": idx + 1,
                "order_id": row["order_id"],
                "status": row["status_raw"],
                "raw_status_change_cell": row["raw_status_change_cell"],
            }
            for idx, row in delivered_present.iterrows()
        ]

        markdown_lines.extend(
            [
                f"## `{path.name}`",
                "",
                f"- absolute_source_file: `{path}`",
                f"- store_code: `{file_store_code or '(unknown)'}`",
                f"- detected_status_change_headers: `{status_change_header_text}`",
                f"- delivered_rows: `{int(delivered_mask.sum())}`",
                f"- delivered_rows_with_nonblank_status_change: `{int((delivered_mask & nonblank_mask).sum())}`",
                "",
                "### Status Summary",
                "",
            ]
        )
        markdown_lines.extend(
            _render_markdown_table(
                summary_rows,
                [
                    "status_raw",
                    "status_internal",
                    "total_rows",
                    "delivered_rows",
                    "status_change_nonblank_count",
                    "status_change_blank_count",
                ],
            )
        )
        markdown_lines.extend(["", "### Delivered Rows With Blank Status-Change", ""])
        if blank_rows:
            markdown_lines.extend(
                _render_markdown_table(
                    blank_rows,
                    ["example_rank", "order_id", "status", "raw_status_change_cell"],
                )
            )
        else:
            markdown_lines.append("_No delivered rows with blank status-change values._")
        markdown_lines.extend(["", "### Delivered Rows With Present Status-Change", ""])
        if present_rows:
            markdown_lines.extend(
                _render_markdown_table(
                    present_rows,
                    ["example_rank", "order_id", "status", "raw_status_change_cell"],
                )
            )
        else:
            markdown_lines.append("_No delivered rows with present status-change values._")
        markdown_lines.append("")

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_csv = output_dir / "raw_status_change_profile.csv"
    profile_md = output_dir / "raw_status_change_profile.md"
    pd.DataFrame(records, columns=PROFILE_COLUMNS).to_csv(
        profile_csv,
        index=False,
        encoding="utf-8",
    )

    overall_decision = (
        "RAW_HAS_DELIVERED_STATUS_CHANGE_VALUES"
        if total_delivered_nonblank > 0
        else "RAW_DELIVERED_STATUS_CHANGE_VALUES_MISSING"
    )
    markdown_lines[4:4] = [
        f"- delivered_rows_total: `{total_delivered_rows}`",
        f"- delivered_rows_with_nonblank_status_change_total: `{total_delivered_nonblank}`",
        f"- viability_hint: `{overall_decision}`",
        "",
    ]
    profile_md.write_text("\n".join(markdown_lines), encoding="utf-8")

    return {
        "status": "PASS",
        "file_count": len(files),
        "profile_csv": str(profile_csv),
        "profile_md": str(profile_md),
        "delivered_rows_total": total_delivered_rows,
        "delivered_rows_with_nonblank_status_change_total": total_delivered_nonblank,
        "viability_hint": overall_decision,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile raw WebUI status-change timestamps")
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        required=True,
        help="Raw WebUI exported file(s) or directories containing ArchiveOrders exports",
    )
    parser.add_argument("--store-code", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = profile_webui_status_change_source(
            inputs=list(args.input),
            store_code=args.store_code,
            output_dir=args.output_dir,
        )
    except RawStatusChangeProfileError as exc:
        print("status=FAIL")
        print("error_code=RAW_STATUS_CHANGE_PROFILE_FAIL")
        print(f"message={exc}")
        return 1

    print(f"raw_status_change_profile_csv={report['profile_csv']}")
    print(f"raw_status_change_profile_md={report['profile_md']}")
    print(f"viability_hint={report['viability_hint']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
