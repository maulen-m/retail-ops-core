# Exception Exposure Metric

`G-QUAR-04` publishes a daily exception age and KZT exposure metric from the
C3 `exception_queue`. The metric is a control surface, not an exception
resolver: open exceptions remain open until their own governing lane closes
them.

## Source

- Production source: `db/app.db`.
- Required table: `exception_queue`.
- Optional valuation tables: `dim_sku` and `dim_sku_size`.
- Included statuses: `OPEN`, `PENDING`, and `BLOCKED`.

The publisher must read the DB only. It must not update exception rows, stock,
cash, workbook state, Google Sheets, Telegram, Kaspi, pricing, or LaunchAgents.

## Formula

For each open exception:

- `age_days` is `as_of - created_at`, floored at zero.
- Direct KZT exposure wins if `evidence_json` contains a numeric exposure-like
  key such as `exposure_kzt`, `amount_kzt`, `goods_value_kzt`, or `cogs_line`.
- Otherwise the publisher may compute conservative goods exposure as
  `abs(quantity_at_risk) * dim_sku.cogs_kzt`.
- `quantity_at_risk` may come from evidence keys such as `physical_anchor_qty`,
  `raw_current_stock`, `quantity`, `qty`, or `units`.
- `exposure_age_kzt_days` is `exposure_kzt * age_days`.
- If either quantity or unit COGS is missing, the row stays visible as
  unvalued. The publisher must not invent missing KZT.

## Output Contract

The JSON artifact must include:

- `as_of`, `generated_at`, `status`, `ok`.
- `open_exception_count`.
- `total_exposure_kzt` and `total_exposure_age_kzt_days`.
- `total_quantity_at_risk` and `total_quantity_age_days`.
- `valued_exception_count` and `unvalued_exception_count`.
- grouped rollups by domain, severity, owner, and reason code.
- per-exception rows with valuation status.

The Markdown artifact must include one owner-readable daily line with open
count, valued count, KZT exposure, KZT-days exposure, quantity at risk, and
oldest age.

## Gate Use

`G-QUAR-04` is satisfied when the current-day artifact exists, is generated
from the DB, validates its schema, and exposes unvalued exceptions instead of
hiding them. Future automation may embed the same JSON in broader daily ops and
weekly owner review bundles.

