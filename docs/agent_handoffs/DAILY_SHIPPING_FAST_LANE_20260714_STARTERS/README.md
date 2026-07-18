# Daily Shipping Fast-Lane starter pack

Canonical plan: `~/Docs/Autonomous_business/docs/parallel_runs/2026-07-14_daily-shipping-fast-lane-optimization/PLAN.md`

Sequence:

1. Agent B and Agent C run independently in parallel.
2. Agent A starts only after both reports exist.
3. Agent D reviews only after Agent A writes its execution log and candidate evidence.
4. The main orchestrator alone decides whether installed-runtime deployment gates are GREEN.

Short launch lines:

- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/DAILY_SHIPPING_FAST_LANE_20260714_STARTERS/01_AGENT_B__RUNTIME_AUDIT__PARALLEL.md`.
- Read the repo bootstrap context and execute `~/Docs/Autonomous_business/docs/agent_handoffs/DAILY_SHIPPING_FAST_LANE_20260714_STARTERS/02_AGENT_C__RELEASE_AUDIT__PARALLEL.md`.
- After Agents B and C finish, execute `~/Docs/Autonomous_business/docs/agent_handoffs/DAILY_SHIPPING_FAST_LANE_20260714_STARTERS/03_AGENT_A__IMPLEMENTATION__AFTER_01_02.md`.
- After Agent A finishes, execute `~/Docs/Autonomous_business/docs/agent_handoffs/DAILY_SHIPPING_FAST_LANE_20260714_STARTERS/04_AGENT_D__INDEPENDENT_RELEASE_REVIEW__AFTER_03.md`.
