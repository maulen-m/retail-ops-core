from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from core.ads.active_scope import resolve_active_store_codes
from core.ops.operational_stock_integration_gates import (
    evaluate_operational_stock_integration_gates,
)
from core.ops.policy_registry_c3 import (
    BLOCKING_FRESHNESS_STATUSES,
    DEFAULT_DB_PATH,
    DEFAULT_POLICY_PATH,
    POLICY_NAMESPACE,
    REQUIRED_C3_GATE_NAMES,
    backup_database,
    validate_exception_queue_db,
    validate_manual_decision_approvals,
    validate_operational_decision_policy_registry,
    validate_policy_gate_results,
    validate_policy_registry_schema,
    validate_policy_source_freshness,
    connect_readonly,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
C3_MATERIALIZATION_ENV_GATE = "ENABLE_C3_POLICY_MATERIALIZATION_WRITE"
COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_CONTRACT = "SOURCE_FRESHNESS_BRIDGE_COPIED_TEMP_V1"
COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_REQUIRED_FIELDS = {
    "source_id",
    "source_packet_path",
    "source_packet_sha",
    "captured_at",
    "as_of",
    "status",
    "blocks_publication",
    "proof_scope",
    "production_authority",
}
ALMATY = timezone(timedelta(hours=5))

OPERATIONAL_TABLE_SOURCES: tuple[tuple[str, str], ...] = (
    ("fact_inventory_snapshot_size", "snapshot_date"),
    ("stock_ledger", "event_date"),
    ("sales_fact_v2", "order_date"),
    ("order_status_event", "event_ts"),
    ("fact_order_entries_kaspi", "updated_at"),
    ("ads_source_refresh_runs", "date_end"),
    ("ads_campaign_product_daily", "date"),
    ("fact_cashflow_events", "event_date"),
    ("fact_cashflow_daily", "date"),
)

AB_OPERATIONAL_ROLLUP_SOURCE_ID = "src_ab_db_operational_truth"
AB_OPERATIONAL_CHILD_SOURCE_TABLES: dict[str, tuple[tuple[str, str], ...]] = {
    "src_ab_db_order_entry_truth": (("fact_order_entries_kaspi", "updated_at"),),
    "src_ab_db_cashflow_truth": (
        ("fact_cashflow_events", "event_date"),
        ("fact_cashflow_daily", "date"),
    ),
    "src_ab_db_stock_truth": (
        ("fact_inventory_snapshot_size", "snapshot_date"),
        ("stock_ledger", "event_date"),
    ),
    "src_ab_db_sales_truth": (("sales_fact_v2", "order_date"),),
    "src_ab_db_order_status_truth": (("order_status_event", "event_ts"),),
    "src_ab_db_ads_truth": (
        ("ads_source_refresh_runs", "date_end"),
        ("ads_campaign_product_daily", "date"),
    ),
}

TABLE_DATE_COLUMNS = dict(OPERATIONAL_TABLE_SOURCES)

AGENT8_HANDOFF_ROOT = Path(
    "~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave"
)
AGENT6_STOCK_REBUILD_ROOT = Path(
    "~/Docs/Autonomous_business_agent_handoffs/"
    "2026-05-03_operational-stock-truth-system/agent6_stock_rebuild_20pct_outputs"
)

DIRECTORY_SCAN_HINTS: dict[str, tuple[str, ...]] = {
    "src_ecommerce_po_artifacts": (
        "docs/Purchase_orders/Products/LINE31",
        "docs/agent_handoffs",
    ),
    "src_sourcing_research_supplier_routes": (
        "captures",
        "docs",
    ),
    "src_facebook_ads_external_ads": (
        "docs",
        "exports",
    ),
}

META_FACEBOOK_SOURCE_ID = "src_facebook_ads_external_ads"
META_EXTERNAL_SPEND_TABLE = "meta_external_ads_spend_daily"
META_EXTERNAL_SPEND_SOURCE_SYSTEM = "meta_instagram"
META_SOURCE_FRESHNESS_PACKET_NAMES = (
    "meta_live_refresh_summary.json",
    "meta_source_freshness_summary.json",
)
WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID = "src_web_automation_kaspi_marketing_directapi"
WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE = (
    Path("runs")
    / "ab_ads_source_refresh_data_gathering"
    / "20260505_source_packet_standardization"
    / "kaspi_marketing_source_freshness_packet.json"
)
WEB_AUTOMATION_KASPI_MARKETING_SUPPORTED_STORES = ("ACMEWEAR", "STOREB")
WEB_AUTOMATION_KASPI_MARKETING_ZERO_FIELDS = (
    "external_write_operations",
    "ad_platform_write_operations",
    "campaign_bid_budget_product_state_changes",
    "autonomous_business_writes",
    "agent38_live_external_operations",
    "agent38_live_browser_operations",
    "agent38_autonomous_business_writes",
)
WEB_AUTOMATION_KASPI_MARKETING_STRICT_TRUE_FIELDS = (
    "all_referenced_files_exist",
    "all_recorded_hashes_match_at_generation",
    "all_source_evidence_summaries_json_valid",
    "all_source_sqlite_integrity_ok",
    "source_write_counts_zero_or_closeout_proven_zero",
    "no_live_calls_made_by_agent38",
    "no_autonomous_business_mutation_by_agent38",
)
WEB_AUTOMATION_KASPI_MARKETING_STORE_ZERO_FIELDS = (
    "external_write_operations",
    "ad_platform_write_operations",
    "campaign_bid_budget_product_state_changes",
    "autonomous_business_writes",
)
WEB_AUTOMATION_KASPI_MARKETING_CLOSEOUT_NO_WRITE_FIELDS = (
    "states_no_autonomous_business_writes",
    "states_no_external_writes",
    "states_no_campaign_bid_budget_product_state_changes",
    "states_no_secret_storage",
)

DIRECTORY_SCAN_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}

DIRECTORY_SCAN_SKIP_FILES = {
    ".DS_Store",
}


def _now_iso() -> str:
    return datetime.now(tz=ALMATY).isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _active_policy(conn: sqlite3.Connection) -> sqlite3.Row:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM policy_version
        WHERE namespace=? AND status='ACTIVE'
        """,
        (POLICY_NAMESPACE,),
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError(f"Expected exactly one ACTIVE {POLICY_NAMESPACE} policy; found {len(rows)}")
    return rows[0]


def _as_of_cutoff(as_of: str) -> datetime:
    parsed_date = datetime.fromisoformat(as_of[:10]).date()
    return datetime.combine(parsed_date, time(23, 59, 59), tzinfo=ALMATY)


def _parse_observed_at(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        try:
            return datetime.combine(datetime.fromisoformat(text).date(), time.min, tzinfo=ALMATY)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.combine(datetime.fromisoformat(text[:10]).date(), time.min, tzinfo=ALMATY)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ALMATY)
    return parsed.astimezone(ALMATY)


def _parse_date_only(value: Any) -> datetime | None:
    try:
        parsed_date = datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None
    return datetime.combine(parsed_date, time(23, 59, 59), tzinfo=ALMATY)


def _max_age_seconds(row: sqlite3.Row) -> int | None:
    value = row["max_age_value"]
    unit = str(row["max_age_unit"] or "").lower()
    if value is None or not unit:
        return None
    numeric = int(value)
    if unit.startswith("hour"):
        return numeric * 60 * 60
    if unit.startswith("day"):
        return numeric * 24 * 60 * 60
    return None


def _status_from_observed(
    *,
    max_observed_at: datetime | None,
    cutoff: datetime,
    max_age_seconds: int | None,
) -> tuple[str, int | None]:
    if max_observed_at is None:
        return "UNKNOWN", None
    lag_seconds = int((cutoff - max_observed_at).total_seconds())
    if lag_seconds < -60:
        return "FUTURE", lag_seconds
    if max_age_seconds is not None and lag_seconds > max_age_seconds:
        return "STALE", lag_seconds
    return "FRESH", max(0, lag_seconds)


def _resolve_source_path(source_path: str | None) -> Path | None:
    if not source_path:
        return None
    path = Path(source_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _directory_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
        entry_count = sum(1 for _ in path.iterdir())
    except OSError:
        return ""
    return _sha256_text(f"{path}:{stat.st_mtime_ns}:{entry_count}")


def _directory_scan_roots(path: Path, policy_source_id: str) -> list[Path]:
    hints = DIRECTORY_SCAN_HINTS.get(policy_source_id, ())
    hinted_roots = [path / hint for hint in hints if (path / hint).exists()]
    return hinted_roots or [path]


def _artifact_payload(root: Path, artifact: Path, mtime: datetime) -> dict[str, Any]:
    try:
        relative_path = str(artifact.relative_to(root))
    except ValueError:
        relative_path = str(artifact)
    try:
        size_bytes = artifact.stat().st_size
    except OSError:
        size_bytes = None
    return {
        "path": str(artifact),
        "relative_path": relative_path,
        "mtime": mtime.isoformat(timespec="seconds"),
        "size_bytes": size_bytes,
    }


def _walk_directory_artifacts(path: Path, policy_source_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    artifacts: list[dict[str, Any]] = []
    issues: list[str] = []
    for scan_root in _directory_scan_roots(path, policy_source_id):
        for dirpath, dirnames, filenames in os.walk(scan_root, followlinks=False):
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if dirname not in DIRECTORY_SCAN_SKIP_DIRS and not dirname.startswith(".")
            ]
            root = Path(dirpath)
            for filename in filenames:
                if filename in DIRECTORY_SCAN_SKIP_FILES or filename.startswith("."):
                    continue
                artifact = root / filename
                try:
                    stat = artifact.stat()
                except OSError as exc:
                    issues.append(f"ARTIFACT_STAT_ERROR:{artifact}:{exc}")
                    continue
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=ALMATY)
                artifacts.append(_artifact_payload(path, artifact, mtime))
    artifacts.sort(key=lambda item: (str(item["mtime"]), str(item["relative_path"])))
    return artifacts, issues


def _meta_source_packet_sort_dt(packet_path: Path) -> datetime:
    generated: datetime | None = None
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        generated = _parse_observed_at(payload.get("generated_at_utc"))
    if generated is not None:
        return generated
    try:
        return datetime.fromtimestamp(packet_path.stat().st_mtime, tz=ALMATY)
    except OSError:
        return datetime.min.replace(tzinfo=ALMATY)


def _meta_source_packet_candidates(source_root: Path) -> list[Path]:
    runs_root = source_root / "runs"
    if not runs_root.exists() or not runs_root.is_dir():
        return []
    candidates: list[Path] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        run_name = run_dir.name.lower()
        if not run_name.startswith("ab_source_freshness_"):
            continue
        if "meta" not in run_name and "facebook" not in run_name:
            continue
        for packet_name in META_SOURCE_FRESHNESS_PACKET_NAMES:
            packet_path = run_dir / packet_name
            if packet_path.exists() and packet_path.is_file():
                candidates.append(packet_path)
    candidates.sort(key=lambda item: (_meta_source_packet_sort_dt(item), str(item)))
    return candidates


def _date_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    dates: list[str] = []
    for item in value:
        parsed = _parse_date_only(item)
        if parsed is None:
            return None
        dates.append(str(item)[:10])
    return dates


def _meta_date_results_by_date(value: Any, issues: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        issues.append("DATE_RESULTS_MISSING")
        return {}
    results: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            issues.append("DATE_RESULT_NOT_MAPPING")
            continue
        date_value = item.get("date")
        if _parse_date_only(date_value) is None:
            issues.append("DATE_RESULT_DATE_INVALID")
            continue
        results[str(date_value)[:10]] = item
    return results


def _raw_meta_evidence_path_for_date(
    packet: dict[str, Any],
    date: str,
    date_result: dict[str, Any] | None,
) -> str | None:
    raw_paths = packet.get("raw_evidence_paths")
    if isinstance(raw_paths, dict) and raw_paths.get(date):
        return str(raw_paths[date])
    if date_result and date_result.get("raw_evidence_path"):
        return str(date_result["raw_evidence_path"])
    return None


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _numeric_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_meta_spend_by_date(
    *,
    packet: dict[str, Any],
    requested_dates: list[str],
    date_results: dict[str, dict[str, Any]],
) -> dict[str, float]:
    spend_by_date: dict[str, float] = {}
    packet_spend = packet.get("spend_by_date")
    if isinstance(packet_spend, dict):
        for date in requested_dates:
            amount = _numeric_value(packet_spend.get(date))
            if amount is not None and amount > 0:
                spend_by_date[date] = amount
    for date in requested_dates:
        result = date_results.get(date)
        if result is None:
            continue
        amount = _numeric_value(result.get("spend"))
        if amount is not None and amount > 0:
            spend_by_date[date] = amount
    return spend_by_date


def _raw_meta_account_id(raw_path_text: str | None) -> str:
    if not raw_path_text:
        return ""
    raw_path = Path(str(raw_path_text)).expanduser()
    if not raw_path.exists() or not raw_path.is_file():
        return ""
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("account_id") or "").strip()


def _meta_external_spend_ingestion_status(
    *,
    conn: sqlite3.Connection | None,
    source: sqlite3.Row,
    packet: dict[str, Any],
    packet_path: Path,
    packet_sha256: str,
    positive_spend_by_date: dict[str, float],
    date_results: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    evidence: dict[str, Any] = {
        "ingestion_table": META_EXTERNAL_SPEND_TABLE,
        "source_system": META_EXTERNAL_SPEND_SOURCE_SYSTEM,
        "positive_spend_dates": sorted(positive_spend_by_date),
        "ingested_rows": [],
    }
    if not positive_spend_by_date:
        return [], evidence
    if conn is None:
        return ["EXTERNAL_SPEND_INGESTION_CONN_MISSING"], evidence
    if not _table_exists(conn, META_EXTERNAL_SPEND_TABLE):
        return ["EXTERNAL_SPEND_INGESTION_TABLE_MISSING"], evidence

    issues: list[str] = []
    store_code = str(source["route_key"] or "ACMEWEAR").strip().upper() or "ACMEWEAR"
    packet_account_id = str(packet.get("account_id") or "").strip()
    account_ids: set[str] = set()

    for date, expected_spend in sorted(positive_spend_by_date.items()):
        result = date_results.get(date) or {}
        raw_from_packet = _raw_meta_evidence_path_for_date(packet, date, result)
        account_id = packet_account_id or _raw_meta_account_id(raw_from_packet)
        if not account_id:
            issues.append(f"EXTERNAL_SPEND_ACCOUNT_ID_MISSING:{date}")
            continue
        account_ids.add(account_id)
        rows = conn.execute(
            f"""
            SELECT date, store_code, source_system, account_id, spend_amount,
                   spend_basis, packet_path, packet_sha256, raw_evidence_path,
                   raw_evidence_sha256, publication_attribution_claimed
            FROM {META_EXTERNAL_SPEND_TABLE}
            WHERE source_system=?
              AND store_code=?
              AND date=?
              AND account_id=?
            ORDER BY ingested_at DESC, rowid DESC
            LIMIT 1
            """,
            (META_EXTERNAL_SPEND_SOURCE_SYSTEM, store_code, date, account_id),
        ).fetchone()
        if rows is None:
            issues.append(f"EXTERNAL_SPEND_INGESTION_ROW_MISSING:{date}")
            continue
        row = dict(rows)
        evidence["ingested_rows"].append(row)
        amount = _numeric_value(row.get("spend_amount"))
        if amount is None or abs(amount - expected_spend) > 0.01:
            issues.append(f"EXTERNAL_SPEND_AMOUNT_MISMATCH:{date}")
        if str(row.get("packet_sha256") or "") != packet_sha256:
            issues.append(f"EXTERNAL_SPEND_PACKET_SHA_MISMATCH:{date}")
        raw_path_text = row.get("raw_evidence_path")
        if not raw_path_text:
            issues.append(f"EXTERNAL_SPEND_RAW_PATH_MISSING:{date}")
        else:
            raw_path = Path(str(raw_path_text)).expanduser()
            if not raw_path.exists() or not raw_path.is_file():
                issues.append(f"EXTERNAL_SPEND_RAW_FILE_MISSING:{date}")
            else:
                raw_hash = _sha256_file(raw_path)
                if str(row.get("raw_evidence_sha256") or "") != raw_hash:
                    issues.append(f"EXTERNAL_SPEND_RAW_SHA_MISMATCH:{date}")
        if int(row.get("publication_attribution_claimed") or 0) != 0:
            issues.append(f"EXTERNAL_SPEND_ATTRIBUTION_CLAIMED:{date}")
        if raw_from_packet and raw_path_text and str(Path(str(raw_path_text)).expanduser()) != str(
            Path(str(raw_from_packet)).expanduser()
        ):
            issues.append(f"EXTERNAL_SPEND_RAW_PATH_DIFFERS_FROM_PACKET:{date}")
        packet_path_text = str(row.get("packet_path") or "")
        if packet_path_text and str(Path(packet_path_text).expanduser()) != str(packet_path):
            issues.append(f"EXTERNAL_SPEND_PACKET_PATH_MISMATCH:{date}")

    evidence["ingestion_issues"] = issues
    evidence["ingestion_complete"] = not issues
    evidence["account_ids"] = sorted(account_ids)
    return issues, evidence


def _observe_meta_source_freshness_packet(
    *,
    conn: sqlite3.Connection | None,
    source: sqlite3.Row,
    path: Path,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]:
    base_evidence: dict[str, Any] = {
        "source_path": source["source_path"],
        "source_kind": source["source_kind"],
        "observation_type": "meta_source_freshness_packet",
        "resolved_path": str(path),
        "packet_names": list(META_SOURCE_FRESHNESS_PACKET_NAMES),
    }
    candidates = _meta_source_packet_candidates(path)
    base_evidence["candidate_packets"] = [str(item) for item in candidates]
    if not candidates:
        evidence = {
            **base_evidence,
            "issues": ["META_SOURCE_FRESHNESS_PACKET_MISSING"],
        }
        return {
            "status": "MISSING",
            "max_observed_at": None,
            "source_sha256": _sha256_text(_json(evidence)),
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }

    packet_path = candidates[-1]
    issues: list[str] = []
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence = {
            **base_evidence,
            "packet_path": str(packet_path),
            "issues": [f"PACKET_JSON_PARSE_ERROR:{exc}"],
        }
        return {
            "status": "BLOCKED",
            "max_observed_at": None,
            "source_sha256": _sha256_file(packet_path),
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }
    if not isinstance(packet, dict):
        issues.append("PACKET_NOT_MAPPING")
        packet = {}

    requested_dates = _date_string_list(packet.get("dates_requested"))
    if not requested_dates:
        issues.append("DATES_REQUESTED_MISSING_OR_INVALID")
        requested_dates = []
    successfully_fetched = _date_string_list(packet.get("dates_successfully_fetched"))
    if successfully_fetched is None:
        issues.append("DATES_SUCCESSFULLY_FETCHED_MISSING_OR_INVALID")
        successfully_fetched = []
    if set(successfully_fetched) != set(requested_dates):
        issues.append("REQUESTED_DATES_NOT_ALL_SUCCESSFULLY_FETCHED")

    false_flag_issues = {
        "platform_writes_occurred": "PLATFORM_WRITES_OCCURRED",
        "budget_status_campaign_adset_ad_writes_occurred": (
            "BUDGET_STATUS_CAMPAIGN_ADSET_AD_WRITES_OCCURRED"
        ),
        "autonomous_business_writes_performed": "AUTONOMOUS_BUSINESS_WRITES_PERFORMED",
        "deterministic_purchase_attribution_claimed": (
            "DETERMINISTIC_PURCHASE_ATTRIBUTION_CLAIMED"
        ),
    }
    for key, issue in false_flag_issues.items():
        if packet.get(key) is not False:
            issues.append(issue)

    date_results = _meta_date_results_by_date(packet.get("date_results"), issues)
    cleared_by_date = packet.get("source_freshness_cleared_by_date")
    if cleared_by_date is not None and not isinstance(cleared_by_date, dict):
        issues.append("SOURCE_FRESHNESS_CLEARED_BY_DATE_NOT_MAPPING")
        cleared_by_date = {}

    positive_spend_by_date = _positive_meta_spend_by_date(
        packet=packet,
        requested_dates=requested_dates,
        date_results=date_results,
    )
    if packet.get("any_spend_found") not in {False, None} and not positive_spend_by_date:
        issues.append("SPEND_FOUND_REQUIRES_EXTERNAL_ADS_INGESTION")
    external_spend_issues, external_spend_evidence = _meta_external_spend_ingestion_status(
        conn=conn,
        source=source,
        packet=packet,
        packet_path=packet_path,
        packet_sha256=_sha256_file(packet_path),
        positive_spend_by_date=positive_spend_by_date,
        date_results=date_results,
    )
    if positive_spend_by_date:
        issues.extend(external_spend_issues)
        if packet.get("gate") not in {"GREEN", "YELLOW"}:
            issues.append("GATE_NOT_GREEN")
        if external_spend_issues:
            issues.append("SPEND_FOUND_REQUIRES_EXTERNAL_ADS_INGESTION")
    else:
        if packet.get("gate") != "GREEN":
            issues.append("GATE_NOT_GREEN")
        if packet.get("ab_can_clear_src_facebook_ads_external_ads") is not True:
            issues.append("AB_CAN_CLEAR_NOT_TRUE")

    verified_raw_paths: dict[str, str] = {}
    for date in requested_dates:
        result = date_results.get(date)
        if result is None:
            issues.append(f"DATE_RESULT_MISSING:{date}")
            continue
        if result.get("source_status") != "SUCCESS":
            issues.append(f"DATE_RESULT_NOT_SUCCESS:{date}")
        if result.get("clears_source_freshness") is not True:
            issues.append(f"DATE_RESULT_DOES_NOT_CLEAR_SOURCE_FRESHNESS:{date}")
        if isinstance(cleared_by_date, dict) and cleared_by_date.get(date) is not True:
            issues.append(f"SUMMARY_DATE_DOES_NOT_CLEAR_SOURCE_FRESHNESS:{date}")
        raw_path_text = _raw_meta_evidence_path_for_date(packet, date, result)
        if not raw_path_text:
            issues.append(f"RAW_EVIDENCE_PATH_MISSING:{date}")
            continue
        raw_path = Path(raw_path_text).expanduser()
        if not raw_path.exists() or not raw_path.is_file():
            issues.append(f"RAW_EVIDENCE_FILE_MISSING:{date}")
            continue
        if not _path_is_under(raw_path, packet_path.parent):
            issues.append(f"RAW_EVIDENCE_OUTSIDE_PACKET_RUN:{date}")
            continue
        verified_raw_paths[date] = str(raw_path)

    observed_window = max(
        (parsed for parsed in (_parse_date_only(date) for date in requested_dates) if parsed is not None),
        default=None,
    )
    if observed_window is None:
        status = "BLOCKED"
        lag_seconds = None
        max_observed_at = None
    elif issues:
        status = "BLOCKED"
        _, lag_seconds = _status_from_observed(
            max_observed_at=observed_window,
            cutoff=_as_of_cutoff(as_of),
            max_age_seconds=_max_age_seconds(source),
        )
        max_observed_at = observed_window.isoformat(timespec="seconds")
    else:
        status, lag_seconds = _status_from_observed(
            max_observed_at=observed_window,
            cutoff=_as_of_cutoff(as_of),
            max_age_seconds=_max_age_seconds(source),
        )
        max_observed_at = observed_window.isoformat(timespec="seconds")

    evidence = {
        **base_evidence,
        "packet_path": str(packet_path),
        "packet_sha256": _sha256_file(packet_path),
        "packet_gate": packet.get("gate"),
        "ab_can_clear_src_facebook_ads_external_ads": packet.get(
            "ab_can_clear_src_facebook_ads_external_ads"
        ),
        "dates_requested": requested_dates,
        "dates_successfully_fetched": successfully_fetched,
        "verified_raw_evidence_paths": verified_raw_paths,
        "any_spend_found": packet.get("any_spend_found"),
        "positive_spend_by_date": positive_spend_by_date,
        "external_spend_ingestion": external_spend_evidence,
        "platform_writes_occurred": packet.get("platform_writes_occurred"),
        "budget_status_campaign_adset_ad_writes_occurred": packet.get(
            "budget_status_campaign_adset_ad_writes_occurred"
        ),
        "autonomous_business_writes_performed": packet.get(
            "autonomous_business_writes_performed"
        ),
        "deterministic_purchase_attribution_claimed": packet.get(
            "deterministic_purchase_attribution_claimed"
        ),
        "issues": sorted(set(issues)),
        "max_age_value": source["max_age_value"],
        "max_age_unit": source["max_age_unit"],
    }
    return {
        "status": status,
        "max_observed_at": max_observed_at,
        "source_sha256": _sha256_file(packet_path),
        "row_count": len(date_results) or len(requested_dates),
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _web_automation_root_from_path(path: Path) -> Path | None:
    parts = path.parts
    if "Web_automation" not in parts:
        return None
    index = parts.index("Web_automation")
    return Path(*parts[: index + 1])


def _web_automation_kaspi_packet_candidates(path: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if path is None:
        candidates.append(Path("~/Docs/Web_automation") / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE)
    else:
        if path.name == WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE.name:
            candidates.append(path)
        candidates.append(path / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE)
        root = _web_automation_root_from_path(path)
        if root is not None:
            candidates.append(root / WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.expanduser())
        if key not in seen:
            seen.add(key)
            unique.append(candidate.expanduser())
    return unique


def _first_existing_file(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _date_flag_key(as_of: str) -> str:
    return "date_coverage_through_" + as_of.replace("-", "_")


def _date_covers_as_of(value: Any, as_of: str) -> bool:
    parsed = _parse_date_only(value)
    as_of_parsed = _parse_date_only(as_of)
    return parsed is not None and as_of_parsed is not None and parsed >= as_of_parsed


def _reference_label(item: dict[str, Any], index: int) -> str:
    for key in ("store", "role", "path"):
        value = item.get(key)
        if value:
            return str(value)
    return str(index)


def _validate_json_reference_file(path: Path, issues: list[str], label: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"SOURCE_EVIDENCE_SUMMARY_JSON_PARSE_ERROR:{label}:{exc}")
        return
    if not isinstance(payload, (dict, list)):
        issues.append(f"SOURCE_EVIDENCE_SUMMARY_JSON_NOT_OBJECT_OR_LIST:{label}")


def _validate_sqlite_reference_file(path: Path, issues: list[str], label: str) -> None:
    try:
        with sqlite3.connect(str(path)) as conn:
            result = conn.execute("PRAGMA integrity_check;").fetchone()
    except Exception as exc:
        issues.append(f"SOURCE_SQLITE_INTEGRITY_ERROR:{label}:{exc}")
        return
    status = str(result[0] if result else "")
    if status.lower() != "ok":
        issues.append(f"SOURCE_SQLITE_INTEGRITY_NOT_OK:{label}:{status}")


def _validate_packet_reference_list(
    packet: dict[str, Any],
    key: str,
    issues: list[str],
    *,
    prefix: str,
    parse_json: bool = False,
    sqlite_integrity: bool = False,
) -> list[str]:
    value = packet.get(key)
    if not isinstance(value, list) or not value:
        issues.append(f"{prefix}_LIST_MISSING_OR_EMPTY")
        return []

    verified_paths: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            issues.append(f"{prefix}_ENTRY_NOT_MAPPING:{index}")
            continue
        label = _reference_label(item, index)
        path_text = item.get("path")
        if not path_text:
            issues.append(f"{prefix}_PATH_MISSING:{label}")
            continue
        path = Path(str(path_text)).expanduser()
        if item.get("exists") is not True:
            issues.append(f"{prefix}_EXISTS_FLAG_NOT_TRUE:{label}")
        if not path.exists() or not path.is_file():
            issues.append(f"{prefix}_FILE_MISSING:{label}")
            continue
        expected_hash = str(item.get("sha256") or "")
        if not expected_hash:
            issues.append(f"{prefix}_HASH_MISSING:{label}")
        else:
            actual_hash = _sha256_file(path)
            if actual_hash != expected_hash:
                issues.append(f"{prefix}_HASH_MISMATCH:{label}")
        if parse_json:
            if item.get("json_valid") is not True:
                issues.append(f"{prefix}_JSON_VALID_FLAG_NOT_TRUE:{label}")
            _validate_json_reference_file(path, issues, label)
        if sqlite_integrity:
            if str(item.get("sqlite_integrity_check") or "").lower() != "ok":
                issues.append(f"{prefix}_RECORDED_INTEGRITY_NOT_OK:{label}")
            _validate_sqlite_reference_file(path, issues, label)
        verified_paths.append(str(path))
    return verified_paths


def _validate_zero_write_map(
    payload: dict[str, Any] | None,
    *,
    issues: list[str],
    label: str,
    issue_prefix: str,
) -> None:
    if not isinstance(payload, dict):
        issues.append(f"{issue_prefix}_MISSING:{label}")
        return
    for field in WEB_AUTOMATION_KASPI_MARKETING_STORE_ZERO_FIELDS:
        if field not in payload:
            issues.append(f"{issue_prefix}_FIELD_MISSING:{label}:{field}")
        elif payload.get(field) != 0:
            issues.append(f"{issue_prefix}_FIELD_NONZERO:{label}:{field}")
    if "secret_values_stored" in payload and payload.get("secret_values_stored") is not False:
            issues.append(f"{issue_prefix}_SECRET_VALUES_STORED:{label}")


def _web_automation_kaspi_marketing_required_stores(as_of: str) -> tuple[str, ...]:
    supported = set(WEB_AUTOMATION_KASPI_MARKETING_SUPPORTED_STORES)
    active = {str(store).strip().upper() for store in resolve_active_store_codes(as_of)}
    return tuple(sorted(store for store in active if store in supported))


def _web_automation_packet_observed_window(
    packet: dict[str, Any],
    as_of: str,
) -> datetime | None:
    values: list[Any] = [
        packet.get("as_of"),
        (packet.get("strict_requirements") or {}).get("date_coverage_through")
        if isinstance(packet.get("strict_requirements"), dict)
        else None,
    ]
    store_coverage = packet.get("store_coverage")
    if isinstance(store_coverage, dict):
        for store_payload in store_coverage.values():
            if isinstance(store_payload, dict):
                values.append(store_payload.get("latest_covered_date"))
    parsed_values = [parsed for parsed in (_parse_date_only(value) for value in values) if parsed]
    if parsed_values:
        return max(parsed_values)
    return _parse_date_only(as_of)


def _observe_web_automation_kaspi_marketing_packet(
    *,
    source: sqlite3.Row,
    path: Path | None,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]:
    candidates = _web_automation_kaspi_packet_candidates(path)
    packet_path = _first_existing_file(candidates)
    base_evidence: dict[str, Any] = {
        "source_path": source["source_path"],
        "source_kind": source["source_kind"],
        "observation_type": "web_automation_kaspi_marketing_source_packet",
        "required_packet_relative_path": str(WEB_AUTOMATION_KASPI_MARKETING_PACKET_RELATIVE),
        "candidate_packets": [str(item) for item in candidates],
    }
    if packet_path is None:
        evidence = {
            **base_evidence,
            "issues": ["KASPI_MARKETING_SOURCE_PACKET_MISSING"],
        }
        return {
            "status": "MISSING",
            "max_observed_at": None,
            "source_sha256": _sha256_text(_json(evidence)),
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }

    issues: list[str] = []
    try:
        packet_raw = json.loads(packet_path.read_text(encoding="utf-8"))
    except Exception as exc:
        evidence = {
            **base_evidence,
            "packet_path": str(packet_path),
            "packet_sha256": _sha256_file(packet_path),
            "issues": [f"PACKET_JSON_PARSE_ERROR:{exc}"],
        }
        return {
            "status": "BLOCKED",
            "max_observed_at": None,
            "source_sha256": _sha256_file(packet_path),
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }
    if not isinstance(packet_raw, dict):
        packet: dict[str, Any] = {}
        issues.append("PACKET_NOT_MAPPING")
    else:
        packet = packet_raw

    if packet.get("schema_version") != "kaspi_marketing_source_freshness_packet.v1":
        issues.append("SCHEMA_VERSION_INVALID")
    if packet.get("source_policy_key") != WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID:
        issues.append("SOURCE_POLICY_KEY_MISMATCH")
    if packet.get("gate") != "GREEN":
        issues.append("GATE_NOT_GREEN")
    if packet.get("ab_can_clear_src_web_automation_kaspi_marketing_directapi") is not True:
        issues.append("AB_CAN_CLEAR_NOT_TRUE")
    if packet.get("as_of") != as_of:
        issues.append(f"PACKET_AS_OF_MISMATCH:{packet.get('as_of')}")
    try:
        required_stores = _web_automation_kaspi_marketing_required_stores(as_of)
    except Exception as exc:
        issues.append(f"ACTIVE_SCOPE_RESOLUTION_ERROR:{exc}")
        required_stores = WEB_AUTOMATION_KASPI_MARKETING_SUPPORTED_STORES

    for field in WEB_AUTOMATION_KASPI_MARKETING_ZERO_FIELDS:
        if field not in packet:
            issues.append(f"NO_WRITE_FIELD_MISSING:{field}")
        elif packet.get(field) != 0:
            issues.append(f"NO_WRITE_FIELD_NONZERO:{field}")
    if "read_only_external_operations" not in packet:
        issues.append("NO_WRITE_FIELD_MISSING:read_only_external_operations")
    elif packet.get("read_only_external_operations") is not True:
        issues.append("READ_ONLY_EXTERNAL_OPERATIONS_NOT_TRUE")

    packet_issues = packet.get("issues")
    if packet_issues != []:
        issues.append("PACKET_ISSUES_NOT_EMPTY")
    missing_fields = packet.get("missing_fields")
    if missing_fields != []:
        issues.append("PACKET_MISSING_FIELDS_NOT_EMPTY")

    strict_requirements = packet.get("strict_requirements")
    stores_covered: list[str] = []
    if not isinstance(strict_requirements, dict):
        issues.append("STRICT_REQUIREMENTS_MISSING")
        strict_requirements = {}
    else:
        for field in WEB_AUTOMATION_KASPI_MARKETING_STRICT_TRUE_FIELDS:
            if strict_requirements.get(field) is not True:
                issues.append(f"STRICT_REQUIREMENT_NOT_TRUE:{field}")
        required = strict_requirements.get("stores_required")
        covered = strict_requirements.get("stores_covered")
        if set(required or []) != set(required_stores):
            issues.append("STORES_REQUIRED_MISMATCH")
        if not isinstance(covered, list):
            issues.append("STORES_COVERED_MISSING_OR_INVALID")
        else:
            stores_covered = sorted(str(item) for item in covered)
            for store in required_stores:
                if store not in stores_covered:
                    issues.append(f"STORE_COVERAGE_MISSING:{store}")
        date_coverage = strict_requirements.get("date_coverage_through")
        if not _date_covers_as_of(date_coverage, as_of):
            issues.append(f"DATE_COVERAGE_BEFORE_AS_OF:{date_coverage}")
        if strict_requirements.get(_date_flag_key(as_of)) is not True:
            issues.append(f"DATE_COVERAGE_FLAG_NOT_TRUE:{_date_flag_key(as_of)}")

    source_roots = packet.get("source_roots")
    if not isinstance(source_roots, list) or not source_roots:
        issues.append("SOURCE_ROOTS_MISSING_OR_EMPTY")
    else:
        for index, item in enumerate(source_roots):
            if not isinstance(item, dict):
                issues.append(f"SOURCE_ROOT_ENTRY_NOT_MAPPING:{index}")
                continue
            label = _reference_label(item, index)
            root_path_text = item.get("path")
            if not root_path_text:
                issues.append(f"SOURCE_ROOT_PATH_MISSING:{label}")
                continue
            root_path = Path(str(root_path_text)).expanduser()
            if item.get("exists") is not True:
                issues.append(f"SOURCE_ROOT_EXISTS_FLAG_NOT_TRUE:{label}")
            if not root_path.exists() or not root_path.is_dir():
                issues.append(f"SOURCE_ROOT_MISSING:{label}")

    verified_sqlite_paths = _validate_packet_reference_list(
        packet,
        "source_sqlite_files",
        issues,
        prefix="SOURCE_SQLITE",
        sqlite_integrity=True,
    )
    verified_summary_paths = _validate_packet_reference_list(
        packet,
        "source_evidence_summaries",
        issues,
        prefix="SOURCE_EVIDENCE_SUMMARY",
        parse_json=True,
    )
    verified_closeout_paths = _validate_packet_reference_list(
        packet,
        "source_closeout_files",
        issues,
        prefix="SOURCE_CLOSEOUT",
    )

    no_write_checks = packet.get("closeout_text_no_write_checks")
    if not isinstance(no_write_checks, list) or not no_write_checks:
        issues.append("CLOSEOUT_NO_WRITE_CHECKS_MISSING_OR_EMPTY")
    else:
        for index, item in enumerate(no_write_checks):
            if not isinstance(item, dict):
                issues.append(f"CLOSEOUT_NO_WRITE_CHECK_NOT_MAPPING:{index}")
                continue
            label = _reference_label(item, index)
            for field in WEB_AUTOMATION_KASPI_MARKETING_CLOSEOUT_NO_WRITE_FIELDS:
                if item.get(field) is not True:
                    issues.append(f"CLOSEOUT_NO_WRITE_FIELD_NOT_TRUE:{label}:{field}")
            path_text = item.get("path")
            if path_text and not Path(str(path_text)).expanduser().is_file():
                issues.append(f"CLOSEOUT_NO_WRITE_FILE_MISSING:{label}")

    store_coverage = packet.get("store_coverage")
    if not isinstance(store_coverage, dict):
        issues.append("STORE_COVERAGE_MISSING")
        store_coverage = {}
    for store in required_stores:
        store_payload = store_coverage.get(store)
        if not isinstance(store_payload, dict):
            issues.append(f"STORE_COVERAGE_MISSING:{store}")
            continue
        if store_payload.get("gate") != "GREEN":
            issues.append(f"STORE_GATE_NOT_GREEN:{store}")
        latest_covered = store_payload.get("latest_covered_date")
        if not _date_covers_as_of(latest_covered, as_of):
            issues.append(f"STORE_DATE_COVERAGE_BEFORE_AS_OF:{store}:{latest_covered}")
        if store_payload.get(_date_flag_key(as_of)) is not True:
            issues.append(f"STORE_DATE_COVERAGE_FLAG_NOT_TRUE:{store}:{_date_flag_key(as_of)}")
        write_safety = store_payload.get("write_safety_from_summary")
        if not isinstance(write_safety, dict):
            write_safety = store_payload.get("write_safety_from_closeouts")
        _validate_zero_write_map(
            write_safety if isinstance(write_safety, dict) else None,
            issues=issues,
            label=store,
            issue_prefix="STORE_WRITE_SAFETY",
        )

    observed_window = _web_automation_packet_observed_window(packet, as_of)
    max_observed_at = observed_window.isoformat(timespec="seconds") if observed_window else None
    if issues:
        status = "BLOCKED"
        _, lag_seconds = _status_from_observed(
            max_observed_at=observed_window,
            cutoff=_as_of_cutoff(as_of),
            max_age_seconds=_max_age_seconds(source),
        )
    else:
        status, lag_seconds = _status_from_observed(
            max_observed_at=observed_window,
            cutoff=_as_of_cutoff(as_of),
            max_age_seconds=_max_age_seconds(source),
        )

    evidence = {
        **base_evidence,
        "packet_path": str(packet_path),
        "packet_sha256": _sha256_file(packet_path),
        "packet_gate": packet.get("gate"),
        "packet_as_of": packet.get("as_of"),
        "ab_can_clear_src_web_automation_kaspi_marketing_directapi": packet.get(
            "ab_can_clear_src_web_automation_kaspi_marketing_directapi"
        ),
        "stores_required": list(required_stores),
        "stores_covered": stores_covered,
        "date_coverage_through": strict_requirements.get("date_coverage_through")
        if isinstance(strict_requirements, dict)
        else None,
        "verified_source_sqlite_paths": verified_sqlite_paths,
        "verified_source_evidence_summary_paths": verified_summary_paths,
        "verified_source_closeout_paths": verified_closeout_paths,
        "issues": sorted(set(issues)),
        "max_age_value": source["max_age_value"],
        "max_age_unit": source["max_age_unit"],
    }
    return {
        "status": status,
        "max_observed_at": max_observed_at,
        "source_sha256": _sha256_file(packet_path),
        "row_count": len(verified_sqlite_paths) + len(verified_summary_paths) + len(verified_closeout_paths),
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _observe_directory_source(
    *,
    source: sqlite3.Row,
    path: Path,
    as_of: str,
    observed_at: str,
    base_evidence: dict[str, Any],
) -> dict[str, Any]:
    root_stat = path.stat()
    root_mtime = datetime.fromtimestamp(root_stat.st_mtime, tz=ALMATY)
    cutoff = _as_of_cutoff(as_of)
    max_age = _max_age_seconds(source)
    artifacts, scan_issues = _walk_directory_artifacts(path, str(source["policy_source_id"]))
    eligible_artifacts = [
        artifact
        for artifact in artifacts
        if _parse_observed_at(artifact["mtime"]) is not None
        and int((cutoff - _parse_observed_at(artifact["mtime"])).total_seconds()) >= -60
    ]
    future_artifacts = [
        artifact
        for artifact in artifacts
        if _parse_observed_at(artifact["mtime"]) is not None
        and int((cutoff - _parse_observed_at(artifact["mtime"])).total_seconds()) < -60
    ]
    latest_eligible = eligible_artifacts[-1] if eligible_artifacts else None
    latest_future = future_artifacts[-1] if future_artifacts else None

    observed = _parse_observed_at(latest_eligible["mtime"]) if latest_eligible else None
    if observed is not None:
        status, lag_seconds = _status_from_observed(
            max_observed_at=observed,
            cutoff=cutoff,
            max_age_seconds=max_age,
        )
        max_observed_at = observed.isoformat(timespec="seconds")
    elif latest_future:
        future_observed = _parse_observed_at(latest_future["mtime"])
        status, lag_seconds = _status_from_observed(
            max_observed_at=future_observed,
            cutoff=cutoff,
            max_age_seconds=max_age,
        )
        max_observed_at = future_observed.isoformat(timespec="seconds") if future_observed else None
    else:
        status, lag_seconds = _status_from_observed(
            max_observed_at=root_mtime,
            cutoff=cutoff,
            max_age_seconds=max_age,
        )
        max_observed_at = root_mtime.isoformat(timespec="seconds")

    evidence = {
        **base_evidence,
        "observation_type": "recursive_latest_artifact_metadata",
        "resolved_path": str(path),
        "exists": True,
        "is_file": False,
        "is_dir": True,
        "root_mtime": root_mtime.isoformat(timespec="seconds"),
        "scan_roots": [str(item) for item in _directory_scan_roots(path, str(source["policy_source_id"]))],
        "artifact_count": len(artifacts),
        "eligible_artifact_count": len(eligible_artifacts),
        "future_artifact_count": len(future_artifacts),
        "latest_eligible_artifact": latest_eligible,
        "latest_future_artifact": latest_future,
        "max_age_value": source["max_age_value"],
        "max_age_unit": source["max_age_unit"],
    }
    if scan_issues:
        evidence["scan_issues"] = scan_issues[:25]
    if not artifacts:
        evidence["directory_metadata_fallback"] = True

    return {
        "status": status,
        "max_observed_at": max_observed_at,
        "source_sha256": _sha256_text(_json(evidence)),
        "row_count": len(artifacts),
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _bank_manual_ingest_issues(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"YAML_PARSE_ERROR:{exc}"]
    if not isinstance(payload, dict):
        return ["YAML_NOT_MAPPING"]
    issues: list[str] = []
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        return ["STORES_MAPPING_MISSING"]
    for store, store_payload in stores.items():
        accounts = store_payload.get("accounts") if isinstance(store_payload, dict) else None
        if not isinstance(accounts, dict):
            issues.append(f"{store}:ACCOUNTS_MAPPING_MISSING")
            continue
        for account, account_payload in accounts.items():
            if not isinstance(account_payload, dict):
                issues.append(f"{store}.{account}:ACCOUNT_MAPPING_MISSING")
                continue
            for key, value in account_payload.items():
                if not str(key).startswith("balance_"):
                    continue
                label = f"{store}.{account}.{key}"
                if value is None or str(value).strip() == "":
                    issues.append(f"{label}:BALANCE_VALUE_MISSING")
                    continue
                if isinstance(value, str) and "," in value:
                    issues.append(f"{label}:BALANCE_USES_COMMA_DECIMAL")
                    continue
                try:
                    float(value)
                except (TypeError, ValueError):
                    issues.append(f"{label}:BALANCE_NOT_NUMERIC")
    return issues


def _table_observation(
    conn: sqlite3.Connection,
    *,
    table: str,
    date_column: str,
    cutoff: datetime,
    max_age_seconds: int | None,
) -> dict[str, Any]:
    if not _table_exists(conn, table):
        return {
            "table": table,
            "date_column": date_column,
            "status": "MISSING",
            "row_count": 0,
            "max_observed_at": None,
            "issue": "TABLE_MISSING",
        }
    cols = _columns(conn, table)
    row_count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
    if row_count <= 0:
        return {
            "table": table,
            "date_column": date_column,
            "status": "EMPTY",
            "row_count": row_count,
            "max_observed_at": None,
            "issue": "TABLE_EMPTY",
        }
    if date_column not in cols:
        return {
            "table": table,
            "date_column": date_column,
            "status": "UNKNOWN",
            "row_count": row_count,
            "max_observed_at": None,
            "issue": "DATE_COLUMN_MISSING",
        }
    raw_values = [
        row[0]
        for row in conn.execute(
            f"""
            SELECT substr(CAST({date_column} AS TEXT), 1, 19)
            FROM {table}
            WHERE {date_column} IS NOT NULL
            """
        ).fetchall()
        if row[0] is not None
    ]
    parsed_values = [
        parsed
        for parsed in (_parse_observed_at(value) for value in raw_values)
        if parsed is not None
    ]
    eligible_values = [value for value in parsed_values if value <= cutoff]
    future_values = [value for value in parsed_values if value > cutoff]
    observed = max(eligible_values, default=None)
    raw_max_observed = max(parsed_values, default=None)
    if observed is None:
        observed = raw_max_observed
    status, lag_seconds = _status_from_observed(
        max_observed_at=observed,
        cutoff=cutoff,
        max_age_seconds=max_age_seconds,
    )
    issue = None if status == "FRESH" else f"TABLE_{status}"
    latest_future = max(future_values, default=None)
    return {
        "table": table,
        "date_column": date_column,
        "status": status,
        "row_count": row_count,
        "eligible_row_count": len(eligible_values),
        "future_row_count": len(future_values),
        "max_observed_at": observed.isoformat(timespec="seconds") if observed else None,
        "raw_max_observed_at": (
            raw_max_observed.isoformat(timespec="seconds") if raw_max_observed else None
        ),
        "latest_future_observed_at": (
            latest_future.isoformat(timespec="seconds") if latest_future else None
        ),
        "lag_seconds": lag_seconds,
        "issue": issue,
    }


def _observe_ab_operational_truth(
    conn: sqlite3.Connection,
    *,
    source: sqlite3.Row,
    db_path: Path,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]:
    cutoff = _as_of_cutoff(as_of)
    max_age = _max_age_seconds(source)
    table_observations = [
        _table_observation(
            conn,
            table=table,
            date_column=date_column,
            cutoff=cutoff,
            max_age_seconds=max_age,
        )
        for table, date_column in OPERATIONAL_TABLE_SOURCES
    ]
    statuses = {item["status"] for item in table_observations}
    issue_counts = Counter(item["issue"] for item in table_observations if item.get("issue"))
    max_values = [
        _parse_observed_at(item.get("max_observed_at"))
        for item in table_observations
        if item.get("max_observed_at")
    ]
    max_observed = max((item for item in max_values if item is not None), default=None)
    row_count = sum(int(item.get("row_count") or 0) for item in table_observations)
    if any(status in BLOCKING_FRESHNESS_STATUSES for status in statuses):
        status = "BLOCKED"
    elif statuses == {"FRESH"}:
        status = "FRESH"
    else:
        status = "UNKNOWN"
    _, lag_seconds = _status_from_observed(
        max_observed_at=max_observed,
        cutoff=cutoff,
        max_age_seconds=max_age,
    )
    evidence = {
        "source_path": str(db_path),
        "source_table": source["source_table"],
        "observation_type": "sqlite_operational_required_tables",
        "table_observations": table_observations,
        "issue_counts": dict(sorted(issue_counts.items())),
    }
    return {
        "status": status,
        "max_observed_at": max_observed.isoformat(timespec="seconds") if max_observed else None,
        "source_sha256": _sha256_text(_json(evidence)),
        "row_count": row_count,
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _child_status_from_table_observations(table_observations: list[dict[str, Any]]) -> str:
    statuses = {str(item["status"]).upper() for item in table_observations}
    if not statuses:
        return "UNKNOWN"
    if statuses == {"FRESH"}:
        return "FRESH"
    if statuses.issubset({"FRESH", "STALE"}) and "STALE" in statuses:
        return "STALE"
    if "FUTURE" in statuses:
        return "FUTURE"
    if "MISSING" in statuses:
        return "MISSING"
    if "EMPTY" in statuses:
        return "EMPTY"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return "BLOCKED"


def _observe_ab_operational_child_truth(
    conn: sqlite3.Connection,
    *,
    source: sqlite3.Row,
    db_path: Path,
    as_of: str,
    observed_at: str,
    table_sources: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    cutoff = _as_of_cutoff(as_of)
    max_age = _max_age_seconds(source)
    table_observations = [
        _table_observation(
            conn,
            table=table,
            date_column=date_column,
            cutoff=cutoff,
            max_age_seconds=max_age,
        )
        for table, date_column in table_sources
    ]
    issue_counts = Counter(item["issue"] for item in table_observations if item.get("issue"))
    max_values = [
        _parse_observed_at(item.get("max_observed_at"))
        for item in table_observations
        if item.get("max_observed_at")
    ]
    max_observed = max((item for item in max_values if item is not None), default=None)
    row_count = sum(int(item.get("row_count") or 0) for item in table_observations)
    status = _child_status_from_table_observations(table_observations)
    _, lag_seconds = _status_from_observed(
        max_observed_at=max_observed,
        cutoff=cutoff,
        max_age_seconds=max_age,
    )
    evidence = {
        "contract_id": "AB_OPERATIONAL_TRUTH_TABLE_SPLIT_V1",
        "parent_policy_source_id": AB_OPERATIONAL_ROLLUP_SOURCE_ID,
        "source_path": str(db_path),
        "source_table": source["source_table"],
        "observation_type": "sqlite_operational_child_required_tables",
        "table_observations": table_observations,
        "issue_counts": dict(sorted(issue_counts.items())),
        "publication_rule": "child_source_status_controls_dependent_gate",
    }
    return {
        "status": status,
        "max_observed_at": max_observed.isoformat(timespec="seconds") if max_observed else None,
        "source_sha256": _sha256_text(_json(evidence)),
        "row_count": row_count,
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _observe_sqlite_table(
    conn: sqlite3.Connection,
    *,
    source: sqlite3.Row,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]:
    table = str(source["source_table"] or "")
    date_column = TABLE_DATE_COLUMNS.get(table, "updated_at")
    observation = _table_observation(
        conn,
        table=table,
        date_column=date_column,
        cutoff=_as_of_cutoff(as_of),
        max_age_seconds=_max_age_seconds(source),
    )
    evidence = {
        "source_path": source["source_path"],
        "source_table": table,
        "observation_type": "sqlite_table",
        "table_observation": observation,
    }
    return {
        "status": observation["status"],
        "max_observed_at": observation["max_observed_at"],
        "source_sha256": _sha256_text(_json(evidence)),
        "row_count": observation["row_count"],
        "lag_seconds": observation.get("lag_seconds"),
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _observe_path_source(
    *,
    conn: sqlite3.Connection | None = None,
    source: sqlite3.Row,
    as_of: str,
    observed_at: str,
) -> dict[str, Any]:
    path = _resolve_source_path(source["source_path"])
    if source["policy_source_id"] == WEB_AUTOMATION_KASPI_MARKETING_SOURCE_ID:
        return _observe_web_automation_kaspi_marketing_packet(
            source=source,
            path=path,
            as_of=as_of,
            observed_at=observed_at,
        )
    evidence: dict[str, Any] = {
        "source_path": source["source_path"],
        "source_kind": source["source_kind"],
        "observation_type": "file_or_directory_metadata",
    }
    if path is None:
        evidence["exists"] = False
        evidence["issue"] = "SOURCE_PATH_EMPTY"
        return {
            "status": "MISSING",
            "max_observed_at": None,
            "source_sha256": "",
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }
    if not path.exists():
        evidence.update({"resolved_path": str(path), "exists": False, "issue": "PATH_MISSING"})
        return {
            "status": "MISSING",
            "max_observed_at": None,
            "source_sha256": "",
            "row_count": 0,
            "lag_seconds": None,
            "evidence": evidence,
            "observed_at": observed_at,
        }

    if source["policy_source_id"] == META_FACEBOOK_SOURCE_ID and path.is_dir():
        return _observe_meta_source_freshness_packet(
            conn=conn,
            source=source,
            path=path,
            as_of=as_of,
            observed_at=observed_at,
        )

    if path.is_dir():
        try:
            return _observe_directory_source(
                source=source,
                path=path,
                as_of=as_of,
                observed_at=observed_at,
                base_evidence=evidence,
            )
        except OSError as exc:
            evidence.update(
                {
                    "resolved_path": str(path),
                    "exists": True,
                    "is_file": False,
                    "is_dir": True,
                    "issue": f"DIRECTORY_UNREADABLE:{exc}",
                }
            )
            return {
                "status": "BLOCKED",
                "max_observed_at": None,
                "source_sha256": "",
                "row_count": 0,
                "lag_seconds": None,
                "evidence": evidence,
                "observed_at": observed_at,
            }

    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=ALMATY)
    max_age = _max_age_seconds(source)
    status, lag_seconds = _status_from_observed(
        max_observed_at=mtime,
        cutoff=_as_of_cutoff(as_of),
        max_age_seconds=max_age,
    )
    source_sha256 = _sha256_file(path) if path.is_file() else _directory_fingerprint(path)
    row_count = 1
    evidence.update(
        {
            "resolved_path": str(path),
            "exists": True,
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "mtime": mtime.isoformat(timespec="seconds"),
            "max_age_value": source["max_age_value"],
            "max_age_unit": source["max_age_unit"],
        }
    )
    if source["policy_source_id"] == "src_bank_manual_ingest" and path.is_file():
        bank_issues = _bank_manual_ingest_issues(path)
        evidence["bank_manual_ingest_issues"] = bank_issues
        if bank_issues:
            status = "BLOCKED"
    return {
        "status": status,
        "max_observed_at": mtime.isoformat(timespec="seconds"),
        "source_sha256": source_sha256,
        "row_count": row_count,
        "lag_seconds": lag_seconds,
        "evidence": evidence,
        "observed_at": observed_at,
    }


def _active_source_rows(
    conn: sqlite3.Connection,
    *,
    source_ids: set[str] | None = None,
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM policy_source_registry
        WHERE active_to IS NULL
          AND required_for_gate IS NOT NULL
        ORDER BY policy_source_id
        """
    ).fetchall()
    if source_ids is None:
        return rows
    available = {str(row["policy_source_id"]) for row in rows}
    missing = sorted(source_ids - available)
    if missing:
        raise RuntimeError(f"Unknown or inactive C3 policy source ids: {', '.join(missing)}")
    return [row for row in rows if str(row["policy_source_id"]) in source_ids]


def _build_source_freshness_rows(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    as_of: str,
    run_id: str,
    observed_at: str,
    source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    active = _active_policy(conn)
    rows: list[dict[str, Any]] = []
    for source in _active_source_rows(conn, source_ids=source_ids):
        source_id = str(source["policy_source_id"])
        if source_id == AB_OPERATIONAL_ROLLUP_SOURCE_ID:
            observation = _observe_ab_operational_truth(
                conn,
                source=source,
                db_path=db_path,
                as_of=as_of,
                observed_at=observed_at,
            )
        elif source_id in AB_OPERATIONAL_CHILD_SOURCE_TABLES:
            observation = _observe_ab_operational_child_truth(
                conn,
                source=source,
                db_path=db_path,
                as_of=as_of,
                observed_at=observed_at,
                table_sources=AB_OPERATIONAL_CHILD_SOURCE_TABLES[source_id],
            )
        elif source["source_kind"] == "sqlite_table":
            observation = _observe_sqlite_table(
                conn,
                source=source,
                as_of=as_of,
                observed_at=observed_at,
            )
        else:
            observation = _observe_path_source(
                conn=conn,
                source=source,
                as_of=as_of,
                observed_at=observed_at,
            )
        blocks_publication = (
            int(source["required_for_publication"] or 0) == 1
            and str(observation["status"]).upper() in BLOCKING_FRESHNESS_STATUSES
        )
        freshness_result_id = "fresh:" + _sha256_text(
            f"{active['policy_version_id']}:{source['policy_source_id']}:{as_of}:{run_id}"
        )[:32]
        rows.append(
            {
                "freshness_result_id": freshness_result_id,
                "run_id": run_id,
                "policy_version_id": active["policy_version_id"],
                "policy_source_id": source["policy_source_id"],
                "as_of_date": as_of,
                "observed_at": observation["observed_at"],
                "max_observed_at": observation["max_observed_at"],
                "source_sha256": observation["source_sha256"],
                "row_count": observation["row_count"],
                "freshness_status": observation["status"],
                "max_age_value": source["max_age_value"],
                "max_age_unit": source["max_age_unit"],
                "lag_seconds": observation["lag_seconds"],
                "blocks_publication": 1 if blocks_publication else 0,
                "evidence_json": _json(
                    {
                        **observation["evidence"],
                        "policy_source_id": source["policy_source_id"],
                        "domain": source["domain"],
                        "required_for_gate": source["required_for_gate"],
                        "required_for_publication": int(source["required_for_publication"] or 0),
                        "status": observation["status"],
                        "blocks_publication": bool(blocks_publication),
                    }
                ),
            }
        )
    return rows


def _insert_source_freshness_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO source_freshness_result (
                freshness_result_id, run_id, policy_version_id, policy_source_id,
                as_of_date, observed_at, max_observed_at, source_sha256,
                row_count, freshness_status, max_age_value, max_age_unit,
                lag_seconds, blocks_publication, evidence_json
            ) VALUES (
                :freshness_result_id, :run_id, :policy_version_id,
                :policy_source_id, :as_of_date, :observed_at,
                :max_observed_at, :source_sha256, :row_count,
                :freshness_status, :max_age_value, :max_age_unit,
                :lag_seconds, :blocks_publication, :evidence_json
            )
            """,
            row,
        )


def _latest_source_rows(conn: sqlite3.Connection, policy_version_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT psr.policy_source_id, psr.domain, psr.required_for_gate,
               psr.required_for_publication, psr.policy_path,
               current.freshness_result_id, current.freshness_status,
               current.blocks_publication, current.evidence_json
        FROM policy_source_registry psr
        LEFT JOIN v_source_freshness_current current
          ON current.policy_source_id = psr.policy_source_id
         AND current.policy_version_id = ?
        WHERE psr.active_to IS NULL
          AND psr.required_for_gate IS NOT NULL
        ORDER BY psr.policy_source_id
        """,
        (policy_version_id,),
    ).fetchall()


def _source_issues_for_gate(
    conn: sqlite3.Connection,
    *,
    policy_version_id: str,
    gate_name: str,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    source_ids: list[str] = []
    result_ids: list[str] = []
    policy_paths: list[str] = []
    issues: list[dict[str, Any]] = []
    for row in _latest_source_rows(conn, policy_version_id):
        if row["required_for_gate"] != gate_name:
            continue
        source_ids.append(row["policy_source_id"])
        if row["policy_path"]:
            policy_paths.append(row["policy_path"])
        if row["freshness_result_id"]:
            result_ids.append(row["freshness_result_id"])
        status = str(row["freshness_status"] or "MISSING").upper()
        blocks = int(row["blocks_publication"] or 0) == 1
        if row["freshness_status"] is None or status in BLOCKING_FRESHNESS_STATUSES or blocks:
            issues.append(
                {
                    "policy_source_id": row["policy_source_id"],
                    "status": status,
                    "blocks_publication": blocks,
                    "required_for_publication": int(row["required_for_publication"] or 0),
                }
            )
    return source_ids, result_ids, policy_paths, issues


def _operational_table_issue_counts(conn: sqlite3.Connection, *, as_of: str) -> Counter[str]:
    cutoff = _as_of_cutoff(as_of)
    counts: Counter[str] = Counter()
    for table, date_column in OPERATIONAL_TABLE_SOURCES:
        observation = _table_observation(
            conn,
            table=table,
            date_column=date_column,
            cutoff=cutoff,
            max_age_seconds=24 * 60 * 60,
        )
        if observation.get("issue"):
            reason = str(observation["issue"])
            if table.startswith("ads_"):
                counts["ADS_TABLE_EMPTY" if reason == "TABLE_EMPTY" else f"ADS_{reason}"] += 1
            elif table.startswith("fact_cashflow"):
                counts[f"CASHFLOW_{reason}"] += 1
            elif table in {"order_status_event", "fact_order_entries_kaspi"}:
                counts[f"ORDER_{reason}"] += 1
            else:
                counts[f"STOCK_{reason}"] += 1
    return counts


def _integration_finding_counts(db_path: Path, *, as_of: str) -> Counter[str]:
    try:
        report = evaluate_operational_stock_integration_gates(db_path, as_of=as_of)
    except Exception as exc:
        return Counter({f"INTEGRATION_GATE_EXCEPTION:{exc}": 1})
    return Counter(
        finding.code
        for finding in report.findings
        if str(finding.severity or "").upper() == "ERROR"
    )


def _gate_row(
    *,
    policy_version_id: str,
    run_id: str,
    gate_name: str,
    domain: str,
    status: str,
    severity: str,
    blocks_owner_publication: bool,
    message: str,
    policy_paths: list[str] | None = None,
    source_ids: list[str] | None = None,
    freshness_result_ids: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_result_id = "gate:" + _sha256_text(
        f"{policy_version_id}:{gate_name}:{run_id}"
    )[:32]
    return {
        "gate_result_id": gate_result_id,
        "run_id": run_id,
        "policy_version_id": policy_version_id,
        "gate_name": gate_name,
        "domain": domain,
        "status": status,
        "severity": severity,
        "blocks_owner_publication": 1 if blocks_owner_publication else 0,
        "policy_paths_json": _json(sorted(set(policy_paths or []))),
        "source_ids_json": _json(sorted(set(source_ids or []))),
        "freshness_result_ids_json": _json(sorted(set(freshness_result_ids or []))),
        "message": message,
        "evidence_json": _json(evidence or {}),
    }


def _open_high_exception_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT exception_id, domain, severity, reason, owner, recommended_action,
               evidence_json, evidence_paths_json, policy_version_id,
               policy_path, policy_source_id, gate_result_id
        FROM exception_queue
        WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'PENDING', 'BLOCKED')
          AND LOWER(COALESCE(severity, '')) IN ('critical', 'high')
        ORDER BY exception_id
        """
    ).fetchall()


def _exception_evidence(row: sqlite3.Row) -> dict[str, Any]:
    try:
        parsed = json.loads(str(row["evidence_json"] or "{}"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _accepted_active_control_type(row: sqlite3.Row) -> str | None:
    reason_upper = str(row["reason"] or "").upper()
    exception_upper = str(row["exception_id"] or "").upper()
    evidence_upper = _json(_exception_evidence(row)).upper()
    combined = f"{reason_upper} {exception_upper} {evidence_upper}"
    if "OWNER_OOS_ACTIVE_ZERO" in combined:
        return "OWNER_OOS_ACTIVE_ZERO"
    if "OWNER_OVERRIDE_NO_DOUBLE_REDUCE" in combined:
        return "OWNER_OVERRIDE_NO_DOUBLE_REDUCE"
    if "LINE61_4XL_EXCLUDED" in combined:
        return "LINE61_4XL_EXCLUDED"
    if "NEGATIVE_RAW_LEDGER_BALANCE" in combined and (
        "BERSERK-RUSH" in combined or "BERSERK_RUSH" in combined
    ):
        return "OWNER_BERSERK_RUSH_NEGATIVE_RAW_QUARANTINE_ACTIVE_ZERO"
    if "NEGATIVE_LEDGER_EXACT_OWNER_ACTIVE_ZERO_QUARANTINE" in combined:
        return "OWNER_NEGATIVE_LEDGER_ACTIVE_ZERO_QUARANTINE"
    return None


def _exception_gate_payload(row: sqlite3.Row, *, control_type: str | None = None) -> dict[str, Any]:
    payload = {
        "exception_id": row["exception_id"],
        "domain": row["domain"],
        "severity": row["severity"],
        "reason": row["reason"],
        "owner": row["owner"],
        "recommended_action": row["recommended_action"],
        "policy_version_id": row["policy_version_id"],
        "policy_path": row["policy_path"],
        "policy_source_id": row["policy_source_id"],
        "gate_result_id": row["gate_result_id"],
        "evidence": _exception_evidence(row),
    }
    if control_type:
        payload["control_type"] = control_type
        payload["blocks_owner_publication"] = False
    else:
        payload["blocks_owner_publication"] = True
    return payload


def _build_policy_gate_rows(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    policy_path: Path,
    as_of: str,
    run_id: str,
) -> list[dict[str, Any]]:
    active = _active_policy(conn)
    policy_version_id = active["policy_version_id"]
    rows: list[dict[str, Any]] = []

    policy_errors = validate_policy_registry_schema(db_path) + validate_operational_decision_policy_registry(
        db_path,
        policy_path,
    )
    rows.append(
        _gate_row(
            policy_version_id=policy_version_id,
            run_id=run_id,
            gate_name="policy_registry",
            domain="policy",
            status="PASS" if not policy_errors else "FAIL",
            severity="INFO" if not policy_errors else "ERROR",
            blocks_owner_publication=bool(policy_errors),
            message="C3 policy registry matches YAML contract." if not policy_errors else "C3 policy registry is missing or drifted.",
            evidence={"errors": policy_errors},
        )
    )

    source_errors = validate_policy_source_freshness(db_path, as_of=as_of)
    source_ids, result_ids, policy_paths, source_issues = _source_issues_for_gate(
        conn,
        policy_version_id=policy_version_id,
        gate_name="source_freshness",
    )
    all_source_issue_rows = [
        {
            "policy_source_id": row["policy_source_id"],
            "required_for_gate": row["required_for_gate"],
            "freshness_status": str(row["freshness_status"] or "MISSING").upper(),
            "blocks_publication": int(row["blocks_publication"] or 0),
        }
        for row in _latest_source_rows(conn, policy_version_id)
        if row["freshness_status"] is None
        or str(row["freshness_status"]).upper() in BLOCKING_FRESHNESS_STATUSES
        or int(row["blocks_publication"] or 0) == 1
    ]
    rows.append(
        _gate_row(
            policy_version_id=policy_version_id,
            run_id=run_id,
            gate_name="source_freshness",
            domain="source_freshness",
            status="PASS" if not source_errors else "BLOCKED",
            severity="INFO" if not source_errors else "ERROR",
            blocks_owner_publication=bool(source_errors),
            message="Required C3 sources are fresh." if not source_errors else "Required C3 sources are missing, stale, blocked, or unknown.",
            policy_paths=policy_paths,
            source_ids=source_ids,
            freshness_result_ids=result_ids,
            evidence={"errors": source_errors, "source_blockers": all_source_issue_rows},
        )
    )

    exception_metadata_errors = validate_exception_queue_db(db_path, strict=True)
    open_high = _open_high_exception_rows(conn)
    accepted_controls: list[dict[str, Any]] = []
    unresolved_exceptions: list[dict[str, Any]] = []
    for exception_row in open_high:
        control_type = _accepted_active_control_type(exception_row)
        if control_type:
            accepted_controls.append(
                _exception_gate_payload(exception_row, control_type=control_type)
            )
        else:
            unresolved_exceptions.append(_exception_gate_payload(exception_row))
    exception_blocks = bool(exception_metadata_errors or unresolved_exceptions)
    if exception_blocks:
        exception_message = "Unresolved high-severity exceptions remain owner-review blockers."
    elif accepted_controls:
        exception_message = "Open high-severity exceptions are accepted active controls and remain visible without blocking global publication."
    else:
        exception_message = "No open high-severity C3 exceptions block publication."
    rows.append(
        _gate_row(
            policy_version_id=policy_version_id,
            run_id=run_id,
            gate_name="exception_queue",
            domain="exception_queue",
            status="PASS" if not exception_blocks else "BLOCKED",
            severity="INFO" if not exception_blocks else "ERROR",
            blocks_owner_publication=exception_blocks,
            message=exception_message,
            policy_paths=["manual_review_ownership.daily_exception_queue.owner"],
            source_ids=["src_ab_db_operational_truth"],
            evidence={
                "metadata_errors": exception_metadata_errors,
                "open_high_exception_count": len(open_high),
                "accepted_active_control_count": len(accepted_controls),
                "unresolved_blocker_count": len(unresolved_exceptions),
                "accepted_active_control_rows": accepted_controls[:50],
                "unresolved_exception_rows": unresolved_exceptions[:50],
            },
        )
    )

    manual_errors = validate_manual_decision_approvals(db_path)
    rows.append(
        _gate_row(
            policy_version_id=policy_version_id,
            run_id=run_id,
            gate_name="manual_approvals",
            domain="manual_approval",
            status="PASS" if not manual_errors else "FAIL",
            severity="INFO" if not manual_errors else "ERROR",
            blocks_owner_publication=bool(manual_errors),
            message="Manual approvals do not override publication gates." if not manual_errors else "Manual approval rows are invalid or attempt a publication waiver.",
            evidence={"errors": manual_errors},
        )
    )

    operational_counts = _operational_table_issue_counts(conn, as_of=as_of)
    integration_counts = _integration_finding_counts(db_path, as_of=as_of)
    domain_specs = {
        "stock_source_truth": {
            "domain": "stock",
            "policy_paths": ["stock_authority", "stock_status_rules"],
            "issue_prefixes": ("STOCK_", "ORDER_", "ORDER_LIFECYCLE", "ORDER_ENTRY", "SKU_", "RETURN_", "QC_"),
        },
        "ads_source_truth": {
            "domain": "ads",
            "policy_paths": ["ads_truth", "decision_thresholds.freshness.kaspi_internal_ads_required_stores"],
            "issue_prefixes": ("ADS_",),
        },
        "cashflow_source_truth": {
            "domain": "cashflow",
            "policy_paths": ["cashflow_truth", "purchase_order_truth.open_supplier_obligations_block_cashflow_green"],
            "issue_prefixes": ("CASHFLOW_",),
        },
        "po_source_truth": {
            "domain": "po",
            "policy_paths": ["purchase_order_truth", "decision_thresholds.freshness.inbound_workbook_or_replacement"],
            "issue_prefixes": ("PO_",),
        },
    }
    for gate_name, spec in domain_specs.items():
        source_ids, result_ids, policy_paths, source_issues = _source_issues_for_gate(
            conn,
            policy_version_id=policy_version_id,
            gate_name=gate_name,
        )
        issue_prefixes = spec["issue_prefixes"]
        relevant_operational = {
            code: count
            for code, count in operational_counts.items()
            if code.startswith(issue_prefixes)
        }
        relevant_integration = {
            code: count
            for code, count in integration_counts.items()
            if code.startswith(issue_prefixes)
        }
        if gate_name == "cashflow_source_truth":
            # Bank snapshot source rows can be fresh by mtime but still blocked by parse/normalization issues.
            relevant_source_issues = source_issues
        else:
            relevant_source_issues = source_issues
        blocked = bool(relevant_source_issues or relevant_operational or relevant_integration)
        rows.append(
            _gate_row(
                policy_version_id=policy_version_id,
                run_id=run_id,
                gate_name=gate_name,
                domain=str(spec["domain"]),
                status="PASS" if not blocked else "BLOCKED",
                severity="INFO" if not blocked else "ERROR",
                blocks_owner_publication=blocked,
                message=f"{gate_name} has fresh evidence." if not blocked else f"{gate_name} has missing, stale, or unresolved evidence.",
                policy_paths=policy_paths + list(spec["policy_paths"]),
                source_ids=source_ids,
                freshness_result_ids=result_ids,
                evidence={
                    "source_blockers": relevant_source_issues,
                    "issue_counts": dict(sorted(relevant_operational.items())),
                    "integration_finding_counts": dict(sorted(relevant_integration.items())),
                },
            )
        )

    wiki_source_ids, wiki_result_ids, wiki_policy_paths, wiki_issues = _source_issues_for_gate(
        conn,
        policy_version_id=policy_version_id,
        gate_name="wiki_context_routing",
    )
    wiki_publication_issues = [
        item for item in wiki_issues if item.get("required_for_publication") == 1
    ]
    rows.append(
        _gate_row(
            policy_version_id=policy_version_id,
            run_id=run_id,
            gate_name="wiki_context_routing",
            domain="wiki_context",
            status="PASS" if not wiki_publication_issues else "WARN",
            severity="INFO" if not wiki_publication_issues else "WARN",
            blocks_owner_publication=False,
            message="Wiki context is represented as routing memory, not operational truth.",
            policy_paths=wiki_policy_paths,
            source_ids=wiki_source_ids,
            freshness_result_ids=wiki_result_ids,
            evidence={
                "source_blockers": wiki_issues,
                "routing_memory_only": True,
                "raw_copy_allowed": False,
            },
        )
    )

    return sorted(rows, key=lambda row: row["gate_name"])


def _insert_gate_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO policy_gate_result (
                gate_result_id, run_id, policy_version_id, gate_name, domain,
                status, severity, blocks_owner_publication, policy_paths_json,
                source_ids_json, freshness_result_ids_json, message, evidence_json
            ) VALUES (
                :gate_result_id, :run_id, :policy_version_id, :gate_name,
                :domain, :status, :severity, :blocks_owner_publication,
                :policy_paths_json, :source_ids_json,
                :freshness_result_ids_json, :message, :evidence_json
            )
            """,
            row,
        )


def _policy_value(conn: sqlite3.Connection, policy_version_id: str, policy_path: str) -> Any:
    row = conn.execute(
        """
        SELECT value_json
        FROM policy_value
        WHERE policy_version_id=? AND policy_path=?
        """,
        (policy_version_id, policy_path),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["value_json"])
    except Exception:
        return row["value_json"]


def _action_and_policy_path(reason: str, *, control_type: str | None = None) -> tuple[str, str]:
    if control_type == "OWNER_OOS_ACTIVE_ZERO":
        return (
            "Accepted active control: keep active sellable stock at zero/quarantine until warehouse or owner evidence explicitly supersedes the hold.",
            "manual_review_ownership.sku_merge_or_override.owner",
        )
    if control_type == "OWNER_OVERRIDE_NO_DOUBLE_REDUCE":
        return (
            "Accepted active control: preserve the owner-approved no-double-reduce override unless a later owner-approved anchor supersedes it.",
            "stock_authority.line51_required_baseline_adjustment",
        )
    if control_type == "LINE61_4XL_EXCLUDED":
        return (
            "Accepted active control: keep Line61 4XL excluded and active sellable zero until owner-approved evidence explicitly reopens it.",
            "stock_authority.best_current_anchor_path",
        )
    if control_type == "OWNER_BERSERK_RUSH_NEGATIVE_RAW_QUARANTINE_ACTIVE_ZERO":
        return (
            "Accepted active control: keep Berserk Rush returned/cancelled stock quarantined and active sellable zero until employee QC acceptance.",
            "stock_authority.quarantined_returns_and_cancels_are_active_stock",
        )
    if control_type == "OWNER_NEGATIVE_LEDGER_ACTIVE_ZERO_QUARANTINE":
        return (
            "Accepted active control: keep exact owner-approved negative ledger SKU quarantined and active sellable zero until QC or owner evidence supersedes it.",
            "stock_authority.quarantined_returns_and_cancels_are_active_stock",
        )
    reason_upper = reason.upper()
    if "NEGATIVE_RAW_LEDGER_BALANCE" in reason_upper:
        return (
            "Owner/ops review negative raw ledger balance, verify physical stock and QC evidence, keep clamped zero provisional until resolved, then rerun C3 gates.",
            "stock_authority.negative_active_stock_action",
        )
    if "OWNER_OOS_ACTIVE_ZERO" in reason_upper:
        return (
            "Business owner or warehouse reverify owner out-of-stock hold before returning this SKU-size to active sellable stock.",
            "manual_review_ownership.sku_merge_or_override.owner",
        )
    if "OWNER_OVERRIDE_NO_DOUBLE_REDUCE" in reason_upper:
        return (
            "Confirm the active owner override and update policy or anchor lineage before applying any baseline decrease; do not double-reduce.",
            "stock_authority.line51_required_baseline_adjustment",
        )
    if "LINE61_4XL_EXCLUDED" in reason_upper:
        return (
            "Keep Line61 4XL excluded until owner-approved superseding stock evidence explicitly reopens it.",
            "stock_authority.best_current_anchor_path",
        )
    return (
        "Business owner review the open stock exception with source evidence and rerun C3 gates after resolution.",
        "manual_review_ownership.daily_exception_queue.owner",
    )


def _default_exception_evidence_paths() -> list[str]:
    return [
        str(AGENT8_HANDOFF_ROOT / "agent_2_c3_stock_orders_returns_qc_closeout.md"),
        str(AGENT8_HANDOFF_ROOT / "agent_7_c3_policy_db_exception_queue_closeout.md"),
        str(AGENT6_STOCK_REBUILD_ROOT / "BASELINE_20PCT_DECREASE_20260404_B6864B5C3108_lineage.json"),
        str(AGENT6_STOCK_REBUILD_ROOT / "BASELINE_20PCT_DECREASE_20260404_B6864B5C3108_owner_report.md"),
    ]


def _latest_gate_result_id(conn: sqlite3.Connection, policy_version_id: str, gate_name: str) -> str | None:
    row = conn.execute(
        """
        SELECT gate_result_id
        FROM v_policy_gate_latest
        WHERE policy_version_id=? AND gate_name=?
        """,
        (policy_version_id, gate_name),
    ).fetchone()
    return str(row["gate_result_id"]) if row else None


def _build_exception_updates(conn: sqlite3.Connection, *, as_of: str) -> list[dict[str, Any]]:
    active = _active_policy(conn)
    policy_version_id = active["policy_version_id"]
    owner = _policy_value(
        conn,
        policy_version_id,
        "manual_review_ownership.daily_exception_queue.owner",
    ) or "business_owner"
    evidence_paths = _default_exception_evidence_paths()
    gate_result_id = _latest_gate_result_id(conn, policy_version_id, "stock_source_truth")
    updates: list[dict[str, Any]] = []
    for row in _open_high_exception_rows(conn):
        if not str(row["exception_id"]).startswith("AGENT6_STOCK_REBUILD_20PCT_20260503:"):
            continue
        control_type = _accepted_active_control_type(row)
        action, policy_path = _action_and_policy_path(
            str(row["reason"] or ""),
            control_type=control_type,
        )
        next_values = {
            "exception_id": row["exception_id"],
            "owner": owner,
            "recommended_action": action,
            "evidence_paths_json": _json(evidence_paths),
            "policy_version_id": policy_version_id,
            "policy_path": policy_path,
            "policy_source_id": "src_ab_db_operational_truth",
            "gate_result_id": gate_result_id,
            "due_at": f"{as_of}T23:59:59+05:00",
            "updated_at": _now_iso(),
        }
        changed = False
        for field in (
            "owner",
            "recommended_action",
            "evidence_paths_json",
            "policy_version_id",
            "policy_path",
            "policy_source_id",
            "gate_result_id",
        ):
            if field == "gate_result_id" and next_values[field] is None:
                continue
            if str(row[field] or "") != str(next_values[field] or ""):
                changed = True
                break
        if not str(row["evidence_paths_json"] or "").strip() or row["evidence_paths_json"] == "[]":
            changed = True
        if changed:
            updates.append(next_values)
    return updates


def _apply_exception_updates(conn: sqlite3.Connection, updates: list[dict[str, Any]]) -> None:
    for update in updates:
        conn.execute(
            """
            UPDATE exception_queue
            SET owner=:owner,
                recommended_action=:recommended_action,
                evidence_paths_json=:evidence_paths_json,
                policy_version_id=:policy_version_id,
                policy_path=:policy_path,
                policy_source_id=:policy_source_id,
                gate_result_id=COALESCE(:gate_result_id, gate_result_id),
                due_at=:due_at,
                updated_at=:updated_at
            WHERE exception_id=:exception_id
            """,
            update,
        )


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)


def _ensure_apply_allowed(db_path: Path) -> None:
    if os.environ.get(C3_MATERIALIZATION_ENV_GATE) != "1":
        raise RuntimeError(f"{C3_MATERIALIZATION_ENV_GATE}=1 is required for Agent 8 C3 DB materialization")
    if not db_path.exists():
        raise RuntimeError(f"DB does not exist: {db_path}")


def _ensure_copied_temp_bridge_db_target(db_path: Path) -> None:
    try:
        if db_path.expanduser().resolve() == DEFAULT_DB_PATH.expanduser().resolve():
            raise RuntimeError(
                "Copied-temp source-freshness bridge refuses to apply to production db/app.db"
            )
    except FileNotFoundError:
        pass


def _load_copied_temp_bridge_rows(bridge_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Copied-temp bridge JSON parse failed: {bridge_path}: {exc}") from exc
    rows = payload.get("bridge_rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("Copied-temp bridge input must be a list or object with bridge_rows")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise RuntimeError(f"Copied-temp bridge row {index} is not an object")
        normalized.append(row)
    return normalized


def _resolve_bridge_packet_path(path_value: Any, *, bridge_path: Path) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        return Path("")
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    bridge_relative = (bridge_path.parent / path).expanduser()
    if bridge_relative.exists():
        return bridge_relative
    return (PROJECT_ROOT / path).expanduser()


def _active_source_rows_by_id(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM policy_source_registry
        WHERE active_to IS NULL
        ORDER BY policy_source_id
        """
    ).fetchall()
    return {str(row["policy_source_id"]): row for row in rows}


def _bridge_bool(value: Any, *, field: str, index: int) -> bool:
    if isinstance(value, bool):
        return value
    raise RuntimeError(f"Copied-temp bridge row {index} field {field} must be a JSON boolean")


def _build_copied_temp_bridge_rows(
    conn: sqlite3.Connection,
    *,
    bridge_path: Path,
    as_of: str,
    run_id: str,
    observed_at: str,
) -> list[dict[str, Any]]:
    active_policy = _active_policy(conn)
    active_sources = _active_source_rows_by_id(conn)
    input_rows = _load_copied_temp_bridge_rows(bridge_path)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, input_row in enumerate(input_rows):
        missing = sorted(COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_REQUIRED_FIELDS - set(input_row))
        if missing:
            errors.append(f"row {index}: missing required fields: {', '.join(missing)}")
            continue

        source_id = str(input_row["source_id"]).strip()
        source = active_sources.get(source_id)
        if source is None:
            errors.append(f"row {index}: unknown or inactive policy source id: {source_id}")
            continue
        if str(input_row["as_of"]) != as_of:
            errors.append(f"row {index}: as_of {input_row['as_of']} does not match requested {as_of}")
            continue
        if str(input_row["proof_scope"]) != "copied_temp":
            errors.append(f"row {index}: proof_scope must be copied_temp")
            continue
        try:
            production_authority = _bridge_bool(
                input_row["production_authority"],
                field="production_authority",
                index=index,
            )
            blocks_publication = _bridge_bool(
                input_row["blocks_publication"],
                field="blocks_publication",
                index=index,
            )
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        if production_authority is not False:
            errors.append(f"row {index}: production_authority must be false")
            continue

        status = str(input_row["status"]).strip().upper()
        if not status:
            errors.append(f"row {index}: status is empty")
            continue
        if status not in {"FRESH", *BLOCKING_FRESHNESS_STATUSES}:
            errors.append(f"row {index}: unsupported freshness status: {status}")
            continue
        captured_at = _parse_observed_at(input_row["captured_at"])
        if captured_at is None:
            errors.append(f"row {index}: captured_at is invalid: {input_row['captured_at']}")
            continue

        packet_path = _resolve_bridge_packet_path(input_row["source_packet_path"], bridge_path=bridge_path)
        if not packet_path.exists() or not packet_path.is_file():
            errors.append(f"row {index}: source_packet_path is not a file: {packet_path}")
            continue
        packet_sha = _sha256_file(packet_path)
        expected_sha = str(input_row["source_packet_sha"]).strip()
        if packet_sha != expected_sha:
            errors.append(f"row {index}: source_packet_sha mismatch for {packet_path}")
            continue

        _, lag_seconds = _status_from_observed(
            max_observed_at=captured_at,
            cutoff=_as_of_cutoff(as_of),
            max_age_seconds=_max_age_seconds(source),
        )
        row_count = int(input_row.get("row_count", 1) or 0)
        freshness_result_id = "fresh_bridge:" + _sha256_text(
            f"{active_policy['policy_version_id']}:{source_id}:{as_of}:{run_id}:{packet_sha}"
        )[:32]
        evidence = {
            "bridge_contract": COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_CONTRACT,
            "source_packet_path": str(packet_path),
            "source_packet_sha": packet_sha,
            "captured_at": str(input_row["captured_at"]),
            "as_of": as_of,
            "status": status,
            "blocks_publication": blocks_publication,
            "proof_scope": "copied_temp",
            "production_authority": False,
            "owner_publication_authority": False,
            "does_not_update_production_db": True,
            "policy_source_id": source_id,
            "domain": source["domain"],
            "required_for_gate": source["required_for_gate"],
            "required_for_publication": int(source["required_for_publication"] or 0),
        }
        for optional_field in ("contract_id", "contract_registry_path", "notes"):
            if optional_field in input_row:
                evidence[optional_field] = input_row[optional_field]
        rows.append(
            {
                "freshness_result_id": freshness_result_id,
                "run_id": run_id,
                "policy_version_id": active_policy["policy_version_id"],
                "policy_source_id": source_id,
                "as_of_date": as_of,
                "observed_at": observed_at,
                "max_observed_at": captured_at.isoformat(timespec="seconds"),
                "source_sha256": packet_sha,
                "row_count": row_count,
                "freshness_status": status,
                "max_age_value": source["max_age_value"],
                "max_age_unit": source["max_age_unit"],
                "lag_seconds": lag_seconds,
                "blocks_publication": 1 if blocks_publication else 0,
                "evidence_json": _json(evidence),
            }
        )
    if errors:
        raise RuntimeError("Copied-temp source-freshness bridge validation failed: " + "; ".join(errors))
    return rows


def materialize_copied_temp_source_freshness_bridge(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    bridge_path: Path,
    as_of: str,
    run_id: str,
    apply: bool = False,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    bridge_path = bridge_path.expanduser().resolve()
    if apply:
        _ensure_copied_temp_bridge_db_target(db_path)
        _ensure_apply_allowed(db_path)
    if not bridge_path.exists():
        raise RuntimeError(f"Copied-temp bridge input does not exist: {bridge_path}")

    observed_at = _now_iso()
    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        validate_errors = validate_policy_registry_schema(db_path)
        if validate_errors:
            raise RuntimeError("C3 policy registry schema is not valid: " + "; ".join(validate_errors))
        bridge_rows = _build_copied_temp_bridge_rows(
            conn,
            bridge_path=bridge_path,
            as_of=as_of,
            run_id=run_id,
            observed_at=observed_at,
        )

    backup_path: Path | None = None
    if apply:
        backup_path = backup_database(
            db_path,
            backup_dir or (PROJECT_ROOT / "runtime" / "backups"),
            label="copied_temp_source_freshness_bridge",
        )
        with sqlite3.connect(str(db_path)) as conn:
            _insert_source_freshness_rows(conn, bridge_rows)
            conn.commit()
            source_freshness_count = _count_table(conn, "source_freshness_result")
    else:
        source_freshness_count = None

    return {
        "applied": apply,
        "db_path": str(db_path),
        "bridge_path": str(bridge_path),
        "as_of": as_of,
        "run_id": run_id,
        "backup_path": str(backup_path) if backup_path else None,
        "bridge_contract": COPIED_TEMP_SOURCE_FRESHNESS_BRIDGE_CONTRACT,
        "proof_scope": "copied_temp",
        "production_authority": False,
        "row_count": len(bridge_rows),
        "source_ids": [row["policy_source_id"] for row in bridge_rows],
        "status_counts": dict(Counter(row["freshness_status"] for row in bridge_rows)),
        "blocks_publication_counts": dict(
            Counter(str(bool(row["blocks_publication"])) for row in bridge_rows)
        ),
        "inserted_or_replaced": len(bridge_rows) if apply else 0,
        "source_freshness_result_count_after": source_freshness_count,
    }


def _materialize(
    *,
    db_path: Path,
    policy_path: Path,
    as_of: str,
    run_id: str,
    apply: bool,
    backup_dir: Path | None,
    sections: set[str],
    source_ids: set[str] | None = None,
) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    policy_path = policy_path.expanduser().resolve()
    observed_at = _now_iso()
    backup_path: Path | None = None
    if apply:
        _ensure_apply_allowed(db_path)
        backup_path = backup_database(
            db_path,
            backup_dir or (PROJECT_ROOT / "runtime" / "backups"),
            label="agent8_c3_policy_materialization",
        )

    report: dict[str, Any] = {
        "applied": apply,
        "db_path": str(db_path),
        "policy_path": str(policy_path),
        "as_of": as_of,
        "run_id": run_id,
        "backup_path": str(backup_path) if backup_path else None,
        "sections": sorted(sections),
        "source_filter": sorted(source_ids) if source_ids else None,
    }
    with (sqlite3.connect(str(db_path)) if apply else connect_readonly(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        validate_errors = validate_policy_registry_schema(db_path)
        if validate_errors:
            raise RuntimeError("C3 policy registry schema is not valid: " + "; ".join(validate_errors))

        source_rows: list[dict[str, Any]] = []
        if "source_freshness" in sections:
            source_rows = _build_source_freshness_rows(
                conn,
                db_path=db_path,
                as_of=as_of,
                run_id=run_id,
                observed_at=observed_at,
                source_ids=source_ids,
            )
            report["active_source_count"] = len(source_rows)
            report["row_count"] = len(source_rows)
            report["source_ids"] = [row["policy_source_id"] for row in source_rows]
            report["source_status_counts"] = dict(Counter(row["freshness_status"] for row in source_rows))
            if apply:
                _insert_source_freshness_rows(conn, source_rows)
                conn.commit()

        exception_updates: list[dict[str, Any]] = []
        if "exceptions" in sections:
            exception_updates = _build_exception_updates(conn, as_of=as_of)
            report["updated_exception_count"] = len(exception_updates)
            if apply:
                _apply_exception_updates(conn, exception_updates)
                conn.commit()

        gate_rows: list[dict[str, Any]] = []
        if "gates" in sections:
            gate_rows = _build_policy_gate_rows(
                conn,
                db_path=db_path,
                policy_path=policy_path,
                as_of=as_of,
                run_id=run_id,
            )
            report["gate_names"] = [row["gate_name"] for row in gate_rows]
            report["gate_status_counts"] = dict(Counter(row["status"] for row in gate_rows))
            if apply:
                _insert_gate_rows(conn, gate_rows)
                conn.commit()

        if apply and "exceptions" in sections and "gates" in sections:
            binding_updates = _build_exception_updates(conn, as_of=as_of)
            if binding_updates:
                _apply_exception_updates(conn, binding_updates)
                conn.commit()
            report["post_gate_exception_binding_updates"] = len(binding_updates)

        if apply:
            report["source_freshness_result_count_after"] = _count_table(conn, "source_freshness_result")
            report["policy_gate_result_count_after"] = _count_table(conn, "policy_gate_result")
            report["open_high_exception_count_after"] = len(_open_high_exception_rows(conn))
            if "source_freshness" in sections:
                report["inserted_or_replaced"] = len(source_rows)
            if "gates" in sections:
                report["inserted_or_replaced_gates"] = len(gate_rows)
    return report


def materialize_source_freshness_results(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: str,
    run_id: str,
    apply: bool = False,
    backup_dir: Path | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
    source_ids: set[str] | None = None,
) -> dict[str, Any]:
    return _materialize(
        db_path=db_path,
        policy_path=policy_path,
        as_of=as_of,
        run_id=run_id,
        apply=apply,
        backup_dir=backup_dir,
        sections={"source_freshness"},
        source_ids=source_ids,
    )


def backfill_exception_queue_metadata(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: str,
    run_id: str,
    apply: bool = False,
    backup_dir: Path | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    return _materialize(
        db_path=db_path,
        policy_path=policy_path,
        as_of=as_of,
        run_id=run_id,
        apply=apply,
        backup_dir=backup_dir,
        sections={"exceptions"},
    )


def materialize_policy_gate_results(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: str,
    run_id: str,
    apply: bool = False,
    backup_dir: Path | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    return _materialize(
        db_path=db_path,
        policy_path=policy_path,
        as_of=as_of,
        run_id=run_id,
        apply=apply,
        backup_dir=backup_dir,
        sections={"gates"},
    )


def materialize_c3_policy_state(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    as_of: str,
    run_id: str,
    apply: bool = False,
    backup_dir: Path | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
    source_ids: set[str] | None = None,
) -> dict[str, Any]:
    return _materialize(
        db_path=db_path,
        policy_path=policy_path,
        as_of=as_of,
        run_id=run_id,
        apply=apply,
        backup_dir=backup_dir,
        sections={"source_freshness", "exceptions", "gates"},
        source_ids=source_ids,
    )
