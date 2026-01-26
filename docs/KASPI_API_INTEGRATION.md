# Kaspi Shop API Integration Guide

Phase 9.5 — Kaspi Order Automation

## Overview

This document describes the integration with Kaspi Shop API for automated order management, waybill downloads, and order status tracking.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     KASPI API INTEGRATION                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │  KaspiAPIClient │───>│ OrderSyncEngine │───>│   SQLite    │ │
│  │  (HTTP Layer)   │    │ (Business Logic)│    │   Database  │ │
│  └─────────────────┘    └─────────────────┘    └─────────────┘ │
│           │                      │                     │        │
│           │                      │                     │        │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │    Waybill      │    │  OrderStatus    │    │   Order     │ │
│  │   Downloader    │    │    Manager      │    │   Alerts    │ │
│  └─────────────────┘    └─────────────────┘    └─────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Set Up API Tokens

Add tokens to your `.env` file:

```bash
# Kaspi API Tokens (one per store)
KASPI_TOKEN_UNIVERSAL=your-universal-token-here
KASPI_TOKEN_ACMEWEAR=your-acmewear-token-here
KASPI_TOKEN_11KZ=your-store-d-token-here
KASPI_TOKEN_MELVIS=your-store-c-token-here
KASPI_TOKEN_STOREB=your-storeb-token-here

# Write operations guard (set to "1" only when ready for production)
ENABLE_KASPI_WRITE=0
```

### 2. Test Connection

```bash
# Validate tokens
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import validate_all_tokens
results = validate_all_tokens()
for store, valid in results.items():
    print(f'{store}: {\"OK\" if valid else \"FAILED\"}')"
```

### 3. Sync Orders

```bash
# Sync orders from Universal store (dry run)
python scripts/sync_kaspi_orders.py --store UNIVERSAL --dry-run

# Sync orders (actual)
python scripts/sync_kaspi_orders.py --store UNIVERSAL

# Sync all stores
python scripts/sync_kaspi_orders.py --all
```

### 4. Download Waybills

```bash
# Check waybill download status
python scripts/download_waybills.py --stats

# Download pending waybills
python scripts/download_waybills.py --store UNIVERSAL
```

---

## API Client Reference

### Module: `core/integrations/kaspi_api_client.py`

#### KaspiAPIClient

Main client for Kaspi Shop API interactions.

```python
from core.integrations.kaspi_api_client import KaspiAPIClient, get_client

# Create client for a specific store
client = get_client('UNIVERSAL')

# List orders
orders = client.list_all_orders(state='NEW', since='2025-12-01')

# Get single order
response = client.get_order('123456789')

# Download waybill
waybill = client.download_waybill('https://kaspi.kz/waybill/xxx.pdf')
```

#### Query filters (supported)

```python
# Optional filters for list_orders/list_all_orders
orders = client.list_all_orders(
    state='KASPI_DELIVERY',
    since='2025-12-01',
    delivery_type='DELIVERY',
    signature_required=False,
    include_orders='user',
)
```

#### Order States

| Kaspi State | Internal Status | Description |
|-------------|-----------------|-------------|
| NEW | NEW | Order just placed |
| ACCEPTED_BY_MERCHANT | ACCEPTED | Order accepted |
| ASSEMBLY | READY | Order assembled, ready for shipment |
| KASPI_DELIVERY | SHIPPED | Handed to Kaspi delivery |
| DELIVERY | SHIPPED | In transit |
| COMPLETED | COMPLETED | Delivered to customer |
| CANCELLED | CANCELLED | Order cancelled |
| RETURNING | RETURNING | Customer returning |
| RETURNED | RETURNED | Returned to seller |

#### Extended API fields captured (fact_orders_kaspi)

The API sync now stores additional attributes from the order payload:

- `kaspi_status_detail` (API status: APPROVED_BY_BANK, ACCEPTED_BY_MERCHANT, etc.)
- `planned_delivery_date`, `courier_transmission_planning_date`, `courier_transmission_date`
- `delivery_mode`, `payment_mode`, `signature_required`, `credit_term`, `pre_order`
- `approved_by_bank_date`, `reservation_date`
- `delivery_cost`, `delivery_cost_for_seller`, `delivery_address`
- `is_imei_required`, `express`, `returned_to_warehouse`, `category`
- `customer_first_name`, `customer_last_name`, `customer_phone`

Migration: `python scripts/migrate_014_kaspi_api_fields.py`

#### Write Operations

Write operations are disabled by default. To enable:

```bash
# In .env file
ENABLE_KASPI_WRITE=1
```

Available write operations:

```python
# Accept order
client.accept_order('123456')

# Mark as assembled
client.assemble_order('123456', parcel_count=1)

# Ship order
client.ship_order('123456')

# Cancel order
client.cancel_order('123456', reason='OUT_OF_STOCK')
```

---

## Order Sync Engine

### Module: `core/sync/order_sync_engine.py`

Synchronizes orders between Kaspi API and local database.

```python
from core.sync.order_sync_engine import OrderSyncEngine

engine = OrderSyncEngine()

# Sync single store
result = engine.sync_store('UNIVERSAL', since='2025-12-01')
print(f"Fetched: {result.orders_fetched}")
print(f"Inserted: {result.orders_inserted}")
print(f"Updated: {result.orders_updated}")

# Sync all stores
result = engine.sync_all_stores()
```

### Configuration: `config/kaspi_stores.yaml`

```yaml
stores:
  UNIVERSAL:
    name: Universal Store
    priority: 1
    sync_enabled: true

  ACMEWEAR:
    name: AcmeWear Store
    priority: 2
    sync_enabled: true

settings:
  default_lookback_days: 7
  rate_limit_rps: 50
```

---

## Order Status Manager

### Module: `core/automation/order_status_manager.py`

Manages order lifecycle via API.

```python
from core.automation.order_status_manager import OrderStatusManager

manager = OrderStatusManager(store_code='UNIVERSAL')

# Accept single order
result = manager.accept_order('123456')

# Accept all NEW orders
result = manager.accept_ready_orders(confirm=True)

# Assemble orders
result = manager.assemble_ready_orders(confirm=True)

# Ship orders with waybills
result = manager.ship_ready_orders(confirm=True)

# Get status summary
summary = manager.get_status_summary()
# {'NEW': 5, 'ACCEPTED': 3, 'READY': 2, ...}
```

### CLI: `scripts/manage_kaspi_orders.py`

```bash
# Show status summary
python scripts/manage_kaspi_orders.py status --store UNIVERSAL

# List orders by status
python scripts/manage_kaspi_orders.py list --store UNIVERSAL --status NEW

# Accept single order
python scripts/manage_kaspi_orders.py accept 123456 --store UNIVERSAL

# Accept all NEW orders
python scripts/manage_kaspi_orders.py accept-all --store UNIVERSAL --confirm

# Assemble orders
python scripts/manage_kaspi_orders.py assemble-all --store UNIVERSAL --confirm

# Ship orders
python scripts/manage_kaspi_orders.py ship-all --store UNIVERSAL --confirm

# Cancel order
python scripts/manage_kaspi_orders.py cancel 123456 --store UNIVERSAL --reason OUT_OF_STOCK

# Show suggested workflow
python scripts/manage_kaspi_orders.py workflow --store UNIVERSAL
```

---

## Waybill Downloader

### Module: `core/waybill/waybill_downloader.py`

Downloads waybill PDFs from Kaspi API.

```python
from core.waybill.waybill_downloader import WaybillDownloader

downloader = WaybillDownloader(store_code='UNIVERSAL')

# Check stats
stats = downloader.get_download_stats()
print(f"Pending: {stats['pending']}")

# Download all pending
result = downloader.download_pending(limit=50)
print(f"Downloaded: {result.successful}")

# Clean old files
count = downloader.clean_old_waybills(days=30)
```

### CLI: `scripts/download_waybills.py`

```bash
# Show download stats
python scripts/download_waybills.py --stats

# Download pending waybills
python scripts/download_waybills.py --store UNIVERSAL

# Limit downloads
python scripts/download_waybills.py --store UNIVERSAL --limit 20

# Force redownload
python scripts/download_waybills.py --store UNIVERSAL --force

# Clean old files
python scripts/download_waybills.py --clean --days 30
```

---

## Order Alerts

### Module: `core/alerts/order_alerts.py`

Telegram alerts for order lifecycle events.

```python
from core.alerts.order_alerts import (
    alert_new_orders,
    alert_shipment_ready,
    send_all_order_alerts,
)
from core.db import get_db

with get_db() as conn:
    # Alert on new orders
    result = alert_new_orders(conn, store_code='UNIVERSAL')

    # Alert on orders ready to ship
    result = alert_shipment_ready(conn, store_code='UNIVERSAL')

    # Send all applicable alerts
    result = send_all_order_alerts(conn, store_code='UNIVERSAL')
```

### Alert Types

| Alert Type | Trigger | Cooldown |
|------------|---------|----------|
| NEW_ORDERS | New orders in database | 1 hour |
| SHIPMENT_READY | Orders ready with waybills | 4 hours |
| DEADLINE_WARNING | Orders approaching deadline | 12 hours |

---

## Database Tables

### fact_orders_kaspi

Main order tracking table:

```sql
CREATE TABLE fact_orders_kaspi (
    id INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL,          -- Kaspi order code
    store_code TEXT NOT NULL,        -- Store identifier
    channel_code TEXT DEFAULT 'KSP', -- Channel (KSP for Kaspi)
    kaspi_status TEXT,               -- Raw Kaspi state
    internal_status TEXT,            -- Mapped internal status
    unit_price_kzt REAL,             -- Order total
    quantity INTEGER DEFAULT 1,
    created_at TEXT,                 -- Order creation time
    planned_shipment_date TEXT,      -- Delivery deadline
    waybill_url TEXT,                -- Kaspi waybill URL
    waybill_downloaded INTEGER DEFAULT 0,
    waybill_path TEXT,               -- Local file path
    assigned_size TEXT,              -- Auto-assigned size
    size_source TEXT,                -- CUSTOMER/OFFER_MODE/STYLE_MODE/DEFAULT
    size_confidence TEXT,            -- HIGH/MEDIUM/LOW
    source TEXT DEFAULT 'API',       -- Data source
    imported_at TEXT,
    status_updated_at TEXT,
    UNIQUE(order_id, store_code)
);
```

---

## Dashboard Status Mapping

The Kaspi merchant dashboard uses internal status values that differ from API filter values.

| Dashboard Tab | Dashboard URL Parameter | API Filter Combination |
|--------------|------------------------|------------------------|
| Новый (New) | `status=NEW` | `state=NEW` + `status=APPROVED_BY_BANK` |
| Упаковка (Assembly) | `status=KASPI_DELIVERY_CARGO_ASSEMBLY` | `state=KASPI_DELIVERY` + `status=ACCEPTED_BY_MERCHANT` + `assembled=false` |
| Передача курьеру | (varies) | `state=KASPI_DELIVERY` + `assembled=true` |
| Архив (Archive) | `status=ARCHIVE` | `state=ARCHIVE` |

### Helper Methods

```python
# Get orders awaiting assembly (Упаковка tab)
orders = client.get_pending_assembly_orders(since='2025-12-01')

# Get orders awaiting courier (assembled, not shipped)
orders = client.get_awaiting_courier_orders(since='2025-12-01')
```

### API Limits

- **Date Range:** Maximum 14 days between `since` and `until`
- **Page Size:** Maximum 100 orders per request
- **Rate Limit:** ~50 requests/second (conservative setting)

---

## Daily Pipeline Integration

The order sync is integrated into `scripts/run_daily_pipeline.py`:

```bash
# Full pipeline (includes order sync)
python scripts/run_daily_pipeline.py

# Skip ingestion, run metrics only
python scripts/run_daily_pipeline.py --skip-ingest

# Dry run
python scripts/run_daily_pipeline.py --dry-run
```

### Pipeline Steps (Order-Related)

1. `sync_kaspi_orders` — Fetch orders from Kaspi API
2. `assign_sizes` — Auto-assign sizes to orders
3. `download_waybills` — Download pending waybill PDFs
4. `send_order_alerts` — Send Telegram notifications

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `KaspiAuthError` | Invalid/expired token | Refresh token in Kaspi merchant portal |
| `KaspiRateLimitError` | Too many requests | Wait and retry, reduce batch size |
| `KaspiWriteDisabledError` | ENABLE_KASPI_WRITE=0 | Set to "1" after validation |
| `Connection timeout` | Network issues | Check connectivity, retry |

### Retry Logic

The client implements automatic retry with exponential backoff:
- Max retries: 3
- Backoff factor: 0.5s (0.5s, 1.0s, 2.0s)
- Retry on: 408, 429, 500, 502, 503, 504

---

## Security Considerations

1. **Token Storage**: Store tokens in `.env` file (not in code)
2. **Write Guard**: Keep `ENABLE_KASPI_WRITE=0` until validated
3. **Rate Limiting**: Respect 50 req/sec limit
4. **Audit Trail**: All status changes logged to database
5. **Confirmation**: Bulk operations require explicit `--confirm` flag

---

## Multi-Store Rollout

### Validation Process

1. **Universal Only** (Week 1-2)
   - Test all operations with Universal store
   - Verify sync accuracy vs Excel export
   - Test write operations in dry-run mode

2. **Enable Writes** (After validation)
   - Set `ENABLE_KASPI_WRITE=1`
   - Test accept/ship on small batch
   - Monitor for errors

3. **Add Stores** (Week 3+)
   - Enable sync for additional stores one at a time
   - Update `kaspi_stores.yaml` with priorities

### Configuration Priority

Stores are synced in priority order (lower = first):

```yaml
stores:
  UNIVERSAL:
    priority: 1  # Synced first
  ACMEWEAR:
    priority: 2
  11KZ:
    priority: 3
```

---

## Troubleshooting

### Verify Token

```python
from dotenv import load_dotenv
load_dotenv()

from core.integrations.kaspi_api_client import get_client

client = get_client('UNIVERSAL')
if client.validate_token():
    print("Token valid")
else:
    print("Token invalid - refresh in Kaspi merchant portal")
```

### Check Sync Status

```bash
python scripts/sync_kaspi_orders.py --store UNIVERSAL --stats
```

### View Order Details

```bash
python scripts/manage_kaspi_orders.py list --store UNIVERSAL --status NEW
```

### Force Re-sync

```bash
# Re-sync last 14 days
python scripts/sync_kaspi_orders.py --store UNIVERSAL --since 2025-11-23
```

---

## Appendix: API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/shop/api/v2/orders` | GET | List orders with filters |
| `/shop/api/v2/orders/{code}` | GET | Get single order |
| `/shop/api/v2/orders/{code}/entries` | GET | Get order line items |
| `/shop/api/v2/orders/{code}/accept` | POST | Accept order |
| `/shop/api/v2/orders/{code}/ship` | POST | Ship order |
| `/shop/api/v2/orders` | POST | Update order (assemble, cancel) |

API Base URL: `https://kaspi.kz/shop/api/v2`

---

*Last updated: 2025-12-07*
*Phase 9.5 — Kaspi Order Automation*
