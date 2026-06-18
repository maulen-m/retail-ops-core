# LINE51 Markdown Guard Contract

Gate: `G-LIQ-04`

Purpose: keep `CL_OC_MEN_LINE51_WHITE` out of generic liquidation markdown automation unless the count-gated evidence and owner-approved fixed-clearance boundary are explicit.

The guard is local/read-only. It validates:

- `G-LIQ-01` still classifies LINE51 as `A_COUNT_GATED`.
- LINE51 is not active in the generic liquidation lead-store map.
- The count extension evidence proves `CL_OC_MEN_LINE51_WHITE_S = 82`.
- Any LINE51 KO clearance decision is temporary, fixed manual price only, and forbids Repricer dumping or automated price writes.

This contract does not authorize Kaspi merchant writes, Repricer writes, stock writes, production DB writes, workbook writes, Google Sheet writes, Telegram sends, customer/operator messages, LaunchAgent changes, or paid marketing.
