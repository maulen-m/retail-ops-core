# Exchanger Email Parsing Reference

Scope: BTCChange24 + UAChanger Gmail notifications.
Purpose: map subject lines to internal statuses and extract normalized fields.

## Status mapping (by subject)

### BTCChange24
- **NEW** — `BTCChange24 - New exchange #<id> [Tether TRC20 -> WeChat]`
  - Meaning: order created
- **IN_PROCESS** — `BTCChange24 - In payout processing #<id> [Tether TRC20 -> WeChat]`
  - Meaning: exchanger is processing payout
- **COMPLETED** — `BTCChange24 - Success done #<id> [Tether TRC20 -> WeChat]`
  - Meaning: WeChat payout completed
- **CANCELLED** — `BTCChange24 - Order deleted #<id> [Tether TRC20 -> WeChat]`
  - Meaning: order cancelled/deleted

### UAChanger
- **NEW** — `Order for exchange <id>`
  - Meaning: order created
- **IN_PROCESS** — `Waiting for confirmation from merchant <id>`
  - Meaning: waiting for merchant confirmation / funds in transit
- **PAID** — `Paid order <id>`
  - Meaning: payment sent by us; awaiting completion
- **COMPLETED** — `Completed order <id>`
  - Meaning: payout completed
- **CANCELLED** — `Cancelled order <id>` / `Canceled order <id>`
  - Meaning: order cancelled

### Ignore (non‑order system emails)
- `User registration`
- `Ваш код двухфакторной аутентификации` (2FA)
- `Подтверждение emailадреса`

## Extracted fields
For each exchanger email, we normalize:
- `exchanger` — BTCChange24 / UAChanger
- `order_id` — numeric ID from subject/body
- `message_date` — email timestamp
- `status` — mapped from subject
- `direction` — e.g. `Tether TRC20 -> WeChat`
- `amount_usdt` — USDT given (float)
- `amount_cny` — CNY received (float)
- `rate_usdt_cny` — **derived** as `amount_cny / amount_usdt` (ignore email FX)
- `deposit_address` — TRC20 address
- `receiver_account` — WeChat ID (if present)
- `subject` — original subject line

## FX derivation rule
Use **actual received CNY** ("You get" / payout amount) divided by USDT sent:

```
USDT/CNY = amount_cny / amount_usdt
```

We intentionally ignore the rate printed in the email because it excludes commission.

## Notes
- Multiple emails per order (NEW → IN_PROCESS → COMPLETED). We upsert by `exchanger_order_id`.
- If deposit address is missing in UAChanger emails, matching falls back to amount + date window.
