#!/usr/bin/env python3
"""Validate the G-LIQ-04 LINE51 generic-markdown guard."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "line51_markdown_guard.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "g_liq04_line51_markdown_guard"

LEAD_COLUMNS = [
    "tranche_id",
    "sku_key",
    "size",
    "lead_store",
    "allowed_follower_stores",
    "effective_from",
    "source_artifact",
    "status",
    "owner_decision_id",
    "notes",
]

SIZE_EVIDENCE_COLUMNS = [
    "sku_id",
    "expected_current_stock",
    "actual_current_stock",
    "snapshot_date",
    "matched",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _parse_as_of(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return _now_almaty()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ).replace(microsecond=0).isoformat()


def _resolve_project_path(raw: str | Path | None) -> Path:
    path = Path(str(raw or ""))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader], list(reader.fieldnames or [])


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _check(ok: bool, name: str, details: str, *, blocker: bool = True, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "check": name,
        "ok": bool(ok),
        "details": details,
        "blocker": bool(blocker),
    }
    row.update(extra)
    return row


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _norm_token(value: Any) -> str:
    return re.sub(r"[\s_-]+", "", str(value or "").strip()).upper()


def _norm_status(value: Any) -> str:
    return str(value or "").strip().upper()


def _find_by_sku(rows: list[dict[str, str]], sku_key: str) -> dict[str, str] | None:
    for row in rows:
        if str(row.get("sku_key") or "").strip() == sku_key:
            return row
    return None


def _lead_row_matches_sku(row: dict[str, str], sku_key: str) -> bool:
    value = str(row.get("sku_key") or "").strip()
    return value == sku_key or value.startswith(f"{sku_key}_")


def _count_evidence_ok(text: str) -> bool:
    return bool(re.search(r"LINE51\s+S.*82.*FULL", text, flags=re.IGNORECASE | re.DOTALL)) and "3/3" in text


def _owner_decision_checks(
    decision: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    checks: list[dict[str, Any]] = []
    sku_key = str(config.get("sku_key") or "")
    allowed_schema = str(config.get("allowed_clearance_schema_version") or "")
    allowed_stores = {_norm_token(v) for v in config.get("allowed_clearance_target_stores") or []}
    allowed_sizes = {str(v).strip().upper() for v in config.get("allowed_clearance_sizes") or []}

    schema = str(decision.get("schema_version") or "")
    checks.append(_check(schema == allowed_schema, "owner_schema", f"schema={schema}"))

    source_family = decision.get("source_family") or {}
    checks.append(
        _check(
            str(source_family.get("sku_key") or "") == sku_key,
            "owner_source_family",
            f"sku_key={source_family.get('sku_key')}",
        )
    )

    approval = decision.get("owner_approval") or {}
    scope = str(approval.get("approval_scope") or "").casefold()
    checks.append(
        _check(
            bool(approval.get("temporary_override_only")) and "fixed-price" in scope and "line51" in scope,
            "owner_scope_temporary_fixed_price",
            f"temporary={approval.get('temporary_override_only')} scope={approval.get('approval_scope')}",
        )
    )

    strategy = decision.get("strategy") or {}
    pricing = str(strategy.get("pricing") or "").strip().casefold()
    checks.append(
        _check(
            pricing == "fixed manual prices only",
            "owner_pricing_fixed_manual_only",
            f"pricing={strategy.get('pricing')}",
        )
    )
    repricer_policy = str(strategy.get("repricer_policy") or "").casefold()
    checks.append(
        _check(
            "never" in repricer_policy and "automated" in repricer_policy and "dumping" in repricer_policy,
            "owner_repricer_policy_forbids_automation",
            f"repricer_policy={strategy.get('repricer_policy')}",
        )
    )

    stores = {_norm_token(row.get("store_code")) for row in decision.get("target_stores") or []}
    checks.append(
        _check(
            stores == allowed_stores,
            "owner_target_stores_exact",
            f"stores={sorted(stores)} expected={sorted(allowed_stores)}",
        )
    )

    variants = decision.get("target_variants") or []
    variant_sizes = {str(row.get("size") or "").strip().upper() for row in variants if isinstance(row, dict)}
    checks.append(
        _check(
            variant_sizes == allowed_sizes,
            "owner_target_sizes_exact",
            f"sizes={sorted(variant_sizes)} expected={sorted(allowed_sizes)}",
        )
    )

    expected_prices = (decision.get("economics_assumptions") or {}).get("initial_prices_by_size") or {}
    price_mismatches: list[str] = []
    for row in variants:
        if not isinstance(row, dict):
            continue
        size = str(row.get("size") or "").strip().upper()
        planned_price = _as_int(row.get("planned_price_kzt"))
        expected_price = _as_int(expected_prices.get(size))
        if planned_price is None or expected_price is None or planned_price != expected_price:
            price_mismatches.append(f"{size}:{planned_price}!={expected_price}")
    checks.append(
        _check(
            not price_mismatches and bool(variants),
            "owner_fixed_prices_match_variants",
            f"mismatches={price_mismatches or []}",
        )
    )

    mapping = decision.get("mapping_policy") or {}
    checks.append(
        _check(
            str(mapping.get("ab_db_mutation_status") or "") == "not_applied_by_this_decision_file",
            "owner_decision_no_ab_db_mutation",
            f"ab_db_mutation_status={mapping.get('ab_db_mutation_status')}",
        )
    )

    stoplines = [str(value).casefold() for value in decision.get("stoplines") or []]
    dumping_stop = any("do not enable repricer dumping" in value for value in stoplines)
    automated_stop = any("do not allow automated repricer price writes" in value for value in stoplines)
    checks.append(
        _check(
            dumping_stop and automated_stop,
            "owner_stoplines_forbid_repricer_dumping_and_automation",
            f"dumping_stop={dumping_stop} automated_stop={automated_stop}",
        )
    )

    status = "separate_fixed_manual_clearance_only" if all(row["ok"] for row in checks) else "invalid_or_unsafe"
    return checks, status


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G-LIQ-04 LINE51 Markdown Guard",
        "",
        f"Gate: {report['gate']}",
        f"Generated: {report['generated_at']}",
        f"As of: {report['as_of']}",
        "",
        "## Summary",
        "",
        f"- count_extension_executed: `{report['count_extension_executed']}`",
        f"- generic_line51_markdown_row_count: `{report['generic_line51_markdown_row_count']}`",
        f"- owner_decision_status: `{report['owner_decision_status']}`",
        f"- required_size_stock: `{report['required_size_stock']}`",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Checks", "", "| check | status | details |", "|---|---:|---|"])
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    lines.append("")
    return "\n".join(lines)


def build_line51_markdown_guard_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if config_path.exists():
        config = _load_json(config_path)
        checks.append(_check(True, "config_present", str(config_path)))
    else:
        config = {}
        checks.append(_check(False, "config_present", f"missing: {config_path}"))
    checks.append(
        _check(
            config.get("contract_id") == "LINE51_MARKDOWN_GUARD_V1" and config.get("gate_id") == "G-LIQ-04",
            "config_identity",
            f"contract={config.get('contract_id')} gate={config.get('gate_id')}",
        )
    )

    sku_key = str(config.get("sku_key") or "CL_OC_MEN_LINE51_WHITE")
    liquidation_dir = _resolve_project_path(config.get("liquidation_register_dir"))
    register_path = liquidation_dir / "liquidation_register.csv"
    segment_path = liquidation_dir / "liquidation_segment_map.csv"
    size_path = liquidation_dir / "liquidation_size_detail.csv"
    lead_map_path = _resolve_project_path(config.get("lead_store_map_csv"))
    count_path = _resolve_project_path(config.get("count_evidence_path"))
    owner_path_raw = str(config.get("owner_decision_path") or "").strip()
    owner_path = _resolve_project_path(owner_path_raw) if owner_path_raw else None

    for label, path in (
        ("liquidation_register_csv", register_path),
        ("liquidation_segment_map_csv", segment_path),
        ("liquidation_size_detail_csv", size_path),
        ("lead_store_map_csv", lead_map_path),
        ("count_evidence_path", count_path),
    ):
        checks.append(_check(path.exists(), f"{label}_present", str(path)))

    register_rows: list[dict[str, str]] = []
    segment_rows: list[dict[str, str]] = []
    size_rows: list[dict[str, str]] = []
    lead_rows: list[dict[str, str]] = []
    lead_fields: list[str] = []
    if register_path.exists():
        register_rows, _ = _load_csv(register_path)
    if segment_path.exists():
        segment_rows, _ = _load_csv(segment_path)
    if size_path.exists():
        size_rows, _ = _load_csv(size_path)
    if lead_map_path.exists():
        lead_rows, lead_fields = _load_csv(lead_map_path)
        missing_lead_cols = sorted(set(LEAD_COLUMNS) - set(lead_fields))
        checks.append(
            _check(
                not missing_lead_cols,
                "lead_map_schema",
                f"missing_columns={missing_lead_cols}",
            )
        )

    register_row = _find_by_sku(register_rows, sku_key)
    segment_row = _find_by_sku(segment_rows, sku_key)
    checks.append(_check(register_row is not None, "line51_register_row_present", sku_key))
    checks.append(_check(segment_row is not None, "line51_segment_row_present", sku_key))
    source_row = segment_row or register_row or {}
    segment = str(source_row.get("segment") or "")
    checks.append(_check(segment == "A_COUNT_GATED", "line51_segment_count_gated", f"segment={segment}"))
    checks.append(
        _check(
            not _as_bool(source_row.get("tranche_sizing_allowed")),
            "line51_tranche_sizing_blocked",
            f"tranche_sizing_allowed={source_row.get('tranche_sizing_allowed')}",
        )
    )
    hold_reason = str(source_row.get("hold_reason") or "")
    checks.append(_check("count_gated" in hold_reason, "line51_hold_reason_count_gated", f"hold_reason={hold_reason}"))

    required_size_stock = {
        str(key): int(value)
        for key, value in (config.get("required_size_stock") or {"CL_OC_MEN_LINE51_WHITE_S": 82}).items()
    }
    size_evidence_rows: list[dict[str, Any]] = []
    by_sku_id = {str(row.get("sku_id") or ""): row for row in size_rows}
    for sku_id, expected_stock in required_size_stock.items():
        row = by_sku_id.get(sku_id)
        actual_stock = _as_int((row or {}).get("current_stock"))
        matched = row is not None and actual_stock == expected_stock
        size_evidence_rows.append(
            {
                "sku_id": sku_id,
                "expected_current_stock": expected_stock,
                "actual_current_stock": "" if actual_stock is None else actual_stock,
                "snapshot_date": (row or {}).get("snapshot_date", ""),
                "matched": matched,
            }
        )
        checks.append(
            _check(
                matched,
                f"required_size_stock_{sku_id}",
                f"actual={actual_stock} expected={expected_stock}",
            )
        )

    count_text = count_path.read_text(encoding="utf-8") if count_path.exists() else ""
    count_extension_executed = _count_evidence_ok(count_text)
    checks.append(
        _check(
            count_extension_executed,
            "count_extension_evidence_line51_s_82_full",
            str(count_path),
        )
    )

    active_statuses = {_norm_status(value) for value in config.get("active_map_statuses") or ["ACTIVE"]}
    generic_line51_rows = [
        row
        for row in lead_rows
        if _norm_status(row.get("status")) in active_statuses and _lead_row_matches_sku(row, sku_key)
    ]
    checks.append(
        _check(
            not generic_line51_rows,
            "no_active_generic_line51_markdown_rows",
            f"rows={len(generic_line51_rows)}",
        )
    )

    owner_decision_status = "not_configured"
    if owner_path is not None:
        if owner_path.exists():
            owner_decision = _load_json(owner_path)
            checks.append(_check(True, "owner_decision_present", str(owner_path)))
            owner_checks, owner_decision_status = _owner_decision_checks(owner_decision, config=config)
            checks.extend(owner_checks)
        else:
            owner_decision_status = "missing"
            checks.append(_check(False, "owner_decision_present", f"missing: {owner_path}"))
    else:
        warnings.append("owner_decision_path not configured; fixed-clearance exception not validated")

    for row in checks:
        if row.get("blocker", True) and not row.get("ok"):
            blockers.append(f"{row['check']}: {row['details']}")
    if generic_line51_rows:
        blockers.append(f"generic LINE51 markdown rows active in lead map: {len(generic_line51_rows)}")

    gate = "GREEN" if not blockers else "RED"
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    generic_rows_path = output_root / "g_liq04_generic_line51_markdown_rows.csv"
    size_evidence_path = output_root / "g_liq04_line51_size_count_evidence.csv"
    _write_csv(generic_rows_path, generic_line51_rows, LEAD_COLUMNS)
    _write_csv(size_evidence_path, size_evidence_rows, SIZE_EVIDENCE_COLUMNS)

    report: dict[str, Any] = {
        "gate_id": "G-LIQ-04",
        "gate": gate,
        "ok": gate == "GREEN",
        "generated_at": _now_almaty(),
        "as_of": _parse_as_of(as_of),
        "config_path": str(config_path),
        "liquidation_register_dir": str(liquidation_dir),
        "lead_store_map_csv": str(lead_map_path),
        "count_evidence_path": str(count_path),
        "owner_decision_path": str(owner_path or ""),
        "sku_key": sku_key,
        "count_extension_executed": count_extension_executed,
        "generic_line51_markdown_row_count": len(generic_line51_rows),
        "owner_decision_status": owner_decision_status,
        "required_size_stock": required_size_stock,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "artifacts": {
            "generic_line51_markdown_rows_csv": str(generic_rows_path),
            "line51_size_count_evidence_csv": str(size_evidence_path),
        },
        "forbidden_writes_performed": False,
        "production_db_written": False,
        "external_writes_performed": False,
    }
    json_path = output_root / "g_liq04_line51_markdown_guard_report.json"
    md_path = output_root / "g_liq04_line51_markdown_guard_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_line51_markdown_guard_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"Report: {report['json_path']}")
        if report["blockers"]:
            print("Blockers:")
            for blocker in report["blockers"]:
                print(f"  - {blocker}")
    return 1 if args.strict and report["gate"] != "GREEN" else 0


if __name__ == "__main__":
    raise SystemExit(main())
