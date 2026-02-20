"""
Kaspi Shop API Client for Order Management (Phase 9.5).

Provides sync HTTP client for Kaspi Shop API with:
- Multi-store token support from environment variables
- Exponential backoff retry logic
- Rate limiting (50 req/sec conservative)
- ENABLE_KASPI_WRITE guard for write operations

API Base: https://kaspi.kz/shop/api/v2/

Environment Variables:
    KASPI_TOKEN_UNIVERSAL: Token for Universal store
    KASPI_TOKEN_ACMEWEAR: Token for AcmeWear store
    KASPI_TOKEN_11KZ: Token for 11KZ store
    KASPI_TOKEN_MELVIS: Token for Store-C store
    KASPI_TOKEN_STOREB: Token for MGroup store
    ENABLE_KASPI_WRITE: Set to "1" to enable write operations (default: "0")

Usage:
    from core.integrations.kaspi_api_client import KaspiAPIClient

    client = KaspiAPIClient(store_code='UNIVERSAL')
    orders = client.list_orders(state='NEW', since='2025-12-01')

    # Write operations require ENABLE_KASPI_WRITE=1
    if client.writes_enabled:
        client.accept_order(order_code='123456')
"""

import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

BASE_URL = "https://kaspi.kz/shop/api/v2"

# Rate limit: 50 requests per second (conservative)
RATE_LIMIT_RPS = 50
MIN_REQUEST_INTERVAL = 1.0 / RATE_LIMIT_RPS  # 0.02 seconds

# Retry settings (Phase 12 Part 6: reduced for faster failure)
MAX_RETRIES = 2           # 2 retries = 3 attempts total (was 3)
BACKOFF_FACTOR = 0.3      # Faster backoff (was 0.5)

# Timeout settings (seconds) - Phase 12 Part 6: reduced to prevent 40-min hangs
DEFAULT_TIMEOUT = 15      # Most API calls complete in <5s (was 30)
DOWNLOAD_TIMEOUT = 45     # Waybill downloads need more time

# API limits
MAX_DATE_RANGE_DAYS = 14      # Kaspi API enforces max 14-day date range
DEFAULT_SYNC_DAYS = 7         # Default lookback for sync operations
MAX_PAGE_SIZE = 100           # Kaspi API max items per page

# Token environment variable prefix
TOKEN_ENV_PREFIX = "KASPI_TOKEN_"

# Store code mapping to env var names
STORE_TOKEN_MAP = {
    'UNIVERSAL': 'KASPI_TOKEN_UNIVERSAL',
    'ACMEWEAR': 'KASPI_TOKEN_ACMEWEAR',
    '11KZ': 'KASPI_TOKEN_11KZ',
    'MELVIS': 'KASPI_TOKEN_MELVIS',
    'STOREB': 'KASPI_TOKEN_STOREB',
}


class OrderState(str, Enum):
    """Kaspi order states."""
    NEW = 'NEW'
    ACCEPTED_BY_MERCHANT = 'ACCEPTED_BY_MERCHANT'
    ASSEMBLY = 'ASSEMBLY'
    KASPI_DELIVERY = 'KASPI_DELIVERY'
    DELIVERY = 'DELIVERY'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'
    RETURNING = 'RETURNING'
    RETURNED = 'RETURNED'


@dataclass
class APIResponse:
    """Standardized API response wrapper."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    status_code: int = 0
    raw_response: Optional[requests.Response] = None


@dataclass
class OrderEntry:
    """Single order line item."""
    entry_id: str
    product_name: str
    offer_id: str
    quantity: int
    price: float
    total_price: float


@dataclass
class Order:
    """Kaspi order with details."""
    order_id: str
    code: str
    state: str
    created_at: datetime
    total_price: float
    delivery_cost: float
    customer_phone: Optional[str] = None
    planned_delivery_date: Optional[datetime] = None
    waybill_url: Optional[str] = None
    entries: list = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class KaspiAPIError(Exception):
    """Base exception for Kaspi API errors."""
    pass


class KaspiAuthError(KaspiAPIError):
    """Authentication/authorization error (401/403)."""
    pass


class KaspiRateLimitError(KaspiAPIError):
    """Rate limit exceeded (429)."""
    pass


class KaspiWriteDisabledError(KaspiAPIError):
    """Write operation attempted with ENABLE_KASPI_WRITE=0."""
    pass


class KaspiNotFoundError(KaspiAPIError):
    """Resource not found (404)."""
    pass


# =============================================================================
# CLIENT
# =============================================================================

class KaspiAPIClient:
    """
    Kaspi Shop API client with retry logic and rate limiting.

    Args:
        store_code: Store identifier (UNIVERSAL, ACMEWEAR, 11KZ, MELVIS, STOREB)
        token: Optional explicit token (overrides env var lookup)
        timeout: Request timeout in seconds
        enable_writes: Override for ENABLE_KASPI_WRITE env var

    Attributes:
        store_code: Current store code
        writes_enabled: Whether write operations are allowed
        last_request_time: Timestamp of last API request (for rate limiting)
    """

    def __init__(
        self,
        store_code: str,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        enable_writes: Optional[bool] = None,
    ):
        self.store_code = store_code.upper()
        self.timeout = timeout
        self._token = token or self._load_token(self.store_code)
        self._last_request_time = 0.0

        # Write operations guard
        if enable_writes is not None:
            self.writes_enabled = enable_writes
        else:
            self.writes_enabled = os.environ.get('ENABLE_KASPI_WRITE', '0') == '1'

        # Setup session with retry logic
        self._session = self._create_session()

        logger.info(
            f"KaspiAPIClient initialized for {self.store_code}, "
            f"writes_enabled={self.writes_enabled}"
        )

    def _load_token(self, store_code: str) -> str:
        """Load API token from environment variable."""
        env_var = STORE_TOKEN_MAP.get(store_code)
        if not env_var:
            raise ValueError(
                f"Unknown store code: {store_code}. "
                f"Valid codes: {list(STORE_TOKEN_MAP.keys())}"
            )

        token = os.environ.get(env_var)
        if not token:
            raise KaspiAuthError(
                f"Token not found for {store_code}. "
                f"Set {env_var} environment variable."
            )

        return token

    def _create_session(self) -> requests.Session:
        """Create session with retry adapter."""
        session = requests.Session()

        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _get_headers(self) -> dict:
        """Get request headers with authorization."""
        return {
            'Authorization': self._token,
            'X-Auth-Token': self._token,
            'Accept': 'application/vnd.api+json',
            'Content-Type': 'application/vnd.api+json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            sleep_time = MIN_REQUEST_INTERVAL - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> APIResponse:
        """
        Make API request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body data
            timeout: Request timeout (overrides default)

        Returns:
            APIResponse with success status and data/error
        """
        self._rate_limit()

        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        timeout = timeout or self.timeout

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
                timeout=timeout,
            )

            # Handle specific status codes
            if response.status_code == 401:
                raise KaspiAuthError("Invalid or expired token")
            if response.status_code == 403:
                raise KaspiAuthError("Access denied to this resource")
            if response.status_code == 404:
                raise KaspiNotFoundError(f"Resource not found: {endpoint}")
            if response.status_code == 429:
                raise KaspiRateLimitError("Rate limit exceeded")

            # Parse JSON response
            try:
                data = response.json()
            except ValueError:
                data = response.text

            if response.ok:
                return APIResponse(
                    success=True,
                    data=data,
                    status_code=response.status_code,
                    raw_response=response,
                )
            else:
                error_msg = data.get('errors', [{}])[0].get('detail', str(data)) \
                    if isinstance(data, dict) else str(data)
                return APIResponse(
                    success=False,
                    error=error_msg,
                    status_code=response.status_code,
                    raw_response=response,
                )

        except requests.exceptions.Timeout:
            return APIResponse(
                success=False,
                error=f"Request timeout after {timeout}s",
                status_code=0,
            )
        except requests.exceptions.ConnectionError as e:
            return APIResponse(
                success=False,
                error=f"Connection error: {str(e)}",
                status_code=0,
            )
        except (KaspiAuthError, KaspiRateLimitError, KaspiNotFoundError):
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in API request: {e}")
            return APIResponse(
                success=False,
                error=f"Unexpected error: {str(e)}",
                status_code=0,
            )

    def _require_write_enabled(self):
        """Check if write operations are enabled."""
        if not self.writes_enabled:
            raise KaspiWriteDisabledError(
                "Write operations disabled. Set ENABLE_KASPI_WRITE=1 to enable."
            )

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def list_orders(
        self,
        state: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        page_number: int = 0,
        page_size: int = 100,
        delivery_type: Optional[str] = None,
        signature_required: Optional[bool] = None,
        include_orders: Optional[str] = None,
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

        Returns:
            APIResponse with list of orders in data
        """
        params = {
            'page[number]': page_number,
            'page[size]': min(page_size, MAX_PAGE_SIZE),
        }

        if state:
            params['filter[orders][state]'] = state

        if status:
            params['filter[orders][status]'] = status

        if since:
            # Convert to milliseconds timestamp if date string
            since_ts = self._to_timestamp_ms(since)
            params['filter[orders][creationDate][$ge]'] = since_ts

        if until:
            until_ts = self._to_timestamp_ms(until)
            params['filter[orders][creationDate][$le]'] = until_ts

        if delivery_type is not None:
            params['filter[orders][deliveryType]'] = delivery_type

        if signature_required is not None:
            params['filter[orders][signatureRequired]'] = str(bool(signature_required)).lower()

        if include_orders is not None:
            params['filter[orders][includeOrders]'] = include_orders

        return self._request('GET', 'orders', params=params)

    def list_all_orders(
        self,
        state: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        signature_required: Optional[bool] = None,
        include_orders: Optional[str] = None,
        max_pages: int = 100,
    ) -> list[dict]:
        """
        List all orders with pagination handling.

        Args:
            state: Filter by order state
            since: Filter orders created after this date
            until: Filter orders created before this date
            max_pages: Maximum pages to fetch (safety limit)

        Returns:
            List of all order dicts
        """
        all_orders = []
        page = 0

        while page < max_pages:
            response = self.list_orders(
                state=state,
                status=status,
                since=since,
                until=until,
                signature_required=signature_required,
                include_orders=include_orders,
                page_number=page,
                page_size=100,
            )

            if not response.success:
                logger.error(f"Failed to fetch page {page}: {response.error}")
                break

            data = response.data.get('data', [])
            if not data:
                break

            all_orders.extend(data)
            page += 1

            # Check if there are more pages
            if len(data) < 100:
                break

        logger.info(f"Fetched {len(all_orders)} orders across {page} pages")
        return all_orders

    def get_order(self, order_code: str) -> APIResponse:
        """
        Get single order by code.

        Note: Kaspi API requires Base64 order ID for direct endpoint,
        but we use filter by code which accepts the numeric code.

        Args:
            order_code: Kaspi order code

        Returns:
            APIResponse with order data
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

    def _get_order_base64_id(self, order_code: str) -> str:
        """
        Get Base64 order ID from order code.

        Kaspi API requires Base64 ID for direct endpoints and write operations,
        but we typically have the numeric order code.

        Args:
            order_code: Numeric order code (e.g., "738784236")

        Returns:
            Base64 order ID (e.g., "NzM4Nzg0MjM2")

        Raises:
            KaspiNotFoundError: If order not found
            KaspiAPIError: If order missing ID field
        """
        result = self.get_order(order_code)
        if not result.success:
            raise KaspiNotFoundError(f"Order {order_code} not found")

        base64_id = result.data.get('id')
        if not base64_id:
            raise KaspiAPIError(f"Order {order_code} missing ID field")

        return base64_id

    def get_order_entries(self, order_code: str) -> APIResponse:
        """
        Get order line items (entries).

        Args:
            order_code: Kaspi order code

        Returns:
            APIResponse with order entries
        """
        base64_id = self._get_order_base64_id(order_code)
        return self._request('GET', f'orders/{base64_id}/entries')

    def get_masterproduct(self, masterproduct_id: str) -> APIResponse:
        """
        Get masterproduct details (Kaspi's official product info).

        The masterproduct contains the official Kaspi product name that
        customers see on the marketplace.

        Args:
            masterproduct_id: Base64-encoded masterproduct ID from entry relationships

        Returns:
            APIResponse with masterproduct data including 'name' (Kaspi public name)
        """
        return self._request('GET', f'masterproducts/{masterproduct_id}')

    def get_waybill_url(self, order: dict) -> Optional[str]:
        """
        Extract waybill URL from order data.

        Args:
            order: Order dict from API response

        Returns:
            Waybill URL or None
        """
        try:
            attrs = order.get('attributes', {})
            kaspi_delivery = attrs.get('kaspiDelivery', {})
            return kaspi_delivery.get('waybill')
        except (KeyError, TypeError):
            return None

    def download_waybill(self, waybill_url: str) -> APIResponse:
        """
        Download waybill PDF from URL.

        Args:
            waybill_url: Direct waybill URL

        Returns:
            APIResponse with PDF binary in data
        """
        self._rate_limit()

        try:
            response = self._session.get(
                waybill_url,
                headers={'Authorization': self._token},
                timeout=DOWNLOAD_TIMEOUT,
            )

            if response.ok:
                return APIResponse(
                    success=True,
                    data=response.content,
                    status_code=response.status_code,
                )
            else:
                return APIResponse(
                    success=False,
                    error=f"Download failed: {response.status_code}",
                    status_code=response.status_code,
                )
        except Exception as e:
            return APIResponse(
                success=False,
                error=f"Download error: {str(e)}",
                status_code=0,
            )

    # =========================================================================
    # WRITE OPERATIONS (require ENABLE_KASPI_WRITE=1)
    # =========================================================================

    def accept_order(self, order_code: str) -> APIResponse:
        """
        Accept order (NEW -> ACCEPTED_BY_MERCHANT).

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            order_code: Kaspi order code

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.info(f"Accepting order {order_code}")

        base64_id = self._get_order_base64_id(order_code)

        data = {
            'data': {
                'type': 'orders',
                'id': base64_id,
                'attributes': {
                    'status': 'ACCEPTED_BY_MERCHANT',
                }
            }
        }

        return self._request('POST', 'orders', json_data=data)

    def assemble_order(
        self,
        order_code: str,
        parcel_count: int = 1,
    ) -> APIResponse:
        """
        Mark order as assembled (status: ASSEMBLE).

        For KASPI_DELIVERY orders, this moves them from "Упаковка" to "Передача курьеру".

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            order_code: Kaspi order code
            parcel_count: Number of parcels (default 1)

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.info(f"Assembling order {order_code} with {parcel_count} parcels")

        base64_id = self._get_order_base64_id(order_code)
        return self.assemble_order_by_id(base64_id, order_code, parcel_count=parcel_count)

    def assemble_order_by_id(
        self,
        base64_id: str,
        order_code: str,
        parcel_count: int = 1,
    ) -> APIResponse:
        """
        Mark order as assembled using pre-fetched Base64 ID.

        This avoids re-fetching the order by code, which can fail with 404
        if the order has changed state since the initial listing.

        For KASPI_DELIVERY orders, this moves them from "Упаковка" to "Передача курьеру".

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            base64_id: Pre-fetched Base64 order ID (from list_all_orders)
            order_code: Kaspi order code (for logging)
            parcel_count: Number of parcels (default 1)

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.info(f"Assembling order {order_code} (ID: {base64_id}) with {parcel_count} parcels")

        # Preferred endpoint (works for Universal + other stores)
        assemble_payload = {'data': {'numberOfSpace': str(parcel_count)}}
        try:
            result = self._request(
                'POST',
                f'orders/{base64_id}/assemble',
                json_data=assemble_payload,
            )
            if result.success:
                return result
        except (KaspiNotFoundError, KaspiAuthError, KaspiRateLimitError):
            # Fall back to legacy endpoint below
            pass
        except Exception as exc:
            logger.warning(f"Assemble via /orders/{base64_id}/assemble failed: {exc}")

        # Legacy fallback (some stores still accept status update on /orders)
        data = {
            'data': {
                'type': 'orders',
                'id': base64_id,
                'attributes': {
                    'status': 'ASSEMBLE',
                    'numberOfSpace': str(parcel_count),
                }
            }
        }

        return self._request('POST', 'orders', json_data=data)

    def ship_order(self, order_code: str) -> APIResponse:
        """
        Ship order (hand over to Kaspi delivery).

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            order_code: Kaspi order code

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.info(f"Shipping order {order_code}")

        base64_id = self._get_order_base64_id(order_code)

        data = {
            'data': {
                'type': 'orders',
                'id': base64_id,
                'attributes': {
                    'status': 'COMPLETED',
                }
            }
        }

        return self._request('POST', 'orders', json_data=data)

    def cancel_order(
        self,
        order_code: str,
        reason: str = 'OUT_OF_STOCK',
    ) -> APIResponse:
        """
        Cancel order.

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            order_code: Kaspi order code
            reason: Cancellation reason (OUT_OF_STOCK, CUSTOMER_REQUEST, etc.)

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.warning(f"Cancelling order {order_code} with reason: {reason}")

        base64_id = self._get_order_base64_id(order_code)

        data = {
            'data': {
                'type': 'orders',
                'id': base64_id,
                'attributes': {
                    'status': 'CANCELLED',
                    'cancellationReason': reason,
                }
            }
        }

        return self._request('POST', 'orders', json_data=data)

    def complete_order(
        self,
        order_code: str,
        security_code: str,
    ) -> APIResponse:
        """
        Complete order with 2-step verification.

        Requires ENABLE_KASPI_WRITE=1.

        Args:
            order_code: Kaspi order code
            security_code: Customer's security code

        Returns:
            APIResponse with updated order
        """
        self._require_write_enabled()
        logger.info(f"Completing order {order_code}")

        base64_id = self._get_order_base64_id(order_code)

        data = {
            'data': {
                'type': 'orders',
                'id': base64_id,
                'attributes': {
                    'status': 'COMPLETED',
                    'signature': security_code,
                }
            }
        }

        return self._request('POST', 'orders', json_data=data)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _fetch_orders_with_pagination(
        self,
        state: str,
        since: str,
        status: Optional[str] = None,
        max_pages: int = 20
    ) -> APIResponse:
        """
        Fetch all orders matching filters with pagination.

        Args:
            state: Order state to filter by (NEW, KASPI_DELIVERY, etc.)
            since: Start date (YYYY-MM-DD)
            status: Optional order status filter (ACCEPTED_BY_MERCHANT, etc.)
            max_pages: Maximum pages to fetch (safety limit)

        Returns:
            APIResponse with all matching orders in data['data']
        """
        all_orders = []
        page = 0

        while page < max_pages:
            params = {
                'page[number]': page,
                'page[size]': 100,
                'filter[orders][creationDate][$ge]': self._to_timestamp_ms(since),
                'filter[orders][state]': state
            }
            if status:
                params['filter[orders][status]'] = status

            result = self._request('GET', 'orders', params=params)

            if not result.success:
                return result

            page_orders = result.data.get('data', [])
            if not page_orders:
                break

            all_orders.extend(page_orders)
            page += 1

            # Check if more pages exist
            meta = result.data.get('meta', {})
            total_pages = meta.get('pageCount', 1)
            if page >= total_pages:
                break

        return APIResponse(
            success=True,
            data={'data': all_orders, 'meta': {'totalCount': len(all_orders)}},
            status_code=200
        )

    def _to_timestamp_ms(self, date_str: str) -> int:
        """Convert date string to milliseconds timestamp."""
        if isinstance(date_str, int):
            return date_str

        try:
            # Try ISO8601 with time
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            try:
                # Try date only
                dt = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid date format: {date_str}")

        return int(dt.timestamp() * 1000)

    def validate_token(self) -> bool:
        """
        Validate API token by making a test request.
        Uses 7-day window to respect API's 14-day max date range limit.

        Returns:
            True if token is valid
        """
        try:
            seven_days_ago = (datetime.now() - timedelta(days=DEFAULT_SYNC_DAYS)).strftime('%Y-%m-%d')
            response = self.list_orders(page_size=1, since=seven_days_ago)
            return response.success
        except KaspiAuthError:
            return False

    def get_store_info(self) -> dict:
        """
        Get information about current store configuration.

        Returns:
            Dict with store_code, writes_enabled, token_valid
        """
        return {
            'store_code': self.store_code,
            'writes_enabled': self.writes_enabled,
            'token_valid': self.validate_token(),
        }

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
            since = (datetime.now() - timedelta(days=DEFAULT_SYNC_DAYS)).strftime('%Y-%m-%d')

        # Fetch all KASPI_DELIVERY + ACCEPTED_BY_MERCHANT orders with pagination
        result = self._fetch_orders_with_pagination(
            state='KASPI_DELIVERY',
            since=since,
            status='ACCEPTED_BY_MERCHANT'
        )

        if not result.success:
            return result

        # Filter to only unassembled orders
        orders = result.data.get('data', [])
        pending = [
            o for o in orders
            if not o.get('attributes', {}).get('assembled', False)
        ]

        return APIResponse(
            success=True,
            data={'data': pending, 'meta': {'totalCount': len(pending)}},
            status_code=200
        )

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
            since = (datetime.now() - timedelta(days=DEFAULT_SYNC_DAYS)).strftime('%Y-%m-%d')

        # Fetch all KASPI_DELIVERY + ACCEPTED_BY_MERCHANT orders with pagination
        result = self._fetch_orders_with_pagination(
            state='KASPI_DELIVERY',
            since=since,
            status='ACCEPTED_BY_MERCHANT'
        )

        if not result.success:
            return result

        # Filter to only assembled orders
        orders = result.data.get('data', [])
        awaiting = [
            o for o in orders
            if o.get('attributes', {}).get('assembled', False) is True
        ]

        return APIResponse(
            success=True,
            data={'data': awaiting, 'meta': {'totalCount': len(awaiting)}},
            status_code=200
        )

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
            since = (datetime.now() - timedelta(days=DEFAULT_SYNC_DAYS)).strftime('%Y-%m-%d')

        # Fetch all NEW orders with pagination
        result = self._fetch_orders_with_pagination(
            state='NEW',
            since=since
        )

        if not result.success:
            return result

        # Filter to only APPROVED_BY_BANK (ready for acceptance)
        orders = result.data.get('data', [])
        new_orders = [
            o for o in orders
            if o.get('attributes', {}).get('status') == 'APPROVED_BY_BANK'
        ]

        return APIResponse(
            success=True,
            data={'data': new_orders, 'meta': {'totalCount': len(new_orders)}},
            status_code=200
        )

    def parse_order(self, raw_order: dict) -> Order:
        """
        Parse raw API order into Order dataclass.

        Args:
            raw_order: Order dict from API response

        Returns:
            Order dataclass
        """
        attrs = raw_order.get('attributes', {})

        # Parse dates
        created_at = None
        if attrs.get('creationDate'):
            created_at = datetime.fromtimestamp(attrs['creationDate'] / 1000)

        planned_date = None
        delivery = attrs.get('kaspiDelivery', {})
        if delivery.get('plannedDeliveryDate'):
            planned_date = datetime.fromtimestamp(
                delivery['plannedDeliveryDate'] / 1000
            )

        return Order(
            order_id=raw_order.get('id', ''),
            code=attrs.get('code', ''),
            state=attrs.get('state', 'NEW'),
            created_at=created_at,
            total_price=attrs.get('totalPrice', 0),
            delivery_cost=attrs.get('deliveryCost', 0),
            customer_phone=attrs.get('customer', {}).get('cellPhone'),
            planned_delivery_date=planned_date,
            waybill_url=delivery.get('waybill'),
            raw_data=raw_order,
        )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def get_client(store_code: str, **kwargs) -> KaspiAPIClient:
    """
    Factory function to get client for a store.

    Args:
        store_code: Store identifier
        **kwargs: Additional args for KaspiAPIClient

    Returns:
        Configured KaspiAPIClient
    """
    return KaspiAPIClient(store_code=store_code, **kwargs)


def get_all_clients() -> dict[str, KaspiAPIClient]:
    """
    Get clients for all configured stores.

    Returns:
        Dict mapping store_code to KaspiAPIClient
    """
    clients = {}
    for store_code in STORE_TOKEN_MAP.keys():
        try:
            clients[store_code] = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError as e:
            logger.warning(f"Skipping {store_code}: {e}")
    return clients


def validate_all_tokens() -> dict[str, bool]:
    """
    Validate tokens for all stores.

    Returns:
        Dict mapping store_code to token validity
    """
    results = {}
    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
            results[store_code] = client.validate_token()
        except KaspiAuthError:
            results[store_code] = False
    return results


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Kaspi API Client Test")
    print("=" * 60)

    # Test token validation
    print("\nValidating tokens for all stores...")
    results = validate_all_tokens()

    for store, valid in results.items():
        status = "OK" if valid else "FAILED"
        print(f"  {store}: {status}")

    # Test with Universal store
    store = sys.argv[1] if len(sys.argv) > 1 else 'UNIVERSAL'
    print(f"\nTesting {store} store...")

    try:
        client = get_client(store)
        print(f"  Token loaded: OK")
        print(f"  Writes enabled: {client.writes_enabled}")

        # Test list orders
        response = client.list_orders(state='NEW', page_size=5)
        if response.success:
            orders = response.data.get('data', [])
            print(f"  List orders (NEW): {len(orders)} found")

            if orders:
                order = orders[0]
                attrs = order.get('attributes', {})
                print(f"    Sample: {attrs.get('code')} - {attrs.get('state')}")
        else:
            print(f"  List orders failed: {response.error}")

    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
