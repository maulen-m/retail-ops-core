# Opus Overnight Execution Plan — Kaspi API Complete Validation

**Date:** 2025-12-08  
**Executor:** Claude Opus (autonomous overnight run)  
**Priority:** HIGH — Enables Phase 9.5 production rollout  
**Estimated Runtime:** 4-6 hours

---

## Executive Summary

The Kaspi API client has been partially fixed but **critical bugs remain**. During live testing:

- `get_pending_assembly_orders()` returns **0 orders** while dashboard shows **35**
- Manual API query using same filters returns **35 orders** (correct)
- **Root cause:** Helper method has a bug in how it processes/returns the APIResponse

This plan provides complete fix + validation + test suite expansion for autonomous overnight execution.

---

## Pre-Flight Checklist

Before starting any tasks, verify environment:

```bash
cd ~/Docs/Autonomous_business
source .venv/bin/activate

# Verify environment
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
stores = ['UNIVERSAL', 'ACMEWEAR', '11KZ', 'MELVIS', 'STOREB']
for store in stores:
    token = os.getenv(f'KASPI_TOKEN_{store}')
    print(f'{store}: {\"✅ Token present\" if token else \"❌ MISSING\"}')"

# Verify tests pass
python -m pytest tests/test_kaspi_api_client.py -v --tb=short 2>&1 | tail -20
```

**Expected:** All 5 tokens present, existing tests pass.

---

## ISSUE 1: `get_pending_assembly_orders()` Returns 0 Orders

### Problem

```python
# Current behavior (WRONG)
result = client.get_pending_assembly_orders()
print(len(result.data.get('data', [])))  # Returns: 0

# Manual query (CORRECT)
result = client._request('GET', 'orders', params={
    'filter[orders][state]': 'KASPI_DELIVERY',
    'filter[orders][creationDate][$ge]': timestamp,
})
orders = [o for o in result.data['data'] if not o['attributes'].get('assembled', False)]
print(len(orders))  # Returns: 35
```

### Investigation Steps

1. **Read current implementation:**
   ```bash
   grep -n "get_pending_assembly_orders" core/integrations/kaspi_api_client.py -A 30
   ```

2. **Compare with working manual query:**
   ```python
   # This works — returns 35:
   result = client._request('GET', 'orders', params={
       'page[number]': 0,
       'page[size]': 100,
       'filter[orders][creationDate][$ge]': client._to_timestamp_ms('2025-12-07'),
       'filter[orders][state]': 'KASPI_DELIVERY'
   })
   orders = [o for o in result.data.get('data', []) 
             if o.get('attributes', {}).get('status') == 'ACCEPTED_BY_MERCHANT'
             and not o.get('attributes', {}).get('assembled', False)]
   print(len(orders))  # 35
   ```

### Suspected Root Causes

1. **Pagination not handled** — If method only fetches page 0, may miss orders
2. **Wrong filter combination** — Using `status` param that API ignores
3. **Response parsing error** — Not extracting `data` from nested structure correctly
4. **Date range too narrow** — Not capturing all relevant orders

### Fix Implementation

**File:** `core/integrations/kaspi_api_client.py`

Replace `get_pending_assembly_orders()` method with:

```python
def get_pending_assembly_orders(self, since: str = None) -> APIResponse:
    """
    Get orders awaiting assembly (Dashboard: Упаковка tab).
    
    These orders have:
    - state: KASPI_DELIVERY
    - status: ACCEPTED_BY_MERCHANT  
    - assembled: false
    
    Args:
        since: Start date (YYYY-MM-DD). Default: 7 days ago.
        
    Returns:
        APIResponse with filtered orders in data['data']
    """
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Fetch ALL KASPI_DELIVERY orders with pagination
    all_orders = []
    page = 0
    max_pages = 20  # Safety limit
    
    while page < max_pages:
        timestamp_ms = self._to_timestamp_ms(since)
        result = self._request('GET', 'orders', params={
            'page[number]': page,
            'page[size]': 100,
            'filter[orders][creationDate][$ge]': timestamp_ms,
            'filter[orders][state]': 'KASPI_DELIVERY'
        })
        
        if not result.success:
            return result
            
        page_orders = result.data.get('data', [])
        if not page_orders:
            break
            
        all_orders.extend(page_orders)
        page += 1
        
        # Check if more pages
        meta = result.data.get('meta', {})
        total_pages = meta.get('pageCount', 1)
        if page >= total_pages:
            break
    
    # Filter to pending assembly only:
    # - status = ACCEPTED_BY_MERCHANT
    # - assembled = false
    pending = []
    for order in all_orders:
        attrs = order.get('attributes', {})
        if (attrs.get('status') == 'ACCEPTED_BY_MERCHANT' and 
            attrs.get('assembled', False) is False):
            pending.append(order)
    
    return APIResponse(
        success=True,
        data={'data': pending, 'meta': {'totalCount': len(pending)}},
        status_code=200
    )
```

### Validation Command

After fix, run:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import KaspiAPIClient

client = KaspiAPIClient('UNIVERSAL')
result = client.get_pending_assembly_orders()

if result.success:
    orders = result.data.get('data', [])
    print(f'✅ Pending assembly orders: {len(orders)}')
    for o in orders[:3]:
        attrs = o.get('attributes', {})
        print(f'   - {attrs.get(\"code\")}: status={attrs.get(\"status\")}, assembled={attrs.get(\"assembled\")}')
else:
    print(f'❌ Error: {result.error}')
"
```

**Expected:** 30-40 orders (should roughly match dashboard Упаковка count)

---

## ISSUE 2: `get_awaiting_courier_orders()` Likely Has Same Bug

### Fix Implementation

Apply same pagination + filtering fix:

```python
def get_awaiting_courier_orders(self, since: str = None) -> APIResponse:
    """
    Get orders assembled and awaiting courier pickup.
    
    These orders have:
    - state: KASPI_DELIVERY
    - status: ACCEPTED_BY_MERCHANT
    - assembled: true
    
    Args:
        since: Start date (YYYY-MM-DD). Default: 7 days ago.
        
    Returns:
        APIResponse with filtered orders in data['data']
    """
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Fetch ALL KASPI_DELIVERY orders with pagination
    all_orders = []
    page = 0
    max_pages = 20
    
    while page < max_pages:
        timestamp_ms = self._to_timestamp_ms(since)
        result = self._request('GET', 'orders', params={
            'page[number]': page,
            'page[size]': 100,
            'filter[orders][creationDate][$ge]': timestamp_ms,
            'filter[orders][state]': 'KASPI_DELIVERY'
        })
        
        if not result.success:
            return result
            
        page_orders = result.data.get('data', [])
        if not page_orders:
            break
            
        all_orders.extend(page_orders)
        page += 1
        
        meta = result.data.get('meta', {})
        total_pages = meta.get('pageCount', 1)
        if page >= total_pages:
            break
    
    # Filter to assembled orders awaiting courier:
    # - status = ACCEPTED_BY_MERCHANT
    # - assembled = true
    awaiting = []
    for order in all_orders:
        attrs = order.get('attributes', {})
        if (attrs.get('status') == 'ACCEPTED_BY_MERCHANT' and 
            attrs.get('assembled', False) is True):
            awaiting.append(order)
    
    return APIResponse(
        success=True,
        data={'data': awaiting, 'meta': {'totalCount': len(awaiting)}},
        status_code=200
    )
```

### Validation Command

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import KaspiAPIClient

client = KaspiAPIClient('UNIVERSAL')
result = client.get_awaiting_courier_orders()

if result.success:
    orders = result.data.get('data', [])
    print(f'✅ Awaiting courier orders: {len(orders)}')
else:
    print(f'❌ Error: {result.error}')
"
```

---

## ISSUE 3: Add `get_new_orders()` Helper

For Dashboard "Новый" tab — orders needing acceptance.

### Implementation

```python
def get_new_orders(self, since: str = None) -> APIResponse:
    """
    Get new orders needing acceptance (Dashboard: Новый tab).
    
    These orders have:
    - state: NEW
    - status: APPROVED_BY_BANK
    
    Args:
        since: Start date (YYYY-MM-DD). Default: 7 days ago.
        
    Returns:
        APIResponse with new orders in data['data']
    """
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    all_orders = []
    page = 0
    max_pages = 20
    
    while page < max_pages:
        timestamp_ms = self._to_timestamp_ms(since)
        result = self._request('GET', 'orders', params={
            'page[number]': page,
            'page[size]': 100,
            'filter[orders][creationDate][$ge]': timestamp_ms,
            'filter[orders][state]': 'NEW'
        })
        
        if not result.success:
            return result
            
        page_orders = result.data.get('data', [])
        if not page_orders:
            break
            
        all_orders.extend(page_orders)
        page += 1
        
        meta = result.data.get('meta', {})
        total_pages = meta.get('pageCount', 1)
        if page >= total_pages:
            break
    
    # Filter to only APPROVED_BY_BANK (ready for acceptance)
    new_orders = []
    for order in all_orders:
        attrs = order.get('attributes', {})
        if attrs.get('status') == 'APPROVED_BY_BANK':
            new_orders.append(order)
    
    return APIResponse(
        success=True,
        data={'data': new_orders, 'meta': {'totalCount': len(new_orders)}},
        status_code=200
    )
```

---

## ISSUE 4: Refactor to Avoid Code Duplication

The three helper methods share pagination logic. Refactor:

### Implementation

Add private helper method:

```python
def _fetch_orders_with_pagination(
    self, 
    state: str,
    since: str,
    max_pages: int = 20
) -> APIResponse:
    """
    Fetch all orders matching state with pagination.
    
    Returns:
        APIResponse with all matching orders
    """
    all_orders = []
    page = 0
    
    while page < max_pages:
        timestamp_ms = self._to_timestamp_ms(since)
        result = self._request('GET', 'orders', params={
            'page[number]': page,
            'page[size]': 100,
            'filter[orders][creationDate][$ge]': timestamp_ms,
            'filter[orders][state]': state
        })
        
        if not result.success:
            return result
            
        page_orders = result.data.get('data', [])
        if not page_orders:
            break
            
        all_orders.extend(page_orders)
        page += 1
        
        meta = result.data.get('meta', {})
        total_pages = meta.get('pageCount', 1)
        if page >= total_pages:
            break
    
    return APIResponse(
        success=True,
        data={'data': all_orders},
        status_code=200
    )
```

Then simplify helper methods:

```python
def get_pending_assembly_orders(self, since: str = None) -> APIResponse:
    """Get orders awaiting assembly (Dashboard: Упаковка tab)."""
    if since is None:
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    result = self._fetch_orders_with_pagination('KASPI_DELIVERY', since)
    if not result.success:
        return result
    
    # Filter: status=ACCEPTED_BY_MERCHANT, assembled=false
    pending = [
        o for o in result.data.get('data', [])
        if o.get('attributes', {}).get('status') == 'ACCEPTED_BY_MERCHANT'
        and not o.get('attributes', {}).get('assembled', False)
    ]
    
    return APIResponse(
        success=True,
        data={'data': pending, 'meta': {'totalCount': len(pending)}},
        status_code=200
    )
```

---

## ISSUE 5: Add Comprehensive Unit Tests

### New Test Cases

**File:** `tests/test_kaspi_api_client.py`

Add these test cases:

```python
class TestHelperMethods:
    """Tests for dashboard-matching helper methods."""
    
    def test_get_pending_assembly_orders_filters_correctly(self, mocker):
        """Verify only unassembled ACCEPTED_BY_MERCHANT orders returned."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
                {'id': '3', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
                {'id': '4', 'attributes': {'status': 'COMPLETED', 'assembled': False}},
            ],
            'meta': {'pageCount': 1}
        }
        mock_response = APIResponse(success=True, data=mock_orders, status_code=200)
        mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        result = client.get_pending_assembly_orders(since='2025-12-01')
        
        assert result.success
        orders = result.data.get('data', [])
        assert len(orders) == 2  # Only orders 1 and 3
        for o in orders:
            assert o['attributes']['assembled'] is False
            assert o['attributes']['status'] == 'ACCEPTED_BY_MERCHANT'

    def test_get_pending_assembly_handles_pagination(self, mocker):
        """Verify all pages are fetched."""
        page1 = {'data': [{'id': '1', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}}], 'meta': {'pageCount': 2}}
        page2 = {'data': [{'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}}], 'meta': {'pageCount': 2}}
        
        call_count = [0]
        def mock_request(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return APIResponse(success=True, data=page1, status_code=200)
            return APIResponse(success=True, data=page2, status_code=200)
        
        mocker.patch.object(KaspiAPIClient, '_request', side_effect=mock_request)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        result = client.get_pending_assembly_orders(since='2025-12-01')
        
        assert result.success
        assert len(result.data['data']) == 2
        assert call_count[0] == 2  # Both pages fetched

    def test_get_pending_assembly_default_since_7_days(self, mocker):
        """Verify default since is 7 days ago."""
        mock_response = APIResponse(success=True, data={'data': [], 'meta': {}}, status_code=200)
        mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        client.get_pending_assembly_orders()  # No since param
        
        # Verify request was made with date ~7 days ago
        call_args = KaspiAPIClient._request.call_args
        params = call_args.kwargs.get('params', {})
        timestamp = params.get('filter[orders][creationDate][$ge]')
        assert timestamp is not None
        # Timestamp should be within last 8 days (7 + buffer)
        from datetime import datetime
        since_dt = datetime.fromtimestamp(timestamp / 1000)
        days_ago = (datetime.now() - since_dt).days
        assert 6 <= days_ago <= 8

    def test_get_awaiting_courier_orders_filters_assembled(self, mocker):
        """Verify only assembled ACCEPTED_BY_MERCHANT orders returned."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
                {'id': '3', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
            ],
            'meta': {'pageCount': 1}
        }
        mock_response = APIResponse(success=True, data=mock_orders, status_code=200)
        mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        result = client.get_awaiting_courier_orders(since='2025-12-01')
        
        assert result.success
        orders = result.data.get('data', [])
        assert len(orders) == 2  # Only orders 1 and 3
        for o in orders:
            assert o['attributes']['assembled'] is True

    def test_get_new_orders_filters_approved_by_bank(self, mocker):
        """Verify only APPROVED_BY_BANK orders returned."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'APPROVED_BY_BANK'}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT'}},
                {'id': '3', 'attributes': {'status': 'APPROVED_BY_BANK'}},
            ],
            'meta': {'pageCount': 1}
        }
        mock_response = APIResponse(success=True, data=mock_orders, status_code=200)
        mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        result = client.get_new_orders(since='2025-12-01')
        
        assert result.success
        orders = result.data.get('data', [])
        assert len(orders) == 2

    def test_helper_returns_api_response_on_error(self, mocker):
        """Verify error propagation."""
        mock_response = APIResponse(success=False, error='API Error', status_code=500)
        mocker.patch.object(KaspiAPIClient, '_request', return_value=mock_response)
        
        client = KaspiAPIClient('UNIVERSAL', token='test')
        result = client.get_pending_assembly_orders(since='2025-12-01')
        
        assert not result.success
        assert result.error == 'API Error'
```

---

## ISSUE 6: Live API Validation Suite

Create a validation script that runs against live API:

**File:** `scripts/validate_kaspi_api.py`

```python
#!/usr/bin/env python3
"""
Kaspi API Validation Suite

Validates API client against live Kaspi API.
Run after any API client changes to ensure functionality.

Usage:
    python scripts/validate_kaspi_api.py
    python scripts/validate_kaspi_api.py --store UNIVERSAL
    python scripts/validate_kaspi_api.py --verbose
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.integrations.kaspi_api_client import KaspiAPIClient, validate_all_tokens


def validate_token(store_code: str, verbose: bool = False) -> bool:
    """Validate API token for store."""
    print(f"\n{'='*60}")
    print(f"VALIDATING: {store_code}")
    print('='*60)
    
    try:
        client = KaspiAPIClient(store_code)
        valid = client.validate_token()
        print(f"Token validation: {'✅ PASS' if valid else '❌ FAIL'}")
        return valid
    except Exception as e:
        print(f"Token validation: ❌ ERROR - {e}")
        return False


def validate_list_orders(store_code: str, verbose: bool = False) -> bool:
    """Validate list_orders endpoint."""
    print(f"\n--- list_orders ---")
    
    try:
        client = KaspiAPIClient(store_code)
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        result = client.list_orders(since=since, page_size=10)
        
        if result.success:
            orders = result.data.get('data', [])
            print(f"✅ PASS - Fetched {len(orders)} orders")
            if verbose and orders:
                for o in orders[:3]:
                    attrs = o.get('attributes', {})
                    print(f"   - {attrs.get('code')}: {attrs.get('state')}/{attrs.get('status')}")
            return True
        else:
            print(f"❌ FAIL - {result.error}")
            return False
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_get_order(store_code: str, verbose: bool = False) -> bool:
    """Validate get_order endpoint."""
    print(f"\n--- get_order ---")
    
    try:
        client = KaspiAPIClient(store_code)
        # First get a valid order code
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        list_result = client.list_orders(since=since, page_size=1)
        
        if not list_result.success or not list_result.data.get('data'):
            print(f"⚠️ SKIP - No orders to test with")
            return True
        
        order_code = list_result.data['data'][0]['attributes']['code']
        result = client.get_order(order_code)
        
        if result.success:
            fetched_code = result.data.get('attributes', {}).get('code')
            if fetched_code == order_code:
                print(f"✅ PASS - Fetched order {order_code}")
                return True
            else:
                print(f"❌ FAIL - Code mismatch: expected {order_code}, got {fetched_code}")
                return False
        else:
            print(f"❌ FAIL - {result.error}")
            return False
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_pending_assembly(store_code: str, verbose: bool = False) -> bool:
    """Validate get_pending_assembly_orders helper."""
    print(f"\n--- get_pending_assembly_orders ---")
    
    try:
        client = KaspiAPIClient(store_code)
        result = client.get_pending_assembly_orders()
        
        if result.success:
            orders = result.data.get('data', [])
            print(f"✅ PASS - Found {len(orders)} pending assembly orders")
            
            # Verify all returned orders match criteria
            for o in orders:
                attrs = o.get('attributes', {})
                if attrs.get('assembled', False):
                    print(f"❌ FAIL - Order {attrs.get('code')} has assembled=True")
                    return False
                if attrs.get('status') != 'ACCEPTED_BY_MERCHANT':
                    print(f"❌ FAIL - Order {attrs.get('code')} has status={attrs.get('status')}")
                    return False
            
            if verbose and orders:
                for o in orders[:3]:
                    attrs = o.get('attributes', {})
                    print(f"   - {attrs.get('code')}: assembled={attrs.get('assembled')}")
            return True
        else:
            print(f"❌ FAIL - {result.error}")
            return False
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_awaiting_courier(store_code: str, verbose: bool = False) -> bool:
    """Validate get_awaiting_courier_orders helper."""
    print(f"\n--- get_awaiting_courier_orders ---")
    
    try:
        client = KaspiAPIClient(store_code)
        result = client.get_awaiting_courier_orders()
        
        if result.success:
            orders = result.data.get('data', [])
            print(f"✅ PASS - Found {len(orders)} awaiting courier orders")
            
            # Verify all returned orders match criteria
            for o in orders:
                attrs = o.get('attributes', {})
                if not attrs.get('assembled', False):
                    print(f"❌ FAIL - Order {attrs.get('code')} has assembled=False")
                    return False
            return True
        else:
            print(f"❌ FAIL - {result.error}")
            return False
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_new_orders(store_code: str, verbose: bool = False) -> bool:
    """Validate get_new_orders helper."""
    print(f"\n--- get_new_orders ---")
    
    try:
        client = KaspiAPIClient(store_code)
        result = client.get_new_orders()
        
        if result.success:
            orders = result.data.get('data', [])
            print(f"✅ PASS - Found {len(orders)} new orders")
            return True
        else:
            print(f"❌ FAIL - {result.error}")
            return False
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_dashboard_match(store_code: str, verbose: bool = False) -> bool:
    """Cross-validate helper methods against raw counts."""
    print(f"\n--- Dashboard Match Validation ---")
    
    try:
        client = KaspiAPIClient(store_code)
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Get all KASPI_DELIVERY orders via raw query
        result = client._request('GET', 'orders', params={
            'page[number]': 0,
            'page[size]': 100,
            'filter[orders][creationDate][$ge]': client._to_timestamp_ms(since),
            'filter[orders][state]': 'KASPI_DELIVERY'
        })
        
        if not result.success:
            print(f"❌ FAIL - Raw query failed: {result.error}")
            return False
        
        raw_orders = result.data.get('data', [])
        
        # Count manually
        manual_pending = 0
        manual_awaiting = 0
        for o in raw_orders:
            attrs = o.get('attributes', {})
            if attrs.get('status') == 'ACCEPTED_BY_MERCHANT':
                if attrs.get('assembled', False):
                    manual_awaiting += 1
                else:
                    manual_pending += 1
        
        # Get via helpers
        pending_result = client.get_pending_assembly_orders()
        awaiting_result = client.get_awaiting_courier_orders()
        
        helper_pending = len(pending_result.data.get('data', [])) if pending_result.success else -1
        helper_awaiting = len(awaiting_result.data.get('data', [])) if awaiting_result.success else -1
        
        print(f"Raw KASPI_DELIVERY orders: {len(raw_orders)}")
        print(f"Manual pending count: {manual_pending}")
        print(f"Helper pending count: {helper_pending}")
        print(f"Manual awaiting count: {manual_awaiting}")
        print(f"Helper awaiting count: {helper_awaiting}")
        
        if helper_pending == manual_pending and helper_awaiting == manual_awaiting:
            print("✅ PASS - Helper methods match manual counts")
            return True
        else:
            print("❌ FAIL - Counts don't match!")
            return False
            
    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def run_validation(store_code: str, verbose: bool = False) -> dict:
    """Run all validations for a store."""
    results = {
        'token': validate_token(store_code, verbose),
        'list_orders': validate_list_orders(store_code, verbose),
        'get_order': validate_get_order(store_code, verbose),
        'pending_assembly': validate_pending_assembly(store_code, verbose),
        'awaiting_courier': validate_awaiting_courier(store_code, verbose),
        'new_orders': validate_new_orders(store_code, verbose),
        'dashboard_match': validate_dashboard_match(store_code, verbose),
    }
    return results


def main():
    parser = argparse.ArgumentParser(description='Kaspi API Validation Suite')
    parser.add_argument('--store', type=str, help='Specific store to validate')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    print("="*60)
    print("KASPI API VALIDATION SUITE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    if args.store:
        stores = [args.store]
    else:
        stores = ['UNIVERSAL']  # Default to just UNIVERSAL for overnight run
    
    all_results = {}
    for store in stores:
        all_results[store] = run_validation(store, args.verbose)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    total_pass = 0
    total_fail = 0
    
    for store, results in all_results.items():
        print(f"\n{store}:")
        for test, passed in results.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {test}")
            if passed:
                total_pass += 1
            else:
                total_fail += 1
    
    print(f"\nTOTAL: {total_pass} passed, {total_fail} failed")
    
    if total_fail > 0:
        sys.exit(1)
    print("\n🎉 All validations passed!")
    return 0


if __name__ == '__main__':
    main()
```

---

## Execution Sequence

### Phase 1: Fix Implementation (30 min)

```bash
# 1. Read current implementation
grep -n "get_pending_assembly_orders\|get_awaiting_courier_orders\|_fetch_orders" core/integrations/kaspi_api_client.py

# 2. Backup current file
cp core/integrations/kaspi_api_client.py core/integrations/kaspi_api_client.py.bak

# 3. Apply fixes from ISSUE 1-4 above
# (Edit the file with corrected implementations)

# 4. Verify syntax
python -m py_compile core/integrations/kaspi_api_client.py
```

### Phase 2: Add Tests (30 min)

```bash
# 1. Add new test cases from ISSUE 5
# (Edit tests/test_kaspi_api_client.py)

# 2. Run tests
python -m pytest tests/test_kaspi_api_client.py -v

# 3. Verify all pass
# Expected: 55+ tests passing
```

### Phase 3: Create Validation Script (15 min)

```bash
# 1. Create validation script from ISSUE 6
# (Create scripts/validate_kaspi_api.py)

# 2. Make executable
chmod +x scripts/validate_kaspi_api.py
```

### Phase 4: Live Validation (15 min)

```bash
# 1. Run validation suite
python scripts/validate_kaspi_api.py --verbose

# 2. Verify all checks pass
# Expected: All ✅

# 3. Validate against all 5 stores
python scripts/validate_kaspi_api.py --store UNIVERSAL --verbose
python scripts/validate_kaspi_api.py --store ACMEWEAR --verbose
python scripts/validate_kaspi_api.py --store 11KZ --verbose
python scripts/validate_kaspi_api.py --store MELVIS --verbose
python scripts/validate_kaspi_api.py --store STOREB --verbose
```

### Phase 5: Integration Test (15 min)

```bash
# 1. Run sync script with dry-run
python scripts/sync_kaspi_orders.py --store UNIVERSAL --dry-run

# 2. Verify order counts reasonable
# Expected: Should show 500+ orders from last 7 days

# 3. Test helper method specifically
python -c "
from dotenv import load_dotenv
load_dotenv()
from core.integrations.kaspi_api_client import KaspiAPIClient
client = KaspiAPIClient('UNIVERSAL')
result = client.get_pending_assembly_orders()
print(f'Pending assembly: {len(result.data.get(\"data\", []))} orders')
"
# Expected: 30-40 orders (should match dashboard)
```

### Phase 6: Commit & Document (10 min)

```bash
# 1. Run full test suite
python -m pytest tests/ -v --tb=short

# 2. Commit changes
git add -A
git commit -m "fix(kaspi): Complete API helper methods with pagination support

Fixed:
- get_pending_assembly_orders() now correctly returns pending orders
- get_awaiting_courier_orders() filters to assembled orders
- Added get_new_orders() helper
- Added _fetch_orders_with_pagination() to DRY up code
- All methods now handle pagination correctly

Added:
- scripts/validate_kaspi_api.py for live API validation
- 8 new unit tests for helper methods
- Dashboard match validation

Tested:
- All 5 stores validated
- Helper methods match dashboard counts
- 55+ tests passing"

# 3. Push
git push origin main
```

---

## Success Criteria

After overnight execution, these conditions MUST be true:

1. **Tests:** 55+ tests passing in `test_kaspi_api_client.py`
2. **Token validation:** All 5 stores return ✅
3. **Helper methods:**
   - `get_pending_assembly_orders()` returns 30-40 orders (matching dashboard)
   - `get_awaiting_courier_orders()` returns assembled orders only
   - `get_new_orders()` returns APPROVED_BY_BANK orders
4. **Dashboard match:** Helper counts == manual query counts
5. **Sync script:** `sync_kaspi_orders.py --store UNIVERSAL --dry-run` completes without errors

---

## Failure Recovery

If any phase fails:

1. **Restore backup:** `cp core/integrations/kaspi_api_client.py.bak core/integrations/kaspi_api_client.py`
2. **Log error details** to `logs/opus_overnight_errors.log`
3. **Create issue** in `ISSUES.md` with:
   - Phase that failed
   - Error message
   - Attempted fix
   - Current state

---

## Post-Execution Report

Create `logs/opus_overnight_report_YYYYMMDD.md`:

```markdown
# Opus Overnight Execution Report

**Date:** [auto-fill]
**Duration:** [auto-fill]
**Status:** [PASS/FAIL]

## Tests
- Total: [X]
- Passed: [X]
- Failed: [X]

## Store Validations
- UNIVERSAL: [✅/❌]
- ACMEWEAR: [✅/❌]
- 11KZ: [✅/❌]
- MELVIS: [✅/❌]
- STOREB: [✅/❌]

## Helper Method Validation
- get_pending_assembly_orders: [count] orders
- get_awaiting_courier_orders: [count] orders
- get_new_orders: [count] orders
- Dashboard match: [✅/❌]

## Commits
- [commit hash]: [message]

## Issues Encountered
- [list any issues]

## Next Steps for Adil
1. [action items]
```

---

*Document created: 2025-12-08 03:00 GMT+5*
*For execution by: Claude Opus (overnight autonomous run)*
