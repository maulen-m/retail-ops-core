import json
import sys
from datetime import date

from scripts import report_import_status as report_mod
from scripts.report_import_status import normalize_store_name, parse_date


def test_normalize_store_name_maps_store_codes():
    assert normalize_store_name("30362323_PP1") == "Store-C"
    assert normalize_store_name("30000002_PP1") == "STORE-B"


def test_normalize_store_name_maps_api_codes():
    assert normalize_store_name("MELVIS") == "Store-C"
    assert normalize_store_name("STOREB") == "STORE-B"


def test_parse_date_handles_iso_datetime_without_dayfirst_flip():
    assert parse_date("2026-03-06 20:00:00") == date(2026, 3, 6)


def test_report_import_status_writes_json_summary(monkeypatch, tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    db_path = tmp_path / "app.db"
    out_json = tmp_path / "health.json"

    monkeypatch.setattr(
        report_mod,
        "get_api_orders_by_store",
        lambda *_args, **_kwargs: ({"UNIVERSAL": {"1", "2"}}, set()),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_db_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1", "2"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_seller_fee_coverage",
        lambda *_args, **_kwargs: {
            "Universal": {
                "seller_fee_expected": 1,
                "seller_fee_filled": 1,
                "miss_seller_fee": 0,
            }
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_import_status.py",
            "--date",
            "2026-02-16",
            "--crm-file",
            str(crm_path),
            "--db-path",
            str(db_path),
            "--json-out",
            str(out_json),
        ],
    )

    rc = report_mod.main()
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["target_date"] == "2026-02-16"
    assert payload["partial_api"] is False
    assert payload["totals"]["api_today"] == 2
    assert payload["totals"]["crm_today"] == 1
    assert payload["totals"]["miss_crm"] == 1
    assert payload["totals"]["stale_crm"] == 0
    assert payload["totals"]["seller_fee_expected"] == 1
    assert payload["totals"]["seller_fee_filled"] == 1
    assert payload["totals"]["miss_seller_fee"] == 0


def test_get_api_orders_by_store_uses_kaspi_delivery_state(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, store_code: str):
            captured["store_code"] = store_code

        def list_all_orders(self, *, state: str, since: str, include_orders: str):
            captured["state"] = state
            captured["since"] = since
            captured["include_orders"] = include_orders
            return []

    monkeypatch.setattr(report_mod, "STORE_TOKEN_MAP", {"UNIVERSAL": "token"})
    monkeypatch.setattr(report_mod, "KaspiAPIClient", _FakeClient)

    orders, errors = report_mod.get_api_orders_by_store(date(2026, 2, 17), since_days=5)

    assert orders == {}
    assert errors == set()
    assert captured["store_code"] == "UNIVERSAL"
    assert captured["state"] == "KASPI_DELIVERY"
    assert captured["include_orders"] == "user"


def test_report_import_status_counts_stale_today_crm_rows(monkeypatch, tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    db_path = tmp_path / "app.db"
    out_json = tmp_path / "health.json"

    monkeypatch.setattr(
        report_mod,
        "get_api_orders_by_store",
        lambda *_args, **_kwargs: ({"UNIVERSAL": {"1"}}, set()),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1", "2"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_db_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_seller_fee_coverage",
        lambda *_args, **_kwargs: {
            "Universal": {
                "seller_fee_expected": 2,
                "seller_fee_filled": 1,
                "miss_seller_fee": 1,
            }
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_import_status.py",
            "--date",
            "2026-02-16",
            "--crm-file",
            str(crm_path),
            "--db-path",
            str(db_path),
            "--json-out",
            str(out_json),
        ],
    )

    rc = report_mod.main()
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["totals"]["miss_crm"] == 0
    assert payload["totals"]["stale_crm"] == 1
    assert payload["totals"]["seller_fee_expected"] == 2
    assert payload["totals"]["seller_fee_filled"] == 1
    assert payload["totals"]["miss_seller_fee"] == 1


def test_report_import_status_ignores_carryforward_rows_in_stale_today_metric(monkeypatch, tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    db_path = tmp_path / "app.db"
    out_json = tmp_path / "health.json"

    monkeypatch.setattr(
        report_mod,
        "get_api_orders_by_store",
        lambda *_args, **_kwargs: ({"UNIVERSAL": {"1"}}, set()),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1", "2"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_carryforward_orders",
        lambda *_args, **_kwargs: {"Universal": {"2"}},
    )
    monkeypatch.setattr(
        report_mod,
        "get_db_orders",
        lambda *_args, **_kwargs: ({"Universal": {"1", "2"}}, {"Universal": {"1"}}),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_seller_fee_coverage",
        lambda *_args, **_kwargs: {
            "Universal": {
                "seller_fee_expected": 2,
                "seller_fee_filled": 2,
                "miss_seller_fee": 0,
            }
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_import_status.py",
            "--date",
            "2026-04-09",
            "--crm-file",
            str(crm_path),
            "--db-path",
            str(db_path),
            "--json-out",
            str(out_json),
        ],
    )

    rc = report_mod.main()
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["totals"]["miss_crm"] == 0
    assert payload["totals"]["stale_crm"] == 0


def test_report_import_status_includes_seller_fee_metrics_per_store(monkeypatch, tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    db_path = tmp_path / "app.db"
    out_json = tmp_path / "health.json"

    monkeypatch.setattr(
        report_mod,
        "get_api_orders_by_store",
        lambda *_args, **_kwargs: ({"ACMEWEAR": {"1"}, "UNIVERSAL": {"2", "3"}}, set()),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_orders",
        lambda *_args, **_kwargs: (
            {"AcmeWear": {"1"}, "Universal": {"2", "3"}},
            {"AcmeWear": {"1"}, "Universal": {"2", "3"}},
        ),
    )
    monkeypatch.setattr(
        report_mod,
        "get_db_orders",
        lambda *_args, **_kwargs: (
            {"AcmeWear": {"1"}, "Universal": {"2", "3"}},
            {"AcmeWear": {"1"}, "Universal": {"2", "3"}},
        ),
    )
    monkeypatch.setattr(
        report_mod,
        "get_crm_seller_fee_coverage",
        lambda *_args, **_kwargs: {
            "AcmeWear": {
                "seller_fee_expected": 1,
                "seller_fee_filled": 1,
                "miss_seller_fee": 0,
            },
            "Universal": {
                "seller_fee_expected": 2,
                "seller_fee_filled": 1,
                "miss_seller_fee": 1,
            },
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_import_status.py",
            "--date",
            "2026-02-16",
            "--crm-file",
            str(crm_path),
            "--db-path",
            str(db_path),
            "--json-out",
            str(out_json),
        ],
    )

    rc = report_mod.main()
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["stores"]["AcmeWear"]["seller_fee_expected"] == 1
    assert payload["stores"]["AcmeWear"]["seller_fee_filled"] == 1
    assert payload["stores"]["AcmeWear"]["miss_seller_fee"] == 0
    assert payload["stores"]["Universal"]["seller_fee_expected"] == 2
    assert payload["stores"]["Universal"]["seller_fee_filled"] == 1
    assert payload["stores"]["Universal"]["miss_seller_fee"] == 1


def test_get_api_orders_by_store_excludes_next_day_courier_planning(monkeypatch):
    tomorrow_order = {
        "attributes": {
            "code": "848191280",
            "state": "KASPI_DELIVERY",
            "status": "ACCEPTED_BY_MERCHANT",
            "creationDate": 1772877981264,  # 2026-03-07 15:06:21 +05:00
            "kaspiDelivery": {
                "courierTransmissionPlanningDate": 1772982000000,  # 2026-03-08 20:00:00 +05:00
            },
        }
    }

    class _FakeClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return [tomorrow_order]

    monkeypatch.setattr(report_mod, "STORE_TOKEN_MAP", {"STOREB": "token"})
    monkeypatch.setattr(report_mod, "KaspiAPIClient", _FakeClient)

    orders, errors = report_mod.get_api_orders_by_store(date(2026, 3, 7), since_days=3)

    assert errors == set()
    assert orders == {}
