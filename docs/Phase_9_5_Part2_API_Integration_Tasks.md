# Phase 9.5 Part 2 — API Integration + Size Engine
## Task Breakdown for TASK-120+

**Date:** 2025-12-07  
**Status:** Phase 1 Complete ✅ | Phase 2 Ready to Start  
**Test Store:** Universal (single store before multi-store rollout)

---

## 1. Dependency Checklist

| # | Prerequisite | Owner | Status | Verification |
|---|--------------|-------|--------|--------------|
| 1 | `pip install aiohttp PyPDF2` | Adil | ⏳ | `python -c "import aiohttp, PyPDF2"` |
| 2 | API tokens in `.env` for all 5 stores | Adil | ✅ | `python scripts/print_tokens.py` |
| 3 | Phase 1 tests passing (67 tests) | — | ✅ | `pytest tests/test_kaspi_*.py tests/test_pdf_*.py` |
| 4 | `fact_orders_kaspi` table exists | — | ✅ | `sqlite3 data/project3.db ".tables"` |
| 5 | Historical sales data for size analysis | — | ✅ | `fact_sales` has 13,050+ records |

**Before starting TASK-120:** Run this verification block:
```bash
cd ~/Docs/Autonomous_business
pip install aiohttp PyPDF2
python -c "import aiohttp, PyPDF2; print('Dependencies OK')"
python scripts/print_tokens.py  # Should show 5 tokens OK
pytest tests/test_kaspi_export_parser.py tests/test_pdf_grouper.py -q
```

---

## 2. Docs to Update in Repo

| Doc | Update Required | When |
|-----|-----------------|------|
| `TASKS.md` | Add TASK-135 through TASK-142 (size engine tasks) | Before Opus starts |
| `Future_Phases_Roadmap.md` | Mark Phase 9.5 Part 2 in progress | After Phase 2 starts |
| `SESSION_LOG.md` | Log Phase 2 progress | During execution |
| `docs/KASPI_API_INTEGRATION.md` | Create (TASK-133) | During Phase 2 |
| `docs/DAILY_SOP.md` | Add API sync + size workflow | After Phase 2 |
| `config/kaspi_stores.yaml` | Create (TASK-121) | TASK-121 |

---

## 3. Size Workflow Redesign

### 3.1 Current Problem

The existing sizing workflow requires:
1. Customer places order on Kaspi (no size selection — clothing is "one-size" listing)
2. WhatsApp autosender (Algatop) sends size consultation message with height/weight questions
3. Customer replies with measurements
4. Human operator looks up size chart, enters `MY_SIZE` in `SALES_KSP_CRM_V3.xlsx`
5. Order ships with determined size

**Blockers:**
- WhatsApp autosender disabled (spam restrictions)
- Facebook Business API verification pending (weeks/months)
- ~40% of customers don't respond even when messaging works

### 3.2 Proposed Solution: Probabilistic Size Assignment

Implement a **3-tier fallback system** that assigns size automatically when customer params unavailable:

```
┌─────────────────────────────────────────────────────────────────┐
│                    SIZE DETERMINATION CASCADE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tier 1: Customer-Provided (Manual Entry)                       │
│    ├── Customer responds via any channel with height/weight     │
│    └── Human enters in batch entry UI → highest confidence      │
│                                                                 │
│  Tier 2: Offer-Level Historical Mode                            │
│    ├── Query: What size do customers ACTUALLY order for this    │
│    │         specific Kaspi offer (kaspi_offer_name)?           │
│    ├── Threshold: ≥5 historical orders, ≥60% mode share         │
│    └── Example: "LINE52 BLACK L" → 70% order L → assign L      │
│                                                                 │
│  Tier 3: Style-Level Historical Mode                            │
│    ├── Query: What size dominates for this SKU_key across all   │
│    │         offers? (aggregates XS-4XL distribution)           │
│    ├── Threshold: ≥10 historical orders, ≥40% mode share        │
│    └── Example: LINE52_BLACK → 45% order L → assign L          │
│                                                                 │
│  Tier 4: Product Type Default                                   │
│    ├── Generic defaults by product category                     │
│    └── T-shirts: L | Pants: 32 | Kids: 28                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Implementation Components

**New Table: `dim_size_probability`**
```sql
CREATE TABLE dim_size_probability (
    id INTEGER PRIMARY KEY,
    level TEXT NOT NULL,           -- 'OFFER' | 'STYLE' | 'PRODUCT_TYPE'
    key_value TEXT NOT NULL,       -- kaspi_offer_name | sku_key | product_type
    mode_size TEXT NOT NULL,       -- Most frequent size
    mode_share REAL NOT NULL,      -- Percentage (0.0-1.0)
    sample_count INTEGER NOT NULL, -- Number of observations
    confidence TEXT NOT NULL,      -- 'HIGH' (≥60%) | 'MEDIUM' (40-60%) | 'LOW' (<40%)
    size_distribution TEXT,        -- JSON: {"S": 0.1, "M": 0.2, "L": 0.4, ...}
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(level, key_value)
);
```

**New Columns in `fact_orders_kaspi`:**
```sql
ALTER TABLE fact_orders_kaspi ADD COLUMN assigned_size TEXT;
ALTER TABLE fact_orders_kaspi ADD COLUMN size_source TEXT;      -- 'CUSTOMER' | 'OFFER_MODE' | 'STYLE_MODE' | 'DEFAULT'
ALTER TABLE fact_orders_kaspi ADD COLUMN size_confidence TEXT;  -- 'HIGH' | 'MEDIUM' | 'LOW'
ALTER TABLE fact_orders_kaspi ADD COLUMN customer_height_cm INTEGER;
ALTER TABLE fact_orders_kaspi ADD COLUMN customer_weight_kg INTEGER;
```

**Batch Entry UI (Simplified):**
Since WhatsApp is blocked, provide a daily batch entry workflow:
1. Morning: Export pending orders without sizes → CSV
2. Human: Contact customers via available channels (Kaspi chat, phone)
3. Human: Enter height/weight in CSV or simple web form
4. System: Import entries, calculate sizes, update `fact_orders_kaspi`

This reduces manual work to data entry only — no size chart lookups needed.

---

## 4. API Endpoint Mapping

| Feature | Endpoint | Method | Notes |
|---------|----------|--------|-------|
| List orders | `/shop/api/v2/orders` | GET | Pagination via `page[number]`, `page[size]` |
| Filter by status | `?filter[orders][state]=NEW` | GET | States: NEW, ACCEPTED_BY_MERCHANT, KASPI_DELIVERY, etc. |
| Filter by date | `?filter[orders][creationDateGe]=...` | GET | ISO8601 format |
| Get order entries | `/shop/api/v2/orderentries/{id}` | GET | Line items with SKU, price, quantity |
| Get product info | `/shop/api/v2/orderentries/{id}/product` | GET | Product details for order line |
| Accept order | `/shop/api/v2/orders/{code}/accept` | POST | Status → ACCEPTED_BY_MERCHANT |
| Ship order | `/shop/api/v2/orders/{code}/ship` | POST | Status → KASPI_DELIVERY |
| Cancel order | `/shop/api/v2/orders` | POST | Requires `cancellationReason` |
| Assemble order | `/shop/api/v2/orders` | POST | Status → ASSEMBLE, sets parcel count |
| Complete order | `/shop/api/v2/orders` | POST | Requires security code (2-step) |
| Get waybill URL | (in order response) | — | `attributes.kaspiDelivery.waybill` |
| Download waybill | (direct URL) | GET | Returns PDF binary |
| **Custom PDF generation** | — | — | ❌ **NOT AVAILABLE** — Manual Fallback Required |
| **Customer messaging** | — | — | ❌ **NOT AVAILABLE** — Use Kaspi chat manually |

---

## 5. Task Breakdown

### Existing Tasks (from original spec)

#### Section F: API Client

**TASK-120: Create `core/integrations/kaspi_api_client.py`**
- KaspiAPIClient class with retry logic (exponential backoff)
- Multi-store token loading from env vars
- Rate limiting (50 req/sec conservative)
- Effort: 4 hours

**TASK-121: Create `config/kaspi_stores.yaml`**
- Store configuration with token references
- Universal as primary test store
- Effort: 0.5 hours

#### Section G: Order Sync Engine

**TASK-122: Create `core/sync/order_sync_engine.py`**
- OrderSyncEngine class
- sync_store(), sync_all_stores(), detect_status_changes()
- Effort: 4 hours

**TASK-123: Create `scripts/sync_kaspi_orders.py`**
- CLI: `--store`, `--since`, `--states`, `--dry-run`
- Effort: 2 hours

#### Section H: Waybill Automation

**TASK-124: Create `core/waybill/waybill_downloader.py`**
- Async parallel download with aiohttp
- Rate limiting respect
- Effort: 2 hours

**TASK-125: Create `scripts/download_waybills.py`**
- CLI for batch waybill download
- Effort: 2 hours

#### Section I: Order Status Management

**TASK-126: Create `core/automation/order_status_manager.py`**
- OrderStatusManager class
- ENABLE_KASPI_WRITE guard
- Telegram confirmation for bulk ops
- Effort: 3 hours

**TASK-127: Create `scripts/manage_kaspi_orders.py`**
- CLI: accept, accept-ready, assemble, cancel, list-pending
- Effort: 2 hours

#### Section J: Alerts & Monitoring

**TASK-128: Create `core/alerts/order_alerts.py`**
- alert_new_orders(), alert_status_changes()
- Telegram integration
- Effort: 2 hours

**TASK-129: Add order sync to daily pipeline**
- step_sync_kaspi_orders(), step_download_waybills()
- Effort: 1 hour

#### Section K: Testing

**TASK-130: Create `tests/test_kaspi_api_client.py`**
- Mocked responses (use `responses` library)
- Effort: 3 hours

**TASK-131: Create `tests/test_order_sync.py`**
- Effort: 2 hours

**TASK-132: Create `tests/test_waybill_downloader.py`**
- Effort: 1.5 hours

#### Section L: Documentation

**TASK-133: Create `docs/KASPI_API_INTEGRATION.md`**
- Effort: 1.5 hours

**TASK-134: Update `docs/DAILY_SOP.md`**
- Effort: 1 hour

---

### NEW Tasks: Size Engine (TASK-135 to TASK-142)

#### Section M: Size Probability Engine

**TASK-135: Create `dim_size_probability` table (Migration 012)**
- Schema as defined in Section 3.3
- Effort: 1 hour

**TASK-136: Create `core/calc/size_probability.py`**
```python
def calc_offer_size_mode(kaspi_offer_name: str) -> SizeProbability:
    """Calculate mode size for specific offer from fact_sales history."""

def calc_style_size_mode(sku_key: str) -> SizeProbability:
    """Calculate mode size for style across all offers."""

def get_product_type_default(product_type: str) -> str:
    """Return hardcoded default size for product type."""

def determine_size(
    order: Dict,
    customer_height: int = None,
    customer_weight: int = None
) -> Tuple[str, str, str]:  # (size, source, confidence)
    """
    Cascade through size determination tiers.
    Returns: (assigned_size, size_source, size_confidence)
    """
```
- Effort: 4 hours

**TASK-137: Create `scripts/build_size_probability.py`**
- Rebuild dim_size_probability from fact_sales history
- CLI: `--min-samples 5`, `--rebuild`
- Effort: 2 hours

**TASK-138: Add size columns to `fact_orders_kaspi` (Migration 012 update)**
- assigned_size, size_source, size_confidence
- customer_height_cm, customer_weight_kg
- Effort: 0.5 hours

**TASK-139: Create `scripts/assign_sizes.py`**
- CLI to assign sizes to pending orders
- `--strategy auto|manual|batch`
- `--export-pending` exports orders needing manual size entry
- Effort: 3 hours

**TASK-140: Create `scripts/import_customer_params.py`**
- Import height/weight from CSV batch entry
- Recalculate sizes using size chart
- Effort: 2 hours

**TASK-141: Create `tests/test_size_probability.py`**
- Test cascade logic, thresholds, edge cases
- Effort: 2 hours

**TASK-142: Integrate size assignment into order sync**
- After sync, auto-assign sizes using cascade
- Flag orders needing manual review
- Effort: 1 hour

---

## 6. Execution Order

```
Phase 2A: API Foundation (Universal store only)
├── TASK-120: API client
├── TASK-121: Store config
├── TASK-122: Sync engine
├── TASK-123: Sync CLI
└── Validate: Compare API vs Excel export for 1 day

Phase 2B: Waybill Automation
├── TASK-124: Waybill downloader
├── TASK-125: Download CLI
└── Validate: Download waybills for today's orders

Phase 2C: Size Engine (Critical Path)
├── TASK-135: Size probability table
├── TASK-136: Size probability core
├── TASK-137: Build probability CLI
├── TASK-138: Order table columns
├── TASK-139: Assign sizes CLI
├── TASK-140: Import params CLI
├── TASK-141: Size tests
└── TASK-142: Pipeline integration

Phase 2D: Order Management
├── TASK-126: Status manager
├── TASK-127: Management CLI
├── TASK-128: Order alerts
└── TASK-129: Pipeline integration

Phase 2E: Testing & Docs
├── TASK-130: API client tests
├── TASK-131: Sync tests
├── TASK-132: Downloader tests
├── TASK-133: API integration doc
└── TASK-134: SOP update
```

**Estimated Total:** 45-50 hours

---

## 7. Open Questions (Require Adil Input)

| # | Question | Default if No Answer | Impact |
|---|----------|---------------------|--------|
| 1 | **Size chart location:** Where is the height/weight → size mapping table? | Discover from `SALES_KSP_CRM_V3.xlsx` SIZE_engine sheets | TASK-136 implementation |
| 2 | **Confidence thresholds:** Accept 60%/40% for offer/style modes? | Yes, as proposed | Size accuracy vs coverage tradeoff |
| 3 | **Manual entry format:** CSV upload or simple web UI? | CSV (faster to build) | TASK-140 scope |
| 4 | **Multi-store rollout timing:** How long to test Universal before adding other stores? | 3-5 days of successful syncs | Risk management |
| 5 | **Write operations:** Enable auto-accept for Universal immediately, or shadow mode first? | Shadow mode first (7 days) | Safety |
| 6 | **Waybill storage:** Keep downloaded PDFs or delete after grouping? | Keep 30 days in `exports/waybills/` | Storage vs auditability |
| 7 | **Return handling:** What happens if assigned size is wrong? Track return rates by size_source? | Yes, add return tracking | Future quality improvement |

---

## 8. Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|------------|
| API rate limit during sync | Medium | Conservative 50/sec, exponential backoff |
| Token expires mid-operation | Low | Pre-sync token validation, alert on 401 |
| Size mode has low confidence | Medium | Fallback to style mode, then default |
| Batch size entry delayed | High | Auto-assign with probabilistic mode, human can override later |
| Return rate increases due to auto-sizing | Medium | Track return rates by size_source, tune thresholds |

---

## 9. Success Criteria

### Phase 2 Complete When:
- [ ] Order sync runs for Universal store without errors for 5+ consecutive days
- [ ] Waybill download completes in <30 seconds for 100 orders
- [ ] Size probability table covers >80% of active kaspi_offer_names
- [ ] Auto-assigned sizes have <15% return rate (vs current baseline)
- [ ] 50+ new tests passing
- [ ] API integration documented

### ROI Validation:
- [ ] Manual Chrome switching eliminated (target: -60 min/day)
- [ ] Size entry time reduced by 50% (target: -15 min/day)
- [ ] Total daily savings: 75+ min/day

---

## 10. Commands for Opus

When ready, tell Opus:

```
Start Phase 9.5 Part 2.

Execution order:
1. TASK-120 → TASK-121 → TASK-122 → TASK-123 (API foundation)
2. Pause for validation: I'll test API sync vs Excel export
3. TASK-124 → TASK-125 (waybill automation)
4. TASK-135 → TASK-136 → TASK-137 → TASK-138 → TASK-139 → TASK-140 → TASK-141 → TASK-142 (size engine)
5. TASK-126 → TASK-127 → TASK-128 → TASK-129 (order management)
6. TASK-130 → TASK-131 → TASK-132 → TASK-133 → TASK-134 (testing & docs)

Key context:
- Test store: Universal only (KASPI_TOKEN_UNIVERSAL in .env)
- ENABLE_KASPI_WRITE=0 until shadow mode validated
- Size engine is CRITICAL PATH — WhatsApp is blocked
- Size chart logic is in SALES_KSP_CRM_V3.xlsx sheets: SIZE_engine_basic, Kid_Sizes
```

---

*Created: 2025-12-07*  
*Owner: Adil / Code Captain*
