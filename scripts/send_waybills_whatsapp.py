#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12: WhatsApp PDF Sender for Waybills

Sends waybill PDFs to a specific WhatsApp chat using WhatsApp Web automation.

Key behavior:
- Uses MERGED bundles first (fallback to PER_STORE/legacy)
- Orders files by category, then by contiguous SKU blocks with size-rising order
- Tracks sent files in sent_pdfs.json to avoid duplicates
- Strict chat safety gate: only send to configured chat title
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_WHATSAPP_CHAT_TITLE = "Заказы"
BLOCKED_CHAT_TITLES_DEFAULT = ("order 2",)

# Browser profile used for WhatsApp Web session
DEFAULT_CHROME_USER_DATA_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
DEFAULT_CHROME_PROFILE_DIR = "Profile 2"

# Copy profile to temp to avoid Chrome singleton lock when user's Chrome is open
COPY_PROFILE_TO_TEMP = True

# Default paths
TODAY_FOLDER = PROJECT_ROOT / "excel_ui" / "Kaspi_orders" / "Today"
SENT_TRACKER_FILE = "sent_pdfs.json"

# PDF sending order (priority high to low)
PDF_CATEGORIES = [
    "SPECIAL_multi_line",
    "SPECIAL_multi_qty",
    "NORMAL_singles",
]
CATEGORY_PRIORITY = {name: idx for idx, name in enumerate(PDF_CATEGORIES)}

# Source roots under Today
SOURCE_AUTO = "auto"
SOURCE_MERGED = "merged"
SOURCE_PER_STORE = "per-store"
SOURCE_LEGACY = "legacy"
SOURCE_CHOICES = [SOURCE_AUTO, SOURCE_MERGED, SOURCE_PER_STORE, SOURCE_LEGACY]

STORE_DISPLAY = {
    "STOREB": "STORE-B",
    "STORE-B": "STORE-B",
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "MELVIS": "Store-C",
    "11KZ": "11KZ",
    "MERGED": "MERGED",
}

# Size ordering for send priority
SIZE_ORDER = {
    # Kids
    "22": 1,
    "24": 2,
    "26": 3,
    "28": 4,
    "30": 5,
    "32": 6,
    "34": 7,
    # Adult
    "S": 10,
    "M": 11,
    "L": 12,
    "XL": 13,
    "2XL": 14,
    "3XL": 15,
    "4XL": 16,
}
SIZE_TOKEN_RE = re.compile(r"(22|24|26|28|30|32|34|2XL|3XL|4XL|XL|S|M|L)", re.IGNORECASE)
TRAILING_SIZE_RE = re.compile(
    r"_(22|24|26|28|30|32|34|2XL|3XL|4XL|XL|S|M|L)-\d+$",
    re.IGNORECASE,
)
MESSY_MULTI_SIZE_RE = re.compile(
    r"-(22|24|26|28|30|32|34|2XL|3XL|4XL|XL|S|M|L)-\d+\(",
    re.IGNORECASE,
)
COLOR_TOKENS = {
    "BLACK", "WHITE", "GRAY", "GREY", "RED", "BLUE", "GREEN", "BROWN", "BEIGE",
    "PINK", "PURPLE", "YELLOW", "ORANGE",
    "ЧЕРНЫЙ", "ЧЕРНАЯ", "БЕЛЫЙ", "БЕЛАЯ", "СЕРЫЙ", "СЕРАЯ", "КРАСНЫЙ", "СИНИЙ",
    "ЗЕЛЕНЫЙ", "КОРИЧНЕВЫЙ", "БЕЖЕВЫЙ", "РОЗОВЫЙ", "ФИОЛЕТОВЫЙ", "ЖЕЛТЫЙ",
}
NOISE_TOKENS = {
    "CL", "NEW", "CLO", "MEN", "MAN", "WOMEN", "WOMAN", "KID", "KIDS",
    "MESTOVAYA", "PROD", "SKU", "COLOR", "SIZE", "PP1",
}

# Delay between sends (seconds)
SEND_DELAY = 2.0

WHATSAPP_WEB_URL = "https://web.whatsapp.com"
CHAT_OPEN_TIMEOUT_MS = 90_000
ACTION_TIMEOUT_MS = 45_000


# =============================================================================
# TRACKER
# =============================================================================


def load_sent_tracker(tracker_path: Path) -> Dict[str, Any]:
    """Load the sent PDFs tracker file."""
    if tracker_path.exists():
        try:
            with open(tracker_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict) and isinstance(payload.get("sent", []), list):
                    return payload
        except (json.JSONDecodeError, IOError):
            pass
    return {"sent": [], "last_updated": None}


def save_sent_tracker(tracker_path: Path, tracker: Dict[str, Any]) -> None:
    """Save the sent PDFs tracker file atomically."""
    tracker["last_updated"] = datetime.now().isoformat()
    temp_path = tracker_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    temp_path.replace(tracker_path)


# =============================================================================
# PDF COLLECTION
# =============================================================================


def _collect_store_folders(scan_root: Path) -> List[Path]:
    """Collect store folders under a specific root."""
    if not scan_root.exists():
        return []

    def collect_from(base: Path) -> List[Path]:
        found: List[Path] = []
        for item in base.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                if any(item.glob("manifest_*.csv")):
                    found.append(item)
        return found

    partitions = [scan_root / "TODAY", scan_root / "OVERDUE"]
    if any(p.exists() for p in partitions):
        folders: List[Path] = []
        for partition in partitions:
            if partition.exists():
                folders.extend(collect_from(partition))
    else:
        folders = collect_from(scan_root)

    return sorted(folders, key=lambda x: x.name)


def _has_store_folders(scan_root: Path) -> bool:
    return bool(_collect_store_folders(scan_root))


def resolve_send_root(today_folder: Path, source_mode: str = SOURCE_AUTO) -> Path:
    """Resolve which bundle root to use under Today/."""
    merged_root = today_folder / "MERGED"
    per_store_root = today_folder / "PER_STORE"

    if source_mode == SOURCE_MERGED:
        return merged_root
    if source_mode == SOURCE_PER_STORE:
        return per_store_root
    if source_mode == SOURCE_LEGACY:
        return today_folder

    for candidate in (merged_root, per_store_root, today_folder):
        if _has_store_folders(candidate):
            return candidate
    return today_folder


def find_store_folders(today_folder: Path, source_mode: str = SOURCE_AUTO) -> List[Path]:
    """Find all store folders in Today directory for selected source mode."""
    scan_root = resolve_send_root(today_folder, source_mode=source_mode)
    return _collect_store_folders(scan_root)


def _store_label_from_folder_name(folder_name: str) -> str:
    match = re.match(r"^\d{2}\.\d{2}\.\d{2}_(.+?)_qnt\d+$", folder_name)
    if match:
        return match.group(1)
    return folder_name


def collect_pdfs_from_category(store_folder: Path, category: str) -> List[Path]:
    """Collect PDFs from a specific category folder."""
    category_path = store_folder / category
    if not category_path.exists():
        return []
    return sorted(
        category_path.rglob("*.pdf"),
        key=lambda x: (
            str(x.parent).lower(),
            x.name.lower(),
        ),
    )


def _build_manifest_output_index(
    store_folder: Path,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Build lookup maps from manifest output paths to row metadata.

    Returns:
      - exact output path map: "NORMAL_singles/file.pdf" -> row
      - basename map: "file.pdf" -> [rows...]
    """
    exact_map: Dict[str, Dict[str, Any]] = {}
    basename_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for manifest_path in sorted(store_folder.glob("manifest_*.csv")):
        with manifest_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                output_raw = str(row.get("output") or "").strip()
                if not output_raw:
                    continue
                output_norm = output_raw.replace("\\", "/").lstrip("./")
                row_meta: Dict[str, Any] = {
                    "sku_key": str(row.get("sku_key") or "").strip(),
                    "sku_id": str(row.get("sku_id") or "").strip(),
                    "store": str(row.get("store") or "").strip(),
                    "order_ids": _split_order_ids(str(row.get("order_id") or "")),
                }
                exact_map[output_norm] = row_meta
                basename_map[Path(output_norm).name].append(row_meta)

    return exact_map, basename_map


def collect_all_pdfs(
    today_folder: Path,
    source_mode: str = SOURCE_AUTO,
    order_store_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Collect all PDFs in correct sending order.

    Returns list of dicts with:
    - path: Path to PDF
    - store: Store folder name
    - category: Category (SPECIAL_multi_line, etc.)
    - filename: Just the filename
    """
    all_pdfs: List[Dict[str, Any]] = []
    order_store_map = dict(order_store_map or {})
    store_folders = find_store_folders(today_folder, source_mode=source_mode)

    for store_folder in store_folders:
        output_exact_map, output_basename_map = _build_manifest_output_index(store_folder)
        for category in PDF_CATEGORIES:
            for pdf_path in collect_pdfs_from_category(store_folder, category):
                rel_store_path = str(pdf_path.relative_to(store_folder)).replace("\\", "/")
                row_meta: Optional[Dict[str, Any]] = output_exact_map.get(rel_store_path)
                if row_meta is None:
                    by_name = output_basename_map.get(pdf_path.name, [])
                    if len(by_name) == 1:
                        row_meta = by_name[0]
                    else:
                        row_meta = {}

                item_core = _extract_item_core(pdf_path.name)
                family_key = _family_key(item_core)
                sku_key = str(row_meta.get("sku_key") or "").strip() or family_key
                order_ids = list(row_meta.get("order_ids") or [])
                row_store = str(row_meta.get("store") or "").strip()
                fallback_store = _store_label_from_folder_name(store_folder.name)
                order_counts_by_store = _derive_order_store_counts(
                    order_ids=order_ids,
                    row_store=row_store,
                    fallback_store=fallback_store,
                    order_store_map=order_store_map,
                )

                all_pdfs.append(
                    {
                        "path": pdf_path,
                        "store": store_folder.name,
                        "store_label": _store_label_from_folder_name(store_folder.name),
                        "category": category,
                        "filename": pdf_path.name,
                        "item_core": item_core,
                        "size_token": _extract_size_token(pdf_path.name),
                        "size_rank": _size_rank(_extract_size_token(pdf_path.name)),
                        "family_key": family_key,
                        "sku_key": sku_key,
                        "sku_id": str(row_meta.get("sku_id") or "").strip(),
                        "order_ids": order_ids,
                        "order_counts_by_store": order_counts_by_store,
                        "relative": _relative_for_tracker(pdf_path, today_folder),
                    }
                )

    return all_pdfs


def _relative_for_tracker(pdf_path: Path, today_folder: Path) -> str:
    """
    Build a stable tracker key.

    Prefer paths relative to Today root so PER_STORE files are namespaced as
    PER_STORE/... and do not collide with legacy layout entries.
    """
    try:
        return str(pdf_path.relative_to(today_folder))
    except Exception:
        return pdf_path.name


def _recover_missing_pdf_path(
    pdf_entry: Dict[str, Any],
    today_folder: Path,
) -> Optional[Path]:
    """
    Recover a moved PDF by filename inside the same store/category tree.

    This handles real-world cases where operators manually re-folder bundles
    (e.g., "New Folder With Items") after build, without changing filenames.
    """
    target_name = str(pdf_entry.get("filename") or "").strip()
    if not target_name:
        return None

    original_path = pdf_entry.get("path")
    if not isinstance(original_path, Path):
        return None

    # Find store root by folder name token captured at collection time.
    store_name = str(pdf_entry.get("store") or "").strip()
    store_root: Optional[Path] = None
    if store_name:
        for parent in original_path.parents:
            if parent.name == store_name:
                store_root = parent
                break
    if store_root is None:
        return None

    category = str(pdf_entry.get("category") or "").strip()
    category_root = store_root / category if category else store_root
    if not category_root.exists():
        category_root = store_root

    matches = sorted(category_root.rglob(target_name), key=lambda p: str(p).lower())
    if not matches:
        return None

    recovered = matches[0]
    pdf_entry["path"] = recovered
    pdf_entry["relative"] = _relative_for_tracker(recovered, today_folder)
    return recovered


def filter_unsent_pdfs(all_pdfs: List[Dict[str, Any]], sent_list: List[str]) -> List[Dict[str, Any]]:
    """Filter out PDFs that have already been sent."""
    sent_set = set(sent_list)
    return [pdf for pdf in all_pdfs if pdf["relative"] not in sent_set]


def _extract_size_token(filename: str) -> str:
    stem = Path(filename).stem.upper()

    trailing = TRAILING_SIZE_RE.search(stem)
    if trailing:
        return trailing.group(1).upper()

    messy = MESSY_MULTI_SIZE_RE.search(stem)
    if messy:
        return messy.group(1).upper()

    any_match = SIZE_TOKEN_RE.search(stem)
    if any_match:
        return any_match.group(1).upper()

    return ""


def _size_rank(size_token: str) -> int:
    if not size_token:
        return 999
    return SIZE_ORDER.get(size_token.upper(), 999)


def _extract_item_core(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^Местовая-\d+_", "", stem, flags=re.IGNORECASE)
    stem = TRAILING_SIZE_RE.sub("", stem)
    return stem


def _family_key(item_core: str) -> str:
    text = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "_", item_core).strip("_").upper()
    if not text:
        return "UNKNOWN"

    tokens = [tok for tok in re.split(r"[_\-]+", text) if tok]
    cleaned: List[str] = []
    for tok in tokens:
        if tok in COLOR_TOKENS or tok in NOISE_TOKENS or tok == "PRO":
            continue
        cleaned.append(tok)

    if not cleaned:
        return text
    return "_".join(cleaned[:3])


def _order_category_entries_by_sku(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order one category by SKU blocks.

    Once a SKU block starts, all its sizes are sent contiguously in rising
    size order before moving to next SKU.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    first_seen: Dict[str, int] = {}
    for idx, entry in enumerate(entries):
        sku_key = str(entry.get("sku_key") or entry.get("family_key") or "UNKNOWN")
        grouped[sku_key].append(entry)
        if sku_key not in first_seen:
            first_seen[sku_key] = idx

    for sku_key, items in grouped.items():
        items.sort(
            key=lambda x: (
                int(x.get("size_rank", 999)),
                str(x.get("size_token", "")).upper(),
                str(x.get("filename", "")).lower(),
            )
        )

    ordered_skus = sorted(grouped.keys(), key=lambda key: (first_seen[key], key))
    result: List[Dict[str, Any]] = []
    for sku_key in ordered_skus:
        result.extend(grouped[sku_key])
    return result


def _category_rank(category: str) -> int:
    """
    Stable category priority for sending sequence.

    Rule: all multi-line and multi-qty bundles are sent before normal singles.
    """
    raw = str(category or "").strip()
    if not raw:
        return 99

    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    if "multi_line" in normalized:
        return 0
    if "multi_qty" in normalized:
        return 1
    if "normal" in normalized and "single" in normalized:
        return 2
    return CATEGORY_PRIORITY.get(raw, 99)


def order_pdfs_for_sending(pdfs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order PDFs by category, then by contiguous SKU blocks with rising sizes.
    """
    category_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for pdf in pdfs:
        category_groups[str(pdf.get("category", ""))].append(pdf)

    ordered: List[Dict[str, Any]] = []
    for category in sorted(category_groups.keys(), key=lambda c: (_category_rank(c), c.lower())):
        ordered.extend(_order_category_entries_by_sku(category_groups[category]))

    return ordered


def _split_order_ids(raw_order_ids: str) -> List[str]:
    return [token.strip() for token in (raw_order_ids or "").split(";") if token.strip()]


def _normalize_store_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "UNKNOWN"
    key = re.sub(r"[^A-Za-z0-9]+", "", text).upper()
    if key == "STOREB":
        return "STORE-B"
    if key in STORE_DISPLAY:
        return STORE_DISPLAY[key]
    return text


def _selection_cache_path(today_folder: Path) -> Path:
    return (today_folder.parent.parent / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json").resolve()


def load_order_store_map_from_selection(today_folder: Path) -> Dict[str, str]:
    """
    Load order_id -> display store mapping from waybill selection cache.
    """
    path = _selection_cache_path(today_folder)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    stores = payload.get("stores")
    if not isinstance(stores, dict):
        return {}

    order_store: Dict[str, str] = {}
    for store_code, order_ids in stores.items():
        store_name = _normalize_store_label(store_code)
        if not isinstance(order_ids, list):
            continue
        for oid in order_ids:
            order_id = str(oid or "").strip()
            if order_id:
                order_store[order_id] = store_name
    return order_store


def _derive_order_store_counts(
    order_ids: List[str],
    row_store: str,
    fallback_store: str,
    order_store_map: Dict[str, str],
) -> Dict[str, int]:
    counts: Dict[str, int] = Counter()
    for order_id in order_ids:
        store = order_store_map.get(order_id)
        if not store:
            if row_store and row_store.upper() != "MERGED":
                store = _normalize_store_label(row_store)
            elif fallback_store and fallback_store.upper() != "MERGED":
                store = _normalize_store_label(fallback_store)
            else:
                store = "UNKNOWN"
        counts[_normalize_store_label(store)] += 1
    return dict(counts)


def collect_store_order_bundle_stats(
    store_folders: List[Path],
    order_store_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, int]]:
    """
    Build per-store order target/ready stats from manifests + selection cache.

    Returns:
      {
        "StoreName": {"orders_target": int, "orders_ready": int}
      }
    """
    order_store_map = dict(order_store_map or {})
    target_sets: Dict[str, set[str]] = defaultdict(set)
    for order_id, store in order_store_map.items():
        target_sets[_normalize_store_label(store)].add(str(order_id))

    ready_sets: Dict[str, set[str]] = defaultdict(set)
    for store_folder in store_folders:
        fallback_store = _store_label_from_folder_name(store_folder.name)
        manifest_files = sorted(store_folder.glob("manifest_*.csv"))
        for manifest_path in manifest_files:
            with manifest_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_store = str(row.get("store") or "").strip()
                    order_ids = _split_order_ids(str(row.get("order_id") or ""))
                    if not order_ids:
                        continue
                    order_counts = _derive_order_store_counts(
                        order_ids=order_ids,
                        row_store=row_store,
                        fallback_store=fallback_store,
                        order_store_map=order_store_map,
                    )
                    for store_name in order_counts:
                        for order_id in order_ids:
                            mapped = order_store_map.get(order_id)
                            if mapped:
                                if _normalize_store_label(mapped) == store_name:
                                    ready_sets[store_name].add(order_id)
                            elif store_name != "UNKNOWN":
                                ready_sets[store_name].add(order_id)

    stores = sorted(set(target_sets.keys()) | set(ready_sets.keys()))
    finalized: Dict[str, Dict[str, int]] = {}
    for store_name in stores:
        finalized[store_name] = {
            "orders_target": len(target_sets.get(store_name, set())),
            "orders_ready": len(ready_sets.get(store_name, set())),
        }
    return finalized


def _build_ascii_table(headers: List[str], rows: List[List[str]]) -> str:
    all_rows = [headers] + rows
    widths = [max(len(str(row[col])) for row in all_rows) for col in range(len(headers))]

    def fmt_row(cells: List[str]) -> str:
        padded = [str(cells[idx]).ljust(widths[idx]) for idx in range(len(widths))]
        return "| " + " | ".join(padded) + " |"

    sep = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    lines = [sep, fmt_row(headers), sep]
    for row in rows:
        lines.append(fmt_row(row))
    lines.append(sep)
    return "\n".join(lines)


def format_pre_send_status_table(
    store_stats: Dict[str, Dict[str, int]],
    bundles_target: int,
) -> str:
    ordered_stores = sorted(store_stats)
    rows: List[List[str]] = []
    total_orders_target = 0
    total_orders_ready = 0

    for store in ordered_stores:
        orders_target = int(store_stats[store].get("orders_target", 0))
        orders_ready = int(store_stats[store].get("orders_ready", 0))
        total_orders_target += orders_target
        total_orders_ready += orders_ready
        rows.append([store, str(orders_target), str(orders_ready)])

    rows.append(["TOTAL", str(total_orders_target), str(total_orders_ready)])
    table = _build_ascii_table(["STORE", "Orders Target", "Orders Ready"], rows)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bundles_line = f"Bundles Target: {bundles_target}"
    return f"{timestamp}\n{table}\n{bundles_line}"


def format_post_send_status_table(
    store_stats: Dict[str, Dict[str, int]],
    sent_orders_by_store: Dict[str, int],
    bundles_target: int,
    bundles_sent: int,
) -> str:
    ordered_stores = sorted(store_stats)
    rows: List[List[str]] = []
    total_orders_target = 0
    total_orders_ready = 0
    total_orders_sent = 0

    for store in ordered_stores:
        orders_target = int(store_stats[store].get("orders_target", 0))
        orders_ready = int(store_stats[store].get("orders_ready", 0))
        orders_sent = int(sent_orders_by_store.get(store, 0))

        total_orders_target += orders_target
        total_orders_ready += orders_ready
        total_orders_sent += orders_sent
        rows.append([store, str(orders_target), str(orders_ready), str(orders_sent)])

    rows.append(["TOTAL", str(total_orders_target), str(total_orders_ready), str(total_orders_sent)])
    table = _build_ascii_table(["STORE", "Orders Target", "Orders Ready", "Orders Sent"], rows)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bundles_line = f"Bundles: target={bundles_target}, sent={bundles_sent}"
    return f"{timestamp}\n{table}\n{bundles_line}"


# =============================================================================
# WHATSAPP WEB AUTOMATION
# =============================================================================


def check_playwright() -> bool:
    """Check if Playwright is available."""
    try:
        import playwright  # noqa: F401

        return True
    except Exception:
        return False


def _normalize_chat_key(name: str) -> str:
    return " ".join((name or "").split()).strip().casefold()


def _copy_profile_to_temp(user_data_dir: Path, profile_directory: str, verbose: bool = False) -> Path:
    """Copy the browser profile into a temp dir to avoid singleton lock conflicts."""
    profile_src = user_data_dir / profile_directory
    if not profile_src.exists():
        raise FileNotFoundError(f"Chrome profile not found: {profile_src}")

    tmp_root = Path(tempfile.mkdtemp(prefix="whatsapp-profile-"))

    local_state = user_data_dir / "Local State"
    if local_state.exists():
        shutil.copy2(local_state, tmp_root / "Local State")

    def ignore_cache_dirs(_dir: str, names: Iterable[str]) -> List[str]:
        skip = {
            "Cache",
            "Code Cache",
            "GPUCache",
            "DawnCache",
            "GrShaderCache",
            "ShaderCache",
            "Service Worker",
            "VideoDecodeStats",
            "blob_storage",
            "Blob Storage",
        }
        return [n for n in names if n in skip]

    shutil.copytree(profile_src, tmp_root / profile_directory, dirs_exist_ok=True, ignore=ignore_cache_dirs)

    for root in (tmp_root, tmp_root / profile_directory):
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = root / lock_name
            if lock_path.exists():
                lock_path.unlink(missing_ok=True)

    if verbose:
        print(f"Using temp browser profile: {tmp_root}")

    return tmp_root


@dataclass
class _SendContext:
    page: Any
    context: Any
    playwright: Any
    temp_profile_root: Optional[Path]


class WhatsAppSender:
    """WhatsApp Web document sender with strict active-chat safety gate."""

    def __init__(
        self,
        chat_title: str,
        user_data_dir: Path,
        profile_directory: str,
        blocked_chat_titles: Iterable[str],
        action_timeout_ms: int = ACTION_TIMEOUT_MS,
        verbose: bool = False,
    ) -> None:
        self.chat_title = chat_title
        self.chat_key = _normalize_chat_key(chat_title)
        self.user_data_dir = Path(user_data_dir)
        self.profile_directory = profile_directory
        self.blocked_chat_keys = {_normalize_chat_key(x) for x in blocked_chat_titles if x}
        self.action_timeout_ms = action_timeout_ms
        self.verbose = verbose
        self._ctx: Optional[_SendContext] = None

        if not self.chat_title:
            raise ValueError("chat_title is required")
        if self.chat_key in self.blocked_chat_keys:
            raise ValueError(f"Target chat '{self.chat_title}' is blocked by safety policy")

    @property
    def page(self) -> Any:
        if not self._ctx:
            raise RuntimeError("WhatsApp sender not started")
        return self._ctx.page

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        temp_root: Optional[Path] = None
        if COPY_PROFILE_TO_TEMP:
            temp_root = _copy_profile_to_temp(self.user_data_dir, self.profile_directory, verbose=self.verbose)
            launch_user_data_dir = temp_root
        else:
            launch_user_data_dir = self.user_data_dir

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(launch_user_data_dir),
            channel="chrome",
            headless=False,
            args=[f"--profile-directory={self.profile_directory}"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(self.action_timeout_ms)
        page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded")

        self._ctx = _SendContext(
            page=page,
            context=context,
            playwright=playwright,
            temp_profile_root=temp_root,
        )

        self._wait_for_chat_list_ready()
        self.open_chat(self.chat_title)

    def close(self) -> None:
        if not self._ctx:
            return

        temp_root = self._ctx.temp_profile_root
        try:
            self._ctx.context.close()
        finally:
            try:
                self._ctx.playwright.stop()
            finally:
                if temp_root:
                    shutil.rmtree(temp_root, ignore_errors=True)
        self._ctx = None

    def __enter__(self) -> "WhatsAppSender":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _wait_for_chat_list_ready(self) -> None:
        self.page.locator("div[aria-label='Chat list']").wait_for(timeout=CHAT_OPEN_TIMEOUT_MS)
        self.page.locator("div[aria-label='Search input textbox']").wait_for(timeout=CHAT_OPEN_TIMEOUT_MS)

    @staticmethod
    def _is_navigation_context_error(exc: Exception) -> bool:
        msg = str(exc or "").lower()
        return (
            "execution context was destroyed" in msg
            or "most likely because of a navigation" in msg
            or "cannot find context with specified id" in msg
            or "target closed" in msg
        )

    def _composer_candidates(self) -> List[Any]:
        return [
            self.page.locator("footer div[contenteditable='true'][role='textbox']").first,
            self.page.locator("footer div[contenteditable='true'][data-lexical-editor='true']").first,
            self.page.locator("div[contenteditable='true'][aria-label='Type a message']").first,
            self.page.locator("div[contenteditable='true'][aria-label^='Type to group']").first,
            self.page.locator("footer div[contenteditable='true']").first,
        ]

    def _resolve_composer(
        self,
        timeout_ms: int,
        required: bool = True,
    ) -> Optional[Any]:
        deadline = time.time() + (timeout_ms / 1000.0)
        last_error: Optional[Exception] = None

        while time.time() < deadline:
            for locator in self._composer_candidates():
                try:
                    if locator.count() <= 0:
                        continue
                    candidate = locator.first
                    candidate.wait_for(timeout=1200)
                    return candidate
                except Exception as exc:
                    last_error = exc
                    continue
            self.page.wait_for_timeout(250)

        if required:
            raise RuntimeError(f"Composer not ready in target chat: {last_error}")
        return None

    def _active_chat_title(self) -> str:
        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                title = self.page.evaluate(
                    """
                    () => {
                      const clean = (value) => (value || '').trim();
                      const skip = new Set([
                        '',
                        'click here for group info',
                        'profile details',
                        'wa-wordmark-refreshed',
                        'whatsapp',
                        'call',
                      ]);

                      // Preferred: selected row in chat list.
                      const selectedRow = document.querySelector(\"div[aria-label='Chat list'] [aria-selected='true']\");
                      if (selectedRow) {
                        const rowName = selectedRow.querySelector(\"span[title], span[dir='auto']\");
                        if (rowName) {
                          const text = clean(rowName.getAttribute('title') || rowName.textContent || '');
                          if (!skip.has(text.toLowerCase())) return text;
                        }
                      }

                      // Fallback: right panel header title. Scan from last header because left nav header is first.
                      const headers = Array.from(document.querySelectorAll('header')).reverse();
                      for (const header of headers) {
                        const nodes = [
                          ...header.querySelectorAll(\"span[dir='auto']\"),
                          ...header.querySelectorAll('span[title]'),
                          ...header.querySelectorAll('h1, h2'),
                        ];
                        for (const node of nodes) {
                          const text = clean((node.getAttribute && node.getAttribute('title')) || node.textContent || '');
                          if (skip.has(text.toLowerCase())) continue;
                          if (text.length >= 2) return text;
                        }
                      }
                      return '';
                    }
                    """
                )
                return str(title or "").strip()
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                self.page.wait_for_timeout(500)
        if last_error and self._is_navigation_context_error(last_error):
            return ""
        if last_error:
            raise last_error
        return ""

    def _assert_active_target_chat(self) -> None:
        deadline = time.time() + 12.0
        last_title = ""
        while time.time() < deadline:
            active_title = self._active_chat_title()
            active_key = _normalize_chat_key(active_title)
            last_title = active_title

            if not active_key:
                self.page.wait_for_timeout(250)
                continue

            if active_key in self.blocked_chat_keys:
                raise RuntimeError(
                    f"Safety gate blocked send: active chat is forbidden ({active_title!r})"
                )

            if active_key == self.chat_key:
                return

            self.page.wait_for_timeout(250)

        if not _normalize_chat_key(last_title):
            raise RuntimeError("Could not determine active WhatsApp chat title")
        raise RuntimeError(
            f"Safety gate blocked send: active chat mismatch ({last_title!r} != {self.chat_title!r})"
        )

    def _try_click_candidate(self, candidates: Iterable[Any]) -> bool:
        for candidate in candidates:
            if candidate.count() <= 0:
                continue
            candidate.first.click()
            self.page.wait_for_timeout(900)
            if _normalize_chat_key(self._active_chat_title()) == self.chat_key:
                return True
        return False

    def open_chat(self, chat_title: str) -> None:
        if _normalize_chat_key(chat_title) in self.blocked_chat_keys:
            raise RuntimeError(f"Requested chat is blocked: {chat_title!r}")

        # First attempt: direct click from visible chat list (fastest + safest).
        chat_list = self.page.locator("div[aria-label='Chat list']")
        if not self._try_click_candidate(
            [
                chat_list.locator(f"span[title='{chat_title}']"),
                chat_list.locator("span[dir='auto']", has_text=chat_title),
                chat_list.get_by_text(chat_title, exact=True),
            ]
        ):
            # Fallback: use search box, then click/enter.
            search = self.page.locator("div[aria-label='Search input textbox']").first
            search.click()
            search.fill("")
            search.fill(chat_title)
            self.page.wait_for_timeout(1000)

            if not self._try_click_candidate(
                [
                    chat_list.locator(f"span[title='{chat_title}']"),
                    chat_list.locator("span[dir='auto']", has_text=chat_title),
                    self.page.locator(f"span[title='{chat_title}']"),
                    self.page.get_by_text(chat_title, exact=True),
                ]
            ):
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(1200)

        self._assert_active_target_chat()
        self._resolve_composer(timeout_ms=min(self.action_timeout_ms, 20_000), required=False)

        if self.verbose:
            print(f"WhatsApp active chat: {self._active_chat_title()}")

    def _safe_click_selectors(
        self,
        selectors: Iterable[str],
        label: str,
        timeout_ms: Optional[int] = None,
    ) -> None:
        timeout_ms = timeout_ms if timeout_ms is not None else self.action_timeout_ms
        deadline = time.time() + (timeout_ms / 1000.0)
        errors: List[str] = []

        while time.time() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector)
                if locator.count() <= 0:
                    continue
                target = locator.first
                try:
                    target.click(timeout=1500)
                    return
                except Exception as exc:
                    errors.append(f"{selector} normal: {exc}")

                try:
                    target.click(timeout=1500, force=True)
                    return
                except Exception as exc:
                    errors.append(f"{selector} force: {exc}")

                try:
                    target.evaluate("el => el.click()")
                    return
                except Exception as exc:
                    errors.append(f"{selector} js: {exc}")

            self.page.wait_for_timeout(250)

        err_tail = " | ".join(errors[-6:]) if errors else "no matching elements"
        raise RuntimeError(f"Failed to click {label}. Errors: {err_tail}")

    def _choose_file_via_document_menu(self, pdf_path: Path) -> None:
        from playwright.sync_api import TimeoutError as PWTimeoutError

        last_error: Optional[Exception] = None
        for _ in range(3):
            try:
                with self.page.expect_file_chooser(timeout=7000) as chooser_info:
                    self._safe_click_selectors(
                        [
                            "div[role='menuitem'][aria-label='Document']",
                            "div[role='menuitem'][aria-label='Документ']",
                        ],
                        "document menu item",
                        timeout_ms=5000,
                    )
                chooser = chooser_info.value
                chooser.set_files(str(pdf_path))
                return
            except PWTimeoutError as exc:
                last_error = exc
                self.page.wait_for_timeout(500)
            except Exception as exc:
                last_error = exc
                self.page.wait_for_timeout(500)

        if last_error:
            raise last_error
        raise RuntimeError("Failed to open document file chooser")

    def _outgoing_message_count(self) -> int:
        try:
            value = self.page.evaluate(
                """
                () => {
                  return document.querySelectorAll("div.message-out").length;
                }
                """
            )
            return int(value or 0)
        except Exception:
            return 0

    def _wait_for_new_outgoing_message(self, previous_count: int, timeout_ms: int) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.wait_for_function(
                    """
                    (prev) => {
                      const count = document.querySelectorAll("div.message-out").length;
                      return count > prev;
                    }
                    """,
                    arg=previous_count,
                    timeout=timeout_ms,
                )
                return
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                if attempt < 3:
                    self.page.wait_for_timeout(800)
                    continue
        # Soft fallback for transient navigation race: avoid hard crash mid-run.
        if last_error and self._is_navigation_context_error(last_error):
            self.page.wait_for_timeout(2000)
            return
        if last_error:
            raise last_error

    def _wait_for_last_outgoing_settled(self, timeout_ms: int) -> None:
        """
        Wait until the latest outgoing message is no longer in "sending/uploading" state.

        This prevents closing the temporary browser profile before WhatsApp finishes
        syncing the just-sent message to server state.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                self.page.wait_for_function(
                    """
                    () => {
                      const outgoing = document.querySelectorAll("div.message-out");
                      if (!outgoing.length) return false;
                      const last = outgoing[outgoing.length - 1];
                      if (!last) return false;

                      const pending = last.querySelector(
                        [
                          "span[data-icon='msg-time']",
                          "span[data-icon='status-clock']",
                          "[role='progressbar']",
                          "[aria-label*='sending']",
                          "[aria-label*='Sending']",
                          "[aria-label*='отправля']",
                          "[aria-label*='Отправля']"
                        ].join(",")
                      );
                      return !pending;
                    }
                    """,
                    timeout=timeout_ms,
                )
                return
            except Exception as exc:
                last_error = exc
                if not self._is_navigation_context_error(exc):
                    raise
                if attempt < 3:
                    self.page.wait_for_timeout(800)
                    continue
        if last_error and self._is_navigation_context_error(last_error):
            self.page.wait_for_timeout(2500)
            return
        if last_error:
            raise last_error

    def wait_for_outgoing_sync(self, timeout_ms: int = 90_000) -> None:
        self._wait_for_last_outgoing_settled(timeout_ms=timeout_ms)

    def send_text_message(self, text: str) -> None:
        if not text.strip():
            return

        lines = text.splitlines()
        if not lines:
            return

        last_error: Optional[Exception] = None
        for attempt in range(1, 5):
            try:
                self._assert_active_target_chat()
                prev_outgoing = self._outgoing_message_count()
                composer = self._resolve_composer(
                    timeout_ms=max(self.action_timeout_ms, 45_000),
                    required=True,
                )
                if composer is None:
                    raise RuntimeError("Composer not available")
                composer.click()

                try:
                    composer.press("Control+A")
                    composer.press("Backspace")
                except Exception:
                    pass

                for idx, line in enumerate(lines):
                    if line:
                        self.page.keyboard.insert_text(line)
                    if idx < len(lines) - 1:
                        self.page.keyboard.press("Shift+Enter")

                self.page.keyboard.press("Enter")
                self._wait_for_new_outgoing_message(
                    prev_outgoing,
                    timeout_ms=max(self.action_timeout_ms, 60_000),
                )
                self._wait_for_last_outgoing_settled(
                    timeout_ms=max(self.action_timeout_ms, 90_000),
                )
                self._assert_active_target_chat()
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 4:
                    break
                if self.verbose:
                    print(f"      text send retry {attempt}/4 due to: {exc}")
                self._wait_for_chat_list_ready()
                self.open_chat(self.chat_title)
                self.page.wait_for_timeout(800)

        if last_error:
            raise last_error

    def send_document(self, pdf_path: Path) -> None:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        last_error: Optional[Exception] = None

        for attempt in range(1, 4):
            try:
                self._assert_active_target_chat()
                prev_outgoing = self._outgoing_message_count()
                self._resolve_composer(
                    timeout_ms=max(self.action_timeout_ms, 45_000),
                    required=True,
                )
                self._safe_click_selectors(
                    [
                        "button[aria-label='Attach']",
                        "button[aria-label='Прикрепить']",
                    ],
                    "attach button",
                    timeout_ms=12_000,
                )

                self._choose_file_via_document_menu(pdf_path)
                self.page.wait_for_timeout(800)

                self._safe_click_selectors(
                    [
                        "button[aria-label='Send']",
                        "button[aria-label='Отправить']",
                        "span[data-icon='wds-ic-send-filled']",
                        "span[data-icon='send']",
                    ],
                    "send button",
                    timeout_ms=15_000,
                )

                self._wait_for_new_outgoing_message(
                    prev_outgoing,
                    timeout_ms=max(self.action_timeout_ms, 90_000),
                )
                self._wait_for_last_outgoing_settled(
                    timeout_ms=max(self.action_timeout_ms, 120_000),
                )
                self._assert_active_target_chat()
                return
            except Exception as exc:
                last_error = exc
                if attempt >= 3:
                    break
                if self.verbose:
                    print(f"      send retry {attempt}/3 due to: {exc}")
                self._wait_for_chat_list_ready()
                self.open_chat(self.chat_title)
                self.page.wait_for_timeout(1000)

        if last_error:
            raise last_error


# =============================================================================
# MAIN LOGIC
# =============================================================================


def run_sender(
    today_folder: Path,
    chat_title: Optional[str],
    dry_run: bool = False,
    resume: bool = True,
    bundle_source: str = SOURCE_AUTO,
    status_messages: bool = True,
    send_delay: float = SEND_DELAY,
    chrome_user_data_dir: Path = DEFAULT_CHROME_USER_DATA_DIR,
    chrome_profile_directory: str = DEFAULT_CHROME_PROFILE_DIR,
    blocked_chat_titles: Iterable[str] = BLOCKED_CHAT_TITLES_DEFAULT,
    fail_fast: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run WhatsApp PDF sender workflow."""
    results: Dict[str, Any] = {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "total": 0,
        "target_chat": chat_title or "",
        "source_root": "",
        "status_message_failed": 0,
    }

    if not chat_title and not dry_run:
        print("ERROR: --chat-title is required for live send.")
        return results

    if not dry_run and not check_playwright():
        print("ERROR: playwright not installed.")
        print("Install with: pip install playwright")
        return results

    source_root = resolve_send_root(today_folder, source_mode=bundle_source)
    results["source_root"] = str(source_root)
    order_store_map = load_order_store_map_from_selection(today_folder)

    tracker_path = today_folder / SENT_TRACKER_FILE
    tracker = load_sent_tracker(tracker_path) if resume else {"sent": [], "last_updated": None}

    all_pdfs = collect_all_pdfs(
        today_folder,
        source_mode=bundle_source,
        order_store_map=order_store_map,
    )
    results["total"] = len(all_pdfs)
    store_folders = find_store_folders(today_folder, source_mode=bundle_source)
    store_stats = collect_store_order_bundle_stats(
        store_folders,
        order_store_map=order_store_map,
    )
    if not store_stats:
        fallback_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"orders_target": 0, "orders_ready": 0}
        )
        for pdf in all_pdfs:
            for store, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                store_name = _normalize_store_label(store)
                fallback_stats[store_name]["orders_ready"] += int(qty)
        store_stats = {name: values for name, values in fallback_stats.items()}

    if verbose:
        print(f"Bundle source root: {source_root}")
        print(f"Found {len(all_pdfs)} PDFs total")

    if not all_pdfs:
        print("No PDFs found in Today folder")
        return results

    pdfs_to_send = filter_unsent_pdfs(all_pdfs, tracker["sent"]) if resume else all_pdfs
    results["skipped"] = len(all_pdfs) - len(pdfs_to_send)

    if results["skipped"] > 0 and verbose:
        print(f"Skipping {results['skipped']} already-sent PDFs")

    if not pdfs_to_send:
        print("All PDFs already sent!")
        sent_orders_snapshot: Counter[str] = Counter()
        for pdf in all_pdfs:
            for store_name, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                sent_orders_snapshot[_normalize_store_label(store_name)] += int(qty)
        pre_status_text = format_pre_send_status_table(
            store_stats,
            bundles_target=len(all_pdfs),
        )
        post_status_text = format_post_send_status_table(
            store_stats,
            dict(sent_orders_snapshot),
            bundles_target=len(all_pdfs),
            bundles_sent=len(all_pdfs),
        )
        print("\nPre-send status:")
        print(pre_status_text)
        print("\nPost-send status:")
        print(post_status_text)
        return results

    pdfs_to_send = order_pdfs_for_sending(pdfs_to_send)
    bundles_target = len(pdfs_to_send)
    bundles_sent = 0
    sent_orders_by_store: Counter[str] = Counter()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}PDFs to send: {len(pdfs_to_send)}")
    print("-" * 50)
    pre_status_text = format_pre_send_status_table(store_stats, bundles_target=bundles_target)
    print("\nPre-send status:")
    print(pre_status_text)

    current_store: Optional[str] = None
    current_category: Optional[str] = None

    if dry_run:
        for i, pdf in enumerate(pdfs_to_send, start=1):
            if pdf["store"] != current_store:
                current_store = pdf["store"]
                print(f"\nStore: {current_store}")

            if pdf["category"] != current_category:
                current_category = pdf["category"]
                print(f"  [{current_category.replace('_', ' ').title()}]")

            print(f"    {i}. {pdf['filename']}")
            results["sent"] += 1
            bundles_sent += 1
            for store_name, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)

        post_status_text = format_post_send_status_table(
            store_stats,
            dict(sent_orders_by_store),
            bundles_target=bundles_target,
            bundles_sent=bundles_sent,
        )
        print("\nPost-send status:")
        print(post_status_text)
        return results

    sender = WhatsAppSender(
        chat_title=chat_title or "",
        user_data_dir=Path(chrome_user_data_dir),
        profile_directory=chrome_profile_directory,
        blocked_chat_titles=blocked_chat_titles,
        action_timeout_ms=ACTION_TIMEOUT_MS,
        verbose=verbose,
    )

    try:
        with sender:
            if status_messages:
                try:
                    sender.send_text_message(pre_status_text)
                except Exception as exc:
                    results["status_message_failed"] = 1
                    print(f"\nWARNING: Failed to send pre-send status message: {exc}")
                    if fail_fast:
                        results["failed"] += 1
                        print("STOPPING: fail-fast enabled.")
                        return results

            for i, pdf in enumerate(pdfs_to_send, start=1):
                if pdf["store"] != current_store:
                    current_store = pdf["store"]
                    print(f"\nStore: {current_store}")

                if pdf["category"] != current_category:
                    current_category = pdf["category"]
                    print(f"  [{current_category.replace('_', ' ').title()}]")

                print(f"    {i}. {pdf['filename']}")

                if not pdf["path"].exists():
                    recovered = _recover_missing_pdf_path(pdf, today_folder)
                    if recovered is not None:
                        if verbose:
                            print(f"      recovered moved PDF path: {recovered}")
                    else:
                        results["failed"] += 1
                        print(f"      SKIP: missing PDF on disk: {pdf['path']}")
                        continue

                try:
                    sender.send_document(pdf["path"])
                except FileNotFoundError:
                    recovered = _recover_missing_pdf_path(pdf, today_folder)
                    if recovered is not None:
                        try:
                            sender.send_document(recovered)
                        except Exception as exc:
                            results["failed"] += 1
                            if fail_fast:
                                print(f"\nSTOPPING: Failed to send {pdf['filename']}: {exc}")
                                print("Use --resume after fixing WhatsApp UI/session")
                                break
                            print(f"\nWARNING: Failed to send {pdf['filename']}: {exc}")
                            continue
                    else:
                        results["failed"] += 1
                        print(f"      SKIP: missing PDF on disk: {pdf['path']}")
                        continue
                except Exception as exc:
                    results["failed"] += 1
                    if fail_fast:
                        print(f"\nSTOPPING: Failed to send {pdf['filename']}: {exc}")
                        print("Use --resume after fixing WhatsApp UI/session")
                        break
                    print(f"\nWARNING: Failed to send {pdf['filename']}: {exc}")
                    continue

                results["sent"] += 1
                bundles_sent += 1
                for store_name, qty in dict(pdf.get("order_counts_by_store") or {}).items():
                    sent_orders_by_store[_normalize_store_label(store_name)] += int(qty)
                tracker["sent"].append(pdf["relative"])
                save_sent_tracker(tracker_path, tracker)

                if i < len(pdfs_to_send) and send_delay > 0:
                    time.sleep(send_delay)

            post_status_text = format_post_send_status_table(
                store_stats,
                dict(sent_orders_by_store),
                bundles_target=bundles_target,
                bundles_sent=bundles_sent,
            )
            print("\nPost-send status:")
            print(post_status_text)
            if status_messages:
                try:
                    sender.send_text_message(post_status_text)
                except Exception as exc:
                    results["status_message_failed"] = 1
                    print(f"\nWARNING: Failed to send post-send status message: {exc}")

            # Ensure final message/doc upload state is synced before browser closes.
            try:
                sender.wait_for_outgoing_sync(timeout_ms=120_000)
            except Exception as exc:
                if verbose:
                    print(f"WARNING: final outgoing sync check failed: {exc}")
    except Exception as exc:
        results["failed"] += 1
        if fail_fast:
            print(f"\nSTOPPING: Sender runtime error: {exc}")
        else:
            print(f"\nWARNING: Sender runtime error: {exc}")
    finally:
        sender.close()

    return results


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="Send waybill PDFs to WhatsApp chat")
    parser.add_argument(
        "--today-folder",
        type=Path,
        default=TODAY_FOLDER,
        help="Path to Today folder (default: excel_ui/Kaspi_orders/Today)",
    )
    parser.add_argument(
        "--chat-title",
        type=str,
        default=DEFAULT_WHATSAPP_CHAT_TITLE,
        help="Exact WhatsApp chat title to send into (default: Заказы)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't send",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't skip already-sent PDFs",
    )
    parser.add_argument(
        "--bundle-source",
        choices=SOURCE_CHOICES,
        default=SOURCE_AUTO,
        help=(
            "Which bundle layout to send from: "
            "auto (prefer MERGED, then PER_STORE, then legacy), "
            "merged, per-store, or legacy."
        ),
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        type=Path,
        default=DEFAULT_CHROME_USER_DATA_DIR,
        help="Chrome user data dir used to clone logged-in profile",
    )
    parser.add_argument(
        "--chrome-profile-directory",
        type=str,
        default=DEFAULT_CHROME_PROFILE_DIR,
        help="Chrome profile directory name (e.g. 'Profile 2')",
    )
    parser.add_argument(
        "--forbid-chat",
        action="append",
        default=list(BLOCKED_CHAT_TITLES_DEFAULT),
        help="Blocked chat title safety gate (repeatable)",
    )
    parser.add_argument(
        "--send-delay",
        type=float,
        default=SEND_DELAY,
        help="Delay between sends in seconds",
    )
    parser.add_argument(
        "--status-messages",
        dest="status_messages",
        action="store_true",
        default=True,
        help="Send pre/post ASCII status tables to WhatsApp chat (default: on)",
    )
    parser.add_argument(
        "--no-status-messages",
        dest="status_messages",
        action="store_false",
        help="Disable sending pre/post ASCII status tables to WhatsApp chat",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first send/runtime error (default: continue and report failures)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()
    dedup_blocked: List[str] = []
    seen_blocked: set[str] = set()
    for name in args.forbid_chat:
        key = _normalize_chat_key(name)
        if key and key not in seen_blocked:
            seen_blocked.add(key)
            dedup_blocked.append(name)

    print("=" * 60)
    print("  WhatsApp PDF Sender")
    print("=" * 60)
    print(f"  Folder: {args.today_folder}")
    print(f"  Bundle source: {args.bundle_source}")
    print(f"  Target chat: {args.chat_title}")
    print(f"  Blocked chats: {', '.join(dedup_blocked)}")
    print(f"  Browser profile: {args.chrome_user_data_dir} / {args.chrome_profile_directory}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Status messages: {'Yes' if args.status_messages else 'No'}")
    print(f"  Fail fast: {'Yes' if args.fail_fast else 'No'}")
    print(f"  Resume: {'No' if args.no_resume else 'Yes'}")
    print()

    started_at = time.monotonic()
    results = run_sender(
        today_folder=args.today_folder,
        chat_title=args.chat_title,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        bundle_source=args.bundle_source,
        send_delay=float(args.send_delay),
        status_messages=bool(args.status_messages),
        chrome_user_data_dir=args.chrome_user_data_dir,
        chrome_profile_directory=args.chrome_profile_directory,
        blocked_chat_titles=dedup_blocked,
        fail_fast=bool(args.fail_fast),
        verbose=args.verbose,
    )
    elapsed = max(0, int(time.monotonic() - started_at))
    mins, secs = divmod(elapsed, 60)

    print()
    print("=" * 60)
    print("  Results:")
    print(f"    Total PDFs: {results['total']}")
    print(f"    Sent: {results['sent']}")
    print(f"    Skipped (already sent): {results['skipped']}")
    print(f"    Failed: {results['failed']}")
    print(f"    Status message failures: {results['status_message_failed']}")
    print(f"    Source root: {results.get('source_root', '')}")
    print(f"    Duration: {mins}m {secs}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
