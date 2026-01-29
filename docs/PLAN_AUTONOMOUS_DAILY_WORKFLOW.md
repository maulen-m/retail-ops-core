# PLAN — Autonomous Daily Orders Workflow (Mac‑centric, Windows as thin client)

Date: 2026-01-29
Owner: Adil
Goal: Minimize owner time while preserving reliability and strict deadlines.

---

## 1) Summary (what changes)

- Mac stays the **single source of truth** (Kaspi API sync + DB).
- Windows laptop becomes a **thin client** for: calls + packaging UI only.
- **No Google Sheets** (eliminate lag + copy/paste + errors).
- Waybills auto-run **immediately after all sizes are done**.
- **Safety cutoff**: 18:30 (packaging must be complete by then).
- Hard SLA: **carrier cutoff 20:00** (rating penalty otherwise).

---

## 2) Constraints & assumptions

- Mac is always on, 24/7. (OK)
- Windows is only on during working hours. (OK)
- Local network access is available between Windows → Mac.
- Excel workbook can be removed from daily path (allowed).
- Size assignment uses existing **Size Probability Engine** (table + historical modes).

Sources in repo:
- `core/calc/size_probability.py` (size engine + cascade)
- `scripts/assign_sizes.py` (batch size assignment)
- `scripts/export_sizing_queue.py` / `scripts/import_sizing_queue.py` (queue + import)

---

## 2.1) Owner Q&A (confirmed inputs)

1) Automation level: **Full automation**. Owner should not manually intervene.
2) Schedule: **Daily** after 16:00 (can change later).
3) Carrier cutoff: **20:00 (GMT+5)**. Missed handoff causes rating penalty.
4) Calls: 1–1.5 hours typical; packaging ~1.5 min/order; warehouse→carrier ~20 min.
5) Employee device: **Windows laptop only** (calls + packaging).
6) Waybills: **Auto‑run immediately** once sizes are complete.
7) Safe deadline for packaging/bundling: **18:30**.
8) Call status required **per order** (block “Done” without status).
9) Size logic:
   - Use **size engine table** rules.
   - If unanswered → use **historical probability** by `kaspi_offer_name`.
   - If customer requests size → override.
10) Auto size: **Yes**, if no response or size left empty, but only after call status set.
11) Packaging PDF bundles: **Current run_build_waybills grouping is acceptable**.
12) Packaging order: strict **color + category** ordering (see section 7).
13) WhatsApp: Desktop is sufficient; WhatsApp is **not required** if better path exists.
14) UI access: **Local network only**; completions must sync to Mac DB.
15) Infra: Mac can run 24/7; cloud optional. Windows only 12:00–20:00.

---

## 3) Roles & ownership

- **System (Mac)**: All API sync, DB updates, sizing logic, waybill build, packaging queue.
- **Employee (Windows)**: Call customers + enter measurements/preferences + packaging confirmation.
- **Owner (Adil)**: Monitoring only; no manual copy/paste.

---

## 4) Workflow hierarchy (ASCII tree with owners)

```
Daily Pipeline (System/Mac)
├─ 16:00 Auto Fetch + Normalize [System/Mac]
│  ├─ API sync (Kaspi → DB)
│  ├─ Build Call Queue (orders missing size)
│  └─ Publish Call UI (local web)
├─ Call Station (Windows UI) [Employee]
│  ├─ For each order:
│  │  ├─ Call outcome (Answered / No answer / Callback / Declined)
│  │  ├─ Height + Weight
│  │  ├─ Preference override (optional)
│  │  └─ Mark Done
│  └─ System writes to DB
├─ Auto‑Sizing Gate [System/Mac]
│  ├─ If Done + missing size → run size engine
│  └─ Block completion if call status missing
├─ 18:30 Safety Cutoff [System/Mac]
│  ├─ Auto‑size any remaining
│  ├─ Flag exceptions
│  └─ Continue to waybills
├─ Waybills Auto‑Run [System/Mac]
│  ├─ run_build_waybills.command (API ship → waybills → bundles)
│  ├─ Build pack queue + packaging list
│  └─ Publish Pack UI
└─ Packaging Station (Windows UI) [Employee]
   ├─ One‑order view + auto‑print label
   ├─ Done → next order
   └─ Dispatch to carrier (before 20:00)
```

---

## 5) Detailed process breakdown

### Phase A — Auto‑fetch (16:00)
**Owner:** System (Mac)
- Run Kaspi API sync + planned date filters.
- Create a **call queue** of orders with no size.
- Store queue in DB (preferred), not in Sheets.

Recommended minimum approach:
- Reuse `scripts/export_sizing_queue.py` logic but **write to DB table** instead of CSV.
- Keep a CSV export as fallback only (optional).

### Phase B — Call Station UI (Windows)
**Owner:** Employee (Windows)
- Web UI served by Mac on local network.
- Each order must have:
  - call outcome
  - height/weight OR explicit size override
  - Done status
- **Rule:** employee cannot mark Done without call status.

### Phase C — Auto‑size assignment
**Owner:** System (Mac)
- For any “Done” order missing size:
  - Run size engine (`determine_size`) using:
    1) customer measurements
    2) historical offer size mode
    3) style mode
    4) default size
- Save `assigned_size`, `size_source`, `size_confidence`.

### Phase D — Auto waybill build
**Owner:** System (Mac)
- Trigger immediately once all orders are Done.
- Also hard trigger at 18:30 if incomplete.
- Output:
  - Store bundles (current logic OK)
  - Packing list sorted by strict order (color + product category)

### Phase E — Packaging Station UI
**Owner:** Employee (Windows)
- “Single order at a time” view:
  - auto‑print label (Windows printer)
  - show product, size, color, order id
  - click Done → next
- Sorting order enforced by config (see section 7).

---

## 6) Deadline control logic

- 16:00: auto‑fetch starts
- 18:30: **hard safety cutoff**
  - auto‑size any remaining
  - proceed to waybills regardless
- 20:00: carrier closes
  - if not completed: send alert + log penalty risk

---

## 7) Packaging order (config‑driven)

We should formalize your packaging order into a config file:
`config/pack_order_rules.yaml`

Example (per store):
1) **Black:** tights → leggings → t‑shirts → heavy (Print/Beli) → long sleeves → kids model 1
2) **White:** tights → leggings → t‑shirts → heavy → long sleeves
3) **Color X:** tights → leggings → t‑shirts → heavy → long sleeves → kids model 1 → kids model 2

This defines the **sort key** for bundling and the packaging UI queue.

---

## 8) Minimal system components to add

### A) Mac local web app (internal only)
- Framework: FastAPI or Flask (lightweight).
- Endpoints:
  - `/call-queue` (view + update)
  - `/pack-queue` (view + update)
  - `/status` (health)
- Auth: none (trusted LAN).

### B) Windows auto‑print helper
- Use SumatraPDF CLI or similar:
  - `SumatraPDF.exe -print-to-default -silent <file>`
- Triggered by Pack UI for each order.

### C) Background scheduler on Mac
- `launchd` for:
  - daily fetch @ 16:00
  - periodic health checks
  - 18:30 cutoff enforcement

---

## 9) Reliability safeguards

- All actions recorded in DB (auditability).
- If call station or pack UI offline:
  - fallback to CSV export + manual update
- If auto‑print fails:
  - pack UI allows manual “Print” retry.

---

## 10) Open questions (final tuning)

1) Which call outcomes should be supported? (Answered / No answer / Callback / Declined / Wrong number)
2) How should “No answer” be handled on deadline day?
3) Should the system auto‑notify employee at 18:00 / 18:20?
4) Are there store‑specific exceptions to packaging order rules?
5) Should we keep CRM Excel for audits only, or fully retire it?

---

## 11) Immediate next implementation steps (lowest risk)

1) Add call‑queue DB table + UI (Mac).
2) Implement size‑input validation rules (no Done without call status).
3) Auto‑trigger waybills when queue complete; force at 18:30.
4) Build pack UI using existing waybill PDFs.
5) Add printing helper on Windows.

---

## 12) Success criteria

- Owner spends **near‑zero time** daily (monitor only).
- No copy/paste between sheets and CRM.
- Packaging completes by 18:30 consistently.
- Wrong‑item packaging errors drop to near‑zero.
