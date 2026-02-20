import csv
import zipfile

from scripts.report_waybill_status import (
    load_output_assigned,
    load_waybills,
    normalize_store_name,
)


def test_normalize_store_name_maps_api_codes():
    assert normalize_store_name("MELVIS") == "Store-C"
    assert normalize_store_name("STOREB") == "STORE-B"


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
