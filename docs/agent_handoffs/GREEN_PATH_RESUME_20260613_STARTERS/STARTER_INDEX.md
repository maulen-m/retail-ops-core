# Green Path Resume 20260613 Starter Index

Workflow: resume the Path-to-100%-GREEN program at the Phase-1/2 boundary after the waybill repair.

Canonical plan inputs:

- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
- `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`

Shared closeout folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/`

Launch order:

1. Root wave in parallel: Agents 1, 2, 3, 4.
2. Orchestrator reads all root closeouts.
3. If root gates are GREEN/PASS, send Agent 5 (`PKT-LINES`) manually.
4. If root gates are YELLOW but explicitly classified by the orchestrator as sequencing/scope corrections rather than blockers, patch the dependent starter with those corrections before sending it.
5. Agents 6, 7, 8, 9, and 10 are read-only apply-readiness prep lanes. They may run in parallel before Agent 5 completes because they write only assigned closeouts and do not hold DB, WA, workbook, LaunchAgent, browser, or external-system write leases.

Root closeout review on 2026-06-13:

- Agent 1: `Gate: GREEN`; preservation, branches, paused daily ops, DB guard, and waybill closeout confirmed.
- Agent 2: `Gate: YELLOW`; current `PKT-LINES` counts and entrypoint corrected. Not a blocker to Agent 5 after starter patch.
- Agent 3: `Gate: YELLOW`; stock/residual stoplines are later-lane sequencing issues. Not a blocker to Agent 5.
- Agent 4: `Gate: YELLOW`; WA/ads dirty overlap affects later ads/pricing lanes. Not a blocker to Agent 5.

Agent 5 was patched after root review to use current counts, `PYTHONPATH=.`, and the direct `scripts/enrich_kaspi_orders.py` writer only.
Agent 5 was patched again before launch to include the governed `order_status_event` materializer and exact validator command forms.

Prep wave roles:

- Agent 6: `PKT-FX` apply readiness.
- Agent 7: `PKT-CASH` and `PKT-RESID` apply readiness.
- Agent 8: `PKT-STOCK` apply readiness.
- Agent 9: Kaspi-only `PKT-ADS` apply readiness.
- Agent 10: `PKT-PROFIT`, `PKT-QUAR`, and `PKT-RETURNS` readiness.

Do not auto-advance to Agent 5 without closeout review.
