# Cashfloor Gate Contract

## Purpose
Protect capital by blocking decision-grade status when conservative projected cash falls below threshold.

## Entry Point
- `scripts/validate_cashfloor.py`

## Inputs
- `fact_cashflow_daily`
- `fact_cashflow_commitments`
- `config/cashflow_scenarios.yaml` (if present)
- fallback absolute floor: `500000` KZT

## Outputs
- `exports/daily/<YYYY-MM-DD>/cashfloor_gate.json`
- `exports/daily/<YYYY-MM-DD>/cashfloor_gate.md`

## Required JSON Fields
- `status` (`GREEN`/`RED`)
- `ok`
- `opex_monthly_kzt`
- `base_floor_kzt`
- `conservative_floor_kzt`
- `base_min_cash_kzt`
- `conservative_min_cash_kzt`
- `reason`

## Fail-Closed Rules
- Missing DB or missing commitment truth => RED.
- Conservative scenario below floor => RED.
- `--strict` must return non-zero when RED.
