# Launch Order

Run only Agent A for this task. Do not launch parallel DB-writing agents.

## Paste To Agent A

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/parallel_runs/2026-04-24_line31-po1-shortage-correction/PROMPT_AGENT_A.md.
```

## Why Single-Agent

This task may mutate `db/app.db` or create correction artifacts that feed current stock truth. One writer keeps the receipt correction, tests, DB backup, and rollback path coherent.
