import csv

from scripts.report_waybill_status import load_output_assigned, normalize_store_name


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
