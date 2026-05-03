# LAUNCH ORDER — Returns/Cancel Quarantine Truth

Run pack:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth`

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth`

## Parallel First Pass

Agent B and Agent C can run in parallel.

Agent B:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PROMPT_AGENT_B.md.
```

Agent C:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PROMPT_AGENT_C.md.
```

## Execution After Reports

Agent A starts only after:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_b_report.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_c_report.md`

Agent A:

```text
Read the repo bootstrap context, the B/C reports, and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth/PROMPT_AGENT_A.md.
```

## Human Note

Employee physical QC/recount is intentionally deferred. Agents must create the queue and truth model now, but must not mark returned items as active stock until human QC feedback is later provided.
