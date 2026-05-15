# C3 Source Truth Read-Only Wave Plan

Status: active starter pack for Option B, Wave 1 read-only agents.

Repo: `~/Docs/Autonomous_business`

Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave`

## Goal

Prepare C3 full completion without unsafe writes by running six independent read-only agents first. Their closeouts will define the exact implementation contracts for the later write-capable C3 DB registry and daily-runner agents.

## Authority Inputs

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/ops/OPERATIONAL_DECISION_POLICY_V1.md`
- `~/Docs/Autonomous_business/config/operational_decision_policy.yaml`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_operational-stock-truth-system/OWNER_QA_OPTION_C_INPUTS_20260503_203849_ALMT.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-03_c3-source-truth-readonly-wave/OWNER_QA_C3_SUPPLIER_LINE31_CONTEXT_20260503_210720_ALMT.md`
- `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/00_AB_KASPI_MARKETING_DIRECT_API_HANDOFF.md`
- `~/Docs/Web_automation/Docs/agent_handoffs/AUTONOMOUS_BUSINESS_KASPI_MARKETING_DIRECT_API_HANDOFF_20260503/acmewear_child_bundle_campaign_registry.csv`

## Source Boundary

Autonomous_business owns operational truth, normalized events, policy gates, daily owner briefs, and decision-grade publication state.

External sources remain owners of their domains:

- PO inquiry generation: `~/Cowork/Projects/E-commerce`
- Supplier communication/catalog/negotiation: `~/Cowork/Projects/Sourcing-Research`
- Commerce memory: `~/Docs/Oracle/knowledge-workspace/wikis/commerce-ops-wiki`
- Business memory: `~/Docs/Oracle/knowledge-workspace/wikis/business-wiki`
- Finance executive memory: `~/Docs/Oracle/knowledge-workspace/wikis/finance-exec-wiki`
- Marketing workflow evidence: `~/Docs/Web_automation`
- External ads workspace: `~/Docs/Business_3/Facebook_ads`

AB should store source pointers, hashes/lineage where useful, freshness, event normalization, and gate decisions. It should not copy all raw supplier/chat/wiki state into AB.

## Wave 1 Read-Only Agents

Launch these in parallel:

1. Agent 1: C3 policy registry and authority model.
2. Agent 2: stock, order status, returns, QC, SKU merge, and snapshot rebuild truth.
3. Agent 3: PO, inbound, supplier routes, ARC LINE31 PO1A, shortage dispute, cargo handoff truth.
4. Agent 4: ads and marketing DirectAPI truth, including the Web_automation handoff.
5. Agent 5: cashflow, bank balances, supplier debt, cargo payments, and reserve gates.
6. Agent 6: wiki context synthesis and cross-repo memory routing.

Allowed writes for Wave 1:

- Each agent may write only its assigned closeout file in `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_c3-source-truth-readonly-wave`.

Not allowed in Wave 1:

- no repo file edits;
- no DB writes;
- no migrations;
- no `.claude/*` edits;
- no `.env` reads unless specifically necessary to confirm variable names, and never copy secret values;
- no live merchant, ads, supplier, payment, or API writes;
- no supplier messages;
- no browser-login automation;
- no green publication claims.

## Sequential C3 Agents

Blocked until Wave 1 closeouts are reviewed:

7. Agent 7: write-capable effective-dated DB policy registry and exception queue.
8. Agent 8: write-capable daily runner, owner brief, and publication gate integration.

## Wave 1 Acceptance Gate

Wave 1 is complete when all six closeouts exist and each has:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- sources read with absolute paths;
- source gaps and stale/unknown facts;
- exact implementation recommendations for Agent 7/8;
- no secret leakage;
- explicit confirmation that no AB repo files, DB rows, external systems, or Web_automation files were modified.

GREEN in Wave 1 means read-only analysis is complete. It does not mean C3 implementation or business publication is green.
