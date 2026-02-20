"""Tests for kaspi_marketing_scrape helpers."""

import json
from pathlib import Path

import pytest

from scripts.kaspi_marketing_scrape import (
    parse_campaigns_report_csv,
    merge_campaign_report,
    merge_product_rows,
    log_day_progress,
    download_with_details,
    build_kaspi_headers,
    build_days_list,
    compute_day_sleep,
    maybe_pause_after_login,
    wait_for_login,
    login_required,
    should_skip_inactive,
)


def test_parse_campaigns_report_csv_maps_and_extras(tmp_path: Path) -> None:
    csv_path = tmp_path / "report.csv"
    csv_path.write_text(
        "Наименование;Текущий статус;Просмотры;Клики;CTR;Ср. стоим. клика;Расходы на рекламу;Сумма заказов;Все заказы;В избранное;В корзину;Доля рекламных расходов;Неизвестно\n"
        "Acmewear_16k;Активная;100;10;0,5;12,3;45,6;78,9;2;3;4;25,0;extra\n",
        encoding="utf-8",
    )

    rows = parse_campaigns_report_csv(csv_path)
    assert len(rows) == 1
    row = rows[0]

    assert row["campaign_name"] == "Acmewear_16k"
    assert row["report_state"] == "Активная"
    assert row["report_views"] == 100
    assert row["report_clicks"] == 10
    assert row["report_ctr"] == pytest.approx(0.5)
    assert row["report_avg_cpc"] == pytest.approx(12.3)
    assert row["report_cost"] == pytest.approx(45.6)
    assert row["report_gmv"] == pytest.approx(78.9)
    assert row["report_transactions"] == 2
    assert row["report_favorites"] == 3
    assert row["report_carts"] == 4
    assert row["report_crr"] == pytest.approx(25.0)

    extra = json.loads(row["report_extra"])
    assert extra == {"Неизвестно": "extra"}


def test_merge_campaign_report_prefers_highest_cost() -> None:
    campaign_rows = [
        {
            "campaign_name": "Acmewear_16k",
            "campaign_id": "1",
        }
    ]
    report_rows = [
        {"campaign_name": "Acmewear_16k", "report_cost": 10},
        {"campaign_name": "Acmewear_16k", "report_cost": 50, "report_ctr": 0.1},
    ]
    run_log: dict[str, object] = {}

    merge_campaign_report(campaign_rows, report_rows, run_log, "2025-01-01")

    row = campaign_rows[0]
    assert row["report_cost"] == 50
    assert row["report_ctr"] == 0.1
    assert "report_duplicates" in run_log


def test_download_with_details_failure(tmp_path: Path) -> None:
    class FakeResponse:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body
            self.headers = {"content-type": "text/plain"}

        def body(self) -> bytes:
            return self._body

    class FakeRequest:
        def __init__(self, response: FakeResponse) -> None:
            self._response = response

        def get(self, url: str):
            return self._response

    class FakeContext:
        def __init__(self, response: FakeResponse) -> None:
            self.request = FakeRequest(response)

    dest = tmp_path / "out.csv"
    response = FakeResponse(403, b"forbidden")
    details = download_with_details(FakeContext(response), "https://example.com", dest)

    assert details["ok"] is False
    assert details["status"] == 403
    assert "forbidden" in details["body"]
    assert not dest.exists()


def test_log_day_progress_emits_info(caplog) -> None:
    from datetime import date
    import logging

    logger = logging.getLogger("kaspi_marketing_test")
    with caplog.at_level(logging.INFO):
        log_day_progress(logger, date(2025, 1, 1), 1, 3, 2, 10, 1)

    assert any("2025-01-01" in rec.message for rec in caplog.records)
    assert any("campaigns=2" in rec.message for rec in caplog.records)
    assert any("products=10" in rec.message for rec in caplog.records)

def test_download_with_details_retries_until_success(tmp_path: Path) -> None:
    calls = {"sleep": []}

    class FakeResponse:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body
            self.headers = {"content-type": "text/plain"}

        def body(self) -> bytes:
            return self._body

    class FakeRequest:
        def __init__(self, responses):
            self._responses = responses
            self._idx = 0

        def get(self, url: str, headers=None):
            resp = self._responses[self._idx]
            self._idx = min(self._idx + 1, len(self._responses) - 1)
            return resp

    class FakeContext:
        def __init__(self, responses) -> None:
            self.request = FakeRequest(responses)

    def fake_sleep(seconds: float) -> None:
        calls["sleep"].append(seconds)

    dest = tmp_path / "report.csv"
    responses = [
        FakeResponse(429, b"rate"),
        FakeResponse(200, b"ok"),
    ]

    details = download_with_details(
        FakeContext(responses),
        "https://example.com",
        dest,
        max_attempts=3,
        retry_statuses=(429,),
        sleep_fn=fake_sleep,
        sleep_seconds=0.1,
    )

    assert details["ok"] is True
    assert details["attempts"] == 2
    assert dest.read_bytes() == b"ok"
    assert calls["sleep"] == [0.1]


def test_build_kaspi_headers_includes_xsrf() -> None:
    cookies = [
        {"name": "XSRF-TOKEN", "value": "abc"},
        {"name": "other", "value": "x"},
    ]
    headers = build_kaspi_headers(cookies, "https://marketing.kaspi.kz/advertising/campaigns")
    assert headers["x-xsrf-token"] == "abc"
    assert headers["x-requested-with"] == "XMLHttpRequest"
    assert headers["referer"].startswith("https://marketing.kaspi.kz/")


def test_build_days_list_applies_max_days() -> None:
    from datetime import date

    days = build_days_list(
        target=date(2025, 1, 10),
        days_back=5,
        start_date=None,
        end_date=None,
        max_days=2,
    )
    assert len(days) == 2
    assert days == [date(2025, 1, 6), date(2025, 1, 7)]


def test_compute_day_sleep_with_backoff() -> None:
    import random

    rng = random.Random(0)
    sleep_val = compute_day_sleep(2, base_seconds=2.5, jitter_seconds=1.0, max_seconds=20.0, rng=rng)
    assert sleep_val > 0
    assert sleep_val <= 20.0


def test_maybe_pause_after_login_calls_sleep() -> None:
    calls = {"count": 0, "seconds": []}

    def fake_sleep(seconds: float) -> None:
        calls["count"] += 1
        calls["seconds"].append(seconds)

    assert maybe_pause_after_login(2.5, sleep_fn=fake_sleep) is True
    assert calls["count"] == 1
    assert calls["seconds"] == [2.5]

    assert maybe_pause_after_login(0, sleep_fn=fake_sleep) is False


def test_wait_for_login_times_out() -> None:
    calls = {"count": 0}

    def login_check() -> bool:
        calls["count"] += 1
        return True

    assert wait_for_login(login_check, timeout_seconds=0.01, poll_seconds=0.0, sleep_fn=lambda _: None) is False
    assert calls["count"] >= 1


def test_wait_for_login_succeeds() -> None:
    calls = {"count": 0}

    def login_check() -> bool:
        calls["count"] += 1
        return calls["count"] < 3

    assert wait_for_login(login_check, timeout_seconds=1.0, poll_seconds=0.0, sleep_fn=lambda _: None) is True


def test_login_required_checks_url_and_password_input() -> None:
    class FakeLocator:
        def __init__(self, count: int) -> None:
            self._count = count

        def count(self) -> int:
            return self._count

    class FakePage:
        def __init__(self, url: str, pwd_count: int, cta_count: int = 0, login_link_count: int = 0) -> None:
            self.url = url
            self._pwd_count = pwd_count
            self._cta_count = cta_count
            self._login_link_count = login_link_count

        def locator(self, selector: str) -> FakeLocator:
            if selector == "input[type='password']":
                return FakeLocator(self._pwd_count)
            if selector == "text=Начать рекламировать товары":
                return FakeLocator(self._cta_count)
            if selector in ("a:has-text('Вход')", "button:has-text('Вход')"):
                return FakeLocator(self._login_link_count)
            return FakeLocator(0)

    assert login_required(FakePage("https://marketing.kaspi.kz/sign-in", 0)) is True
    assert login_required(FakePage("https://marketing.kaspi.kz/advertising/", 1)) is True
    assert login_required(FakePage("https://marketing.kaspi.kz/advertising/", 0)) is False
    assert login_required(FakePage("https://marketing.kaspi.kz/advertising/", 0, cta_count=1)) is True
    assert login_required(FakePage("https://marketing.kaspi.kz/advertising/", 0, login_link_count=1)) is True


def test_should_skip_inactive_only_after_consecutive_inactive() -> None:
    assert should_skip_inactive("", "Paused") is False
    assert should_skip_inactive(None, "Finished") is False
    assert should_skip_inactive("Enabled", "Paused") is False
    assert should_skip_inactive("Paused", "Paused") is True
    assert should_skip_inactive("Finished", "Finished") is True
    assert should_skip_inactive("Paused", "Enabled") is False


def test_merge_product_rows_sets_bid_cpc_source_from_api() -> None:
    csv_rows = [
        {
            "campaign_id": "1",
            "sku_key": "sku-1",
            "product_name": "Item 1",
            "bid_cpc": None,
        }
    ]
    json_rows = [
        {
            "sku": "sku-1",
            "bid": 150.0,
        }
    ]

    merged = merge_product_rows(
        csv_rows,
        json_rows,
        "Campaign",
        "2025-01-01",
        "759051",
        "30137883",
    )

    assert merged[0]["bid_cpc"] == 150.0
    assert merged[0]["bid_cpc_source"] == "api_current"


def test_merge_product_rows_sets_bid_cpc_source_from_csv() -> None:
    csv_rows = [
        {
            "campaign_id": "1",
            "sku_key": "sku-1",
            "product_name": "Item 1",
            "bid_cpc": 200.0,
        }
    ]
    json_rows = [
        {
            "sku": "sku-1",
            "bid": 150.0,
        }
    ]

    merged = merge_product_rows(
        csv_rows,
        json_rows,
        "Campaign",
        "2025-01-01",
        "759051",
        "30137883",
    )

    assert merged[0]["bid_cpc"] == 200.0
    assert merged[0]["bid_cpc_source"] == "csv"
