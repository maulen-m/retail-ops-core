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

        # Get all KASPI_DELIVERY + ACCEPTED_BY_MERCHANT orders via pagination helper
        result = client._fetch_orders_with_pagination(
            'KASPI_DELIVERY',
            since,
            status='ACCEPTED_BY_MERCHANT'
        )

        if not result.success:
            print(f"❌ FAIL - Raw query failed: {result.error}")
            return False

        raw_orders = result.data.get('data', [])

        # Count manually
        manual_pending = 0
        manual_awaiting = 0
        for o in raw_orders:
            attrs = o.get('attributes', {})
            if attrs.get('assembled', False):
                manual_awaiting += 1
            else:
                manual_pending += 1

        # Get via helpers
        pending_result = client.get_pending_assembly_orders()
        awaiting_result = client.get_awaiting_courier_orders()

        helper_pending = len(pending_result.data.get('data', [])) if pending_result.success else -1
        helper_awaiting = len(awaiting_result.data.get('data', [])) if awaiting_result.success else -1

        print(f"Total KASPI_DELIVERY + ACCEPTED_BY_MERCHANT: {len(raw_orders)}")
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


def validate_get_order_entries(store_code: str, verbose: bool = False) -> bool:
    """Validate get_order_entries works."""
    print(f"\n--- get_order_entries ---")

    try:
        client = KaspiAPIClient(store_code)

        # Get any order
        since = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        orders = client.list_orders(since=since, page_size=1)
        if not orders.success or not orders.data.get('data'):
            print("⚠️ SKIP - No orders to test")
            return True

        test_order = orders.data['data'][0]['attributes']['code']
        result = client.get_order_entries(test_order)

        if result.success:
            entries = result.data.get('data', [])
            print(f"✅ PASS - Order {test_order} has {len(entries)} entries")

            if verbose and entries:
                for e in entries[:2]:
                    offer = e.get('attributes', {}).get('offer', {})
                    print(f"   - {offer.get('name', 'Unknown')[:50]}...")
            return True
        else:
            print(f"❌ FAIL - {result.error}")
            return False

    except Exception as e:
        print(f"❌ ERROR - {e}")
        return False


def validate_assemble_order(store_code: str, verbose: bool = False) -> bool:
    """Validate assemble_order works (on first pending order)."""
    print(f"\n--- assemble_order ---")

    try:
        client = KaspiAPIClient(store_code)

        if not client.writes_enabled:
            print("⚠️ SKIP - Writes disabled (ENABLE_KASPI_WRITE=0)")
            return True

        # Get a pending order
        pending = client.get_pending_assembly_orders()
        if not pending.success or not pending.data.get('data'):
            print("⚠️ SKIP - No pending orders to test")
            return True

        test_order = pending.data['data'][0]['attributes']['code']
        print(f"Testing with order: {test_order}")

        result = client.assemble_order(test_order)

        if result.success:
            print(f"✅ PASS - Order {test_order} assembled")
            return True
        else:
            print(f"❌ FAIL - {result.error}")
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
        'get_order_entries': validate_get_order_entries(store_code, verbose),
        'pending_assembly': validate_pending_assembly(store_code, verbose),
        'awaiting_courier': validate_awaiting_courier(store_code, verbose),
        'new_orders': validate_new_orders(store_code, verbose),
        'dashboard_match': validate_dashboard_match(store_code, verbose),
        'assemble_order': validate_assemble_order(store_code, verbose),
    }
    return results


def main():
    parser = argparse.ArgumentParser(description='Kaspi API Validation Suite')
    parser.add_argument('--store', type=str, help='Specific store to validate')
    parser.add_argument('--all-stores', action='store_true', help='Validate all 5 stores')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("="*60)
    print("KASPI API VALIDATION SUITE")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    if args.all_stores:
        stores = ['UNIVERSAL', 'ACMEWEAR', '11KZ', 'MELVIS', 'STOREB']
    elif args.store:
        stores = [args.store]
    else:
        stores = ['UNIVERSAL']  # Default to just UNIVERSAL

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
