from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.utils.kaspi_name_core_resolver import (
    clean_str,
    iter_sku_family_candidates,
    load_active_kaspi_name_core_maps,
    normalize_offer_key,
    normalize_store_key,
    resolve_kaspi_name_core,
)
from core.utils.kaspi_order_core_overrides import load_order_name_core_overrides
from core.utils.sku_normalize import normalize_sku_key


def _map_conflicts(
    conn: sqlite3.Connection,
) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    sku_cores: dict[str, set[str]] = {}
    offer_cores: dict[tuple[str, str], set[str]] = {}
    rows = conn.execute(
        """
        SELECT store_code, kaspi_offer_name, sku_key, kaspi_name_core
        FROM dim_kaspi_article_map
        WHERE active_flag = 1
          AND kaspi_name_core IS NOT NULL
          AND TRIM(kaspi_name_core) <> ''
        """
    ).fetchall()
    for row in rows:
        core = clean_str(row["kaspi_name_core"])
        sku_key = normalize_sku_key(clean_str(row["sku_key"]))
        store = normalize_store_key(row["store_code"])
        offer = normalize_offer_key(row["kaspi_offer_name"])
        if sku_key:
            sku_cores.setdefault(sku_key, set()).add(core)
        if store and offer:
            offer_cores.setdefault((store, offer), set()).add(core)
    return sku_cores, offer_cores


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def load_exact_article_identities(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, list[str]],
]:
    """Resolve current Board rows through exact store/article evidence.

    The Board payload intentionally carries the immutable DB row id rather than
    repeating the marketplace article.  Resolve that locator back to the
    current order row, then require one unique active core for the exact
    store/article and the same canonical SKU key.  Historical family aliases
    cannot override this exact identity; conflicting exact rows remain blocked.
    """

    required_order_columns = {
        "id",
        "order_id",
        "store_code",
        "kaspi_article",
        "sku_key",
    }
    required_map_columns = {
        "id",
        "store_code",
        "kaspi_article",
        "sku_key",
        "kaspi_name_core",
        "active_flag",
    }
    if not required_order_columns.issubset(_table_columns(conn, "fact_orders_kaspi")):
        return {}, {}, {}
    if not required_map_columns.issubset(_table_columns(conn, "dim_kaspi_article_map")):
        return {}, {}, {}

    row_ids = sorted(
        {
            int(clean_str(row.get("_db_row_id")))
            for row in rows
            if clean_str(row.get("_db_row_id")).isdigit()
        }
    )
    if not row_ids:
        return {}, {}, {}

    placeholders = ",".join("?" for _ in row_ids)
    order_rows = conn.execute(
        f"""
        SELECT
            CAST(id AS TEXT) AS db_row_id,
            TRIM(COALESCE(order_id, '')) AS order_id,
            UPPER(TRIM(COALESCE(store_code, ''))) AS store_code,
            TRIM(COALESCE(kaspi_article, '')) AS kaspi_article,
            TRIM(COALESCE(sku_key, '')) AS sku_key
        FROM fact_orders_kaspi
        WHERE id IN ({placeholders})
        """,
        row_ids,
    ).fetchall()

    order_identities: dict[str, dict[str, Any]] = {}
    exact: dict[str, dict[str, Any]] = {}
    article_issues: dict[str, list[str]] = {}
    for order_row in order_rows:
        db_row_id = clean_str(order_row["db_row_id"])
        order_id = clean_str(order_row["order_id"])
        store_code = normalize_store_key(order_row["store_code"])
        article = clean_str(order_row["kaspi_article"])
        order_sku = normalize_sku_key(clean_str(order_row["sku_key"]))
        if not db_row_id:
            continue
        order_identities[db_row_id] = {
            "order_id": order_id,
            "store_code": store_code,
            "sku_key": order_sku,
            "kaspi_article": article,
        }
        issues: list[str] = []
        if not order_id:
            issues.append("DB_ROW_MISSING_ORDER_ID")
        if not store_code:
            issues.append("DB_ROW_MISSING_STORE")
        if not order_sku:
            issues.append("DB_ROW_MISSING_SKU_KEY")
        if not article:
            issues.append("MISSING_ARTICLE_IDENTITY")
        if issues:
            article_issues[db_row_id] = issues
            continue
        map_rows = conn.execute(
            """
            SELECT id, sku_key, kaspi_name_core, COALESCE(active_flag, 1) AS active_flag
            FROM dim_kaspi_article_map
            WHERE UPPER(TRIM(COALESCE(store_code, ''))) = ?
              AND UPPER(TRIM(COALESCE(kaspi_article, ''))) = UPPER(TRIM(?))
            ORDER BY id
            """,
            (store_code, article),
        ).fetchall()
        active_rows = [
            map_row
            for map_row in map_rows
            if int(map_row["active_flag"]) == 1
            and clean_str(map_row["kaspi_name_core"])
        ]
        compatible = [
            map_row
            for map_row in active_rows
            if normalize_sku_key(clean_str(map_row["sku_key"])) == order_sku
        ]
        cores = {clean_str(map_row["kaspi_name_core"]) for map_row in compatible}
        cross_store_rows = conn.execute(
            """
            SELECT store_code, sku_key, kaspi_name_core
            FROM dim_kaspi_article_map
            WHERE COALESCE(active_flag, 1) = 1
              AND UPPER(TRIM(COALESCE(kaspi_article, ''))) = UPPER(TRIM(?))
              AND TRIM(COALESCE(kaspi_name_core, '')) <> ''
            """,
            (article,),
        ).fetchall()
        cross_store_cores = {
            clean_str(map_row["kaspi_name_core"])
            for map_row in cross_store_rows
            if normalize_sku_key(clean_str(map_row["sku_key"])) == order_sku
        }
        if len(cross_store_cores) > 1:
            article_issues.setdefault(db_row_id, []).append(
                "CROSS_STORE_ARTICLE_CORE_CONFLICT"
            )
        if len(cores) == 1:
            exact[db_row_id] = {
                "core": next(iter(cores)),
                "kaspi_article": article,
                "map_ids": [int(map_row["id"]) for map_row in compatible],
            }
        elif len(cores) > 1:
            article_issues.setdefault(db_row_id, []).append(
                "AMBIGUOUS_ARTICLE_IDENTITY"
            )
        elif active_rows:
            article_issues.setdefault(db_row_id, []).append(
                "SKU_INCOMPATIBLE_ARTICLE_IDENTITY"
            )
        elif map_rows:
            article_issues.setdefault(db_row_id, []).append(
                "INACTIVE_ARTICLE_IDENTITY"
            )
        else:
            article_issues.setdefault(db_row_id, []).append(
                "MISSING_ARTICLE_IDENTITY"
            )
    return order_identities, exact, article_issues


def audit_salesraw_name_core_attribution(
    *,
    rows: list[dict[str, Any]],
    db_path: Path,
    include_safe_rows: bool = False,
) -> dict[str, Any]:
    """Fail closed when a published shipping line lacks deterministic attribution."""

    target = Path(db_path).expanduser().resolve()
    conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sku_keys = {clean_str(row.get("SKU_key")) for row in rows if clean_str(row.get("SKU_key"))}
        store_offer_pairs = {
            (clean_str(row.get("STORE_NAME")), clean_str(row.get("KASPI_OFFER_NAME")))
            for row in rows
            if clean_str(row.get("STORE_NAME")) and clean_str(row.get("KASPI_OFFER_NAME"))
        }
        maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys=sku_keys,
            store_offer_pairs=store_offer_pairs,
        )
        sku_cores, offer_cores = _map_conflicts(conn)
        (
            order_identities,
            exact_article_identities,
            article_identity_issues,
        ) = load_exact_article_identities(conn, rows)
    finally:
        conn.close()

    overrides = load_order_name_core_overrides()
    findings: list[dict[str, Any]] = []
    blocked = 0
    source_counts: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for row_index, row in enumerate(rows):
        order_id = clean_str(row.get("OrderID"))
        store_code = normalize_store_key(row.get("STORE_NAME"))
        offer_name = clean_str(row.get("KASPI_OFFER_NAME"))
        sku_key = clean_str(row.get("SKU_key"))
        displayed_core = clean_str(row.get("Kaspi_name_core"))
        db_row_id = clean_str(row.get("_db_row_id"))
        db_identity = order_identities.get(db_row_id, {})
        forced_core = overrides.get(order_id, "")
        article_identity = exact_article_identities.get(db_row_id, {})
        identity_issues: list[str] = []
        if not db_row_id:
            identity_issues.append("MISSING_DB_ROW_ID")
        elif not db_row_id.isdigit():
            identity_issues.append("INVALID_DB_ROW_ID")
        elif not db_identity:
            identity_issues.append("DB_ROW_ID_NOT_FOUND")
        else:
            if order_id != clean_str(db_identity.get("order_id")):
                identity_issues.append("DB_ROW_ORDER_ID_MISMATCH")
            if store_code != normalize_store_key(db_identity.get("store_code")):
                identity_issues.append("DB_ROW_STORE_MISMATCH")
            if normalize_sku_key(sku_key) != normalize_sku_key(db_identity.get("sku_key")):
                identity_issues.append("DB_ROW_SKU_KEY_MISMATCH")
            identity_issues.extend(article_identity_issues.get(db_row_id, []))
        exact_identity_bound = not identity_issues and bool(article_identity)
        preferred_core = (
            forced_core
            if forced_core
            else clean_str(article_identity.get("core"))
            if exact_identity_bound
            else ""
        )
        preferred_source = (
            "forced_core"
            if forced_core
            else "article_identity"
            if preferred_core
            else "preferred_core"
        )
        strict = resolve_kaspi_name_core(
            store_code=store_code,
            kaspi_offer_name=offer_name,
            sku_key=sku_key,
            maps=maps,
            preferred_core=preferred_core,
            preferred_source=preferred_source,
            allow_unsafe_fallback=False,
        )
        permissive = resolve_kaspi_name_core(
            store_code=store_code,
            kaspi_offer_name=offer_name,
            sku_key=sku_key,
            maps=maps,
            preferred_core=preferred_core,
            preferred_source=preferred_source,
            allow_unsafe_fallback=True,
        )
        issues: list[str] = list(identity_issues)
        if not preferred_core:
            conflicting_sku_candidates = [
                candidate
                for candidate in iter_sku_family_candidates(sku_key)
                if len(sku_cores.get(candidate, set())) > 1
            ]
            if conflicting_sku_candidates:
                issues.append("CONFLICTING_SKU_CORE_MAP")
            offer_pair = (store_code, normalize_offer_key(offer_name))
            if (
                strict.source not in {"sku_key", "sku_family", "forced_core", "article_identity"}
                and offer_pair[0]
                and offer_pair[1]
                and len(offer_cores.get(offer_pair, set())) > 1
            ):
                issues.append("AMBIGUOUS_STORE_OFFER_MAP")
        if not strict.safe or not strict.core:
            issues.append("UNMAPPED_OR_UNSAFE_ATTRIBUTION")
        if strict.core and displayed_core != strict.core:
            issues.append("DISPLAYED_CORE_MISMATCH")
        issues = list(dict.fromkeys(issues))
        safe = not issues
        source = strict.source if strict.core else permissive.source
        source_counts[source] = source_counts.get(source, 0) + 1
        for issue in issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        if not safe:
            blocked += 1
        if include_safe_rows or not safe:
            findings.append(
                {
                    "status": "SAFE" if safe else "BLOCKED",
                    "row_index": row_index,
                    "issues": issues,
                    "order_id": order_id,
                    "db_row_id": db_row_id,
                    "store_code": store_code,
                    "sku_key": sku_key,
                    "kaspi_offer_name": offer_name,
                    "displayed_core": displayed_core,
                    "resolved_core": strict.core,
                    "resolution_source": strict.source,
                    "kaspi_article": clean_str(article_identity.get("kaspi_article")),
                    "article_map_ids": list(article_identity.get("map_ids") or []),
                    "db_identity_order_id": clean_str(db_identity.get("order_id")),
                    "db_identity_store_code": normalize_store_key(
                        db_identity.get("store_code")
                    ),
                    "db_identity_sku_key": normalize_sku_key(
                        clean_str(db_identity.get("sku_key"))
                    ),
                    "unsafe_fallback_source": "" if strict.core else permissive.source,
                }
            )

    return {
        "schema_version": 1,
        "ok": blocked == 0,
        "total_rows": len(rows),
        "safe_rows": len(rows) - blocked,
        "blocked_rows": blocked,
        "source_counts": dict(sorted(source_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "findings": findings,
    }
