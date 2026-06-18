# Owner Dashboard Cadence Contract

Gate: `G-MET-02`

The owner dashboard cadence bundle is the stable reporting surface for the Phase 4 owner metric loop.

Cadences:

- daily: automation failures, cash confidence, sales/profit coverage, ads CRR, exception exposure;
- weekly: frozen capital, release velocity, stock confidence, comeback/return QC;
- monthly: PPCH v1, forecast review, PO review.

The bundle is local/read-only. It discovers the latest approved evidence artifacts, records their status, freshness, and source path, and publishes a JSON/Markdown/CSV packet. It may publish `ARMED` when the bundle exists but a 7-day delivery history or required measured inputs are still missing. It must not mark `GREEN` until all three cadences have current passing evidence and the cadence history has matured.

Missing cadence items, upstream `ARMED` metric inputs, or not-yet-mature history stay visible as blockers. They are not filled with invented facts.

This contract does not authorize production DB writes, workbook writes, Google Sheet writes, Telegram sends, Kaspi merchant/UI/API writes, Repricer writes, price uploads, stock writes, customer/operator-message writes, LaunchAgent changes, or external writes.
