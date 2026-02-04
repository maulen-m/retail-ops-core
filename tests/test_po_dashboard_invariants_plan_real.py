from scripts.validate_po_dashboard_invariants import validate_payload


def test_non_plan_requires_archived_pos_entry():
    payload = {
        "pos": {
            "PO-1": {
                "po_name": "PO-1",
                "po_kind": "REAL_ARCHIVE",
                "sku_level": [],
            }
        },
        "archived_pos": [],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("archived_pos" in err for err in errors)


def test_non_plan_requires_real_archive_kind():
    payload = {
        "pos": {
            "PO-1": {
                "po_name": "PO-1",
                "sku_level": [],
            }
        },
        "archived_pos": ["PO-1"],
        "real_pos": [],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("po_kind" in err for err in errors)


def test_real_pos_requires_min_fields():
    payload = {
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "sku_level": [],
            }
        },
        "archived_pos": [],
        "real_pos": [
            {
                "po_id": "PO-1",
                "status": "IN_TRANSIT",
                "message_date": None,
                "units_total": 0,
            }
        ],
    }

    errors = validate_payload(payload, db_path=None, strict_portfolio=False)
    assert any("real_pos" in err for err in errors)
