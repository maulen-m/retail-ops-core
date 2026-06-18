# PPCH v1 Metric Contract

Gate: `G-MET-01`

PPCH v1 is the owner headline metric once all headline inputs are measured. The published basis is denominator-consistent:

`720 * sum(net_contribution_kzt) / sum(capital_kzt_stage * hours_stage)`

This implementation uses `capitalized_rows_basis`: only positive-stock inventory rows with positive landed COGS enter the denominator. Positive stock rows without landed COGS are exposed as excluded rows rather than treated as free capital.

The report is local/read-only. It publishes:

- denominator snapshot date and age;
- capitalized-row denominator totals;
- month-to-latest-sales net contribution;
- PPCH v1 lower/mid/upper fields;
- headline readiness status.

When return QC has no measured event yet, the report is `ARMED` and keeps `v0.75` as the interim owner headline. It does not invent return-loss economics.

This contract does not authorize production DB writes, workbook writes, Google Sheet writes, Telegram sends, Kaspi merchant/UI/API writes, Repricer writes, price uploads, stock writes, customer/operator-message writes, LaunchAgent changes, or external writes.
