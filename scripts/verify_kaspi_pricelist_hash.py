#!/usr/bin/env python3
"""Verify G-WA-02 pricelist rollback and post-readback SHA evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_MANIFEST = PROJECT_ROOT / "config" / "validation" / "kaspi_pricelist_hash_manifest.csv"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "kaspi_pricelist_hash"
DEFAULT_WEB_AUTO_ROOT = Path.home() / "Docs" / "Web_automation"

REQUIRED_COLUMNS = [
    "upload_id",
    "upload_stage",
    "store_name",
    "upload_file",
    "rollback_file",
    "post_readback_file",
    "expected_upload_sha256",
    "expected_rollback_sha256",
    "expected_post_readback_sha256",
    "upload_applied_at",
    "owner_decision_id",
    "gate_id",
    "notes",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _load_manifest(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _resolve_path(raw: str, *, manifest_path: Path, web_auto_root: Path) -> Path:
    value = str(raw or "").strip()
    path = Path(value)
    if path.is_absolute():
        return path
    manifest_relative = manifest_path.parent / path
    if manifest_relative.exists():
        return manifest_relative
    return web_auto_root / path


def _verify_file_hash(
    *,
    row: dict[str, str],
    file_col: str,
    hash_col: str,
    manifest_path: Path,
    web_auto_root: Path,
    required: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    raw_file = str(row.get(file_col) or "").strip()
    expected = str(row.get(hash_col) or "").strip().lower()
    if not raw_file:
        return _check(not required, f"{file_col}_present", "optional blank" if not required else "missing"), None
    path = _resolve_path(raw_file, manifest_path=manifest_path, web_auto_root=web_auto_root)
    if not path.exists():
        return _check(False, f"{file_col}_exists", f"missing: {path}"), None
    actual = _sha256(path)
    ok = bool(expected) and actual == expected
    detail = f"actual={actual} expected={expected or 'missing'}"
    return _check(ok, f"{hash_col}_matches", detail, path=str(path)), {
        "path": str(path),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "ok": ok,
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-WA-02 Pricelist Rollback Hash Report",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"Manifest: `{report['manifest_path']}`",
        f"Web_automation root: `{report['web_auto_root']}`",
        "",
        "## Summary",
        "",
        f"- row_count_total: `{report['row_count_total']}`",
        f"- applied_row_count: `{report['applied_row_count']}`",
        f"- planned_row_count: `{report['planned_row_count']}`",
        f"- first_applied_upload_required: `{report['first_applied_upload_required']}`",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["row_errors"]:
        lines.extend(["", "## Row Errors", ""])
        for error in report["row_errors"]:
            lines.append(f"- row {error['row_number']} `{error.get('upload_id')}`: {', '.join(error['errors'])}")
    lines.append("")
    return "\n".join(lines)


def build_pricelist_hash_report(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    web_auto_root: Path = DEFAULT_WEB_AUTO_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    row_errors: list[dict[str, Any]] = []
    manifest_path = manifest_path.resolve()
    rows, fieldnames = _load_manifest(manifest_path)
    checks.append(_check(manifest_path.exists(), "manifest_present", str(manifest_path)))
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
    checks.append(
        _check(
            not missing_columns,
            "manifest_schema_columns",
            "missing=" + (",".join(missing_columns) if missing_columns else "none"),
            fieldnames=fieldnames,
        )
    )
    checks.append(_check(web_auto_root.exists(), "web_auto_root_present", str(web_auto_root)))

    seen_upload_ids: set[str] = set()
    applied_count = 0
    planned_count = 0
    verified_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=2):
        errors: list[str] = []
        upload_id = str(row.get("upload_id") or "").strip()
        if not upload_id:
            errors.append("upload_id missing")
        elif upload_id in seen_upload_ids:
            errors.append("duplicate upload_id")
        seen_upload_ids.add(upload_id)

        stage = str(row.get("upload_stage") or "").strip().lower()
        if stage not in {"planned", "applied"}:
            errors.append("upload_stage must be planned or applied")
        if stage == "applied":
            applied_count += 1
            if not str(row.get("upload_applied_at") or "").strip():
                errors.append("upload_applied_at required for applied rows")
        elif stage == "planned":
            planned_count += 1

        if str(row.get("gate_id") or "").strip() != "G-WA-02":
            errors.append("gate_id must be G-WA-02")
        for col in ("store_name", "upload_file", "rollback_file", "expected_upload_sha256", "expected_rollback_sha256"):
            if not str(row.get(col) or "").strip():
                errors.append(f"{col} missing")

        file_checks: list[dict[str, Any]] = []
        file_payloads: dict[str, Any] = {}
        for file_col, hash_col, required in (
            ("upload_file", "expected_upload_sha256", True),
            ("rollback_file", "expected_rollback_sha256", True),
            ("post_readback_file", "expected_post_readback_sha256", stage == "applied"),
        ):
            check, payload = _verify_file_hash(
                row=row,
                file_col=file_col,
                hash_col=hash_col,
                manifest_path=manifest_path,
                web_auto_root=web_auto_root,
                required=required,
            )
            file_checks.append(check)
            if payload:
                file_payloads[file_col] = payload
        checks.extend(file_checks)
        if not all(check["ok"] for check in file_checks):
            errors.append("one or more file/hash checks failed")

        verified_rows.append(
            {
                "row_number": index,
                "upload_id": upload_id,
                "upload_stage": stage,
                "store_name": str(row.get("store_name") or "").strip(),
                "owner_decision_id": str(row.get("owner_decision_id") or "").strip(),
                "files": file_payloads,
            }
        )
        if errors:
            row_errors.append({"row_number": index, "upload_id": upload_id, "errors": errors})

    checks.append(_check(not row_errors, "manifest_rows_valid", f"invalid_rows={len(row_errors)} total_rows={len(rows)}"))

    no_failures = all(row["ok"] for row in checks)
    if not no_failures:
        gate = "RED"
    elif applied_count > 0:
        gate = "GREEN"
    else:
        gate = "ARMED"

    out_dir = output_root.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at": _now_almaty(),
        "gate": gate,
        "status": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "manifest_path": str(manifest_path),
        "web_auto_root": str(web_auto_root.resolve()),
        "row_count_total": len(rows),
        "applied_row_count": applied_count,
        "planned_row_count": planned_count,
        "first_applied_upload_required": applied_count == 0,
        "checks": checks,
        "row_errors": row_errors,
        "rows": verified_rows,
        "no_external_writes_performed": True,
        "production_db_written": False,
    }
    json_path = out_dir / "kaspi_pricelist_hash_report.json"
    md_path = out_dir / "kaspi_pricelist_hash_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify G-WA-02 pricelist rollback/readback hashes.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--web-auto-root", type=Path, default=DEFAULT_WEB_AUTO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_pricelist_hash_report(
        manifest_path=args.manifest,
        web_auto_root=args.web_auto_root,
        output_root=args.output_dir,
    )
    print(f"Gate: {report['gate']}")
    print(f"Report: {report['json_path']}")
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
