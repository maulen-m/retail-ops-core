Phase N1 — Operational telemetry “trust” loop (read-only)

Goal: 72h of clean hourly telemetry for Acmewear + Universal, with coverage checks.

Deliverables:

scripts/kaspi_ads_healthcheck.py

checks freshness of latest snapshot per store,

checks reconciliation drift within tolerance,

exits non-zero on failure (so you can wire monitoring later).

scripts/kaspi_ads_campaign_coverage_report.py

dumps campaigns/products seen over last 24h,

flags “expected but missing” vs last known campaign inventory JSON.

Acceptance gates:

No missing hours > 2h.

Reconciliation drift stable (no trend worse after canary later).

Coverage report matches expected campaigns for both stores (esp. Line52 campaigns in Universal).

231138_TASK-ADS-WT-V1_universal…

Owners:

Ads_agent: implement scripts + tests.

Human: keep job running; review logs.

Phase N2 — Profit realism calibration (still read-only)

Goal: Improve decision quality before touching bids.

Deliverables:

config/kaspi_ads_cost_adjustments.yaml

discount schedule (e.g., LINE61 30% discount until <date>),

optional per-campaign spend multipliers.

Extend scripts/kaspi_ads_elasticity.py to apply “effective_cost” and output both:

raw spend ROIC

effective spend ROIC (after discount)

Acceptance gates:

Report clearly shows both raw and effective metrics.

No silent fallbacks; every override must be logged in report.

Owners:

Ads_analytics_agent.

Phase N3 — Human-validated bid discovery (one-time)

Goal: Make live write/rollback “real”, not theoretical.

Deliverables:

A real discovery capture session (per store if needed), following the operator steps:

open campaign product page,

manually change ONE bid,

capture request,

save sanitized payload (no cookies/tokens).

231138_TASK-ADS-WT-V1_universal…

Owners:

Human (required) + agent help for capturing data.

Phase N4 — LINE61 live canary (single SKU)

Goal: Find sweet spot safely using the already-defined canary schedule and rollback.

Use the existing operator commands (02:00 reduce; 07:00 restore; emergency rollback).

215658_TASK-ADS-WT-V1_real-worl…

Stop conditions are already explicit — keep them strict. 

215658_TASK-ADS-WT-V1_real-worl…

Owners:

Human executes.

Ads_agent monitors DB/log outputs.

Phase N5 — Expand to Universal Line52 (after LINE61 canary success)

Goal: Run the same loop for Line52 campaigns discovered in Universal.

Deliverables:

Add Line52 campaign IDs to analysis runs (elasticity + daily brief).

Later: allowlist Line52 for bid manager in a second canary (still one campaign at a time).

Owners:

Ads_agent + Human.

Phase N6 — Promotion to main repo (fast + safe)

Follow the already-defined promotion method:

create a separate “promotion worktree”,

cherry-pick phase commits (no runtime db files),

run full gates,

merge with defaults OFF (dry_run true, ENABLE_KASPI_ADS_WRITE unset, ALLOW_PROD_ADS_DB unset).

231138_TASK-ADS-WT-V1_universal…

Owner:

Promotion_agent.

ASCII roadmap tree (parallel + owners)
ADS SYSTEM REAL-WORLD ACTIVATION (WT ads_v1)  [Goal: LINE61 sweet spot + Line52 scale]

├─ N1 Telemetry Trust Loop (72h, READ-ONLY)  [Ads_agent + Human]
│  ├─ Healthcheck (freshness + reconciliation drift)
│  ├─ Coverage report (campaign/product completeness)
│  └─ Fix Acmewear "rows=1" anomaly if incomplete ingestion
│
├─ N2 Profit Realism Calibration (READ-ONLY) [Ads_analytics_agent]
│  ├─ LINE61 discount/effective-cost policy
│  ├─ Margin overrides for key SKUs (until sales truth stabilizes)
│  └─ Daily "decision brief" report (CSV/MD)
│
├─ N3 Bid Write Discovery (ONE-TIME HUMAN)   [Human + Ads_agent]
│  └─ Manual bid edit → capture network req → sanitize payload
│
├─ N4 LINE61 Canary (WRITE, tightly gated)   [Human + Ads_agent]
│  ├─ 02:00 reduce (0.5) / 07:00 restore (1.0)
│  ├─ Stop conditions + rollback-last-good
│  └─ Post-mortem: was spend→orders→profit improved?
│
├─ N5 Universal Line52 Activation           [Ads_agent + Human]
│  ├─ Elasticity runs for campaign 2566809 / 2572387
│  └─ One-campaign canary if LINE61 proven
│
└─ N6 Promote to MAIN repo (defaults OFF)    [Promotion_agent]
   ├─ promotion worktree
   ├─ cherry-pick phase commits only
   └─ gates + merge (no ops changes auto-enabled)