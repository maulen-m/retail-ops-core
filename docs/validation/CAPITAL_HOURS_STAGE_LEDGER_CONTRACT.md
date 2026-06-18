# Capital-Hours Stage Ledger Contract

Gate: `G-MET-04`

The capital-hours stage report publishes the cash-timing-drag lens for capital by lifecycle stage.

Target stages:

- `paid_supplier`
- `inbound`
- `on_hand`
- `on_delivery`
- `returned`
- `quarantine`
- `receivable`

The weekly report is local/read-only. It may compute measured stage-hours from `fact_cashflow_daily` where stage columns already exist, but it must mark the gate `ARMED` until all target stages have measured sources and return/QC facts are present. In D1 Kaspi Pay mode, receivable stage-hours are expected to be zero unless an explicit model-ledger diagnostic is selected.

Missing stage sources are blockers, not zeroes. A stage with no measured source must never be treated as solved by a derived placeholder.

This contract does not authorize production DB writes, workbook writes, Google Sheet writes, Telegram sends, Kaspi merchant/UI/API writes, Repricer writes, price uploads, stock writes, customer/operator-message writes, LaunchAgent changes, or external writes.
