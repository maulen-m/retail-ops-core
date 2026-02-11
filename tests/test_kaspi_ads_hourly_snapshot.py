from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.kaspi_ads_hourly_snapshot import (
    acquire_file_lock,
    ensure_schema,
    persist_hourly_snapshot,
    release_file_lock,
    request_json_with_backoff,
)


def _snapshot_row(*, clicks: int, views: int = 0, cost: float = 0.0, gmv: float = 0.0, orders: int = 0) -> dict[str, object]:
    return {
        "date": "2026-02-10",
        "merchant_id": "759051",
        "campaign_id": "2380614",
        "campaign_name": "Acmewear_16k",
        "sku_key": "19796919b",
        "bid_cpc": 70.0,
        "views_cumul": views,
        "clicks_cumul": clicks,
        "cost_cumul": cost,
        "gmv_cumul": gmv,
        "orders_cumul": orders,
        "favorites_cumul": 0,
        "carts_cumul": 0,
        "cost_today": cost,
    }


def test_persist_hourly_snapshot_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)

        snapshot_at = datetime(2026, 2, 10, 10, 5, 0)
        rows = [_snapshot_row(clicks=10, views=100, cost=500.0, gmv=1500.0, orders=2)]

        persist_hourly_snapshot(conn, snapshot_at=snapshot_at, rows=rows)
        persist_hourly_snapshot(conn, snapshot_at=snapshot_at, rows=rows)

        snapshot_count = conn.execute("SELECT COUNT(*) FROM hourly_snapshot").fetchone()[0]
        delta_count = conn.execute("SELECT COUNT(*) FROM hourly_delta").fetchone()[0]
        assert snapshot_count == 1
        assert delta_count == 1


def test_persist_hourly_snapshot_marks_reset_and_no_negative_delta(tmp_path: Path) -> None:
    db_path = tmp_path / "ads.db"
    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)

        persist_hourly_snapshot(
            conn,
            snapshot_at=datetime(2026, 2, 10, 10, 5, 0),
            rows=[_snapshot_row(clicks=12, views=120, cost=700.0, gmv=2200.0, orders=3)],
        )
        persist_hourly_snapshot(
            conn,
            snapshot_at=datetime(2026, 2, 10, 11, 5, 0),
            rows=[_snapshot_row(clicks=9, views=90, cost=600.0, gmv=1800.0, orders=2)],
        )

        row = conn.execute(
            """
            SELECT clicks_delta, views_delta, cost_delta, gmv_delta, orders_delta, delta_method, is_reset_anomaly
            FROM hourly_delta
            WHERE date='2026-02-10' AND hour_start=10 AND hour_end=11
            """
        ).fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] == 0
        assert row[2] == 0
        assert row[3] == 0
        assert row[4] == 0
        assert row[5] == "reset_anomaly"
        assert row[6] == 1


def test_lock_behavior_skips_when_already_locked(tmp_path: Path) -> None:
    lock_path = tmp_path / ".kaspi_ads.lock"
    first = acquire_file_lock(lock_path, timeout_seconds=0.1, poll_seconds=0.01)
    assert first is not None
    try:
        second = acquire_file_lock(lock_path, timeout_seconds=0.01, poll_seconds=0.0, sleep_fn=lambda _: None)
        assert second is None
    finally:
        release_file_lock(first, lock_path)


class _FakeResponse:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeRequest:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, _url: str, headers=None):  # noqa: ANN001
        self.calls += 1
        if self.calls == 1:
            return _FakeResponse(429, {"error": "rate-limit"})
        return _FakeResponse(200, {"data": [1, 2, 3]})


def test_request_json_with_backoff_retries_on_429() -> None:
    req = _FakeRequest()
    sleeps: list[float] = []

    data = request_json_with_backoff(
        req,
        "https://example.test",
        max_attempts=3,
        base_sleep_seconds=0.25,
        sleep_fn=lambda s: sleeps.append(s),
    )

    assert data == {"data": [1, 2, 3]}
    assert req.calls == 2
    assert sleeps == [0.25]
