# LINE31 48h Partial Scale Preflight Plan

Created: `2026-06-06`

## Goal

Integrate the 48h external expert answer into a concrete, evidence-gated execution path for LINE31 countrywide Meta scale.

Decision target:
- Prepare, but do not execute, a controlled budget-only scale from current LINE31 countrywide ad set budget to about `25,000 KZT/day`.
- Exact target if approved later: ad set `120245481997290641`, `daily_budget=5155` Meta minor units, using `485 KZT/USD`.

External expert answer:
- `~/Docs/Oracle/oracle_packs/Instagram_funnel_packs/line31_countrywide_48h_second_take_scale_traceability_oracle_pack__20260606_1221_GMT5/Answer/Strategy_expert_06.06.2026_13_11_13.md`

## Scope And Boundaries

Allowed in this wave:
- Read-only Meta API state/insights checks.
- Read-only ACMEWEAR Kaspi live-order sync.
- Read-only / local-only LINE31 stock, cash, and PO guard inspection.
- Read-only Cloudflare / log-backed website traceability checks.
- Local evidence packets, manifests, closeouts, and approval phrase draft.

Not allowed in this wave:
- Meta campaign, ad set, ad, creative, budget, bid, targeting, status, or placement writes.
- Website deploys or code changes.
- Kaspi/WebUI/API mutations.
- Production DB/workbook writes.
- Scheduler/source-pointer changes.
- Stock, price, cash, supplier, PO, owner-publication, or internal Kaspi campaign changes.

## Gate Logic

Use truth lanes separately:
- Meta = traffic and object-state truth.
- acmewear.pro = first-party website and clickout truth.
- Kaspi API = live order truth.
- Owner-confirmed attribution = contextual truth only.
- Autonomous_business LINE31 packet = stock/cash/product-truth guardrail context.

25k approval preparation can be `GREEN` only if:
- Current Meta objects match expected campaign/adset/ad IDs and remain `ACTIVE`.
- Current ad set budget remains `3093` before any proposed change.
- Same-day LINE31 order refresh does not invalidate the `7` contextual order signal and shows no abnormal cancellation/return spike.
- LINE31 sellable stock and Starry Black route stock remain safe for a 48h test.
- Cash/PO guard has no known adverse owner/current-source blocker.
- Website route is not broken; website analytics may remain `YELLOW`, but not `RED`.

If website analytics remain incomplete but all other gates are acceptable, final gate should be `YELLOW_25K_APPROVAL_READY_WITH_TRACKING_CAVEAT`, not false `GREEN`.

30k+, 50k, LINE31 Astana local, men countrywide, and new creative exploration cell remain blocked until website traceability is `GREEN` or stable `live_logbacked`, and API factory/create path is green or bounded manual fallback is explicitly approved.

## Agent Wave

Parallel root agents:
- Agent 1: Meta current-state and metrics preflight in Facebook_ads.
- Agent 2: ACMEWEAR LINE31 live order truth refresh in Facebook_ads.
- Agent 3: LINE31 stock/cash/PO guard refresh in Autonomous_business.
- Agent 4: website traceability and API-factory no-write readiness in Facebook_ads.

After Agents 1-4:
- Agent 5: synthesis, evidence lock, exact approval phrase, rollback plan.

## Expected Output

Primary starter folder:
- `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_48H_PARTIAL_SCALE_PREFLIGHT_20260606_STARTERS`

Closeout folder:
- `~/Docs/Autonomous_business_agent_handoffs/2026-06-06_line31_48h_partial_scale_preflight`

Final synthesis must include:
- Standalone `Gate: <GREEN/YELLOW/RED>` line.
- Evidence paths and SHA256 locks.
- Exact proposed owner approval phrase for `daily_budget=5155`.
- Rollback instruction to restore `daily_budget=3093` or pause exact LINE31 objects if post-scale gates fail.
- Explicit note that no live write was performed.
