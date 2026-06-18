# Dark Relist Recovery Slope Contract

Gate: G-DARK-02

Purpose: measure organic recovery after OD-033 relists, without pretending a 30-day post-relist curve exists before relist execution.

## Checks

1. Dependency G-DARK-01 is GREEN.
2. Baseline order history can be read from production truth in read-only mode.
3. A relist start date exists.
4. At least 30 post-relist days are mature.
5. Measured post-relist order curve is published.

## Status Semantics

- GREEN: G-DARK-01 is green and a mature 30-day post-relist recovery curve exists.
- ARMED: baseline evidence exists, but relist has not happened, is blocked, or the 30-day window is not mature.
- RED: source truth cannot be read or the measured curve is malformed after maturity.

This report is read-only. It does not relist offers, upload prices, write stock, send messages, or mutate external systems.
