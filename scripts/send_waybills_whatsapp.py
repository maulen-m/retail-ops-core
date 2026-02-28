#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12: WhatsApp PDF Sender for Waybills

Semi-automated sending of waybill PDFs to WhatsApp group.
Uses pywhatkit for WhatsApp Web automation.

Features:
- Sends PDFs in correct order: MULTI_LINE → MULTI_QTY → NORMAL
- Tracks sent files to prevent duplicates
- Supports --resume to continue after interruption
- 10-second delay between sends to avoid rate limiting

Usage:
    python scripts/send_waybills_whatsapp.py --dry-run
    python scripts/send_waybills_whatsapp.py --verbose
    python scripts/send_waybills_whatsapp.py --resume
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import webbrowser
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# =============================================================================
# CONFIGURATION
# =============================================================================

# WhatsApp group ID - PLACEHOLDER: Set this to your actual group ID
# To find group ID: Open WhatsApp Web, navigate to group, check URL
WHATSAPP_GROUP_ID = None  # e.g., "AbCdEfGhIjKlMnOp1234567890"

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
SEND_DELAY = 10


# =============================================================================
# TRACKER
# =============================================================================

def load_sent_tracker(tracker_path: Path) -> Dict:
    """Load the sent PDFs tracker file."""
    if tracker_path.exists():
        try:
            with open(tracker_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"sent": [], "last_updated": None}
    return {"sent": [], "last_updated": None}


def save_sent_tracker(tracker_path: Path, tracker: Dict) -> None:
    """Save the sent PDFs tracker file atomically."""
    tracker["last_updated"] = datetime.now().isoformat()
    temp_path = tracker_path.with_suffix('.tmp')
    with open(temp_path, 'w', encoding='utf-8') as f:
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
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it looks like a store folder (has manifest files)
                if any(item.glob("manifest_*.csv")):
                    found.append(item)
        return found

    partitions = [scan_root / "TODAY", scan_root / "OVERDUE"]
    if any(p.exists() for p in partitions):
        folders = []
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

    # Auto mode: prefer merged, then per-store, then legacy.
    for candidate in (merged_root, per_store_root, today_folder):
        if _has_store_folders(candidate):
            return candidate
    return today_folder


def find_store_folders(today_folder: Path, source_mode: str = SOURCE_AUTO) -> List[Path]:
    """Find all store folders in Today directory for selected source mode."""
    scan_root = resolve_send_root(today_folder, source_mode=source_mode)
    return _collect_store_folders(scan_root)


def collect_pdfs_from_category(store_folder: Path, category: str) -> List[Path]:
    """Collect PDFs from a specific category folder."""
    category_path = store_folder / category
    if not category_path.exists():
        return []

    pdfs = list(category_path.glob("*.pdf"))

    # Sort by name for consistent ordering
    return sorted(pdfs, key=lambda x: x.name.lower())


def collect_all_pdfs(today_folder: Path, source_mode: str = SOURCE_AUTO) -> List[Dict]:
    """
    Collect all PDFs in correct sending order.

    Returns list of dicts with:
    - path: Path to PDF
    - store: Store folder name
    - category: Category (SPECIAL_multi_line, etc.)
    - filename: Just the filename
    """
    all_pdfs = []

    store_folders = find_store_folders(today_folder, source_mode=source_mode)

    for store_folder in store_folders:
        store_name = store_folder.name

        for category in PDF_CATEGORIES:
            pdfs = collect_pdfs_from_category(store_folder, category)

            for pdf_path in pdfs:
                all_pdfs.append({
                    "path": pdf_path,
                    "store": store_name,
                    "category": category,
                    "filename": pdf_path.name,
                    "item_core": _extract_item_core(pdf_path.name),
                    "size_token": _extract_size_token(pdf_path.name),
                    "size_rank": _size_rank(_extract_size_token(pdf_path.name)),
                    "family_key": _family_key(_extract_item_core(pdf_path.name)),
                    "relative": _relative_for_tracker(pdf_path, today_folder),
                })

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


def filter_unsent_pdfs(all_pdfs: List[Dict], sent_list: List[str]) -> List[Dict]:
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

    cleaned: list[str] = []
    for tok in tokens:
        if tok in COLOR_TOKENS or tok in NOISE_TOKENS:
            continue
        if tok == "PRO":
            continue
        cleaned.append(tok)

    if not cleaned:
        return text
    return "_".join(cleaned[:3])


def _interleave_by_family(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Interleave entries by family key to avoid near-neighbor duplicates.

    Within each family bucket, keep size-rising order.
    """
    buckets: dict[str, deque[Dict[str, Any]]] = {}
    grouped: dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry.get("family_key") or "UNKNOWN")].append(entry)

    for family, items in grouped.items():
        items.sort(key=lambda x: (x.get("size_rank", 999), str(x.get("filename", "")).lower()))
        buckets[family] = deque(items)

    result: list[Dict[str, Any]] = []
    last_family = ""
    while True:
        alive = [family for family, queue in buckets.items() if queue]
        if not alive:
            break

        candidates = [family for family in alive if family != last_family]
        if not candidates:
            candidates = alive
        candidates.sort(key=lambda family: (-len(buckets[family]), family))
        chosen = candidates[0]

        result.append(buckets[chosen].popleft())
        last_family = chosen

    return result


def order_pdfs_for_sending(pdfs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order PDFs by category, then by size-rising sequence with family diversity.

    This keeps legacy category priority while improving packer-friendly ordering.
    """
    category_groups: dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for pdf in pdfs:
        category_groups[str(pdf.get("category", ""))].append(pdf)

    ordered: list[Dict[str, Any]] = []
    for category in PDF_CATEGORIES:
        if category_groups.get(category):
            ordered.extend(_interleave_by_family(category_groups[category]))

    # Unknown categories (if any) go last, stable by filename.
    unknown = []
    for category, items in category_groups.items():
        if category not in CATEGORY_PRIORITY:
            unknown.extend(items)
    unknown.sort(key=lambda x: str(x.get("filename", "")).lower())
    ordered.extend(unknown)

    return ordered


# =============================================================================
# WHATSAPP SENDING
# =============================================================================

def check_pywhatkit() -> bool:
    """Check if pywhatkit is available."""
    try:
        import pywhatkit
        return True
    except ImportError:
        return False


def send_pdf_to_whatsapp(pdf_path: Path, group_id: str, verbose: bool = False) -> bool:
    """
    Send a PDF to WhatsApp group using pywhatkit.

    Returns True if successful, False otherwise.
    """
    try:
        import pywhatkit as pwk

        if verbose:
            print(f"    Sending: {pdf_path.name}")

        # pywhatkit.sendwhats_image works for files too
        # It opens WhatsApp Web and sends the file
        pwk.sendwhats_image(
            receiver=group_id,
            img_path=str(pdf_path),
            caption=pdf_path.stem,  # Use filename without extension as caption
            wait_time=15,  # Seconds to wait for WhatsApp Web to load
            tab_close=True,
        )

        return True

    except Exception as e:
        print(f"    ERROR sending {pdf_path.name}: {e}")
        return False


# =============================================================================
# MAIN LOGIC
# =============================================================================

def run_sender(
    today_folder: Path,
    group_id: Optional[str],
    dry_run: bool = False,
    resume: bool = True,
    bundle_source: str = SOURCE_AUTO,
    verbose: bool = False,
) -> Dict:
    """
    Run the WhatsApp PDF sender.

    Args:
        today_folder: Path to Today folder
        group_id: WhatsApp group ID
        dry_run: Preview only, don't send
        resume: Skip already-sent PDFs
        bundle_source: Which Today sub-layout to use
        verbose: Print progress

    Returns:
        Dict with results: sent, skipped, failed, total
    """
    results = {
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "total": 0,
    }

    # Check for WhatsApp group ID
    if not group_id and not dry_run:
        print("ERROR: WHATSAPP_GROUP_ID not configured.")
        print("Edit scripts/send_waybills_whatsapp.py and set WHATSAPP_GROUP_ID")
        print("Or use --dry-run to preview files")
        return results

    # Check pywhatkit
    if not dry_run and not check_pywhatkit():
        print("ERROR: pywhatkit not installed.")
        print("Install with: pip install pywhatkit")
        return results

    source_root = resolve_send_root(today_folder, source_mode=bundle_source)

    # Load tracker
    tracker_path = today_folder / SENT_TRACKER_FILE
    tracker = load_sent_tracker(tracker_path) if resume else {"sent": [], "last_updated": None}

    # Collect PDFs
    all_pdfs = collect_all_pdfs(today_folder, source_mode=bundle_source)
    results["total"] = len(all_pdfs)

    if verbose:
        print(f"Bundle source: {source_root}")
        print(f"Found {len(all_pdfs)} PDFs total")

    if not all_pdfs:
        print("No PDFs found in Today folder")
        return results

    # Filter already sent
    pdfs_to_send = filter_unsent_pdfs(all_pdfs, tracker["sent"]) if resume else all_pdfs
    results["skipped"] = len(all_pdfs) - len(pdfs_to_send)

    if results["skipped"] > 0 and verbose:
        print(f"Skipping {results['skipped']} already-sent PDFs")

    if not pdfs_to_send:
        print("All PDFs already sent!")
        return results

    pdfs_to_send = order_pdfs_for_sending(pdfs_to_send)

    try:
        browser_backend = str(webbrowser.get())
    except Exception:
        browser_backend = "system default browser"
    print(f"Sender browser/profile: {browser_backend} (WhatsApp Web logged-in session)")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}PDFs to send: {len(pdfs_to_send)}")
    print("-" * 50)

    # Group by category for display
    current_store = None
    current_category = None

    for i, pdf in enumerate(pdfs_to_send):
        # Print category headers
        if pdf["store"] != current_store:
            current_store = pdf["store"]
            print(f"\nStore: {current_store}")

        if pdf["category"] != current_category:
            current_category = pdf["category"]
            category_display = current_category.replace("_", " ").title()
            print(f"  [{category_display}]")

        # Print filename
        print(f"    {i+1}. {pdf['filename']}")

        if dry_run:
            results["sent"] += 1
            continue

        # Actually send
        success = send_pdf_to_whatsapp(pdf["path"], group_id, verbose)

        if success:
            results["sent"] += 1
            # Track as sent
            tracker["sent"].append(pdf["relative"])
            save_sent_tracker(tracker_path, tracker)

            # Delay before next send
            if i < len(pdfs_to_send) - 1:
                if verbose:
                    print(f"    Waiting {SEND_DELAY}s before next...")
                time.sleep(SEND_DELAY)
        else:
            results["failed"] += 1
            print(f"\n    STOPPING: Failed to send {pdf['filename']}")
            print(f"    Use --resume to continue from here")
            break

    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Send waybill PDFs to WhatsApp group"
    )
    parser.add_argument(
        "--today-folder",
        type=Path,
        default=TODAY_FOLDER,
        help="Path to Today folder (default: excel_ui/Kaspi_orders/Today)"
    )
    parser.add_argument(
        "--group-id",
        type=str,
        default=WHATSAPP_GROUP_ID,
        help="WhatsApp group ID"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't send"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't skip already-sent PDFs"
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
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  WhatsApp PDF Sender")
    print("=" * 60)
    print(f"  Folder: {args.today_folder}")
    print(f"  Bundle source: {args.bundle_source}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Resume: {'No' if args.no_resume else 'Yes'}")
    print()

    results = run_sender(
        today_folder=args.today_folder,
        group_id=args.group_id,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        bundle_source=args.bundle_source,
        verbose=args.verbose,
    )

    print()
    print("=" * 60)
    print(f"  Results:")
    print(f"    Total PDFs: {results['total']}")
    print(f"    Sent: {results['sent']}")
    print(f"    Skipped (already sent): {results['skipped']}")
    print(f"    Failed: {results['failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
