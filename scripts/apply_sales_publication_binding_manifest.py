#!/usr/bin/env python3
"""Validate or apply an exact publication binding to a disposable copied DB."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.publication_binding import (  # noqa: E402
    HEADER_TABLE,
    LINE_TABLE,
    install_publication_binding_schema,
)
from core.sales.truth_views import ensure_sales_truth_views  # noqa: E402
from core.sales.truth_view_contract import (  # noqa: E402
    TruthViewContractError,
    require_apply_contract_match,
    require_post_refresh_stored_sql,
)
from core.sales.publication_prerequisites import (  # noqa: E402
    MinimalPublicationSchemaError,
    require_matching_minimal_publication_schema,
)
from scripts.build_sales_publication_binding_manifest import (  # noqa: E402
    OLD_PUBLIC_COLUMNS,
    PublicationBindingManifestError,
    SCHEMA_VERSION,
    _multiset_hash,
    build_manifest,
    canonical_sha256,
    sha256_file,
)


WRITE_ENV_GATE = "ENABLE_COPIED_SALES_PUBLICATION_BINDING_WRITE"
PRODUCTION_DB = (PROJECT_ROOT / "db" / "app.db").resolve()
BINDING_MUTATION_TABLES = frozenset((HEADER_TABLE, LINE_TABLE))


class PublicationBindingApplyError(RuntimeError):
    pass


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicationBindingApplyError("manifest must be a JSON object")
    expected = str(payload.get("manifest_sha256") or "")
    body = dict(payload)
    body.pop("manifest_sha256", None)
    observed = canonical_sha256(body)
    if not expected or observed != expected:
        raise PublicationBindingApplyError(
            f"manifest internal hash mismatch: expected {expected or 'missing'}, observed {observed}"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PublicationBindingApplyError(
            f"unsupported manifest schema: expected {SCHEMA_VERSION}, "
            f"observed {payload.get('schema_version') or 'missing'}"
        )
    if not isinstance(payload.get("truth_view_runtime_contract"), dict):
        raise PublicationBindingApplyError(
            "manifest lacks required truth_view_runtime_contract"
        )
    if not isinstance(payload.get("minimal_publication_schema_contract"), dict):
        raise PublicationBindingApplyError(
            "manifest lacks required minimal_publication_schema_contract"
        )
    return payload


def _integrity(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def _logical_hash(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
    if not columns:
        return canonical_sha256([])
    rows = [dict(zip(columns, row)) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    return canonical_sha256(sorted(rows, key=lambda row: canonical_sha256(row)))


def _logical_hash_excluding_binding_id(
    conn: sqlite3.Connection,
    table: str,
    binding_id: str,
) -> str:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
    rows = [
        dict(zip(columns, row))
        for row in conn.execute(
            f"SELECT * FROM {table} WHERE binding_id<>?",
            (binding_id,),
        ).fetchall()
    ]
    return canonical_sha256(sorted(rows, key=lambda row: canonical_sha256(row)))


def _assert_table_count_contract(
    *,
    table_counts_before: dict[str, int],
    table_counts_after: dict[str, int],
    binding_table_counts_before: dict[str, int],
    target_binding_counts_after: dict[str, int],
    expected_target_count: int,
) -> None:
    unexpected_new = (
        set(table_counts_after)
        - set(table_counts_before)
        - BINDING_MUTATION_TABLES
    )
    if unexpected_new:
        raise PublicationBindingApplyError(
            f"unexpected additive tables: {sorted(unexpected_new)}"
        )
    for name, count in table_counts_before.items():
        if name in BINDING_MUTATION_TABLES:
            continue
        if table_counts_after.get(name) != count:
            raise PublicationBindingApplyError(
                f"pre-existing table count changed: {name}"
            )
    expected_global = {
        HEADER_TABLE: binding_table_counts_before[HEADER_TABLE] + 1,
        LINE_TABLE: binding_table_counts_before[LINE_TABLE] + expected_target_count,
    }
    observed_global = {
        table: table_counts_after.get(table, -1)
        for table in BINDING_MUTATION_TABLES
    }
    if observed_global != expected_global:
        raise PublicationBindingApplyError(
            "binding table count delta is not exact: "
            f"expected {expected_global}, observed {observed_global}"
        )
    expected_target = {
        HEADER_TABLE: 1,
        LINE_TABLE: expected_target_count,
    }
    if target_binding_counts_after != expected_target:
        raise PublicationBindingApplyError(
            "target binding counts are not exact: "
            f"expected {expected_target}, observed {target_binding_counts_after}"
        )


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}


def _sidecars(path: Path) -> list[Path]:
    return [candidate for candidate in (Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + "-journal")) if candidate.exists()]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _post_commit_barrier(path: Path) -> None:
    if _integrity(path).lower() != "ok":
        raise PublicationBindingApplyError("post-commit integrity_check failed")


def _restore_verified_backup(
    *, target: Path, backup: Path, expected_sha256: str
) -> str:
    sidecars = _sidecars(target)
    if sidecars:
        raise PublicationBindingApplyError(
            "cannot restore copied DB while SQLite sidecars exist: "
            + ", ".join(str(path) for path in sidecars)
        )
    shutil.copy2(backup, target)
    restored_sha = sha256_file(target)
    if restored_sha != expected_sha256 or _integrity(target).lower() != "ok":
        raise PublicationBindingApplyError(
            "publication binding restore did not reproduce exact copied preimage"
        )
    return restored_sha


def _assert_copied_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PRODUCTION_DB:
        raise PublicationBindingApplyError("refusing canonical production DB")
    if PRODUCTION_DB.exists() and os.path.samefile(resolved, PRODUCTION_DB):
        raise PublicationBindingApplyError("refusing hardlink or alias to canonical production DB")
    if "/runs/tmux_orchestration/" not in str(resolved):
        raise PublicationBindingApplyError("copied apply target must be inside runs/tmux_orchestration")
    existing = _sidecars(resolved)
    if existing:
        raise PublicationBindingApplyError(
            "refusing copied apply while SQLite sidecars exist: " + ", ".join(map(str, existing))
        )


def _rebuild_manifest(manifest: dict[str, Any], db_path: Path) -> dict[str, Any]:
    return build_manifest(
        db_path=db_path,
        order_id=str(manifest["order_id"]),
        store_code=str(manifest["store_code"]),
        source_sidecar_manifest_path=Path(manifest["source_sidecar_manifest_path"]),
        source_proof_path=Path(manifest["source_proof_file_path"]),
        promotion_manifest_path=Path(manifest["promotion_manifest_path"]),
        promotion_apply_report_path=Path(manifest["promotion_apply_report_path"]),
        api_header_path=Path(manifest["api_header_path"]),
    )


def _binding_postimages(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    manifest_file_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    anchor = manifest["anchor_preimage"]
    header = {
        "binding_id": manifest["binding_id"],
        "order_id": manifest["order_id"],
        "store_code": manifest["store_code"],
        "binding_status": "VALID",
        "active_flag": 1,
        "provisional_flag": int(bool(manifest["provisional_flag"])),
        "publication_effective_date": manifest["publication_effective_date"],
        "terminal_date_semantics": manifest["terminal_date_semantics"],
        "expected_line_count": manifest["expected_line_count"],
        "external_evidence_validated": 1,
        "copied_db_pre_sha256": manifest["copied_db_sha256"],
        "canonical_hash_version": manifest["canonical_hash_version"],
        "economics_policy_sha256": manifest["economics_policy_sha256"],
        "originating_manifest_path": str(manifest_path.resolve()),
        "originating_manifest_file_sha256": manifest_file_sha256,
        "originating_manifest_internal_sha256": manifest["manifest_sha256"],
        "source_proof_file_path": manifest["source_proof_file_path"],
        "source_proof_file_sha256": manifest["source_proof_file_sha256"],
        "source_proof_key": manifest["source_proof_key"],
        "source_sidecar_manifest_path": manifest["source_sidecar_manifest_path"],
        "source_sidecar_manifest_file_sha256": manifest["source_sidecar_manifest_file_sha256"],
        "source_sidecar_manifest_internal_sha256": manifest["source_sidecar_manifest_internal_sha256"],
        "promotion_manifest_path": manifest["promotion_manifest_path"],
        "promotion_manifest_file_sha256": manifest["promotion_manifest_file_sha256"],
        "promotion_manifest_internal_sha256": manifest["promotion_manifest_internal_sha256"],
        "promotion_apply_report_path": manifest["promotion_apply_report_path"],
        "promotion_apply_report_sha256": manifest["promotion_apply_report_sha256"],
        "api_header_path": manifest["api_header_path"],
        "api_header_sha256": manifest["api_header_sha256"],
        "terminal_evidence_sha256": manifest["terminal_evidence_sha256"],
        "workbook_anchor_preimage_sha256": manifest["anchor_preimage_sha256"],
        "unbound_selected_multiset_sha256": manifest["unbound_selected_multiset_sha256"],
        "source_line_multiset_sha256": manifest["source_rows_multiset_sha256"],
        "anchor_sale_date": anchor["sale_date"],
        "anchor_quantity": anchor["quantity"],
        "anchor_net_rev_kzt": anchor["net_rev_kzt"],
        "anchor_total_price_kzt": anchor["total_price_kzt"],
        "anchor_source_file": anchor.get("source_file"),
        "anchor_updated_at": anchor.get("updated_at"),
    }
    lines: list[dict[str, Any]] = []
    for target in manifest["targets"]:
        source = target["source_row_preimage"]
        unbound = target["unbound_selected_preimage"]
        publication = target["publication"]
        line = {
            "binding_id": manifest["binding_id"],
            "line_ordinal": target["line_ordinal"],
            "source_table": "sales_fact_v2",
            "source_sale_id": target["sale_id"],
            "source_entry_id": source["source_entry_id"],
            "line_identity_key": source["line_identity_key"],
            "source_order_id": source["order_id"],
            "source_store_code": source["store_code"],
            "source_order_date": source["order_date"],
            "source_sku_key": source["sku_key"],
            "source_sku_id": source["sku_id"],
            "source_my_size": source["my_size"],
            "source_quantity": source["quantity"],
            "source_sell_price_kzt": source["sell_price_kzt"],
            "source_delivery_fee": source["delivery_fee"],
            "source_cogs_kzt": source.get("cogs"),
            "source_net_rev_kzt": source["net_rev"],
            "source_profit_kzt": source.get("profit"),
            "source_status": source["status"],
            "source_return_flag": source["return_flag"],
            "source_file": source.get("source_file"),
            "source_kaspi_article": source.get("kaspi_article"),
            "source_row_preimage_sha256": target["source_row_preimage_sha256"],
            "entry_evidence_sha256": target["entry_evidence_sha256"],
            "source_line_proof_sha256": target["source_line_proof_sha256"],
            "promotion_target_sha256": target["promotion_target_sha256"],
            "unbound_sale_date": unbound["sale_date"],
            "unbound_units": unbound["units"],
            "unbound_net_rev_kzt": unbound["net_rev_kzt"],
            "publication_sale_date": publication["sale_date"],
            "publication_units": publication["units"],
            "publication_net_rev_kzt": publication["net_rev_kzt"],
        }
        lines.append(line)
    return header, lines


def _insert_binding(
    conn: sqlite3.Connection,
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    manifest_file_sha256: str,
) -> None:
    header, lines = _binding_postimages(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_file_sha256=manifest_file_sha256,
    )
    columns = list(header)
    conn.execute(
        f"INSERT INTO {HEADER_TABLE} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        [header[column] for column in columns],
    )
    for line in lines:
        columns = list(line)
        conn.execute(
            f"INSERT INTO {LINE_TABLE} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [line[column] for column in columns],
        )


def _validate_external_evidence(manifest: dict[str, Any]) -> None:
    for path_field, hash_field in (
        ("source_sidecar_manifest_path", "source_sidecar_manifest_file_sha256"),
        ("source_proof_file_path", "source_proof_file_sha256"),
        ("promotion_manifest_path", "promotion_manifest_file_sha256"),
        ("promotion_apply_report_path", "promotion_apply_report_sha256"),
        ("api_header_path", "api_header_sha256"),
    ):
        path = Path(str(manifest[path_field]))
        if not path.is_file() or sha256_file(path) != str(manifest[hash_field]):
            raise PublicationBindingApplyError(f"external evidence drift: {path}")
    for item in manifest.get("economics_policy_files") or []:
        path = Path(str(item.get("path") or ""))
        if not path.is_file() or sha256_file(path) != str(item.get("sha256") or ""):
            raise PublicationBindingApplyError(f"economics policy drift: {path}")


def _exact_applied_state(
    *,
    db_path: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if HEADER_TABLE not in tables or LINE_TABLE not in tables:
            return None
        manifest_file_sha = sha256_file(manifest_path)
        expected_header, expected_lines = _binding_postimages(
            manifest=manifest,
            manifest_path=manifest_path,
            manifest_file_sha256=manifest_file_sha,
        )
        header_row = conn.execute(
            f"SELECT * FROM {HEADER_TABLE} WHERE binding_id=?",
            (manifest["binding_id"],),
        ).fetchone()
        if header_row is None:
            return None
        for key, expected in expected_header.items():
            if header_row[key] != expected:
                raise PublicationBindingApplyError(
                    f"partial/drifted applied binding header field {key}: {header_row[key]!r} != {expected!r}"
                )
        line_rows = conn.execute(
            f"SELECT * FROM {LINE_TABLE} WHERE binding_id=? ORDER BY line_ordinal",
            (manifest["binding_id"],),
        ).fetchall()
        if len(line_rows) != len(expected_lines):
            raise PublicationBindingApplyError("partial applied binding line set")
        for row, expected_line in zip(line_rows, expected_lines):
            for key, expected in expected_line.items():
                if row[key] != expected:
                    raise PublicationBindingApplyError(
                        f"drifted applied binding line {expected_line['line_ordinal']} field {key}"
                    )
        validation_row = conn.execute(
            "SELECT * FROM view_sales_publication_binding_validation WHERE binding_id=?",
            (manifest["binding_id"],),
        ).fetchone()
        if validation_row is None:
            raise PublicationBindingApplyError("applied binding validation row is missing")
        validation = dict(validation_row)
        if validation.get("validation_status") != "VALID_ACTIVE" or int(validation.get("publication_binding_usable") or 0) != 1:
            raise PublicationBindingApplyError(f"applied binding is not valid: {validation}")
        selected = [
            dict(row)
            for row in conn.execute(
                f"SELECT {','.join(OLD_PUBLIC_COLUMNS)} FROM view_sales_line_truth "
                "WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?",
                (manifest["order_id"], manifest["store_code"]),
            ).fetchall()
        ]
        selected_hash = _multiset_hash(
            selected,
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        )
        if selected_hash != manifest["expected_bound_old_columns_multiset_sha256"]:
            raise PublicationBindingApplyError("applied binding selected target hash drift")
        return {"validation": validation, "target_old_columns_multiset_sha256": selected_hash}
    finally:
        conn.close()


def apply_manifest(
    *,
    db_path: Path,
    manifest_path: Path,
    output_path: Path,
    backup_dir: Path | None,
    apply: bool,
    expected_pre_sha256: str | None,
    expected_target_count: int,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    manifest_path = manifest_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise PublicationBindingApplyError(f"output path already exists: {output_path}")
    manifest = _load_manifest(manifest_path)
    _assert_copied_target(db_path)
    prerequisite_conn = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True,
    )
    try:
        minimal_publication_schema_readback = (
            require_matching_minimal_publication_schema(
                prerequisite_conn,
                pinned_contract=manifest[
                    "minimal_publication_schema_contract"
                ],
            )
        )
    except MinimalPublicationSchemaError as exc:
        raise PublicationBindingApplyError(str(exc)) from exc
    finally:
        prerequisite_conn.close()
    try:
        truth_view_contract_readback = require_apply_contract_match(
            db_path,
            pinned_contract=manifest["truth_view_runtime_contract"],
        )
    except TruthViewContractError as exc:
        raise PublicationBindingApplyError(str(exc)) from exc
    _validate_external_evidence(manifest)
    pre_sha = sha256_file(db_path)
    idempotent_state = None
    if pre_sha != str(manifest.get("copied_db_sha256")):
        idempotent_state = _exact_applied_state(
            db_path=db_path,
            manifest=manifest,
            manifest_path=manifest_path,
        )
    if pre_sha != str(manifest.get("copied_db_sha256")) and idempotent_state is None:
        raise PublicationBindingApplyError(
            f"copied DB SHA mismatch: manifest {manifest.get('copied_db_sha256')}, observed {pre_sha}"
        )
    if expected_pre_sha256 and pre_sha != expected_pre_sha256 and idempotent_state is None:
        raise PublicationBindingApplyError(
            f"--expected-pre-sha256 mismatch: expected {expected_pre_sha256}, observed {pre_sha}"
        )
    targets = manifest.get("targets") or []
    if len(targets) != expected_target_count or int(manifest.get("expected_line_count") or 0) != expected_target_count:
        raise PublicationBindingApplyError(
            f"expected {expected_target_count} targets, manifest has {len(targets)}"
        )
    rebuilt = None if idempotent_state is not None else _rebuild_manifest(manifest, db_path)
    if rebuilt is not None and rebuilt["manifest_sha256"] != manifest["manifest_sha256"]:
        raise PublicationBindingApplyError(
            "fresh manifest rebuild differs from reviewed manifest: "
            f"{rebuilt['manifest_sha256']} != {manifest['manifest_sha256']}"
        )

    report: dict[str, Any] = {
        "status": "PASS",
        "operation": "COPIED_DB_EXACT_SALES_PUBLICATION_BINDING",
        "apply_requested": apply,
        "production_apply": False,
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": sha256_file(manifest_path),
        "manifest_internal_sha256": manifest["manifest_sha256"],
        "truth_view_runtime_contract_sha256": truth_view_contract_readback[
            "contract_sha256"
        ],
        "minimal_publication_schema_contract_sha256": (
            minimal_publication_schema_readback["contract_sha256"]
        ),
        "target_count": len(targets),
        "rows_inserted": 0,
        "idempotent_replay": idempotent_state is not None,
    }
    if idempotent_state is not None:
        if apply and os.environ.get(WRITE_ENV_GATE) != "1":
            raise PublicationBindingApplyError(f"{WRITE_ENV_GATE}=1 is required for copied apply replay")
        report.update(idempotent_state)
        report["post_sha256"] = pre_sha
        _write_json_atomic(output_path, report)
        return report
    if not apply:
        _write_json_atomic(output_path, report)
        return report
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise PublicationBindingApplyError(f"{WRITE_ENV_GATE}=1 is required for copied apply")
    if backup_dir is None:
        raise PublicationBindingApplyError("--backup-dir is required with --apply")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{db_path.stem}.before_publication_binding_{pre_sha[:12]}_{stamp}.db"
    rollback_path = backup_dir / f"ROLLBACK_{stamp}.json"
    if backup_path.exists() or rollback_path.exists():
        raise PublicationBindingApplyError("backup or rollback path collision")
    shutil.copy2(db_path, backup_path)
    backup_sha = sha256_file(backup_path)
    if backup_sha != pre_sha or _integrity(backup_path).lower() != "ok":
        raise PublicationBindingApplyError("byte-valid copied DB backup verification failed")
    report.update({"backup_path": str(backup_path), "backup_sha256": backup_sha})

    rollback: dict[str, Any] = {
        "operation": "REPLACE_DISPOSABLE_COPY_WITH_BYTE_VALID_PREWRITE_BACKUP",
        "status": "PREPARED_BEFORE_TRANSACTION",
        "target_path": str(db_path),
        "target_pre_sha256": pre_sha,
        "target_post_sha256": None,
        "backup_path": str(backup_path),
        "backup_sha256": backup_sha,
        "restore_verified": False,
        "command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}",
    }
    _write_json_atomic(rollback_path, rollback)
    report["rollback_path"] = str(rollback_path)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    transaction_error: BaseException | None = None
    try:
        table_counts_before = _table_counts(conn)
        protected_tables = [
            name
            for name in (
                "fact_sales_workbook_anchor",
                "sales_fact_v2",
                "fact_cashflow_events",
                "stock_ledger",
                "fact_orders_kaspi",
                "fact_order_entries_kaspi",
            )
            if name in table_counts_before
        ]
        protected_hashes_before = {name: _logical_hash(conn, name) for name in protected_tables}
        conn.execute("BEGIN IMMEDIATE")
        install_publication_binding_schema(conn)
        binding_table_counts_before = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in BINDING_MUTATION_TABLES
        }
        binding_non_target_hashes_before = {
            table: _logical_hash(conn, table)
            for table in BINDING_MUTATION_TABLES
        }
        existing_header = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {HEADER_TABLE} WHERE binding_id=?",
                (manifest["binding_id"],),
            ).fetchone()[0]
        )
        existing_lines = int(
            conn.execute(
                f"SELECT COUNT(*) FROM {LINE_TABLE} WHERE binding_id=?",
                (manifest["binding_id"],),
            ).fetchone()[0]
        )
        if existing_header or existing_lines:
            raise PublicationBindingApplyError("binding_id already exists before first apply")
        _insert_binding(
            conn,
            manifest=manifest,
            manifest_path=manifest_path,
            manifest_file_sha256=report["manifest_file_sha256"],
        )
        ensure_sales_truth_views(conn)
        try:
            require_post_refresh_stored_sql(
                conn,
                pinned_contract=manifest["truth_view_runtime_contract"],
            )
        except TruthViewContractError as exc:
            raise PublicationBindingApplyError(str(exc)) from exc
        try:
            require_matching_minimal_publication_schema(
                conn,
                pinned_contract=manifest[
                    "minimal_publication_schema_contract"
                ],
            )
        except MinimalPublicationSchemaError as exc:
            raise PublicationBindingApplyError(str(exc)) from exc
        validation = dict(
            conn.execute(
                "SELECT * FROM view_sales_publication_binding_validation WHERE binding_id=?",
                (manifest["binding_id"],),
            ).fetchone()
        )
        if validation.get("validation_status") != "VALID_ACTIVE" or int(validation.get("publication_binding_usable") or 0) != 1:
            raise PublicationBindingApplyError(f"binding validation failed: {validation}")
        selected_rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT {','.join(OLD_PUBLIC_COLUMNS)}
                FROM view_sales_line_truth
                WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
                ORDER BY CAST(source_row_id AS INTEGER)
                """,
                (manifest["order_id"], manifest["store_code"]),
            ).fetchall()
        ]
        selected_hash = _multiset_hash(
            selected_rows,
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        )
        if len(selected_rows) != expected_target_count or selected_hash != manifest["expected_bound_old_columns_multiset_sha256"]:
            raise PublicationBindingApplyError(
                f"bound target readback mismatch: count={len(selected_rows)}, hash={selected_hash}"
            )
        target_keys = {
            (
                str(target["source_row_preimage"]["order_id"]),
                str(target["source_row_preimage"]["store_code"]).upper(),
                "sales_fact_v2",
                str(target["source_row_preimage"]["sku_id"]),
                str(target["source_row_preimage"]["my_size"]),
            )
            for target in targets
        }
        all_rows = [
            dict(row)
            for row in conn.execute(f"SELECT {','.join(OLD_PUBLIC_COLUMNS)} FROM view_sales_line_truth").fetchall()
        ]
        non_target = [
            row
            for row in all_rows
            if (
                str(row["order_id"]),
                str(row["store_code"]).upper(),
                str(row["source_table"]),
                str(row["source_sku_id"]),
                str(row["my_size"]),
            )
            not in target_keys
        ]
        non_target_hash = _multiset_hash(
            non_target,
            sort_fields=(
                "order_id",
                "store_code",
                "source_table",
                "source_sku_key",
                "source_sku_id",
                "my_size",
                "sale_date",
            ),
        )
        if len(non_target) != int(manifest["non_target_old_columns_count"]) or non_target_hash != manifest["non_target_old_columns_multiset_sha256"]:
            raise PublicationBindingApplyError(
                f"non-target selected view drift: count={len(non_target)}, hash={non_target_hash}"
            )
        protected_hashes_after = {name: _logical_hash(conn, name) for name in protected_tables}
        if protected_hashes_after != protected_hashes_before:
            raise PublicationBindingApplyError("protected business-table logical hash changed")
        table_counts_after = _table_counts(conn)
        target_binding_counts_after = {
            HEADER_TABLE: int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {HEADER_TABLE} WHERE binding_id=?",
                    (manifest["binding_id"],),
                ).fetchone()[0]
            ),
            LINE_TABLE: int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {LINE_TABLE} WHERE binding_id=?",
                    (manifest["binding_id"],),
                ).fetchone()[0]
            ),
        }
        binding_non_target_hashes_after = {
            table: _logical_hash_excluding_binding_id(
                conn,
                table,
                str(manifest["binding_id"]),
            )
            for table in BINDING_MUTATION_TABLES
        }
        if binding_non_target_hashes_after != binding_non_target_hashes_before:
            raise PublicationBindingApplyError(
                "pre-existing non-target binding rows changed"
            )
        _assert_table_count_contract(
            table_counts_before=table_counts_before,
            table_counts_after=table_counts_after,
            binding_table_counts_before=binding_table_counts_before,
            target_binding_counts_after=target_binding_counts_after,
            expected_target_count=expected_target_count,
        )
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise PublicationBindingApplyError(f"post-apply integrity_check failed: {integrity}")
        conn.execute("COMMIT")
    except BaseException as exc:
        transaction_error = exc
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    finally:
        conn.close()
    if transaction_error is not None:
        try:
            restored_sha = _restore_verified_backup(
                target=db_path,
                backup=backup_path,
                expected_sha256=pre_sha,
            )
        except BaseException as restore_exc:
            rollback.update(
                {
                    "status": "RESTORE_FAILED_AFTER_TRANSACTION_FAILURE",
                    "failure": f"{type(transaction_error).__name__}: {transaction_error}",
                    "restore_failure": f"{type(restore_exc).__name__}: {restore_exc}",
                }
            )
            try:
                _write_json_atomic(rollback_path, rollback)
            except Exception:
                pass
            raise PublicationBindingApplyError(
                "AMBIGUOUS: publication transaction failed and exact restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
        rollback.update(
            {
                "status": "TRANSACTION_ROLLED_BACK_AND_PREIMAGE_RESTORED",
                "failure": f"{type(transaction_error).__name__}: {transaction_error}",
                "restore_verified": True,
                "restored_sha256": restored_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        raise transaction_error

    try:
        _post_commit_barrier(db_path)
        post_state = _exact_applied_state(
            db_path=db_path,
            manifest=manifest,
            manifest_path=manifest_path,
        )
        if post_state is None:
            raise PublicationBindingApplyError(
                "post-commit exact binding readback is missing"
            )
        report.update(
            {
                "rows_inserted": 1 + expected_target_count,
                "header_rows_inserted": 1,
                "line_rows_inserted": expected_target_count,
                "validation": validation,
                "target_old_columns_multiset_sha256": selected_hash,
                "non_target_old_columns_count": len(non_target),
                "non_target_old_columns_multiset_sha256": non_target_hash,
                "protected_table_hashes_before": protected_hashes_before,
                "protected_table_hashes_after": protected_hashes_after,
                "table_counts_before": table_counts_before,
                "table_counts_after": table_counts_after,
                "binding_table_counts_before": binding_table_counts_before,
                "binding_table_counts_after": {
                    table: table_counts_after[table]
                    for table in BINDING_MUTATION_TABLES
                },
                "binding_table_count_deltas": {
                    table: table_counts_after[table] - binding_table_counts_before[table]
                    for table in BINDING_MUTATION_TABLES
                },
                "target_binding_counts_after": target_binding_counts_after,
                "binding_non_target_hashes_before": binding_non_target_hashes_before,
                "binding_non_target_hashes_after": binding_non_target_hashes_after,
                "integrity_check": integrity,
                "post_commit_exact_readback": post_state,
                "post_sha256": sha256_file(db_path),
            }
        )
        rollback.update(
            {
                "status": "READY",
                "target_post_sha256": report["post_sha256"],
                "restore_verified": False,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        _write_json_atomic(output_path, report)
        return report
    except BaseException as exc:
        try:
            restored_sha = _restore_verified_backup(
                target=db_path,
                backup=backup_path,
                expected_sha256=pre_sha,
            )
        except BaseException as restore_exc:
            rollback.update(
                {
                    "status": "RESTORE_FAILED_AFTER_POST_COMMIT_FAILURE",
                    "failure": f"{type(exc).__name__}: {exc}",
                    "restore_failure": f"{type(restore_exc).__name__}: {restore_exc}",
                }
            )
            try:
                _write_json_atomic(rollback_path, rollback)
            except Exception:
                pass
            raise PublicationBindingApplyError(
                "AMBIGUOUS: publication post-commit failure and exact restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
        rollback.update(
            {
                "status": "RESTORED_AFTER_POST_COMMIT_FAILURE",
                "failure": f"{type(exc).__name__}: {exc}",
                "target_post_sha256": None,
                "restore_verified": True,
                "restored_sha256": restored_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        output_path.unlink(missing_ok=True)
        raise PublicationBindingApplyError(
            "publication post-commit verification or evidence finalization failed; "
            "copied DB restored to exact preimage"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--expected-target-count", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = apply_manifest(
            db_path=args.db,
            manifest_path=args.manifest,
            output_path=args.output,
            backup_dir=args.backup_dir,
            apply=args.apply,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_target_count=args.expected_target_count,
        )
    except (PublicationBindingApplyError, PublicationBindingManifestError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "apply_requested": report["apply_requested"], "rows_inserted": report["rows_inserted"], "post_sha256": report.get("post_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
