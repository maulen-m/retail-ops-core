from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional

from core.utils.sku_map import extract_kaspi_name_core
from core.utils.sku_normalize import normalize_sku_key


SAFE_KASPI_NAME_CORE_SOURCES = frozenset(
    {
        "preferred_core",
        "article_identity",
        "store_offer",
        "sku_key",
        "sku_family",
        "forced_core",
    }
)


@dataclass(frozen=True)
class KaspiNameCoreMaps:
    by_store_offer: dict[tuple[str, str], str]
    by_sku_key: dict[str, str]


@dataclass(frozen=True)
class KaspiNameCoreResolution:
    core: str
    source: str
    matched_sku_key: str = ""

    @property
    def safe(self) -> bool:
        return self.source in SAFE_KASPI_NAME_CORE_SOURCES


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        try:
            if value != value:
                return ""
        except Exception:
            pass
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def normalize_store_key(value: Any) -> str:
    store = clean_str(value).upper()
    if store == "STORE-B":
        return "STOREB"
    return store


def clean_offer_value(value: Any) -> str:
    offer = clean_str(value)
    if offer.upper() in {"YES", "NO", "TRUE", "FALSE", "Y", "N"}:
        return ""
    return offer


def normalize_offer_key(value: Any) -> str:
    return " ".join(clean_offer_value(value).split()).casefold()


def iter_sku_family_candidates(sku_key: Any) -> list[str]:
    normalized = normalize_sku_key(clean_str(sku_key))
    if not normalized:
        return []
    parts = normalized.split("_")
    min_parts = 5
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str) -> None:
        candidate = value.strip()
        if candidate and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)

    add_candidate(normalized)
    for end in range(len(parts) - 1, min_parts - 1, -1):
        candidate = "_".join(parts[:end]).strip()
        add_candidate(candidate)
    return candidates


def load_active_kaspi_name_core_maps(
    conn: sqlite3.Connection,
    *,
    sku_keys: Optional[set[str]] = None,
    store_offer_pairs: Optional[set[tuple[str, str]]] = None,
) -> KaspiNameCoreMaps:
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
    ).fetchone()
    if not has_table:
        return KaspiNameCoreMaps(by_store_offer={}, by_sku_key={})

    filtered_sku_candidates = {
        candidate
        for raw_key in (sku_keys or set())
        for candidate in iter_sku_family_candidates(raw_key)
    }
    filtered_store_offer_pairs = {
        (normalize_store_key(store_code), normalize_offer_key(offer_name))
        for store_code, offer_name in (store_offer_pairs or set())
        if normalize_store_key(store_code) and normalize_offer_key(offer_name)
    }

    rows = conn.execute(
        """
        SELECT store_code, kaspi_offer_name, sku_key, kaspi_name_core
        FROM dim_kaspi_article_map
        WHERE active_flag = 1
          AND kaspi_name_core IS NOT NULL
          AND TRIM(kaspi_name_core) <> ''
        ORDER BY updated_at DESC
        """
    ).fetchall()

    by_store_offer: dict[tuple[str, str], str] = {}
    by_sku_key: dict[str, str] = {}
    store_offer_cores: dict[tuple[str, str], set[str]] = {}
    store_offer_latest_core: dict[tuple[str, str], str] = {}
    for row in rows:
        store_code = normalize_store_key(row["store_code"])
        offer_key = normalize_offer_key(row["kaspi_offer_name"])
        sku_key = normalize_sku_key(clean_str(row["sku_key"]))
        kaspi_core = clean_str(row["kaspi_name_core"])
        if not kaspi_core:
            continue

        if sku_key and (not filtered_sku_candidates or sku_key in filtered_sku_candidates):
            by_sku_key.setdefault(sku_key, kaspi_core)

        store_offer_key = (store_code, offer_key)
        if (
            store_code
            and offer_key
            and (not filtered_store_offer_pairs or store_offer_key in filtered_store_offer_pairs)
        ):
            store_offer_latest_core.setdefault(store_offer_key, kaspi_core)
            store_offer_cores.setdefault(store_offer_key, set()).add(kaspi_core)

    by_store_offer = {
        store_offer_key: store_offer_latest_core[store_offer_key]
        for store_offer_key, cores in store_offer_cores.items()
        if len(cores) == 1
    }

    return KaspiNameCoreMaps(by_store_offer=by_store_offer, by_sku_key=by_sku_key)


def resolve_kaspi_name_core(
    *,
    store_code: Any,
    kaspi_offer_name: Any,
    sku_key: Any,
    sku_id: Any = "",
    maps: Optional[KaspiNameCoreMaps] = None,
    preferred_core: Any = "",
    preferred_source: str = "preferred_core",
    allow_unsafe_fallback: bool = True,
    extract_fallback: Optional[Callable[[str], str]] = None,
) -> KaspiNameCoreResolution:
    core = clean_str(preferred_core)
    if core:
        return KaspiNameCoreResolution(core=core, source=preferred_source)

    maps = maps or KaspiNameCoreMaps(by_store_offer={}, by_sku_key={})
    sku_candidates = iter_sku_family_candidates(sku_key)
    if sku_candidates:
        exact_sku = maps.by_sku_key.get(sku_candidates[0])
        if exact_sku:
            return KaspiNameCoreResolution(core=exact_sku, source="sku_key", matched_sku_key=sku_candidates[0])
        for candidate in sku_candidates[1:]:
            family_core = maps.by_sku_key.get(candidate)
            if family_core:
                return KaspiNameCoreResolution(core=family_core, source="sku_family", matched_sku_key=candidate)

    store_offer_key = (normalize_store_key(store_code), normalize_offer_key(kaspi_offer_name))
    if store_offer_key[0] and store_offer_key[1]:
        exact_store_offer = maps.by_store_offer.get(store_offer_key)
        if exact_store_offer:
            return KaspiNameCoreResolution(core=exact_store_offer, source="store_offer")

    if not allow_unsafe_fallback:
        return KaspiNameCoreResolution(core="", source="unresolved")

    fallback_fn = extract_fallback or extract_kaspi_name_core
    offer_name = clean_str(kaspi_offer_name)
    if offer_name:
        extracted = clean_str(fallback_fn(offer_name))
        if extracted and extracted.lower() != "unknown":
            return KaspiNameCoreResolution(core=extracted, source="raw_offer_extract")

    normalized_sku = normalize_sku_key(clean_str(sku_key))
    if normalized_sku:
        return KaspiNameCoreResolution(core=normalized_sku, source="sku_key_fallback")

    fallback_sku_id = clean_str(sku_id)
    if fallback_sku_id:
        return KaspiNameCoreResolution(core=fallback_sku_id, source="sku_id_fallback")

    return KaspiNameCoreResolution(core="UNKNOWN", source="unknown_fallback")
