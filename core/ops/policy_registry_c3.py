from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "operational_decision_policy.yaml"
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
POLICY_NAMESPACE = "operational_decision_policy"

REQUIRED_C3_GATE_NAMES = {
    "policy_registry",
    "source_freshness",
    "exception_queue",
    "manual_approvals",
    "stock_source_truth",
    "ads_source_truth",
    "cashflow_source_truth",
    "po_source_truth",
    "wiki_context_routing",
}

BLOCKING_FRESHNESS_STATUSES = {
    "STALE",
    "MISSING",
    "EMPTY",
    "FUTURE",
    "UNKNOWN",
    "CONFLICT",
    "BLOCKED",
    "ERROR",
    "PARTIAL",
    "NO_AUTH",
}

REQUIRED_C3_TABLES: dict[str, set[str]] = {
    "policy_version": {
        "policy_version_id",
        "namespace",
        "version",
        "status",
        "effective_from",
        "effective_to",
        "timezone",
        "owner_role",
        "canonical_doc_path",
        "canonical_doc_sha256",
        "source_yaml_path",
        "source_yaml_sha256",
        "source_yaml_loaded_at",
        "approved_by",
        "approved_at",
        "approval_id",
        "supersedes_policy_version_id",
        "rollback_of_policy_version_id",
        "created_by",
        "created_at",
        "notes",
    },
    "policy_value": {
        "policy_value_id",
        "policy_version_id",
        "policy_path",
        "domain",
        "authority_class",
        "value_type",
        "value_json",
        "unit",
        "effective_from",
        "effective_to",
        "owner_role",
        "source_doc_path",
        "source_yaml_path",
        "source_yaml_sha256",
        "fail_closed_action",
        "created_at",
    },
    "policy_source_registry": {
        "policy_source_id",
        "domain",
        "source_owner",
        "source_kind",
        "source_path",
        "source_table",
        "external_system",
        "route_key",
        "authority_role",
        "policy_path",
        "required_for_gate",
        "required_for_publication",
        "max_age_value",
        "max_age_unit",
        "freshness_basis",
        "active_from",
        "active_to",
        "owner_role",
        "secret_safe",
        "notes",
        "created_at",
    },
    "source_freshness_result": {
        "freshness_result_id",
        "run_id",
        "policy_version_id",
        "policy_source_id",
        "as_of_date",
        "observed_at",
        "max_observed_at",
        "source_sha256",
        "row_count",
        "freshness_status",
        "max_age_value",
        "max_age_unit",
        "lag_seconds",
        "blocks_publication",
        "evidence_json",
        "created_at",
    },
    "policy_gate_result": {
        "gate_result_id",
        "run_id",
        "policy_version_id",
        "gate_name",
        "domain",
        "status",
        "severity",
        "blocks_owner_publication",
        "policy_paths_json",
        "source_ids_json",
        "freshness_result_ids_json",
        "message",
        "evidence_json",
        "created_at",
    },
    "manual_decision_approval": {
        "approval_id",
        "domain",
        "request_type",
        "target_table",
        "target_id",
        "policy_version_id",
        "policy_path",
        "exception_id",
        "gate_result_id",
        "owner_role_required",
        "requested_by",
        "requested_at",
        "decision",
        "approved_by",
        "approved_at",
        "valid_from",
        "valid_to",
        "evidence_paths_json",
        "notes",
        "cannot_override_publication_gate",
    },
    "source_pointer": {
        "source_pointer_id",
        "domain",
        "event_type",
        "fact_key",
        "fact_value",
        "owning_source_system",
        "owning_repo_path",
        "owning_wiki_path",
        "compiled_wiki_page_path",
        "primary_source_path",
        "source_kind",
        "source_id",
        "source_hash",
        "source_lineage",
        "source_as_of",
        "captured_at",
        "confirmed_at",
        "review_due_at",
        "effective_from",
        "effective_to",
        "decision_grade",
        "freshness_state",
        "contradiction_state",
        "evidence_strength",
        "memory_tier",
        "route_scope",
        "supplier_company_id",
        "supplier_company_aliases",
        "supplier_contact_route_id",
        "confidentiality_group",
        "conflict_group",
        "supersedes_source_pointer_id",
        "superseded_by_source_pointer_id",
        "requires_source_refresh_before_apply",
        "human_owner_required",
        "raw_copy_allowed",
        "secret_or_private_artifact_flag",
        "external_write_allowed",
        "notes",
        "created_at",
    },
    "policy_change_event": {
        "event_id",
        "event_type",
        "policy_version_id",
        "from_policy_version_id",
        "to_policy_version_id",
        "actor",
        "event_at",
        "reason",
        "db_backup_path",
        "dry_run_report_path",
        "validator_report_path",
        "git_head",
        "evidence_json",
    },
    "policy_registry_backup": {
        "backup_id",
        "policy_version_id",
        "db_backup_path",
        "db_backup_sha256",
        "created_at",
        "created_by",
        "restore_command",
        "notes",
    },
}

REQUIRED_EXCEPTION_QUEUE_COLUMNS = {
    "owner",
    "recommended_action",
    "evidence_paths_json",
    "policy_version_id",
    "policy_path",
    "policy_source_id",
    "gate_result_id",
    "due_at",
    "resolved_by",
    "resolution_decision",
    "resolution_approval_id",
    "updated_at",
}

REQUIRED_C3_INDEXES = {
    "ux_policy_version_active_namespace",
    "ux_policy_value_version_path",
    "idx_source_freshness_latest",
    "idx_policy_gate_latest",
    "idx_exception_queue_open_owner",
}

REQUIRED_C3_VIEWS = {
    "v_policy_active_metadata",
    "v_policy_active_value",
    "v_policy_active_json",
    "v_source_freshness_current",
    "v_policy_gate_latest",
    "v_publication_blockers",
    "v_open_exception_queue",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _view_exists(conn: sqlite3.Connection, view: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",
            (view,),
        ).fetchone()
        is not None
    )


def _index_exists(conn: sqlite3.Connection, index: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (index,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in _columns(conn, table)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if _table_exists(conn, table) and not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def backup_database(db_path: Path, backup_dir: Path, *, label: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_before_{label}_{stamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open an existing SQLite DB in hard read-only mode for validators/dry-runs."""

    resolved = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def migrate_policy_registry_c3(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS policy_version (
                policy_version_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL DEFAULT 'operational_decision_policy',
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                timezone TEXT NOT NULL,
                owner_role TEXT NOT NULL,
                canonical_doc_path TEXT NOT NULL,
                canonical_doc_sha256 TEXT,
                source_yaml_path TEXT NOT NULL,
                source_yaml_sha256 TEXT NOT NULL,
                source_yaml_loaded_at TEXT NOT NULL,
                approved_by TEXT,
                approved_at TEXT,
                approval_id TEXT,
                supersedes_policy_version_id TEXT,
                rollback_of_policy_version_id TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                notes TEXT,
                CHECK(status IN ('DRAFT','ACTIVE','RETIRED','ROLLED_BACK'))
            );

            CREATE TABLE IF NOT EXISTS policy_value (
                policy_value_id TEXT PRIMARY KEY,
                policy_version_id TEXT NOT NULL REFERENCES policy_version(policy_version_id),
                policy_path TEXT NOT NULL,
                domain TEXT NOT NULL,
                authority_class TEXT NOT NULL,
                value_type TEXT NOT NULL,
                value_json TEXT NOT NULL,
                unit TEXT,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                owner_role TEXT NOT NULL,
                source_doc_path TEXT,
                source_yaml_path TEXT NOT NULL,
                source_yaml_sha256 TEXT NOT NULL,
                fail_closed_action TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS policy_source_registry (
                policy_source_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                source_owner TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_path TEXT,
                source_table TEXT,
                external_system TEXT,
                route_key TEXT,
                authority_role TEXT NOT NULL,
                policy_path TEXT,
                required_for_gate TEXT,
                required_for_publication INTEGER NOT NULL DEFAULT 1,
                max_age_value INTEGER,
                max_age_unit TEXT,
                freshness_basis TEXT,
                active_from TEXT NOT NULL,
                active_to TEXT,
                owner_role TEXT NOT NULL,
                secret_safe INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS source_freshness_result (
                freshness_result_id TEXT PRIMARY KEY,
                run_id TEXT,
                policy_version_id TEXT NOT NULL,
                policy_source_id TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                max_observed_at TEXT,
                source_sha256 TEXT,
                row_count INTEGER,
                freshness_status TEXT NOT NULL,
                max_age_value INTEGER,
                max_age_unit TEXT,
                lag_seconds INTEGER,
                blocks_publication INTEGER NOT NULL DEFAULT 1,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS policy_gate_result (
                gate_result_id TEXT PRIMARY KEY,
                run_id TEXT,
                policy_version_id TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                domain TEXT NOT NULL,
                status TEXT NOT NULL,
                severity TEXT NOT NULL,
                blocks_owner_publication INTEGER NOT NULL DEFAULT 1,
                policy_paths_json TEXT NOT NULL DEFAULT '[]',
                source_ids_json TEXT NOT NULL DEFAULT '[]',
                freshness_result_ids_json TEXT NOT NULL DEFAULT '[]',
                message TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS manual_decision_approval (
                approval_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                request_type TEXT NOT NULL,
                target_table TEXT,
                target_id TEXT,
                policy_version_id TEXT NOT NULL,
                policy_path TEXT,
                exception_id TEXT,
                gate_result_id TEXT,
                owner_role_required TEXT NOT NULL,
                requested_by TEXT,
                requested_at TEXT NOT NULL DEFAULT (datetime('now')),
                decision TEXT NOT NULL,
                approved_by TEXT,
                approved_at TEXT,
                valid_from TEXT,
                valid_to TEXT,
                evidence_paths_json TEXT NOT NULL DEFAULT '[]',
                notes TEXT,
                cannot_override_publication_gate INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS source_pointer (
                source_pointer_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                event_type TEXT,
                fact_key TEXT,
                fact_value TEXT,
                owning_source_system TEXT,
                owning_repo_path TEXT,
                owning_wiki_path TEXT,
                compiled_wiki_page_path TEXT,
                primary_source_path TEXT,
                source_kind TEXT NOT NULL,
                source_id TEXT,
                source_hash TEXT,
                source_lineage TEXT,
                source_as_of TEXT,
                captured_at TEXT,
                confirmed_at TEXT,
                review_due_at TEXT,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                decision_grade INTEGER NOT NULL DEFAULT 0,
                freshness_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                contradiction_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                evidence_strength TEXT NOT NULL DEFAULT 'pointer',
                memory_tier TEXT NOT NULL,
                route_scope TEXT,
                supplier_company_id TEXT,
                supplier_company_aliases TEXT,
                supplier_contact_route_id TEXT,
                confidentiality_group TEXT,
                conflict_group TEXT,
                supersedes_source_pointer_id TEXT,
                superseded_by_source_pointer_id TEXT,
                requires_source_refresh_before_apply INTEGER NOT NULL DEFAULT 1,
                human_owner_required INTEGER NOT NULL DEFAULT 0,
                raw_copy_allowed INTEGER NOT NULL DEFAULT 0,
                secret_or_private_artifact_flag INTEGER NOT NULL DEFAULT 0,
                external_write_allowed INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS policy_change_event (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                policy_version_id TEXT NOT NULL,
                from_policy_version_id TEXT,
                to_policy_version_id TEXT,
                actor TEXT NOT NULL,
                event_at TEXT NOT NULL DEFAULT (datetime('now')),
                reason TEXT,
                db_backup_path TEXT,
                dry_run_report_path TEXT,
                validator_report_path TEXT,
                git_head TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS policy_registry_backup (
                backup_id TEXT PRIMARY KEY,
                policy_version_id TEXT,
                db_backup_path TEXT NOT NULL,
                db_backup_sha256 TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                created_by TEXT NOT NULL,
                restore_command TEXT,
                notes TEXT
            );
            """
        )

        if _table_exists(conn, "exception_queue"):
            _ensure_column(conn, "exception_queue", "owner", "TEXT NOT NULL DEFAULT ''")
            _ensure_column(conn, "exception_queue", "recommended_action", "TEXT NOT NULL DEFAULT ''")
            _ensure_column(conn, "exception_queue", "evidence_paths_json", "TEXT NOT NULL DEFAULT '[]'")
            _ensure_column(conn, "exception_queue", "policy_version_id", "TEXT")
            _ensure_column(conn, "exception_queue", "policy_path", "TEXT")
            _ensure_column(conn, "exception_queue", "policy_source_id", "TEXT")
            _ensure_column(conn, "exception_queue", "gate_result_id", "TEXT")
            _ensure_column(conn, "exception_queue", "due_at", "TEXT")
            _ensure_column(conn, "exception_queue", "resolved_by", "TEXT")
            _ensure_column(conn, "exception_queue", "resolution_decision", "TEXT")
            _ensure_column(conn, "exception_queue", "resolution_approval_id", "TEXT")
            _ensure_column(conn, "exception_queue", "updated_at", "TEXT")
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS exception_queue (
                    exception_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    domain TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    reason TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now')),
                    resolved_at TEXT,
                    owner TEXT NOT NULL DEFAULT '',
                    recommended_action TEXT NOT NULL DEFAULT '',
                    evidence_paths_json TEXT NOT NULL DEFAULT '[]',
                    policy_version_id TEXT,
                    policy_path TEXT,
                    policy_source_id TEXT,
                    gate_result_id TEXT,
                    due_at TEXT,
                    resolved_by TEXT,
                    resolution_decision TEXT,
                    resolution_approval_id TEXT,
                    updated_at TEXT
                );
                """
            )

        conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_policy_version_active_namespace
            ON policy_version(namespace)
            WHERE status = 'ACTIVE';

            CREATE UNIQUE INDEX IF NOT EXISTS ux_policy_value_version_path
            ON policy_value(policy_version_id, policy_path);

            CREATE INDEX IF NOT EXISTS idx_source_freshness_latest
            ON source_freshness_result(policy_source_id, policy_version_id, observed_at);

            CREATE INDEX IF NOT EXISTS idx_policy_gate_latest
            ON policy_gate_result(policy_version_id, gate_name, created_at);

            CREATE INDEX IF NOT EXISTS idx_exception_queue_open_owner
            ON exception_queue(status, owner, due_at);

            CREATE VIEW IF NOT EXISTS v_policy_active_metadata AS
            SELECT *
            FROM policy_version
            WHERE status = 'ACTIVE';

            CREATE VIEW IF NOT EXISTS v_policy_active_value AS
            SELECT pv.namespace, pv.policy_version_id, pv.version, pv.status,
                   pv.effective_from AS policy_effective_from,
                   pv.effective_to AS policy_effective_to,
                   pval.policy_path, pval.domain, pval.authority_class,
                   pval.value_type, pval.value_json, pval.unit,
                   pval.fail_closed_action, pval.owner_role
            FROM policy_version pv
            JOIN policy_value pval ON pval.policy_version_id = pv.policy_version_id
            WHERE pv.status = 'ACTIVE'
              AND (pval.effective_to IS NULL OR pval.effective_to > datetime('now'));

            CREATE VIEW IF NOT EXISTS v_policy_active_json AS
            SELECT policy_version_id, policy_path, value_json, value_type
            FROM v_policy_active_value
            ORDER BY policy_path;

            CREATE VIEW IF NOT EXISTS v_source_freshness_current AS
            SELECT sfr.*
            FROM source_freshness_result sfr
            JOIN (
                SELECT policy_version_id, policy_source_id, MAX(observed_at) AS observed_at
                FROM source_freshness_result
                GROUP BY policy_version_id, policy_source_id
            ) latest
              ON latest.policy_version_id = sfr.policy_version_id
             AND latest.policy_source_id = sfr.policy_source_id
             AND latest.observed_at = sfr.observed_at;

            CREATE VIEW IF NOT EXISTS v_policy_gate_latest AS
            SELECT pgr.*
            FROM policy_gate_result pgr
            JOIN (
                SELECT policy_version_id, gate_name, MAX(rowid) AS max_rowid
                FROM policy_gate_result
                GROUP BY policy_version_id, gate_name
            ) latest
              ON latest.policy_version_id = pgr.policy_version_id
             AND latest.gate_name = pgr.gate_name
             AND latest.max_rowid = pgr.rowid;

            CREATE VIEW IF NOT EXISTS v_publication_blockers AS
            SELECT *
            FROM v_policy_gate_latest
            WHERE UPPER(status) IN ('FAIL', 'BLOCKED')
              AND blocks_owner_publication = 1;

            CREATE VIEW IF NOT EXISTS v_open_exception_queue AS
            SELECT exception_id, run_id, domain, severity, status, reason,
                   owner, recommended_action, evidence_paths_json,
                   policy_version_id, policy_path, policy_source_id, gate_result_id,
                   due_at, created_at, updated_at
            FROM exception_queue
            WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'PENDING', 'BLOCKED');
            """
        )
        conn.commit()


def apply_policy_registry_schema_migration(
    *,
    db_path: Path,
    backup_dir: Path,
    actor: str = "agent7",
    now: str | None = None,
) -> dict[str, Any]:
    if os.environ.get("ENABLE_POLICY_REGISTRY_WRITE") != "1":
        raise RuntimeError("ENABLE_POLICY_REGISTRY_WRITE=1 is required to apply C3 migration")
    if not db_path.exists():
        raise RuntimeError(f"DB does not exist: {db_path}")

    event_at = now or _now_iso()
    backup_path = backup_database(db_path, backup_dir, label="policy_registry_c3_migration")
    migrate_policy_registry_c3(db_path)
    git_head = _git_head()
    event_id = "policy_migration:" + _sha256_text(f"{db_path}:{backup_path}:{event_at}")[:24]

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO policy_change_event (
                event_id, event_type, policy_version_id, actor, event_at,
                reason, db_backup_path, git_head, evidence_json
            ) VALUES (?, 'MIGRATE', 'SCHEMA_C3', ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                actor,
                event_at,
                "Additive C3 policy registry schema migration.",
                str(backup_path),
                git_head,
                _json({"validator": "validate_policy_registry_schema"}),
            ),
        )
        conn.commit()

    return {
        "applied": True,
        "db_path": str(db_path),
        "backup_path": str(backup_path),
        "git_head": git_head,
        "schema_errors": validate_policy_registry_schema(db_path),
    }


def _load_policy(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Policy YAML must be a mapping: {path}")
    return data


def flatten_policy(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        rows: dict[str, Any] = {}
        for key in sorted(data):
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.update(flatten_policy(data[key], child))
        return rows
    return {prefix: data}


def _domain_for_path(policy_path: str) -> str:
    if policy_path.startswith("stock_") or policy_path.startswith("stock_status_rules"):
        return "stock"
    if policy_path.startswith("store_scope"):
        return "stock"
    if policy_path.startswith("ads_truth"):
        return "ads"
    if policy_path.startswith("purchase_order_truth"):
        return "po"
    if policy_path.startswith("cashflow_truth"):
        return "cashflow"
    if policy_path.startswith("publication_gates"):
        return "publication"
    if policy_path.startswith("decision_thresholds.freshness"):
        return "source_freshness"
    if policy_path.startswith("decision_thresholds.sku_mapping"):
        return "stock"
    if policy_path.startswith("decision_thresholds.reorder"):
        return "po"
    if policy_path.startswith("manual_review_ownership"):
        return "manual_review"
    if policy_path.startswith("future_c3_migration"):
        return "roadmap"
    return "policy"


def _looks_like_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("/") or value.startswith("docs/") or value.startswith("config/")


def _authority_for_path(policy_path: str, value: Any) -> str:
    if policy_path.startswith("future_c3_migration") or policy_path.endswith(".target_state"):
        return "roadmap_metadata"
    if policy_path.endswith("source") and _looks_like_path(value):
        return "formula_pointer"
    if policy_path.endswith("_path") or policy_path.endswith("_root") or policy_path in {
        "canonical_doc",
        "owner_qa_capture",
    }:
        return "source_pointer"
    if _looks_like_path(value):
        return "source_pointer"
    if policy_path in {"version", "status", "owner", "timezone", "fail_closed_default"}:
        return "bootstrap_metadata"
    return "runtime_policy"


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "real"
    if isinstance(value, str) and _looks_like_path(value):
        return "path"
    if isinstance(value, str):
        return "string"
    return "json"


def _unit_for_path(policy_path: str) -> str | None:
    if policy_path.endswith("_hours") or policy_path.endswith(".max_age_hours"):
        return "hours"
    if policy_path.endswith("_days") or policy_path.endswith(".max_age_days"):
        return "days"
    if policy_path.endswith("_kzt") or "_kzt_" in policy_path:
        return "KZT"
    if policy_path.endswith("_pct") or policy_path.endswith(".pct"):
        return "percent"
    return None


def _fail_closed_action(policy_path: str, value: Any) -> str | None:
    if policy_path.endswith(".action_if_stale") and value:
        return str(value)
    if "blocks" in policy_path and value is True:
        return "block_publication"
    if policy_path.endswith(".publication_waiver_allowed_by_agent") and value is False:
        return "agents_may_not_override_publication_gates"
    if policy_path.endswith(".may_override_publication_gates") and value is False:
        return "agents_may_not_override_publication_gates"
    if policy_path.endswith(".cannot_override_publication_gate") and value is True:
        return "cannot_override_publication_gate"
    return None


def _policy_value_rows(
    *,
    policy: dict[str, Any],
    policy_version_id: str,
    policy_path: Path,
    source_sha256: str,
    now: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, value in flatten_policy(policy).items():
        value_json = _json(value)
        rows.append(
            {
                "policy_value_id": f"{policy_version_id}:{_sha256_text(path)[:16]}",
                "policy_version_id": policy_version_id,
                "policy_path": path,
                "domain": _domain_for_path(path),
                "authority_class": _authority_for_path(path, value),
                "value_type": _value_type(value),
                "value_json": value_json,
                "unit": _unit_for_path(path),
                "effective_from": now,
                "owner_role": str(policy.get("owner") or "business_owner"),
                "source_doc_path": str(policy.get("canonical_doc") or ""),
                "source_yaml_path": str(policy_path.relative_to(PROJECT_ROOT)),
                "source_yaml_sha256": source_sha256,
                "fail_closed_action": _fail_closed_action(path, value),
            }
        )
    return rows


def _source_registry_seed(policy: dict[str, Any], *, now: str) -> list[dict[str, Any]]:
    return [
        {
            "policy_source_id": "src_ab_db_operational_truth",
            "domain": "operational_rollup",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_rollup",
            "source_path": "db/app.db",
            "source_table": None,
            "external_system": None,
            "route_key": None,
            "authority_role": "rollup_observation",
            "policy_path": "operational_truth.rollup",
            "required_for_gate": "source_freshness_rollup",
            "required_for_publication": 0,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "child_source_rollup",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "AB operational DB roll-up remains informational; child source rows own publication blocking.",
        },
        {
            "policy_source_id": "src_ab_db_order_entry_truth",
            "domain": "order_entry",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "fact_order_entries_kaspi",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.order_entry",
            "required_for_gate": "stock_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Order-entry freshness child source for AB copied-temp and owner-publication gates.",
        },
        {
            "policy_source_id": "src_ab_db_cashflow_truth",
            "domain": "cashflow",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "fact_cashflow_events,fact_cashflow_daily",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.cashflow",
            "required_for_gate": "cashflow_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Cashflow operational-table freshness child source.",
        },
        {
            "policy_source_id": "src_ab_db_stock_truth",
            "domain": "stock",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "fact_inventory_snapshot_size,stock_ledger",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.stock",
            "required_for_gate": "stock_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Stock snapshot and ledger freshness child source; stale rows block stock/PO publication claims.",
        },
        {
            "policy_source_id": "src_ab_db_sales_truth",
            "domain": "sales",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "sales_fact_v2",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.sales",
            "required_for_gate": "stock_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Sales fact freshness child source for stock/profit claim safety.",
        },
        {
            "policy_source_id": "src_ab_db_order_status_truth",
            "domain": "order_status",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "order_status_event",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.order_status",
            "required_for_gate": "stock_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Lifecycle/status freshness child source; stale rows block dependent publication claims.",
        },
        {
            "policy_source_id": "src_ab_db_ads_truth",
            "domain": "ads",
            "source_owner": "Autonomous_business",
            "source_kind": "sqlite_operational_table_group",
            "source_path": "db/app.db",
            "source_table": "ads_source_refresh_runs,ads_campaign_product_daily",
            "external_system": None,
            "route_key": None,
            "authority_role": "event_source",
            "policy_path": "operational_truth.ads",
            "required_for_gate": "ads_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "max_event_date_per_table",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "AB-local ads materialization freshness child source; stale rows block ads/profit publication claims.",
        },
        {
            "policy_source_id": "src_web_automation_kaspi_marketing_directapi",
            "domain": "ads",
            "source_owner": "Web_automation",
            "source_kind": "handoff",
            "source_path": "~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md",
            "source_table": None,
            "external_system": "kaspi_marketing_directapi",
            "route_key": "ACMEWEAR_STOREB",
            "authority_role": "evidence_pointer",
            "policy_path": "ads_truth",
            "required_for_gate": "ads_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "source_hash",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "DirectAPI remains dry-run/post-verify gated; no live control approval.",
        },
        {
            "policy_source_id": "src_facebook_ads_external_ads",
            "domain": "ads",
            "source_owner": "Facebook_ads",
            "source_kind": "external_file",
            "source_path": str(policy.get("ads_truth", {}).get("external_ads_source_root", "")),
            "source_table": None,
            "external_system": "meta_instagram",
            "route_key": "ACMEWEAR",
            "authority_role": "evidence_pointer",
            "policy_path": "ads_truth.external_ads_source_root",
            "required_for_gate": "ads_source_truth",
            "required_for_publication": 1,
            "max_age_value": 24,
            "max_age_unit": "hours",
            "freshness_basis": "recursive_latest_artifact_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Meta/Instagram traffic/spend truth applies to ACMEWEAR funnel evidence only; STOREB uses Kaspi internal marketing evidence.",
        },
        {
            "policy_source_id": "src_ecommerce_po_artifacts",
            "domain": "po",
            "source_owner": "E-commerce",
            "source_kind": "external_file",
            "source_path": "~/Cowork/Projects/E-commerce",
            "source_table": None,
            "external_system": None,
            "route_key": "LINE31_PO1A_20260428_TRACY",
            "authority_role": "evidence_pointer",
            "policy_path": "purchase_order_truth",
            "required_for_gate": "po_source_truth",
            "required_for_publication": 1,
            "max_age_value": 7,
            "max_age_unit": "days",
            "freshness_basis": "recursive_latest_artifact_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "PO inquiry and supplier-facing artifact source pointer.",
        },
        {
            "policy_source_id": "src_sourcing_research_supplier_routes",
            "domain": "po",
            "source_owner": "Sourcing-Research",
            "source_kind": "external_file",
            "source_path": "~/Cowork/Projects/Sourcing-Research",
            "source_table": None,
            "external_system": None,
            "route_key": "ROUTE__JUYITANG__TRACY_WUCHUN__LINE31_PO1A450",
            "authority_role": "evidence_pointer",
            "policy_path": "purchase_order_truth",
            "required_for_gate": "po_source_truth",
            "required_for_publication": 1,
            "max_age_value": 7,
            "max_age_unit": "days",
            "freshness_basis": "recursive_latest_artifact_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Supplier route evidence pointer; raw chat/media stays outside AB.",
        },
        {
            "policy_source_id": "src_inbound_workbook",
            "domain": "po",
            "source_owner": "Autonomous_business",
            "source_kind": "workbook",
            "source_path": str(policy.get("purchase_order_truth", {}).get("canonical_inbound_workbook", "")),
            "source_table": None,
            "external_system": None,
            "route_key": None,
            "authority_role": "freshness_source",
            "policy_path": "purchase_order_truth.canonical_inbound_workbook",
            "required_for_gate": "po_source_truth",
            "required_for_publication": 1,
            "max_age_value": 7,
            "max_age_unit": "days",
            "freshness_basis": "file_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Canonical inbound workbook until owner-approved replacement.",
        },
        {
            "policy_source_id": "src_bank_manual_ingest",
            "domain": "cashflow",
            "source_owner": "Autonomous_business",
            "source_kind": "yaml",
            "source_path": str(policy.get("cashflow_truth", {}).get("manual_balance_latest_path", "")),
            "source_table": None,
            "external_system": None,
            "route_key": None,
            "authority_role": "freshness_source",
            "policy_path": "cashflow_truth.manual_balance_latest_path",
            "required_for_gate": "cashflow_source_truth",
            "required_for_publication": 1,
            "max_age_value": 7,
            "max_age_unit": "days",
            "freshness_basis": "file_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Bank snapshots are reconciliation evidence, not duplicate cashflow events.",
        },
        {
            "policy_source_id": "src_payment_evidence_root",
            "domain": "cashflow",
            "source_owner": "Autonomous_business",
            "source_kind": "external_file",
            "source_path": str(policy.get("purchase_order_truth", {}).get("transaction_evidence_root", "")),
            "source_table": None,
            "external_system": None,
            "route_key": None,
            "authority_role": "evidence_pointer",
            "policy_path": "purchase_order_truth.transaction_evidence_root",
            "required_for_gate": "cashflow_source_truth",
            "required_for_publication": 1,
            "max_age_value": 7,
            "max_age_unit": "days",
            "freshness_basis": "file_mtime",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Payment evidence pointer only; raw payment receiver/QR data must stay controlled.",
        },
        {
            "policy_source_id": "src_commerce_ops_wiki_context",
            "domain": "wiki_context",
            "source_owner": "commerce-ops-wiki",
            "source_kind": "wiki",
            "source_path": "~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki",
            "source_table": None,
            "external_system": None,
            "route_key": "compiled_memory",
            "authority_role": "evidence_pointer",
            "policy_path": None,
            "required_for_gate": "wiki_context_routing",
            "required_for_publication": 0,
            "max_age_value": None,
            "max_age_unit": None,
            "freshness_basis": "review_due_at",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Wiki is routing/context memory, not operational truth.",
        },
        {
            "policy_source_id": "src_business_wiki_context",
            "domain": "wiki_context",
            "source_owner": "business-wiki",
            "source_kind": "wiki",
            "source_path": "~/Docs/Oracle/knowledge-workspace/wikis/business-wiki",
            "source_table": None,
            "external_system": None,
            "route_key": "compiled_memory",
            "authority_role": "evidence_pointer",
            "policy_path": None,
            "required_for_gate": "wiki_context_routing",
            "required_for_publication": 0,
            "max_age_value": None,
            "max_age_unit": None,
            "freshness_basis": "review_due_at",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Executive routing context only.",
        },
        {
            "policy_source_id": "src_finance_exec_wiki_context",
            "domain": "wiki_context",
            "source_owner": "finance-exec-wiki",
            "source_kind": "wiki",
            "source_path": "~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki",
            "source_table": None,
            "external_system": None,
            "route_key": "compiled_memory",
            "authority_role": "evidence_pointer",
            "policy_path": None,
            "required_for_gate": "wiki_context_routing",
            "required_for_publication": 0,
            "max_age_value": None,
            "max_age_unit": None,
            "freshness_basis": "review_due_at",
            "active_from": now,
            "owner_role": "business_owner",
            "notes": "Finance wiki is memory/routing; current cash needs primary source evidence.",
        },
    ]


def _source_pointer_seed(policy: dict[str, Any], *, now: str, yaml_hash: str) -> list[dict[str, Any]]:
    return [
        {
            "source_pointer_id": "ptr_policy_yaml_bootstrap_contract",
            "domain": "policy",
            "event_type": "POLICY_CONTRACT",
            "fact_key": "operational_decision_policy_yaml",
            "fact_value": str(policy.get("version")),
            "owning_source_system": "Autonomous_business",
            "owning_repo_path": str(PROJECT_ROOT),
            "owning_wiki_path": None,
            "compiled_wiki_page_path": None,
            "primary_source_path": str(DEFAULT_POLICY_PATH.relative_to(PROJECT_ROOT)),
            "source_kind": "yaml",
            "source_id": "config/operational_decision_policy.yaml",
            "source_hash": yaml_hash,
            "source_lineage": "C2 policy bootstrap promoted into C3 registry.",
            "source_as_of": now,
            "captured_at": now,
            "confirmed_at": now,
            "effective_from": now,
            "decision_grade": 1,
            "freshness_state": "current",
            "contradiction_state": "none",
            "evidence_strength": "primary_contract",
            "memory_tier": "primary_source",
            "requires_source_refresh_before_apply": 0,
            "human_owner_required": 0,
            "raw_copy_allowed": 1,
            "secret_or_private_artifact_flag": 0,
            "external_write_allowed": 0,
            "notes": "Safe local policy contract; no secrets.",
        },
        {
            "source_pointer_id": "ptr_owner_qa_current_c3_context",
            "domain": "policy",
            "event_type": "OWNER_QA_SOURCE_POINTER",
            "fact_key": "owner_qa_capture",
            "fact_value": str(policy.get("owner_qa_capture", "")),
            "owning_source_system": "Autonomous_business",
            "owning_repo_path": str(PROJECT_ROOT),
            "owning_wiki_path": None,
            "compiled_wiki_page_path": None,
            "primary_source_path": str(policy.get("owner_qa_capture", "")),
            "source_kind": "doc",
            "source_id": "owner_qa_capture",
            "source_hash": "",
            "source_lineage": "Owner QA file supplies current source-truth corrections.",
            "source_as_of": "2026-05-03",
            "captured_at": now,
            "confirmed_at": now,
            "effective_from": now,
            "decision_grade": 1,
            "freshness_state": "current",
            "contradiction_state": "none",
            "evidence_strength": "owner_qa",
            "memory_tier": "primary_source",
            "requires_source_refresh_before_apply": 0,
            "human_owner_required": 0,
            "raw_copy_allowed": 1,
            "secret_or_private_artifact_flag": 0,
            "external_write_allowed": 0,
            "notes": "Owner QA is newer than stale wiki pages and must remain distinct.",
        },
        {
            "source_pointer_id": "ptr_commerce_ops_wiki_line31_context",
            "domain": "wiki_context",
            "event_type": "COMPILED_WIKI_MEMORY",
            "fact_key": "line31_route_context",
            "fact_value": "routing_memory_only",
            "owning_source_system": "commerce-ops-wiki",
            "owning_repo_path": "~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki",
            "owning_wiki_path": "~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki",
            "compiled_wiki_page_path": "~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki/wiki/syntheses/SYN__LINE31_SOURCE_OF_TRUTH_MAP.md",
            "primary_source_path": None,
            "source_kind": "wiki",
            "source_id": "commerce_ops_wiki_line31_source_map",
            "source_hash": "",
            "source_lineage": "Compiled context; source refresh required before apply.",
            "source_as_of": None,
            "captured_at": now,
            "confirmed_at": None,
            "effective_from": now,
            "decision_grade": 0,
            "freshness_state": "stale_or_watch",
            "contradiction_state": "unknown",
            "evidence_strength": "compiled_memory",
            "memory_tier": "compiled_memory",
            "route_scope": "ARC_LINE31_SHORTAGE_DISPUTE_AND_TRACY_CLEAN_ROUTE",
            "conflict_group": "LINE31_ROUTE_SEPARATION",
            "requires_source_refresh_before_apply": 1,
            "human_owner_required": 1,
            "raw_copy_allowed": 0,
            "secret_or_private_artifact_flag": 0,
            "external_write_allowed": 0,
            "notes": "Do not convert wiki prose into operational truth.",
        },
        {
            "source_pointer_id": "ptr_finance_exec_wiki_cash_context",
            "domain": "wiki_context",
            "event_type": "COMPILED_WIKI_MEMORY",
            "fact_key": "cash_and_bank_context",
            "fact_value": "routing_memory_only",
            "owning_source_system": "finance-exec-wiki",
            "owning_repo_path": "~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki",
            "owning_wiki_path": "~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki",
            "compiled_wiki_page_path": "~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki/wiki/truths/cash_truth.md",
            "primary_source_path": None,
            "source_kind": "wiki",
            "source_id": "finance_exec_wiki_cash_truth",
            "source_hash": "",
            "source_lineage": "Compiled finance memory; primary bank evidence required.",
            "source_as_of": None,
            "captured_at": now,
            "confirmed_at": None,
            "effective_from": now,
            "decision_grade": 0,
            "freshness_state": "stale_or_watch",
            "contradiction_state": "unknown",
            "evidence_strength": "compiled_memory",
            "memory_tier": "compiled_memory",
            "requires_source_refresh_before_apply": 1,
            "human_owner_required": 1,
            "raw_copy_allowed": 0,
            "secret_or_private_artifact_flag": 0,
            "external_write_allowed": 0,
            "notes": "Bank snapshots are reconciliation evidence, not duplicated cashflow events.",
        },
    ]


def _insert_source_registry(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    changed = 0
    compare_fields = (
        "domain",
        "source_owner",
        "source_kind",
        "source_path",
        "source_table",
        "external_system",
        "route_key",
        "authority_role",
        "policy_path",
        "required_for_gate",
        "required_for_publication",
        "max_age_value",
        "max_age_unit",
        "freshness_basis",
        "owner_role",
        "notes",
    )
    for row in rows:
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO policy_source_registry (
                policy_source_id, domain, source_owner, source_kind, source_path,
                source_table, external_system, route_key, authority_role, policy_path,
                required_for_gate, required_for_publication, max_age_value, max_age_unit,
                freshness_basis, active_from, owner_role, notes
            ) VALUES (
                :policy_source_id, :domain, :source_owner, :source_kind, :source_path,
                :source_table, :external_system, :route_key, :authority_role, :policy_path,
                :required_for_gate, :required_for_publication, :max_age_value, :max_age_unit,
                :freshness_basis, :active_from, :owner_role, :notes
            )
            """,
            row,
        )
        delta = conn.total_changes - before
        if delta:
            changed += delta
            continue
        existing = conn.execute(
            """
            SELECT domain, source_owner, source_kind, source_path, source_table,
                   external_system, route_key, authority_role, policy_path,
                   required_for_gate, required_for_publication, max_age_value,
                   max_age_unit, freshness_basis, owner_role, notes
            FROM policy_source_registry
            WHERE policy_source_id=?
            """,
            (row["policy_source_id"],),
        ).fetchone()
        if existing is None:
            continue
        if all(existing[field] == row.get(field) for field in compare_fields):
            continue
        before = conn.total_changes
        conn.execute(
            """
            UPDATE policy_source_registry
            SET domain=:domain,
                source_owner=:source_owner,
                source_kind=:source_kind,
                source_path=:source_path,
                source_table=:source_table,
                external_system=:external_system,
                route_key=:route_key,
                authority_role=:authority_role,
                policy_path=:policy_path,
                required_for_gate=:required_for_gate,
                required_for_publication=:required_for_publication,
                max_age_value=:max_age_value,
                max_age_unit=:max_age_unit,
                freshness_basis=:freshness_basis,
                owner_role=:owner_role,
                notes=:notes
            WHERE policy_source_id=:policy_source_id
            """,
            row,
        )
        changed += conn.total_changes - before
    return changed


def _insert_source_pointers(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    fields = {
        "source_pointer_id",
        "domain",
        "event_type",
        "fact_key",
        "fact_value",
        "owning_source_system",
        "owning_repo_path",
        "owning_wiki_path",
        "compiled_wiki_page_path",
        "primary_source_path",
        "source_kind",
        "source_id",
        "source_hash",
        "source_lineage",
        "source_as_of",
        "captured_at",
        "confirmed_at",
        "effective_from",
        "decision_grade",
        "freshness_state",
        "contradiction_state",
        "evidence_strength",
        "memory_tier",
        "route_scope",
        "conflict_group",
        "requires_source_refresh_before_apply",
        "human_owner_required",
        "raw_copy_allowed",
        "secret_or_private_artifact_flag",
        "external_write_allowed",
        "notes",
    }
    for row in rows:
        params = {field: row.get(field) for field in fields}
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO source_pointer (
                source_pointer_id, domain, event_type, fact_key, fact_value,
                owning_source_system, owning_repo_path, owning_wiki_path,
                compiled_wiki_page_path, primary_source_path, source_kind,
                source_id, source_hash, source_lineage, source_as_of, captured_at,
                confirmed_at, effective_from, decision_grade, freshness_state,
                contradiction_state, evidence_strength, memory_tier, route_scope,
                conflict_group, requires_source_refresh_before_apply,
                human_owner_required, raw_copy_allowed, secret_or_private_artifact_flag,
                external_write_allowed, notes
            ) VALUES (
                :source_pointer_id, :domain, :event_type, :fact_key, :fact_value,
                :owning_source_system, :owning_repo_path, :owning_wiki_path,
                :compiled_wiki_page_path, :primary_source_path, :source_kind,
                :source_id, :source_hash, :source_lineage, :source_as_of, :captured_at,
                :confirmed_at, :effective_from, :decision_grade, :freshness_state,
                :contradiction_state, :evidence_strength, :memory_tier, :route_scope,
                :conflict_group, :requires_source_refresh_before_apply,
                :human_owner_required, :raw_copy_allowed, :secret_or_private_artifact_flag,
                :external_write_allowed, :notes
            )
            """,
            params,
        )
        inserted += conn.total_changes - before
    return inserted


def promote_operational_decision_policy(
    *,
    db_path: Path,
    policy_path: Path = DEFAULT_POLICY_PATH,
    apply: bool = False,
    backup_dir: Path | None = None,
    actor: str = "agent7",
    now: str | None = None,
) -> dict[str, Any]:
    policy_path = policy_path.expanduser().resolve()
    db_path = db_path.expanduser().resolve()
    policy = _load_policy(policy_path)
    source_yaml_sha256 = _sha256_file(policy_path)
    canonical_doc = str(policy.get("canonical_doc") or "")
    canonical_doc_path = (PROJECT_ROOT / canonical_doc).resolve() if canonical_doc else None
    canonical_doc_sha256 = _sha256_file(canonical_doc_path) if canonical_doc_path else ""
    event_at = now or _now_iso()
    policy_version_id = f"{POLICY_NAMESPACE}_v{policy.get('version')}_{source_yaml_sha256[:12]}"
    value_rows = _policy_value_rows(
        policy=policy,
        policy_version_id=policy_version_id,
        policy_path=policy_path,
        source_sha256=source_yaml_sha256,
        now=event_at,
    )

    report: dict[str, Any] = {
        "applied": False,
        "policy_version_id": policy_version_id,
        "policy_leaf_count": len(value_rows),
        "source_yaml_sha256": source_yaml_sha256,
        "backup_path": None,
        "policy_version_reused": False,
        "inserted_policy_values": 0,
        "inserted_sources": 0,
        "inserted_source_pointers": 0,
    }
    if not apply:
        report["proposed_policy_paths"] = [row["policy_path"] for row in value_rows]
        return report

    if os.environ.get("ENABLE_POLICY_REGISTRY_WRITE") != "1":
        raise RuntimeError("ENABLE_POLICY_REGISTRY_WRITE=1 is required to promote policy registry rows")
    if not db_path.exists():
        raise RuntimeError(f"DB does not exist: {db_path}")

    backup_root = backup_dir or (PROJECT_ROOT / "runtime" / "backups")
    backup_path = backup_database(db_path, backup_root, label="policy_registry_c3_promotion")
    report["backup_path"] = str(backup_path)
    migrate_policy_registry_c3(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT policy_version_id FROM policy_version WHERE policy_version_id=?",
            (policy_version_id,),
        ).fetchone()
        active = conn.execute(
            """
            SELECT policy_version_id
            FROM policy_version
            WHERE namespace=? AND status='ACTIVE'
            """,
            (POLICY_NAMESPACE,),
        ).fetchone()
        if existing is None:
            if active is not None:
                conn.execute(
                    """
                    UPDATE policy_version
                    SET status='RETIRED', effective_to=?
                    WHERE policy_version_id=?
                    """,
                    (event_at, active["policy_version_id"]),
                )
            conn.execute(
                """
                INSERT INTO policy_version (
                    policy_version_id, namespace, version, status, effective_from,
                    timezone, owner_role, canonical_doc_path, canonical_doc_sha256,
                    source_yaml_path, source_yaml_sha256, source_yaml_loaded_at,
                    approved_by, approved_at, created_by, supersedes_policy_version_id,
                    notes
                ) VALUES (?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_version_id,
                    POLICY_NAMESPACE,
                    int(policy.get("version") or 0),
                    event_at,
                    str(policy.get("timezone") or "Asia/Almaty"),
                    str(policy.get("owner") or "business_owner"),
                    canonical_doc,
                    canonical_doc_sha256,
                    str(policy_path.relative_to(PROJECT_ROOT)),
                    source_yaml_sha256,
                    event_at,
                    actor,
                    event_at,
                    actor,
                    active["policy_version_id"] if active is not None else None,
                    "Promoted from config/operational_decision_policy.yaml for C3 runtime checks.",
                ),
            )
        else:
            report["policy_version_reused"] = True

        inserted_values = 0
        for row in value_rows:
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO policy_value (
                    policy_value_id, policy_version_id, policy_path, domain,
                    authority_class, value_type, value_json, unit, effective_from,
                    owner_role, source_doc_path, source_yaml_path,
                    source_yaml_sha256, fail_closed_action
                ) VALUES (
                    :policy_value_id, :policy_version_id, :policy_path, :domain,
                    :authority_class, :value_type, :value_json, :unit, :effective_from,
                    :owner_role, :source_doc_path, :source_yaml_path,
                    :source_yaml_sha256, :fail_closed_action
                )
                """,
                row,
            )
            inserted_values += conn.total_changes - before

        report["inserted_policy_values"] = inserted_values
        report["inserted_sources"] = _insert_source_registry(
            conn,
            _source_registry_seed(policy, now=event_at),
        )
        report["inserted_source_pointers"] = _insert_source_pointers(
            conn,
            _source_pointer_seed(policy, now=event_at, yaml_hash=source_yaml_sha256),
        )

        backup_sha = _sha256_file(backup_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO policy_registry_backup (
                backup_id, policy_version_id, db_backup_path, db_backup_sha256,
                created_at, created_by, restore_command, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "backup:" + _sha256_text(str(backup_path))[:24],
                policy_version_id,
                str(backup_path),
                backup_sha,
                event_at,
                actor,
                f"cp {backup_path} {db_path}",
                "Pre-promotion DB backup for C3 policy registry apply.",
            ),
        )
        event_id = "promote:" + _sha256_text(f"{policy_version_id}:{event_at}:{backup_path}")[:24]
        conn.execute(
            """
            INSERT OR REPLACE INTO policy_change_event (
                event_id, event_type, policy_version_id, from_policy_version_id,
                to_policy_version_id, actor, event_at, reason, db_backup_path,
                git_head, evidence_json
            ) VALUES (?, 'PROMOTE', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                policy_version_id,
                active["policy_version_id"] if active is not None else None,
                policy_version_id,
                actor,
                event_at,
                "Promoted operational decision policy YAML into C3 DB registry.",
                str(backup_path),
                _git_head(),
                _json(
                    {
                        "source_yaml_path": str(policy_path),
                        "source_yaml_sha256": source_yaml_sha256,
                        "inserted_policy_values": inserted_values,
                    }
                ),
            ),
        )
        conn.commit()

    report["applied"] = True
    return report


def validate_policy_registry_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    if not Path(db_path).exists():
        return [f"Database not found: {db_path}"]
    with connect_readonly(db_path) as conn:
        for table, required in REQUIRED_C3_TABLES.items():
            if not _table_exists(conn, table):
                errors.append(f"Missing table: {table}")
                continue
            missing = sorted(required - _columns(conn, table))
            if missing:
                errors.append(f"{table} missing columns: {', '.join(missing)}")
        if _table_exists(conn, "exception_queue"):
            missing_exc = sorted(REQUIRED_EXCEPTION_QUEUE_COLUMNS - _columns(conn, "exception_queue"))
            if missing_exc:
                errors.append(f"exception_queue missing columns: {', '.join(missing_exc)}")
        else:
            errors.append("Missing table: exception_queue")
        for index in sorted(REQUIRED_C3_INDEXES):
            if not _index_exists(conn, index):
                errors.append(f"Missing index: {index}")
        for view in sorted(REQUIRED_C3_VIEWS):
            if not _view_exists(conn, view):
                errors.append(f"Missing view: {view}")
    return errors


def _active_policy(conn: sqlite3.Connection) -> sqlite3.Row | None:
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
        return None
    return rows[0]


def validate_operational_decision_policy_registry(
    db_path: Path,
    policy_path: Path = DEFAULT_POLICY_PATH,
    *,
    strict: bool = False,
) -> list[str]:
    del strict
    errors = validate_policy_registry_schema(db_path)
    if errors:
        return errors

    policy = _load_policy(policy_path)
    expected = flatten_policy(policy)
    source_sha256 = _sha256_file(policy_path)

    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        active_rows = conn.execute(
            """
            SELECT *
            FROM policy_version
            WHERE namespace=? AND status='ACTIVE'
            """,
            (POLICY_NAMESPACE,),
        ).fetchall()
        if len(active_rows) != 1:
            errors.append(f"Expected exactly one ACTIVE {POLICY_NAMESPACE} policy; found {len(active_rows)}")
            return errors
        active = active_rows[0]
        if active["timezone"] != str(policy.get("timezone")):
            errors.append(f"Active policy timezone drift: DB={active['timezone']} YAML={policy.get('timezone')}")
        if active["owner_role"] != str(policy.get("owner")):
            errors.append(f"Active policy owner drift: DB={active['owner_role']} YAML={policy.get('owner')}")
        if active["canonical_doc_path"] != str(policy.get("canonical_doc")):
            errors.append(
                f"Active policy canonical_doc drift: DB={active['canonical_doc_path']} YAML={policy.get('canonical_doc')}"
            )
        if active["source_yaml_sha256"] != source_sha256:
            errors.append("Active policy source_yaml_sha256 drift from current YAML")
        if not active["approved_by"] or not active["approved_at"]:
            errors.append("Active policy must be approved before runtime use")

        db_rows = conn.execute(
            """
            SELECT policy_path, value_json
            FROM policy_value
            WHERE policy_version_id=?
            """,
            (active["policy_version_id"],),
        ).fetchall()
        actual = {row["policy_path"]: row["value_json"] for row in db_rows}

    for path, value in expected.items():
        expected_json = _json(value)
        if path not in actual:
            errors.append(f"Policy path missing from DB active policy: {path}")
        elif actual[path] != expected_json:
            errors.append(
                f"Policy registry drift for {path}: DB={actual[path]} YAML={expected_json}"
            )
    for path in sorted(set(actual) - set(expected)):
        errors.append(f"Extra active DB policy path absent from YAML: {path}")
    return errors


def validate_policy_source_freshness(
    db_path: Path,
    *,
    as_of: str | None = None,
    strict: bool = False,
) -> list[str]:
    del strict
    errors = validate_policy_registry_schema(db_path)
    if errors:
        return errors
    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        active = _active_policy(conn)
        if active is None:
            return [f"Expected exactly one ACTIVE {POLICY_NAMESPACE} policy for source freshness"]
        if as_of is None:
            rows = conn.execute(
                """
                SELECT psr.policy_source_id, psr.domain, psr.required_for_gate,
                       current.as_of_date, current.freshness_status,
                       current.blocks_publication, current.observed_at
                FROM policy_source_registry psr
                LEFT JOIN v_source_freshness_current current
                  ON current.policy_source_id = psr.policy_source_id
                 AND current.policy_version_id = ?
                WHERE psr.required_for_publication = 1
                  AND psr.active_to IS NULL
                ORDER BY psr.policy_source_id
                """,
                (active["policy_version_id"],),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT psr.policy_source_id, psr.domain, psr.required_for_gate,
                       current.as_of_date, current.freshness_status,
                       current.blocks_publication, current.observed_at
                FROM policy_source_registry psr
                LEFT JOIN source_freshness_result current
                  ON current.policy_source_id = psr.policy_source_id
                 AND current.policy_version_id = ?
                 AND current.as_of_date = ?
                 AND current.observed_at = (
                    SELECT MAX(sfr2.observed_at)
                    FROM source_freshness_result sfr2
                    WHERE sfr2.policy_version_id = current.policy_version_id
                      AND sfr2.policy_source_id = current.policy_source_id
                      AND sfr2.as_of_date = current.as_of_date
                 )
                WHERE psr.required_for_publication = 1
                  AND psr.active_to IS NULL
                ORDER BY psr.policy_source_id
                """,
                (active["policy_version_id"], as_of),
            ).fetchall()
    for row in rows:
        if row["freshness_status"] is None:
            if as_of is not None:
                errors.append(
                    f"Required source {row['policy_source_id']} has missing freshness result for requested as-of {as_of}"
                )
                continue
            errors.append(
                f"Required source {row['policy_source_id']} has missing freshness result"
            )
            continue
        status = str(row["freshness_status"]).upper()
        if status in BLOCKING_FRESHNESS_STATUSES or int(row["blocks_publication"] or 0) == 1:
            if as_of is not None:
                errors.append(
                    f"Required source {row['policy_source_id']} freshness for requested as-of {as_of} is {status} and blocks publication (blocks_publication={int(row['blocks_publication'] or 0)})"
                )
                continue
            errors.append(
                f"Required source {row['policy_source_id']} freshness is {status} and blocks publication"
            )
    return errors


def validate_policy_gate_results(db_path: Path, *, strict: bool = False) -> list[str]:
    del strict
    errors = validate_policy_registry_schema(db_path)
    if errors:
        return errors
    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        active = _active_policy(conn)
        if active is None:
            return [f"Expected exactly one ACTIVE {POLICY_NAMESPACE} policy for gate validation"]
        for gate_name in sorted(REQUIRED_C3_GATE_NAMES):
            row = conn.execute(
                """
                SELECT *
                FROM policy_gate_result
                WHERE policy_version_id=? AND gate_name=?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (active["policy_version_id"], gate_name),
            ).fetchone()
            if row is None:
                errors.append(f"Required C3 gate result missing: {gate_name}")
                continue
            status = str(row["status"]).upper()
            if status not in {"PASS", "WARN"} or int(row["blocks_owner_publication"] or 0) == 1:
                errors.append(
                    f"Required C3 gate {gate_name} is {status} and blocks owner publication"
                )
    return errors


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def validate_exception_queue_db(db_path: Path, *, strict: bool = False) -> list[str]:
    errors = validate_policy_registry_schema(db_path)
    if errors:
        return errors
    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT exception_id, severity, status, owner, recommended_action,
                   evidence_paths_json
            FROM exception_queue
            WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'PENDING', 'BLOCKED')
              AND LOWER(COALESCE(severity, '')) IN ('critical', 'high')
            ORDER BY exception_id
            """
        ).fetchall()
    for row in rows:
        prefix = f"exception_queue[{row['exception_id']}]"
        if not str(row["owner"] or "").strip():
            errors.append(f"{prefix} owner is required")
        if not str(row["recommended_action"] or "").strip():
            errors.append(f"{prefix} recommended_action is required")
        if not _json_list(row["evidence_paths_json"]):
            errors.append(f"{prefix} evidence_paths_json must be a non-empty list")
    return errors


def validate_manual_decision_approvals(db_path: Path, *, strict: bool = False) -> list[str]:
    del strict
    errors = validate_policy_registry_schema(db_path)
    if errors:
        return errors
    with connect_readonly(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT approval_id, domain, request_type, decision, approved_by,
                   approved_at, evidence_paths_json, cannot_override_publication_gate
            FROM manual_decision_approval
            ORDER BY approval_id
            """
        ).fetchall()
    for row in rows:
        decision = str(row["decision"] or "").upper()
        if decision != "APPROVED":
            continue
        prefix = f"manual_decision_approval[{row['approval_id']}]"
        if not str(row["approved_by"] or "").strip() or not str(row["approved_at"] or "").strip():
            errors.append(f"{prefix} approved decisions require approved_by and approved_at")
        if not _json_list(row["evidence_paths_json"]):
            errors.append(f"{prefix} approved decisions require evidence_paths_json")
        if int(row["cannot_override_publication_gate"] or 0) == 0:
            errors.append(
                f"{prefix} cannot override publication gates; agents may not waive publication blockers"
            )
    return errors
