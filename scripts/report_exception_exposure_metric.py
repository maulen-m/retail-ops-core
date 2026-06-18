#!/usr/bin/env python3
"""Publish daily exception age and KZT exposure metrics from exception_queue."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"

OPEN_STATUSES = {"OPEN", "PENDING", "BLOCKED"}
DIRECT_KZT_KEYS = (
    "exposure_kzt",
    "amount_kzt",
    "goods_value_kzt",
    "cogs_line",
    "line_cogs_kzt",
    "loss_kzt",
    "expected_loss_kzt",
)
QUANTITY_KEYS = (
    "quantity_at_risk",
    "physical_anchor_qty",
    "raw_current_stock",
    "quantity",
    "qty",
    "units",
    "current_stock",
)


@dataclass(frozen=True)
class Valuation:
    quantity_at_risk: float | None
    unit_cogs_kzt: float | None
    exposure_kzt: float | None
    exposure_source: str
    valuation_status: str


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
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


def _first_numeric(payload: dict[str, Any], keys: tuple[str, ...]) -> tuple[str | None, float | None]:
    for key in keys:
        value = _number(payload.get(key))
        if value is not None:
            return key, value
    return None, None


def _reason_code(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "UNKNOWN"
    return text.split(":", 1)[0].strip() or "UNKNOWN"


def _db_sha256(db_path: Path) -> str:
    h = hashlib.sha256()
    with db_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _sku_cogs_map(conn: sqlite3.Connection) -> dict[str, float]:
    mapping: dict[str, float] = {}
    if not _table_exists(conn, "dim_sku"):
        return mapping
    for row in conn.execute("SELECT sku_key, cogs_kzt FROM dim_sku WHERE cogs_kzt IS NOT NULL"):
        sku_key = str(row["sku_key"] or "").strip()
        cogs = _number(row["cogs_kzt"])
        if sku_key and cogs is not None:
            mapping[sku_key] = cogs
    if _table_exists(conn, "dim_sku_size"):
        for row in conn.execute(
            """
            SELECT s.sku_id, d.cogs_kzt
            FROM dim_sku_size s
            JOIN dim_sku d ON d.sku_key = s.sku_key
            WHERE d.cogs_kzt IS NOT NULL
            """
        ):
            sku_id = str(row["sku_id"] or "").strip()
            cogs = _number(row["cogs_kzt"])
            if sku_id and cogs is not None:
                mapping[sku_id] = cogs
    return mapping


def _valuation(evidence: dict[str, Any], cogs_map: dict[str, float]) -> Valuation:
    direct_key, direct_kzt = _first_numeric(evidence, DIRECT_KZT_KEYS)
    qty_key, quantity = _first_numeric(evidence, QUANTITY_KEYS)
    if quantity is not None:
        quantity = abs(quantity)

    sku_key = str(evidence.get("sku_key") or "").strip()
    sku_id = str(evidence.get("sku_id") or "").strip()
    unit_cogs = cogs_map.get(sku_id) if sku_id else None
    if unit_cogs is None and sku_key:
        unit_cogs = cogs_map.get(sku_key)

    if direct_kzt is not None:
        return Valuation(
            quantity_at_risk=quantity,
            unit_cogs_kzt=unit_cogs,
            exposure_kzt=abs(direct_kzt),
            exposure_source=f"evidence_json.{direct_key}",
            valuation_status="VALUED_DIRECT",
        )
    if quantity is not None and unit_cogs is not None:
        return Valuation(
            quantity_at_risk=quantity,
            unit_cogs_kzt=unit_cogs,
            exposure_kzt=round(quantity * unit_cogs, 2),
            exposure_source="quantity_at_risk_times_dim_sku_cogs_kzt",
            valuation_status="VALUED_BY_COGS",
        )
    if quantity is None:
        status = "UNVALUED_MISSING_QUANTITY"
    elif unit_cogs is None:
        status = "UNVALUED_MISSING_UNIT_COGS"
    else:
        status = "UNVALUED"
    source = "none"
    if qty_key:
        source = f"evidence_json.{qty_key}"
    return Valuation(
        quantity_at_risk=quantity,
        unit_cogs_kzt=unit_cogs,
        exposure_kzt=None,
        exposure_source=source,
        valuation_status=status,
    )


def _rollup(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {
        key: "",
        "open_exception_count": 0,
        "valued_exception_count": 0,
        "unvalued_exception_count": 0,
        "total_exposure_kzt": 0.0,
        "total_exposure_age_kzt_days": 0.0,
        "total_quantity_at_risk": 0.0,
        "total_quantity_age_days": 0.0,
        "max_age_days": 0,
    })
    for row in rows:
        value = str(row.get(key) or "UNKNOWN")
        bucket = groups[value]
        bucket[key] = value
        bucket["open_exception_count"] += 1
        if row.get("exposure_kzt") is None:
            bucket["unvalued_exception_count"] += 1
        else:
            bucket["valued_exception_count"] += 1
            bucket["total_exposure_kzt"] += float(row["exposure_kzt"])
            bucket["total_exposure_age_kzt_days"] += float(row["exposure_age_kzt_days"])
        if row.get("quantity_at_risk") is not None:
            bucket["total_quantity_at_risk"] += float(row["quantity_at_risk"])
            bucket["total_quantity_age_days"] += float(row["quantity_age_days"])
        bucket["max_age_days"] = max(bucket["max_age_days"], int(row["age_days"]))

    out = []
    for bucket in groups.values():
        for numeric_key in (
            "total_exposure_kzt",
            "total_exposure_age_kzt_days",
            "total_quantity_at_risk",
            "total_quantity_age_days",
        ):
            bucket[numeric_key] = round(bucket[numeric_key], 2)
        out.append(bucket)
    return sorted(out, key=lambda item: (-item["total_exposure_age_kzt_days"], str(item[key])))


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Exception Exposure Metric",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- db_sha256: `{payload['db_sha256']}`",
        "",
        "## Daily Line",
        "",
        (
            "- exception_exposure: "
            f"open={payload['open_exception_count']}; "
            f"valued={payload['valued_exception_count']}; "
            f"unvalued={payload['unvalued_exception_count']}; "
            f"exposure_kzt={payload['total_exposure_kzt']}; "
            f"exposure_age_kzt_days={payload['total_exposure_age_kzt_days']}; "
            f"quantity_at_risk={payload['total_quantity_at_risk']}; "
            f"quantity_age_days={payload['total_quantity_age_days']}; "
            f"oldest_age_days={payload['oldest_age_days']}"
        ),
        "",
        "## Domain Rollup",
        "",
        "| domain | open | valued | unvalued | exposure_kzt | exposure_age_kzt_days | quantity_at_risk | max_age_days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rollups"]["by_domain"]:
        lines.append(
            f"| `{row['domain']}` | {row['open_exception_count']} | {row['valued_exception_count']} | "
            f"{row['unvalued_exception_count']} | {row['total_exposure_kzt']} | "
            f"{row['total_exposure_age_kzt_days']} | {row['total_quantity_at_risk']} | {row['max_age_days']} |"
        )

    lines.extend(
        [
            "",
            "## Open Exceptions",
            "",
            "| exception_id | reason_code | age_days | valuation_status | exposure_kzt | quantity_at_risk |",
            "|---|---|---:|---|---:|---:|",
        ]
    )
    for row in payload["exceptions"]:
        lines.append(
            f"| `{row['exception_id']}` | `{row['reason_code']}` | {row['age_days']} | "
            f"`{row['valuation_status']}` | {row['exposure_kzt']} | {row['quantity_at_risk']} |"
        )
    return "\n".join(lines) + "\n"


def build_exception_exposure_metric(
    *,
    db_path: Path,
    as_of: date,
    output_dir: Path,
) -> dict[str, Any]:
    db = db_path.resolve()
    if not db.exists():
        raise RuntimeError(f"DB not found: {db}")

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "exception_queue"):
            raise RuntimeError("missing required table: exception_queue")
        cogs_map = _sku_cogs_map(conn)
        rows: list[dict[str, Any]] = []
        query = """
            SELECT exception_id, run_id, domain, severity, status, reason, owner,
                   recommended_action, evidence_json, evidence_paths_json, created_at,
                   due_at, updated_at
            FROM exception_queue
            WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'PENDING', 'BLOCKED')
            ORDER BY datetime(COALESCE(created_at, '1970-01-01')), exception_id
        """
        for record in conn.execute(query):
            try:
                evidence = json.loads(record["evidence_json"] or "{}")
                if not isinstance(evidence, dict):
                    evidence = {"_raw_evidence_json_type": type(evidence).__name__}
            except json.JSONDecodeError as exc:
                evidence = {"_evidence_json_error": str(exc)}
            created_date = _parse_date(record["created_at"])
            age_days = 0 if created_date is None else max(0, (as_of - created_date).days)
            valuation = _valuation(evidence, cogs_map)
            exposure_age = None
            if valuation.exposure_kzt is not None:
                exposure_age = round(valuation.exposure_kzt * age_days, 2)
            quantity_age = None
            if valuation.quantity_at_risk is not None:
                quantity_age = round(valuation.quantity_at_risk * age_days, 2)
            row = {
                "exception_id": record["exception_id"],
                "domain": record["domain"],
                "severity": record["severity"],
                "status": record["status"],
                "owner": record["owner"],
                "reason_code": _reason_code(record["reason"]),
                "reason": record["reason"],
                "created_at": record["created_at"],
                "due_at": record["due_at"],
                "age_days": age_days,
                "sku_key": evidence.get("sku_key"),
                "sku_id": evidence.get("sku_id"),
                "my_size": evidence.get("my_size"),
                "quantity_at_risk": valuation.quantity_at_risk,
                "unit_cogs_kzt": valuation.unit_cogs_kzt,
                "exposure_kzt": valuation.exposure_kzt,
                "exposure_age_kzt_days": exposure_age,
                "quantity_age_days": quantity_age,
                "exposure_source": valuation.exposure_source,
                "valuation_status": valuation.valuation_status,
            }
            rows.append(row)
    finally:
        conn.close()

    total_exposure = round(sum(float(r["exposure_kzt"]) for r in rows if r["exposure_kzt"] is not None), 2)
    total_exposure_age = round(
        sum(float(r["exposure_age_kzt_days"]) for r in rows if r["exposure_age_kzt_days"] is not None),
        2,
    )
    total_quantity = round(sum(float(r["quantity_at_risk"]) for r in rows if r["quantity_at_risk"] is not None), 2)
    total_quantity_age = round(
        sum(float(r["quantity_age_days"]) for r in rows if r["quantity_age_days"] is not None),
        2,
    )
    valued = sum(1 for r in rows if r["exposure_kzt"] is not None)
    oldest_age = max((int(r["age_days"]) for r in rows), default=0)

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "status": "GREEN",
        "ok": True,
        "schema_version": "v1",
        "source": "exception_queue",
        "db_path": str(db),
        "db_sha256": _db_sha256(db),
        "open_statuses": sorted(OPEN_STATUSES),
        "open_exception_count": len(rows),
        "valued_exception_count": valued,
        "unvalued_exception_count": len(rows) - valued,
        "total_exposure_kzt": total_exposure,
        "total_exposure_age_kzt_days": total_exposure_age,
        "total_quantity_at_risk": total_quantity,
        "total_quantity_age_days": total_quantity_age,
        "oldest_age_days": oldest_age,
        "exceptions": rows,
        "rollups": {
            "by_domain": _rollup(rows, "domain"),
            "by_severity": _rollup(rows, "severity"),
            "by_owner": _rollup(rows, "owner"),
            "by_reason_code": _rollup(rows, "reason_code"),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "exception_exposure_metric.json"
    md_path = output_dir / "exception_exposure_metric.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": True,
        "status": "GREEN",
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish exception age and KZT exposure metric")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        as_of = date.fromisoformat(str(args.as_of))
    except ValueError as exc:
        raise SystemExit(f"invalid --as-of date: {args.as_of}") from exc
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / as_of.isoformat())
    result = build_exception_exposure_metric(db_path=args.db, as_of=as_of, output_dir=output_dir)
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "payload"}, ensure_ascii=False, indent=2))
    else:
        print(f"exception_exposure_json={result['json_path']}")
        print(f"exception_exposure_md={result['md_path']}")
        print(f"status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

