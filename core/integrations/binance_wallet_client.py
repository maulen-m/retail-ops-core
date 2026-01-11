"""Binance wallet API client (withdraw history)."""

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

    def _request(self, params: dict) -> dict:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        signed = self._sign_params(params)
        url = f"{BASE_URL}{ENDPOINT_WITHDRAW_HISTORY}?{signed}"
        headers = {"X-MBX-APIKEY": self.api_key}
        resp = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            raise BinanceWalletError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def _request_funding(self, params: dict) -> list[dict]:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        signed = self._sign_params(params)
        url = f"{BASE_URL}{ENDPOINT_FUNDING_ASSET}?{signed}"
        headers = {"X-MBX-APIKEY": self.api_key}
        resp = self.session.post(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            raise BinanceWalletError(f"HTTP {resp.status_code}: {resp.text}")
        payload = resp.json()
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

    def get_funding_assets(self, asset: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if asset:
            params["asset"] = asset
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
