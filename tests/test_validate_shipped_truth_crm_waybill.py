from __future__ import annotations

from datetime import date, timedelta
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts import validate_shipped_truth_crm_waybill as shipped_validator


def _write_crm(path: Path, rows: list[dict[str, object]]) -> None:
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SALES_KSP_CRM_1", index=False)


def _write_db(path: Path, statuses: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT PRIMARY KEY,
            internal_status TEXT
        )
        """
    )
    for order_id, status in statuses.items():
        conn.execute(
            "INSERT INTO fact_orders_kaspi(order_id, internal_status) VALUES(?, ?)",
            (order_id, status),
        )
    conn.commit()
    conn.close()


def _write_archive_waybills(archive_root: Path, day: str, order_ids: list[str]) -> None:
    waybill_dir = archive_root / f"input_{day}_183550" / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    for order_id in order_ids:
        (waybill_dir / f"{order_id}.pdf").write_bytes(b"%PDF-1.4\n%stub\n")


def test_fetch_api_shipped_for_day_queries_kaspi_delivery_and_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class DummyClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **kwargs):
            state = kwargs["state"]
            calls.append((self.store_code, state))
            if state == "ARCHIVE":
                return [
                    {
                        "attributes": {
                            "code": "900000001",
                            "state": "ARCHIVE",
                            "status": "completed",
                            "kaspiDelivery": {
                                "courierTransmissionDate": 1772352000000,  # 2026-03-01 13:00:00+05
                            },
                        }
                    }
                ]
            return []

    monkeypatch.setattr(shipped_validator, "KaspiAPIClient", DummyClient)
    monkeypatch.setattr(shipped_validator, "STORE_TOKEN_MAP", {"UNIVERSAL": "x"})

    df = shipped_validator.fetch_api_shipped_for_day(date(2026, 3, 1), "2026-02-25")

    assert set(calls) == {("UNIVERSAL", "KASPI_DELIVERY"), ("UNIVERSAL", "ARCHIVE")}
    assert len(df) == 1
    assert str(df.iloc[0]["order_id"]) == "900000001"


def test_fetch_api_shipped_for_day_fails_when_no_store_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyClient:
        def __init__(self, store_code: str):
            raise shipped_validator.KaspiAuthError(f"missing token: {store_code}")

    monkeypatch.setattr(shipped_validator, "KaspiAPIClient", DummyClient)
    monkeypatch.setattr(shipped_validator, "STORE_TOKEN_MAP", {"UNIVERSAL": "x", "ACMEWEAR": "y"})

    with pytest.raises(RuntimeError, match="No Kaspi API tokens configured"):
        shipped_validator.fetch_api_shipped_for_day(date(2026, 3, 1), "2026-02-25")


def test_fetch_api_shipped_for_range_filters_by_courier_transmission_date(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str, str]] = []

    class DummyClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_orders(self, **kwargs):
            state = kwargs["state"]
            since = kwargs["since"]
            until = kwargs["until"]
            calls.append((self.store_code, state, since, until))
            return type(
                "Resp",
                (),
                {
                    "success": True,
                    "error": None,
                    "data": {
                        "data": [
                            {
                                "attributes": {
                                    "code": "9101",
                                    "state": state,
                                    "status": "completed",
                                    "kaspiDelivery": {"courierTransmissionDate": 1772352000000},  # 2026-03-01
                                }
                            },
                            {
                                "attributes": {
                                    "code": "9102",
                                    "state": state,
                                    "status": "completed",
                                    "kaspiDelivery": {"courierTransmissionDate": 1772438400000},  # 2026-03-02
                                }
                            },
                        ]
                    },
                },
            )()

    monkeypatch.setattr(shipped_validator, "KaspiAPIClient", DummyClient)
    monkeypatch.setattr(shipped_validator, "STORE_TOKEN_MAP", {"UNIVERSAL": "x"})

    df = shipped_validator.fetch_api_shipped_for_range(
        since=date(2026, 3, 1),
        until=date(2026, 3, 2),
    )

    assert len(df) == 2
    assert sorted(df["order_id"].tolist()) == ["9101", "9102"]
    assert all(row[1] in {"KASPI_DELIVERY", "ARCHIVE"} for row in calls)


def test_validate_passes_with_cancel_normalization(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "1001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "L",
            },
            {
                "OrderID": "1002",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "XL",
            },
            {
                "OrderID": "1003",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "M",
            },
        ],
    )
    _write_db(db_path, {"1001": "COMPLETED", "1002": "SHIPPED", "1003": "CANCELLED"})
    _write_archive_waybills(archive_root, "2026-02-27", ["1001", "1002", "1003"])

    def fake_fetcher(day: date, _since: str) -> pd.DataFrame:
        if day.isoformat() != "2026-02-27":
            return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])
        return pd.DataFrame(
            [
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "1001",
                    "is_cancelled_final": False,
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                },
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "1002",
                    "is_cancelled_final": False,
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                },
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "1003",
                    "is_cancelled_final": True,
                    "api_state": "ARCHIVE",
                    "api_status": "cancelled",
                },
            ]
        )

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-27",
        until="2026-02-27",
        strict=True,
        output_root=tmp_path / "out",
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=0.0,
        cancel_drift_threshold_pct=0.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    assert report["status"] == "PASS"
    assert report["rows"][0]["cancel_drift_pct"] == 0.0


def test_validate_fails_when_primary_mismatch_exceeds_threshold(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "2001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "L",
            },
            {
                "OrderID": "2002",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "XL",
            },
        ],
    )
    _write_db(db_path, {"2001": "SHIPPED", "2002": "SHIPPED"})
    _write_archive_waybills(archive_root, "2026-02-27", ["2001", "2002"])

    def fake_fetcher(day: date, _since: str) -> pd.DataFrame:
        if day.isoformat() != "2026-02-27":
            return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])
        return pd.DataFrame(
            [
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "2001",
                    "is_cancelled_final": False,
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                },
            ]
        )

    with pytest.raises(RuntimeError, match="shipped truth CRM/waybill validation failed"):
        shipped_validator.validate_shipped_truth_crm_waybill(
            project_root=tmp_path,
            since="2026-02-27",
            until="2026-02-27",
            strict=True,
            output_root=tmp_path / "out",
            volatility_days=0,
            mismatch_threshold_pct=0.0,
            waybill_missing_threshold_pct=100.0,
            cancel_drift_threshold_pct=100.0,
            crm_path=crm_path,
            db_path=db_path,
            archive_root=archive_root,
            api_fetcher=fake_fetcher,
        )
    exception_json = tmp_path / "exports" / "exceptions" / "2026-02-27" / "shipped_truth_exception.json"
    exception_md = tmp_path / "exports" / "exceptions" / "2026-02-27" / "shipped_truth_exception.md"
    assert exception_json.exists()
    assert exception_md.exists()


def test_cancel_drift_ignores_crm_pre_ship_cancellations(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "3001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "L",
            },
            {
                "OrderID": "3002",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "XL",
            },
            {
                # Cancelled in CRM but never entered shipped universe.
                "OrderID": "3999",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "27.02.2026",
                "MY_SIZE": "M",
            },
        ],
    )
    _write_db(db_path, {"3001": "COMPLETED", "3002": "CANCELLED", "3999": "CANCELLED"})
    _write_archive_waybills(archive_root, "2026-02-27", ["3001", "3002"])

    def fake_fetcher(day: date, _since: str) -> pd.DataFrame:
        if day.isoformat() != "2026-02-27":
            return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])
        return pd.DataFrame(
            [
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "3001",
                    "is_cancelled_final": False,
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                },
                {
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "3002",
                    "is_cancelled_final": True,
                    "api_state": "ARCHIVE",
                    "api_status": "cancelled",
                },
            ]
        )

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-27",
        until="2026-02-27",
        strict=True,
        output_root=tmp_path / "out",
        mismatch_threshold_pct=100.0,
        waybill_missing_threshold_pct=100.0,
        cancel_drift_threshold_pct=0.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    row = report["rows"][0]
    assert row["api_cancelled"] == 1
    assert row["crm_cancelled"] == 1
    assert row["cancel_drift_pct"] == 0.0


def test_recent_day_is_provisional_inside_volatility_window(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"
    day = shipped_validator.datetime.now(shipped_validator.ALMATY_TZ).date() - timedelta(days=1)

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "4001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": day.isoformat(),
                "MY_SIZE": "L",
            },
        ],
    )
    _write_db(db_path, {"4001": "SHIPPED"})

    def fake_fetcher(_day: date, _since: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since=day.isoformat(),
        until=day.isoformat(),
        strict=True,
        output_root=tmp_path / "out",
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=0.0,
        cancel_drift_threshold_pct=0.0,
        volatility_days=14,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=fake_fetcher,
    )
    assert report["ok"] is True
    assert report["rows"][0]["provisional"] is True


def test_validate_prefetch_uses_configured_api_creation_lookback_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"
    _write_crm(
        crm_path,
        [
            {
                "OrderID": "5001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "2026-02-27",
                "MY_SIZE": "L",
            },
        ],
    )
    _write_db(db_path, {"5001": "SHIPPED"})

    call_args: dict[str, int] = {}

    def fake_range(*, since: date, until: date, lookback_days: int = 7) -> pd.DataFrame:
        call_args["lookback_days"] = int(lookback_days)
        return pd.DataFrame(
            columns=[
                "ship_date",
                "store_code",
                "store_name",
                "order_id",
                "api_state",
                "api_status",
                "state_bucket",
                "is_cancelled_final",
            ]
        )

    monkeypatch.setattr(shipped_validator, "fetch_api_shipped_for_range", fake_range)

    shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-27",
        until="2026-02-27",
        strict=False,
        output_root=tmp_path / "out",
        mismatch_threshold_pct=100.0,
        waybill_missing_threshold_pct=100.0,
        cancel_drift_threshold_pct=100.0,
        api_creation_lookback_days=77,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=None,
    )

    assert call_args["lookback_days"] == 77


def test_adjacent_day_shifted_ids_are_not_counted_as_hard_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "6101",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "2026-02-16",
                "MY_SIZE": "L",
            },
            {
                "OrderID": "6102",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "2026-02-17",
                "MY_SIZE": "XL",
            },
        ],
    )
    _write_db(db_path, {"6101": "SHIPPED", "6102": "SHIPPED"})

    def fake_range(*, since: date, until: date, lookback_days: int = 7) -> pd.DataFrame:  # noqa: ARG001
        return pd.DataFrame(
            [
                {
                    "ship_date": date(2026, 2, 17),
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "6101",
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                    "state_bucket": "ARCHIVE",
                    "is_cancelled_final": False,
                },
                {
                    "ship_date": date(2026, 2, 16),
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "6102",
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                    "state_bucket": "ARCHIVE",
                    "is_cancelled_final": False,
                },
            ]
        )

    monkeypatch.setattr(shipped_validator, "fetch_api_shipped_for_range", fake_range)

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-16",
        until="2026-02-17",
        strict=True,
        output_root=tmp_path / "out",
        volatility_days=0,
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=100.0,
        cancel_drift_threshold_pct=100.0,
        date_shift_tolerance_days=1,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=None,
    )

    assert report["ok"] is True
    shifted_path = Path(report["shifted_csv"])
    assert shifted_path.exists()
    shifted_df = pd.read_csv(shifted_path)
    assert sorted(shifted_df["order_id"].astype(str).tolist()) == ["6101", "6101", "6102", "6102"]


def test_db_status_resolution_uses_latest_record_per_order(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "app.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            internal_status TEXT,
            imported_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi(order_id, internal_status, imported_at, updated_at)
        VALUES ('7001', 'NEW', '2026-02-10 10:00:00', '2026-02-10 10:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi(order_id, internal_status, imported_at, updated_at)
        VALUES ('7001', 'CANCELLED', '2026-02-11 10:00:00', '2026-02-11 10:00:00')
        """
    )
    conn.commit()
    conn.close()

    snapshot_map = shipped_validator._read_db_order_snapshot_map(db_path, ["7001"])
    assert snapshot_map["7001"].internal_status == "CANCELLED"


def test_new_db_rows_without_shipped_marker_are_excluded_from_crm_shipped_universe(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "8001",
                "STORE_NAME": "AcmeWear",
                "PLANNED_SHIPPING_DATE": "2026-02-20",
                "MY_SIZE": "XL",
            },
        ],
    )
    _write_db(db_path, {"8001": "NEW"})

    def fake_fetcher(_day: date, _since: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-20",
        until="2026-02-20",
        strict=True,
        output_root=tmp_path / "out",
        volatility_days=0,
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=0.0,
        cancel_drift_threshold_pct=0.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    row = report["rows"][0]
    assert row["crm_all"] == 1
    assert row["crm_expected"] == 0


def test_detail_fallback_recovers_missing_list_orders_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "9001",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "2026-02-10",
                "MY_SIZE": "L",
            },
        ],
    )
    _write_db(db_path, {"9001": "SHIPPED"})

    def fake_range(*, since: date, until: date, lookback_days: int = 7) -> pd.DataFrame:  # noqa: ARG001
        return pd.DataFrame(
            columns=[
                "ship_date",
                "store_code",
                "store_name",
                "order_id",
                "api_state",
                "api_status",
                "state_bucket",
                "is_cancelled_final",
            ]
        )

    class DummyClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def get_order(self, order_code: str):
            assert order_code == "9001"
            return type(
                "Resp",
                (),
                {
                    "success": True,
                    "data": {
                        "attributes": {
                            "code": "9001",
                            "state": "ARCHIVE",
                            "status": "completed",
                            "kaspiDelivery": {
                                "courierTransmissionDate": 1770732000000,  # 2026-02-10
                            },
                        }
                    },
                },
            )()

    monkeypatch.setattr(shipped_validator, "fetch_api_shipped_for_range", fake_range)
    monkeypatch.setattr(shipped_validator, "KaspiAPIClient", DummyClient)

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-10",
        until="2026-02-10",
        strict=True,
        output_root=tmp_path / "out",
        volatility_days=0,
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=100.0,
        cancel_drift_threshold_pct=100.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        api_fetcher=None,
    )

    assert report["ok"] is True
    assert report["rows"][0]["detail_fallback_hits"] == 1


def test_waybill_fallback_cache_covers_missing_archive_pdf(tmp_path: Path) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"
    fallback_dir = tmp_path / "excel_ui" / "ActiveOrders" / "waybills"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "910100",
                "STORE_NAME": "STORE-B",
                "PLANNED_SHIPPING_DATE": "2026-02-17",
                "MY_SIZE": "L",
            },
        ],
    )
    _write_db(db_path, {"910100": "SHIPPED"})
    # Intentionally no archive day PDF; only fallback cache has it.
    fallback_dir.mkdir(parents=True, exist_ok=True)
    (fallback_dir / "910100.pdf").write_bytes(b"%PDF-1.4\n%stub\n")

    def fake_fetcher(day: date, _since: str) -> pd.DataFrame:
        if day.isoformat() != "2026-02-17":
            return pd.DataFrame(columns=["store_name", "order_id", "is_cancelled_final"])
        return pd.DataFrame(
            [
                {
                    "store_code": "STOREB",
                    "store_name": "STORE-B",
                    "order_id": "910100",
                    "is_cancelled_final": False,
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                },
            ]
        )

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-17",
        until="2026-02-17",
        strict=True,
        output_root=tmp_path / "out",
        volatility_days=0,
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=0.0,
        cancel_drift_threshold_pct=0.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        waybill_fallback_dir=fallback_dir,
        api_fetcher=fake_fetcher,
    )

    assert report["ok"] is True
    assert report["rows"][0]["waybill_ids"] == 1


def test_waybill_detail_fallback_resolves_missing_pdf_without_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crm_path = tmp_path / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    db_path = tmp_path / "db" / "app.db"
    archive_root = tmp_path / "excel_ui" / "Archive"

    _write_crm(
        crm_path,
        [
            {
                "OrderID": "920100",
                "STORE_NAME": "Universal",
                "PLANNED_SHIPPING_DATE": "2026-02-10",
                "MY_SIZE": "L",
            },
        ],
    )
    _write_db(db_path, {"920100": "SHIPPED"})
    _write_archive_waybills(archive_root, "2026-02-10", ["999999"])

    def fake_range(*, since: date, until: date, lookback_days: int = 7) -> pd.DataFrame:  # noqa: ARG001
        return pd.DataFrame(
            [
                {
                    "ship_date": date(2026, 2, 10),
                    "store_code": "UNIVERSAL",
                    "store_name": "Universal",
                    "order_id": "920100",
                    "api_state": "ARCHIVE",
                    "api_status": "completed",
                    "state_bucket": "ARCHIVE",
                    "is_cancelled_final": False,
                },
            ]
        )

    class DummyClient:
        def __init__(self, store_code: str):  # noqa: ARG002
            pass

        def get_order(self, order_code: str):
            assert order_code == "920100"
            return type(
                "Resp",
                (),
                {
                    "success": True,
                    "data": {
                        "attributes": {
                            "code": "920100",
                            "state": "ARCHIVE",
                            "status": "completed",
                            "kaspiDelivery": {
                                "courierTransmissionDate": 1770732000000,  # 2026-02-10
                                "waybill": "https://example.test/waybill/920100",
                                "waybillNumber": "WB-920100",
                            },
                        }
                    },
                },
            )()

    monkeypatch.setattr(shipped_validator, "fetch_api_shipped_for_range", fake_range)
    monkeypatch.setattr(shipped_validator, "KaspiAPIClient", DummyClient)

    report = shipped_validator.validate_shipped_truth_crm_waybill(
        project_root=tmp_path,
        since="2026-02-10",
        until="2026-02-10",
        strict=True,
        output_root=tmp_path / "out",
        volatility_days=0,
        mismatch_threshold_pct=0.0,
        waybill_missing_threshold_pct=0.0,
        cancel_drift_threshold_pct=0.0,
        crm_path=crm_path,
        db_path=db_path,
        archive_root=archive_root,
        waybill_fallback_dir=tmp_path / "empty_waybills",
        api_fetcher=None,
    )

    assert report["ok"] is True
    row = report["rows"][0]
    assert row["waybill_detail_resolved"] == 1
