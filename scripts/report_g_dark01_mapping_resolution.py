#!/usr/bin/env python3
"""Classify the no-write G-DARK-01 mapping/catalog route for missing rows."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_PREFLIGHT_TARGET_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "g_dark01_relist_preflight_latest"
    / "20260618_204904_0500"
    / "dark_relist_preflight_target_rows.csv"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_REPRICER_DB = Path("~/Docs/Web_automation/data/repricer_items.sqlite")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_dark01_mapping_resolution"

RESOLUTION_COLUMNS = [
    "family_id",
    "sku_key",
    "size",
    "current_stock",
    "preflight_row_status",
    "repricer_exact_token_rows",
    "article_map_exact_sku_rows",
    "article_map_title_size_rows",
    "other_family_title_size_rows",
    "recommended_route",
    "reason",
]

ARTICLE_MAP_COLUMNS = [
    "store_code",
    "kaspi_article",
    "sku_id",
    "kaspi_offer_name",
    "source",
    "candidate_type",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _run_id(value: str) -> str:
    return value.replace("-", "").replace(":", "").replace("+", "_").replace("T", "_")


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _extract_token_size(merchant_sku: str, sku_key: str) -> str:
    text = str(merchant_sku or "").strip()
    prefix = f"{sku_key}_"
    if text.startswith(prefix):
        token = text[len(prefix) :].split("_", 1)[0].upper()
        if token in {"S", "M", "L", "XL", "2XL", "3XL", "4XL"}:
            return token
    match = re.search(r"_(S|M|L|XL|2XL|3XL|4XL)(?:_|$)", text.upper())
    return match.group(1) if match else ""


def _title_mentions_size(title: str, size: str) -> bool:
    normalized = " ".join(str(title or "").replace("_", " ").split()).upper()
    if not normalized:
        return False
    size = size.upper()
    patterns = [
        rf"(?:^|\s){re.escape(size)}(?:\s|$)",
        rf"(?:^|\s){re.escape(size)}(?:-|/|,)",
        rf"(?:-|/|,){re.escape(size)}(?:\s|$)",
    ]
    return any(re.search(pattern, normalized) for pattern in patterns)


def _sku_id_size(sku_id: str, sku_key: str) -> str:
    return _extract_token_size(sku_id, sku_key)


def _target_missing_rows(preflight_rows: list[dict[str, str]], family_sku_key: str) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for row in preflight_rows:
        sku_key = str(row.get("sku_key") or "").strip()
        size = str(row.get("size") or "").strip().upper()
        if sku_key != family_sku_key:
            continue
        if str(row.get("row_status") or "") != "MISSING_FROM_ACTIVE_AND_ARCHIVE":
            continue
        key = (sku_key, size)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _load_article_map_rows(conn: sqlite3.Connection, sku_key: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, source
            FROM dim_kaspi_article_map
            WHERE active_flag = 1
              AND (sku_key = ? OR kaspi_article LIKE ?)
            ORDER BY store_code, kaspi_article
            """,
            (sku_key, f"{sku_key}%"),
        ).fetchall()
    ]


def _load_other_family_title_rows(conn: sqlite3.Connection, sku_key: str, size: str) -> list[dict[str, Any]]:
    family_hint = sku_key.rsplit("_", 1)[0] if "_" in sku_key else sku_key
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT store_code, kaspi_article, kaspi_offer_name, sku_key, sku_id, source
            FROM dim_kaspi_article_map
            WHERE active_flag = 1
              AND sku_key != ?
              AND (sku_key LIKE ? OR kaspi_article LIKE ? OR kaspi_name_core LIKE ?)
            ORDER BY sku_key, store_code, kaspi_article
            """,
            (sku_key, f"%RUSH%WHITE%", "%RUSH%WHITE%", "%рашгард%бел%"),
        ).fetchall()
    ]
    return [row for row in rows if _title_mentions_size(str(row.get("kaspi_offer_name") or ""), size)]


def _load_repricer_rows(conn: sqlite3.Connection, sku_key: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT fetched_at, store_id, store_name, merchant_sku, kaspi_sku, merchant_title,
                   link, price, min_price, max_price, active, is_available, preorder
            FROM repricer_items
            WHERE merchant_sku LIKE ? OR merchant_title LIKE ?
            ORDER BY store_id, merchant_sku
            """,
            (f"%{sku_key}%", "%RUSH%WHITE%"),
        ).fetchall()
    ]


def _classify_row(
    *,
    target: dict[str, str],
    article_rows: list[dict[str, Any]],
    other_family_rows: list[dict[str, Any]],
    repricer_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    sku_key = str(target.get("sku_key") or "").strip()
    size = str(target.get("size") or "").strip().upper()
    exact_token_rows = [
        row
        for row in repricer_rows
        if str(row.get("merchant_sku") or "").startswith(f"{sku_key}_")
        and _extract_token_size(str(row.get("merchant_sku") or ""), sku_key) == size
    ]
    exact_sku_rows = [row for row in article_rows if _sku_id_size(str(row.get("sku_id") or ""), sku_key) == size]
    title_size_rows = [row for row in article_rows if _title_mentions_size(str(row.get("kaspi_offer_name") or ""), size)]
    other_title_rows = [row for row in other_family_rows if _title_mentions_size(str(row.get("kaspi_offer_name") or ""), size)]

    if exact_token_rows:
        route = "ARTICLE_MAP_CORRECTION"
        reason = "Fresh Repricer has exact seller-article token rows, but the preflight did not resolve them."
    elif title_size_rows and not exact_sku_rows:
        route = "ARTICLE_MAP_OR_PRODUCT_TITLE_MAPPING_REVIEW"
        reason = "Family article-map rows mention this title size but map to different local sku_id sizes."
    elif title_size_rows and exact_sku_rows:
        route = "PLATFORM_ROW_RESTORE_OR_OFFER_CREATION"
        reason = "Local article-map evidence exists for this size, but no ACTIVE/ARCHIVE platform row was found."
    elif other_title_rows:
        route = "DIFFERENT_PRODUCT_TITLE_MAPPING_REVIEW"
        reason = "Matching title-size evidence exists under a different RUSH/WHITE family; do not create a new offer until family mapping is reviewed."
    else:
        route = "OFFER_CREATION_OR_CATALOG_MISSING_REVIEW"
        reason = "No exact seller-article, same-family article-map, or alternate-family title evidence proves a reusable row."

    return {
        "family_id": target.get("family_id", ""),
        "sku_key": sku_key,
        "size": size,
        "current_stock": target.get("current_stock", ""),
        "preflight_row_status": target.get("row_status", ""),
        "repricer_exact_token_rows": len(exact_token_rows),
        "article_map_exact_sku_rows": len(exact_sku_rows),
        "article_map_title_size_rows": len(title_size_rows),
        "other_family_title_size_rows": len(other_title_rows),
        "recommended_route": route,
        "reason": reason,
    }


def _candidate_rows(
    *,
    targets: list[dict[str, str]],
    article_rows: list[dict[str, Any]],
    other_family_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in targets:
        sku_key = str(target.get("sku_key") or "").strip()
        size = str(target.get("size") or "").strip().upper()
        for row in article_rows:
            if _sku_id_size(str(row.get("sku_id") or ""), sku_key) == size:
                rows.append({**row, "candidate_type": f"same_family_sku_id_{size}"})
            elif _title_mentions_size(str(row.get("kaspi_offer_name") or ""), size):
                rows.append({**row, "candidate_type": f"same_family_title_{size}"})
        for row in other_family_rows:
            if _title_mentions_size(str(row.get("kaspi_offer_name") or ""), size):
                rows.append({**row, "candidate_type": f"other_family_title_{size}"})
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("candidate_type") or ""),
            str(row.get("store_code") or ""),
            str(row.get("kaspi_article") or ""),
        )
        unique[key] = row
    return list(unique.values())


def build_mapping_resolution_report(
    *,
    preflight_target_csv: Path,
    db_path: Path,
    repricer_db_path: Path,
    output_root: Path,
    sku_key: str = "CL_NEW-CLO_MEN_RUSH_WHITE",
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or _now_almaty()
    out_dir = output_root / _run_id(generated_at)
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight_rows = _read_csv(preflight_target_csv)
    targets = _target_missing_rows(preflight_rows, sku_key)
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    checks.append({"check": "preflight_target_csv_present", "ok": preflight_target_csv.exists(), "path": str(preflight_target_csv)})
    checks.append({"check": "db_present", "ok": db_path.exists(), "path": str(db_path)})
    checks.append({"check": "repricer_db_present", "ok": repricer_db_path.exists(), "path": str(repricer_db_path)})
    if not targets:
        blockers.append(f"no missing target rows found for {sku_key}")

    resolution_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    repricer_source_max = ""
    if db_path.exists() and repricer_db_path.exists():
        with _connect_ro(db_path) as db_conn, _connect_ro(repricer_db_path) as repricer_conn:
            article_rows = _load_article_map_rows(db_conn, sku_key)
            repricer_rows = _load_repricer_rows(repricer_conn, sku_key)
            fetched_values = sorted({str(row.get("fetched_at") or "") for row in repricer_rows if row.get("fetched_at")})
            repricer_source_max = fetched_values[-1] if fetched_values else ""
            all_other_rows: list[dict[str, Any]] = []
            for target in targets:
                all_other_rows.extend(_load_other_family_title_rows(db_conn, sku_key, str(target.get("size") or "")))
            for target in targets:
                resolution_rows.append(
                    _classify_row(
                        target=target,
                        article_rows=article_rows,
                        other_family_rows=all_other_rows,
                        repricer_rows=repricer_rows,
                    )
                )
            candidates = _candidate_rows(targets=targets, article_rows=article_rows, other_family_rows=all_other_rows)

    route_counts: dict[str, int] = {}
    for row in resolution_rows:
        route = str(row.get("recommended_route") or "")
        route_counts[route] = route_counts.get(route, 0) + 1
    if any(row.get("recommended_route") == "OFFER_CREATION_OR_CATALOG_MISSING_REVIEW" for row in resolution_rows):
        blockers.append("at least one missing size has no reusable mapping evidence")
    if any("MAPPING_REVIEW" in str(row.get("recommended_route") or "") for row in resolution_rows):
        blockers.append("at least one missing size has article/title-size mapping drift")

    resolution_csv = out_dir / "rush_white_missing_size_resolution.csv"
    candidates_csv = out_dir / "rush_white_article_map_candidates.csv"
    _write_csv(resolution_csv, resolution_rows, RESOLUTION_COLUMNS)
    _write_csv(candidates_csv, candidates, ARTICLE_MAP_COLUMNS)

    gate = "ARMED" if resolution_rows else "RED"
    report = {
        "gate_id": "G-DARK-01",
        "gate": gate,
        "status": "NO_WRITE_MAPPING_RESOLUTION_READY" if resolution_rows else "NO_WRITE_MAPPING_RESOLUTION_BLOCKED",
        "generated_at": generated_at,
        "preflight_target_csv": str(preflight_target_csv),
        "db_path": str(db_path),
        "repricer_db_path": str(repricer_db_path),
        "repricer_source_max_fetched_at": repricer_source_max,
        "sku_key": sku_key,
        "target_missing_size_count": len(targets),
        "target_missing_sizes": [str(row.get("size") or "") for row in targets],
        "route_counts": dict(sorted(route_counts.items())),
        "resolution_csv": str(resolution_csv),
        "candidate_csv": str(candidates_csv),
        "blockers": blockers,
        "checks": checks,
        "production_db_written": False,
        "external_writes_performed": False,
        "live_upload_authorized": False,
        "notes": [
            "This report is no-write evidence only; it does not upload, relist, create offers, or mutate DB/workbook/source systems.",
            "G-DARK-01 remains not GREEN until an owner-approved write lane repairs the verified route and fresh readback passes.",
        ],
    }
    json_path = out_dir / "g_dark01_mapping_resolution_report.json"
    md_path = out_dir / "g_dark01_mapping_resolution_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-DARK-01 Mapping Resolution",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- sku_key: {report['sku_key']}",
        f"- target_missing_sizes: {', '.join(report['target_missing_sizes'])}",
        f"- repricer_source_max_fetched_at: {report['repricer_source_max_fetched_at']}",
        f"- live_upload_authorized: {report['live_upload_authorized']}",
        "",
        "## Route Counts",
        "",
    ]
    if report["route_counts"]:
        lines.extend(f"- {route}: {count}" for route, count in report["route_counts"].items())
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Artifacts", ""])
    lines.append(f"- resolution_csv: `{report['resolution_csv']}`")
    lines.append(f"- candidate_csv: `{report['candidate_csv']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-target-csv", type=Path, default=DEFAULT_PREFLIGHT_TARGET_CSV)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--repricer-db-path", type=Path, default=DEFAULT_REPRICER_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sku-key", default="CL_NEW-CLO_MEN_RUSH_WHITE")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_mapping_resolution_report(
        preflight_target_csv=_resolve_path(args.preflight_target_csv),
        db_path=_resolve_path(args.db_path),
        repricer_db_path=_resolve_path(args.repricer_db_path),
        output_root=_resolve_path(args.output_root),
        sku_key=args.sku_key,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Status: {report['status']}")
        print(f"Report: {report['json_path']}")
    return 1 if args.strict and report["gate"] == "RED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
