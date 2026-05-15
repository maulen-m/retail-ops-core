## PLAN — LINE51 Root-Cause And Decision-Grade Second Pass

Date: 2026-04-23

### Purpose

Investigate why the external rebuild likely overstates `CL_OC_MEN_LINE51_WHITE` active stock, determine whether the same bias affects other families, and prepare a corrected second-pass external analysis path that is decision-useful even without a near-term full manual recount.

### Why This Run Exists

We now have three important facts:

1. The external rebuild workbook is directionally useful, but it is not active-stock truth as written.
2. LINE51 appears materially overstated versus warehouse intuition: rough owner estimate is about `750` total units, while the external rebuild is much higher.
3. We do not currently have a reliable near-term option for a full warehouse recount, so we must isolate root causes from data and improve the external second pass rather than guessing a blanket haircut.

### Direct Questions This Run Must Answer

1. Is LINE51 overstated because sales were undercounted, because returns were overcounted, because cancellations were misinterpreted, because mapping duplicated stock, or some combination?
2. Is the LINE51 gap family-specific, or does it indicate a broader pattern affecting other high-capital families?
3. Can we justify any cross-family correction rule from evidence, or must corrections stay family-specific?
4. What exact context and constraints must the next external expert pass receive so we stop wasting his computation on missing assumptions?

### Operating Repo And Shared Paths

- Operating repo: `~/Docs/Autonomous_business`
- Run pack: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_line51-root-cause-and-second-pass`
- Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass`

### Canonical Protocol

Read and follow:

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_stock-cost-truth-repair-second-pass/PLAN.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_a_execution_log.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/agent_c_report.md`

### Key Existing Artifacts

Primary external workbook under review:

- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/stock_anchor_selection_and_rebuild_v2_2026-04-23.xlsx`

Key external answer artifacts:

- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/stock_anchor_selection_and_rebuild_v2_report_2026-04-23.md`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/current_stock_rebuild_2026-04-23.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/movement_replay_2026-04-23.csv`
- `~/Docs/Oracle/Autonomous_business/2026-04-23/092937_TASK-000_decision-grade-stock-anchor-selection-rebuild-v2-with-db-tail/answer/product_kaspi_offer_mapping_catalog.csv`

Previous repair outputs that must be reused:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/second_pass_inputs/second_pass_expert_pack_spec_2026-04-23.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/second_pass_inputs/stock_rebuild_landed_cogs_overlay_2026-04-23.csv`
- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_stock-cost-truth-repair-second-pass/second_pass_inputs/second_pass_cost_surface_summary_2026-04-23.md`

Quarantine truth artifacts:

- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_summary.md`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/return_cancel_backlog.csv`
- `~/Docs/Autonomous_business/exports/returns_quarantine/2026-04-23/employee_qc_queue.csv`

### Execution Posture

- Agent A is the only write-capable execution agent.
- Agent B and Agent C are read-only analysts.
- B and C publish independently before reading each other.
- Agent A starts only after both first-pass reports exist.
- No DB writes unless they are clearly necessary, backup-first, env-gated, and explicitly logged.

### Scope

In scope:

1. LINE51-only root-cause analysis on movement, returns, cancellations, and mapping chronology.
2. Cross-family sensitivity analysis for top-capital families to test whether LINE51’s gap is local or systemic.
3. A repo-side execution pass that creates an override-ready, quarantine-aware active-stock sidecar and prepares the corrected external second-pass bundle/prompt.
4. A final external-expert handoff prompt that uses the improved context efficiently.

Out of scope:

- broad manual recount workflows
- pretending the current external workbook is already decision-grade
- arbitrary blanket haircut rules without evidence
- unrelated cashflow/PO/dashboard refactors

### Agent Split

#### Agent B — LINE51 Root-Cause Analyst

Read-only.

Mission:

- Determine exactly where LINE51 may be overstated.
- Audit LINE51 movement chronology end to end:
  - anchor quantity
  - shipped / completed / delivered movements
  - returned-to-warehouse movements
  - cancellations and whether they should or should not affect stock
  - mapping / alias / duplicate article issues
- Answer whether LINE51 overstatement is most likely driven by:
  - undercounted sales
  - overcounted returns
  - cancellation misclassification
  - duplicate mapping / aliasing
  - anchor overstatement
  - another specific cause
- Quantify the probable gap if possible.

Required deliverable:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_b_report.md`

#### Agent C — Cross-Family Sensitivity And Quarantine Analyst

Read-only.

Mission:

- Test whether LINE51’s overstatement pattern likely generalizes.
- Focus on top-capital / top-units families, especially:
  - `CL_OC_MEN_LINE51_WHITE`
  - `CL_NEW-CLO2_MEN_SUIT-61_BLACK`
  - `CL_OC_MEN_LINE52_BLACK`
  - `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK`
  - `CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE`
  - `CL_NEW-CLO_MEN_T-SHIRT_BLACK`
- Determine whether a global haircut rule can be justified.
- Determine which families can be:
  - left mostly as-is
  - family-overridden
  - still blocked pending stronger evidence

Required deliverable:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_c_report.md`

#### Agent A — Execution Agent

Write-capable after B and C publish.

Mission:

1. Read B and C reports.
2. Build the smallest safe operator-ready decision surface:
   - active-stock sidecar
   - quarantine-aware family adjustments
   - LINE51 override-ready logic if warranted by evidence
3. Prepare the improved external second-pass context bundle and prompt.
4. Do not perform broad DB mutation unless clearly required and explicitly logged.

Required deliverable:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_line51-root-cause-and-second-pass/agent_a_execution_log.md`

### Desired End State

By the end of this run we want:

1. a clear root-cause statement for LINE51 overstatement
2. an evidence-backed answer on whether a global haircut rule is justified
3. a corrected internal sidecar / decision surface for near-term use
4. a well-scoped, assumption-complete external expert prompt and pack spec

### Sequence

1. Agent B and Agent C run in parallel.
2. Agent A runs after both reports exist.
3. Human owner reviews Agent A output.
4. External expert receives the corrected second-pass bundle and prompt.
5. After the external answer returns, we do one final review pass before any stock truth is promoted for business decisions.

### Done Criteria

This run is successful when:

- LINE51 root-cause is narrowed honestly and concretely
- we know whether the problem is local, systemic, or mixed
- we have an operator-safe interim decision surface better than “apply 20% everywhere”
- the external second pass is set up with complete assumptions instead of guesswork
