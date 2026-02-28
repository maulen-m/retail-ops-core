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
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

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

def find_store_folders(today_folder: Path) -> List[Path]:
    """Find all store folders in Today directory (legacy or PER_STORE layout)."""
    scan_root = today_folder / "PER_STORE" if (today_folder / "PER_STORE").is_dir() else today_folder
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

    # Sort by name (date_store format)
    return sorted(folders, key=lambda x: x.name)


def collect_pdfs_from_category(store_folder: Path, category: str) -> List[Path]:
    """Collect PDFs from a specific category folder."""
    category_path = store_folder / category
    if not category_path.exists():
        return []

    pdfs = list(category_path.glob("*.pdf"))

    # Sort by name for consistent ordering
    return sorted(pdfs, key=lambda x: x.name.lower())


def collect_all_pdfs(today_folder: Path) -> List[Dict]:
    """
    Collect all PDFs in correct sending order.

    Returns list of dicts with:
    - path: Path to PDF
    - store: Store folder name
    - category: Category (SPECIAL_multi_line, etc.)
    - filename: Just the filename
    """
    all_pdfs = []

    store_folders = find_store_folders(today_folder)

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
    verbose: bool = False,
) -> Dict:
    """
    Run the WhatsApp PDF sender.

    Args:
        today_folder: Path to Today folder
        group_id: WhatsApp group ID
        dry_run: Preview only, don't send
        resume: Skip already-sent PDFs
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

    # Load tracker
    tracker_path = today_folder / SENT_TRACKER_FILE
    tracker = load_sent_tracker(tracker_path) if resume else {"sent": [], "last_updated": None}

    # Collect PDFs
    all_pdfs = collect_all_pdfs(today_folder)
    results["total"] = len(all_pdfs)

    if verbose:
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
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  WhatsApp PDF Sender")
    print("=" * 60)
    print(f"  Folder: {args.today_folder}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Resume: {'No' if args.no_resume else 'Yes'}")
    print()

    results = run_sender(
        today_folder=args.today_folder,
        group_id=args.group_id,
        dry_run=args.dry_run,
        resume=not args.no_resume,
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
