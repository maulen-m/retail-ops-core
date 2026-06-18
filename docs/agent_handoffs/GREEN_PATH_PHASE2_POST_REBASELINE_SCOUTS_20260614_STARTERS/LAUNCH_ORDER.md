# Launch Order

Parallel root group:
- Agent 19: stock gates scout.
- Agent 20: returns gates scout.
- Agent 21: ads/pricing/LINE31 scout.
- Agent 22: scheduler/alert/ops scout.

All four agents are read-only and independent. No downstream prompt is pre-authorized by this pack.

The orchestrator must review closeouts before any production write, dashboard flip, LaunchAgent change, external-system action, workbook change, or code edit.

