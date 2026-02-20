Primary sequential plan (one agent, in order)
Phase Q — Reality Bridge: PLAN PO vs REAL PO

Goal: dashboards stop being “intent”; become reconcilable “executed truth.”

Deliverables (verifiable):

PO dashboard labels and schemas explicitly separate:

PLAN recommendations (computed)

REAL POs (tracked lifecycle)

materialize_plan_po_to_real_po workflow:

creates REAL PO draft from a selected PLAN PO

stored in DB with stable IDs

“Arrival workflow”:

marks PO arrived/received

produces inventory receive events (idempotent)

Tests:

plan/real separation contract tests

idempotency (materialize twice == no double rows)

arrival produces expected inventory deltas

Phase R — Correctness gates + portfolio completeness

Goal: prevent “false confidence” when coverage is incomplete.

Deliverables:

scripts/validate_po_dashboard_invariants.py (hard fail) with invariants like those already sketched in earlier scope:

no silent fallbacks

sums match

per-store and portfolio completeness (tie into portfolio_active) 

Sales_Data_Model_V16

Add these checks into the contract suite runner so a clean clone can validate them. 

003952_TASK-367_phase-l-contrac…

Phase S — Schema + migration hygiene for autonomy
Goal: stop “if table exists” logic and make schema deterministic across agents/runs.

Deliverables:
Strict migration chain and schema validation so contract suite and EOD never rely on accidental local DB state.

Note: This aligns with the earlier “schema hygiene / always-green” intent—just extended to PO execution tables.