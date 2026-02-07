from core.config.business_params import DEFAULT_FX_RATES as BUSINESS_DEFAULTS
from scripts.bootstrap_db import PARAMS as BOOTSTRAP_PARAMS
from scripts.seed_params import DEFAULT_FX_RATES as SEED_DEFAULTS


def test_seed_defaults_match_reconciled_policy():
    assert SEED_DEFAULTS["cny_kzt"] == 75.0
    assert SEED_DEFAULTS["usd_kzt"] == 520.0


def test_bootstrap_defaults_match_reconciled_policy():
    param_map = {(k, t): v for (k, t, v, _desc) in BOOTSTRAP_PARAMS}
    assert param_map[("CNY_KZT", None)] == 75
    assert param_map[("USD_KZT", None)] == 520


def test_runtime_defaults_align_across_paths():
    assert BUSINESS_DEFAULTS["cny_kzt"] == SEED_DEFAULTS["cny_kzt"]
    assert BUSINESS_DEFAULTS["usd_kzt"] == SEED_DEFAULTS["usd_kzt"]
