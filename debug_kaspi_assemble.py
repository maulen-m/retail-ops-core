#!/usr/bin/env python3
"""
Debug script to see raw Kaspi API response for assemble_order.
This bypasses the exception handling to show the actual error.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# Load env
from dotenv import load_dotenv
load_dotenv()

# Get token
token = os.environ.get('KASPI_TOKEN_UNIVERSAL')
if not token:
    print("❌ KASPI_TOKEN_UNIVERSAL not set")
    sys.exit(1)

BASE_URL = "https://kaspi.kz/shop/api/v2"

headers = {
    'Authorization': token,
    'X-Auth-Token': token,
    'Accept': 'application/vnd.api+json',
    'Content-Type': 'application/vnd.api+json',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
}

def get_pending_orders():
    """Get pending assembly orders."""
    since_ts = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
    params = {
        'page[number]': 0,
        'page[size]': 10,
        'filter[orders][state]': 'KASPI_DELIVERY',
        'filter[orders][status]': 'ACCEPTED_BY_MERCHANT',
        'filter[orders][creationDate][$ge]': since_ts,
    }
    
    resp = requests.get(f"{BASE_URL}/orders", headers=headers, params=params)
    print(f"\n📋 GET /orders status: {resp.status_code}")
    
    if not resp.ok:
        print(f"❌ Error: {resp.text}")
        return []
    
    data = resp.json()
    orders = data.get('data', [])
    
    # Filter to unassembled
    pending = [o for o in orders if not o.get('attributes', {}).get('assembled', False)]
    print(f"Found {len(pending)} pending orders")
    
    return pending


def get_order_base64_id(order_code):
    """Get Base64 ID for order code."""
    params = {'filter[orders][code]': order_code}
    resp = requests.get(f"{BASE_URL}/orders", headers=headers, params=params)
    
    print(f"\n🔍 GET order {order_code} status: {resp.status_code}")
    
    if not resp.ok:
        print(f"❌ Error: {resp.text}")
        return None
    
    data = resp.json()
    orders = data.get('data', [])
    
    if not orders:
        print(f"❌ Order not found")
        return None
    
    base64_id = orders[0].get('id')
    order_attrs = orders[0].get('attributes', {})
    
    print(f"✅ Found order:")
    print(f"   Base64 ID: {base64_id}")
    print(f"   Code: {order_attrs.get('code')}")
    print(f"   State: {order_attrs.get('state')}")
    print(f"   Status: {order_attrs.get('status')}")
    print(f"   Assembled: {order_attrs.get('assembled')}")
    
    return base64_id


def assemble_order_debug(order_code, parcel_count=1):
    """Try to assemble order and show raw response."""
    
    # First get Base64 ID
    base64_id = get_order_base64_id(order_code)
    if not base64_id:
        return
    
    # Build payload per Kaspi docs
    payload = {
        "data": {
            "type": "orders",
            "id": base64_id,
            "attributes": {
                "status": "ASSEMBLE",
                "numberOfSpace": str(parcel_count)  # STRING!
            }
        }
    }
    
    print(f"\n📤 POST /orders payload:")
    print(json.dumps(payload, indent=2))
    
    # Make the request
    resp = requests.post(f"{BASE_URL}/orders", headers=headers, json=payload)
    
    print(f"\n📥 Response status: {resp.status_code}")
    print(f"📥 Response headers:")
    for k, v in resp.headers.items():
        if k.lower() in ['content-type', 'x-request-id', 'date']:
            print(f"   {k}: {v}")
    
    print(f"\n📥 Response body:")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except:
        print(resp.text)
    
    if resp.ok:
        print("\n✅ SUCCESS!")
    else:
        print(f"\n❌ FAILED with status {resp.status_code}")


def main():
    print("=" * 60)
    print("KASPI API DEBUG - ASSEMBLE ORDER")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Get pending orders
    pending = get_pending_orders()
    
    if not pending:
        print("\n⚠️ No pending orders to test")
        return
    
    # Show available orders
    print("\n📋 Available pending orders:")
    for i, o in enumerate(pending[:5]):
        attrs = o.get('attributes', {})
        print(f"  [{i}] {attrs.get('code')} - {attrs.get('state')}/{attrs.get('status')} - assembled={attrs.get('assembled')}")
    
    # Test with first order
    test_order = pending[0]['attributes']['code']
    print(f"\n🎯 Testing with order: {test_order}")
    
    assemble_order_debug(test_order)


if __name__ == '__main__':
    main()
