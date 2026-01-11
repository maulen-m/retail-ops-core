"""Binance wallet API client (withdraw, deposit, transfer, snapshots)."""

from __future__ import annotations

import hmac
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode, quote

import requests

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
ENDPOINT_WITHDRAW_HISTORY = "/sapi/v1/capital/withdraw/history"
ENDPOINT_DEPOSIT_HISTORY = "/sapi/v1/capital/deposit/hisrec"
ENDPOINT_UNIVERSAL_TRANSFER = "/sapi/v1/asset/transfer"
ENDPOINT_ACCOUNT_SNAPSHOT = "/sapi/v1/accountSnapshot"
ENDPOINT_FUNDING_ASSET = "/sapi/v1/asset/get-funding-asset"

DEFAULT_TIMEOUT = 20
RECV_WINDOW = 5000
MAX_LIMIT = 1000


class BinanceWalletError(Exception):
    pass


@dataclass
class WithdrawResponse:
    success: bool
    data: list[dict]
    raw: Optional[dict] = None


class BinanceWalletClient:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("BINANCE_TOKEN")
        self.api_secret = api_secret or os.getenv("BINANCE_SECRET_KEY")
        if not self.api_key or not self.api_secret:
            raise BinanceWalletError("Missing BINANCE_TOKEN or BINANCE_SECRET_KEY in environment")
        self.session = requests.Session()

    def _sign_params(self, params: dict) -> str:
        query = urlencode(params, doseq=True, quote_via=quote, safe="")
        sig = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return query + "&signature=" + sig

    def _request_signed(self, endpoint: str, params: dict, method: str = "GET") -> Any:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        signed = self._sign_params(params)
        url = f"{BASE_URL}{endpoint}?{signed}"
        headers = {"X-MBX-APIKEY": self.api_key}
        method = method.upper()
        if method == "POST":
            resp = self.session.post(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        else:
            resp = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            raise BinanceWalletError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def _request(self, params: dict) -> dict:
        return self._request_signed(ENDPOINT_WITHDRAW_HISTORY, params, method="GET")

    def _request_funding(self, params: dict) -> list[dict]:
        payload = self._request_signed(ENDPOINT_FUNDING_ASSET, params, method="POST")
        if isinstance(payload, list):
            return payload
        return payload.get("data") or []

    def list_withdrawals(
        self,
        coin: Optional[str] = None,
        status: Optional[int] = None,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        offset: int = 0,
        limit: int = MAX_LIMIT,
    ) -> WithdrawResponse:
        params: dict[str, Any] = {
            "offset": max(0, offset),
            "limit": min(limit, MAX_LIMIT),
        }
        if coin:
            params["coin"] = coin
        if status is not None:
            params["status"] = int(status)
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)

        payload = self._request(params)
        if isinstance(payload, list):
            data = payload
        else:
            data = payload.get("withdrawList") or payload.get("data") or []
        return WithdrawResponse(success=True, data=data, raw=payload)

    def iter_withdrawals(
        self,
        coin: Optional[str] = None,
        status: Optional[int] = None,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = MAX_LIMIT,
        sleep_s: float = 0.2,
    ) -> list[dict]:
        offset = 0
        all_rows: list[dict] = []
        while True:
            resp = self.list_withdrawals(
                coin=coin,
                status=status,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                offset=offset,
                limit=limit,
            )
            if not resp.data:
                break
            all_rows.extend(resp.data)
            if len(resp.data) < limit:
                break
            offset += limit
            time.sleep(sleep_s)
        return all_rows

    def list_deposits(
        self,
        coin: Optional[str] = None,
        status: Optional[int] = None,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        offset: int = 0,
        limit: int = MAX_LIMIT,
        include_source: bool = False,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "offset": max(0, offset),
            "limit": min(limit, MAX_LIMIT),
        }
        if coin:
            params["coin"] = coin
        if status is not None:
            params["status"] = int(status)
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        if include_source:
            params["includeSource"] = "true"

        payload = self._request_signed(ENDPOINT_DEPOSIT_HISTORY, params, method="GET")
        if isinstance(payload, list):
            return payload
        return payload.get("data") or payload.get("depositList") or []

    def iter_deposits(
        self,
        coin: Optional[str] = None,
        status: Optional[int] = None,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = MAX_LIMIT,
        sleep_s: float = 0.2,
    ) -> list[dict]:
        offset = 0
        all_rows: list[dict] = []
        while True:
            rows = self.list_deposits(
                coin=coin,
                status=status,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                offset=offset,
                limit=limit,
            )
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            offset += limit
            time.sleep(sleep_s)
        return all_rows

    def list_universal_transfers(
        self,
        transfer_type: str,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        current: int = 1,
        size: int = 100,
    ) -> dict:
        params: dict[str, Any] = {
            "type": transfer_type,
            "current": max(1, current),
            "size": min(max(1, size), 100),
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        return self._request_signed(ENDPOINT_UNIVERSAL_TRANSFER, params, method="GET")

    def iter_universal_transfers(
        self,
        transfer_type: str,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        size: int = 100,
        sleep_s: float = 0.2,
    ) -> list[dict]:
        current = 1
        all_rows: list[dict] = []
        while True:
            payload = self.list_universal_transfers(
                transfer_type=transfer_type,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                current=current,
                size=size,
            )
            rows = payload.get("rows") or []
            if not rows:
                break
            all_rows.extend(rows)
            total = payload.get("total")
            if total is None:
                if len(rows) < size:
                    break
            else:
                if len(all_rows) >= int(total):
                    break
            current += 1
            time.sleep(sleep_s)
        return all_rows

    def list_account_snapshots(
        self,
        account_type: str = "SPOT",
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = 30,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "type": account_type,
            "limit": min(max(7, limit), 30),
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        payload = self._request_signed(ENDPOINT_ACCOUNT_SNAPSHOT, params, method="GET")
        return payload.get("snapshotVos") or []

    def get_funding_assets(
        self,
        asset: str | None = None,
        need_btc_valuation: bool | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if asset:
            params["asset"] = asset
        if need_btc_valuation is not None:
            params["needBtcValuation"] = "true" if need_btc_valuation else "false"
        return self._request_funding(params)

    def get_funding_balance(self, asset: str = "USDT") -> Optional[float]:
        rows = self.get_funding_assets(asset=asset)
        for row in rows:
            if str(row.get("asset", "")).upper() == asset.upper():
                try:
                    return float(row.get("free", 0))
                except (TypeError, ValueError):
                    return None
        return None
