import csv
import zipfile

from scripts.report_waybill_status import (
    get_crm_orders,
    load_output_assigned,
    load_waybills,
    normalize_store_name,
    parse_date,
)


def test_normalize_store_name_maps_api_codes():
    assert normalize_store_name("MELVIS") == "Store-C"
    assert normalize_store_name("STOREB") == "STORE-B"


def test_parse_date_handles_iso_datetime_without_dayfirst_flip():
    assert parse_date("2026-03-06 20:00:00").isoformat() == "2026-03-06"


def test_load_output_assigned_normalizes_store_names(tmp_path):
    build_log = tmp_path / "build_log.csv"
    with open(build_log, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["type", "store", "order_id"])
        writer.writeheader()
        writer.writerow({"type": "NORMAL", "store": "MELVIS", "order_id": "123;456"})

    summary = tmp_path / "package_summary.csv"
    with open(summary, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Магазин", "Сумма", "Кол-во"])
        writer.writerow(["MELVIS", "", "5"])

    assigned, bundles, packages = load_output_assigned(tmp_path)

    assert assigned == {"Store-C": {"123", "456"}}
    assert bundles == {"Store-C": 1}
    assert packages == {"Store-C": 5}


def test_load_waybills_respects_order_id_filter(tmp_path):
    waybill_dir = tmp_path / "ActiveOrders"
    folder = waybill_dir / "waybills"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "111.pdf").write_bytes(b"%PDF-1.4")
    (folder / "222.pdf").write_bytes(b"%PDF-1.4")

    zip_path = waybill_dir / "waybill_a.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("KASPI_SHOP-333.pdf", b"%PDF-1.4")
        zf.writestr("KASPI_SHOP-444.pdf", b"%PDF-1.4")

    ids = load_waybills(waybill_dir, order_id_filter={"222", "333"})
    assert ids == {"222", "333"}


def test_get_crm_orders_backfills_blank_current_day_size_for_overdue_rows(tmp_path):
    crm_path = tmp_path / "crm.xlsx"
    rows = [
        {
            "Date": "2026-03-09",
            "OrderID": "850084962",
            "MY_SIZE": "M",
            "PLANNED_SHIPPING_DATE": "2026-03-09",
            "STORE_NAME": "Universal",
            "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
            "SKU_ID": "SKU-TOP",
            "Quantity": 1,
        },
        {
            "Date": "2026-03-10",
            "OrderID": "850084962",
            "MY_SIZE": "",
            "PLANNED_SHIPPING_DATE": "2026-03-09",
            "STORE_NAME": "Universal",
            "KASPI_OFFER_NAME": "Рашгард Мужская термофутболка для тренировок белый M",
            "SKU_ID": "SKU-TOP",
            "Quantity": 1,
        },
    ]
    import pandas as pd

    pd.DataFrame(rows).to_excel(crm_path, index=False)

    crm_all, crm_size = get_crm_orders(
        crm_path=crm_path,
        sheet_name="Sheet1",
        target_date=parse_date("2026-03-10"),
        include_overdue=True,
        lookback_days=3,
    )

    assert crm_all == {"Universal": {"850084962"}}
    assert crm_size == {"Universal": {"850084962"}}
