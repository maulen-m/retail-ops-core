# PLAN — PO‑5 Final Demand Overrides Freeze + Regenerate PLAN‑1 Outputs (CNY Deadline)
**Date:** 2026‑01‑20  
**Repo:** `~/Docs/Autonomous_business`  
**Goal:** Apply Adil’s finalized manual demand values as DB overrides so the PO engine 
(esp. PLAN‑1 / PO‑5 draft) uses them, then regenerate exports + run minimum gates for 
a safe PO‑5 placement today.

---

## Why this exists (physics)
Demand **D** is the “fuel rate” of the whole inventory engine: it directly drives 
SS_total, ROP, and order qty. If D is wrong, the system can order the wrong magnitude 
— this is direct capital risk.

We already support **date-window demand overrides** (multi-window). Overrides are 
active when:
- `start_date <= as_of_date < end_date` (inclusive/exclusive), `active_flag=1`
- If multiple windows are active, **latest start_date wins**.  
Source: `get_demand_overrides()` behavior. :contentReference[oaicite:0]{index=0}

Also note:
- `set_demand_override()` defaults `end_date` to **9999‑12‑31** (i.e., “indefinite”) 
when not provided. :contentReference[oaicite:1]{index=1}
- The DB uniqueness key is `(sku_key, start_date, end_date)`; we must avoid creating 
ambiguous “same start_date, different end_date” rows for the same SKU unless 
intentional. :contentReference[oaicite:2]{index=2}

---

## Non‑negotiable NO‑GO (stop conditions)
1. Any gate fails (below).
2. Any SKU in the override payload that is present in `PLAN-1` output does **not** 
show the expected `d_override / d_sku` in `exports/po_dashboard_data.json`.
3. Any DB override ambiguity for today:
   - If there are **2+ active override rows for the same (sku_key, start_date)** for 
   the cutoff date → STOP (tie risk because selection is start_date sorted).  
4. Any CL size canonicalization gate fails (already implemented earlier; must remain 
green).

---

## Inputs (provided by Adil)
**Final override demands (daily D):**

| sku_key | D |
|---|---:|
| CL_OC_MEN_LINE51_WHITE | 12.00 |
| CL_OC_MEN_LINE52_BLACK | 40.00 *(keep seasonal schedule already used: 40 then 30)* |
| CL_NEW-CLO2_MEN_HUS_GREEN | 1.50 |
| CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY | 0.00 |
| CL_NEW-CLO2_MEN_SUIT-61_BLACK | 10.00 |
| CL_NEW-CLO_KIDS_KID-31_BLACK | 1.36 |
| CL_NEW-CLO_KID_ROMBIK_BLACK | 3.16 |
| CL_NEW-CLO_MEN_BERSERK-RUSH_BLACK | 2.75 |
| CL_NEW-CLO_MEN_BERSERK-RUSH_WHITE | 2.70 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_BLACK | 4.53 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_GREEN | 0.00 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_GREY | 0.00 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_GREY-BLK | 0.00 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_RED | 0.00 |
| CL_NEW-CLO_MEN_BERSERK-SHIRT_WHITE | 0.91 |
| CL_NEW-CLO_MEN_LEG_BLACK | 3.70 |
| CL_NEW-CLO_MEN_LEG_WHITE | 3.70 |
| CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK | 7.64 |
| CL_NEW-CLO_MEN_NIKE-SHIRT_GREY | 2.70 |
| CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE | 5.40 |
| CL_NEW-CLO_MEN_ROMBIK_BLACK | 3.05 |
| CL_NEW-CLO_MEN_RUSH-PRO_BLACK | 3.62 |
| CL_NEW-CLO_MEN_RUSH-PRO_GREEN | 0.00 |
| CL_NEW-CLO_MEN_RUSH-PRO_GREY | 0.00 |
| CL_NEW-CLO_MEN_RUSH-PRO_RED | 0.00 |
| CL_NEW-CLO_MEN_RUSH_WHITE | 3.29 |
| CL_NEW-CLO_MEN_S-NK31_BLACK | 0.00 |
| CL_NEW-CLO_MEN_SPIDER-RUSH_BLACK | 2.00 |
| CL_NEW-CLO_MEN_T-SHIRT_BLACK | 4.81 |
| CL_NEW-CLO_MEN_T-SHIRT_WHITE | 2.00 |
| CL_NEW-CLO_MEN_T-SHIRT_GREY | 0.00 |
| CL_NEW-CLO_MEN_T-SHIRT_White | 2.00 |
| CL_NEW-CLO_MEN_TAICI_BLACK | 1.12 |
| CL_NEW-CLO_MEN_TAICI_WHITE | 1.11 |

**Important:**
- Values are floats; do not round.
- Some SKUs are intentionally set to `0.00` — ordering should become zero; system must 
not crash (division by zero guards must hold).

---

## Implementation strategy (fast + low risk)
We do **not** change formulas. We only change **parameters** (DB overrides).

### A) Add a versioned payload file (source of truth)
Create:
`data/demand_overrides/po5_final_overrides_20260120.csv`

CSV format (example):
```csv
sku_key,d_override,start_date,end_date,reason,source
CL_OC_MEN_LINE51_WHITE,12.0,2026-01-20,9999-12-31,"PO-5 final manual D (Adil)",
"MANUAL_PO5"
CL_NEW-CLO2_MEN_SUIT-61_BLACK,10.0,2026-01-20,9999-12-31,"PO-5 final manual D (Adil)",
"MANUAL_PO5"
...

For LINE52 keep the seasonal schedule (already required):

CL_OC_MEN_LINE52_BLACK,40.0,2026-01-01,2026-03-01,"LINE52 seasonal window 1",
"MANUAL_PO5"
CL_OC_MEN_LINE52_BLACK,30.0,2026-03-01,2026-06-01,"LINE52 seasonal window 2",
"MANUAL_PO5"

B) Add/Use a bulk apply script (idempotent)

Preferred (if not already present): create
scripts/apply_demand_overrides_csv.py

Requirements:

Default mode = dry-run (print what would be written)

Apply mode requires both:

--apply

env ENABLE_PARAM_WRITE=1 (protect from accidents)

For each CSV row call the existing set_demand_override() so we get the migration/index 
behavior and conflict-upsert semantics. 

191107_TASK-000_TASK-315_size-r…

If you believe a bulk script already exists, reuse it — but it must support 
multi-window (LINE52 has 2 rows).

Execution steps (today)
T0 — Tracking (append-only)

Update:

.claude/GOALS.md

.claude/TASKS.md

Add new goals (do not delete old ones):

G26 (TODO) — PO‑5 final demand overrides freeze (bulk payload + apply + verification)

G27 (TODO) — PO‑5 final sign-off pack regenerated after final overrides

Mark prior demand-window work as already DONE, do not rewrite history.

T1 — DB safety backup (mandatory)
python3 scripts/backup_db.py \
  --dest ~/Docs/Oracle/Autonomous_business/2026-01-20/po5_final_overrides \
  --db db/app.db --no-cleanup


Record the .db.gz path in session log + oracle pack later.

T2 — Apply overrides (dry-run first)
# dry-run
python3 scripts/apply_demand_overrides_csv.py \
  --csv data/demand_overrides/po5_final_overrides_20260120.csv

# apply
ENABLE_PARAM_WRITE=1 python3 scripts/apply_demand_overrides_csv.py \
  --csv data/demand_overrides/po5_final_overrides_20260120.csv \
  --apply

T3 — Verify override correctness for cutoff date (hard gate)

Determine cutoff date (use your standard “max snapshot date” or whatever 
update_po_dashboard uses).

Verify active overrides match expectations for that date.

Add a quick one-off verification snippet (or a small script) that:

loads the CSV rows active for cutoff_date

compares to get_demand_overrides(as_of_date=cutoff_date)

fails if mismatch for any SKU that appears in PLAN-1 output.

Also add a DB ambiguity check (must be empty):

-- Replace :cutoff with cutoff_date iso string
SELECT sku_key, start_date, COUNT(*) AS n
FROM dim_demand_overrides
WHERE active_flag=1
  AND (start_date IS NULL OR start_date <= :cutoff)
  AND (end_date IS NULL OR end_date > :cutoff)
GROUP BY sku_key, start_date
HAVING COUNT(*) > 1;


If any rows → STOP and fix (deactivate duplicates or normalize windows).

T4 — Regenerate authoritative outputs (no stale files)
python3 scripts/update_po_dashboard.py


Confirm updated files exist:

exports/po_dashboard_data.json

exports/po_dashboard.html

latest exports/po_supplier_export_*.csv

latest exports/po_supplier_summary_*.md

T5 — Minimum gates (must be green)
python3 scripts/validate_po_dashboard_invariants.py
python3 scripts/run_end_of_day.py --verbose


(If time is extremely tight and EOD is slow, you may proceed only if the last EOD run 
is from today and no ingest/ledger writes happened since — but you must explicitly 
record that decision in the oracle pack as an exception.)

T6 — PO‑5 “ready to order” proof (human-readable checks)

Produce exports/po5_final_override_check.txt that proves:

LINE52 active override = 40 for cutoff date (and future 30 window exists)

LINE51 override = 12

SUIT‑61 override = 10

For all SKUs with D=0.00 in payload:

dashboard does not crash

PLAN‑1 order qty is 0 (or SKU not present)

Supplier export contains no non-canonical CL sizes (previous size gate must stay green)

T7 — Oracle pack (final sign-off for PO‑5)

Create a single pack note:
~/Docs/Oracle/Autonomous_business/2026-01-20/
<timestamp>_TASK-000_TASK-XXX_po5_final_overrides_signoff.md

Include:

branch + HEAD

DB backup path

commands run

gate outputs

links/paths to regenerated exports

the override CSV file content (or reference) + proof file po5_final_override_check.txt

Definition of Done (GO)

We are GO to place real PO‑5 if:

Overrides applied and verified at cutoff date

update_po_dashboard.py outputs are fresh

invariants + EOD gates pass

supplier export is canonical (no “42”, etc.)

LINE52/LINE51/SUIT‑61 show expected D values in dashboard JSON