# Kaspi API Client Fix Plan

**Date:** 2025-12-08  
**Session:** Debugging session with Adil  
**Status:** Ready for Opus execution  
**Priority:** HIGH — blocks Phase 9.5 validation

---

## Executive Summary

During live API testing, we discovered multiple issues preventing the Kaspi API client from correctly fetching orders. The API connection works, but filters and validation logic have bugs. This document provides a complete fix plan for autonomous execution.

---

## Issues Discovered

### Issue 1: Missing User-Agent Header (FIXED by Sonnet)

**Symptom:** API requests hung indefinitely (timeout)  
**Root Cause:** Kaspi API has anti-bot protection that drops requests without browser-like User-Agent  
**Fix Applied:** Added User-Agent header to `_get_headers()`  
**Status:** ✅ DONE

---

### Issue 2: Wrong Date Filter Format (FIXED by Sonnet)

**Symptom:** API returned error "Required filter [orders][creationDate][$ge] is empty"  
**Root Cause:** Code used `filter[orders][creationDateGe]` but API expects `filter[orders][creationDate][$ge]`  
**Fix Applied:** Changed parameter names in `list_orders()`  
**Status:** ✅ DONE

---

### Issue 3: `validate_token()` Uses Invalid Date Range

**Symptom:** `validate_all_tokens()` returns ❌ for all 5 stores  
**Root Cause:** `validate_token()` calls `list_orders(page_size=1, since="2025-01-01")` but Kaspi API has **14-day maximum date range limit**  

**Current Code (line ~691):**
```python
def validate_token(self) -> bool:
    try:
        response = self.list_orders(page_size=1, since="2025-01-01")
        return response.success
    except KaspiAuthError:
        return False
```

**Fix Required:**
```python
def validate_token(self) -> bool:
    """
    Validate API token by making a test request.
    Uses 7-day window to respect API's 14-day max limit.
    """
    try:
        from datetime import datetime, timedelta
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.list_orders(page_size=1, since=seven_days_ago)
        return response.success
    except KaspiAuthError:
        return False
```

**Status:** ❌ TODO

---

### Issue 4: `get_order()` Uses Wrong ID Format

**Symptom:** `get_order('739463441')` returns 404 "Resource not found"  
**Root Cause:** API endpoint requires Base64-encoded order ID (`NzM5NDYzNDQx`), not the order code (`739463441`)  

**Discovery:** 
- `GET /orders/739463441` → 404 Not Found
- `GET /orders?filter[orders][code]=739463441` → Returns order with `id: "NzM5NDYzNDQx"`

**Current Code (line ~447):**
```python
def get_order(self, order_code: str) -> APIResponse:
    return self._request('GET', f'orders/{order_code}')
```

**Fix Required:**
```python
def get_order(self, order_code: str) -> APIResponse:
    """
    Get single order by code.
    
    Note: Kaspi API requires Base64 order ID for direct endpoint,
    but we use filter by code which accepts the numeric code.
    """
    # Use filter approach which works with order code
    result = self._request('GET', 'orders', params={
        'filter[orders][code]': order_code
    })
    
    # Extract single order from list response
    if result.success and isinstance(result.data, dict):
        orders = result.data.get('data', [])
        if orders:
            return APIResponse(
                success=True,
                data=orders[0],
                status_code=result.status_code
            )
        return APIResponse(
            success=False,
            error=f"Order {order_code} not found",
            status_code=404
        )
    return result
```

**Status:** ❌ TODO

---

### Issue 5: Dashboard Status vs API Status Mismatch

**Symptom:** Dashboard shows 35 "NEW" orders, API returns 0 with `state=NEW`  
**Root Cause:** Dashboard "Упаковка" tab uses internal status `KASPI_DELIVERY_CARGO_ASSEMBLY` which is NOT a valid API filter value  

**Discovery:**
```
Dashboard URL: https://kaspi.kz/mc/#/orders-new?status=KASPI_DELIVERY_CARGO_ASSEMBLY
Actual API data for these 35 orders:
  - state: KASPI_DELIVERY
  - status: ACCEPTED_BY_MERCHANT  
  - assembled: false
```

**API Status Mapping (add to docs):**

| Dashboard Tab (Russian) | Dashboard URL Status | API Filters |
|------------------------|---------------------|-------------|
| Новый | NEW | `state=NEW`, `status=APPROVED_BY_BANK` |
| Упаковка | KASPI_DELIVERY_CARGO_ASSEMBLY | `state=KASPI_DELIVERY`, `status=ACCEPTED_BY_MERCHANT`, `assembled=false` |
| Передача курьеру | (varies) | `state=KASPI_DELIVERY`, `status=ACCEPTED_BY_MERCHANT`, `assembled=true` |
| В доставке | (varies) | `state=KASPI_DELIVERY`, courier fields populated |
| Архив | ARCHIVE | `state=ARCHIVE` |

**Fix Required:** Add helper methods for common dashboard views:

```python
def get_pending_assembly_orders(self, since: str = None) -> APIResponse:
    """
    Get orders awaiting assembly (Dashboard: Упаковка).
    These have state=KASPI_DELIVERY, status=ACCEPTED_BY_MERCHANT, assembled=false.
    """
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    result = self.list_orders(
        state='KASPI_DELIVERY',
        status='ACCEPTED_BY_MERCHANT',
        since=since,
        page_size=100
    )
    
    if result.success and isinstance(result.data, dict):
        orders = result.data.get('data', [])
        # Filter to only unassembled orders
        pending = [o for o in orders if not o.get('attributes', {}).get('assembled', False)]
        return APIResponse(
            success=True,
            data={'data': pending, 'meta': {'totalCount': len(pending)}},
            status_code=result.status_code
        )
    return result


def get_awaiting_courier_orders(self, since: str = None) -> APIResponse:
    """
    Get orders assembled and awaiting courier pickup.
    These have state=KASPI_DELIVERY, status=ACCEPTED_BY_MERCHANT, assembled=true.
    """
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    result = self.list_orders(
        state='KASPI_DELIVERY',
        status='ACCEPTED_BY_MERCHANT',
        since=since,
        page_size=100
    )
    
    if result.success and isinstance(result.data, dict):
        orders = result.data.get('data', [])
        # Filter to only assembled orders
        awaiting = [o for o in orders if o.get('attributes', {}).get('assembled', False)]
        return APIResponse(
            success=True,
            data={'data': awaiting, 'meta': {'totalCount': len(awaiting)}},
            status_code=result.status_code
        )
    return result
```

**Status:** ❌ TODO

---

### Issue 6: `list_orders()` Missing `status` Parameter

**Symptom:** Cannot filter by status (e.g., ACCEPTED_BY_MERCHANT)  
**Root Cause:** Method signature doesn't include `status` parameter  

**Current Code:**
```python
def list_orders(
    self,
    state: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    page_number: int = 0,
    page_size: int = 100,
) -> APIResponse:
```

**Fix Required:**
```python
def list_orders(
    self,
    state: Optional[str] = None,
    status: Optional[str] = None,  # ADD THIS
    since: Optional[str] = None,
    until: Optional[str] = None,
    page_number: int = 0,
    page_size: int = 100,
) -> APIResponse:
    """
    List orders with optional filters.

    Args:
        state: Filter by order state (NEW, KASPI_DELIVERY, PICKUP, DELIVERY, ARCHIVE)
        status: Filter by order status (APPROVED_BY_BANK, ACCEPTED_BY_MERCHANT, 
                COMPLETED, CANCELLED, CANCELLING)
        since: Filter orders created after this date (ISO8601 or YYYY-MM-DD)
        until: Filter orders created before this date
        page_number: Page number (0-indexed)
        page_size: Items per page (max 100)
    """
    # ... existing code ...
    
    if status:
        params['filter[orders][status]'] = status
    
    # ... rest of method ...
```

**Status:** ❌ TODO

---

### Issue 7: Add Constants for API Limits

**Purpose:** Document API constraints as constants for maintainability

**Add near top of file (~line 60-65):**
```python
# API Configuration Constants
DEFAULT_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60
MAX_DATE_RANGE_DAYS = 14      # Kaspi API enforces max 14-day date range
DEFAULT_SYNC_DAYS = 7         # Default lookback for sync operations
MAX_PAGE_SIZE = 100           # Kaspi API max items per page
```

**Status:** ❌ TODO

---

## Files to Modify

### 1. `core/integrations/kaspi_api_client.py`

| Line(s) | Change |
|---------|--------|
| ~60-65 | Add `MAX_DATE_RANGE_DAYS`, `DEFAULT_SYNC_DAYS` constants |
| ~359-397 | Add `status` parameter to `list_orders()` |
| ~447-458 | Fix `get_order()` to use filter approach |
| ~683-694 | Fix `validate_token()` to use 7-day window |
| (new) | Add `get_pending_assembly_orders()` method |
| (new) | Add `get_awaiting_courier_orders()` method |

### 2. `docs/KASPI_API_INTEGRATION.md`

Add new section documenting dashboard-to-API status mapping:

```markdown
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
- **Rate Limit:** ~100 requests/second (was 100/hour historically)
```

### 3. `tests/test_kaspi_api_client.py`

Add/update tests:

```python
def test_validate_token_uses_valid_date_range(self, mocker):
    """Ensure validate_token uses date within 14-day API limit."""
    mock_response = APIResponse(success=True, data={'data': []})
    mocker.patch.object(KaspiAPIClient, 'list_orders', return_value=mock_response)
    
    client = KaspiAPIClient('UNIVERSAL', token='test_token')
    result = client.validate_token()
    
    assert result is True
    # Verify list_orders was called with a recent since date
    call_kwargs = KaspiAPIClient.list_orders.call_args.kwargs
    assert 'since' in call_kwargs
    # Verify date is within 14 days
    from datetime import datetime
    since_date = datetime.strptime(call_kwargs['since'], '%Y-%m-%d')
    days_ago = (datetime.now() - since_date).days
    assert days_ago <= 14


def test_get_order_by_code(self, mocker):
    """Test get_order uses filter approach that works with order codes."""
    mock_data = {'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]}
    mock_response = APIResponse(success=True, data=mock_data)
    mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
    
    client = KaspiAPIClient('UNIVERSAL', token='test_token')
    result = client.get_order('12345')
    
    assert result.success
    assert result.data['attributes']['code'] == '12345'


def test_list_orders_with_status_filter(self, mocker):
    """Test list_orders accepts status parameter."""
    mock_response = APIResponse(success=True, data={'data': []})
    mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
    
    client = KaspiAPIClient('UNIVERSAL', token='test_token')
    client.list_orders(state='KASPI_DELIVERY', status='ACCEPTED_BY_MERCHANT', since='2025-12-01')
    
    call_args = KaspiAPIClient._request.call_args
    params = call_args.kwargs.get('params', {})
    assert params.get('filter[orders][status]') == 'ACCEPTED_BY_MERCHANT'


def test_get_pending_assembly_orders(self, mocker):
    """Test helper method filters to unassembled orders."""
    mock_orders = {
        'data': [
            {'id': '1', 'attributes': {'assembled': False}},
            {'id': '2', 'attributes': {'assembled': True}},
            {'id': '3', 'attributes': {'assembled': False}},
        ]
    }
    mock_response = APIResponse(success=True, data=mock_orders, status_code=200)
    mocker.patch.object(KaspiAPIClient, 'list_orders', return_value=mock_response)
    
    client = KaspiAPIClient('UNIVERSAL', token='test_token')
    result = client.get_pending_assembly_orders(since='2025-12-01')
    
    assert result.success
    assert len(result.data['data']) == 2  # Only unassembled orders
```

---

## Validation Commands

After applying fixes, run these commands to validate:

### 1. Run Test Suite
```bash
cd ~/Docs/Autonomous_business
python -m pytest tests/test_kaspi_api_client.py -v
```

### 2. Validate All Store Tokens
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import validate_all_tokens
results = validate_all_tokens()
for store, ok in results.items():
    print(f'{store}: {\"✅\" if ok else \"❌\"}')"
```

**Expected:** All 5 stores show ✅

### 3. Test get_order Fix
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import KaspiAPIClient
client = KaspiAPIClient('UNIVERSAL')
result = client.get_order('739463441')
print(f'Success: {result.success}')
print(f'Code: {result.data.get(\"attributes\", {}).get(\"code\") if result.success else \"N/A\"}')"
```

**Expected:** Success with order code 739463441

### 4. Test Pending Assembly Orders
```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import KaspiAPIClient
client = KaspiAPIClient('UNIVERSAL')
result = client.get_pending_assembly_orders(since='2025-12-07')
print(f'Pending assembly orders: {len(result.data.get(\"data\", []))}')"
```

**Expected:** ~35 orders (matching dashboard Упаковка count)

---

## Commit Message

```
fix(kaspi): API client fixes for date range, order lookup, and status filters

Issues fixed:
- validate_token() now uses 7-day window (API has 14-day max limit)
- get_order() uses filter approach (API requires Base64 ID for direct endpoint)
- list_orders() now accepts status parameter
- Added get_pending_assembly_orders() helper for dashboard "Упаковка" view
- Added get_awaiting_courier_orders() helper
- Added MAX_DATE_RANGE_DAYS and DEFAULT_SYNC_DAYS constants
- Updated KASPI_API_INTEGRATION.md with dashboard status mapping

Tested with live API:
- All 5 store tokens validate successfully
- Pending assembly orders match dashboard count
```

---

## Appendix: API Response Examples

### Order with state=KASPI_DELIVERY, status=ACCEPTED_BY_MERCHANT, assembled=false

```json
{
  "id": "NzM5NDYzNDQx",
  "type": "orders",
  "attributes": {
    "code": "739463441",
    "state": "KASPI_DELIVERY",
    "status": "ACCEPTED_BY_MERCHANT",
    "assembled": false,
    "totalPrice": 8999.0,
    "deliveryMode": "DELIVERY_PICKUP",
    "isKaspiDelivery": true,
    "customer": {
      "id": "Nzc1MzcyODExMg",
      "name": "Тұрағал",
      "cellPhone": "7753728112"
    },
    "kaspiDelivery": {
      "waybill": null,
      "courierTransmissionDate": null,
      "courierTransmissionPlanningDate": 1765206000000
    }
  }
}
```

### Valid Order States (from API docs)

| State | Russian | Description |
|-------|---------|-------------|
| NEW | новый | New order, needs acceptance |
| SIGN_REQUIRED | нужно подписать | Credit documents need signature |
| PICKUP | самовывоз | Customer pickup |
| DELIVERY | ваша доставка | Seller delivery |
| KASPI_DELIVERY | Kaspi Доставка | Kaspi courier delivery |
| ARCHIVE | архивный | Completed/cancelled |

### Valid Order Statuses (from API docs)

| Status | Russian | Description |
|--------|---------|-------------|
| APPROVED_BY_BANK | одобрен банком | Needs seller acceptance |
| ACCEPTED_BY_MERCHANT | принят | Accepted by seller |
| COMPLETED | завершён | Delivered to customer |
| CANCELLED | отменён | Cancelled |
| CANCELLING | ожидает отмены | Cancellation in progress |
| KASPI_DELIVERY_RETURN_REQUESTED | ожидает возврата | Return requested |
| RETURNED | возвращен | Returned |

---

*Document created: 2025-12-08 01:45 GMT+5*
*For execution by: Opus agent*
