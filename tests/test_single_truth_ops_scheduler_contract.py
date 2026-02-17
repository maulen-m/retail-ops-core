from pathlib import Path


def test_single_truth_preflight_plist_contract() -> None:
    plist_path = Path("config/com.example.single-truth-preflight.plist")
    assert plist_path.exists(), "missing launchd plist for strict preflight"
    plist = plist_path.read_text(encoding="utf-8")
    assert "<string>com.example.single-truth-preflight</string>" in plist
    assert "<key>AB_CRM_WORKBOOK_PATH</key>" in plist
    assert "<string>~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx</string>" in plist
    assert "<key>AB_CRM_WORKBOOK_MAX_AGE_HOURS</key>" in plist
    assert "<string>36</string>" in plist
    assert "<key>AB_CRM_WORKBOOK_MAX_FUTURE_SKEW_SECONDS</key>" in plist
    assert "<string>120</string>" in plist
    assert "<string>scripts/run_strict_daily_preflight.py</string>" in plist
    assert "<string>--emit-lineage</string>" in plist
    assert "<string>--send-alert-on-fail</string>" in plist
    assert "<string>--ensure-business-insides</string>" in plist
    assert "<string>/usr/bin/env</string>" in plist
    assert "<string>python3</string>" in plist


def test_on_delivery_residuals_plist_contract() -> None:
    plist_path = Path("config/com.example.on-delivery-residuals.plist")
    assert plist_path.exists(), "missing launchd plist for on-delivery residual checks"
    plist = plist_path.read_text(encoding="utf-8")
    assert "<string>com.example.on-delivery-residuals</string>" in plist
    assert "<string>scripts/check_on_delivery_residuals.py</string>" in plist
    assert "<string>--send-alert</string>" in plist
    assert "<string>--since</string>" in plist
    assert "<string>2026-01-01</string>" in plist
    assert "<string>/usr/bin/env</string>" in plist
    assert "<string>python3</string>" in plist


def test_install_script_references_both_single_truth_jobs() -> None:
    script_path = Path("scripts/install_single_truth_ops_scheduler.sh")
    assert script_path.exists(), "missing scheduler installer"
    script = script_path.read_text(encoding="utf-8")
    assert "com.example.single-truth-preflight.plist" in script
    assert "com.example.on-delivery-residuals.plist" in script
    assert "launchctl load" in script
