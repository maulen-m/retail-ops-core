"""Binance C2C/P2P API client (read-only)."""

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
ENDPOINT_C2C_HISTORY = "/sapi/v1/c2c/orderMatch/listUserOrderHistory"

DEFAULT_TIMEOUT = 20
MAX_ROWS = 100
RECV_WINDOW = 5000


class BinanceC2CError(Exception):
    pass


@dataclass
class C2CResponse:
    success: bool
    data: list[dict]
    total: int = 0
    raw: Optional[dict] = None


class BinanceC2CClient:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("BINANCE_TOKEN")
        self.api_secret = api_secret or os.getenv("BINANCE_SECRET_KEY")
        if not self.api_key or not self.api_secret:
            raise BinanceC2CError("Missing BINANCE_TOKEN or BINANCE_SECRET_KEY in environment")
        self.session = requests.Session()

    def _sign_params(self, params: dict) -> str:
        # Binance requires percent-encoding before signing
        query = urlencode(params, doseq=True, quote_via=quote, safe="")
        sig = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return query + "&signature=" + sig

    def _request(self, params: dict) -> dict:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = RECV_WINDOW
        signed = self._sign_params(params)
        url = f"{BASE_URL}{ENDPOINT_C2C_HISTORY}?{signed}"
        headers = {"X-MBX-APIKEY": self.api_key}
        resp = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            raise BinanceC2CError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        return data

    def list_user_orders(
        self,
        trade_type: str,
        begin_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        page: int = 1,
        rows: int = MAX_ROWS,
    ) -> C2CResponse:
        params: dict[str, Any] = {
            "tradeType": trade_type,
            "page": page,
            "rows": min(rows, MAX_ROWS),
        }
        if begin_time_ms is not None:
            params["beginTime"] = int(begin_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        payload = self._request(params)

        # Typical response includes success/code/message/data/total
        success = bool(payload.get("success", False)) or payload.get("code") == "000000"
        if not success:
            raise BinanceC2CError(str(payload))
        data = payload.get("data") or []
        total = int(payload.get("total", len(data)))
        return C2CResponse(success=True, data=data, total=total, raw=payload)

    def iter_user_orders(
        self,
        trade_type: str,
        begin_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        rows: int = MAX_ROWS,
        sleep_s: float = 0.2,
    ) -> list[dict]:
        page = 1
        out: list[dict] = []
        while True:
            resp = self.list_user_orders(
                trade_type=trade_type,
                begin_time_ms=begin_time_ms,
                end_time_ms=end_time_ms,
                page=page,
                rows=rows,
            )
            if not resp.data:
                break
            out.extend(resp.data)
            if len(out) >= resp.total:
                break
            page += 1
            time.sleep(sleep_s)
        return out
