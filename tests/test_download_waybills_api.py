import json
import sqlite3
from datetime import date

from scripts import download_waybills_api as waybill_mod
from scripts.download_waybills_api import get_target_order_ids_from_db, parse_date


def test_parse_date_handles_iso_datetime_without_dayfirst_flip():
    assert parse_date("2026-03-06 20:00:00") == date(2026, 3, 6)


def test_db_fallback_uses_raw_courier_planning_date_over_planned_shipment_date(tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            courier_transmission_planning_date TEXT,
            courier_transmission_date TEXT,
            signature_required INTEGER,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            returned_to_warehouse INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, assigned_size, my_size,
            planned_shipment_date, courier_transmission_planning_date,
            courier_transmission_date, signature_required,
            kaspi_status, kaspi_status_detail, returned_to_warehouse
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "848191280",
            "STOREB",
            "S",
            "",
            "2026-03-07",
            "2026-03-08 20:00:00",
            None,
            0,
            "KASPI_DELIVERY",
            "ACCEPTED_BY_MERCHANT",
            0,
        ),
    )
    conn.commit()
    conn.close()

    selected = get_target_order_ids_from_db(
        db_path,
        target_date=date(2026, 3, 7),
        store_filter="STOREB",
        exact_date=False,
        lookback_days=3,
    )

    assert selected == {}


def test_db_fallback_includes_overdue_pending_row_with_raw_courier_datetime(tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            courier_transmission_planning_date TEXT,
            courier_transmission_date TEXT,
            signature_required INTEGER,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            returned_to_warehouse INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, assigned_size, my_size,
            planned_shipment_date, courier_transmission_planning_date,
            courier_transmission_date, signature_required,
            kaspi_status, kaspi_status_detail, returned_to_warehouse
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "846479842",
            "STOREB",
            "L",
            "",
            "2026-03-06",
            "2026-03-06 20:00:00",
            None,
            0,
            "KASPI_DELIVERY",
            "ACCEPTED_BY_MERCHANT",
            0,
        ),
    )
    conn.commit()
    conn.close()

    selected = get_target_order_ids_from_db(
        db_path,
        target_date=date(2026, 3, 7),
        store_filter="STOREB",
        exact_date=False,
        lookback_days=3,
    )

    assert selected == {"STOREB": {"846479842"}}


def test_download_all_waybills_keeps_cached_overdue_fallback_targets(monkeypatch, tmp_path):
    output_dir = tmp_path / "waybills"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "845784291.pdf").write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(waybill_mod, "STORE_TOKEN_MAP", {"STOREB": "token"})
    monkeypatch.setattr(
        waybill_mod,
        "get_target_orders_from_api",
        lambda *args, **kwargs: (
            [{"attributes": {"code": "847016620"}}],
            False,
        ),
    )
    monkeypatch.setattr(
        waybill_mod,
        "get_target_order_ids_from_db",
        lambda *args, **kwargs: {"STOREB": {"847016620", "845784291"}},
    )
    monkeypatch.setattr(
        waybill_mod,
        "get_target_order_ids_from_crm",
        lambda *args, **kwargs: {},
    )

    captured: dict[str, set[str]] = {}

    def _fake_download_waybills_for_store(store_code, target_order_ids, **_kwargs):
        captured[store_code] = set(target_order_ids)
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": 1,
            "invalid_pdf": 0,
            "skipped_terminal": 0,
            "skipped_nonready": 0,
            "terminal_skipped_order_ids": [],
            "nonready_skipped_order_ids": [],
            "errors": [],
        }

    monkeypatch.setattr(waybill_mod, "download_waybills_for_store", _fake_download_waybills_for_store)

    waybill_mod.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=date(2026, 3, 7),
        db_path=tmp_path / "app.db",
        since_days=3,
        fallback_crm=True,
    )

    assert captured == {"STOREB": {"847016620", "845784291"}}

    payload = json.loads((output_dir / "_waybill_selection_orders.json").read_text(encoding="utf-8"))
    assert payload["stores"] == {"STOREB": ["845784291", "847016620"]}


def test_download_all_waybills_fitpack_exclusion_filters_storeb_fallback(monkeypatch, tmp_path):
    output_dir = tmp_path / "waybills"
    captured: dict[str, set[str]] = {}
    api_called: list[str] = []

    monkeypatch.setattr(waybill_mod, "load_storeb_packing_excluded", lambda **_kwargs: True)
    monkeypatch.setattr(waybill_mod, "STORE_TOKEN_MAP", {"STOREB": "token", "UNIVERSAL": "token"})
    monkeypatch.setattr(
        waybill_mod,
        "load_sync_enabled_kaspi_store_codes",
        lambda: ["STOREB", "UNIVERSAL"],
    )

    def _fake_api(store_code, *args, **kwargs):
        api_called.append(store_code)
        return ([{"attributes": {"code": "U1001"}}], False)

    monkeypatch.setattr(waybill_mod, "get_target_orders_from_api", _fake_api)
    monkeypatch.setattr(waybill_mod, "get_target_order_ids_from_crm", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        waybill_mod,
        "get_target_order_ids_from_db",
        lambda *args, **kwargs: {"STOREB": {"M2001"}, "UNIVERSAL": {"U1002"}},
    )

    def _fake_download_waybills_for_store(store_code, target_order_ids, **_kwargs):
        captured[store_code] = set(target_order_ids)
        return {
            "downloaded": 0,
            "skipped_not_target": 0,
            "missing_waybill": 0,
            "already_exists": len(target_order_ids),
            "invalid_pdf": 0,
            "skipped_terminal": 0,
            "skipped_nonready": 0,
            "terminal_skipped_order_ids": [],
            "nonready_skipped_order_ids": [],
            "errors": [],
        }

    monkeypatch.setattr(waybill_mod, "download_waybills_for_store", _fake_download_waybills_for_store)

    result = waybill_mod.download_all_waybills(
        output_dir=output_dir,
        crm_path=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        target_date=date(2026, 7, 4),
        db_path=tmp_path / "app.db",
        since_days=3,
        fallback_crm=True,
    )

    assert api_called == ["UNIVERSAL"]
    assert captured == {"UNIVERSAL": {"U1001", "U1002"}}
    assert result["fitpack_storeb_excluded"] is True
    assert result["fitpack_storeb_skipped"] == 1
    payload = json.loads((output_dir / "_waybill_selection_orders.json").read_text(encoding="utf-8"))
    assert payload["stores"] == {"UNIVERSAL": ["U1001", "U1002"]}
