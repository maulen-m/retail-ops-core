from __future__ import annotations

import sys
from typing import Any

import scripts.sync_kaspi_orders as mod


class _FakeResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.success = True
        self.orders_fetched = 0
        self.orders_inserted = 0
        self.orders_updated = 0
        self.status_changes: list[Any] = []
        self.duration_sec = 0.1


class _FakeMultiResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.store_results = {}
        self.total_orders_fetched = 0
        self.total_orders_inserted = 0
        self.total_orders_updated = 0
        self.duration_sec = 0.1


class _FakeEngine:
    def sync_all_stores(self, **_kwargs: Any) -> _FakeMultiResult:
        return _FakeMultiResult()

    def sync_store(self, **_kwargs: Any) -> _FakeResult:
        return _FakeResult()


def test_main_calls_enrichment_for_all_mode(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(mod, "OrderSyncEngine", lambda: _FakeEngine())
    monkeypatch.setattr(mod, "setup_logging", lambda verbose=False: None)
    monkeypatch.setattr(mod, "print_multi_result", lambda _result: None)
    monkeypatch.setattr(mod, "print_sync_result", lambda _result: None)

    def _fake_enrich(stores, since, until, dry_run):
        calls.append(
            {
                "stores": stores,
                "since": since,
                "until": until,
                "dry_run": dry_run,
            }
        )

    monkeypatch.setattr(mod, "_run_enrichment", _fake_enrich)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sync_kaspi_orders.py", "--all", "--since", "2026-03-01", "--until", "2026-03-04", "--enrich"],
    )

    rc = mod.main()
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["stores"] == ["UNIVERSAL", "ACMEWEAR", "11KZ", "MELVIS", "STOREB"]
    assert calls[0]["since"] == "2026-03-01"
    assert calls[0]["until"] == "2026-03-04"
    assert calls[0]["dry_run"] is False


def test_main_calls_enrichment_for_single_store_mode(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(mod, "OrderSyncEngine", lambda: _FakeEngine())
    monkeypatch.setattr(mod, "setup_logging", lambda verbose=False: None)
    monkeypatch.setattr(mod, "print_multi_result", lambda _result: None)
    monkeypatch.setattr(mod, "print_sync_result", lambda _result: None)

    def _fake_enrich(stores, since, until, dry_run):
        calls.append(
            {
                "stores": stores,
                "since": since,
                "until": until,
                "dry_run": dry_run,
            }
        )

    monkeypatch.setattr(mod, "_run_enrichment", _fake_enrich)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sync_kaspi_orders.py", "--store", "UNIVERSAL", "--since", "2026-03-01", "--enrich"],
    )

    rc = mod.main()
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["stores"] == ["UNIVERSAL"]
    assert calls[0]["since"] == "2026-03-01"
    assert calls[0]["dry_run"] is False
