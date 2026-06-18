#!/usr/bin/env python3
"""Shared helpers for identity stabilization validators/remediation scripts."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

WEB_AUTOMATION_ROOT = Path("~/Docs/Web_automation")
WEB_SNAPSHOT_ROOT = WEB_AUTOMATION_ROOT / "exports" / "pricelist_snapshots"
DEFAULT_ACTIVE_STORES = ("UNIVERSAL", "STOREB")

_STORE_FILENAME_MAP = {
    "universal": "UNIVERSAL",
    "30000001pp1": "UNIVERSAL",
    "store-b": "STOREB",
    "storeb": "STOREB",
    "30000002pp1": "STOREB",
    "30000002pp2": "STOREB",
    "acmewear": "ACMEWEAR",
    "30137883pp1": "ACMEWEAR",
    "store-d": "11KZ",
    "30290083pp1": "11KZ",
    "store-c": "MELVIS",
    "30362323pp1": "MELVIS",
}


class IdentityPlanError(RuntimeError):
    """Raised when identity-plan contracts fail."""


class StatusError(IdentityPlanError):
    """Fail-closed error carrying explicit status code for stopline reporting."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_store_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9\-]+", "", text)
    return _STORE_FILENAME_MAP.get(text, text.upper())


def parse_snapshot_date_from_name(path: Path) -> date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def resolve_latest_snapshot_files(
    *,
    snapshot_root: Path,
    stores: tuple[str, ...] = DEFAULT_ACTIVE_STORES,
) -> dict[str, Path]:
    out: dict[str, tuple[date, Path]] = {}
    if not snapshot_root.exists():
        return {}

    for path in sorted(snapshot_root.glob("*_snapshot_*.xlsx")):
        store = normalize_store_code(path.name.split("_snapshot_")[0])
        if store not in stores:
            continue
        snap_date = parse_snapshot_date_from_name(path)
        if snap_date is None:
            continue
        current = out.get(store)
        if current is None or snap_date > current[0]:
            out[store] = (snap_date, path.resolve())

    return {store: payload[1] for store, payload in out.items()}


def normalize_offer_name(value: Any) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def read_snapshot_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, dtype=str).fillna("")
    raise IdentityPlanError(f"unsupported snapshot file type: {path}")


def ensure_required_columns(df: pd.DataFrame, columns: list[str], *, source: Path) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"missing required columns in {source}: {', '.join(missing)}",
        )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_iso_date(value: str, *, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise IdentityPlanError(f"missing required date field: {field}")
    return date.fromisoformat(text)
