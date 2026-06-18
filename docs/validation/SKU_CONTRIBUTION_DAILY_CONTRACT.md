# Daily SKU Contribution Contract

Gate: `G-MET-03`

The daily SKU contribution report publishes the measured portion of net contribution by date, store, and SKU from read-only truth surfaces.

Known-input formula:

`profit_kzt - mapped_ads_cost_kzt`

The full target formula remains:

`price - commission - delivery - ads_allocated - expected_return_loss - landed_cogs - handling`

If expected return loss or handling cost sources are not measured, the report is `ARMED`, not `GREEN`. Missing inputs stay visible as measurement blockers rather than being filled with invented values.

This contract does not authorize production DB writes, workbook writes, Google Sheet writes, Telegram sends, Kaspi merchant/UI/API writes, Repricer writes, price uploads, stock writes, customer/operator-message writes, LaunchAgent changes, or external writes.
