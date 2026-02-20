# Opus Plan: Kaspi Order Size, Waybill & WhatsApp Automation

**Document Version:** 1.0  
**Created:** 2025-12-11  
**Status:** Specification for autonomous implementation  
**Phase:** 12 (Post-Phase 11 Daily Workflow)

---

## Context

### Business Overview

Adil operates a Kazakhstan-based retail business importing clothing from China, selling primarily through Kaspi marketplace across 5 stores (Universal, AcmeWear, 11KZ, STORE-B, Store-C). The business has a same-day shipping SLA for orders received before 16:00 GMT+5.

### Current State

A dedicated employee processes orders daily from an Excel-based CRM (`SALES_KSP_CRM_V3.xlsx`). The workflow involves:
- Calling customers to collect height/weight measurements
- Assigning correct sizes (`MY_SIZE` column)
- Generating grouped waybill PDFs for shipping
- Manually sending PDFs to a WhatsApp group chat for visual verification

### Key Files & Commands

| File/Command | Purpose |
|--------------|---------|
| `SALES_KSP_CRM_V3.xlsx` | Master CRM with all orders |
| `run_full_import.command` | Downloads API orders → imports to CRM |
| `run_build_waybills.command` | Generates grouped PDF waybills after sizes assigned |
| `scripts/export_api_orders.py` | Pulls orders from Kaspi API |
| `scripts/import_orders_to_crm.py` | Appends orders to CRM Excel (xlwings) |
| `scripts/build_daily_waybills.py` | Groups waybills by type (NORMAL/MULTI_LINE/MULTI_QTY) |

### Repository Location

```
~/Docs/Autonomous_business/
├── excel_ui/
│   ├── SALES_KSP_CRM_V3.xlsx          # Master CRM
│   ├── ActiveOrders/                   # Input folder for downloads
│   │   ├── ActiveOrders.xlsx           # API-generated orders file
│   │   └── waybill*.zip                # Downloaded waybill PDFs
│   └── Kaspi_orders/Today/             # Output: grouped PDFs
├── scripts/
│   ├── export_api_orders.py            # API → Excel
│   ├── import_orders_to_crm.py         # Excel → CRM
│   └── build_daily_waybills.py         # Waybill grouper
└── config/
    └── kaspi_stores.yaml               # Store token mapping
```

---

## Objectives

### Primary Goals

| # | Objective | Success Metric |
|---|-----------|----------------|
| 1 | **Automated imports** | `run_full_import.command` runs at 11:00 and 16:00 GMT+5 without manual intervention |
| 2 | **Phone number enrichment** | Customer phone appears in CRM `Phone` column automatically (100% coverage from API) |
| 3 | **Reduced WhatsApp work** | PDF sending time reduced from 20+ minutes to <5 minutes with zero duplicate/missed sends |
| 4 | **Documented constraints** | All operational rules captured in persistent `.md` files within repo |
| 5 | **Implementation guidance** | Step-by-step instructions for all automation components |

### Non-Goals (Out of Scope)

- Automated customer calls (still requires human for size consultation)
- Official WhatsApp Business API integration (no verified account)
- Real-time order sync (batch processing at fixed times is sufficient)

---

## Current Workflow (As-Is)

### Daily Schedule (GMT+5)

```
┌─────────┬─────────────────────────────────────────────────────────────────┐
│  TIME   │  ACTIVITY                                                       │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  11:00  │  Employee arrives, runs manual import (downloads Excel from     │
│         │  Kaspi Merchant Cabinet → copies to ActiveOrders folder →       │
│         │  runs import script)                                            │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  11:00  │  First wave: Employee calls customers to collect height/weight  │
│  -16:00 │  and assign MY_SIZE. Also manually copies phone numbers from    │
│         │  Kaspi Merchant website order-by-order.                         │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  16:00  │  CUTOFF: Orders after this time ship NEXT day                   │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  16:10  │  Second calling round:                                          │
│         │  - Retry customers who didn't answer earlier                    │
│         │  - Call new orders received 11:00-16:00                         │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  17:00  │  Size assignment completion (depends on order volume)           │
│  -18:40 │                                                                 │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  After  │  1. Employee runs run_build_waybills.command manually           │
│  18:40  │  2. Sends PDFs ONE BY ONE to WhatsApp group (20+ min)           │
│         │  3. Prints each PDF                                             │
│         │  4. Labels packages according to waybills                       │
└─────────┴─────────────────────────────────────────────────────────────────┘
```

### Pain Points

| Problem | Impact |
|---------|--------|
| Manual phone copy-paste | ~30 sec per order × 50 orders = 25 min/day wasted |
| Manual PDF→WhatsApp | ~20 min/day, risk of duplicates/misses |
| No 16:00 auto-refresh | Employee must remember to re-import |
| Inconsistent import timing | Some orders processed late, SLA risk |

---

## Target Workflow (To-Be)

### Daily Schedule (GMT+5) - Automated

```
┌─────────┬─────────────────────────────────────────────────────────────────┐
│  TIME   │  ACTIVITY                                                       │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  11:00  │  🤖 AUTOMATIC: launchd runs run_full_import.command             │
│         │     - Fetches orders from Kaspi API (all 5 stores)              │
│         │     - Phone numbers populated automatically                     │
│         │     - CRM updated with new orders                               │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  11:05  │  Employee arrives, opens CRM - orders already there with phones │
│  -16:00 │  Calls customers, assigns MY_SIZE (no phone lookup needed)      │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  16:00  │  🤖 AUTOMATIC: launchd runs run_full_import.command again       │
│         │     - Fetches any new orders since 11:00                        │
│         │     - Deduplication prevents double-entry                       │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  16:10  │  Employee sees refreshed order list, does second calling round  │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  17:00  │  Size assignment completion                                     │
│  -18:40 │                                                                 │
├─────────┼─────────────────────────────────────────────────────────────────┤
│  After  │  1. Employee runs run_build_waybills.command (manual trigger)   │
│  sizes  │  2. 🤖 SEMI-AUTO: Script sends PDFs to WhatsApp in correct      │
│  done   │     order with visual confirmation                              │
│         │  3. Prints PDFs (same as before)                                │
│         │  4. Labels packages (same as before)                            │
└─────────┴─────────────────────────────────────────────────────────────────┘
```

### Time Savings

| Task | Current | Target | Savings |
|------|---------|--------|---------|
| Phone lookup | 25 min/day | 0 min | 25 min |
| WhatsApp sends | 20 min/day | 3 min | 17 min |
| Import timing | Manual (variable) | Automatic (consistent) | Reliability |
| **Total** | **45 min/day** | **3 min/day** | **42 min/day** |

---

## Constraints

### Operational Constraints

#### 1. Employee Schedule & Timing

| Constraint | Rule |
|------------|------|
| Start time | 11:00 GMT+5 (orders must be ready before this) |
| Second refresh | 16:00 GMT+5 (catch orders placed during work day) |
| Waybill build | Manual trigger only (after ALL sizes assigned) |
| SLA cutoff | Orders ≤16:00 = same-day; >16:00 = next-day |

#### 2. Shipping SLA

```python
def determine_shipping_day(order_created_at: datetime) -> str:
    """
    Same-day shipping for orders until 16:00 GMT+5.
    Next-day shipping for orders after 16:00 GMT+5.
    
    Note: 16:00 sharp is INCLUDED in same-day.
    """
    cutoff = order_created_at.replace(hour=16, minute=0, second=0)
    if order_created_at <= cutoff:
        return "SAME_DAY"
    else:
        return "NEXT_DAY"
```

#### 3. Packaging Rules (Heavy SKUs)

Certain heavy items require **separate packages**. When transitioning order status from «Упаковка» to «передача», the `«Количество мест»` field must reflect actual package count.

**Heavy SKU list** (maintain in `build_daily_waybills.py:HEAVY_ITEMS`):
```python
HEAVY_ITEMS = {
    # Add sku_key or kaspi_name_core patterns for heavy items
    # Example: 'FUR_COAT_MEN_BLACK',
    # Example: 'ELS_JACKET_WINTER_XL',
}
```

**Package counting rules** (already implemented):

| Group Type | Condition | Package Count |
|------------|-----------|---------------|
| NORMAL | qty=1, not heavy | 1 |
| MULTI_QTY | qty≤3, not heavy | 1 |
| MULTI_QTY | qty>3 OR heavy | qty |
| MULTI_LINE | total_qty≤3, no heavy items | 1 |
| MULTI_LINE | heavy items present | heavy_count + 1 (if light items) |

### Technical Constraints

#### 1. Phone Number Sourcing

**Current (manual):**
- Employee copies OrderID from CRM
- Searches in Kaspi Merchant website (for each store account)
- Finds phone number attached to order
- Copy-pastes to `Phone` column

**Target (automated):**
- Kaspi API returns `customer.cellPhone` in order response
- `kaspi_api_client.py` already extracts this to `Order.customer_phone`
- Need: Modify `export_api_orders.py` to include phone in output
- Need: Modify `import_orders_to_crm.py` to write phone to column I

#### 2. WhatsApp Limitations

| Limitation | Implication |
|------------|-------------|
| No verified WhatsApp Business account | Cannot use official WhatsApp Business API |
| Must still call customers | Cannot automate size consultation (height/weight collection) |
| Web automation fragile | WhatsApp Web sessions expire, may require manual re-login |

**Recommended approach:** Use `pywhatkit` or `selenium` with WhatsApp Web for semi-automated PDF sending with human supervision.

#### 3. CRM & Tooling

| Constraint | Detail |
|------------|--------|
| CRM engine | **xlwings** required (openpyxl corrupts external links) |
| CRM structure | Table `tb_SalesRaw` with 18 external links to other workbooks |
| Phone column | Column I (`Phone`) in `SALES_KSP_CRM_1` sheet |
| Idempotency | Deduplication via OrderID prevents double-entry |

#### 4. Manual Verification & Error Risk

Current risks with manual WhatsApp sending:
- Sending same PDF twice
- Missing some PDFs
- Wrong order (should be MULTI_LINE → MULTI_QTY → NORMAL)

Automation must track which PDFs were sent and allow resume on failure.

### Grouping & Sorting Rules

#### Group Type Classification

```
MULTI_LINE: Same order_id, multiple different SKUs
            → Multiple products in one order
            
MULTI_QTY:  Single SKU, quantity > 1
            → Same product, multiple units
            
NORMAL:     Single SKU, quantity = 1
            → Standard single-item order
```

#### PDF Processing Order

```
1. MULTI_LINE PDFs first (highest complexity, most error-prone)
2. MULTI_QTY PDFs second (need to verify multiple items)
3. NORMAL PDFs last (straightforward single items)
```

#### Sorting Within Each Group

```python
def manifest_sort_key(group: WaybillGroup) -> tuple:
    """Sort by: kaspi_name_core → size → sku_key → sku_id"""
    return (
        group.kaspi_name_core or "",
        size_sort_key(group.my_size),
        group.sku_key or "",
        group.sku_id or "",
    )
```

#### Size Ordering

| Category | Order | Example |
|----------|-------|---------|
| Kids | 22 → 24 → 26 → 28 → 30 → 32 → 34 | Ascending numeric |
| Adults | S → M → L → XL → 2XL → 3XL → 4XL | Standard size progression |

**Already implemented in** `build_daily_waybills.py:SIZE_ORDER`:
```python
SIZE_ORDER = {
    # Kids
    '22': 1, '24': 2, '26': 3, '28': 4, '30': 5, '32': 6, '34': 7,
    # Adults
    'S': 10, 'M': 11, 'L': 12, 'XL': 13, '2XL': 14, '3XL': 15, '4XL': 16,
}
```

---

## Implementation Tasks for Opus

### Task 1: Schedule `run_full_import.command` at 11:00 and 16:00 GMT+5

**Task ID:** PHASE12-001  
**Title:** Create launchd plist for automated imports  
**Owner:** Opus

**Description:**  
Create a macOS launchd plist that triggers `run_full_import.command` at 11:00 and 16:00 GMT+5 daily.

**Inputs:**
- Script path: `~/Docs/Autonomous_business/excel_ui/run_full_import.command`
- Timezone: GMT+5 (Astana) = UTC+5
- launchd requires UTC times: 11:00 GMT+5 = 06:00 UTC, 16:00 GMT+5 = 11:00 UTC

**Outputs:**
- `~/Library/LaunchAgents/com.example.kaspi-import.plist`
- Log files at `~/Docs/Autonomous_business/logs/`

**Implementation:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" 
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.kaspi-import</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>~/Docs/Autonomous_business/excel_ui/run_full_import.command</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <array>
        <!-- 11:00 GMT+5 = 06:00 UTC -->
        <dict>
            <key>Hour</key>
            <integer>6</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- 16:00 GMT+5 = 11:00 UTC -->
        <dict>
            <key>Hour</key>
            <integer>11</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>
    
    <key>StandardOutPath</key>
    <string>~/Docs/Autonomous_business/logs/kaspi_import.log</string>
    
    <key>StandardErrorPath</key>
    <string>~/Docs/Autonomous_business/logs/kaspi_import_error.log</string>
    
    <key>WorkingDirectory</key>
    <string>~/Docs/Autonomous_business</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

**Installation commands:**
```bash
# Create logs directory
mkdir -p ~/Docs/Autonomous_business/logs

# Copy plist to LaunchAgents
cp com.example.kaspi-import.plist ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/com.example.kaspi-import.plist

# Verify it's loaded
launchctl list | grep kaspi

# Test run immediately (optional)
launchctl start com.example.kaspi-import
```

**Dependencies:**
- macOS (launchd is macOS-specific)
- Scripts must be executable (`chmod +x run_full_import.command`)
- Environment variables for Kaspi API tokens must be set in shell profile

---

### Task 2: Integrate Phone Number Fetch into Import Flow

**Task ID:** PHASE12-002  
**Title:** Add customer phone to CRM import pipeline  
**Owner:** Opus

**Description:**  
Modify the import pipeline so phone numbers from Kaspi API are written to the CRM's `Phone` column (Column I).

**Current state:**
- `kaspi_api_client.py` already extracts `customer_phone` from API response
- `Order` dataclass has `customer_phone: Optional[str] = None` field
- Phone is NOT written to output Excel or CRM

**Changes required:**

1. **Modify `scripts/export_api_orders.py`**

Add phone column to the DataFrame output:

```python
# In the order-to-row conversion section
row_data = {
    '№ заказа': order.code,
    'Дата поступления заказа': order.created_at.strftime('%d.%m.%Y %H:%M'),
    # ... other fields ...
    'Phone': order.customer_phone or '',  # NEW: Add phone column
}
```

2. **Modify `scripts/import_orders_to_crm.py`**

Update the CRM column mapping:

```python
# In the row preparation section
crm_row = {
    # ... existing columns A-H ...
    'Phone': row.get('Phone', ''),  # Column I
    # ... columns J onwards ...
}
```

**Inputs:**
- `kaspi_api_client.py` (no changes needed)
- `scripts/export_api_orders.py` (modify)
- `scripts/import_orders_to_crm.py` (modify)

**Outputs:**
- Updated `export_api_orders.py` with Phone column in Excel output
- Updated `import_orders_to_crm.py` writing to Column I
- Phone numbers visible in CRM immediately after import

**Phone format handling:**
```python
def normalize_phone(phone: str) -> str:
    """
    Normalize Kaspi phone format for display.
    
    API returns: '7021234567' (10 digits, no +)
    Display as: '+7 702 123 4567' or '7021234567'
    """
    if not phone:
        return ''
    
    # Remove any non-digit characters
    digits = ''.join(c for c in phone if c.isdigit())
    
    # Kaspi phones are 10 digits (without country code) or 11 (with 7)
    if len(digits) == 10:
        return f"7{digits}"  # Prepend 7 for Kazakhstan
    elif len(digits) == 11 and digits.startswith('7'):
        return digits
    else:
        return digits  # Return as-is for unexpected formats
```

**Dependencies:**
- Task 1 completed (scheduling)
- xlwings installed
- CRM file accessible

---

### Task 3: Design WhatsApp PDF Automation

**Task ID:** PHASE12-003  
**Title:** Semi-automated WhatsApp PDF sending  
**Owner:** Opus

**Description:**  
Create a solution to send grouped waybill PDFs to the WhatsApp group chat automatically while maintaining the correct order and tracking sent files.

**Approach: WhatsApp Web Automation with `pywhatkit`**

Given the constraint of no verified WhatsApp Business account, the recommended approach uses `pywhatkit` which automates WhatsApp Web:

**Pros:**
- No API verification needed
- Works with existing WhatsApp account
- Can send files/images

**Cons:**
- Requires active WhatsApp Web session
- Browser must stay open during sending
- May break if WhatsApp Web UI changes

**Implementation:**

1. **Create `scripts/send_waybills_whatsapp.py`**

```python
#!/usr/bin/env python3
"""
Send waybill PDFs to WhatsApp group in correct order.

Usage:
    python scripts/send_waybills_whatsapp.py --date 2025-12-11
    python scripts/send_waybills_whatsapp.py --dry-run
    python scripts/send_waybills_whatsapp.py --resume  # Continue from last sent
"""

import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# pywhatkit for WhatsApp Web automation
# pip install pywhatkit
import pywhatkit

logger = logging.getLogger(__name__)

# Configuration
WHATSAPP_GROUP_ID = "YOUR_GROUP_ID"  # Get from WhatsApp Web URL
SEND_DELAY_SECONDS = 10  # Delay between sends to avoid rate limiting
SENT_LOG_FILE = "sent_pdfs.json"


@dataclass
class PDFSendResult:
    filepath: str
    sent_at: datetime
    success: bool
    error: str = None


def load_sent_log(log_path: Path) -> set:
    """Load set of already-sent PDF filenames."""
    if log_path.exists():
        with open(log_path) as f:
            data = json.load(f)
            return set(data.get('sent', []))
    return set()


def save_sent_log(log_path: Path, sent_files: set):
    """Save updated sent files log."""
    with open(log_path, 'w') as f:
        json.dump({
            'sent': list(sent_files),
            'last_updated': datetime.now().isoformat()
        }, f, indent=2)


def get_pdfs_in_order(output_dir: Path) -> list[Path]:
    """
    Get PDFs in correct sending order:
    1. SPECIAL_multi_line (first)
    2. SPECIAL_multi_qty (second)
    3. NORMAL_singles (last)
    
    Within each, sorted by filename (which embeds kaspi_name_core+size).
    """
    pdfs = []
    
    # Process each store folder
    for store_folder in sorted(output_dir.iterdir()):
        if not store_folder.is_dir():
            continue
        
        # Order: multi_line → multi_qty → normal
        for subdir in ['SPECIAL_multi_line', 'SPECIAL_multi_qty', 'NORMAL_singles']:
            subdir_path = store_folder / subdir
            if subdir_path.exists():
                store_pdfs = sorted(subdir_path.glob('*.pdf'))
                pdfs.extend(store_pdfs)
    
    return pdfs


def send_pdf_to_group(pdf_path: Path, group_id: str, dry_run: bool = False) -> PDFSendResult:
    """Send a single PDF to WhatsApp group."""
    result = PDFSendResult(
        filepath=str(pdf_path),
        sent_at=datetime.now(),
        success=False
    )
    
    if dry_run:
        logger.info(f"DRY RUN: Would send {pdf_path.name}")
        result.success = True
        return result
    
    try:
        # pywhatkit.sendwhats_image also works for PDFs
        # Requires WhatsApp Web to be logged in
        pywhatkit.sendwhats_image(
            receiver=group_id,
            img_path=str(pdf_path),
            caption=pdf_path.stem,  # Filename without extension
            wait_time=15,  # Seconds to wait for WhatsApp Web to load
            tab_close=True
        )
        result.success = True
        logger.info(f"✓ Sent: {pdf_path.name}")
        
    except Exception as e:
        result.error = str(e)
        logger.error(f"✗ Failed: {pdf_path.name} - {e}")
    
    return result


def main(date_str: str, dry_run: bool = False, resume: bool = False):
    """Main sending workflow."""
    # Find today's output folder
    output_base = Path("~/Docs/Autonomous_business/excel_ui/Kaspi_orders/Today")
    
    # Get all PDFs in order
    pdfs = get_pdfs_in_order(output_base)
    logger.info(f"Found {len(pdfs)} PDFs to send")
    
    # Load sent log for resume functionality
    log_path = output_base / SENT_LOG_FILE
    sent_files = load_sent_log(log_path) if resume else set()
    
    # Filter out already-sent files
    if resume and sent_files:
        pdfs = [p for p in pdfs if p.name not in sent_files]
        logger.info(f"Resuming: {len(pdfs)} PDFs remaining")
    
    # Send each PDF
    results = []
    for i, pdf in enumerate(pdfs, 1):
        logger.info(f"[{i}/{len(pdfs)}] Sending: {pdf.name}")
        
        result = send_pdf_to_group(pdf, WHATSAPP_GROUP_ID, dry_run)
        results.append(result)
        
        if result.success:
            sent_files.add(pdf.name)
            save_sent_log(log_path, sent_files)
        else:
            # Stop on first failure, user can resume later
            logger.error(f"Stopping due to failure. Use --resume to continue.")
            break
        
        # Delay between sends
        if i < len(pdfs) and not dry_run:
            logger.info(f"Waiting {SEND_DELAY_SECONDS}s before next send...")
            time.sleep(SEND_DELAY_SECONDS)
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    logger.info(f"\nComplete: {success_count}/{len(results)} sent successfully")
    
    return results
```

2. **Create `.command` launcher**

```bash
#!/bin/bash
# send_waybills_whatsapp.command
# Double-click to send waybills to WhatsApp group

cd ~/Docs/Autonomous_business
source .venv/bin/activate 2>/dev/null || true

echo "========================================"
echo "  WhatsApp Waybill Sender"
echo "========================================"
echo ""
echo "This will send all grouped PDFs to the WhatsApp group."
echo "Make sure WhatsApp Web is logged in and visible."
echo ""
read -p "Press Enter to start (Ctrl+C to cancel)..."

python scripts/send_waybills_whatsapp.py --verbose

echo ""
echo "Done! Press Enter to close..."
read
```

**Alternative approach: Selenium with WhatsApp Web**

If `pywhatkit` proves unreliable, a more robust alternative using Selenium:

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

def send_via_selenium(pdf_path: Path, group_name: str):
    """Send PDF via Selenium automation of WhatsApp Web."""
    # Requires: chromedriver, existing WhatsApp Web session
    
    driver = webdriver.Chrome()
    driver.get("https://web.whatsapp.com")
    
    # Wait for user to scan QR if needed
    input("Scan QR code if needed, then press Enter...")
    
    # Find and click the group
    search_box = driver.find_element(By.XPATH, "//div[@contenteditable='true']")
    search_box.send_keys(group_name)
    time.sleep(2)
    
    # Click attachment button
    attach_btn = driver.find_element(By.XPATH, "//span[@data-icon='attach-menu-plus']")
    attach_btn.click()
    
    # Upload file
    file_input = driver.find_element(By.XPATH, "//input[@type='file']")
    file_input.send_keys(str(pdf_path))
    
    # Send
    send_btn = driver.find_element(By.XPATH, "//span[@data-icon='send']")
    send_btn.click()
```

**Inputs:**
- Output from `run_build_waybills.command`
- WhatsApp group ID or name
- Active WhatsApp Web session

**Outputs:**
- PDFs sent to WhatsApp group in correct order
- `sent_pdfs.json` log for resume capability
- Console output showing progress

**Dependencies:**
- `pywhatkit` package (`pip install pywhatkit`)
- WhatsApp Web logged in
- Chrome browser (for pywhatkit's web automation)

---

### Task 4: Document Constraints in Persistent `.md` Files

**Task ID:** PHASE12-004  
**Title:** Create and update repository documentation  
**Owner:** Opus

**Description:**  
Ensure all operational constraints, workflow rules, and API details are captured in persistent documentation within the repository.

**Files to create/update:**

1. **CREATE: `docs/DAILY_WORKFLOW.md`**
   - Full employee schedule
   - Step-by-step process
   - SLA rules (16:00 cutoff)

2. **CREATE: `docs/PACKAGING_RULES.md`**
   - Heavy SKU list
   - Package counting logic
   - «Количество мест» field requirements

3. **UPDATE: `docs/Phase_11_Daily_Kaspi_Workflow.md`**
   - **FIX:** Change "Use openpyxl, NOT xlwings" to "Use xlwings for CRM writes"
   - Add phone column population from API

4. **UPDATE: `docs/KASPI_API_INTEGRATION.md`**
   - Document phone number extraction
   - Add `customer.cellPhone` field mapping

5. **CREATE: `config/heavy_items.yaml`**
   - List of heavy SKUs requiring separate packages
   - Easier to maintain than hardcoded Python list

**Template for `heavy_items.yaml`:**
```yaml
# Heavy items requiring separate packages
# Add sku_key or kaspi_name_core patterns

heavy_sku_keys:
  - FUR_COAT_MEN_BLACK
  - ELS_JACKET_WINTER_XXXL
  
heavy_name_patterns:
  - "пуховик"
  - "зимняя куртка"
  
# Items over this weight (kg) are always heavy
heavy_weight_threshold: 2.0
```

**Inputs:**
- Current operational knowledge
- Existing documentation in repo

**Outputs:**
- New `.md` files in `docs/` folder
- Updated `config/` with `heavy_items.yaml`
- All constraints documented for future reference

**Dependencies:**
- None

---

### Task 5: Step-by-Step Implementation Instructions

**Task ID:** PHASE12-005  
**Title:** Provide complete implementation guide  
**Owner:** Opus

**Description:**  
Compile a step-by-step implementation checklist that Adil can follow to deploy all Phase 12 automation.

**Implementation Guide:**

```markdown
# Phase 12 Implementation Checklist

## Prerequisites

- [ ] macOS with launchd
- [ ] Python 3.10+ with venv activated
- [ ] xlwings installed (`pip install xlwings`)
- [ ] pywhatkit installed (`pip install pywhatkit`)
- [ ] Kaspi API tokens in environment variables
- [ ] Chrome browser (for WhatsApp automation)

## Step 1: Install Python Dependencies

```bash
cd ~/Docs/Autonomous_business
source .venv/bin/activate
pip install pywhatkit selenium
```

## Step 2: Update Import Scripts for Phone Numbers

```bash
# Opus will provide exact code changes
# Apply changes to:
# - scripts/export_api_orders.py
# - scripts/import_orders_to_crm.py
```

## Step 3: Create Logs Directory

```bash
mkdir -p ~/Docs/Autonomous_business/logs
```

## Step 4: Install launchd Schedule

```bash
# Create plist file (Opus provides content)
nano ~/Library/LaunchAgents/com.example.kaspi-import.plist

# Load the agent
launchctl load ~/Library/LaunchAgents/com.example.kaspi-import.plist

# Verify it's running
launchctl list | grep kaspi
```

## Step 5: Test Manual Run

```bash
# Test the full import
./excel_ui/run_full_import.command

# Verify phone numbers appear in CRM column I
```

## Step 6: Setup WhatsApp Web

1. Open Chrome
2. Go to https://web.whatsapp.com
3. Scan QR code with phone
4. Leave tab open (for automation)

## Step 7: Test WhatsApp Sender (Dry Run)

```bash
python scripts/send_waybills_whatsapp.py --dry-run
```

## Step 8: Configure WhatsApp Group ID

1. In WhatsApp Web, open target group
2. Copy group ID from URL or use group name
3. Update WHATSAPP_GROUP_ID in script

## Step 9: Document Heavy Items

```bash
# Edit config/heavy_items.yaml
# Add your heavy SKUs
```

## Step 10: Verify Schedule Works

Wait for 11:00 or 16:00, then check:
- [ ] Log file shows execution
- [ ] CRM has new orders
- [ ] Phone numbers populated
```

**Inputs:**
- All previous tasks

**Outputs:**
- Complete implementation checklist
- Verification steps for each component

**Dependencies:**
- Tasks 1-4 completed

---

### Task 6: Additional Considerations (Catch-All)

**Task ID:** PHASE12-006  
**Title:** Additional automation concerns  
**Owner:** Opus

**Description:**  
Address additional important considerations not explicitly listed but implied by the workflow.

**6.1 Logging & Monitoring**

Create centralized logging for all automation:

```python
# config/logging_config.py
LOGGING_CONFIG = {
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '~/Docs/Autonomous_business/logs/automation.log',
            'maxBytes': 10_000_000,  # 10MB
            'backupCount': 5,
        },
        'telegram': {
            'class': 'telegram_handler.TelegramHandler',
            'token': os.environ.get('TELEGRAM_BOT_TOKEN'),
            'chat_id': '687884487',  # Adil's chat
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'telegram']
    }
}
```

**6.2 Error Notifications**

Send Telegram alerts on failures:

```python
def send_error_alert(error: str, script_name: str):
    """Send error notification to Telegram."""
    message = f"⚠️ {script_name} failed:\n{error}"
    # Use existing Telegram bot from Phase 9
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={'chat_id': '687884487', 'text': message}
    )
```

**6.3 Mac Sleep Prevention**

Ensure Mac doesn't sleep during scheduled runs:

```bash
# Add to launchd plist KeepAlive section
# Or use caffeinate in the .command script:
caffeinate -i python scripts/export_api_orders.py
```

**6.4 Token Refresh Handling**

Kaspi tokens may expire. Add validation:

```python
def validate_api_token(store_code: str) -> bool:
    """Check if token is still valid before full import."""
    client = KaspiAPIClient(store_code)
    try:
        # Make a minimal API call
        client.list_orders(state='NEW', page_size=1)
        return True
    except KaspiAuthError:
        logger.error(f"Token expired for {store_code}")
        send_error_alert(f"Kaspi token expired for {store_code}", "token_check")
        return False
```

**6.5 CRM Backup Before Write**

Create automatic backup before each import:

```python
def backup_crm():
    """Create timestamped backup of CRM file."""
    src = Path("~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx")
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = backup_dir / f"SALES_KSP_CRM_V3_{timestamp}.xlsx"
    
    shutil.copy2(src, dst)
    logger.info(f"Backup created: {dst}")
    
    # Keep only last 7 days of backups
    cleanup_old_backups(backup_dir, days=7)
```

---

## Edge Cases & Failure Handling

### Edge Case 1: No Orders at Import Time

**Condition:** 11:00 or 16:00 import finds 0 active orders

**Expected behavior:**
- Log "No active orders found" (not an error)
- Send informational Telegram message (optional)
- CRM unchanged (no empty rows added)
- Exit code 0 (success)

**Implementation:**
```python
if len(orders) == 0:
    logger.info("No active orders found for import")
    return 0  # Success, just nothing to do
```

### Edge Case 2: Orders Near 16:00 Cutoff

**Condition:** Order created at 16:00, 16:01, or 16:02

**Rule:**
- Order created at exactly 16:00:00 → SAME_DAY shipping
- Order created at 16:00:01 or later → NEXT_DAY shipping

**Implementation:**
```python
def get_shipping_day(created_at: datetime) -> str:
    """
    Cutoff is 16:00:00.000 GMT+5 inclusive.
    """
    cutoff = created_at.replace(hour=16, minute=0, second=0, microsecond=0)
    return "SAME_DAY" if created_at <= cutoff else "NEXT_DAY"
```

**How it appears in workflow:**
- 16:00 import captures orders up to 16:00 (same-day)
- Orders after 16:00 appear in next day's 11:00 import
- `planned_delivery_date` from API is the source of truth

### Edge Case 3: Missing or Invalid Phone Numbers

**Condition:** 
- API returns `null` for customer phone
- Phone format unexpected (not 10-11 digits)
- Multiple phone numbers (edge case in API)

**Expected behavior:**
- Write empty string to Phone column
- Log warning with OrderID
- Flag in separate "needs_manual_phone" log file

**Implementation:**
```python
def process_phone(phone: Optional[str], order_code: str) -> str:
    """Validate and normalize phone number."""
    if not phone:
        logger.warning(f"Order {order_code}: No phone number from API")
        return ""
    
    digits = ''.join(c for c in phone if c.isdigit())
    
    if len(digits) not in (10, 11):
        logger.warning(f"Order {order_code}: Invalid phone format: {phone}")
        return ""
    
    return digits
```

### Edge Case 4: API Failures or Timeouts

**Condition:**
- Kaspi API returns 5xx error
- Network timeout
- Rate limit (429)

**Expected behavior:**
- Retry up to 3 times with exponential backoff (already in client)
- After all retries fail: log error, send Telegram alert, exit with code 1
- Partial success: record which stores succeeded, allow manual rerun

**Implementation:**
```python
# Already handled in kaspi_api_client.py
# KaspiAPIClient has built-in retry logic

# Additional handling in import script:
def import_all_stores():
    results = {}
    for store in STORES:
        try:
            results[store] = import_store(store)
        except KaspiAPIError as e:
            logger.error(f"Failed to import {store}: {e}")
            send_error_alert(f"Import failed for {store}", "import")
            results[store] = {"error": str(e)}
    
    # Return success only if all stores succeeded
    return all('error' not in r for r in results.values())
```

### Edge Case 5: WhatsApp Automation Failures

**Condition:**
- WhatsApp Web session expired
- Browser closed during sending
- Network disconnection mid-batch

**Expected behavior:**
- Stop immediately on failure
- Record last successfully sent PDF
- Allow `--resume` flag to continue from last position
- Never send same PDF twice

**Implementation:**
```python
# Already in Task 3 send_waybills_whatsapp.py:
# - sent_pdfs.json tracks what was sent
# - --resume flag skips already-sent files
# - Exits on first failure rather than continuing
```

### Edge Case 6: Duplicate or Missing PDF Sends

**Condition:**
- Script runs twice accidentally
- PDF file deleted between runs
- Filename collision

**Prevention:**
1. Unique identifiers in `sent_pdfs.json` (filename + date)
2. Check file exists before attempting send
3. Atomic save of sent log after each success

**Implementation:**
```python
def send_pdf_safe(pdf_path: Path, sent_log: set) -> bool:
    """Send PDF with duplicate/missing prevention."""
    
    # Check for duplicate
    if pdf_path.name in sent_log:
        logger.warning(f"Skipping duplicate: {pdf_path.name}")
        return True  # Considered success (already done)
    
    # Check file exists
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        return False
    
    # Attempt send
    success = send_pdf_to_group(pdf_path)
    
    # Record success
    if success:
        sent_log.add(pdf_path.name)
        save_sent_log(sent_log)  # Immediate save
    
    return success
```

### Edge Case 7: Incorrect Grouping/Sorting

**Condition:**
- kaspi_name_core extraction fails
- Size column empty (MY_SIZE not filled)
- Unexpected characters in product names

**Expected behavior:**
- Log warning for each malformed record
- Group as "UNKNOWN" or skip from waybill processing
- Require human review before sending to WhatsApp

**Implementation:**
```python
def validate_order_for_grouping(order: OrderItem) -> list[str]:
    """Return list of validation errors, empty if valid."""
    errors = []
    
    if not order.kaspi_name_core:
        errors.append(f"Order {order.order_id}: Missing kaspi_name_core")
    
    if not order.my_size:
        errors.append(f"Order {order.order_id}: MY_SIZE not filled")
    
    return errors

# In main processing:
def process_orders(orders):
    valid = []
    invalid = []
    
    for order in orders:
        errors = validate_order_for_grouping(order)
        if errors:
            invalid.append((order, errors))
        else:
            valid.append(order)
    
    if invalid:
        logger.warning(f"{len(invalid)} orders have validation errors")
        write_invalid_orders_report(invalid)
    
    return valid
```

### Edge Case 8: Heavy SKU Packaging Misconfiguration

**Condition:**
- Heavy item not in `heavy_items.yaml`
- `«Количество мест»` field set incorrectly
- Mixed heavy/light items in MULTI_LINE order

**Prevention:**
- Validation step before status transition
- Log warning if package count might be wrong

**Implementation:**
```python
def validate_package_count(group: WaybillGroup) -> tuple[bool, str]:
    """Validate package count before API status update."""
    expected = count_packages([group])
    
    # Check if any items should be heavy but aren't configured
    for item in group.items:
        weight = get_item_weight(item.sku_key)
        if weight and weight > HEAVY_WEIGHT_THRESHOLD:
            if not is_heavy_item(item):
                return False, f"Item {item.sku_key} weighs {weight}kg but not marked heavy"
    
    return True, f"Expected packages: {expected}"
```

---

## Open Questions & Assumptions

### Open Questions

| # | Question | Impact | Default Assumption |
|---|----------|--------|-------------------|
| 1 | What is the exact WhatsApp group ID/name? | Required for automation | Will configure during implementation |
| 2 | Should 16:00 cutoff be configurable? | SLA changes | Hardcoded to 16:00 GMT+5 |
| 3 | How many days of sent_pdfs.json to retain? | Disk space | 7 days rolling |
| 4 | Should failed imports retry automatically? | Reliability | No - alert and wait for manual intervention |
| 5 | Is there a list of all heavy SKUs? | Package counting | Start with empty list, add as discovered |

### Assumptions

| # | Assumption | If Wrong |
|---|------------|----------|
| 1 | Kaspi API always returns phone for delivery orders | Need manual fallback column |
| 2 | Mac is awake/powered at 11:00 and 16:00 | Use Wake on LAN or cloud scheduling |
| 3 | WhatsApp Web session stays alive for days | Add session check before sending |
| 4 | Order volumes under 200/day | May need batch processing optimization |
| 5 | xlwings works headless | May need visible Excel for some operations |

---

## Implementation Notes

### Idempotency Requirements

All scripts must be safe to re-run:

| Script | Idempotency Mechanism |
|--------|----------------------|
| `export_api_orders.py` | Overwrites ActiveOrders.xlsx (no accumulation) |
| `import_orders_to_crm.py` | Dedup by OrderID (existing orders skipped) |
| `build_daily_waybills.py` | Clears output folder before build |
| `send_waybills_whatsapp.py` | sent_pdfs.json prevents duplicates |

### Logging Standards

All scripts should:
1. Log to both console and file
2. Include timestamp and log level
3. Log OrderID for any order-specific issues
4. Log start/end with summary counts

### Testing Approach

Before deploying:
1. Run with `--dry-run` flag (all scripts support this)
2. Test with single store first (`--store UNIVERSAL`)
3. Verify CRM changes in backup before committing
4. Test WhatsApp sender with 1-2 PDFs manually first

### Rollback Plan

If automation causes issues:
1. `launchctl unload ~/Library/LaunchAgents/com.example.kaspi-import.plist`
2. Restore CRM from backup folder
3. Revert to manual workflow
4. Debug using logs in `/logs/` folder

---

## Examples

### Example 1: Grouping & Sorting PDFs for WhatsApp

**Input orders:**

| OrderID | store_sku_key | kaspi_name_core | size | qnt |
|---------|---------------|-----------------|------|-----|
| 001 | UNI_CL_SHIRT | Рубашка мужская | L | 1 |
| 002 | UNI_CL_SHIRT | Рубашка мужская | M | 1 |
| 003 | UNI_CL_SHIRT | Рубашка мужская | XL | 3 |
| 004 | UNI_CL_PANTS | Брюки классические | L | 1 |
| 004 | UNI_CL_BELT | Ремень кожаный | - | 1 |

**Grouping result:**

| Group Type | OrderID | Items |
|------------|---------|-------|
| MULTI_LINE | 004 | Брюки L-1, Ремень -1 |
| MULTI_QTY | 003 | Рубашка XL-3 |
| NORMAL | 002 | Рубашка M-1 |
| NORMAL | 001 | Рубашка L-1 |

**Final sorted PDF order for WhatsApp:**

1. `Местовая-1_Брюки-L-1(1-2)_Ремень--1(2-2).pdf` (MULTI_LINE)
2. `Местовая-1_Рубашка_XL-3.pdf` (MULTI_QTY)
3. `Рубашка_L-1.pdf` (NORMAL, L comes after M)
4. `Рубашка_M-1.pdf` (NORMAL, sorted by size)

Wait, that's wrong - sizes should be ascending:

**Corrected sorted PDF order:**

1. `Местовая-1_Брюки-L-1(1-2)_Ремень--1(2-2).pdf` (MULTI_LINE)
2. `Местовая-1_Рубашка_XL-3.pdf` (MULTI_QTY)
3. `Рубашка_M-1.pdf` (NORMAL, M=11)
4. `Рубашка_L-1.pdf` (NORMAL, L=12)

### Example 2: Phone Number Enrichment

**Before (manual workflow):**

```
11:05 - Employee opens CRM, sees Order #12345
11:06 - Opens Kaspi Merchant, searches "12345"
11:07 - Finds order, copies phone "7021234567"
11:08 - Pastes into CRM column I
11:09 - Calls customer to ask height/weight
...repeat for each order...
```

**After (automated workflow):**

```
06:00 UTC - launchd triggers run_full_import.command
06:01 - export_api_orders.py fetches orders including phone
06:02 - import_orders_to_crm.py writes to CRM with Phone in column I
...
11:00 - Employee opens CRM, phone already populated
11:01 - Immediately calls first customer
```

**Time saved:** ~30 seconds per order × 50 orders = **25 minutes/day**

### Example 3: Edge Case - Order at 16:02

**Scenario:**
- Customer places order at 16:02 GMT+5 on Monday
- Order status: KASPI_DELIVERY

**Processing:**

```
Monday 16:00 import: Order NOT captured (created after cutoff)
Tuesday 11:00 import: Order captured
  → planned_delivery_date: Tuesday
  → Shipping day: Tuesday (next day from Monday perspective)
```

**CRM entry shows:**
- Date column: Tuesday's date
- This order is processed with Tuesday's batch

---

## Verification Checklist

Use this checklist to verify the implementation is complete:

### Scheduling
- [ ] launchd plist created at `~/Library/LaunchAgents/com.example.kaspi-import.plist`
- [ ] Agent loaded (`launchctl list | grep kaspi`)
- [ ] Logs directory exists (`/logs/`)
- [ ] Test run at scheduled time produces logs

### Phone Number Import
- [ ] `export_api_orders.py` includes Phone column in output
- [ ] `import_orders_to_crm.py` writes to column I
- [ ] Phone appears in CRM after import
- [ ] Phone format normalized (10-11 digits)

### WhatsApp Automation
- [ ] `pywhatkit` installed
- [ ] WhatsApp Web logged in
- [ ] Group ID configured
- [ ] Dry run completes successfully
- [ ] sent_pdfs.json tracks sent files
- [ ] Resume functionality works

### Documentation
- [ ] `docs/DAILY_WORKFLOW.md` created
- [ ] `docs/PACKAGING_RULES.md` created
- [ ] `config/heavy_items.yaml` created
- [ ] Phase 11 spec updated (xlwings note)

### Error Handling
- [ ] API failure sends Telegram alert
- [ ] CRM backup created before writes
- [ ] All edge cases have handling

---

## Document Maintenance

**Update this document when:**
- New heavy SKUs are discovered
- SLA timing changes
- New stores are added
- WhatsApp group changes
- API behavior changes

**Location:** `~/Docs/Autonomous_business/docs/Opus_Plan_Phase_12.md`

**Last updated:** 2025-12-11
