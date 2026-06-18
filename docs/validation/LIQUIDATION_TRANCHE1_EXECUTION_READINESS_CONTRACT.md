# Liquidation Tranche-1 Execution Readiness Contract

Gate: G-LIQ-02

Purpose: make liquidation tranche execution auditable before any markdown upload or live price change. The readiness report may create local candidate rows, but it must not claim execution until the governed upload/apply/readback evidence exists.

## Inputs

- Fresh G-LIQ-01 liquidation register and segment map.
- Green-path scoreboard/dashboard gate states.
- Header or executed tranche ledger: `config/validation/liquidation_tranche_ledger.csv`.
- Price/write safety gates.

## Checks

1. Dependency stack green: G-LIQ-01, G-PRICE-01, G-PRICE-02, G-WA-01.
2. Price stopline gates are not RED: G-PRICE-03 and G-PRICE-05.
3. Fresh liquidation register artifacts exist and expose at least one candidate row.
4. Local candidate row file contains the required non-execution planning fields.
5. Executed ledger rows, if any, contain all required execution fields.
6. Governed apply/readback evidence exists before GREEN.

## Status Semantics

- GREEN: dependencies are green, price stoplines are clear, executed ledger rows exist, required execution fields are complete, and governed apply/readback evidence is present.
- ARMED: local readiness/candidate evidence exists, but execution has not safely happened or one or more upstream gates are not green.
- RED: required source artifacts are missing, malformed, or no eligible candidates can be evaluated.

This report does not upload prices, write DB rows, edit workbooks, send messages, change LaunchAgents, create purchases, or mutate external systems.
