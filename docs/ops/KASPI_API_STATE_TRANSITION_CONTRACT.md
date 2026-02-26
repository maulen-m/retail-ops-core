# Kaspi API State Transition Contract

## Purpose
Prevent false-green write-like API outcomes. HTTP transport success is insufficient.

## Rule (Hard)
A write-like action (`assemble`, `ship`, `cancel`) is successful only when:
1. HTTP call succeeded, and
2. Post-action state transition is confirmed.

If condition (2) is missing, strict validation must fail.

## Required Event Fields
- `order_code`
- `action`
- `http_success` (bool)
- `confirmed` (bool)
- `pre_state`
- `post_state`

## Failure Cases
- `http_success=true` and `confirmed=false` (HTTP-only success) => FAIL.
- `confirmed=true` and `post_state` unchanged/missing => FAIL.
- `confirmed=true` and `http_success=false` => FAIL.

## Validator
```bash
python3 scripts/validate_kaspi_state_transition.py \
  --input <events.json> \
  --as-of <YYYY-MM-DD> \
  --strict
```

Outputs:
- `exports/exceptions/<YYYY-MM-DD>/api_state_transition_exceptions.json`
- `exports/exceptions/<YYYY-MM-DD>/api_state_transition_exceptions.md`

## Owning Tests
- `tests/test_kaspi_state_transition_contract.py`
- `tests/test_validate_kaspi_api.py`
- `tests/test_ship_orders_api.py`
