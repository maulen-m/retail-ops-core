# LAUNCH ORDER — Stock/Cost Truth Repair Second Pass

Run pack:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass`

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass`

## Parallel First Pass

Agent B and Agent C can run in parallel.

Agent B:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PROMPT_AGENT_B.md.
```

Agent C:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PROMPT_AGENT_C.md.
```

## Execution After Reports

Agent A starts only after:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_b_report.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`

Agent A:

```text
Read the repo bootstrap context, the B/C reports, and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PROMPT_AGENT_A.md.
```

## Human Note

This run exists to fix the repo-side truth surface before a second external pass. Do not ask Agent A to jump straight into a fresh Oracle/expert rerun before the landed-cost surface and quarantine posture are clarified.
