# Phase 9.5 — Kaspi Order Automation
## Mega Build Specification

**Date:** 2025-12-06  
**Executor:** Claude Sonnet  
**Estimated Total Time:** 25-35 hours agent execution  
**Prerequisites:** Phase 8 complete ✅

---

## Executive Summary

Phase 9.5 migrates legacy semi-automated order processing scripts from `kaspi_etl` repo into Project 3's unified architecture, then integrates Kaspi API for autonomous multi-store order management. This eliminates the current **60+ min/day** manual Chrome profile switching across 5 Kaspi stores.

**What:** Two-phase implementation — (1) rebuild legacy `ActiveOrders → CRM` ingestion + PDF waybill grouping, (2) API-based order sync with auto-status updates and parallel waybill downloads.

**Why:** Current workflow requires manual export from each store, profile switching, and xlwings-based Excel manipulation. API integration enables real-time order visibility across all stores from a single endpoint.

**Expected ROI:**
- **Phase 1:** -30 min/day (unified ingestion replaces per-store Excel exports)
- **Phase 2:** -45 min/day (API polling replaces manual downloads) + reduced errors
- **Annual value:** ~450 hours saved × $15/hr opportunity cost = **$6,750** + error reduction

---

## Current State Analysis

### Legacy Workflow (from `pdf_sales_scripts_wrokflow_V3.md`)

| Component | Location | Function | Dependency |
|-----------|----------|----------|------------|
| `import_active_orders.py` | `docs/ops/kaspi/` | ActiveOrders*.xlsx → SALES_KSP_CRM_V3.xlsx | xlwings, psutil |
| `build_kaspi_orders.py` | `docs/ops/kaspi/` | Waybill ZIP + Excel → Grouped PDFs | PyPDF2, pandas |
| `SALES_KSP_CRM_V3.xlsx` | `docs/ops/kaspi/` | Master CRM database | Excel ListObject "CRM" |

### Current Pain Points

1. **Chrome profile switching** — 5 stores × 3 actions × 4 min = 60+ min/day
2. **xlwings dependency** — Requires Excel running, macOS-specific quirks
3. **No real-time visibility** — Orders only visible after manual export
4. **Waybill grouping** — Manual ZIP download + script execution
5. **Duplicate detection** — xlwings-based, fragile on Excel formula cells

### Kaspi API Capabilities (from `Kaspi_API_doc_CL.md`)

| Capability | Endpoint | Available |
|------------|----------|-----------|
| List orders | `GET /shop/api/v2/orders` | ✅ Yes |
| Filter by status | `filter[orders][state]=NEW,ACCEPTED` | ✅ Yes |
| Filter by date | `filter[orders][creationDateGe/Le]` | ✅ Yes |
| Get order entries | `GET /shop/api/v2/orderentries/{id}` | ✅ Yes |
| Get waybill URL | `attributes.kaspiDelivery.waybill` | ✅ Yes |
| Accept order | `POST /orders/{code}/accept` | ✅ Yes |
| Ship order | `POST /orders/{code}/ship` | ✅ Yes |
| Complete order | `POST /orders` + security code | ✅ Yes |
| Cancel order | `POST /orders` + cancellation reason | ✅ Yes |
| Generate custom PDF | — | ❌ No (Manual Fallback Required) |

---

## Phase 1: Legacy Migration

**Goal:** Rebuild core order processing without xlwings dependency, integrated into Project 3 architecture.

### Section A: Discovery & Audit

#### TASK-110: Audit legacy script logic

**Purpose:** Document exact behavior of legacy scripts before migration.

**Actions:**
1. Read `docs/ops/kaspi/import_active_orders.py` (21,486 chars per doc)
2. Read `docs/ops/kaspi/build_kaspi_orders.py` (18,300 chars per doc)
3. Extract: column mappings, filter logic, dedup rules, output formats

**Output:** `docs/legacy_kaspi_audit.md` with:
- Input/output schemas
- Filter conditions (Russian status strings)
- Deduplication logic
- Edge case handling

**Effort:** 2 hours  
**Dependencies:** None

---

#### TASK-111: Map legacy columns to Project 3 schema

**Purpose:** Create translation layer between Kaspi export format and `fact_sales` schema.

**Input:** Legacy column names (Russian):
```
№ заказа, Статус, Дата создания, Плановая дата передачи курьеру,
Название товара, Артикул, Цена, Склад, Требуется подписание
```

**Output:** `config/kaspi_column_map.yaml`:
```yaml
kaspi_export:
  order_id: "№ заказа"
  status: "Статус"
  created_date: "Дата создания"
  planned_date: "Плановая дата передачи курьеру"
  product_name: "Название товара"
  article: "Артикул"
  price: "Цена"
  store: "Склад"
  signature_required: "Требуется подписание"
  
status_filter:
  awaiting_courier: "Ожидает передачи курьеру"
  signature_not_required: "Не требуется"
```

**Effort:** 1 hour  
**Dependencies:** TASK-110

---

### Section B: Order Ingestion Rebuild

#### TASK-112: Create `core/parsers/kaspi_export_parser.py`

**Purpose:** Parse Kaspi ActiveOrders Excel exports without xlwings.

**File:** `core/parsers/kaspi_export_parser.py`

**Functions:**
```python
def parse_active_orders(filepath: Path) -> List[Dict]:
    """
    Parse Kaspi ActiveOrders*.xlsx export file.
    
    Args:
        filepath: Path to ActiveOrders Excel file
        
    Returns:
        List of order dicts with normalized column names
    """

def filter_for_shipment(orders: List[Dict], target_date: date = None) -> List[Dict]:
    """
    Filter orders ready for shipment.
    
    Conditions:
        - Status == "Ожидает передачи курьеру"
        - Signature required == "Не требуется" (if column exists)
        - Planned date <= target_date (default: today)
    """

def normalize_order(raw: Dict) -> Dict:
    """
    Normalize raw Kaspi export row to Project 3 schema.
    
    Returns:
        Dict with keys: order_id, sku_id, price_kzt, store_code, 
                       status, created_at, planned_date, kaspi_offer_name
    """
```

**Effort:** 3 hours  
**Dependencies:** TASK-111

---

#### TASK-113: Create `scripts/ingest_kaspi_export.py`

**Purpose:** CLI to ingest ActiveOrders exports into fact_sales_raw.

**File:** `scripts/ingest_kaspi_export.py`

**Usage:**
```bash
# Single file
python scripts/ingest_kaspi_export.py data_raw/ActiveOrders_2025-12-06.xlsx

# Directory scan (all ActiveOrders*.xlsx)
python scripts/ingest_kaspi_export.py --scan-dir ~/Downloads

# With date filter
python scripts/ingest_kaspi_export.py --scan-dir ~/Downloads --target-date 2025-12-06

# Dry run
python scripts/ingest_kaspi_export.py data_raw/ActiveOrders.xlsx --dry-run
```

**Logic:**
1. Parse Excel files using `kaspi_export_parser`
2. Filter for shipment-ready orders
3. UPSERT to `fact_sales_raw` on `(order_id, sku_id, store_code)`
4. Auto-create `dim_sku_size` entries if missing (--auto-create-sku flag)
5. Log: inserted, updated, skipped counts

**Effort:** 3 hours  
**Dependencies:** TASK-112

---

#### TASK-114: Create `fact_orders_kaspi` table

**Purpose:** Track order lifecycle separately from sales (orders can be cancelled before becoming sales).

**Migration:** `scripts/migrate_011.py`

```sql
CREATE TABLE IF NOT EXISTS fact_orders_kaspi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    store_code TEXT NOT NULL,
    channel_code TEXT DEFAULT 'KSP',
    
    -- Order details
    kaspi_offer_name TEXT,
    sku_key TEXT,
    sku_id TEXT,
    my_size TEXT,
    quantity INTEGER DEFAULT 1,
    unit_price_kzt REAL,
    
    -- Dates
    created_at TEXT,
    planned_shipment_date TEXT,
    actual_shipment_date TEXT,
    
    -- Status tracking
    kaspi_status TEXT,  -- Raw Kaspi status
    internal_status TEXT DEFAULT 'NEW',  -- NEW, READY, SHIPPED, COMPLETED, CANCELLED
    status_updated_at TEXT,
    
    -- Waybill
    waybill_url TEXT,
    waybill_number TEXT,
    waybill_downloaded INTEGER DEFAULT 0,
    
    -- Audit
    source TEXT DEFAULT 'EXCEL_EXPORT',  -- EXCEL_EXPORT, API
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(order_id, sku_id, store_code)
);

CREATE INDEX idx_orders_kaspi_status ON fact_orders_kaspi(internal_status);
CREATE INDEX idx_orders_kaspi_date ON fact_orders_kaspi(planned_shipment_date);
CREATE INDEX idx_orders_kaspi_store ON fact_orders_kaspi(store_code);
```

**Effort:** 1 hour  
**Dependencies:** None

---

### Section C: PDF Waybill Grouping

#### TASK-115: Create `core/waybill/pdf_grouper.py`

**Purpose:** Group waybill PDFs by store/product/size without external dependencies.

**File:** `core/waybill/pdf_grouper.py`

**Functions:**
```python
@dataclass
class WaybillGroup:
    group_type: str  # NORMAL, MULTI_LINE, MULTI_QTY
    store_code: str
    kaspi_name_core: str
    my_size: str
    total_quantity: int
    order_ids: List[str]
    pdf_paths: List[Path]
    output_filename: str

def extract_waybills_from_zip(zip_path: Path, temp_dir: Path) -> Dict[str, Path]:
    """
    Extract waybill PDFs from Kaspi ZIP.
    
    Returns:
        Dict mapping order_id -> PDF path
        (parses KASPI_SHOP-<OrderID>.pdf pattern)
    """

def group_orders_for_shipment(
    orders: List[Dict],
    waybill_map: Dict[str, Path]
) -> Tuple[List[WaybillGroup], List[str]]:
    """
    Group orders into waybill bundles.
    
    Logic:
        - MULTI_QTY: Same kaspi_name_core, quantity > 1 (merge across orders)
        - MULTI_LINE: Same order_id appears on multiple lines
        - NORMAL: Single item, single quantity
        
    Returns:
        (groups, missing_order_ids)
    """

def merge_pdfs(pdf_paths: List[Path], output_path: Path) -> Path:
    """Merge multiple PDFs into single file using PyPDF2."""
```

**Effort:** 4 hours  
**Dependencies:** TASK-112

---

#### TASK-116: Create `scripts/build_waybill_bundles.py`

**Purpose:** CLI to generate grouped waybill PDFs for shipment.

**File:** `scripts/build_waybill_bundles.py`

**Usage:**
```bash
# From Excel + ZIP
python scripts/build_waybill_bundles.py \
    --orders data_raw/ActiveOrders_2025-12-06.xlsx \
    --waybills data_raw/waybills_2025-12-06.zip \
    --output-dir exports/2025-12-06/waybills/

# From database (orders already ingested)
python scripts/build_waybill_bundles.py \
    --from-db \
    --date 2025-12-06 \
    --waybills data_raw/waybills.zip \
    --output-dir exports/2025-12-06/waybills/
```

**Output Structure:**
```
exports/2025-12-06/waybills/
├── NORMAL_singles/
│   └── PP1___L___LINE52_BLACK.pdf
├── SPECIAL_multi_line/
│   └── PP1___ORDER123456_2items.pdf
├── SPECIAL_multi_qty/
│   └── LINE52_BLACK___qnt5.pdf
├── manifest.csv
├── missing_orders.csv
└── build_log.csv
```

**Effort:** 3 hours  
**Dependencies:** TASK-115

---

### Section D: Testing Phase 1

#### TASK-117: Create `tests/test_kaspi_export_parser.py`

**Tests:**
- Parse valid ActiveOrders file
- Handle Russian column names
- Date parsing (DD.MM.YYYY format, dayfirst=True)
- Status filtering logic
- Missing columns handling
- Encoding edge cases (Cyrillic in product names)

**Effort:** 2 hours  
**Dependencies:** TASK-112

---

#### TASK-118: Create `tests/test_pdf_grouper.py`

**Tests:**
- ZIP extraction with various naming patterns
- NORMAL grouping (1 order, 1 item, 1 qty)
- MULTI_QTY grouping (same product, qty > 1)
- MULTI_LINE grouping (order with multiple SKUs)
- Missing waybill handling
- PDF merge functionality

**Effort:** 2 hours  
**Dependencies:** TASK-115

---

### Section E: Pipeline Integration Phase 1

#### TASK-119: Add kaspi export ingestion to daily pipeline

**File:** Update `scripts/run_daily_pipeline.py`

**New Step:** `step_ingest_kaspi_exports()`
- Scan `data_raw/` for today's ActiveOrders*.xlsx
- Ingest to fact_orders_kaspi
- Report: new orders, duplicates skipped

**Effort:** 1 hour  
**Dependencies:** TASK-113, TASK-114

---

## Phase 2: API Integration

**Goal:** Replace manual exports with automated API polling and order management.

### Section F: API Client

#### TASK-120: Create `core/integrations/kaspi_api_client.py`

**Purpose:** Robust Kaspi API client with retry logic and multi-store support.

**File:** `core/integrations/kaspi_api_client.py`

**Class:**
```python
class KaspiAPIClient:
    """
    Kaspi Shop API client with retry and rate limiting.
    
    Usage:
        client = KaspiAPIClient(store_code='PP1')
        orders = client.get_orders(state='NEW', since=yesterday)
    """
    
    def __init__(self, store_code: str, token: str = None):
        """
        Initialize client for specific store.
        
        Token loaded from env: KASPI_TOKEN_{store_code}
        """
    
    def get_orders(
        self,
        state: str = None,
        delivery_mode: str = None,
        created_after: datetime = None,
        created_before: datetime = None,
        page_size: int = 100
    ) -> List[Dict]:
        """
        Fetch orders with pagination.
        
        States: NEW, ACCEPTED_BY_MERCHANT, ASSEMBLE, KASPI_DELIVERY, 
                COMPLETED, CANCELLED, RETURNED
        """
    
    def get_order_entries(self, order_id: str) -> List[Dict]:
        """Get line items for an order."""
    
    def accept_order(self, order_code: str) -> bool:
        """Accept order (status -> ACCEPTED_BY_MERCHANT)."""
    
    def assemble_order(self, order_code: str, num_parcels: int = 1) -> bool:
        """Mark order as assembled for Kaspi Delivery."""
    
    def ship_order(self, order_code: str) -> bool:
        """Mark order as shipped."""
    
    def cancel_order(self, order_code: str, reason: str) -> bool:
        """Cancel order with reason."""
    
    def get_waybill_url(self, order_id: str) -> Optional[str]:
        """Extract waybill PDF URL from order."""
```

**Features:**
- Exponential backoff on 429/5xx errors (max 6 retries)
- Token loaded from environment variables
- Rate limiting (100/sec max, configurable)
- Request/response logging for audit

**Effort:** 4 hours  
**Dependencies:** None

---

#### TASK-121: Create `config/kaspi_stores.yaml`

**Purpose:** Multi-store configuration with token references.

**File:** `config/kaspi_stores.yaml`

```yaml
stores:
  PP1:
    name: "AcmeWear PP1"
    token_env: "KASPI_TOKEN_PP1"
    active: true
    poll_interval_minutes: 5
    
  PP2:
    name: "AcmeWear PP2"
    token_env: "KASPI_TOKEN_PP2"
    active: true
    poll_interval_minutes: 5
    
  UNIVERSAL:
    name: "Universal Store"
    token_env: "KASPI_TOKEN_UNIVERSAL"
    active: true
    poll_interval_minutes: 5
    
  11KZ:
    name: "11KZ"
    token_env: "KASPI_TOKEN_11KZ"
    active: true
    poll_interval_minutes: 5
    
  MELVIS:
    name: "Store-C"
    token_env: "KASPI_TOKEN_MELVIS"
    active: true
    poll_interval_minutes: 5

default_poll_interval_minutes: 5
api_base_url: "https://kaspi.kz/shop/api/v2"
rate_limit_per_second: 50  # Conservative limit
```

**Effort:** 0.5 hours  
**Dependencies:** None

---

### Section G: Order Sync Engine

#### TASK-122: Create `core/sync/order_sync_engine.py`

**Purpose:** Sync orders from Kaspi API to local database.

**File:** `core/sync/order_sync_engine.py`

**Class:**
```python
class OrderSyncEngine:
    """
    Synchronize Kaspi orders across all stores.
    
    Usage:
        engine = OrderSyncEngine()
        results = engine.sync_all_stores(since=yesterday)
    """
    
    def sync_store(
        self,
        store_code: str,
        since: datetime = None,
        states: List[str] = None
    ) -> SyncResult:
        """
        Sync orders for single store.
        
        Returns:
            SyncResult with counts: new, updated, unchanged, errors
        """
    
    def sync_all_stores(
        self,
        since: datetime = None,
        parallel: bool = True
    ) -> Dict[str, SyncResult]:
        """
        Sync all active stores.
        
        If parallel=True, uses ThreadPoolExecutor (respects rate limits).
        """
    
    def detect_status_changes(self, store_code: str) -> List[OrderStatusChange]:
        """
        Compare API status vs local status.
        
        Returns list of orders with status changes for alerting.
        """
```

**Effort:** 4 hours  
**Dependencies:** TASK-120, TASK-121

---

#### TASK-123: Create `scripts/sync_kaspi_orders.py`

**Purpose:** CLI for manual and scheduled order sync.

**File:** `scripts/sync_kaspi_orders.py`

**Usage:**
```bash
# Sync all stores, last 24 hours
python scripts/sync_kaspi_orders.py

# Sync specific store
python scripts/sync_kaspi_orders.py --store PP1

# Sync with date range
python scripts/sync_kaspi_orders.py --since 2025-12-01 --until 2025-12-06

# Only new/pending orders
python scripts/sync_kaspi_orders.py --states NEW,ACCEPTED_BY_MERCHANT

# Dry run (no DB writes)
python scripts/sync_kaspi_orders.py --dry-run
```

**Output:**
```
Kaspi Order Sync — 2025-12-06 14:30:00
═══════════════════════════════════════
Store: PP1
  New orders: 12
  Updated: 5
  Unchanged: 45
  Errors: 0

Store: PP2
  New orders: 8
  Updated: 3
  ...

Total: 5 stores synced in 4.2s
New orders: 47
```

**Effort:** 2 hours  
**Dependencies:** TASK-122

---

### Section H: Waybill Automation

#### TASK-124: Create `core/waybill/waybill_downloader.py`

**Purpose:** Parallel waybill PDF download from API.

**File:** `core/waybill/waybill_downloader.py`

**Functions:**
```python
async def download_waybill(
    session: aiohttp.ClientSession,
    url: str,
    output_path: Path
) -> bool:
    """Download single waybill PDF."""

async def download_waybills_batch(
    waybills: List[Tuple[str, str, Path]],  # (order_id, url, path)
    max_concurrent: int = 10
) -> DownloadResult:
    """
    Download multiple waybills in parallel.
    
    Returns:
        DownloadResult with success/failed counts and paths
    """

def get_pending_waybills(store_code: str = None) -> List[Dict]:
    """
    Get orders with waybill_url but waybill_downloaded=0.
    """
```

**Effort:** 2 hours  
**Dependencies:** TASK-120

---

#### TASK-125: Create `scripts/download_waybills.py`

**Purpose:** CLI for batch waybill download.

**File:** `scripts/download_waybills.py`

**Usage:**
```bash
# Download all pending waybills
python scripts/download_waybills.py

# For specific store
python scripts/download_waybills.py --store PP1

# For specific date
python scripts/download_waybills.py --date 2025-12-06

# Output to custom directory
python scripts/download_waybills.py --output-dir exports/waybills/

# Then group them
python scripts/build_waybill_bundles.py \
    --from-db --date 2025-12-06 \
    --waybills-dir exports/waybills/raw/ \
    --output-dir exports/waybills/grouped/
```

**Effort:** 2 hours  
**Dependencies:** TASK-124

---

### Section I: Order Status Management

#### TASK-126: Create `core/automation/order_status_manager.py`

**Purpose:** Automate order status transitions with safety guards.

**File:** `core/automation/order_status_manager.py`

**Class:**
```python
class OrderStatusManager:
    """
    Manage order status transitions via Kaspi API.
    
    Safety features:
        - ENABLE_KASPI_WRITE env flag required
        - Telegram confirmation for bulk operations
        - Audit logging of all status changes
    """
    
    def accept_orders(
        self,
        order_ids: List[str],
        store_code: str,
        require_confirmation: bool = True
    ) -> BatchResult:
        """
        Accept multiple orders.
        
        If require_confirmation=True, sends Telegram confirmation first.
        """
    
    def mark_assembled(
        self,
        order_ids: List[str],
        store_code: str
    ) -> BatchResult:
        """Mark orders as assembled for Kaspi Delivery."""
    
    def auto_accept_ready_orders(
        self,
        store_code: str = None,
        max_orders: int = 50
    ) -> BatchResult:
        """
        Auto-accept orders ready for shipment.
        
        Criteria:
            - Status: NEW
            - Planned date <= today
            - All items in stock
            - No signature required
        """
```

**Effort:** 3 hours  
**Dependencies:** TASK-120

---

#### TASK-127: Create `scripts/manage_kaspi_orders.py`

**Purpose:** CLI for order status management.

**File:** `scripts/manage_kaspi_orders.py`

**Usage:**
```bash
# Accept specific orders
python scripts/manage_kaspi_orders.py accept --orders ORD123,ORD456 --store PP1

# Accept all ready orders (requires confirmation)
python scripts/manage_kaspi_orders.py accept-ready --store PP1

# Mark as assembled
python scripts/manage_kaspi_orders.py assemble --orders ORD123,ORD456 --store PP1

# Cancel orders
python scripts/manage_kaspi_orders.py cancel --orders ORD123 --store PP1 --reason MERCHANT_OUT_OF_STOCK

# Show pending orders
python scripts/manage_kaspi_orders.py list-pending --store PP1
```

**Effort:** 2 hours  
**Dependencies:** TASK-126

---

### Section J: Alerts & Monitoring

#### TASK-128: Create `core/alerts/order_alerts.py`

**Purpose:** Telegram alerts for order events.

**File:** `core/alerts/order_alerts.py`

**Functions:**
```python
def alert_new_orders(orders: List[Dict], store_code: str):
    """
    Send Telegram alert for new orders.
    
    Message format:
        🛒 New Orders — PP1
        ━━━━━━━━━━━━━━━━━
        12 new orders
        Total value: 156,000 KZT
        
        Top items:
        • LINE52_BLACK (4)
        • LINE51_WHITE (3)
        ...
    """

def alert_status_changes(changes: List[OrderStatusChange]):
    """Alert on unexpected status changes (cancellations, returns)."""

def alert_shipment_ready(orders: List[Dict], store_code: str):
    """Daily summary of orders ready for shipment."""

def request_bulk_confirmation(
    action: str,
    orders: List[Dict],
    store_code: str
) -> bool:
    """
    Request confirmation for bulk operations.
    
    Returns True if confirmed via Telegram callback.
    """
```

**Effort:** 2 hours  
**Dependencies:** TASK-122

---

#### TASK-129: Add order sync to daily pipeline

**File:** Update `scripts/run_daily_pipeline.py`

**New Steps:**
1. `step_sync_kaspi_orders()` — Sync all stores
2. `step_download_waybills()` — Download pending waybills
3. `step_alert_shipment_ready()` — Send daily shipment summary

**Effort:** 1 hour  
**Dependencies:** TASK-123, TASK-125, TASK-128

---

### Section K: Testing Phase 2

#### TASK-130: Create `tests/test_kaspi_api_client.py`

**Tests:**
- Token loading from env
- Order listing with filters
- Pagination handling
- Retry on 429/5xx
- Order status transitions
- Error handling

**Note:** Use mocked responses (vcr.py or responses library)

**Effort:** 3 hours  
**Dependencies:** TASK-120

---

#### TASK-131: Create `tests/test_order_sync.py`

**Tests:**
- Full sync cycle
- Incremental sync (since timestamp)
- Multi-store parallel sync
- Status change detection
- Duplicate handling

**Effort:** 2 hours  
**Dependencies:** TASK-122

---

#### TASK-132: Create `tests/test_waybill_downloader.py`

**Tests:**
- Single download
- Batch parallel download
- Failed download handling
- Rate limiting respect

**Effort:** 1.5 hours  
**Dependencies:** TASK-124

---

### Section L: Documentation

#### TASK-133: Create `docs/KASPI_API_INTEGRATION.md`

**Contents:**
- Token setup guide
- Multi-store configuration
- API endpoint reference
- Error handling guide
- Monitoring setup

**Effort:** 1.5 hours  
**Dependencies:** All Phase 2 tasks

---

#### TASK-134: Update `docs/DAILY_SOP.md`

**Add:**
- New order sync commands
- Waybill download workflow
- Troubleshooting guide

**Effort:** 1 hour  
**Dependencies:** TASK-133

---

## ROI Priority Matrix

| Feature | Impact | Effort | Priority | Phase |
|---------|--------|--------|----------|-------|
| API order sync (all stores) | H | M | **P1** | 2 |
| Excel export parser (legacy compat) | H | L | **P2** | 1 |
| Parallel waybill download | H | L | **P3** | 2 |
| PDF grouping rebuild | M | M | **P4** | 1 |
| Auto-accept ready orders | M | M | **P5** | 2 |
| Status change alerts | M | L | **P6** | 2 |
| Bulk order management CLI | L | M | **P7** | 2 |
| Telegram confirmation flow | L | M | **P8** | 2 |

**Legend:**
- Impact: H = >30 min/day saved, M = 10-30 min/day, L = <10 min/day
- Effort: H = >4 hours, M = 2-4 hours, L = <2 hours

---

## Risk & Blockers

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API rate limit hit during peak | Medium | Medium | Conservative 50/sec limit, exponential backoff |
| Token expiration mid-sync | Low | High | Token health check before sync, alert on 401 |
| Waybill URL format changes | Low | Medium | Robust URL parsing, fallback to manual |
| xlwings dependency in legacy data | Low | Low | One-time migration, then pure Python |

### Known Limitations

1. **Custom PDF generation NOT available via API** — Kaspi's "Выгрузить в PDF" button is UI-only
   - **Workaround:** Download individual waybill PDFs and merge with PyPDF2
   - **Manual Fallback:** For custom label formats, use third-party services (smartbid.kz, kstat.kz)

2. **No webhooks** — Must poll for order updates
   - **Workaround:** Poll every 5 minutes, or use ApiMonster middleware for pseudo-webhooks

3. **Security code for COMPLETED status** — Two-step process requires customer code
   - **Workaround:** Keep COMPLETED transition manual or implement Telegram-based code entry

### Blockers

| Blocker | Owner | Status | Resolution |
|---------|-------|--------|------------|
| API tokens for all 5 stores | Adil | Pending | Generate in Kaspi dashboard |
| ENABLE_KASPI_WRITE env flag | Adil | Pending | Add to .env after Phase 1 validation |
| Legacy data migration | Agent | Not started | TASK-110 discovery first |

---

## Success Criteria

### Phase 1 Complete When:
- [ ] `ingest_kaspi_export.py` parses ActiveOrders files correctly
- [ ] `build_waybill_bundles.py` generates grouped PDFs matching legacy output
- [ ] 25+ tests passing for Phase 1 components
- [ ] Legacy workflow can be fully replaced (side-by-side validation)

### Phase 2 Complete When:
- [ ] Order sync runs for all 5 stores without errors
- [ ] Waybill download completes in <30 seconds for 100 orders
- [ ] Status changes reflected in local DB within 5 minutes
- [ ] Daily pipeline includes API sync steps
- [ ] 40+ tests passing for Phase 2 components
- [ ] Time savings validated: 45+ min/day reduction

---

## Execution Timeline

```
Week 1: Phase 1 (Legacy Migration)
├── Day 1-2: Discovery & audit (TASK-110, 111)
├── Day 3-4: Parser & ingestion (TASK-112, 113, 114)
├── Day 5-6: PDF grouping (TASK-115, 116)
└── Day 7: Testing & validation (TASK-117, 118, 119)

Week 2: Phase 2 (API Integration)
├── Day 1-2: API client & config (TASK-120, 121)
├── Day 3-4: Sync engine (TASK-122, 123)
├── Day 5: Waybill automation (TASK-124, 125)
└── Day 6-7: Status management & alerts (TASK-126, 127, 128)

Week 3: Testing & Rollout
├── Day 1-2: Integration tests (TASK-130, 131, 132)
├── Day 3: Documentation (TASK-133, 134)
├── Day 4-5: Shadow mode validation
└── Day 6-7: Production cutover
```

---

## Phase 1 vs Phase 2 Decision Tree

```
Start
  │
  ├─ Do you need API tokens today? 
  │   ├─ No → Start Phase 1 (legacy migration)
  │   └─ Yes → Generate tokens, then Phase 2
  │
  ├─ Is legacy workflow still needed as fallback?
  │   ├─ Yes → Complete Phase 1 first
  │   └─ No → Skip to Phase 2
  │
  └─ Are all 5 store tokens available?
      ├─ Yes → Phase 2 can proceed
      └─ No → Phase 1 while waiting for tokens
```

---

## Summary

**Total Tasks:** 25  
**Total Effort:** 48-55 hours  
**Expected Time Savings:** 45-60 min/day  
**Annual ROI:** ~$6,750 + reduced errors

**Recommended Execution:** Start Phase 1 immediately (no API dependencies), parallel-track token generation, then Phase 2.

---

*Owner: Adil / Code Captain*  
*Created: 2025-12-06*
