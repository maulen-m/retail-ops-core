from scripts.audit_dashboard_output import audit_prep_model


def test_prep_model_audit_skips_real_archive_els_rows() -> None:
    data = {
        "pos": {
            "EPSON_PO-1": {
                "po_kind": "REAL_ARCHIVE",
                "sku_level": [
                    {
                        "sku_key": "ELS_PRINTER_EPSON_L1250_BLACK",
                        "po_qty_total": 4,
                        "prep_days": 0,
                    }
                ],
            }
        }
    }

    ok, messages = audit_prep_model(data)

    assert ok is True
    assert any("REAL_ARCHIVE" in message for message in messages)


def test_prep_model_audit_still_blocks_future_els_zero_prep() -> None:
    data = {
        "pos": {
            "PLAN-1": {
                "po_kind": "PLAN",
                "sku_level": [
                    {
                        "sku_key": "ELS_PRINTER_EPSON_L1250_BLACK",
                        "po_qty_total": 4,
                        "prep_days": 0,
                    }
                ],
            }
        }
    }

    ok, messages = audit_prep_model(data)

    assert ok is False
    assert any("expected=1" in message for message in messages)
