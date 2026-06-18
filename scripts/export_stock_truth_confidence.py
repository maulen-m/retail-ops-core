#!/usr/bin/env python3
"""Export per-SKU/size stock-truth confidence scores.

Read-only over the operational DB. The script publishes report artifacts that
downstream price, ads, and liquidation lanes can consume; it does not mutate DB
state or external systems.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any, Iterable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.ops.manual_stock_count_manifest import (  # noqa: E402
    APPROVED_MANIFEST_DIR,
    aggregate_manual_stock_counts,
    load_approved_manual_stock_manifest,
)


ALMATY = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "stock_truth_confidence"
DEFAULT_CURRENT_ROOT = PROJECT_ROOT / "exports" / "current" / "stock_truth_confidence"
OCR_INPUT_SOURCE = "OWNER_APPROVED_TEMP_OCR_OVERRIDE"
OPEN_EXCEPTION_STATUSES = {"OPEN", "PENDING", "BLOCKED", "NEW", "ACTIVE"}
GREEN_SCORE = 80.0
YELLOW_SCORE = 50.0


@dataclass(frozen=True)
class ActiveSkuSize:
    sku_id: str
    sku_key: str
    my_size: str
    barcode: str
    size_order: int | None
    model: str
    color: str
    product_type: str
    category: str
    gender: str


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _days_between(as_of: date, value: str | None) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max(0, (as_of - parsed).days)


def _factor_from_days(days: int | None, bands: tuple[tuple[int, float], ...], missing: float) -> float:
    if days is None:
        return missing
    for max_days, factor in bands:
        if days <= max_days:
            return factor
    return bands[-1][1]


def _confidence_band(score: float) -> str:
    if score >= GREEN_SCORE:
        return "GREEN"
    if score >= YELLOW_SCORE:
        return "YELLOW"
    return "RED"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_active_sku_sizes(conn: sqlite3.Connection) -> list[ActiveSkuSize]:
    rows = conn.execute(
        """
        SELECT
            ds.sku_id,
            ds.sku_key,
            COALESCE(ds.my_size, '') AS my_size,
            COALESCE(ds.barcode, '') AS barcode,
            ds.size_order,
            COALESCE(d.model, '') AS model,
            COALESCE(d.color, '') AS color,
            COALESCE(d.product_type, '') AS product_type,
            COALESCE(d.category, '') AS category,
            COALESCE(d.gender, '') AS gender
        FROM dim_sku_size ds
        JOIN dim_sku d ON d.sku_key = ds.sku_key
        WHERE COALESCE(ds.active_flag, 1) = 1
          AND COALESCE(d.active_flag, 1) = 1
        ORDER BY
            COALESCE(d.model, ''),
            COALESCE(d.color, ''),
            ds.sku_key,
            COALESCE(ds.size_order, 999999),
            COALESCE(ds.my_size, ''),
            ds.sku_id
        """
    ).fetchall()
    return [
        ActiveSkuSize(
            sku_id=str(row["sku_id"] or ""),
            sku_key=str(row["sku_key"] or ""),
            my_size=str(row["my_size"] or ""),
            barcode=str(row["barcode"] or ""),
            size_order=int(row["size_order"]) if row["size_order"] is not None else None,
            model=str(row["model"] or ""),
            color=str(row["color"] or ""),
            product_type=str(row["product_type"] or ""),
            category=str(row["category"] or ""),
            gender=str(row["gender"] or ""),
        )
        for row in rows
    ]


def _latest_snapshot_date(conn: sqlite3.Connection, as_of: date) -> str:
    row = conn.execute(
        """
        SELECT MAX(snapshot_date) AS snapshot_date
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date <= ?
        """,
        (as_of.isoformat(),),
    ).fetchone()
    if row is not None and row["snapshot_date"]:
        return str(row["snapshot_date"])
    fallback = conn.execute("SELECT MAX(snapshot_date) AS snapshot_date FROM fact_inventory_snapshot_size").fetchone()
    if fallback is None or not fallback["snapshot_date"]:
        raise RuntimeError("fact_inventory_snapshot_size has no snapshot rows")
    return str(fallback["snapshot_date"])


def _load_snapshot_rows(conn: sqlite3.Connection, snapshot_date: str) -> dict[str, sqlite3.Row]:
    return {
        str(row["sku_id"]): row
        for row in conn.execute(
            """
            SELECT sku_id, sku_key, my_size, current_stock, inbound_stock, created_at
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
            """,
            (snapshot_date,),
        ).fetchall()
    }


def _load_ledger_stats(conn: sqlite3.Connection, snapshot_date: str) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        """
        SELECT
            sku_id,
            COALESCE(SUM(qty_change), 0) AS ledger_balance,
            MAX(event_date) AS latest_ledger_event_date,
            COUNT(*) AS ledger_event_count,
            COALESCE(SUM(ABS(qty_change)), 0) AS ledger_abs_qty,
            COALESCE(SUM(
                CASE
                    WHEN UPPER(COALESCE(reference_id, '')) LIKE '%NEGATIVE_CLAMP%'
                      OR UPPER(COALESCE(idempotency_key, '')) LIKE '%NEGATIVE_CLAMP%'
                      OR UPPER(COALESCE(notes, '')) LIKE '%NEGATIVE_CLAMP%'
                    THEN 1 ELSE 0
                END
            ), 0) AS clamp_event_count,
            COALESCE(SUM(
                CASE
                    WHEN UPPER(COALESCE(reference_id, '')) LIKE '%NEGATIVE_CLAMP%'
                      OR UPPER(COALESCE(idempotency_key, '')) LIKE '%NEGATIVE_CLAMP%'
                      OR UPPER(COALESCE(notes, '')) LIKE '%NEGATIVE_CLAMP%'
                    THEN ABS(qty_change) ELSE 0
                END
            ), 0) AS clamp_abs_qty
        FROM stock_ledger
        WHERE event_date <= ?
        GROUP BY sku_id
        """,
        (snapshot_date,),
    ).fetchall():
        stats[str(row["sku_id"])] = {
            "ledger_balance": int(row["ledger_balance"] or 0),
            "latest_ledger_event_date": str(row["latest_ledger_event_date"] or ""),
            "ledger_event_count": int(row["ledger_event_count"] or 0),
            "ledger_abs_qty": int(row["ledger_abs_qty"] or 0),
            "clamp_event_count": int(row["clamp_event_count"] or 0),
            "clamp_abs_qty": int(row["clamp_abs_qty"] or 0),
        }
    return stats


def _manual_manifest_paths(paths: Iterable[Path] | None, *, include_defaults: bool) -> list[Path]:
    if paths is not None:
        return [path.expanduser() for path in paths]
    if not include_defaults:
        return []
    return sorted(APPROVED_MANIFEST_DIR.glob("*.approved.json"))


def _load_manual_count_latest(
    conn: sqlite3.Connection,
    *,
    manifest_paths: list[Path],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}

    for manifest_path in manifest_paths:
        resolved_path = manifest_path if manifest_path.is_absolute() else PROJECT_ROOT / manifest_path
        manifest = load_approved_manual_stock_manifest(resolved_path)
        batch_id = str(manifest.get("batch_id") or "")
        for aggregate in aggregate_manual_stock_counts(manifest):
            for sku_id in aggregate.applies_to_sku_ids:
                event_ts = str(aggregate.count_timestamp_at_almaty)
                candidate = {
                    "latest_count_date": event_ts[:10],
                    "latest_count_at": event_ts,
                    "latest_count_source": f"manual_manifest:{batch_id}",
                    "latest_count_quantity": int(aggregate.quantity),
                }
                current = latest.get(str(sku_id))
                if current is None or str(candidate["latest_count_at"]) > str(current["latest_count_at"]):
                    latest[str(sku_id)] = candidate

    if _table_exists(conn, "stock_ledger"):
        for row in conn.execute(
            """
            SELECT
                sku_id,
                MAX(event_date) AS latest_count_date,
                COUNT(*) AS ocr_count_rows,
                COALESCE(SUM(qty_change), 0) AS ocr_qty_delta
            FROM stock_ledger
            WHERE input_source = ?
            GROUP BY sku_id
            """,
            (OCR_INPUT_SOURCE,),
        ).fetchall():
            sku_id = str(row["sku_id"] or "")
            event_date = str(row["latest_count_date"] or "")
            candidate = {
                "latest_count_date": event_date,
                "latest_count_at": event_date,
                "latest_count_source": OCR_INPUT_SOURCE,
                "latest_count_quantity": int(row["ocr_qty_delta"] or 0),
                "ocr_count_rows": int(row["ocr_count_rows"] or 0),
            }
            current = latest.get(sku_id)
            if current is None or str(candidate["latest_count_at"]) > str(current["latest_count_at"]):
                latest[sku_id] = candidate

    return latest


def _load_open_exceptions(conn: sqlite3.Connection) -> list[dict[str, str]]:
    if not _table_exists(conn, "exception_queue"):
        return []
    rows = []
    for row in conn.execute(
        """
        SELECT exception_id, severity, status, reason, evidence_json
        FROM exception_queue
        """
    ).fetchall():
        status = str(row["status"] or "").upper()
        if status not in OPEN_EXCEPTION_STATUSES:
            continue
        rows.append(
            {
                "exception_id": str(row["exception_id"] or ""),
                "severity": str(row["severity"] or "").upper(),
                "status": status,
                "reason": str(row["reason"] or ""),
                "evidence_json": str(row["evidence_json"] or ""),
            }
        )
    return rows


def _exception_stats_for_row(row: ActiveSkuSize, exceptions: list[dict[str, str]]) -> dict[str, Any]:
    haystack_keys = [row.sku_id, row.sku_key]
    matched: list[dict[str, str]] = []
    for exc in exceptions:
        text = f"{exc['reason']}\n{exc['evidence_json']}"
        if any(key and key in text for key in haystack_keys):
            matched.append(exc)
    high_count = sum(1 for exc in matched if exc["severity"] in {"HIGH", "CRITICAL"})
    medium_count = sum(1 for exc in matched if exc["severity"] in {"MEDIUM", "WARN", "WARNING"})
    low_count = max(0, len(matched) - high_count - medium_count)
    if high_count:
        factor = 0.4
    elif medium_count:
        factor = 0.65
    elif low_count:
        factor = 0.8
    else:
        factor = 1.0
    return {
        "open_exception_count": len(matched),
        "high_exception_count": high_count,
        "medium_exception_count": medium_count,
        "quarantine_factor": factor,
        "exception_ids": ";".join(exc["exception_id"] for exc in matched[:5]),
    }


def _score_row(
    active: ActiveSkuSize,
    *,
    as_of: date,
    snapshot_date: str,
    snapshot: sqlite3.Row | None,
    ledger: dict[str, Any],
    count: dict[str, Any] | None,
    exception_stats: dict[str, Any],
) -> dict[str, Any]:
    snapshot_present = snapshot is not None
    current_stock = int(snapshot["current_stock"]) if snapshot_present else 0
    inbound_stock = int(snapshot["inbound_stock"]) if snapshot_present else 0
    ledger_balance = int(ledger.get("ledger_balance", 0))
    discrepancy_units = current_stock - ledger_balance if snapshot_present else ""
    discrepancy_abs = abs(int(discrepancy_units)) if snapshot_present else ""

    count_date = str((count or {}).get("latest_count_date") or "")
    latest_ledger_event_date = str(ledger.get("latest_ledger_event_date") or "")
    count_freshness_days = _days_between(as_of, count_date)
    ledger_freshness_days = _days_between(as_of, latest_ledger_event_date)
    snapshot_freshness_days = _days_between(as_of, snapshot_date if snapshot_present else "")

    count_factor = _factor_from_days(
        count_freshness_days,
        ((7, 1.0), (14, 0.85), (30, 0.7), (3650, 0.5)),
        missing=0.45,
    )
    ledger_factor = _factor_from_days(
        ledger_freshness_days,
        ((2, 1.0), (7, 0.9), (14, 0.75), (3650, 0.6)),
        missing=0.5,
    )
    snapshot_factor = _factor_from_days(
        snapshot_freshness_days,
        ((2, 1.0), (7, 0.9), (14, 0.75), (3650, 0.5)),
        missing=0.2,
    )

    if not snapshot_present:
        discrepancy_factor = 0.2
    elif discrepancy_abs == 0:
        discrepancy_factor = 1.0
    else:
        denominator = max(abs(current_stock), abs(ledger_balance), 1)
        discrepancy_factor = max(0.15, round(1.0 - min(0.85, discrepancy_abs / denominator), 4))

    clamp_abs_qty = int(ledger.get("clamp_abs_qty", 0))
    ledger_abs_qty = int(ledger.get("ledger_abs_qty", 0))
    clamp_share = round(clamp_abs_qty / max(ledger_abs_qty, clamp_abs_qty, 1), 6) if clamp_abs_qty else 0.0
    clamp_factor = max(0.2, round(1.0 - min(0.8, clamp_share), 4)) if clamp_abs_qty else 1.0

    score = round(
        100.0
        * count_factor
        * ledger_factor
        * snapshot_factor
        * discrepancy_factor
        * float(exception_stats["quarantine_factor"])
        * clamp_factor,
        1,
    )
    band = _confidence_band(score)
    notes: list[str] = []
    if not snapshot_present:
        notes.append("missing_snapshot")
    if count_date == "":
        notes.append("missing_manual_count")
    if latest_ledger_event_date == "":
        notes.append("missing_ledger")
    if snapshot_present and current_stock < 0:
        notes.append("negative_stock")
    if snapshot_present and discrepancy_abs:
        notes.append("ledger_snapshot_discrepancy")
    if exception_stats["open_exception_count"]:
        notes.append("open_exception")
    if clamp_abs_qty:
        notes.append("negative_clamp_history")
    if count_freshness_days is not None and count_freshness_days > 7:
        notes.append("count_stale_gt_7d")
    if ledger_freshness_days is not None and ledger_freshness_days > 2:
        notes.append("ledger_stale_gt_2d")

    price_upload_gate = (
        "ALLOW"
        if band == "GREEN"
        and snapshot_present
        and current_stock >= 0
        and discrepancy_abs == 0
        and exception_stats["high_exception_count"] == 0
        else "HOLD"
    )
    ads_gate = "ALLOW" if price_upload_gate == "ALLOW" and current_stock > 0 else "HOLD"
    liquidation_gate = (
        "ALLOW"
        if score >= YELLOW_SCORE
        and snapshot_present
        and current_stock > 0
        and exception_stats["high_exception_count"] == 0
        else "HOLD"
    )

    return {
        "sku_id": active.sku_id,
        "sku_key": active.sku_key,
        "my_size": active.my_size,
        "model": active.model,
        "color": active.color,
        "product_type": active.product_type,
        "category": active.category,
        "gender": active.gender,
        "snapshot_date": snapshot_date if snapshot_present else "",
        "snapshot_present": str(snapshot_present).lower(),
        "current_stock": current_stock if snapshot_present else "",
        "inbound_stock": inbound_stock if snapshot_present else "",
        "ledger_balance": ledger_balance,
        "discrepancy_units": discrepancy_units,
        "discrepancy_abs": discrepancy_abs,
        "latest_count_date": count_date,
        "latest_count_source": str((count or {}).get("latest_count_source") or ""),
        "count_freshness_days": count_freshness_days if count_freshness_days is not None else "",
        "latest_ledger_event_date": latest_ledger_event_date,
        "ledger_freshness_days": ledger_freshness_days if ledger_freshness_days is not None else "",
        "ledger_event_count": int(ledger.get("ledger_event_count", 0)),
        "clamp_event_count": int(ledger.get("clamp_event_count", 0)),
        "clamp_abs_qty": clamp_abs_qty,
        "clamp_share": clamp_share,
        "open_exception_count": int(exception_stats["open_exception_count"]),
        "high_exception_count": int(exception_stats["high_exception_count"]),
        "exception_ids": str(exception_stats["exception_ids"]),
        "snapshot_factor": snapshot_factor,
        "count_factor": count_factor,
        "ledger_factor": ledger_factor,
        "discrepancy_factor": discrepancy_factor,
        "quarantine_factor": float(exception_stats["quarantine_factor"]),
        "clamp_factor": clamp_factor,
        "confidence_score": score,
        "confidence_band": band,
        "price_upload_gate": price_upload_gate,
        "ads_gate": ads_gate,
        "liquidation_gate": liquidation_gate,
        "notes": ";".join(notes),
    }


def _spot_check_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(candidate: dict[str, Any] | None) -> None:
        if candidate is None:
            return
        sku_id = str(candidate["sku_id"])
        if sku_id in seen:
            return
        selected.append(candidate)
        seen.add(sku_id)

    add(next((row for row in rows if row["snapshot_present"] == "false"), None))
    add(next((row for row in rows if row["current_stock"] != "" and int(row["current_stock"]) < 0), None))
    add(max((row for row in rows if row["discrepancy_abs"] != ""), key=lambda row: int(row["discrepancy_abs"]), default=None))
    add(max(rows, key=lambda row: (float(row["clamp_share"]), str(row["sku_id"])), default=None))
    for row in sorted(rows, key=lambda item: (float(item["confidence_score"]), str(item["sku_id"]))):
        add(row)
        if len(selected) >= 5:
            break
    return selected[:5]


def _summarize(rows: list[dict[str, Any]], *, as_of: date, snapshot_date: str, db_path: Path) -> dict[str, Any]:
    by_band = {band: sum(1 for row in rows if row["confidence_band"] == band) for band in ("GREEN", "YELLOW", "RED")}
    return {
        "status": "OK",
        "as_of_date": as_of.isoformat(),
        "db_path": str(db_path),
        "db_sha256": _file_sha256(db_path),
        "latest_snapshot_date": snapshot_date,
        "active_sku_size_rows": len(rows),
        "score_rows": len(rows),
        "missing_score_rows": 0,
        "snapshot_missing_rows": sum(1 for row in rows if row["snapshot_present"] == "false"),
        "negative_stock_rows": sum(1 for row in rows if row["current_stock"] != "" and int(row["current_stock"]) < 0),
        "discrepancy_rows": sum(1 for row in rows if row["discrepancy_abs"] != "" and int(row["discrepancy_abs"]) != 0),
        "open_exception_rows": sum(1 for row in rows if int(row["open_exception_count"]) > 0),
        "clamp_history_rows": sum(1 for row in rows if int(row["clamp_event_count"]) > 0),
        "confidence_band_counts": by_band,
        "price_upload_gate_allow_rows": sum(1 for row in rows if row["price_upload_gate"] == "ALLOW"),
        "price_upload_gate_hold_rows": sum(1 for row in rows if row["price_upload_gate"] == "HOLD"),
        "ads_gate_allow_rows": sum(1 for row in rows if row["ads_gate"] == "ALLOW"),
        "ads_gate_hold_rows": sum(1 for row in rows if row["ads_gate"] == "HOLD"),
        "liquidation_gate_allow_rows": sum(1 for row in rows if row["liquidation_gate"] == "ALLOW"),
        "liquidation_gate_hold_rows": sum(1 for row in rows if row["liquidation_gate"] == "HOLD"),
        "gate_complete_for_g_stock_05": True,
    }


def _write_closeout(path: Path, summary: dict[str, Any], output_files: dict[str, str]) -> None:
    lines = [
        "# Stock Truth Confidence Export",
        "",
        f"- Status: {summary['status']}",
        f"- As of: {summary['as_of_date']}",
        f"- Latest snapshot: {summary['latest_snapshot_date']}",
        f"- Active SKU-size rows scored: {summary['score_rows']} / {summary['active_sku_size_rows']}",
        f"- Missing score rows: {summary['missing_score_rows']}",
        f"- Confidence bands: {summary['confidence_band_counts']}",
        f"- Price gate allow/hold: {summary['price_upload_gate_allow_rows']} / {summary['price_upload_gate_hold_rows']}",
        f"- Ads gate allow/hold: {summary['ads_gate_allow_rows']} / {summary['ads_gate_hold_rows']}",
        f"- Liquidation gate allow/hold: {summary['liquidation_gate_allow_rows']} / {summary['liquidation_gate_hold_rows']}",
        "",
        "## Outputs",
    ]
    for name, value in output_files.items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_stock_truth_confidence(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: date | None = None,
    output_root: Path | None = None,
    current_root: Path | None = DEFAULT_CURRENT_ROOT,
    manifest_paths: list[Path] | None = None,
    include_default_manifests: bool = True,
) -> dict[str, Any]:
    as_of_date = as_of or datetime.now(ALMATY).date()
    run_id = datetime.now(ALMATY).strftime("%Y%m%d_%H%M%S")
    if output_root is None:
        output_root = DEFAULT_OUTPUT_ROOT / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    with _connect_readonly(db_path) as conn:
        active_rows = _load_active_sku_sizes(conn)
        snapshot_date = _latest_snapshot_date(conn, as_of_date)
        snapshot_rows = _load_snapshot_rows(conn, snapshot_date)
        ledger_stats = _load_ledger_stats(conn, snapshot_date)
        count_latest = _load_manual_count_latest(
            conn,
            manifest_paths=_manual_manifest_paths(manifest_paths, include_defaults=include_default_manifests),
        )
        open_exceptions = _load_open_exceptions(conn)

        rows = [
            _score_row(
                active,
                as_of=as_of_date,
                snapshot_date=snapshot_date,
                snapshot=snapshot_rows.get(active.sku_id),
                ledger=ledger_stats.get(active.sku_id, {}),
                count=count_latest.get(active.sku_id),
                exception_stats=_exception_stats_for_row(active, open_exceptions),
            )
            for active in active_rows
        ]

    spot_rows = _spot_check_rows(rows)
    summary = _summarize(rows, as_of=as_of_date, snapshot_date=snapshot_date, db_path=db_path)

    score_csv = output_root / "stock_truth_confidence.csv"
    score_json = output_root / "stock_truth_confidence.json"
    spot_csv = output_root / "spot_check.csv"
    summary_json = output_root / "summary.json"
    closeout_md = output_root / "closeout.md"
    _write_csv(score_csv, rows)
    _write_json(score_json, {"summary": summary, "rows": rows})
    _write_csv(spot_csv, spot_rows)
    _write_json(summary_json, summary)

    output_files = {
        "score_csv": str(score_csv),
        "score_json": str(score_json),
        "spot_check_csv": str(spot_csv),
        "summary_json": str(summary_json),
        "closeout_md": str(closeout_md),
    }
    _write_closeout(closeout_md, summary, output_files)

    if current_root is not None:
        current_root.mkdir(parents=True, exist_ok=True)
        latest_csv = current_root / "stock_truth_confidence_latest.csv"
        latest_json = current_root / "stock_truth_confidence_latest.json"
        latest_summary = current_root / "summary_latest.json"
        shutil.copyfile(score_csv, latest_csv)
        shutil.copyfile(score_json, latest_json)
        shutil.copyfile(summary_json, latest_summary)
        output_files.update(
            {
                "latest_score_csv": str(latest_csv),
                "latest_score_json": str(latest_json),
                "latest_summary_json": str(latest_summary),
            }
        )

    summary["output_files"] = output_files
    _write_json(summary_json, summary)
    if current_root is not None:
        _write_json(current_root / "summary_latest.json", summary)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", type=str, default="")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--current-root", type=Path, default=DEFAULT_CURRENT_ROOT)
    parser.add_argument("--no-current", action="store_true", help="Do not update exports/current latest copies")
    parser.add_argument("--manual-manifest", type=Path, action="append", default=None)
    parser.add_argument("--no-default-manifests", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print summary JSON")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    as_of_date = date.fromisoformat(args.as_of) if args.as_of else None
    summary = export_stock_truth_confidence(
        db_path=args.db,
        as_of=as_of_date,
        output_root=args.output_root,
        current_root=None if args.no_current else args.current_root,
        manifest_paths=args.manual_manifest,
        include_default_manifests=not args.no_default_manifests,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "stock_truth_confidence "
            f"status={summary['status']} "
            f"score_rows={summary['score_rows']} "
            f"active_rows={summary['active_sku_size_rows']} "
            f"missing_score_rows={summary['missing_score_rows']} "
            f"latest_snapshot_date={summary['latest_snapshot_date']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
