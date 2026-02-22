"""
Tests for Kaspi API Client (Phase 9.5 - TASK-130).

Tests cover:
- Token loading from environment
- Request building and headers
- Rate limiting
- Response parsing
- Order state enum
- Error handling
- Write operation guards
"""

import os
import time
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    APIResponse,
    Order,
    OrderEntry,
    OrderState,
    KaspiAPIError,
    KaspiAuthError,
    KaspiRateLimitError,
    KaspiWriteDisabledError,
    KaspiNotFoundError,
    get_client,
    get_all_clients,
    validate_all_tokens,
    STORE_TOKEN_MAP,
    BASE_URL,
    RATE_LIMIT_RPS,
    MAX_DATE_RANGE_DAYS,
    DEFAULT_SYNC_DAYS,
    MAX_PAGE_SIZE,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    env_vars = {
        'KASPI_TOKEN_UNIVERSAL': 'test-token-universal',
        'KASPI_TOKEN_ACMEWEAR': 'test-token-acmewear',
        'KASPI_TOKEN_11KZ': 'test-token-store-d',
        'KASPI_MERCHANT_UID_UNIVERSAL': '30000001',
        'ENABLE_KASPI_WRITE': '0',
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def mock_env_with_write():
    """Set up mock environment with writes enabled."""
    env_vars = {
        'KASPI_TOKEN_UNIVERSAL': 'test-token-universal',
        'KASPI_MERCHANT_UID_UNIVERSAL': '30000001',
        'ENABLE_KASPI_WRITE': '1',
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def client(mock_env):
    """Create test client."""
    return KaspiAPIClient(store_code='UNIVERSAL')


@pytest.fixture
def client_with_write(mock_env_with_write):
    """Create test client with writes enabled."""
    return KaspiAPIClient(store_code='UNIVERSAL')


@pytest.fixture
def sample_api_order():
    """Sample order from API response."""
    return {
        'id': 'order-123',
        'attributes': {
            'code': '123456789',
            'state': 'NEW',
            'totalPrice': 15000,
            'deliveryCost': 500,
            'creationDate': int(datetime(2025, 12, 7, 10, 30).timestamp() * 1000),
            'customer': {
                'cellPhone': '+77001234567',
            },
            'kaspiDelivery': {
                'waybill': 'https://kaspi.kz/waybill/123.pdf',
                'plannedDeliveryDate': int(datetime(2025, 12, 10).timestamp() * 1000),
            }
        }
    }


# =============================================================================
# TOKEN LOADING TESTS
# =============================================================================

class TestTokenLoading:
    """Tests for token loading from environment."""

    def test_load_token_from_env(self, mock_env):
        """Test loading token from environment variable."""
        client = KaspiAPIClient(store_code='UNIVERSAL')
        assert client._token == 'test-token-universal'

    def test_load_token_from_env_different_stores(self, mock_env):
        """Test loading tokens for different stores."""
        client_uni = KaspiAPIClient(store_code='UNIVERSAL')
        client_acmewear = KaspiAPIClient(store_code='ACMEWEAR')

        assert client_uni._token == 'test-token-universal'
        assert client_acmewear._token == 'test-token-acmewear'

    def test_explicit_token_overrides_env(self, mock_env):
        """Test that explicit token parameter overrides env var."""
        client = KaspiAPIClient(store_code='UNIVERSAL', token='explicit-token')
        assert client._token == 'explicit-token'

    def test_missing_token_raises_error(self):
        """Test that missing token raises KaspiAuthError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KaspiAuthError, match="Token not found"):
                KaspiAPIClient(store_code='UNIVERSAL')

    def test_unknown_store_code_raises_error(self, mock_env):
        """Test that unknown store code raises ValueError."""
        with pytest.raises(ValueError, match="Unknown store code"):
            KaspiAPIClient(store_code='INVALID_STORE')

    def test_store_code_case_insensitive(self, mock_env):
        """Test that store code is case insensitive."""
        client = KaspiAPIClient(store_code='universal')
        assert client.store_code == 'UNIVERSAL'


# =============================================================================
# WRITE OPERATION TESTS
# =============================================================================

class TestWriteOperations:
    """Tests for write operation guards."""

    def test_writes_disabled_by_default(self, mock_env):
        """Test that writes are disabled when ENABLE_KASPI_WRITE=0."""
        client = KaspiAPIClient(store_code='UNIVERSAL')
        assert client.writes_enabled is False

    def test_writes_enabled_with_env_var(self, mock_env_with_write):
        """Test that writes are enabled when ENABLE_KASPI_WRITE=1."""
        client = KaspiAPIClient(store_code='UNIVERSAL')
        assert client.writes_enabled is True

    def test_writes_override_parameter(self, mock_env):
        """Test that enable_writes parameter overrides env var."""
        client = KaspiAPIClient(store_code='UNIVERSAL', enable_writes=True)
        assert client.writes_enabled is True

    def test_accept_order_disabled_raises_error(self, client):
        """Test that accept_order raises error when writes disabled."""
        with pytest.raises(KaspiWriteDisabledError, match="Write operations disabled"):
            client.accept_order('123')

    def test_ship_order_disabled_raises_error(self, client):
        """Test that ship_order raises error when writes disabled."""
        with pytest.raises(KaspiWriteDisabledError, match="Write operations disabled"):
            client.ship_order('123')

    def test_cancel_order_disabled_raises_error(self, client):
        """Test that cancel_order raises error when writes disabled."""
        with pytest.raises(KaspiWriteDisabledError, match="Write operations disabled"):
            client.cancel_order('123')

    def test_assemble_order_disabled_raises_error(self, client):
        """Test that assemble_order raises error when writes disabled."""
        with pytest.raises(KaspiWriteDisabledError, match="Write operations disabled"):
            client.assemble_order('123')


# =============================================================================
# ORDER STATE TESTS
# =============================================================================

class TestOrderState:
    """Tests for OrderState enum."""

    def test_order_states_exist(self):
        """Test that all expected order states exist."""
        expected_states = [
            'NEW', 'ACCEPTED_BY_MERCHANT', 'ASSEMBLY', 'KASPI_DELIVERY',
            'DELIVERY', 'COMPLETED', 'CANCELLED', 'RETURNING', 'RETURNED'
        ]
        for state in expected_states:
            assert hasattr(OrderState, state)

    def test_order_state_values(self):
        """Test that order state values match."""
        assert OrderState.NEW.value == 'NEW'
        assert OrderState.COMPLETED.value == 'COMPLETED'
        assert OrderState.CANCELLED.value == 'CANCELLED'


# =============================================================================
# REQUEST BUILDING TESTS
# =============================================================================

class TestRequestBuilding:
    """Tests for request building."""

    def test_headers_include_authorization(self, client):
        """Test that headers include authorization token."""
        headers = client._get_headers()
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'test-token-universal'

    def test_headers_include_content_type(self, client):
        """Test that headers include content type."""
        headers = client._get_headers()
        assert headers['Content-Type'] == 'application/vnd.api+json'
        assert headers['Accept'] == 'application/vnd.api+json'

    def test_headers_include_merchant_uid_when_configured(self, mock_env):
        """Write header should include merchant UID when configured."""
        client = KaspiAPIClient(store_code='UNIVERSAL')
        headers = client._get_headers()
        assert headers.get('X-Merchant-Uid') == '30000001'


# =============================================================================
# DATE CONVERSION TESTS
# =============================================================================

class TestDateConversion:
    """Tests for date string to timestamp conversion."""

    def test_date_only_conversion(self, client):
        """Test YYYY-MM-DD conversion."""
        ts = client._to_timestamp_ms('2025-12-07')
        # Should be start of day in local timezone
        assert isinstance(ts, int)
        assert ts > 0

    def test_iso8601_conversion(self, client):
        """Test ISO8601 datetime conversion."""
        ts = client._to_timestamp_ms('2025-12-07T10:30:00')
        assert isinstance(ts, int)
        assert ts > 0

    def test_integer_passthrough(self, client):
        """Test that integer timestamps pass through."""
        ts = client._to_timestamp_ms(1733558400000)
        assert ts == 1733558400000

    def test_invalid_date_raises_error(self, client):
        """Test that invalid date format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid date format"):
            client._to_timestamp_ms('not-a-date')


# =============================================================================
# ORDER PARSING TESTS
# =============================================================================

class TestOrderParsing:
    """Tests for parsing API orders."""

    def test_parse_order_basic(self, client, sample_api_order):
        """Test basic order parsing."""
        order = client.parse_order(sample_api_order)

        assert isinstance(order, Order)
        assert order.order_id == 'order-123'
        assert order.code == '123456789'
        assert order.state == 'NEW'
        assert order.total_price == 15000
        assert order.delivery_cost == 500

    def test_parse_order_dates(self, client, sample_api_order):
        """Test date parsing in orders."""
        order = client.parse_order(sample_api_order)

        assert order.created_at is not None
        assert isinstance(order.created_at, datetime)
        assert order.planned_delivery_date is not None

    def test_parse_order_customer(self, client, sample_api_order):
        """Test customer info parsing."""
        order = client.parse_order(sample_api_order)
        assert order.customer_phone == '+77001234567'

    def test_parse_order_waybill(self, client, sample_api_order):
        """Test waybill URL extraction."""
        order = client.parse_order(sample_api_order)
        assert order.waybill_url == 'https://kaspi.kz/waybill/123.pdf'

    def test_get_waybill_url(self, client, sample_api_order):
        """Test get_waybill_url helper."""
        url = client.get_waybill_url(sample_api_order)
        assert url == 'https://kaspi.kz/waybill/123.pdf'

    def test_get_waybill_url_missing(self, client):
        """Test get_waybill_url with missing waybill."""
        order = {'attributes': {}}
        url = client.get_waybill_url(order)
        assert url is None


# =============================================================================
# API RESPONSE TESTS
# =============================================================================

class TestAPIResponse:
    """Tests for APIResponse dataclass."""

    def test_api_response_success(self):
        """Test successful API response."""
        response = APIResponse(
            success=True,
            data={'orders': []},
            status_code=200,
        )
        assert response.success is True
        assert response.error is None

    def test_api_response_error(self):
        """Test error API response."""
        response = APIResponse(
            success=False,
            error='Rate limit exceeded',
            status_code=429,
        )
        assert response.success is False
        assert response.error == 'Rate limit exceeded'


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limit_interval(self, client):
        """Test that rate limiting delays requests."""
        # First request sets last_request_time
        client._last_request_time = time.time()

        # Second request should wait
        start = time.time()
        client._rate_limit()
        elapsed = time.time() - start

        # Should have waited approximately MIN_REQUEST_INTERVAL
        # (allowing some tolerance)
        assert elapsed >= 0.01  # At least some delay


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_get_client(self, mock_env):
        """Test get_client factory function."""
        client = get_client('UNIVERSAL')
        assert isinstance(client, KaspiAPIClient)
        assert client.store_code == 'UNIVERSAL'

    def test_store_token_map_has_all_stores(self):
        """Test that STORE_TOKEN_MAP has expected stores."""
        expected_stores = ['UNIVERSAL', 'ACMEWEAR', '11KZ', 'MELVIS', 'STOREB']
        for store in expected_stores:
            assert store in STORE_TOKEN_MAP


# =============================================================================
# MOCKED API CALL TESTS
# =============================================================================

class TestMockedAPICalls:
    """Tests with mocked HTTP responses."""

    @patch('requests.Session.request')
    def test_list_orders_success(self, mock_request, client):
        """Test successful list_orders call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'id': '1', 'attributes': {'code': '001', 'state': 'NEW'}},
                {'id': '2', 'attributes': {'code': '002', 'state': 'NEW'}},
            ]
        }
        mock_request.return_value = mock_response

        result = client.list_orders(state='NEW', page_size=10)

        assert result.success is True
        assert len(result.data['data']) == 2

    @patch('requests.Session.request')
    def test_list_orders_with_date_filter(self, mock_request, client):
        """Test list_orders with date filter."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}
        mock_request.return_value = mock_response

        result = client.list_orders(since='2025-12-01', until='2025-12-07')

        assert result.success is True
        # Verify params were passed
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get('params', {})
        assert 'filter[orders][creationDate][$ge]' in params
        assert 'filter[orders][creationDate][$le]' in params

    @patch('requests.Session.request')
    def test_get_order_success(self, mock_request, client, sample_api_order):
        """Test successful get_order call (uses filter approach)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        # get_order now uses filter approach, so response is a list
        mock_response.json.return_value = {'data': [sample_api_order]}
        mock_request.return_value = mock_response

        result = client.get_order('123456789')

        assert result.success is True
        # get_order returns single order, not wrapped in 'data'
        assert result.data['id'] == 'order-123'

    @patch('requests.Session.request')
    def test_401_raises_auth_error(self, mock_request, client):
        """Test that 401 response raises KaspiAuthError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_request.return_value = mock_response

        with pytest.raises(KaspiAuthError, match="Invalid or expired token"):
            client.list_orders()

    @patch('requests.Session.request')
    def test_404_raises_not_found_error(self, mock_request, client):
        """Test that 404 response raises KaspiNotFoundError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response

        with pytest.raises(KaspiNotFoundError, match="Resource not found"):
            client.get_order('nonexistent')

    @patch('requests.Session.request')
    def test_429_raises_rate_limit_error(self, mock_request, client):
        """Test that 429 response raises KaspiRateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_request.return_value = mock_response

        with pytest.raises(KaspiRateLimitError, match="Rate limit exceeded"):
            client.list_orders()

    @patch('requests.Session.request')
    def test_accept_order_success(self, mock_request, client_with_write):
        """Test successful accept_order call."""
        # First call: get_order lookup returns order with Base64 ID
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '123'}}]
        }

        # Second call: accept_order POST returns updated order
        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 200
        write_response.json.return_value = {
            'data': {'id': 'ABC123', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT'}}
        }

        mock_request.side_effect = [lookup_response, write_response]

        result = client_with_write.accept_order('123')

        assert result.success is True
        # Verify POST was called with correct Base64 ID
        assert mock_request.call_count == 2
        write_call = mock_request.call_args_list[1]
        assert write_call[1]['method'] == 'POST'
        assert write_call[1]['json']['data']['id'] == 'ABC123'

    @patch('requests.Session.request')
    def test_cancel_order_success(self, mock_request, client_with_write):
        """Test successful cancel_order call."""
        # First call: get_order lookup
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '123'}}]
        }

        # Second call: cancel_order POST
        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 200
        write_response.json.return_value = {
            'data': {'id': 'ABC123', 'attributes': {'status': 'CANCELLED'}}
        }

        mock_request.side_effect = [lookup_response, write_response]

        result = client_with_write.cancel_order('123', reason='OUT_OF_STOCK')

        assert result.success is True
        # Verify correct payload structure
        write_call = mock_request.call_args_list[1]
        json_data = write_call[1]['json']
        assert json_data['data']['id'] == 'ABC123'
        assert json_data['data']['attributes']['cancellationReason'] == 'OUT_OF_STOCK'


# =============================================================================
# STORE INFO TESTS
# =============================================================================

class TestStoreInfo:
    """Tests for store info methods."""

    def test_get_store_info(self, client):
        """Test get_store_info returns expected structure."""
        with patch.object(client, 'validate_token', return_value=True):
            info = client.get_store_info()

            assert info['store_code'] == 'UNIVERSAL'
            assert info['writes_enabled'] is False
            assert info['token_valid'] is True


# =============================================================================
# NEW TESTS FOR KASPI API CLIENT FIXES
# =============================================================================

class TestValidateTokenDateRange:
    """Tests for validate_token using valid date range."""

    @patch('requests.Session.request')
    def test_validate_token_uses_valid_date_range(self, mock_request, mock_env):
        """Ensure validate_token uses date within 14-day API limit."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.validate_token()

        assert result is True
        # Verify list_orders was called with a recent since date
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get('params', {})
        assert 'filter[orders][creationDate][$ge]' in params
        # The since date should be within 14 days (using DEFAULT_SYNC_DAYS=7)
        # We can't easily verify the exact date, but we know the call happened


class TestListOrdersStatusFilter:
    """Tests for list_orders with status parameter."""

    @patch('requests.Session.request')
    def test_list_orders_with_status_filter(self, mock_request, mock_env):
        """Test list_orders accepts status parameter."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        client.list_orders(state='KASPI_DELIVERY', status='ACCEPTED_BY_MERCHANT', since='2025-12-01')

        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get('params', {})
        assert params.get('filter[orders][status]') == 'ACCEPTED_BY_MERCHANT'
        assert params.get('filter[orders][state]') == 'KASPI_DELIVERY'


class TestGetOrderByCode:
    """Tests for get_order using filter approach."""

    @patch('requests.Session.request')
    def test_get_order_by_code_success(self, mock_request, mock_env):
        """Test get_order uses filter approach that works with order codes."""
        mock_data = {'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]}
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_order('12345')

        assert result.success
        assert result.data['attributes']['code'] == '12345'
        # Verify filter param was used
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get('params', {})
        assert params.get('filter[orders][code]') == '12345'

    @patch('requests.Session.request')
    def test_get_order_not_found(self, mock_request, mock_env):
        """Test get_order returns error when order not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}  # Empty list
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_order('nonexistent')

        assert result.success is False
        assert result.status_code == 404
        assert 'not found' in result.error.lower()


class TestPendingAssemblyOrders:
    """Tests for get_pending_assembly_orders helper method."""

    @patch('requests.Session.request')
    def test_get_pending_assembly_orders(self, mock_request, mock_env):
        """Test helper method filters to unassembled orders."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'assembled': False}},
                {'id': '2', 'attributes': {'assembled': True}},
                {'id': '3', 'attributes': {'assembled': False}},
            ]
        }
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_orders
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_pending_assembly_orders(since='2025-12-01')

        assert result.success
        assert len(result.data['data']) == 2  # Only unassembled orders
        assert result.data['meta']['totalCount'] == 2

    @patch('requests.Session.request')
    def test_get_awaiting_courier_orders(self, mock_request, mock_env):
        """Test helper method filters to assembled orders."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'assembled': False}},
                {'id': '2', 'attributes': {'assembled': True}},
                {'id': '3', 'attributes': {'assembled': True}},
            ]
        }
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = mock_orders
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_awaiting_courier_orders(since='2025-12-01')

        assert result.success
        assert len(result.data['data']) == 2  # Only assembled orders
        assert result.data['meta']['totalCount'] == 2


class TestAPIConstants:
    """Tests for API configuration constants."""

    def test_max_date_range_days(self):
        """Test MAX_DATE_RANGE_DAYS constant is set correctly."""
        assert MAX_DATE_RANGE_DAYS == 14

    def test_default_sync_days(self):
        """Test DEFAULT_SYNC_DAYS constant is set correctly."""
        assert DEFAULT_SYNC_DAYS == 7

    def test_max_page_size(self):
        """Test MAX_PAGE_SIZE constant is set correctly."""
        assert MAX_PAGE_SIZE == 100


# =============================================================================
# PAGINATION AND HELPER METHOD TESTS
# =============================================================================

class TestPaginationHelper:
    """Tests for _fetch_orders_with_pagination helper."""

    @patch('requests.Session.request')
    def test_fetch_orders_handles_pagination(self, mock_request, mock_env):
        """Verify all pages are fetched."""
        page1 = {
            'data': [{'id': '1', 'attributes': {'code': '001'}}],
            'meta': {'pageCount': 2, 'totalCount': 2}
        }
        page2 = {
            'data': [{'id': '2', 'attributes': {'code': '002'}}],
            'meta': {'pageCount': 2, 'totalCount': 2}
        }

        call_count = [0]
        def mock_response_factory(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_resp.status_code = 200
            call_count[0] += 1
            if call_count[0] == 1:
                mock_resp.json.return_value = page1
            else:
                mock_resp.json.return_value = page2
            return mock_resp

        mock_request.side_effect = mock_response_factory

        client = KaspiAPIClient('UNIVERSAL')
        result = client._fetch_orders_with_pagination('KASPI_DELIVERY', '2025-12-01')

        assert result.success
        assert len(result.data['data']) == 2
        assert call_count[0] == 2  # Both pages fetched

    @patch('requests.Session.request')
    def test_fetch_orders_respects_max_pages(self, mock_request, mock_env):
        """Verify max_pages limit is respected."""
        # Always return more pages exist
        page_data = {
            'data': [{'id': '1', 'attributes': {'code': '001'}}],
            'meta': {'pageCount': 100, 'totalCount': 10000}
        }

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = page_data
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        result = client._fetch_orders_with_pagination('KASPI_DELIVERY', '2025-12-01', max_pages=3)

        assert result.success
        assert mock_request.call_count == 3  # Stopped at max_pages

    @patch('requests.Session.request')
    def test_fetch_orders_propagates_errors(self, mock_request, mock_env):
        """Verify API errors are propagated."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')

        with pytest.raises(KaspiAuthError):
            client._fetch_orders_with_pagination('KASPI_DELIVERY', '2025-12-01')


class TestHelperMethodFiltering:
    """Tests for correct filtering in helper methods."""

    @patch('requests.Session.request')
    def test_pending_assembly_filters_status_and_assembled(self, mock_request, mock_env):
        """Verify get_pending_assembly_orders filters correctly."""
        # Note: API filters by status=ACCEPTED_BY_MERCHANT, so mock only includes those
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
                {'id': '3', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
            ],
            'meta': {'pageCount': 1, 'totalCount': 3}
        }

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_orders
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_pending_assembly_orders(since='2025-12-01')

        assert result.success
        orders = result.data.get('data', [])
        # Should only return orders 1 and 3 (assembled=False)
        assert len(orders) == 2  # Orders 1 and 3
        for o in orders:
            assert o['attributes']['assembled'] is False

    @patch('requests.Session.request')
    def test_awaiting_courier_filters_assembled_true(self, mock_request, mock_env):
        """Verify get_awaiting_courier_orders filters assembled=true."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': False}},
                {'id': '3', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT', 'assembled': True}},
            ],
            'meta': {'pageCount': 1, 'totalCount': 3}
        }

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_orders
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_awaiting_courier_orders(since='2025-12-01')

        assert result.success
        orders = result.data.get('data', [])
        assert len(orders) == 2  # Orders 1 and 3
        for o in orders:
            assert o['attributes']['assembled'] is True

    @patch('requests.Session.request')
    def test_new_orders_filters_approved_by_bank(self, mock_request, mock_env):
        """Verify get_new_orders filters status=APPROVED_BY_BANK."""
        mock_orders = {
            'data': [
                {'id': '1', 'attributes': {'status': 'APPROVED_BY_BANK'}},
                {'id': '2', 'attributes': {'status': 'ACCEPTED_BY_MERCHANT'}},
                {'id': '3', 'attributes': {'status': 'APPROVED_BY_BANK'}},
            ],
            'meta': {'pageCount': 1, 'totalCount': 3}
        }

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_orders
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_new_orders(since='2025-12-01')

        assert result.success
        orders = result.data.get('data', [])
        assert len(orders) == 2  # Orders 1 and 3
        for o in orders:
            assert o['attributes']['status'] == 'APPROVED_BY_BANK'

    @patch('requests.Session.request')
    def test_helper_methods_use_default_7_day_since(self, mock_request, mock_env):
        """Verify helpers use 7-day default when since not provided."""
        mock_orders = {
            'data': [],
            'meta': {'pageCount': 1, 'totalCount': 0}
        }

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_orders
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        client.get_pending_assembly_orders()  # No since param

        # Verify date filter was applied
        call_kwargs = mock_request.call_args[1]
        params = call_kwargs.get('params', {})
        timestamp = params.get('filter[orders][creationDate][$ge]')
        assert timestamp is not None

        # Verify timestamp is ~7 days ago
        from datetime import datetime
        since_dt = datetime.fromtimestamp(timestamp / 1000)
        days_ago = (datetime.now() - since_dt).days
        assert 6 <= days_ago <= 8

    @patch('requests.Session.request')
    def test_helper_returns_error_on_api_failure(self, mock_request, mock_env):
        """Verify error propagation from helpers."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.json.return_value = {'errors': [{'detail': 'Server error'}]}
        mock_request.return_value = mock_resp

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_pending_assembly_orders(since='2025-12-01')

        assert not result.success
        assert result.status_code == 500


# =============================================================================
# WRITE OPERATIONS BASE64 ID TESTS (Phase 9.5 Fix)
# =============================================================================

class TestWriteOperationsBase64ID:
    """Tests for write operations using Base64 ID lookup."""

    @patch('requests.Session.request')
    def test_get_order_base64_id_success(self, mock_request, mock_env):
        """Test _get_order_base64_id helper extracts Base64 ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [{'id': 'NzM4Nzg0MjM2', 'attributes': {'code': '738784236'}}]
        }
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        base64_id = client._get_order_base64_id('738784236')

        assert base64_id == 'NzM4Nzg0MjM2'

    @patch('requests.Session.request')
    def test_get_order_base64_id_not_found(self, mock_request, mock_env):
        """Test _get_order_base64_id raises error when order not found."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}  # Empty list
        mock_request.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')

        with pytest.raises(KaspiNotFoundError, match="not found"):
            client._get_order_base64_id('nonexistent')

    @patch('requests.Session.request')
    def test_get_order_entries_uses_base64_id(self, mock_request, mock_env):
        """Test get_order_entries uses Base64 ID in URL path."""
        # First call: get_order lookup
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]
        }

        # Second call: entries request
        entries_response = MagicMock()
        entries_response.ok = True
        entries_response.status_code = 200
        entries_response.json.return_value = {
            'data': [{'id': 'entry1', 'attributes': {'quantity': 2}}]
        }

        mock_request.side_effect = [lookup_response, entries_response]

        client = KaspiAPIClient('UNIVERSAL')
        result = client.get_order_entries('12345')

        assert result.success
        # Verify URL contains Base64 ID, not order code
        entries_call = mock_request.call_args_list[1]
        url = entries_call[1]['url']
        assert 'ABC123/entries' in url
        assert '12345' not in url

    @patch('requests.Session.request')
    def test_assemble_order_uses_base64_id(self, mock_request, mock_env_with_write):
        """Test assemble_order posts update to /orders with Base64 ID payload."""
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'NzM4Nzg0MjM2', 'attributes': {'code': '738784236'}}]
        }

        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 200
        write_response.json.return_value = {'data': {'id': 'NzM4Nzg0MjM2'}}

        mock_request.side_effect = [lookup_response, write_response]

        client = KaspiAPIClient('UNIVERSAL')
        client.assemble_order('738784236')

        # Verify write goes through /orders endpoint
        write_call = mock_request.call_args_list[1]
        url = write_call[1]['url']
        assert url.endswith('/orders')

    @patch('requests.Session.request')
    def test_assemble_order_uses_correct_format(self, mock_request, mock_env_with_write):
        """Test assemble_order uses status+numberOfSpace payload for /orders update."""
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]
        }

        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 201
        write_response.json.return_value = {'data': {'id': 'ABC123'}}

        mock_request.side_effect = [lookup_response, write_response]

        client = KaspiAPIClient('UNIVERSAL')
        client.assemble_order('12345', parcel_count=2)

        # Verify correct payload format for /orders update
        write_call = mock_request.call_args_list[1]
        json_data = write_call[1]['json']
        assert json_data['data']['id'] == 'ABC123'
        assert json_data['data']['attributes']['status'] == 'ASSEMBLE'
        assert json_data['data']['attributes']['numberOfSpace'] == '2'  # API requires STRING


class TestWaybillDownload:
    """Tests for waybill download call contract."""

    @patch('requests.Session.get')
    def test_download_waybill_accepts_timeout_override(self, mock_get, mock_env):
        """download_waybill should accept per-call timeout override used by downloader script."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.content = b'%PDF-test'
        mock_get.return_value = mock_response

        client = KaspiAPIClient('UNIVERSAL')
        result = client.download_waybill('https://kaspi.kz/waybill/test.pdf', timeout=12)

        assert result.success
        mock_get.assert_called_once()
        assert mock_get.call_args[1]['timeout'] == 12
        sent_headers = mock_get.call_args[1]['headers']
        assert sent_headers['User-Agent'].startswith('Mozilla/')
        assert sent_headers['X-Auth-Token'] == 'test-token-universal'

    @patch('requests.Session.request')
    def test_ship_order_uses_base64_id(self, mock_request, mock_env_with_write):
        """Test ship_order uses Base64 ID."""
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]
        }

        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 200
        write_response.json.return_value = {'data': {}}

        mock_request.side_effect = [lookup_response, write_response]

        client = KaspiAPIClient('UNIVERSAL')
        result = client.ship_order('12345')

        assert result.success
        write_call = mock_request.call_args_list[1]
        json_data = write_call[1]['json']
        assert json_data['data']['id'] == 'ABC123'

    @patch('requests.Session.request')
    def test_complete_order_uses_base64_id(self, mock_request, mock_env_with_write):
        """Test complete_order uses Base64 ID."""
        lookup_response = MagicMock()
        lookup_response.ok = True
        lookup_response.status_code = 200
        lookup_response.json.return_value = {
            'data': [{'id': 'ABC123', 'attributes': {'code': '12345'}}]
        }

        write_response = MagicMock()
        write_response.ok = True
        write_response.status_code = 200
        write_response.json.return_value = {'data': {}}

        mock_request.side_effect = [lookup_response, write_response]

        client = KaspiAPIClient('UNIVERSAL')
        result = client.complete_order('12345', security_code='1234')

        assert result.success
        write_call = mock_request.call_args_list[1]
        json_data = write_call[1]['json']
        assert json_data['data']['id'] == 'ABC123'
        assert json_data['data']['attributes']['signature'] == '1234'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
