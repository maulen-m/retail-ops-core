LAUNCH_ORDER

Launch sequence

1. Agent B
   - read `PROMPT_AGENT_B.md`
   - publish first-pass findings to the shared handoff folder

2. Agent C
   - read `PROMPT_AGENT_C.md`
   - publish first-pass findings to the shared handoff folder

3. Agent A
   - start only after both analyst reports are published
   - read `PROMPT_AGENT_A.md`
   - execute the repair path in the order defined by `PLAN.md`

Owner reminder

- B and C may run in parallel
- A is the only writer
- do not let this rollout overlap with the Google Sheet API / CRM / WhatsApp / import track
