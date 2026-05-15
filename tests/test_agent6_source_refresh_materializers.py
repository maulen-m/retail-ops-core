from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts import materialize_order_status_events_from_kaspi_orders as status_events
from scripts import sync_bank_manual_ingest_snapshot as bank_ingest
from scripts.migrate_027_order_status_observations import migrate as migrate_observations
from scripts.migrate_028_operational_stock_truth_p0_schema import migrate as migrate_p0


FX_RATES = {
    "USDT_KZT": (490.0, "binance_p2p", "2026-02-10"),
    "USD_KZT": (514.0, "dim_fx_rates", "2026-02-06"),
    "RUB_KZT": (6.6, "default", "hardcoded"),
    "CNY_KZT": (75.0, "dim_fx_rates", "2026-02-06"),
}


BROKEN_MANUAL_INGEST = """\
as_of: 2026-05-03 19:59:00 GMT+5
stores:
  UNIVERSAL:
    accounts:
      kaspi_gold:
        balance_kzt: 3191000
      kaspi_pay:10000
        balance_kzt:
      bcc:
        balance_kzt: 306000
      freedom:
        balance_kzt: 27000
      cash_kzt:
        balance_kzt: 495000
      cash_usd:
        balance_usd: 0
      cash_rub:
        balance_rub: 10000
      binance_usdt:
        balance_usdt: 3526,19
  "11KZ":
    accounts:
      kaspi_gold:
        balance_kzt: 0
      kaspi_pay:
        balance_kzt: 0
      binance_usdt:
        balance_usdt: 0
  STOREB:
    accounts:
      kaspi_gold:
        balance_kzt: 34000
      kaspi_pay:
        balance_kzt: 7000
  ACMEWEAR:
    accounts:
      kaspi_gold:
        balance_kzt: 422000
      kaspi_pay:
        balance_kzt: 1465000
      cash_kzt:
        balance_kzt: 0
  MELVIS:
    accounts:
      kaspi_gold:
        balance_kzt: 0
      kaspi_pay:
        balance_kzt: 0
"""


def test_bank_manual_ingest_normalizes_snapshot_and_history_without_apply(tmp_path: Path) -> None:
    manual = tmp_path / "manual.yaml"
    history = tmp_path / "history.yaml"
    snapshot = tmp_path / "bank_accounts.yaml"
    totals = tmp_path / "bank_accounts_history_totals.md"
    manual.write_text(BROKEN_MANUAL_INGEST, encoding="utf-8")
    history.write_text("entries:\n", encoding="utf-8")

    report = bank_ingest.sync_manual_ingest_snapshot(
        manual_path=manual,
        history_path=history,
        snapshot_path=snapshot,
        totals_path=totals,
        fx_rates=FX_RATES,
        apply=False,
    )

    assert report["applied"] is False
    assert report["balance_row_count"] == 18
    assert report["totals_by_currency"] == {
        "KZT": 5957000.0,
        "RUB": 10000.0,
        "USD": 0.0,
        "USDT": 3526.19,
    }
    assert report["total_kzt_equivalent"] == pytest.approx(7750833.1)
    assert "kaspi_pay:10000" not in report["normalized_manual_yaml"]
    assert "balance_usdt: 3526.19" in report["normalized_manual_yaml"]
    assert not snapshot.exists()
    assert history.read_text(encoding="utf-8") == "entries:\n"


def test_bank_manual_ingest_apply_is_env_gated_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manual = tmp_path / "manual.yaml"
    history = tmp_path / "history.yaml"
    snapshot = tmp_path / "bank_accounts.yaml"
    totals = tmp_path / "bank_accounts_history_totals.md"
    manual.write_text(BROKEN_MANUAL_INGEST, encoding="utf-8")
    history.write_text("entries:\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="ENABLE_BANK_MANUAL_INGEST_WRITE=1"):
        bank_ingest.sync_manual_ingest_snapshot(
            manual_path=manual,
            history_path=history,
            snapshot_path=snapshot,
            totals_path=totals,
            fx_rates=FX_RATES,
            apply=True,
        )

    monkeypatch.setenv(bank_ingest.BANK_MANUAL_INGEST_ENV_GATE, "1")
    first = bank_ingest.sync_manual_ingest_snapshot(
        manual_path=manual,
        history_path=history,
        snapshot_path=snapshot,
        totals_path=totals,
        fx_rates=FX_RATES,
        apply=True,
    )
    second = bank_ingest.sync_manual_ingest_snapshot(
        manual_path=manual,
        history_path=history,
        snapshot_path=snapshot,
        totals_path=totals,
        fx_rates=FX_RATES,
        apply=True,
    )

    assert first["history_appended"] is True
    assert second["history_appended"] is False
    assert yaml.safe_load(manual.read_text(encoding="utf-8"))["stores"]["UNIVERSAL"]["accounts"]["kaspi_pay"]["balance_kzt"] == 10000
    entries = yaml.safe_load(history.read_text(encoding="utf-8"))["entries"]
    assert len(entries) == 1
    assert entries[0]["as_of"] == "2026-05-03 19:59:00 GMT+5"
    assert "TOTALS (as of 2026-05-03)" in snapshot.read_text(encoding="utf-8")
    assert "2026-05-03 19:59:00 GMT+5" in totals.read_text(encoding="utf-8")


def _seed_order_db(db_path: Path) -> None:
    migrate_p0(db_path)
    migrate_observations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, updated_at, created_at, source
            ) VALUES (
                'ORD-1', 'ACMEWEAR', 'ARCHIVE', 'COMPLETED', 'COMPLETED',
                '2026-05-03T10:15:00+05:00',
                '2026-05-03T10:20:00+05:00', '2026-05-01T09:00:00+05:00',
                'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, sku_id, kaspi_status, kaspi_status_detail, internal_status,
                status_updated_at, updated_at, created_at, source
            ) VALUES (
                'ORD-1', 'ACMEWEAR', 'SKU-SECOND', 'ARCHIVE', 'COMPLETED', 'COMPLETED',
                '2026-05-03T10:15:00+05:00',
                '2026-05-03T10:25:00+05:00', '2026-05-01T09:00:00+05:00',
                'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations (
                order_id, store_code, status_internal, observed_at, source, ledger_run_id
            ) VALUES (
                'ORD-2', 'STOREB', 'RETURNED', '2026-05-03T11:00:00+05:00',
                'WEBUI_ARCHIVE', 'obs-run'
            )
            """
        )
        conn.commit()


def test_order_status_materializer_is_dry_run_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_order_db(db_path)

    report = status_events.materialize_order_status_events(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-status-events",
        apply=False,
        backup_dir=tmp_path / "backups",
    )

    assert report["applied"] is False
    assert report["backup_path"] is None
    assert report["candidate_count"] == 2
    assert report["stage_counts"] == {"COMPLETED": 1, "RETURNED": 1}
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM order_status_event").fetchone()[0] == 0


def test_order_status_materializer_apply_is_env_gated_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _seed_order_db(db_path)

    with pytest.raises(RuntimeError, match="ENABLE_ORDER_STATUS_EVENT_WRITE=1"):
        status_events.materialize_order_status_events(
            db_path=db_path,
            as_of="2026-05-03",
            run_id="pytest-status-events",
            apply=True,
            backup_dir=tmp_path / "backups",
        )

    monkeypatch.setenv(status_events.ORDER_STATUS_EVENT_ENV_GATE, "1")
    first = status_events.materialize_order_status_events(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-status-events",
        apply=True,
        backup_dir=tmp_path / "backups",
    )
    second = status_events.materialize_order_status_events(
        db_path=db_path,
        as_of="2026-05-03",
        run_id="pytest-status-events",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    assert Path(first["backup_path"]).exists()
    assert first["inserted_count"] == 2
    assert second["inserted_count"] == 0
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT store_code, order_id, stage_code, source, source_run_id
            FROM order_status_event
            ORDER BY store_code, order_id
            """
        ).fetchall()
    assert rows == [
        ("STOREB", "ORD-2", "RETURNED", "LOCAL_FACT_ORDER_STATUS_OBSERVATIONS", "pytest-status-events"),
        ("ACMEWEAR", "ORD-1", "COMPLETED", "LOCAL_FACT_ORDERS_KASPI", "pytest-status-events"),
    ]


def test_order_status_materializer_as_of_excludes_future_status_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    migrate_p0(db_path)
    migrate_observations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, updated_at, created_at, source
            ) VALUES (
                'ORD-BEFORE', 'ACMEWEAR', 'ARCHIVE', 'COMPLETED',
                'COMPLETED', '2026-05-04T21:59:00+05:00',
                '2026-05-04T22:00:00+05:00', '2026-05-04T09:00:00+05:00',
                'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, updated_at, created_at, source
            ) VALUES (
                'ORD-AFTER', 'ACMEWEAR', 'ARCHIVE', 'COMPLETED',
                'COMPLETED', '2026-05-05T00:01:00+05:00',
                '2026-05-05T00:02:00+05:00', '2026-05-04T09:00:00+05:00',
                'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations (
                order_id, store_code, status_internal, observed_at, source, ledger_run_id
            ) VALUES (
                'OBS-BEFORE', 'STOREB', 'RETURNED', '2026-05-04T12:00:00+05:00',
                'WEBUI_ARCHIVE', 'obs-run'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_status_observations (
                order_id, store_code, status_internal, observed_at, source, ledger_run_id
            ) VALUES (
                'OBS-AFTER', 'STOREB', 'RETURNED', '2026-05-05T12:00:00+05:00',
                'WEBUI_ARCHIVE', 'obs-run'
            )
            """
        )
        conn.commit()

    monkeypatch.setenv(status_events.ORDER_STATUS_EVENT_ENV_GATE, "1")
    report = status_events.materialize_order_status_events(
        db_path=db_path,
        as_of="2026-05-04",
        run_id="pytest-asof-contract",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT order_id, date(event_ts)
            FROM order_status_event
            WHERE source_run_id = ?
            ORDER BY order_id
            """,
            ("pytest-asof-contract",),
        ).fetchall()
        post_as_of_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM order_status_event
            WHERE source_run_id = ?
              AND date(event_ts) > date('2026-05-04')
            """,
            ("pytest-asof-contract",),
        ).fetchone()[0]

    assert report["as_of"] == "2026-05-04"
    assert report["candidate_count"] == 2
    assert report["inserted_count"] == 2
    assert rows == [
        ("OBS-BEFORE", "2026-05-04"),
        ("ORD-BEFORE", "2026-05-04"),
    ]
    assert post_as_of_count == 0


def test_order_status_materializer_without_as_of_keeps_current_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    migrate_p0(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, updated_at, created_at, source
            ) VALUES (
                'ORD-CURRENT', 'ACMEWEAR', 'ARCHIVE', 'COMPLETED',
                'COMPLETED', '2026-05-05T12:01:00+05:00',
                '2026-05-05T12:02:00+05:00', '2026-05-04T09:00:00+05:00',
                'API'
            )
            """
        )
        conn.commit()

    monkeypatch.setenv(status_events.ORDER_STATUS_EVENT_ENV_GATE, "1")
    report = status_events.materialize_order_status_events(
        db_path=db_path,
        as_of=None,
        run_id="pytest-current-contract",
        apply=True,
        backup_dir=tmp_path / "backups",
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT order_id, date(event_ts)
            FROM order_status_event
            WHERE source_run_id = ?
            """,
            ("pytest-current-contract",),
        ).fetchall()

    assert report["as_of"] is None
    assert report["candidate_count_before_as_of_filter"] == 1
    assert report["candidate_count_after_as_of_filter"] == 1
    assert report["as_of_filtered_count"] == 0
    assert report["inserted_count"] == 1
    assert rows == [("ORD-CURRENT", "2026-05-05")]


def test_order_status_materializer_requires_strict_completed_header_contract(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    migrate_p0(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, source
            ) VALUES (
                'ORD-STRICT', 'ACMEWEAR', 'ARCHIVE', 'COMPLETED',
                'COMPLETED', '2026-05-03T10:15:00+05:00', 'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, source
            ) VALUES (
                'ORD-LOOSE', 'ACMEWEAR', 'ARCHIVE', 'ACCEPTED_BY_MERCHANT',
                'COMPLETED', '2026-05-03T10:20:00+05:00', 'API'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                order_id, store_code, kaspi_status, kaspi_status_detail,
                internal_status, status_updated_at, source
            ) VALUES (
                'ORD-MISSING-DETAIL', 'ACMEWEAR', 'ARCHIVE', NULL,
                'COMPLETED', '2026-05-03T10:25:00+05:00', 'API'
            )
            """
        )
        conn.commit()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        candidates, skipped = status_events.build_order_status_event_candidates(
            conn,
            run_id="pytest-strict-contract",
        )
    finally:
        conn.close()

    assert skipped == {"fact_orders_kaspi": 2}
    assert [(row["order_id"], row["stage_code"]) for row in candidates] == [
        ("ORD-STRICT", "COMPLETED")
    ]
