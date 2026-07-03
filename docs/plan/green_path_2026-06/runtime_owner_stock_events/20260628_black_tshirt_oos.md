# Owner Stock Event: Black T-Shirt OOS

Recorded at: 2026-06-29 01:00 +05
Effective event time: 2026-06-28 23:45 +05
Source: owner chat instruction in the Web_automation Repricer strategy convergence thread.

## Decision

Owner confirmed that black T-shirt warehouse stock is out of stock now.

Affected stock family:

- `CL_NEW-CLO_MEN_T-SHIRT_BLACK`

Temporary stock materialization should treat the active size pools for this
family as `0` ready-to-sell units until a newer owner-approved count supersedes
this event.

This is a stock-authority event, not an aggressive-pricing event. Marketplace
offers covered by this event should be protected by stoploss pricing rather than
lowered under high-stock 5% landed-COGS selloff rules.
