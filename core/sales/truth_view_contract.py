"""Pin canonical sales truth views to the exact runtime that builds them.

Publication manifests must never be built from stored SQLite views that differ
from the views the applier would install.  This module derives the expected
definitions on a disposable coherent copy, records code and SQL hashes, and
provides fail-closed guards for manifest build, pre-apply, and post-refresh.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any

from core.sales.publication_binding import install_publication_binding_schema
from core.sales.truth_views import ensure_sales_truth_views


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA_VERSION = "sales_truth_view_runtime_contract_v1"
DEFINITION_VERSION = "install-binding-schema-then-ensure-sales-truth-views-v1"
TRACKED_VIEWS = (
    "view_sales_line_truth_unbound",
    "view_sales_publication_binding_validation",
    "view_sales_line_truth",
    "view_sales_daily_truth",
    "view_sales_line_reference",
    "view_sales_daily_reference",
)


class TruthViewContractError(RuntimeError):
    """Raised when stored truth views do not exactly match reviewed runtime."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)


def _capture_view_sql(conn: sqlite3.Connection) -> dict[str, str | None]:
    rows = {
        str(name): (None if sql is None else str(sql))
        for name, sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='view'"
        ).fetchall()
    }
    return {name: rows.get(name) for name in TRACKED_VIEWS}


def _sql_hash(sql: str | None) -> str | None:
    return None if sql is None else _sha256_bytes(sql.encode("utf-8"))


def _relative_source_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError as exc:
        raise TruthViewContractError(
            f"runtime source file is outside project root: {path}"
        ) from exc


def _code_pin() -> dict[str, Any]:
    truth_file = Path(inspect.getsourcefile(ensure_sales_truth_views) or "").resolve()
    binding_file = Path(
        inspect.getsourcefile(install_publication_binding_schema) or ""
    ).resolve()
    if not truth_file.is_file() or not binding_file.is_file():
        raise TruthViewContractError("runtime view-builder source files are unavailable")
    return {
        "definition_version": DEFINITION_VERSION,
        "truth_views_module_path": _relative_source_path(truth_file),
        "truth_views_module_sha256": _sha256_file(truth_file),
        "ensure_sales_truth_views_source_sha256": _sha256_bytes(
            inspect.getsource(ensure_sales_truth_views).encode("utf-8")
        ),
        "publication_binding_module_path": _relative_source_path(binding_file),
        "publication_binding_module_sha256": _sha256_file(binding_file),
        "install_publication_binding_schema_source_sha256": _sha256_bytes(
            inspect.getsource(install_publication_binding_schema).encode("utf-8")
        ),
    }


def _runtime_expected_view_sql(
    db_path: Path,
    *,
    probe_dir: Path,
) -> dict[str, str | None]:
    """Derive runtime SQL on an automatically deleted coherent DB copy."""

    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_path = probe_dir / f".truth_view_runtime_probe_{uuid.uuid4().hex}.db"
    sidecars = [
        Path(str(probe_path) + suffix)
        for suffix in ("-wal", "-shm", "-journal")
    ]
    source = _connect_read_only(db_path)
    target = sqlite3.connect(str(probe_path))
    try:
        source.backup(target)
        install_publication_binding_schema(target)
        ensure_sales_truth_views(target)
        target.commit()
        integrity = str(target.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise TruthViewContractError(
                f"runtime view probe integrity_check failed: {integrity}"
            )
        result = _capture_view_sql(target)
        missing = [name for name, sql in result.items() if sql is None]
        if missing:
            raise TruthViewContractError(
                f"runtime view builder omitted tracked views: {missing}"
            )
        return result
    finally:
        target.close()
        source.close()
        probe_path.unlink(missing_ok=True)
        for sidecar in sidecars:
            sidecar.unlink(missing_ok=True)


def build_truth_view_contract(
    db_path: Path,
    *,
    probe_dir: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic stored-versus-runtime truth-view contract."""

    db_path = db_path.resolve()
    conn = _connect_read_only(db_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise TruthViewContractError(
                f"source DB integrity_check failed: {integrity}"
            )
        stored = _capture_view_sql(conn)
    finally:
        conn.close()

    if probe_dir is None:
        with tempfile.TemporaryDirectory(prefix="ab_truth_view_contract_") as tmp:
            expected = _runtime_expected_view_sql(db_path, probe_dir=Path(tmp))
    else:
        expected = _runtime_expected_view_sql(db_path, probe_dir=probe_dir)

    views: dict[str, dict[str, Any]] = {}
    mismatches: list[str] = []
    for name in TRACKED_VIEWS:
        stored_hash = _sql_hash(stored[name])
        expected_hash = _sql_hash(expected[name])
        matches = stored[name] is not None and stored_hash == expected_hash
        if not matches:
            mismatches.append(name)
        views[name] = {
            "stored_present": stored[name] is not None,
            "stored_sql_sha256": stored_hash,
            "stored_sql_bytes": (
                0 if stored[name] is None else len(stored[name].encode("utf-8"))
            ),
            "runtime_expected_present": expected[name] is not None,
            "runtime_expected_sql_sha256": expected_hash,
            "runtime_expected_sql_bytes": (
                0 if expected[name] is None else len(expected[name].encode("utf-8"))
            ),
            "matches_runtime": matches,
        }

    stored_hash_rows = [
        {"view_name": name, "sql_sha256": views[name]["stored_sql_sha256"]}
        for name in TRACKED_VIEWS
    ]
    expected_hash_rows = [
        {
            "view_name": name,
            "sql_sha256": views[name]["runtime_expected_sql_sha256"],
        }
        for name in TRACKED_VIEWS
    ]
    body: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "runtime_code": _code_pin(),
        "tracked_views": list(TRACKED_VIEWS),
        "views": views,
        "stored_view_set_sha256": canonical_sha256(stored_hash_rows),
        "runtime_expected_view_set_sha256": canonical_sha256(expected_hash_rows),
        "mismatched_views": mismatches,
        "compatible": not mismatches,
        "manifest_regeneration_required": bool(mismatches),
    }
    body["contract_sha256"] = canonical_sha256(body)
    return body


def _validate_internal_contract_hash(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise TruthViewContractError(
            "unsupported truth-view contract schema; regenerate manifest"
        )
    if contract.get("tracked_views") != list(TRACKED_VIEWS):
        raise TruthViewContractError(
            "truth-view contract tracked-view set mismatch; regenerate manifest"
        )
    expected = str(contract.get("contract_sha256") or "")
    body = dict(contract)
    body.pop("contract_sha256", None)
    observed = canonical_sha256(body)
    if not expected or observed != expected:
        raise TruthViewContractError(
            "truth-view contract internal hash mismatch; regenerate manifest"
        )


def require_manifest_build_compatible(contract: dict[str, Any]) -> None:
    """Refuse to freeze rows from legacy or drifted stored views."""

    _validate_internal_contract_hash(contract)
    if not bool(contract.get("compatible")):
        names = ",".join(str(item) for item in contract.get("mismatched_views") or [])
        raise TruthViewContractError(
            "stored sales truth views differ from exact runtime ensure definition; "
            f"refresh copied baseline and regenerate manifest (mismatches={names})"
        )


def require_apply_contract_match(
    db_path: Path,
    *,
    pinned_contract: dict[str, Any],
    probe_dir: Path | None = None,
) -> dict[str, Any]:
    """Require current runtime/stored SQL to match the reviewed manifest pin."""

    _validate_internal_contract_hash(pinned_contract)
    current = build_truth_view_contract(db_path, probe_dir=probe_dir)
    require_manifest_build_compatible(current)
    if current["contract_sha256"] != pinned_contract.get("contract_sha256"):
        raise TruthViewContractError(
            "current runtime/stored truth-view contract differs from reviewed "
            "manifest contract; regenerate and re-review manifest before apply"
        )
    return current


def require_post_refresh_stored_sql(
    conn: sqlite3.Connection,
    *,
    pinned_contract: dict[str, Any],
) -> None:
    """Verify in-transaction stored SQL without creating another probe."""

    _validate_internal_contract_hash(pinned_contract)
    observed = _capture_view_sql(conn)
    mismatches = []
    for name in TRACKED_VIEWS:
        expected_hash = pinned_contract["views"][name][
            "runtime_expected_sql_sha256"
        ]
        if _sql_hash(observed[name]) != expected_hash:
            mismatches.append(name)
    if mismatches:
        raise TruthViewContractError(
            "post-refresh stored truth-view SQL differs from manifest pin: "
            + ",".join(mismatches)
        )
