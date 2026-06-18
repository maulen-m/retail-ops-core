#!/usr/bin/env python3
"""Narrow repair for workbook-anchor date drift in sales_fact_v2.

The repair is intentionally smaller than a sales_fact_v2 rebuild: it derives
date-drift candidates from the workbook-anchor classifier, selects only the
subset needed to clear the daily workbook overage class, and may mutate only
sales_fact_v2.order_date.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views  # noqa: E402
from scripts.classify_workbook_anchor_overages import (  # noqa: E402
    classify_workbook_anchor_overages,
)
from scripts.validate_sales_against_workbook import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    load_daily_source,
    parse_workbook_daily_totals,
    validate_sales_against_workbook,
)

ENV_GATE = "ENABLE_WORKBOOK_ANCHOR_DATE_DRIFT_REPAIR"
ALLOWED_BUCKETS = {"KASPI_REBUILD_DATE_DRIFT", "INTERNAL_SOURCE_DATE_DRIFT"}
ALLOWED_PAIR_STATUSES = {"ORDER_IN_WB_OTHER_DAY"}
ALLOWED_SOURCE_FILES = {
    "KASPI_API_ENTRIES_REBUILD",
    "KASPI_API_HEADER_FALLBACK_REBUILD",
}
DEFAULT_TOL_PCT = 5.0
UNIT_OVERAGE_WEIGHT_KZT = 10_000.0


class DateDriftRepairError(RuntimeError):
    """Raised when the date-drift repair cannot proceed safely."""


@dataclass(frozen=True)
class Candidate:
    index: int
    source_date: str
    order_id: str
    store_code: str
    source_file: str
    published_units: float
    published_net_rev_kzt: float
    workbook_dates: tuple[str, ...]
    sale_ids: tuple[int, ...]


@dataclass(frozen=True)
class Move:
    candidate: Candidate
    target_date: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect_readonly(path)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _sqlite_backup(src_path: Path, dst_path: Path) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect_readonly(src_path)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity = _sqlite_integrity_check(dst_path)
    if integrity.lower() != "ok":
        raise DateDriftRepairError(f"backup integrity_check failed for {dst_path}: {integrity}")
    return dst_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise DateDriftRepairError(f"expected classifier CSV missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _safe_float(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    return float(text)


def _safe_int(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    return int(float(text))


def _round2(value: float) -> float:
    return round(float(value or 0.0), 2)


def _assert_close(label: str, observed: float, expected: float) -> None:
    if abs(_round2(observed) - _round2(expected)) > 0.01:
        raise DateDriftRepairError(
            f"{label} mismatch: observed={_round2(observed)} expected={_round2(expected)}"
        )


def _normalize_date_set(raw: str) -> tuple[str, ...]:
    dates = tuple(sorted(part.strip() for part in str(raw or "").split("|") if part.strip()))
    if not dates:
        raise DateDriftRepairError("candidate has no workbook_dates")
    for value in dates:
        date.fromisoformat(value)
    return dates


def _make_validation_copy(db_path: Path, output_dir: Path, name: str) -> Path:
    return _sqlite_backup(db_path, output_dir / "_validation_copies" / name)


def _run_classifier_on_copy(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str,
    start: str,
    end: str,
    output_dir: Path,
) -> dict[str, Any]:
    classifier_db = _make_validation_copy(db_path, output_dir, "classifier_input.db")
    return classify_workbook_anchor_overages(
        db_path=classifier_db,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        start=start,
        end=end,
        output_dir=output_dir / "classifier_before",
        strict=True,
    )


def _validate_pre_classifier_contract(
    *,
    report: dict[str, Any],
    expected_error_references: int,
    expected_failing_dates: int,
    expected_unresolved_error_references: int,
    expected_units_overage: float,
    expected_net_overage_kzt: float,
) -> dict[str, Any]:
    if not report.get("ok"):
        raise DateDriftRepairError(f"classifier did not pass: {report.get('errors')}")
    checks = {
        "error_references_total": int(report.get("error_references_total") or 0),
        "unique_failing_dates": int(report.get("unique_failing_dates") or 0),
        "unresolved_error_references": int(report.get("unresolved_error_references") or 0),
    }
    expected = {
        "error_references_total": int(expected_error_references),
        "unique_failing_dates": int(expected_failing_dates),
        "unresolved_error_references": int(expected_unresolved_error_references),
    }
    for key, observed in checks.items():
        if observed != expected[key]:
            raise DateDriftRepairError(f"{key} mismatch: observed={observed} expected={expected[key]}")

    outputs = report.get("outputs") or {}
    days_rows = _read_csv_dicts(Path(outputs["workbook_overage_days_csv"]))
    source_mix_rows = _read_csv_dicts(Path(outputs["workbook_overage_source_mix_csv"]))
    lineage_rows = _read_csv_dicts(Path(outputs["workbook_overage_order_lineage_csv"]))

    units_overage = sum(_safe_float(row.get("units_overage")) for row in days_rows)
    net_overage = sum(_safe_float(row.get("net_overage_kzt")) for row in days_rows)
    _assert_close("units_overage", units_overage, expected_units_overage)
    _assert_close("net_overage_kzt", net_overage, expected_net_overage_kzt)

    source_buckets = {str(row.get("bucket") or "").strip().upper() for row in source_mix_rows}
    source_pair_statuses = {str(row.get("pair_status") or "").strip().upper() for row in source_mix_rows}
    source_files = {str(row.get("source_file") or "").strip().upper() for row in source_mix_rows}
    unexpected_buckets = sorted(source_buckets - ALLOWED_BUCKETS)
    unexpected_pairs = sorted(source_pair_statuses - ALLOWED_PAIR_STATUSES)
    unexpected_sources = sorted(source_files - ALLOWED_SOURCE_FILES)
    if unexpected_buckets:
        raise DateDriftRepairError(f"unexpected classifier buckets: {unexpected_buckets}")
    if unexpected_pairs:
        raise DateDriftRepairError(f"unexpected classifier pair statuses: {unexpected_pairs}")
    if unexpected_sources:
        raise DateDriftRepairError(f"unexpected classifier source_file values: {unexpected_sources}")

    return {
        "days_rows": days_rows,
        "source_mix_rows": source_mix_rows,
        "lineage_rows": lineage_rows,
        "units_overage": _round2(units_overage),
        "net_overage_kzt": _round2(net_overage),
        "source_buckets": sorted(source_buckets),
        "source_pair_statuses": sorted(source_pair_statuses),
        "source_files": sorted(source_files),
    }


def _load_candidate_rows(conn: sqlite3.Connection, lineage_rows: list[dict[str, str]]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for idx, row in enumerate(lineage_rows):
        pair_status = str(row.get("pair_status") or "").strip().upper()
        bucket = str(row.get("bucket") or "").strip().upper()
        source_file = str(row.get("source_file") or "").strip().upper()
        if pair_status not in ALLOWED_PAIR_STATUSES:
            continue
        if bucket not in ALLOWED_BUCKETS:
            continue
        if source_file not in ALLOWED_SOURCE_FILES:
            continue

        order_id = str(row.get("order_id") or "").strip()
        source_date = str(row.get("date") or "").strip()
        store_code = str(row.get("store_code") or "").strip().upper()
        workbook_dates = _normalize_date_set(str(row.get("workbook_dates") or ""))
        if not order_id or not source_date or not store_code:
            raise DateDriftRepairError(f"incomplete candidate lineage row: {row}")
        date.fromisoformat(source_date)

        db_rows = conn.execute(
            """
            SELECT
                sale_id,
                COALESCE(quantity, 0),
                COALESCE(net_rev, 0)
            FROM sales_fact_v2
            WHERE CAST(order_id AS TEXT) = ?
              AND date(order_date) = ?
              AND UPPER(COALESCE(store_code, '')) = ?
              AND UPPER(COALESCE(source_file, '')) = ?
              AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0
            ORDER BY sale_id
            """,
            (order_id, source_date, store_code, source_file),
        ).fetchall()
        if not db_rows:
            raise DateDriftRepairError(
                f"no sales_fact_v2 rows for candidate order={order_id} store={store_code} date={source_date}"
            )
        sale_ids = tuple(int(db_row[0]) for db_row in db_rows)
        db_units = _round2(sum(float(db_row[1] or 0.0) for db_row in db_rows))
        db_net = _round2(sum(float(db_row[2] or 0.0) for db_row in db_rows))
        lineage_units = _round2(_safe_float(row.get("published_units")))
        lineage_net = _round2(_safe_float(row.get("published_net_rev_kzt")))
        _assert_close(f"candidate {order_id} units", db_units, lineage_units)
        _assert_close(f"candidate {order_id} net_rev", db_net, lineage_net)
        candidates.append(
            Candidate(
                index=idx,
                source_date=source_date,
                order_id=order_id,
                store_code=store_code,
                source_file=source_file,
                published_units=db_units,
                published_net_rev_kzt=db_net,
                workbook_dates=workbook_dates,
                sale_ids=sale_ids,
            )
        )
    if not candidates:
        raise DateDriftRepairError("no allowed date-drift candidates were derived from classifier lineage")
    return candidates


def _date_range(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    out: list[str] = []
    while current <= final:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def _load_daily_maps(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str,
    as_of: str,
    output_dir: Path,
    tol_pct: float,
) -> dict[str, Any]:
    validator_db = _make_validation_copy(db_path, output_dir, "daily_maps.db")
    report = validate_sales_against_workbook(
        db_path=validator_db,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        as_of=as_of,
        days=14,
        tol_pct=tol_pct,
        min_overlap_days=1,
        max_lag_days=366,
        output_dir=None,
    )
    if not report.get("window_start") or not report.get("window_end"):
        raise DateDriftRepairError("validator did not produce a daily window")
    workbook_daily = parse_workbook_daily_totals(workbook_path, sheet_name=sheet_name)
    conn = sqlite3.connect(str(validator_db))
    try:
        ensure_sales_truth_views(conn)
        published_daily = load_daily_source(conn, "published_truth")
    finally:
        conn.close()

    window_dates = _date_range(str(report["window_start"]), str(report["window_end"]))
    units = {day: _round2(float(published_daily.get(day, {}).get("units", 0.0))) for day in window_dates}
    net = {
        day: _round2(float(published_daily.get(day, {}).get("net_rev_kzt", 0.0)))
        for day in window_dates
    }
    workbook_units = {
        day: _round2(float(workbook_daily.get(day, {}).get("units", 0.0))) for day in window_dates
    }
    workbook_net = {
        day: _round2(float(workbook_daily.get(day, {}).get("net_rev_kzt", 0.0)))
        for day in window_dates
    }
    return {
        "report": report,
        "window_dates": window_dates,
        "units": units,
        "net": net,
        "workbook_units": workbook_units,
        "workbook_net": workbook_net,
    }


def _overage_for_day(
    day: str,
    *,
    units: dict[str, float],
    net: dict[str, float],
    workbook_units: dict[str, float],
    workbook_net: dict[str, float],
    tol_pct: float,
) -> tuple[float, float]:
    multiplier = 1.0 + float(tol_pct) / 100.0
    units_over = max(0.0, _round2(units[day] - workbook_units[day] * multiplier))
    net_over = max(0.0, _round2(net[day] - workbook_net[day] * multiplier))
    return units_over, net_over


def _failing_days(
    *,
    window_dates: list[str],
    units: dict[str, float],
    net: dict[str, float],
    workbook_units: dict[str, float],
    workbook_net: dict[str, float],
    tol_pct: float,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for day in window_dates:
        units_over, net_over = _overage_for_day(
            day,
            units=units,
            net=net,
            workbook_units=workbook_units,
            workbook_net=workbook_net,
            tol_pct=tol_pct,
        )
        if units_over > 0.0 or net_over > 0.0:
            failures.append(
                {
                    "date": day,
                    "published_units": units[day],
                    "workbook_units": workbook_units[day],
                    "units_overage": units_over,
                    "published_net_rev_kzt": net[day],
                    "workbook_net_rev_kzt": workbook_net[day],
                    "net_overage_kzt": net_over,
                }
            )
    return failures


def _select_moves(
    *,
    candidates: list[Candidate],
    daily_maps: dict[str, Any],
    tol_pct: float,
) -> tuple[list[Move], list[dict[str, Any]], list[dict[str, Any]]]:
    window_dates: list[str] = list(daily_maps["window_dates"])
    units = dict(daily_maps["units"])
    net = dict(daily_maps["net"])
    workbook_units = dict(daily_maps["workbook_units"])
    workbook_net = dict(daily_maps["workbook_net"])
    before_failures = _failing_days(
        window_dates=window_dates,
        units=units,
        net=net,
        workbook_units=workbook_units,
        workbook_net=workbook_net,
        tol_pct=tol_pct,
    )

    moved: list[Move] = []
    moved_indexes: set[int] = set()
    by_source = sorted({candidate.source_date for candidate in candidates})
    for source_day in by_source:
        if source_day not in units:
            continue
        while True:
            source_units_over, source_net_over = _overage_for_day(
                source_day,
                units=units,
                net=net,
                workbook_units=workbook_units,
                workbook_net=workbook_net,
                tol_pct=tol_pct,
            )
            if source_units_over <= 0.0 and source_net_over <= 0.0:
                break

            scored: list[tuple[float, float, str, str, Candidate, str]] = []
            source_candidates = [
                candidate
                for candidate in candidates
                if candidate.source_date == source_day and candidate.index not in moved_indexes
            ]
            for candidate in source_candidates:
                feasible_targets: list[tuple[int, str]] = []
                for target_day in candidate.workbook_dates:
                    if target_day not in units:
                        feasible_targets.append((0, target_day))
                        continue
                    next_units = units[target_day] + candidate.published_units
                    next_net = net[target_day] + candidate.published_net_rev_kzt
                    multiplier = 1.0 + float(tol_pct) / 100.0
                    if (
                        next_units <= workbook_units[target_day] * multiplier + 1e-6
                        and next_net <= workbook_net[target_day] * multiplier + 1e-6
                    ):
                        feasible_targets.append((1, target_day))
                if not feasible_targets:
                    continue
                target_day = sorted(feasible_targets, key=lambda item: (item[0], item[1]))[0][1]
                contribution = min(candidate.published_net_rev_kzt, source_net_over) + (
                    UNIT_OVERAGE_WEIGHT_KZT * min(candidate.published_units, source_units_over)
                )
                scored.append(
                    (
                        -contribution,
                        -candidate.published_net_rev_kzt,
                        candidate.order_id,
                        candidate.store_code,
                        candidate,
                        target_day,
                    )
                )

            if not scored:
                raise DateDriftRepairError(
                    "no feasible target capacity for source day "
                    f"{source_day}: units_overage={source_units_over} net_overage_kzt={source_net_over}"
                )

            _score, _net_score, _order, _store, selected, target_day = sorted(scored)[0]
            units[source_day] = _round2(units[source_day] - selected.published_units)
            net[source_day] = _round2(net[source_day] - selected.published_net_rev_kzt)
            if target_day in units:
                units[target_day] = _round2(units[target_day] + selected.published_units)
                net[target_day] = _round2(net[target_day] + selected.published_net_rev_kzt)
            moved.append(Move(candidate=selected, target_date=target_day))
            moved_indexes.add(selected.index)

    after_failures = _failing_days(
        window_dates=window_dates,
        units=units,
        net=net,
        workbook_units=workbook_units,
        workbook_net=workbook_net,
        tol_pct=tol_pct,
    )
    if after_failures:
        raise DateDriftRepairError(f"selected moves do not clear workbook-anchor daily failures: {after_failures}")
    if not moved:
        raise DateDriftRepairError("selected move set is empty")
    return moved, before_failures, after_failures


def _candidate_dict(candidate: Candidate, *, target_date: str | None = None) -> dict[str, Any]:
    payload = {
        "order_id": candidate.order_id,
        "store_code": candidate.store_code,
        "source_file": candidate.source_file,
        "before_date": candidate.source_date,
        "published_units": candidate.published_units,
        "published_net_rev_kzt": candidate.published_net_rev_kzt,
        "workbook_dates": "|".join(candidate.workbook_dates),
        "sale_ids": "|".join(str(sale_id) for sale_id in candidate.sale_ids),
    }
    if target_date is not None:
        payload["target_date"] = target_date
    return payload


def _write_moves_csv(path: Path, moves: list[Move]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "order_id",
        "store_code",
        "source_file",
        "before_date",
        "target_date",
        "published_units",
        "published_net_rev_kzt",
        "workbook_dates",
        "sale_ids",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for move in moves:
            writer.writerow(_candidate_dict(move.candidate, target_date=move.target_date))


def _fetch_rows_by_sale_ids(conn: sqlite3.Connection, sale_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not sale_ids:
        return {}
    placeholders = ",".join("?" for _ in sale_ids)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(sales_fact_v2)").fetchall()]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM sales_fact_v2 WHERE sale_id IN ({placeholders})",
        sale_ids,
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for raw in rows:
        payload = dict(zip(cols, raw))
        out[int(payload["sale_id"])] = payload
    return out


def _apply_moves_to_db(conn: sqlite3.Connection, moves: list[Move]) -> int:
    sale_ids = sorted({sale_id for move in moves for sale_id in move.candidate.sale_ids})
    before = _fetch_rows_by_sale_ids(conn, sale_ids)
    expected_count = len(sale_ids)
    if len(before) != expected_count:
        raise DateDriftRepairError(f"sale_id readback mismatch before update: {len(before)} != {expected_count}")

    updated = 0
    for move in moves:
        for sale_id in move.candidate.sale_ids:
            result = conn.execute(
                """
                UPDATE sales_fact_v2
                SET order_date = ?
                WHERE sale_id = ?
                  AND date(order_date) = ?
                """,
                (move.target_date, sale_id, move.candidate.source_date),
            )
            if result.rowcount != 1:
                raise DateDriftRepairError(
                    f"unexpected update count for sale_id={sale_id}: {result.rowcount}"
                )
            updated += result.rowcount

    after = _fetch_rows_by_sale_ids(conn, sale_ids)
    if len(after) != expected_count:
        raise DateDriftRepairError(f"sale_id readback mismatch after update: {len(after)} != {expected_count}")
    target_by_sale_id = {
        sale_id: move.target_date for move in moves for sale_id in move.candidate.sale_ids
    }
    for sale_id, before_row in before.items():
        after_row = after[sale_id]
        for field, before_value in before_row.items():
            after_value = after_row[field]
            if field == "order_date":
                if str(after_value) != str(target_by_sale_id[sale_id]):
                    raise DateDriftRepairError(
                        f"sale_id={sale_id} order_date did not update to {target_by_sale_id[sale_id]}"
                    )
                continue
            if before_value != after_value:
                raise DateDriftRepairError(
                    f"forbidden column mutation for sale_id={sale_id} field={field}: "
                    f"{before_value!r} -> {after_value!r}"
                )
    return updated


def _run_post_validators(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str,
    start: str,
    end: str,
    as_of: str,
    output_dir: Path,
    tol_pct: float,
) -> dict[str, Any]:
    validation_db = _make_validation_copy(db_path, output_dir, "post_validator_input.db")
    validator_report = validate_sales_against_workbook(
        db_path=validation_db,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        as_of=as_of,
        days=14,
        tol_pct=tol_pct,
        min_overlap_days=1,
        max_lag_days=366,
        output_dir=output_dir / "post_sales_vs_workbook_anchor",
    )
    classifier_report = classify_workbook_anchor_overages(
        db_path=validation_db,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        start=start,
        end=end,
        output_dir=output_dir / "classifier_after",
        strict=True,
    )
    if not validator_report.get("ok"):
        raise DateDriftRepairError(f"post-repair workbook validator still failing: {validator_report.get('errors')}")
    if int(classifier_report.get("error_references_total") or 0) != 0:
        raise DateDriftRepairError(f"post-repair classifier still has errors: {classifier_report}")
    return {
        "validator_report": validator_report,
        "classifier_report": classifier_report,
    }


def _apply_moves_to_copy_for_simulation(*, db_path: Path, output_dir: Path, moves: list[Move]) -> Path:
    simulation_db = _sqlite_backup(db_path, output_dir / "simulation_apply.db")
    conn = sqlite3.connect(str(simulation_db))
    try:
        _apply_moves_to_db(conn, moves)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return simulation_db


def _assert_apply_allowed(
    *,
    apply: bool,
    db_path: Path,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
) -> dict[str, Any]:
    pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise DateDriftRepairError(
            f"pre-SHA mismatch: expected {expected_pre_sha256}, observed {pre_sha}"
        )
    if not apply:
        return {"pre_sha256": pre_sha, "backup_path": None, "backup_sha256": None}
    if str(os.environ.get(ENV_GATE) or "").strip() != "1":
        raise DateDriftRepairError(f"{ENV_GATE}=1 is required with --apply")
    if backup_dir is None:
        raise DateDriftRepairError("--backup-dir is required with --apply")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = _sqlite_backup(db_path, backup_dir / f"app_before_workbook_anchor_date_drift_{stamp}.db")
    return {
        "pre_sha256": pre_sha,
        "backup_path": str(backup_path),
        "backup_sha256": _sha256_file(backup_path),
        "backup_integrity_check": _sqlite_integrity_check(backup_path),
    }


def run_repair(
    *,
    db_path: Path,
    workbook_path: Path,
    start: str,
    end: str,
    as_of: str,
    expected_error_references: int,
    expected_failing_dates: int,
    expected_unresolved_error_references: int,
    expected_units_overage: float,
    expected_net_overage_kzt: float,
    output_dir: Path,
    sheet_name: str = DEFAULT_SHEET,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
    apply: bool = False,
    tol_pct: float = DEFAULT_TOL_PCT,
) -> dict[str, Any]:
    if not db_path.exists():
        raise DateDriftRepairError(f"db not found: {db_path}")
    if not workbook_path.exists():
        raise DateDriftRepairError(f"workbook not found: {workbook_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    gate = _assert_apply_allowed(
        apply=apply,
        db_path=db_path,
        expected_pre_sha256=expected_pre_sha256,
        backup_dir=backup_dir,
    )
    classifier_report = _run_classifier_on_copy(
        db_path=db_path,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        start=start,
        end=end,
        output_dir=output_dir,
    )
    classifier_contract = _validate_pre_classifier_contract(
        report=classifier_report,
        expected_error_references=expected_error_references,
        expected_failing_dates=expected_failing_dates,
        expected_unresolved_error_references=expected_unresolved_error_references,
        expected_units_overage=expected_units_overage,
        expected_net_overage_kzt=expected_net_overage_kzt,
    )

    conn = _connect_readonly(db_path)
    try:
        candidates = _load_candidate_rows(conn, classifier_contract["lineage_rows"])
    finally:
        conn.close()

    daily_maps = _load_daily_maps(
        db_path=db_path,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        as_of=as_of,
        output_dir=output_dir,
        tol_pct=tol_pct,
    )
    moves, before_failures, predicted_after_failures = _select_moves(
        candidates=candidates,
        daily_maps=daily_maps,
        tol_pct=tol_pct,
    )
    moves_csv = output_dir / "candidate_moves.csv"
    _write_moves_csv(moves_csv, moves)

    simulation_db = _apply_moves_to_copy_for_simulation(db_path=db_path, output_dir=output_dir, moves=moves)
    simulation_post = _run_post_validators(
        db_path=simulation_db,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        start=start,
        end=end,
        as_of=as_of,
        output_dir=output_dir / "simulation_post",
        tol_pct=tol_pct,
    )

    rows_updated = 0
    post_apply: dict[str, Any] | None = None
    post_sha: str | None = None
    if apply:
        conn = sqlite3.connect(str(db_path))
        try:
            rows_updated = _apply_moves_to_db(conn, moves)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        post_sha = _sha256_file(db_path)
        post_apply = _run_post_validators(
            db_path=db_path,
            workbook_path=workbook_path,
            sheet_name=sheet_name,
            start=start,
            end=end,
            as_of=as_of,
            output_dir=output_dir / "post_apply",
            tol_pct=tol_pct,
        )

    total_units_moved = _round2(sum(move.candidate.published_units for move in moves))
    total_net_moved = _round2(sum(move.candidate.published_net_rev_kzt for move in moves))
    report = {
        "status": "APPLIED" if apply else "DRY_RUN",
        "ok": True,
        "db_path": str(db_path),
        "workbook_path": str(workbook_path),
        "start": start,
        "end": end,
        "as_of": as_of,
        "env_gate": ENV_GATE,
        "apply": apply,
        "gate": gate,
        "post_sha256": post_sha,
        "classifier_before": classifier_report,
        "classifier_contract": {
            key: value
            for key, value in classifier_contract.items()
            if key not in {"lineage_rows", "source_mix_rows", "days_rows"}
        },
        "candidate_count": len(candidates),
        "selected_move_count": len(moves),
        "selected_sale_row_count": sum(len(move.candidate.sale_ids) for move in moves),
        "rows_updated": rows_updated,
        "total_units_moved": total_units_moved,
        "total_net_rev_moved_kzt": total_net_moved,
        "before_failures": before_failures,
        "predicted_after_failures": predicted_after_failures,
        "candidate_moves_csv": str(moves_csv),
        "simulation_db": str(simulation_db),
        "simulation_post": simulation_post,
        "post_apply": post_apply,
    }
    report_path = output_dir / "date_drift_repair_report.json"
    _write_json(report_path, report)
    report["report_json"] = str(report_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply narrow workbook-anchor date-drift repair")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--expected-error-references", type=int, required=True)
    parser.add_argument("--expected-failing-dates", type=int, required=True)
    parser.add_argument("--expected-unresolved-error-references", type=int, required=True)
    parser.add_argument("--expected-units-overage", type=float, required=True)
    parser.add_argument("--expected-net-overage-kzt", type=float, required=True)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tol-pct", type=float, default=DEFAULT_TOL_PCT)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = run_repair(
            db_path=args.db,
            workbook_path=args.workbook,
            sheet_name=args.sheet_name,
            start=args.start,
            end=args.end,
            as_of=args.as_of,
            expected_error_references=args.expected_error_references,
            expected_failing_dates=args.expected_failing_dates,
            expected_unresolved_error_references=args.expected_unresolved_error_references,
            expected_units_overage=args.expected_units_overage,
            expected_net_overage_kzt=args.expected_net_overage_kzt,
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir,
            output_dir=args.output_dir,
            apply=bool(args.apply),
            tol_pct=float(args.tol_pct),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": report["status"],
        "ok": report["ok"],
        "candidate_count": report["candidate_count"],
        "selected_move_count": report["selected_move_count"],
        "selected_sale_row_count": report["selected_sale_row_count"],
        "rows_updated": report["rows_updated"],
        "total_units_moved": report["total_units_moved"],
        "total_net_rev_moved_kzt": report["total_net_rev_moved_kzt"],
        "report_json": report["report_json"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
