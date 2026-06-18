# ACMEWEAR Parent/Child/RUSH31 Strategy Ingest - Split-Repo Dry-Run Plan

Created: 2026-05-28

Gate: PLAN_READY_REVIEW_ONLY

## Objective

Ingest the two Strategy Expert answers from the Web_automation Oracle pack into Autonomous_business as review-only strategy evidence, then prepare a split-repo implementation route.

Autonomous_business owns the business decision layer:

- cash runway
- SHR/Sahar payable and payment-proof ingestion
- stock, COGS, inventory capital, and PO guardrails
- final-sale truth and order-truth distinctions
- owner-only approval gates

Web_automation owns only the technical marketplace/ad/offer dry-run mechanics:

- Kaspi Marketing read-only and dry-run command planning
- offer-state/pricelist dry-run planning
- campaign/bid/cap/price dry-run diffs
- route monitoring command planning

No live writes are authorized by this plan.

## Source Inputs

Oracle pack root:

`~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18`

Primary request:

`~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md`

Strategy answer part 1:

`~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/Answer_part_1/28.05.2026_15_24_15.md`

Strategy answer part 2:

`~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/Answer/part_2/Strategy_expert_28.05.2026_18_25_06.md`

Pack manifest:

`~/Docs/Oracle/Web_automation/2026-05-27/20260527_220139_ACMEWEAR_PARENT_CHILD_RUSH31_REEVAL_V2_STRATEGY_FLAT18/00_MAX20_MANIFEST.md`

## Source Hashes

| Source | SHA-256 |
| --- | --- |
| `28.05.2026_15_24_15.md` | `7335d4bfcbb4a44dd55234b7d611ad2600a469b01db132b59a8c2f56953c7e57` |
| `Strategy_expert_28.05.2026_18_25_06.md` | `850cab4940c9fcf140ebd7fc2b90ab548377d882456ed5e1e2d76968832f0f99` |
| `01_MAIN_ORACLE_CONTEXT_AND_REQUEST.md` | `04cc3f9080366d13f0354b725c8cd3b586c813d489ab6e77041dfe92736cf656` |
| `00_MAX20_MANIFEST.md` | `739aef7a124c4315b7c624e995108a6539949b08aa42e34fe1db748c8879c136` |

## Controlling Conclusions To Ingest

1. Pay or formally handle SHR/Sahar first. Strategy cannot assume a new PO before the current payable is handled.
2. Full V3 default reorder is not cash-fundable after SHR unless supplier terms, financing, or fresh cash receipts change the runway.
3. Line61 is a constrained winner; protect upper sizes and avoid broad reopening.
4. LINE51 is trapped inventory capital; use controlled sell-through, especially after fixing 4XL out-of-stock sale-state conflicts.
5. LINE31/RUSH31 is a discovery test only; do not fund LINE31 PO1B from current cash without screenshot-backed timing evidence and explicit owner override.
6. Direct CRM paid buyouts are cash truth. Scheduled deliveries are not revenue.
7. WebUI status-change rows are final marketplace sale truth. Kaspi order intake is demand truth, not final sale truth.
8. Local direct-funnel state is useful context, but it must not be blindly imported into Kaspi price/bid decisions.

## Split-Repo Ownership

| Domain | Owner repo | Current lane action |
| --- | --- | --- |
| Cash runway and SHR payable | Autonomous_business | Read-only preflight and review packet only |
| Inventory/COGS/stockout risk | Autonomous_business | Read-only preflight and strategy gate matrix only |
| PO/supplier terms and payment proof | Autonomous_business | Draft decision gates only; no supplier message or payment |
| Kaspi offer-state and campaign mechanics | Web_automation | Dry-run command plan only under current approval |
| Meta/local ad restart | Web_automation plus local CRM context | Preflight plan only; no Meta/CRM writes |
| Monitoring cadence | Autonomous_business orchestrator | Schedule specification only; no scheduler mutation |

## Implementation Phases

### Phase 0 - Source Integrity And Strategy Ingest

Goal: prove the two expert answers and V2 source pack are available, hashed, and correctly classified.

Outputs:

- source hash manifest
- strategy conclusion matrix
- decision ownership matrix
- closeout gate

Allowed gate: `GREEN` only if all source hashes match and no repo boundary conflict is found.

### Phase 1 - Read-Only Business Preflight

Goal: compare the strategy against current local AB evidence without applying anything.

Checks:

- latest cash snapshot and SHR payable source presence
- latest inventory capital workbook or summary presence
- Line61 upper-size guardrails
- LINE51 4XL owner-truth conflict status as a blocker, not as a write
- LINE31 PO1B timing-risk source state

Outputs:

- AB cash/stock/PO preflight table
- owner-only action checklist
- retained blockers

### Phase 2 - Web_automation Dry-Run Handoff

Goal: convert the strategy into Web_automation dry-run requirements, not live actions.

Do not execute commands that write `runs/`, configs, schedulers, browser sessions, Kaspi/API/WebUI/Meta/CRM, or external surfaces under the current approval.

Outputs:

- exact dry-run command plan for later owner-approved Web_automation lane
- expected diff surfaces
- rollback/receipt requirements for future apply lane
- values requiring exact owner approval before any apply

### Phase 3 - Approval Phrase And CodeCaptain Packet Readiness

Goal: produce a compact owner decision packet and exact approval phrases for the next live/dry-run stage.

Outputs:

- next approval phrase set
- route-by-route gate table
- CodeCaptain review questions if any remain disputed
- launch order for follow-up agents

## Stoplines

Stop and mark `YELLOW` if:

- a source file moved or hash differs;
- current cash, stock, or campaign state cannot be verified read-only;
- the dry-run route would require Web_automation repo writes under current approval;
- any action would change a live platform, scheduler, DB, workbook, source pointer, cash, PO, stock, price, bid, budget, campaign, supplier message, or owner publication.

Mark `RED` if:

- any protected surface is mutated;
- an agent sends a supplier/platform/customer message;
- an agent executes a live price/bid/budget/campaign/offer/state/payment/PO/stock change;
- an agent writes to Web_automation despite the current no-Web_automation-write boundary.

## Next Execution Topology

Root agents can run in parallel:

- Agent 1: AB source integrity and business preflight.
- Agent 2: Web_automation dry-run route plan.
- Agent 3: owner gate and approval phrase synthesis.

Agent 4 runs only after Agents 1-3 close out:

- Agent 4: final split-repo review packet and next-launch bundle.

Shared handoff folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-28_acmewear_parent_child_rush31_strategy_dryrun`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/ACMEWEAR_PARENT_CHILD_RUSH31_STRATEGY_DRYRUN_20260528_STARTERS`
