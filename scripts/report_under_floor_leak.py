#!/usr/bin/env python3
"""Report G-PRICE-03 under-floor sales leaks from read-only sales truth."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any
import warnings
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "validation" / "under_floor_leak.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "under_floor_leak"

UNDER_FLOOR_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_source",
    "floor_resolution_source",
    "gap_per_unit_kzt",
    "gap_total_kzt",
    "status",
    "kaspi_offer_name",
]

MISSING_FLOOR_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_resolution_source",
    "status",
    "kaspi_offer_name",
]

MISSING_PRICE_COLUMNS = [
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_resolution_source",
    "status",
    "kaspi_offer_name",
]

BY_SKU_COLUMNS = [
    "sku_key",
    "floor_sku_key",
    "floor_min_price_kzt",
    "non_cancelled_rows",
    "non_cancelled_units",
    "under_floor_rows",
    "under_floor_units",
    "gap_total_kzt",
    "missing_floor_rows",
    "missing_price_rows",
    "min_sell_price_kzt",
    "stores",
]

STRATEGIC_BRAND_PRICING_CLASS = "STRATEGIC_BRAND_PRICING"
EXCLUDE_FROM_LEAK_SCORING = "EXCLUDE_FROM_LEAK_SCORING"
ENFORCE_FLOOR = "ENFORCE_FLOOR"

STRATEGIC_EXCLUDED_COLUMNS = [
    "exception_id",
    "exception_class",
    "exception_action",
    "decision_ref",
    "decision_record",
    "exception_match",
    "exception_eval_status",
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_source",
    "floor_resolution_source",
    "gap_per_unit_kzt",
    "gap_total_kzt",
    "status",
    "kaspi_offer_name",
]

SELLOFF_PROTECTED_COLUMNS = [
    "protection_match",
    "protection_eval_status",
    "order_date",
    "order_id",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "floor_sku_key",
    "floor_min_price_kzt",
    "floor_source",
    "floor_resolution_source",
    "gap_per_unit_kzt",
    "gap_total_kzt",
    "status",
    "kaspi_offer_name",
]


def _now_almaty() -> str:
    return datetime.now(ALMATY_TZ).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_simple_top_level_yaml(path: Path) -> dict[str, Any]:
    """Load the small, flat WA protection contract without requiring PyYAML."""
    payload: dict[str, Any] = {}
    active_list: str | None = None
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line.startswith("  - "):
            if not active_list:
                raise ValueError(f"line_{line_number}:list_item_without_key")
            value = stripped[2:].strip().strip('"').strip("'")
            payload[active_list].append(value)
            continue
        if raw_line[:1].isspace():
            raise ValueError(f"line_{line_number}:nested_yaml_not_supported")
        key, separator, raw_value = raw_line.partition(":")
        if not separator or not key.strip():
            raise ValueError(f"line_{line_number}:invalid_mapping")
        key = key.strip()
        value = raw_value.strip()
        if not value:
            payload[key] = []
            active_list = key
            continue
        active_list = None
        if value.lower() == "true":
            payload[key] = True
        elif value.lower() == "false":
            payload[key] = False
        elif value.lower() in {"null", "~"}:
            payload[key] = None
        else:
            payload[key] = value.strip('"').strip("'")
    return payload


def _load_mapping(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        payload: Any = _load_json(path)
    else:
        try:
            import yaml  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            payload = _load_simple_top_level_yaml(path)
        else:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config_root_must_be_object")
    return payload


def _check(ok: bool, name: str, details: str, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"check": name, "ok": bool(ok), "details": details}
    row.update(extra)
    return row


def _resolve_project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _parse_as_of(value: str | None) -> date:
    text = str(value or "").strip()
    if not text:
        return datetime.now(ALMATY_TZ).date()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if isinstance(parsed, datetime):
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ALMATY_TZ)
        return parsed.astimezone(ALMATY_TZ).date()
    return parsed


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
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


def _as_int(value: Any) -> int:
    parsed = _as_float(value)
    if parsed is None:
        return 0
    return int(parsed)


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}"


def _status_is_non_cancelled(status: str, excluded_tokens: list[str]) -> bool:
    clean = status.strip().upper()
    return not any(token in clean for token in excluded_tokens)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_upper(value: Any) -> str:
    return _clean_text(value).upper()


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _load_selloff_price_protect(
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    authority = config.get("selloff_price_protect")
    empty = {
        "enabled": False,
        "source_kind": "",
        "source_path": "",
        "schema_version": "",
        "never_raise": False,
        "sku_key_prefixes": [],
        "product_codes": [],
        "owner_decision": "",
    }
    if authority is None:
        return empty, [], []
    if not isinstance(authority, dict):
        return empty, [{"error": "selloff_price_protect_must_be_object"}], []

    wa_raw = _clean_text(authority.get("wa_path"))
    fallback_raw = _clean_text(authority.get("local_fallback_path"))
    if not wa_raw:
        return empty, [{"error": "wa_path_required"}], []
    if not fallback_raw:
        return empty, [{"error": "local_fallback_path_required"}], []

    wa_path = _resolve_project_path(wa_raw)
    fallback_path = _resolve_project_path(fallback_raw)
    source_path: Path | None = None
    source_kind = ""
    load_warnings: list[str] = []
    if wa_path.exists():
        source_path = wa_path
        source_kind = "wa_primary"
    elif fallback_path.exists():
        source_path = fallback_path
        source_kind = "ab_local_fallback"
        message = f"selloff_price_protect WA YAML unavailable; using AB-local fallback: {fallback_path}"
        load_warnings.append(message)
        warnings.warn(message, RuntimeWarning, stacklevel=2)
    else:
        return (
            empty,
            [
                {
                    "error": "selloff_price_protect_sources_missing",
                    "wa_path": str(wa_path),
                    "local_fallback_path": str(fallback_path),
                }
            ],
            [],
        )

    try:
        payload = _load_mapping(source_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return (
            {**empty, "source_kind": source_kind, "source_path": str(source_path)},
            [{"error": "selloff_price_protect_load_failed", "details": str(exc)}],
            load_warnings,
        )

    errors: list[dict[str, Any]] = []
    schema_version = _clean_text(payload.get("schema_version"))
    sku_key_prefixes = _as_text_list(payload.get("sku_key_prefixes"))
    product_codes = _as_text_list(payload.get("product_codes"))
    never_raise = payload.get("never_raise") is True
    required_never_raise = authority.get("required_never_raise", True) is True
    if not schema_version:
        errors.append({"error": "schema_version_required"})
    if not sku_key_prefixes and not product_codes:
        errors.append({"error": "protection_scope_required"})
    if required_never_raise and not never_raise:
        errors.append({"error": "never_raise_true_required"})

    loaded = {
        "enabled": not errors,
        "source_kind": source_kind,
        "source_path": str(source_path),
        "schema_version": schema_version,
        "never_raise": never_raise,
        "sku_key_prefixes": sku_key_prefixes,
        "product_codes": product_codes,
        "owner_decision": _clean_text(payload.get("owner_decision")),
    }
    return loaded, errors, load_warnings


def _selloff_protection_match(row: dict[str, Any], authority: dict[str, Any]) -> str | None:
    if not authority.get("enabled"):
        return None
    sku_key = _clean_text(row.get("sku_key"))
    for prefix in authority.get("sku_key_prefixes") or []:
        if sku_key.startswith(str(prefix)):
            return f"sku_key_prefix:{prefix}"
    sku_id = _clean_text(row.get("sku_id"))
    for product_code in authority.get("product_codes") or []:
        if sku_id == str(product_code):
            return f"product_code:{product_code}"
    return None


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_floor_rows(path: Path) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]]]:
    rows: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        required = {"SKU_key", "Min_price_35pct"}
        missing = sorted(required - set(fieldnames))
        if missing:
            errors.append({"row": 0, "error": f"missing_columns:{','.join(missing)}"})
            return rows, fieldnames, errors
        for idx, row in enumerate(reader, start=2):
            sku_key = str(row.get("SKU_key") or "").strip()
            floor = _as_float(row.get("Min_price_35pct"))
            if not sku_key:
                errors.append({"row": idx, "error": "missing_sku_key"})
                continue
            if floor is None or floor <= 0:
                errors.append({"row": idx, "sku_key": sku_key, "error": "invalid_floor"})
                continue
            rows[sku_key] = {
                "sku_key": sku_key,
                "floor_min_price_kzt": float(floor),
                "floor_source": str(row.get("floor_source") or "").strip() or "floor_csv",
            }
    return rows, fieldnames, errors


def _alias_for(config: dict[str, Any], sku_key: str) -> tuple[str, str]:
    aliases = config.get("floor_aliases") or {}
    raw = aliases.get(sku_key)
    if raw is None:
        return sku_key, "exact"
    if isinstance(raw, str):
        return raw, "alias"
    if isinstance(raw, dict):
        target = str(raw.get("floor_sku_key") or "").strip()
        source = str(raw.get("source") or "alias").strip()
        return target or sku_key, f"alias:{source}"
    return sku_key, "exact"


def _entry_match_detail(row: dict[str, Any], entry: dict[str, Any]) -> str | None:
    store_code = _clean_upper(row.get("store_code"))
    entry_store = _clean_upper(entry.get("store_code"))
    if not entry_store or entry_store == "*" or store_code != entry_store:
        return None

    sku_key = _clean_text(row.get("sku_key"))
    sku_id = _clean_text(row.get("sku_id"))
    offer_name = _clean_text(row.get("kaspi_offer_name"))

    sku_keys = set(_as_text_list(entry.get("sku_keys")))
    if sku_key in sku_keys:
        return f"sku_key:{sku_key}"

    for prefix in _as_text_list(entry.get("sku_key_prefixes")):
        if sku_key.startswith(prefix):
            return f"sku_key_prefix:{prefix}"

    sku_ids = set(_as_text_list(entry.get("sku_ids")))
    if sku_id in sku_ids:
        return f"sku_id:{sku_id}"

    for prefix in _as_text_list(entry.get("sku_id_prefixes")):
        if sku_id.startswith(prefix):
            return f"sku_id_prefix:{prefix}"

    offer_name_upper = offer_name.upper()
    for token in _as_text_list(entry.get("kaspi_offer_name_contains")):
        if token.upper() in offer_name_upper:
            return f"kaspi_offer_name_contains:{token}"

    return None


def _entry_has_row_scope(entry: dict[str, Any]) -> bool:
    return any(
        _as_text_list(entry.get(key))
        for key in (
            "sku_keys",
            "sku_key_prefixes",
            "sku_ids",
            "sku_id_prefixes",
            "kaspi_offer_name_contains",
        )
    )


def _load_scoring_exception_authority(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    authority = config.get("scoring_exception_authority")
    if authority is None:
        return [], []
    if not isinstance(authority, dict):
        return [], [{"entry": "scoring_exception_authority", "error": "must_be_object"}]

    entries_raw = authority.get("entries") or []
    if not isinstance(entries_raw, list):
        return [], [{"entry": "scoring_exception_authority.entries", "error": "must_be_array"}]

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, raw in enumerate(entries_raw):
        label = f"entries[{idx}]"
        if not isinstance(raw, dict):
            errors.append({"entry": label, "error": "must_be_object"})
            continue
        entry = dict(raw)
        entry_errors: list[dict[str, Any]] = []
        entry_id = _clean_text(entry.get("id"))
        action = _clean_upper(entry.get("action"))
        class_name = _clean_upper(entry.get("class"))
        decision_ref = _clean_text(entry.get("decision_ref"))
        decision_record = _clean_text(entry.get("decision_record"))
        store_code = _clean_text(entry.get("store_code"))

        if not entry_id:
            entry_errors.append({"entry": label, "error": "missing_id"})
        if class_name != STRATEGIC_BRAND_PRICING_CLASS:
            entry_errors.append({"entry": entry_id or label, "error": f"unsupported_class:{class_name or '<missing>'}"})
        if action not in {EXCLUDE_FROM_LEAK_SCORING, ENFORCE_FLOOR}:
            entry_errors.append({"entry": entry_id or label, "error": f"unsupported_action:{action or '<missing>'}"})
        if not store_code or store_code == "*":
            entry_errors.append({"entry": entry_id or label, "error": "store_code_required_no_wildcard"})
        if not decision_ref:
            entry_errors.append({"entry": entry_id or label, "error": "decision_ref_required"})
        if not decision_record:
            entry_errors.append({"entry": entry_id or label, "error": "decision_record_required"})
        if not _entry_has_row_scope(entry):
            entry_errors.append({"entry": entry_id or label, "error": "row_scope_required"})

        if entry_errors:
            errors.extend(entry_errors)
        else:
            entry["id"] = entry_id
            entry["class"] = class_name
            entry["action"] = action
            entry["decision_ref"] = decision_ref
            entry["decision_record"] = decision_record
            entry["store_code"] = store_code
            entries.append(entry)

    return entries, errors


def _scoring_exception_for_row(
    row: dict[str, Any],
    entries: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    for entry in entries:
        if entry.get("action") != ENFORCE_FLOOR:
            continue
        match = _entry_match_detail(row, entry)
        if match:
            return None, f"carve_out:{entry['id']}:{match}"

    for entry in entries:
        if entry.get("action") != EXCLUDE_FROM_LEAK_SCORING:
            continue
        match = _entry_match_detail(row, entry)
        if match:
            return entry, match
    return None, ""


def _load_sales_rows(conn: sqlite3.Connection, start_date: date, as_of_date: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            order_date,
            order_id,
            store_code,
            sku_key,
            sku_id,
            my_size,
            kaspi_offer_name,
            quantity,
            sell_price_kzt,
            status
        FROM sales_fact_v2
        WHERE date(order_date) >= date(?)
          AND date(order_date) <= date(?)
        ORDER BY date(order_date), store_code, sku_key, order_id, sku_id
        """,
        (start_date.isoformat(), as_of_date.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_sales_date(conn: sqlite3.Connection, as_of_date: date) -> date | None:
    row = conn.execute(
        """
        SELECT MAX(order_date) AS max_order_date
        FROM sales_fact_v2
        WHERE date(order_date) <= date(?)
        """,
        (as_of_date.isoformat(),),
    ).fetchone()
    if not row or not row["max_order_date"]:
        return None
    return _parse_date(row["max_order_date"])


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-PRICE-03 Under-Floor Leak Report",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"As of: {report['as_of']}",
        f"Window: {report['window_start']}..{report['window_end']}",
        "",
        "## Summary",
        "",
        f"- total sales rows in window: {report['sales_row_count_total']}",
        f"- non-cancelled rows: {report['non_cancelled_row_count']}",
        f"- non-cancelled units: {report['non_cancelled_units']}",
        f"- under-floor rows: {report['under_floor_row_count']}",
        f"- under-floor units: {report['under_floor_units']}",
        f"- under-floor gap KZT: {report['under_floor_gap_kzt']}",
        f"- selloff-protected rows: {report['selloff_protected']['row_count']}",
        f"- selloff-protected units: {report['selloff_protected']['units']}",
        f"- selloff-protected gap KZT: {report['selloff_protected']['gap_kzt']}",
        f"- strategic brand pricing excluded rows: {report['strategic_brand_pricing_excluded_row_count']}",
        f"- strategic brand pricing excluded units: {report['strategic_brand_pricing_excluded_units']}",
        f"- strategic brand pricing excluded gap KZT: {report['strategic_brand_pricing_excluded_gap_kzt']}",
        f"- missing floor rows: {report['missing_floor_row_count']}",
        f"- missing price rows: {report['missing_price_row_count']}",
        f"- latest sales date: {report['latest_sales_date']}",
        f"- sales data lag days: {report['sales_data_lag_days']}",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- {mark} {check['check']}: {check['details']}")
    lines.extend(
        [
            "",
            "## Selloff Protected",
            "",
            f"- authority source: `{report['selloff_protected']['source_path']}`",
            f"- source kind: {report['selloff_protected']['source_kind']}",
            f"- rows: {report['selloff_protected']['row_count']}",
            f"- units: {report['selloff_protected']['units']}",
            f"- under-floor gap excluded from lift candidates KZT: {report['selloff_protected']['gap_kzt']}",
            f"- warnings: {len(report['selloff_protected']['warnings'])}",
            f"- CSV: `{report['artifacts'].get('selloff_protected_csv', '')}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Strategic Brand Pricing Excluded Rows",
            "",
            f"- rows: {report['strategic_brand_pricing_excluded_row_count']}",
            f"- units: {report['strategic_brand_pricing_excluded_units']}",
            f"- under-floor gap excluded from leak count KZT: {report['strategic_brand_pricing_excluded_gap_kzt']}",
            f"- CSV: `{report['artifacts'].get('strategic_brand_pricing_excluded_csv', '')}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for name, path in report["artifacts"].items():
        lines.append(f"- {name}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def build_under_floor_leak_report(
    *,
    config_path: Path = DEFAULT_CONFIG,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    as_of_date = _parse_as_of(as_of)
    window_days = int(config.get("window_days") or 7)
    start_date = as_of_date - timedelta(days=max(window_days, 1) - 1)
    db_path = _resolve_project_path(config.get("db_path") or "db/app.db")
    floor_csv_path = _resolve_project_path(config.get("floor_csv_path") or "")
    excluded_tokens = [str(v).strip().upper() for v in (config.get("excluded_status_tokens") or ["CANCEL"]) if str(v).strip()]
    max_sales_lag_days = int(config.get("max_sales_data_lag_days") or 2)
    strict_missing_floor = bool(config.get("strict_missing_floor_blocks_green", True))
    strict_missing_price = bool(config.get("strict_missing_price_blocks_green", True))
    selloff_protect, selloff_protect_errors, selloff_protect_warnings = _load_selloff_price_protect(config)
    scoring_exception_entries, scoring_exception_errors = _load_scoring_exception_authority(config)

    checks: list[dict[str, Any]] = []
    if "selloff_price_protect" in config:
        checks.append(
            _check(
                not selloff_protect_errors,
                "selloff_price_protect_config_valid",
                (
                    f"source_kind={selloff_protect['source_kind'] or '<missing>'} "
                    f"prefixes={len(selloff_protect['sku_key_prefixes'])} "
                    f"product_codes={len(selloff_protect['product_codes'])} "
                    f"warnings={len(selloff_protect_warnings)} errors={len(selloff_protect_errors)}"
                ),
                errors=selloff_protect_errors,
                warnings=selloff_protect_warnings,
            )
        )
    if "scoring_exception_authority" in config:
        exclude_count = sum(1 for entry in scoring_exception_entries if entry.get("action") == EXCLUDE_FROM_LEAK_SCORING)
        enforce_count = sum(1 for entry in scoring_exception_entries if entry.get("action") == ENFORCE_FLOOR)
        checks.append(
            _check(
                not scoring_exception_errors,
                "scoring_exception_authority_config_valid",
                f"entries={len(scoring_exception_entries)} exclude={exclude_count} enforce={enforce_count} errors={len(scoring_exception_errors)}",
                errors=scoring_exception_errors,
            )
        )
    floor_rows: dict[str, dict[str, Any]] = {}
    floor_fieldnames: list[str] = []
    floor_errors: list[dict[str, Any]] = []
    if not floor_csv_path.exists():
        checks.append(_check(False, "floor_csv_present", str(floor_csv_path)))
    else:
        floor_rows, floor_fieldnames, floor_errors = _load_floor_rows(floor_csv_path)
        checks.append(_check(True, "floor_csv_present", str(floor_csv_path)))
    checks.append(
        _check(
            len(floor_rows) > 0 and not floor_errors,
            "floor_csv_valid",
            f"floor_rows={len(floor_rows)} errors={len(floor_errors)}",
            fieldnames=floor_fieldnames,
        )
    )

    sales_rows: list[dict[str, Any]] = []
    latest_sales: date | None = None
    if not db_path.exists():
        checks.append(_check(False, "db_path_present", str(db_path)))
    else:
        checks.append(_check(True, "db_path_present", str(db_path)))
        with _connect_readonly(db_path) as conn:
            checks.append(_check(_table_exists(conn, "sales_fact_v2"), "sales_fact_v2_present", "table exists"))
            if _table_exists(conn, "sales_fact_v2"):
                sales_rows = _load_sales_rows(conn, start_date, as_of_date)
                latest_sales = _latest_sales_date(conn, as_of_date)

    sales_lag_days: int | None = None
    if latest_sales is None:
        checks.append(_check(False, "sales_data_latest_date_present", "latest_sales_date missing"))
    else:
        sales_lag_days = max(0, (as_of_date - latest_sales).days)
        checks.append(
            _check(
                sales_lag_days <= max_sales_lag_days,
                "sales_data_fresh_enough",
                f"latest_sales_date={latest_sales.isoformat()} lag_days={sales_lag_days} max={max_sales_lag_days}",
            )
        )

    non_cancelled_rows: list[dict[str, Any]] = []
    under_floor_rows: list[dict[str, Any]] = []
    selloff_protected_rows: list[dict[str, Any]] = []
    strategic_excluded_rows: list[dict[str, Any]] = []
    missing_floor_rows: list[dict[str, Any]] = []
    missing_price_rows: list[dict[str, Any]] = []
    by_sku: dict[tuple[str, str], dict[str, Any]] = {}

    for row in sales_rows:
        status = str(row.get("status") or "").strip()
        if not _status_is_non_cancelled(status, excluded_tokens):
            continue
        non_cancelled_rows.append(row)
        quantity = max(0, _as_int(row.get("quantity")))
        sku_key = str(row.get("sku_key") or "").strip()
        floor_sku_key, floor_resolution_source = _alias_for(config, sku_key)
        floor = floor_rows.get(floor_sku_key)
        sell_price = _as_float(row.get("sell_price_kzt"))

        protection_match = _selloff_protection_match(row, selloff_protect)
        if protection_match is not None:
            floor_min = float(floor["floor_min_price_kzt"]) if floor else None
            gap_per_unit = max(0.0, floor_min - sell_price) if floor_min is not None and sell_price is not None else None
            gap_total = gap_per_unit * quantity if gap_per_unit is not None else None
            if floor is None:
                protection_eval_status = "missing_floor_protected"
            elif sell_price is None:
                protection_eval_status = "missing_price_protected"
            elif gap_per_unit and gap_per_unit > 0:
                protection_eval_status = "under_floor_protected"
            else:
                protection_eval_status = "not_under_floor_protected"
            selloff_protected_rows.append(
                {
                    "protection_match": protection_match,
                    "protection_eval_status": protection_eval_status,
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_source": floor.get("floor_source", "") if floor else "",
                    "floor_resolution_source": floor_resolution_source,
                    "gap_per_unit_kzt": _fmt_money(gap_per_unit),
                    "gap_total_kzt": _fmt_money(gap_total),
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue

        bucket_key = (sku_key, floor_sku_key)
        bucket = by_sku.setdefault(
            bucket_key,
            {
                "sku_key": sku_key,
                "floor_sku_key": floor_sku_key,
                "floor_min_price_kzt": _fmt_money(floor["floor_min_price_kzt"]) if floor else "",
                "non_cancelled_rows": 0,
                "non_cancelled_units": 0,
                "under_floor_rows": 0,
                "under_floor_units": 0,
                "gap_total_kzt": 0.0,
                "missing_floor_rows": 0,
                "missing_price_rows": 0,
                "min_sell_price_kzt": None,
                "stores": set(),
            },
        )
        bucket["non_cancelled_rows"] += 1
        bucket["non_cancelled_units"] += quantity
        bucket["stores"].add(str(row.get("store_code") or "").strip())
        if sell_price is not None:
            current_min = bucket["min_sell_price_kzt"]
            bucket["min_sell_price_kzt"] = sell_price if current_min is None else min(float(current_min), sell_price)

        scoring_exception, exception_match = _scoring_exception_for_row(row, scoring_exception_entries)
        if scoring_exception is not None:
            floor_min = float(floor["floor_min_price_kzt"]) if floor else None
            gap_per_unit = max(0.0, floor_min - sell_price) if floor_min is not None and sell_price is not None else None
            gap_total = gap_per_unit * quantity if gap_per_unit is not None else None
            if floor is None:
                exception_eval_status = "missing_floor_excluded"
            elif sell_price is None:
                exception_eval_status = "missing_price_excluded"
            elif gap_per_unit and gap_per_unit > 0:
                exception_eval_status = "under_floor_excluded"
            else:
                exception_eval_status = "not_under_floor_excluded"
            strategic_excluded_rows.append(
                {
                    "exception_id": scoring_exception.get("id", ""),
                    "exception_class": scoring_exception.get("class", ""),
                    "exception_action": scoring_exception.get("action", ""),
                    "decision_ref": scoring_exception.get("decision_ref", ""),
                    "decision_record": scoring_exception.get("decision_record", ""),
                    "exception_match": exception_match,
                    "exception_eval_status": exception_eval_status,
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_source": floor.get("floor_source", "") if floor else "",
                    "floor_resolution_source": floor_resolution_source,
                    "gap_per_unit_kzt": _fmt_money(gap_per_unit),
                    "gap_total_kzt": _fmt_money(gap_total),
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue

        if floor is None:
            bucket["missing_floor_rows"] += 1
            missing_floor_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_resolution_source": floor_resolution_source,
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue
        floor_min = float(floor["floor_min_price_kzt"])
        if sell_price is None:
            bucket["missing_price_rows"] += 1
            missing_price_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_resolution_source": floor_resolution_source,
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )
            continue
        if sell_price < floor_min:
            gap_per_unit = floor_min - sell_price
            gap_total = gap_per_unit * quantity
            bucket["under_floor_rows"] += 1
            bucket["under_floor_units"] += quantity
            bucket["gap_total_kzt"] += gap_total
            under_floor_rows.append(
                {
                    "order_date": row.get("order_date", ""),
                    "order_id": row.get("order_id", ""),
                    "store_code": row.get("store_code", ""),
                    "sku_key": sku_key,
                    "sku_id": row.get("sku_id", ""),
                    "my_size": row.get("my_size", ""),
                    "quantity": quantity,
                    "sell_price_kzt": _fmt_money(sell_price),
                    "floor_sku_key": floor_sku_key,
                    "floor_min_price_kzt": _fmt_money(floor_min),
                    "floor_source": floor.get("floor_source", ""),
                    "floor_resolution_source": floor_resolution_source,
                    "gap_per_unit_kzt": _fmt_money(gap_per_unit),
                    "gap_total_kzt": _fmt_money(gap_total),
                    "status": status,
                    "kaspi_offer_name": row.get("kaspi_offer_name", ""),
                }
            )

    by_sku_rows: list[dict[str, Any]] = []
    for bucket in by_sku.values():
        by_sku_rows.append(
            {
                "sku_key": bucket["sku_key"],
                "floor_sku_key": bucket["floor_sku_key"],
                "floor_min_price_kzt": bucket["floor_min_price_kzt"],
                "non_cancelled_rows": bucket["non_cancelled_rows"],
                "non_cancelled_units": bucket["non_cancelled_units"],
                "under_floor_rows": bucket["under_floor_rows"],
                "under_floor_units": bucket["under_floor_units"],
                "gap_total_kzt": _fmt_money(float(bucket["gap_total_kzt"])),
                "missing_floor_rows": bucket["missing_floor_rows"],
                "missing_price_rows": bucket["missing_price_rows"],
                "min_sell_price_kzt": _fmt_money(bucket["min_sell_price_kzt"]),
                "stores": ";".join(sorted(v for v in bucket["stores"] if v)),
            }
        )
    by_sku_rows.sort(key=lambda row: (-int(row["under_floor_units"]), -int(row["missing_floor_rows"]), str(row["sku_key"])))
    under_floor_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))
    selloff_protected_rows.sort(
        key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"]))
    )
    strategic_excluded_rows.sort(
        key=lambda row: (
            str(row["exception_id"]),
            str(row["order_date"]),
            str(row["store_code"]),
            str(row["sku_key"]),
            str(row["order_id"]),
        )
    )
    missing_floor_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))
    missing_price_rows.sort(key=lambda row: (str(row["order_date"]), str(row["store_code"]), str(row["sku_key"]), str(row["order_id"])))

    under_floor_units = sum(_as_int(row["quantity"]) for row in under_floor_rows)
    selloff_protected_units = sum(_as_int(row["quantity"]) for row in selloff_protected_rows)
    strategic_excluded_units = sum(_as_int(row["quantity"]) for row in strategic_excluded_rows)
    missing_floor_units = sum(_as_int(row["quantity"]) for row in missing_floor_rows)
    missing_price_units = sum(_as_int(row["quantity"]) for row in missing_price_rows)
    gap_total = sum(float(row["gap_total_kzt"] or 0) for row in under_floor_rows)
    selloff_protected_gap_total = sum(float(row["gap_total_kzt"] or 0) for row in selloff_protected_rows)
    strategic_excluded_gap_total = sum(float(row["gap_total_kzt"] or 0) for row in strategic_excluded_rows)
    non_cancelled_units = sum(max(0, _as_int(row.get("quantity"))) for row in non_cancelled_rows)

    checks.append(
        _check(
            under_floor_units == 0,
            "zero_under_floor_units",
            f"under_floor_rows={len(under_floor_rows)} under_floor_units={under_floor_units} gap_kzt={_fmt_money(gap_total)}",
        )
    )
    if strict_missing_floor:
        checks.append(
            _check(
                missing_floor_units == 0,
                "all_non_cancelled_rows_have_floor",
                f"missing_floor_rows={len(missing_floor_rows)} missing_floor_units={missing_floor_units}",
            )
        )
    if strict_missing_price:
        checks.append(
            _check(
                missing_price_units == 0,
                "all_non_cancelled_rows_have_sell_price",
                f"missing_price_rows={len(missing_price_rows)} missing_price_units={missing_price_units}",
            )
        )

    output_dir = output_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    under_floor_csv = output_dir / "under_floor_sales.csv"
    selloff_protected_csv = output_dir / "selloff_protected.csv"
    strategic_excluded_csv = output_dir / "strategic_brand_pricing_excluded_rows.csv"
    missing_floor_csv = output_dir / "missing_floor_sales.csv"
    missing_price_csv = output_dir / "missing_price_sales.csv"
    by_sku_csv = output_dir / "under_floor_by_sku.csv"
    _write_csv(under_floor_csv, UNDER_FLOOR_COLUMNS, under_floor_rows)
    _write_csv(selloff_protected_csv, SELLOFF_PROTECTED_COLUMNS, selloff_protected_rows)
    _write_csv(strategic_excluded_csv, STRATEGIC_EXCLUDED_COLUMNS, strategic_excluded_rows)
    _write_csv(missing_floor_csv, MISSING_FLOOR_COLUMNS, missing_floor_rows)
    _write_csv(missing_price_csv, MISSING_PRICE_COLUMNS, missing_price_rows)
    _write_csv(by_sku_csv, BY_SKU_COLUMNS, by_sku_rows)

    no_failures = all(row["ok"] for row in checks)
    gate = "GREEN" if no_failures else "RED"
    report: dict[str, Any] = {
        "generated_at": _now_almaty(),
        "as_of": as_of_date.isoformat(),
        "gate": gate,
        "status": gate,
        "ok": gate == "GREEN",
        "config_path": str(config_path.resolve()),
        "db_path": str(db_path),
        "db_open_mode": "ro",
        "sales_source_table": "sales_fact_v2",
        "floor_csv_path": str(floor_csv_path),
        "floor_version": str(config.get("floor_version") or ""),
        "floor_rows_loaded": len(floor_rows),
        "floor_errors": floor_errors,
        "floor_alias_count": len(config.get("floor_aliases") or {}),
        "selloff_price_protect_errors": selloff_protect_errors,
        "scoring_exception_authority_entry_count": len(scoring_exception_entries),
        "scoring_exception_authority_errors": scoring_exception_errors,
        "window_days": window_days,
        "window_start": start_date.isoformat(),
        "window_end": as_of_date.isoformat(),
        "latest_sales_date": latest_sales.isoformat() if latest_sales else "",
        "sales_data_lag_days": sales_lag_days,
        "max_sales_data_lag_days": max_sales_lag_days,
        "sales_row_count_total": len(sales_rows),
        "non_cancelled_row_count": len(non_cancelled_rows),
        "non_cancelled_units": non_cancelled_units,
        "under_floor_row_count": len(under_floor_rows),
        "under_floor_units": under_floor_units,
        "under_floor_gap_kzt": _fmt_money(gap_total),
        "selloff_protected": {
            "source_kind": selloff_protect["source_kind"],
            "source_path": selloff_protect["source_path"],
            "schema_version": selloff_protect["schema_version"],
            "never_raise": selloff_protect["never_raise"],
            "sku_key_prefixes": selloff_protect["sku_key_prefixes"],
            "product_codes": selloff_protect["product_codes"],
            "owner_decision": selloff_protect["owner_decision"],
            "warnings": selloff_protect_warnings,
            "rows": selloff_protected_rows,
            "row_count": len(selloff_protected_rows),
            "units": selloff_protected_units,
            "gap_kzt": _fmt_money(selloff_protected_gap_total),
        },
        "strategic_brand_pricing_excluded_rows": strategic_excluded_rows,
        "strategic_brand_pricing_excluded_row_count": len(strategic_excluded_rows),
        "strategic_brand_pricing_excluded_units": strategic_excluded_units,
        "strategic_brand_pricing_excluded_gap_kzt": _fmt_money(strategic_excluded_gap_total),
        "missing_floor_row_count": len(missing_floor_rows),
        "missing_floor_units": missing_floor_units,
        "missing_price_row_count": len(missing_price_rows),
        "missing_price_units": missing_price_units,
        "checks": checks,
        "artifacts": {
            "under_floor_sales_csv": str(under_floor_csv),
            "selloff_protected_csv": str(selloff_protected_csv),
            "strategic_brand_pricing_excluded_csv": str(strategic_excluded_csv),
            "missing_floor_sales_csv": str(missing_floor_csv),
            "missing_price_sales_csv": str(missing_price_csv),
            "under_floor_by_sku_csv": str(by_sku_csv),
        },
        "production_db_written": False,
        "external_writes_performed": False,
        "forbidden_writes_performed": False,
    }
    json_path = output_dir / "under_floor_leak_report.json"
    md_path = output_dir / "under_floor_leak_report.md"
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Report G-PRICE-03 under-floor leak status.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--strict", action="store_true", help="Return non-zero unless gate is GREEN.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_under_floor_leak_report(
        config_path=args.config,
        output_root=args.output_dir,
        as_of=args.as_of or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Gate: {report['gate']}")
        print(f"ok: {report['ok']}")
        print(f"under_floor_units: {report['under_floor_units']}")
        print(f"selloff_protected_units: {report['selloff_protected']['units']}")
        print(f"strategic_brand_pricing_excluded_units: {report['strategic_brand_pricing_excluded_units']}")
        print(f"missing_floor_rows: {report['missing_floor_row_count']}")
        print(f"Report: {report['json_path']}")
    if args.strict and report["gate"] != "GREEN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
