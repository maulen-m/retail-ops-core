from core.ops.fitpack_coordination import (
    EXCLUSION_LOG_LINE,
    filter_storeb_store_codes,
    is_storeb_store,
    load_storeb_packing_excluded,
)


def test_storeb_exclusion_defaults_off_when_config_absent(tmp_path):
    warnings: list[str] = []

    assert load_storeb_packing_excluded(tmp_path / "missing.yaml", warn=warnings.append) is False
    assert warnings == []


def test_storeb_exclusion_accepts_explicit_true_and_false(tmp_path):
    config_path = tmp_path / "fitpack_coordination.yaml"

    config_path.write_text("storeb_packing_excluded: true\n", encoding="utf-8")
    assert load_storeb_packing_excluded(config_path) is True

    config_path.write_text("storeb_packing_excluded: false\n", encoding="utf-8")
    assert load_storeb_packing_excluded(config_path) is False


def test_storeb_exclusion_parse_error_fails_open_with_warning(tmp_path):
    config_path = tmp_path / "fitpack_coordination.yaml"
    config_path.write_text("storeb_packing_excluded: [\n", encoding="utf-8")
    warnings: list[str] = []

    assert load_storeb_packing_excluded(config_path, warn=warnings.append) is False
    assert any(EXCLUSION_LOG_LINE in warning for warning in warnings)
    assert any("NOT applied" in warning for warning in warnings)


def test_storeb_store_aliases_and_filter():
    warnings: list[str] = []

    assert is_storeb_store("STORE-B") is True
    assert is_storeb_store("STOREB") is True
    assert is_storeb_store("30000002_PP1") is True
    assert is_storeb_store("UNIVERSAL") is False
    assert filter_storeb_store_codes(
        ["STOREB", "UNIVERSAL", "ACMEWEAR"],
        enabled=True,
        warn=warnings.append,
        context="test scope",
    ) == ["UNIVERSAL", "ACMEWEAR"]
    assert any(EXCLUSION_LOG_LINE in warning for warning in warnings)
