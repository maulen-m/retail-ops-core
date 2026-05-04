# Launch Order

Starter folder:

- `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts`

Launch in parallel:

1. Agent 1, writer/execution:
   - `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts/01_AGENT_1__RESOLVER_HARDENING_WRITER__PARALLEL.md`
2. Agent 2, read-only LINE31 identity audit:
   - `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts/02_AGENT_2__LINE31_IDENTITY_AUDIT__READONLY_PARALLEL.md`

Agent 1 may finish the resolver/test fix without waiting for Agent 2, but the orchestrator should review both closeouts before accepting the LINE31-wide prevention claim.

Short copy-paste starter prompts:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts/01_AGENT_1__RESOLVER_HARDENING_WRITER__PARALLEL.md
```

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-05-04_line31-name-core-resolver-hardening/starter_prompts/02_AGENT_2__LINE31_IDENTITY_AUDIT__READONLY_PARALLEL.md
```
