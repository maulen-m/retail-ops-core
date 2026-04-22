# docs_plan.md — Documentation Refactor Plan (Kaspi-only, v8 rollout)

Historical note: this was the original v8/v2 documentation rollout plan. Current active authority is `docs/inventory/Master_Inventory_Rules_v9.md` and `docs/protocol/active/PO_making_logic_v3.md`; keep the body below as historical context.

**Objective:** eliminate formula/version drift, remove out-of-scope channel content, and shrink default context load for agents — without losing auditability.

**Prime directive:** protect capital. Wrong VAT / delivery fee / lead time rules cause bad ROIC → bad POs → cash burn.

---

## Phase: NOW (must do before any next PO freeze)

### 1) Establish the entrypoint doc
**Action**
- Add `00_START_HERE.md` to the docs root.
- Read `AGENTS.md`, make sure that every agent reads `00_START_HERE.md` before any other doc.

**Acceptance**
- `AGENTS.md` explicitly says: “Read `00_START_HERE.md` first.”
- `00_START_HERE.md` contains the truth ladder + minimal reading sets.

---

### 2) Roll out Master_Inventory_Rules_v8 as the single truth
**Action**
- Add `inventory/Master_Inventory_Rules_v8.md` (Kaspi-only) created by merging:
  - v7’s regulatory updates (VAT 4%, delivery matrix, V16 sheet map, impact analysis)
  - v6.1’s missing logic:
    - Prep days system (Effective_L)
    - Partial OOS suppression detection (size drift)

**Acceptance**
- v8 contains:
  - VAT_rate = 0.04
  - Delivery fee matrix + lookup table + Excel + Python reference
  - Prep days (CL batch weight, cap at R)
  - Partial OOS detection + anchor_weight boost rules
  - Quick reference updated

---

### 3) Deprecate old rules docs to prevent accidental reuse
**Action**
- If any legacy rules docs exist, add a top banner:
  > **DEPRECATED:** superseded by `inventory/Master_Inventory_Rules_v8.md`. Do not implement from this file.

**Acceptance**
- No legacy rules doc can be opened without a DEPRECATED banner.

---

## Phase: NEXT (remove truth contamination + out-of-scope content)

### 4) Fix the “Oracle Pack” problem (very high risk)
**Problem**
- Legacy oracle pack summaries reference outdated sources (older rules docs, legacy VAT/delivery tiers). This can directly cause wrong implementations.

**Action**
Option A (preferred, fastest):
- Deprecate the legacy oracle pack summary and remove it from default context.
- Replace with a new short doc: `SYSTEM_OVERVIEW.md` (≤200 lines) that only links to:
  - `00_START_HERE.md`
  - `inventory/Master_Inventory_Rules_v8.md`
  - `ARCHITECTURE.md`
  - `DAILY_SOP.md`

**Acceptance**
- Oracle pack contains no doc that teaches outdated VAT/delivery/lead-time rules.

---

### 5) Update contract docs to v8/V16 and remove non-Kaspi (legacy multi-channel) assumptions
**Target files**
- `inventory/Excel_UI_Contract_for_CRM_V1.md`
- `inventory/Automation_Handoff_V16.md`
- `inventory/Sales_Data_Model_V16.md` (deprecate V15)
- `protocol/active/PO_making_logic_v2.md`

**Actions**
- Replace any references to legacy VAT or delivery tiers with v8 delivery matrix lookup.
- Remove non-Kaspi channel assumptions in wording and examples.
- Ensure each doc points back to v8 for formulas (do not restate formulas unless necessary).

**Acceptance**
- Grep check in docs root (excluding `archive/`):
  - no legacy VAT references
  - no legacy delivery tier constants described as current
  - no non-Kaspi export rows in ingestion tables
- Each contract doc contains a short “Source of truth” pointer to v8.

---

### 6) Upgrade schema docs to Autonomous_business/excel/Inventory_Core_V18.1_V2.xlsx (fix mismatch)
**Problem**
- Current docs describe conflicting `Fact_Sales` layouts (V15 vs V16).  
  That’s a direct source of ingestion bugs and reconciliation failures.

**Action**
- Create `inventory/Sales_Data_Model_V16.md`:
  - Align with v8’s `Fact_Sales` and `Fact_Sales_Daily` columns.
  - move V15 doc as deprecated to `archive/`.
- Update references in `Automation_Handoff` + `Excel_UI_Contract` to point to V16 doc.

**Acceptance**
- Only one “current” schema doc exists (Inventory_Core_V18.1_V2.xlsx).
- `Fact_Sales` column order matches v8.

---

## Phase: CLEANUP (context efficiency + long-term maintainability)

### 7) Split protocols into ACTIVE vs ARCHIVE
**Problem**
- Too many plan/protocol files are mixed with contracts, creating default context bloat.

**Action**
- Create:
  - `protocol/active/`
  - `protocol/archive/`
- Move files:
  - Keep only *currently active* plans in `protocol/active/`
  - Move completed/old plans to `protocol/archive/`
- In `00_START_HERE.md`, list only the active ones.

**Acceptance**
- Default agent onboarding does not include archive plans.
- Active protocols are ≤ 10 files.

---

### 8) Remove duplicate documents
**Problem**
- Some docs exist in multiple locations (duplicates cause drift).

**Action**
- Keep a single canonical location per doc.
- Replace duplicates with a 3-line stub pointing to the canonical file (or delete).

**Acceptance**
- No two files share identical title+content for the same topic.

---

### 9) Add lightweight “docs CI” checks (optional but recommended)
**Action**
- Add a simple script (or Make target) that runs:
  - grep for banned strings in non-archive docs
  - grep for outdated version pointers (legacy rules versions, legacy VAT/delivery tiers)

**Acceptance**
- Fails fast if someone reintroduces old formulas.

---

## Definition of Done (DoD)

- v8 exists and is referenced by all contracts.
- Outdated formulas removed from contracts.
- Only one “current” schema doc exists (V16).
- Entry doc exists + AGENTS.md points to it.
- Protocols are separated into active vs archive.
- Default context load is reduced (agents don’t read ~20k lines to do a 200-line task).

---

## Notes for implementers

- Prefer **renaming** over rewriting when possible (keeps git history).
- When removing large sections, consider moving them into `protocol/archive/` rather than deleting (auditability).
