## Phase-1 Success Criteria

Phase-1 is successful when:

### 1. Daily Loop
One command (or very short script sequence) ingests the latest Kaspi orders file(s), updates the DB, and regenerates `sales_daily`, inventory state, and PO suggestions without manual Excel formulas.

### 2. Size-Aware PO Suggestions
For critical SKUs (LINE52, LINE51, and at least 5 other models), the system proposes POs at `SKU_key` + `MY_SIZE` level.

**Example output:** `LINE52: S=10, M=20, L=15, XL=12…`

These must match your "human best guess" within a small tolerance.

### 3. Capital Tracking
The DB produces a report showing, per `SKU_key`:
- On-hand stock
- On-order stock
- D₃₀
- SS_total
- ROP
- ROIC
- Capital tied up

**Tolerance thresholds vs V15:**
| Metric | Allowed Variance |
|--------|------------------|
| D₃₀, SS_total | ±1% |
| ROIC | ±2% |

### 4. Founder Time
On a normal day: ≤20-30 minutes reviewing outputs and copying PO lines to suppliers (plus whatever time you choose to invest in improvements), instead of rebuilding analytics.

### 5. Reliability & Auditability
Any bug or weird number can be traced by:
- Checking DB tables
- Comparing to the Excel UI
- Looking up a row in `MIGRATION_LOG.md` or the sales ingest logs

No guessing required.