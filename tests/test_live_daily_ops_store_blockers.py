from __future__ import annotations

from scripts.run_kaspi_daily_ops import classify_preflight_blocker, classify_store_blocker


def test_classify_store_blocker_parses_waybill_stopline_counts() -> None:
    meta = classify_store_blocker(
        "UNIVERSAL",
        1,
        "\n".join(
            [
                "| Universal | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 2 |",
                "Missing in CRM (first 5): 849656111, 850084962",
                "Missing PDF (first 5): 849656111, 850084962",
                "Missing in bundles (first 5): 849656111, 850084962",
                "STOP-LINE: strict waybill health gate failed",
            ]
        ),
    )

    assert meta["blocker_class"] == "WAYBILL_STOPLINE"
    assert meta["blocker_details"]["miss_crm"] == 2
    assert meta["blocker_details"]["miss_pdf"] == 2
    assert meta["blocker_details"]["miss_bundle"] == 2
    assert meta["blocker_details"]["missing_order_ids"] == ["849656111", "850084962"]


def test_classify_preflight_blocker_detects_validate_params_failure() -> None:
    blocker = classify_preflight_blocker(
        "\n".join(
            [
                "Shipment Preflight",
                "Status: FAIL",
                "- anchor_health: OK (rc=0) anchor health PASS",
                "- validate_params_strict: FAIL (rc=1) Status: FAIL",
                "- ops_status: OK (rc=0) OPS_STATUS PASS: anchor health PASS; validate-only PASS",
            ]
        )
    )

    assert blocker["blocker_class"] == "PREFLIGHT_VALIDATE_PARAMS"
    assert blocker["failed_checks"] == ["validate_params_strict"]
