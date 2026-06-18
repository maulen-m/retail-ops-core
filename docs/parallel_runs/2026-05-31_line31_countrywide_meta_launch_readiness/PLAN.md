# LINE31 Countrywide Meta Launch-Readiness Plan

Created: 2026-05-31 21:06 +05

Gate: ROOT_READY_NO_LIVE_WRITES

## Objective

Turn the Strategy Expert LINE31 countrywide Meta tracking answer and asset pack into an internal, repo-tailored launch-readiness implementation wave.

This wave prepares local scaffold, tracking QA, attribution policy, daily bridge reporting, and launch gates. It does not approve or perform a Meta launch, website deploy, internal Kaspi isolation, campaign mutation, price change, stock change, cash movement, supplier payment, PO commitment, or production apply.

## Source Inputs

- Strategy answer: `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/Strategy_expert_31.05.2026_20_33_01.md`
- Unpacked expert asset folder: `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531`
- Expert zip: `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531.zip`
- Cashflow cockpit workbook recorded by owner as ready to work on: `~/Docs/Oracle/Autonomous_business/2026-05-30/131112_TASK-000_cashflow-po-decision-workbook-external-eval-20260530/Answer/assets_of_answer/ACMEWEAR_cashflow_inventory_po_decision_cockpit_20260530.xlsx`

## Current Authorization Boundary

Allowed in this wave:

- read-only source inspection across `Autonomous_business`, `Facebook_ads`, `acmewear_web_v2`, and `Web_automation`;
- repo-local docs/scripts/tests/config additions that support dry-run launch-readiness only;
- local evidence generation, manifests, review packets, and closeouts;
- read-only live freshness fetches where existing repo methods and credentials already support them;
- tmux-orchestrated execution agents with closeout files as the source of truth.

Not authorized in this wave:

- production DB writes or workbook writes;
- scheduler, LaunchAgent, cron, source-pointer, website deploy, or Cloudflare deploy changes;
- Meta/Kaspi/WebUI/API/CRM mutations;
- campaign bid, budget, state, creative, ad set, audience, promo, or objective changes;
- price, stock, offer-state, cash, supplier, payment, PO, owner-publication, or dashboard-publication actions;
- internal LINE31 Kaspi campaign or seller-bonus isolation.

Hard owner directive:

- LINE31 internal Kaspi marketing and seller bonus stay ON until the owner explicitly declares LINE31 creative videos complete and separately approves exact live changes.

## Truth Model

- Meta/Facebook Ads owns traffic truth only.
- `acmewear.pro` owns first-party behavior and clickout truth only.
- `/go/:color` server `KaspiRedirect` is the deepest reliable website-side conversion signal.
- Kaspi API/WebUI/ArchiveOrders own order and lifecycle truth.
- Website events must not be called purchase truth.
- While LINE31 internal Kaspi marketing remains active, LINE31 orders during a Meta test are directional attribution only.

## Implementation Shape

Use a five-agent wave:

| Agent | Repo | Role | Parallelism |
| --- | --- | --- | --- |
| 1 | `Facebook_ads` | LINE31 Meta scaffold, UTMs, creative placeholders, monitoring rules | root parallel |
| 2 | `acmewear_web_v2` | landing route and tracking QA, no deploy | root parallel |
| 3 | `Web_automation` | read-only LINE31 internal Kaspi context and attribution-noise report | root parallel |
| 4 | `Autonomous_business` | LINE31 daily bridge report for cash, stock, redirects, and order truth | root parallel |
| 5 | `Autonomous_business` | synthesis readiness packet after Agents 1-4 | after 1-4 |

## Launch Gates

Use these gates in the final readiness packet:

- `Scaffold GREEN`: campaign scaffold, UTMs, creative placeholders, budget/stop rules, and approval phrases are locally ready.
- `Tracking GREEN`: PageView, ViewContent, ColorSelect, QualifiedVisit, KaspiClick, HighIntentKaspiClick, and server `KaspiRedirect` are verified without fake ecommerce events.
- `Creative GREEN`: owner has declared final creative videos complete and mapped assets to slots.
- `Cash/Inventory GREEN`: cash cockpit, LINE31 sellable stock, reserve treatment, and spend ceiling are current.
- `Launch GREEN`: all prior gates are green and the owner provides exact Meta publish approval.

## Stoplines

- Stop if any agent finds a live-write path in this wave.
- Stop if any route would bypass `/go/:color`.
- Stop if fake ecommerce events are present or proposed.
- Stop if LINE31 internal Kaspi isolation is attempted before creative-ready declaration.
- Stop if cash/stock freshness cannot be proven; report `YELLOW`, not `GREEN`.

## Required Closeout Standard

Every agent closeout must contain a standalone machine-readable line:

`Gate: GREEN`

or:

`Gate: YELLOW`

or:

`Gate: RED`

`GREEN` means the assigned readiness lane is complete and validated under the no-live-write boundary. `YELLOW` means useful evidence was produced but launch-readiness blockers remain. `RED` means boundary violation, unsafe action, or unreliable evidence.
