#!/usr/bin/env python3
"""Run stock+price sync preparation for Kaspi pricelist by store."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import re
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from core.integrations.kaspi_pricelist.generator import generate_pricelist
from scripts.build_offer_stock_mapper import DEFAULT_TABLE as DEFAULT_MAPPER_TABLE
from scripts.build_offer_stock_mapper import build_offer_stock_mapper
from scripts.check_kaspi_pricelist_url import check_url
from scripts.deploy_kaspi_pricelist import S3Uploader, deploy_pricelist
from scripts.validate_offer_stock_sync import validate_offer_stock_sync
from scripts.verify_kaspi_pricelist_hash import verify_hash

DEFAULT_STORES = ("UNIVERSAL", "STOREB")
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_pricelist.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "exports" / "kaspi_pricelist"

CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _safe_table_name(table_name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name):
        raise ValueError(f"Unsafe table name: {table_name}")
    return table_name


def _normalize_stores(stores: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for raw in stores:
        code = str(raw or "").strip().upper()
        if code and code not in out:
            out.append(code)
    return out


def _load_allowlist(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not path.exists():
        raise FileNotFoundError(f"Allowlist file not found: {path}")
    values: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            values.add(cleaned)
    return values


def _build_effective_allowlist(
    *,
    conn: sqlite3.Connection,
    table_name: str,
    store_code: str,
    min_confidence: str,
    external_allowlist: set[str],
) -> list[str]:
    min_rank = CONFIDENCE_RANK[min_confidence]
    rows = conn.execute(
        f"""
        SELECT sku_id, mapping_method, mapping_confidence, COALESCE(is_ambiguous, 0) AS is_ambiguous
        FROM {table_name}
        WHERE store_code = ?
        """,
        (store_code,),
    ).fetchall()
    sku_ids: set[str] = set()
    for row in rows:
        sku_id = str(row["sku_id"] or "").strip()
        if not sku_id:
            continue
        if str(row["mapping_method"]) == "unresolved":
            continue
        if int(row["is_ambiguous"] or 0) == 1:
            continue
        confidence = str(row["mapping_confidence"] or "").upper().strip()
        if CONFIDENCE_RANK.get(confidence, 0) < min_rank:
            continue
        if external_allowlist and sku_id not in external_allowlist:
            continue
        sku_ids.add(sku_id)
    return sorted(sku_ids)


def _write_allowlist(path: Path, sku_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sku_ids) + "\n", encoding="utf-8")


def _parse_verify_urls(entries: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in entries or []:
        raw = str(entry or "").strip()
        if not raw:
            continue
        if "=" not in raw:
            raise ValueError(f"--verify-url expects STORE=URL, got: {raw}")
        store, url = raw.split("=", 1)
        store_code = store.strip().upper()
        value = url.strip()
        if not store_code or not value:
            raise ValueError(f"--verify-url expects STORE=URL, got: {raw}")
        out[store_code] = value
    return out


def run_offer_stock_price_sync(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    stores: list[str] | tuple[str, ...] = DEFAULT_STORES,
    config_path: Path = DEFAULT_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    mode: str = "dry-run",
    mapper_table_name: str = DEFAULT_MAPPER_TABLE,
    window_days: int = 90,
    min_confidence: str = "MEDIUM",
    external_allowlist_path: Path | None = None,
    max_unresolved: int = 0,
    min_confident_rate: float = 0.95,
    skip_validate: bool = False,
    bucket: str | None = None,
    prefix: str | None = None,
    verify_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    selected_stores = _normalize_stores(stores)
    if not selected_stores:
        raise ValueError("stores list is empty")
    if mode not in {"dry-run", "publish"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if min_confidence not in CONFIDENCE_RANK:
        raise ValueError(f"Unsupported min_confidence: {min_confidence}")
    mapper_table = _safe_table_name(mapper_table_name)
    verify_url_map = verify_urls or {}

    mapper_summary = build_offer_stock_mapper(
        db_path=db_path,
        stores=selected_stores,
        table_name=mapper_table,
        window_days=window_days,
        dry_run=False,
    )

    validation_report = None
    if not skip_validate:
        validation_report = validate_offer_stock_sync(
            db_path=db_path,
            stores=selected_stores,
            table_name=mapper_table,
            max_unresolved=max_unresolved,
            min_confident_rate=min_confident_rate,
            require_snapshot_coverage=True,
        )
        if not validation_report["ok"]:
            error_text = "; ".join(validation_report.get("errors") or ["unknown validation failure"])
            raise RuntimeError(f"Validation failed before pricelist sync: {error_text}")

    external_allowlist = _load_allowlist(external_allowlist_path)
    allowlist_dir = output_dir / "allowlists"
    allowlist_paths: dict[str, Path] = {}
    allowlist_counts: dict[str, int] = {}

    with get_db(db_path) as conn:
        for store_code in selected_stores:
            sku_ids = _build_effective_allowlist(
                conn=conn,
                table_name=mapper_table,
                store_code=store_code,
                min_confidence=min_confidence,
                external_allowlist=external_allowlist,
            )
            if not sku_ids:
                raise RuntimeError(f"{store_code}: effective allowlist is empty")
            allowlist_path = allowlist_dir / f"{store_code.lower()}_mapper_allowlist.txt"
            _write_allowlist(allowlist_path, sku_ids)
            allowlist_paths[store_code] = allowlist_path
            allowlist_counts[store_code] = len(sku_ids)

    per_store: dict[str, dict[str, Any]] = {}

    if mode == "dry-run":
        for store_code in selected_stores:
            result = generate_pricelist(
                db_path=db_path,
                store_code=store_code,
                config_path=config_path,
                output_dir=output_dir,
                dry_run=True,
                publish_path=None,
                allowlist_path=allowlist_paths[store_code],
            )
            per_store[store_code] = {
                "allowlist_path": str(allowlist_paths[store_code]),
                "allowlist_count": allowlist_counts[store_code],
                "catalog_path": str(result.catalog_path),
                "diff_report_path": str(result.diff_report_path),
                "offer_count": int(result.offer_count),
                "published": False,
            }
    else:
        if os.environ.get("ENABLE_KASPI_PRICELIST_PUBLISH") != "1":
            raise RuntimeError("ENABLE_KASPI_PRICELIST_PUBLISH=1 is required for publish mode")
        if not bucket:
            raise RuntimeError("--bucket is required in publish mode")
        uploader = S3Uploader(bucket=bucket, prefix=prefix or "")
        for store_code in selected_stores:
            results = deploy_pricelist(
                store_codes=[store_code],
                db_path=db_path,
                config_path=config_path,
                output_dir=output_dir,
                allowlist_path=allowlist_paths[store_code],
                publish=True,
                uploader=uploader,
            )
            if not results:
                raise RuntimeError(f"{store_code}: deploy returned no results")
            deployed = results[0]
            per_store[store_code] = {
                "allowlist_path": str(allowlist_paths[store_code]),
                "allowlist_count": allowlist_counts[store_code],
                "catalog_path": str(deployed.local_xml_path),
                "offer_count": None,
                "remote_path": deployed.remote_path,
                "backup_path": deployed.backup_path,
                "published": True,
            }
            verify_url = verify_url_map.get(store_code)
            if verify_url:
                check_url(verify_url)
                verify_hash(verify_url, deployed.local_xml_path)
                per_store[store_code]["verify_url"] = verify_url
                per_store[store_code]["verify_hash"] = True

    return {
        "db_path": str(db_path),
        "mode": mode,
        "stores": selected_stores,
        "mapper_summary": mapper_summary,
        "validation_report": validation_report,
        "allowlist_counts": allowlist_counts,
        "per_store": per_store,
    }


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"Mode: {summary['mode']}")
    print(f"Stores: {', '.join(summary['stores'])}")
    print(
        "Mapper: rows_total={rows_total} unresolved={unresolved_rows} ambiguous={ambiguous_rows}".format(
            **summary["mapper_summary"]
        )
    )
    for store_code in summary["stores"]:
        row = summary["per_store"][store_code]
        if summary["mode"] == "dry-run":
            print(
                f"{store_code}: allowlist={row['allowlist_count']} offers={row['offer_count']} "
                f"xml={row['catalog_path']}"
            )
        else:
            print(
                f"{store_code}: allowlist={row['allowlist_count']} "
                f"published_to={row['remote_path']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offer stock+price sync preparation")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        help="Store code (repeatable). Default: UNIVERSAL + STOREB",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "publish"],
        default="dry-run",
        help="dry-run: generate only, publish: upload via S3/CloudFront",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--mapper-table", default=DEFAULT_MAPPER_TABLE)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument(
        "--min-confidence",
        choices=["LOW", "MEDIUM", "HIGH"],
        default="MEDIUM",
        help="Minimum mapping confidence included into allowlist",
    )
    parser.add_argument("--allowlist", type=Path, default=None, help="Optional external allowlist to intersect")
    parser.add_argument("--max-unresolved", type=int, default=0)
    parser.add_argument("--min-confident-rate", type=float, default=0.95)
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--bucket", default=None, help="S3 bucket (required for publish mode)")
    parser.add_argument("--prefix", default="", help="S3 key prefix")
    parser.add_argument(
        "--verify-url",
        action="append",
        dest="verify_urls",
        help="Optional post-publish verification mapping STORE=URL",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stores = args.stores if args.stores else list(DEFAULT_STORES)
    summary = run_offer_stock_price_sync(
        db_path=args.db,
        stores=stores,
        config_path=args.config,
        output_dir=args.output_dir,
        mode=args.mode,
        mapper_table_name=args.mapper_table,
        window_days=args.window_days,
        min_confidence=args.min_confidence,
        external_allowlist_path=args.allowlist,
        max_unresolved=args.max_unresolved,
        min_confident_rate=args.min_confident_rate,
        skip_validate=args.skip_validate,
        bucket=args.bucket,
        prefix=args.prefix,
        verify_urls=_parse_verify_urls(args.verify_urls),
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
