#!/usr/bin/env python3
"""Validate Import/Waybill/Ship selector parity with deterministic archived artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMPORT_LOG = PROJECT_ROOT / "runtime_logs" / "kaspi_import_stdout.log"
DEFAULT_WAYBILL_LOG = PROJECT_ROOT / "runtime_logs" / "kaspi_waybill_deadline_stdout.log"
DEFAULT_ARCHIVE_ROOT = PROJECT_ROOT / "excel_ui" / "Archive"
DEFAULT_SELECTION_CACHE = (
    PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "ops_selection_parity"
ORDER_ID_RE = re.compile(r"(\d{6,})")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_import_orders_for_day(log_text: str, as_of: str) -> int | None:
    pattern = re.compile(
        rf"SUCCESS_GATE_OK:\s+activeorders snapshot parity \(target_date={re.escape(as_of)}, orders=(\d+)\)"
    )
    matches = [int(m.group(1)) for m in pattern.finditer(log_text)]
    if not matches:
        return None
    return int(matches[-1])


def _parse_latest_shipped_total(log_text: str, as_of: str) -> int | None:
    lines = log_text.splitlines()
    run_starts: list[int] = []
    run_date = f"Time: {as_of} "
    for idx, line in enumerate(lines):
        if line.strip().startswith(run_date):
            run_starts.append(idx)
    if not run_starts:
        return None
    start = run_starts[-1]
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].strip().startswith("Time: "):
            end = idx
            break
    block = lines[start:end]
    shipped_values = []
    ship_re = re.compile(r"^\s*Shipped:\s*(\d+)\s*$")
    for line in block:
        match = ship_re.match(line)
        if match:
            shipped_values.append(int(match.group(1)))
    if not shipped_values:
        no_pending_marker = "No orders pending assembly in Kaspi"
        if any(no_pending_marker in line for line in block):
            return 0
        return None
    return int(sum(shipped_values))


def _find_latest_archive_input_dir(archive_root: Path, as_of: str) -> Path | None:
    if not archive_root.exists():
        return None
    pattern = f"input_{as_of}_*"
    candidates = [path for path in archive_root.glob(pattern) if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _extract_pdf_order_ids(waybill_dir: Path) -> set[str]:
    ids: set[str] = set()
    for pdf in sorted(waybill_dir.glob("*.pdf")):
        match = ORDER_ID_RE.search(pdf.name)
        if match:
            ids.add(str(match.group(1)))
    return ids


def _load_selection_cache_ids(cache_path: Path, as_of: str) -> set[str] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("target_date") or "").strip() != as_of:
        return None
    stores = payload.get("stores") or {}
    if not isinstance(stores, dict):
        return None
    ids: set[str] = set()
    for raw_ids in stores.values():
        if not isinstance(raw_ids, list):
            continue
        for order_id in raw_ids:
            cleaned = str(order_id).strip()
            if cleaned:
                ids.add(cleaned)
    return ids


def _write_diff_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = ["order_id", "reason", "left_source", "right_source"]
    lines = [",".join(headers)]
    for row in rows:
        values = [str(row.get(col) or "").replace(",", " ") for col in headers]
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Ops Selection Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- archive_input_dir: `{report.get('archive_input_dir')}`",
        f"- import_orders: `{report.get('import_orders')}`",
        f"- waybill_selected_orders: `{report.get('waybill_selected_orders')}`",
        f"- waybill_pdf_orders: `{report.get('waybill_pdf_orders')}`",
        f"- shipped_orders: `{report.get('shipped_orders')}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_ops_selection_parity(
    *,
    as_of: str,
    import_log: Path,
    waybill_log: Path,
    archive_root: Path,
    selection_cache: Path,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    if not import_log.exists():
        raise RuntimeError(f"missing import log: {import_log}")
    if not waybill_log.exists():
        raise RuntimeError(f"missing waybill log: {waybill_log}")

    import_orders = _parse_import_orders_for_day(_read_text(import_log), as_of)
    if import_orders is None:
        errors.append(f"import selector count not found in {import_log} for as_of={as_of}")

    shipped_orders = _parse_latest_shipped_total(_read_text(waybill_log), as_of)
    if shipped_orders is None:
        errors.append(f"shipped selector count not found in {waybill_log} for as_of={as_of}")

    archive_dir = _find_latest_archive_input_dir(archive_root.resolve(), as_of)
    if archive_dir is None:
        errors.append(f"archive input folder not found for as_of={as_of} under {archive_root.resolve()}")
        manifest = {}
        pdf_ids: set[str] = set()
        selected_count = 0
        copied_waybills = 0
        missing_waybills = 0
    else:
        manifest_path = archive_dir / "archive_manifest.json"
        waybill_dir = archive_dir / "waybills"
        if not manifest_path.exists():
            errors.append(f"missing archive manifest: {manifest_path}")
            manifest = {}
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"invalid archive manifest JSON: {manifest_path} ({exc})")
                manifest = {}
        if not waybill_dir.exists():
            errors.append(f"missing archive waybill directory: {waybill_dir}")
            pdf_ids = set()
        else:
            pdf_ids = _extract_pdf_order_ids(waybill_dir)

        selected_count = int(float((manifest or {}).get("selected_count") or 0))
        copied_waybills = int(float((manifest or {}).get("copied_waybills") or 0))
        missing_waybills = int(float((manifest or {}).get("missing_waybills") or 0))

        checks.append(
            {
                "check": "manifest_selected_equals_copied_plus_missing",
                "ok": selected_count > 0 and selected_count == (copied_waybills + missing_waybills),
                "details": f"selected={selected_count} copied={copied_waybills} missing={missing_waybills}",
            }
        )
        if selected_count <= 0 or selected_count != (copied_waybills + missing_waybills):
            errors.append(
                "archive manifest mismatch: selected_count must equal copied_waybills + missing_waybills"
            )

        checks.append(
            {
                "check": "archive_pdf_count_matches_manifest",
                "ok": len(pdf_ids) == copied_waybills,
                "details": f"pdf_count={len(pdf_ids)} copied_waybills={copied_waybills}",
            }
        )
        if len(pdf_ids) != copied_waybills:
            errors.append(
                f"archive waybill pdf count mismatch: pdf_count={len(pdf_ids)} copied_waybills={copied_waybills}"
            )

    if import_orders is not None:
        checks.append(
            {
                "check": "import_orders_within_waybill_selection",
                "ok": import_orders <= selected_count,
                "details": f"import_orders={import_orders} waybill_selected={selected_count}",
            }
        )
        if import_orders > selected_count:
            errors.append(
                f"import selector count exceeds waybill selection: import={import_orders} waybill={selected_count}"
            )

    if shipped_orders is not None:
        checks.append(
            {
                "check": "shipped_orders_within_waybill_selection",
                "ok": shipped_orders <= selected_count,
                "details": f"shipped_orders={shipped_orders} waybill_selected={selected_count}",
            }
        )
        if shipped_orders > selected_count:
            errors.append(
                f"shipped selector count exceeds waybill selection: shipped={shipped_orders} waybill={selected_count}"
            )

    cache_ids = _load_selection_cache_ids(selection_cache.resolve(), as_of)
    missing_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []
    if cache_ids is not None:
        cache_minus_archive = sorted(cache_ids - pdf_ids)
        archive_minus_cache = sorted(pdf_ids - cache_ids)
        for order_id in cache_minus_archive:
            missing_rows.append(
                {
                    "order_id": order_id,
                    "reason": "present_in_cache_missing_pdf",
                    "left_source": "selection_cache",
                    "right_source": "archive_waybills",
                }
            )
        for order_id in archive_minus_cache:
            extra_rows.append(
                {
                    "order_id": order_id,
                    "reason": "pdf_without_cache_selection",
                    "left_source": "archive_waybills",
                    "right_source": "selection_cache",
                }
            )

        checks.append(
            {
                "check": "cache_to_manifest_count_match",
                "ok": len(cache_ids) == selected_count,
                "details": f"cache_ids={len(cache_ids)} selected_count={selected_count}",
            }
        )
        if len(cache_ids) != selected_count:
            errors.append(
                f"selection cache count mismatch: cache_ids={len(cache_ids)} selected_count={selected_count}"
            )

        checks.append(
            {
                "check": "cache_missing_ids_match_manifest_missing",
                "ok": len(cache_minus_archive) == missing_waybills,
                "details": f"cache_minus_archive={len(cache_minus_archive)} missing_waybills={missing_waybills}",
            }
        )
        if len(cache_minus_archive) != missing_waybills:
            errors.append(
                "selection cache missing-id count mismatch vs manifest missing_waybills "
                f"(cache_minus_archive={len(cache_minus_archive)} missing_waybills={missing_waybills})"
            )

        checks.append(
            {
                "check": "no_archive_extra_ids_vs_cache",
                "ok": len(archive_minus_cache) == 0,
                "details": f"archive_minus_cache={len(archive_minus_cache)}",
            }
        )
        if archive_minus_cache:
            errors.append(
                f"archive contains order IDs not present in selection cache (count={len(archive_minus_cache)})"
            )
    else:
        checks.append(
            {
                "check": "selection_cache_available_for_as_of",
                "ok": True,
                "details": f"skipped (cache target_date mismatch or cache missing at {selection_cache.resolve()})",
            }
        )

    ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    missing_csv = out_dir / "missing_order_ids.csv"
    extra_csv = out_dir / "extra_order_ids.csv"
    _write_diff_csv(missing_csv, missing_rows)
    _write_diff_csv(extra_csv, extra_rows)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "import_log": str(import_log.resolve()),
        "waybill_log": str(waybill_log.resolve()),
        "archive_root": str(archive_root.resolve()),
        "archive_input_dir": str(archive_dir) if archive_dir else None,
        "selection_cache": str(selection_cache.resolve()),
        "import_orders": import_orders,
        "waybill_selected_orders": selected_count,
        "waybill_pdf_orders": len(pdf_ids),
        "shipped_orders": shipped_orders,
        "cache_ids_count": (len(cache_ids) if cache_ids is not None else None),
        "missing_diff_csv": str(missing_csv),
        "extra_diff_csv": str(extra_csv),
        "checks": checks,
        "errors": errors,
    }
    json_path = out_dir / "parity_report.json"
    md_path = out_dir / "parity_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("ops selection parity validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate import/waybill/ship selector parity")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--import-log", type=Path, default=DEFAULT_IMPORT_LOG)
    parser.add_argument("--waybill-log", type=Path, default=DEFAULT_WAYBILL_LOG)
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--selection-cache", type=Path, default=DEFAULT_SELECTION_CACHE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_ops_selection_parity(
        as_of=str(args.as_of),
        import_log=args.import_log,
        waybill_log=args.waybill_log,
        archive_root=args.archive_root,
        selection_cache=args.selection_cache,
        output_root=args.output_root,
        strict=bool(args.strict),
    )
    print(f"ops_selection_parity_json={report['json_path']}")
    print(f"ops_selection_parity_md={report['md_path']}")
    print(f"missing_diff_csv={report['missing_diff_csv']}")
    print(f"extra_diff_csv={report['extra_diff_csv']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
