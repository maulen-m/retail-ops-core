# Agent 752 - Cash Risk Daily Surface Spec Read-Only

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_752_cash_risk_daily_surface_spec_readonly_closeout.md`

Assigned evidence folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_752_cash_risk_daily_surface_spec_readonly_evidence/`

Dependency:

- Start only after the Agent750 CodeCaptain review pack returns the GREEN decision token, the DB/workbook-boundary review has resolved `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`, the guarded orchestrator launch has already recorded pre-launch `scripts/check_agent750_launch_readiness.py` `"ok": true`, and your post-launch boundary check below returns `"ok": true`.

## Hard Launch Stopline

Before doing any work, run from `~/Docs/Autonomous_business`:

```bash
./scripts/check_agent750_launch_readiness.py --allow-existing-downstream-artifacts
```

This is a post-launch child-agent boundary check. The flag only tolerates the Agent751/752/753 downstream artifacts created by the guarded monitor-only launch; all other readiness errors remain hard blockers.

If it does not return `"ok": true`, stop before mission work. This includes `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`. Do not manually ping, paste, or send any tmux/chat message to the orchestrator or any other pane. Write only the assigned closeout with the readiness JSON/errors, a standalone `Gate: RED` line, and a clear `ReadinessStopline:` section; do not create extra evidence beyond what is needed for that closeout. Do not bypass this with manual memory of a review answer.

## Mission

Create a read-only Cash Risk Daily owner-output specification for Option C validate-only. This is analyst/spec work only. Do not edit shared repo docs or code unless the orchestrator gives a new explicit write boundary.

## Required Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/OPTION_C_VALIDATE_ONLY_IMPLEMENTATION_PLAN_AFTER_DEC77_REANCHOR_20260509.md`
5. Agent750 closeout.
6. Agent750 CodeCaptain review answer.
7. Agent747, Agent748, and Agent749 closeouts.
8. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/DB_BOUNDARY_DRIFT_TRIAGE_20260510_124512.md`
9. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/CODECAPTAIN_DB_BOUNDARY_SUPPLEMENT_AGENT750_20260510_124512.md`
10. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/BOUNDARY_REANCHOR_APPROVAL_AGENT750_20260510_153410.md`

Use the launch-time readiness JSON as the active DB/workbook boundary source. Do not assume the original `dec77` DB boundary or reviewed workbook boundary is current unless the boundary review/re-anchor has cleared `production_db_sha_mismatch` and `protected_workbook_sha_mismatch`.

## Current Boundary

- Original Agent750 reviewed DB SHA: `dec77f37cc63147e54e9085a6a0f9564d9ead9e57aea0d8483dc0473886bee64`
- Supplement DB SHA before launch-time re-anchor: `f8ab3968cb9ea2f718f789f3bf1ee08742d41a6b5ae8c0cca6da421f9f70b156`
- Re-anchored launch-readiness DB SHA: `44426216a026c3ab4f7c658e4950421446b99bae99e7cf704db8e2c96d35cc91`
- Launch-time DB SHA: use the `db_sha256` from the readiness JSON that returns `"ok": true`.
- Original Agent750 reviewed workbook SHA: `3ad4b81c39b125c48b34c02afb8a30eafd348658e07afd27c11f628b8987025c`
- Supplement workbook SHA before launch-time re-anchor: `7cf6eb60607d2b1a6e1cd238156121c897f22fcb319426a376a66dfac3f4bd75`
- Re-anchored launch-readiness workbook SHA: `bd7c5bb3e336f0cf35423ad00e7e6f25fa5ae41cdeb3ceb51075e09047f613b9`
- Launch-time workbook SHA: use the `workbook_sha256` from the readiness JSON that returns `"ok": true`.

## Write Boundary

Allowed writes:

- assigned closeout;
- assigned evidence folder.

Forbidden:

- Do not mutate repo code or shared docs.
- Do not mutate production DB or workbook.
- Do not mutate schedulers, LaunchAgents, or plist files.
- Do not create or remove `config/proof_window.lock`.
- Do not write external systems.
- Do not ask owner for approval.
- Do not reuse the old Agent54 phrase or activate Agent64.

## Required Output

Produce a concise spec in the closeout/evidence folder covering:

- Cash Risk Daily sections and field list;
- trust banner wording for `GREEN`, `WARNING`, and `BLOCKED`;
- allowed and blocked owner decisions in validate-only mode;
- required source freshness and cashflow gates;
- `last_statement_date` handling;
- actual/model separation wording;
- cash preservation matrix visibility;
- draft-only publication language;
- gaps that Agent751 must encode in tests or runner output.

## Gate Semantics

`GREEN`:

- spec is concrete enough for Agent751 to implement;
- Cash Risk Daily remains draft-only;
- no production authority is implied;
- no forbidden mutation occurred.

`YELLOW`:

- spec is usable but needs orchestrator/CodeCaptain clarification.

`RED`:

- spec implies production cash/PO/payment/ad authority;
- forbidden mutation occurs.

## Closeout

Write closeout with READCHECK, files written, findings, recommended fields, stoplines, implementation notes for Agent751, and standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
