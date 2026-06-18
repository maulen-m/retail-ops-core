#!/usr/bin/env python3
"""Validate G-WA-01 internal-cannibalization guard evidence."""

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

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "internal_cannibalization_guard.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "internal_cannibalization_guard"

EVIDENCE_COMPETITOR_COLUMNS = [
    "store_id",
    "store_name",
    "row_id",
    "merchant_sku",
    "kaspi_sku",
    "link",
    "current_price",
    "own_competitor_mid",
    "own_competitor_name",
    "own_competitor_price",
    "not_competitor_present",
    "own_store_undercut",
]

EVIDENCE_SPREAD_COLUMNS = [
    "link",
    "store_prices",
    "min_price",
    "max_price",
    "spread_kzt",
    "stores",
    "merchant_skus",
]

EVIDENCE_LEAD_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "lead_store",
    "matched_store_ids",
    "matched_merchant_skus",
    "non_lead_visible_store_ids",
    "status",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _resolve_project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _store_id_lookup(config: dict[str, Any]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for block in ("managed_pricing_store_ids", "own_store_ids"):
        for name, sid in (config.get(block) or {}).items():
            parsed = _as_int(sid)
            if parsed is not None:
                merged[_norm(name)] = parsed
                merged[str(parsed)] = parsed
    return merged


def _store_name_by_id(config: dict[str, Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for block in ("own_store_ids", "managed_pricing_store_ids"):
        for name, sid in (config.get(block) or {}).items():
            parsed = _as_int(sid)
            if parsed is not None:
                out[parsed] = str(name)
    return out


def _split_stores(raw: str, lookup: dict[str, int]) -> set[int]:
    result: set[int] = set()
    for part in re.split(r"[;,]", str(raw or "")):
        token = part.strip()
        if not token:
            continue
        sid = lookup.get(_norm(token)) or lookup.get(token)
        if sid is not None:
            result.add(int(sid))
    return result


def _load_lead_map(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _connect_readonly(sqlite_path: Path) -> sqlite3.Connection:
    uri = f"file:{sqlite_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_repricer_rows(sqlite_path: Path) -> list[dict[str, Any]]:
    with _connect_readonly(sqlite_path) as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    fetched_at,
                    store_id,
                    store_name,
                    row_id,
                    merchant_sku,
                    kaspi_sku,
                    merchant_title,
                    link,
                    price,
                    min_price,
                    max_price,
                    active,
                    is_available,
                    raw_json
                FROM repricer_items
                """
            ).fetchall()
        ]


def _raw_json(row: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(str(row.get("raw_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _matches_own_name(name: str, config: dict[str, Any]) -> bool:
    norm_name = _norm(name)
    return any(_norm(token) == norm_name for token in config.get("own_store_name_tokens") or [])


def _is_active_available(row: dict[str, Any]) -> bool:
    return _as_int(row.get("active")) == 1 and _as_int(row.get("is_available")) == 1


def _collect_own_competitor_rows(
    rows: list[dict[str, Any]],
    *,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    own_ids = {str(v) for v in (config.get("own_store_ids") or {}).values()}
    evidence: list[dict[str, Any]] = []
    name_warnings: list[dict[str, Any]] = []
    for row in rows:
        if not _is_active_available(row):
            continue
        current_store_id = str(row.get("store_id") or "").strip()
        raw = _raw_json(row)
        not_competitors = {str(v).strip() for v in raw.get("not_competitors") or []}
        current_price = _as_float(row.get("price"))
        for comp in raw.get("competitors") or []:
            if not isinstance(comp, dict):
                continue
            mid = str(comp.get("mid") or "").strip()
            comp_name = str(comp.get("name") or "").strip()
            if mid == current_store_id:
                continue
            is_own_mid = bool(mid and mid in own_ids)
            if not is_own_mid:
                if _matches_own_name(comp_name, config):
                    name_warnings.append(
                        {
                            "store_id": row.get("store_id"),
                            "row_id": row.get("row_id"),
                            "merchant_sku": row.get("merchant_sku"),
                            "own_competitor_mid": mid,
                            "own_competitor_name": comp_name,
                            "warning": "own_store_name_match_without_configured_mid",
                        }
                    )
                continue
            comp_price = _as_float(comp.get("price"))
            undercut = current_price is not None and comp_price is not None and comp_price < current_price
            evidence.append(
                {
                    "store_id": row.get("store_id"),
                    "store_name": row.get("store_name"),
                    "row_id": row.get("row_id"),
                    "merchant_sku": row.get("merchant_sku"),
                    "kaspi_sku": row.get("kaspi_sku"),
                    "link": row.get("link"),
                    "current_price": row.get("price"),
                    "own_competitor_mid": mid,
                    "own_competitor_name": comp_name,
                    "own_competitor_price": comp.get("price"),
                    "not_competitor_present": mid in not_competitors,
                    "own_store_undercut": undercut,
                }
            )
    return evidence, name_warnings


def _collect_shared_spreads(rows: list[dict[str, Any]], managed_ids: set[int]) -> list[dict[str, Any]]:
    by_link: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        store_id = _as_int(row.get("store_id"))
        link = str(row.get("link") or "").strip()
        if store_id not in managed_ids or not link or not _is_active_available(row):
            continue
        by_link.setdefault(link, []).append(row)
    evidence: list[dict[str, Any]] = []
    for link, link_rows in sorted(by_link.items()):
        store_ids = sorted({int(row["store_id"]) for row in link_rows if _as_int(row.get("store_id")) is not None})
        if len(store_ids) < 2:
            continue
        prices = [_as_int(row.get("price")) for row in link_rows]
        clean_prices = [p for p in prices if p is not None]
        if not clean_prices:
            continue
        min_price = min(clean_prices)
        max_price = max(clean_prices)
        if max_price == min_price:
            continue
        evidence.append(
            {
                "link": link,
                "store_prices": ";".join(f"{row.get('store_id')}:{row.get('price')}" for row in link_rows),
                "min_price": min_price,
                "max_price": max_price,
                "spread_kzt": max_price - min_price,
                "stores": ";".join(str(sid) for sid in store_ids),
                "merchant_skus": ";".join(str(row.get("merchant_sku") or "") for row in link_rows),
            }
        )
    return evidence


def _match_tranche(row: dict[str, Any], *, sku_key: str, size: str) -> bool:
    text = f"{row.get('merchant_sku') or ''} {row.get('merchant_title') or ''}".upper()
    sku = str(sku_key or "").strip().upper()
    if not sku or sku not in text:
        return False
    size_text = str(size or "").strip().upper()
    if not size_text or size_text in {"ALL", "*"}:
        return True
    tokens = {size_text, f"_{size_text}_", f"({size_text})"}
    return any(token in text for token in tokens)


def _collect_lead_map_audit(
    *,
    lead_rows: list[dict[str, str]],
    repricer_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookup = _store_id_lookup(config)
    active_statuses = {_norm(v) for v in config.get("active_map_statuses") or ["ACTIVE"]}
    managed_ids = {int(v) for v in (config.get("managed_pricing_store_ids") or {}).values()}
    audit_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(lead_rows, start=2):
        status = _norm(row.get("status"))
        if status not in active_statuses:
            continue
        sku_key = str(row.get("sku_key") or "").strip()
        size = str(row.get("size") or "").strip()
        key = (_norm(sku_key), _norm(size))
        row_errors: list[str] = []
        if not sku_key:
            row_errors.append("sku_key missing")
        if not size:
            row_errors.append("size missing")
        if key in seen_keys:
            row_errors.append("duplicate active sku_key/size")
        seen_keys.add(key)

        lead_store = str(row.get("lead_store") or "").strip()
        lead_store_id = lookup.get(_norm(lead_store)) or lookup.get(lead_store)
        if lead_store_id is None:
            row_errors.append("lead_store unknown")
        allowed_followers = _split_stores(str(row.get("allowed_follower_stores") or ""), lookup)
        matched = [
            mrow
            for mrow in repricer_rows
            if _is_active_available(mrow)
            and _as_int(mrow.get("store_id")) in managed_ids
            and _match_tranche(mrow, sku_key=sku_key, size=size)
        ]
        matched_store_ids = sorted(
            {int(mrow["store_id"]) for mrow in matched if _as_int(mrow.get("store_id")) is not None}
        )
        allowed_visible = set()
        if lead_store_id is not None:
            allowed_visible.add(int(lead_store_id))
        allowed_visible.update(allowed_followers)
        non_lead_visible = sorted(set(matched_store_ids) - allowed_visible)
        if non_lead_visible:
            row_errors.append("non-lead store visible for mapped liquidation row")
        audit_rows.append(
            {
                "tranche_id": row.get("tranche_id", ""),
                "sku_key": sku_key,
                "size": size,
                "lead_store": lead_store,
                "matched_store_ids": ";".join(str(v) for v in matched_store_ids),
                "matched_merchant_skus": ";".join(str(v.get("merchant_sku") or "") for v in matched),
                "non_lead_visible_store_ids": ";".join(str(v) for v in non_lead_visible),
                "status": row.get("status", ""),
            }
        )
        if row_errors:
            errors.append({"row_number": index, "tranche_id": row.get("tranche_id", ""), "errors": row_errors})
    return audit_rows, errors


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-WA-01 Internal Cannibalization Guard Report",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"Repricer SQLite: `{report['repricer_sqlite_path']}`",
        f"Lead-store map: `{report['lead_store_map_csv']}`",
        "",
        "## Summary",
        "",
        f"- repricer_row_count: `{report['repricer_row_count']}`",
        f"- active_available_row_count: `{report['active_available_row_count']}`",
        f"- source_max_fetched_at: `{report['source_max_fetched_at']}`",
        f"- source_age_days: `{report['source_age_days']}`",
        f"- own_store_competitor_rows: `{report['own_store_competitor_rows']}`",
        f"- own_store_not_excluded_count: `{report['own_store_not_excluded_count']}`",
        f"- own_store_undercut_violation_count: `{report['own_store_undercut_violation_count']}`",
        f"- own_store_visible_lower_price_rows: `{report['own_store_visible_lower_price_rows']}`",
        f"- active_lead_map_rows: `{report['active_lead_map_rows']}`",
        f"- first_liquidation_lead_map_required: `{report['first_liquidation_lead_map_required']}`",
        f"- lead_map_error_count: `{report['lead_map_error_count']}`",
        f"- shared_price_spread_rows: `{report['shared_price_spread_rows']}`",
        "",
        "## Checks",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["lead_map_errors"]:
        lines.extend(["", "## Lead Map Errors", ""])
        for error in report["lead_map_errors"]:
            lines.append(f"- row {error['row_number']} `{error.get('tranche_id')}`: {', '.join(error['errors'])}")
    lines.append("")
    return "\n".join(lines)


def build_internal_cannibalization_guard_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    config_path = config_path.resolve()
    if not config_path.exists():
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
        config: dict[str, Any] = {}
    else:
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    checks.append(
        _check(
            config.get("contract_id") == "INTERNAL_CANNIBALIZATION_GUARD_V1"
            and config.get("gate_id") == "G-WA-01"
            and config.get("owner_decision_id") == "OD-011",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')} decision={config.get('owner_decision_id')}",
        )
    )

    generated_at = _now_almaty()
    as_of_dt = _parse_datetime(as_of or generated_at) or datetime.now(ALMATY_TZ)
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=ALMATY_TZ)

    sqlite_path = _resolve_project_path(config.get("repricer_sqlite_path", ""))
    lead_map_path = _resolve_project_path(config.get("lead_store_map_csv", ""))
    checks.append(_check(sqlite_path.exists(), "repricer_sqlite_present", str(sqlite_path)))
    checks.append(_check(lead_map_path.exists(), "lead_store_map_present", str(lead_map_path)))

    repricer_rows: list[dict[str, Any]] = []
    if sqlite_path.exists():
        try:
            repricer_rows = _load_repricer_rows(sqlite_path)
            checks.append(_check(True, "repricer_sqlite_readonly_open", "mode=ro"))
        except sqlite3.Error as exc:
            checks.append(_check(False, "repricer_sqlite_readonly_open", str(exc)))
    max_fetched = None
    fetched_times = [_parse_datetime(row.get("fetched_at")) for row in repricer_rows]
    clean_times = [dt.astimezone(ALMATY_TZ) for dt in fetched_times if dt is not None]
    if clean_times:
        max_fetched = max(clean_times)
    max_age_days = int(config.get("max_source_age_days") or 7)
    source_age_days = None
    source_fresh = False
    if max_fetched is not None:
        source_age_days = round((as_of_dt.astimezone(ALMATY_TZ) - max_fetched).total_seconds() / 86400, 4)
        source_fresh = source_age_days <= max_age_days
    checks.append(
        _check(
            source_fresh,
            "repricer_source_fresh",
            f"max_fetched_at={max_fetched.isoformat() if max_fetched else 'none'} age_days={source_age_days}",
        )
    )

    required_columns = [str(v) for v in config.get("required_lead_store_columns") or []]
    lead_rows, lead_fieldnames = _load_lead_map(lead_map_path)
    missing_lead_columns = [col for col in required_columns if col not in lead_fieldnames]
    checks.append(
        _check(
            not missing_lead_columns,
            "lead_store_map_schema",
            "missing=" + (",".join(missing_lead_columns) if missing_lead_columns else "none"),
            fieldnames=lead_fieldnames,
        )
    )

    own_evidence, name_warnings = _collect_own_competitor_rows(repricer_rows, config=config)
    not_excluded = [row for row in own_evidence if not row["not_competitor_present"]]
    undercut_violations = [row for row in not_excluded if row["own_store_undercut"]]
    visible_lower = [row for row in own_evidence if row["own_store_undercut"]]
    checks.append(
        _check(
            not not_excluded,
            "own_store_competitors_excluded",
            f"missing_not_competitor_rows={len(not_excluded)}",
        )
    )
    checks.append(
        _check(
            not undercut_violations,
            "own_store_undercut_rows",
            f"missing_not_competitor_and_lower_price_rows={len(undercut_violations)}",
        )
    )

    managed_ids = {int(v) for v in (config.get("managed_pricing_store_ids") or {}).values()}
    spread_rows = _collect_shared_spreads(repricer_rows, managed_ids)
    lead_audit_rows, lead_errors = _collect_lead_map_audit(
        lead_rows=lead_rows,
        repricer_rows=repricer_rows,
        config=config,
    )
    active_statuses = {_norm(v) for v in config.get("active_map_statuses") or ["ACTIVE"]}
    active_lead_rows = [row for row in lead_rows if _norm(row.get("status")) in active_statuses]
    checks.append(_check(not lead_errors, "lead_store_map_active_rows", f"errors={len(lead_errors)}"))

    hard_fail = any(not check["ok"] for check in checks)
    if hard_fail:
        gate = "RED"
    elif not active_lead_rows and bool(config.get("armed_when_no_active_lead_rows", True)):
        gate = "ARMED"
    else:
        gate = "GREEN"

    output_root.mkdir(parents=True, exist_ok=True)
    competitor_csv = output_root / "own_store_competitor_exclusions.csv"
    spread_csv = output_root / "own_store_visible_price_spread.csv"
    lead_csv = output_root / "liquidation_lead_store_map_audit.csv"
    _write_csv(competitor_csv, EVIDENCE_COMPETITOR_COLUMNS, own_evidence)
    _write_csv(spread_csv, EVIDENCE_SPREAD_COLUMNS, spread_rows)
    _write_csv(lead_csv, EVIDENCE_LEAD_COLUMNS, lead_audit_rows)

    report: dict[str, Any] = {
        "gate": gate,
        "status": gate,
        "ok": gate in {"GREEN", "ARMED"},
        "generated_at": generated_at,
        "as_of": as_of_dt.astimezone(ALMATY_TZ).isoformat(),
        "config_path": str(config_path),
        "repricer_sqlite_path": str(sqlite_path),
        "lead_store_map_csv": str(lead_map_path),
        "repricer_row_count": len(repricer_rows),
        "active_available_row_count": sum(1 for row in repricer_rows if _is_active_available(row)),
        "source_max_fetched_at": max_fetched.isoformat() if max_fetched else "",
        "source_age_days": source_age_days,
        "own_store_competitor_rows": len(own_evidence),
        "own_store_not_excluded_count": len(not_excluded),
        "own_store_undercut_violation_count": len(undercut_violations),
        "own_store_visible_lower_price_rows": len(visible_lower),
        "own_store_name_warning_count": len(name_warnings),
        "lead_map_rows": len(lead_rows),
        "active_lead_map_rows": len(active_lead_rows),
        "first_liquidation_lead_map_required": not bool(active_lead_rows),
        "lead_map_error_count": len(lead_errors),
        "shared_price_spread_rows": len(spread_rows),
        "checks": checks,
        "lead_map_errors": lead_errors,
        "artifacts": {
            "own_store_competitor_exclusions_csv": str(competitor_csv),
            "own_store_visible_price_spread_csv": str(spread_csv),
            "liquidation_lead_store_map_audit_csv": str(lead_csv),
        },
        "forbidden_writes_performed": False,
    }
    (output_root / "internal_cannibalization_guard_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "internal_cannibalization_guard_report.md").write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate G-WA-01 internal-cannibalization guard evidence.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true", help="Return non-zero unless gate is GREEN or ARMED.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    report = build_internal_cannibalization_guard_report(
        config_path=Path(args.config),
        output_root=Path(args.output_dir),
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Gate: {report['gate']}")
        print(f"ok: {report['ok']}")
        print(f"output_dir: {args.output_dir}")
    if args.strict and report["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
