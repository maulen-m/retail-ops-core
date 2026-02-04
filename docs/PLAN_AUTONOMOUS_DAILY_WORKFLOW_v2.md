# PLAN — Autonomous Daily Orders Workflow v2

Mac (Office) = system-of-record | Windows (Warehouse) = thin client UI + printing

- Date: 2026-01-30
- Owner: Adil
- Timezone: GMT+5 (Asia/Qyzylorda)
- Doc name: docs/PLAN_AUTONOMOUS_DAILY_WORKFLOW_v2.md

## 1) Purpose

Redesign daily order processing so the owner spends near-zero time on ops coordination, while improving reliability and minimizing employee error.

We eliminate:
- Google Sheets copy/paste loops
- Owner ↔ employee coordination pings
- Manual WhatsApp file dragging
- Manual “when do I run the command” ambiguity

We keep:
- Mac repo DB as canonical truth
- Existing Kaspi API sync + waybill build logic
- Existing size engine (table + historical probability) as canonical

We add:
- A remote-accessible Call Station UI + Packaging Station UI for the employee
- Deterministic “one order at a time” packing flow with auto-print
- Telegram notifications for deadlines and transitions
- A safe pilot/dual-run path to avoid “one-day failure” risk

## 2) What changed vs v1

v2 incorporates new constraints + confirmed answers:

### 2.1 Remote constraint (critical change)

Mac/owner is at office, Windows/employee is at warehouse (distant locations).

LAN/local network cannot be assumed.

Therefore: the UI must work reliably over the internet via a private, secure connectivity layer.

### 2.2 Call attempt rules (new)

Outcomes supported: Answered / No answer / Callback / Declined

No answer allows up to 3 attempts per order with a visible checklist.

After 3 attempts (or at cutoff), No answer becomes final and the system proceeds.

### 2.3 Cutoff semantics corrected

18:30 is the call/sizing cutoff (not “packaging complete”).

At 18:30 we auto-assign missing sizes and proceed to waybills.

Packaging typically begins after waybills/bundles are ready (with reminder at 18:45).

### 2.4 Telegram notifications (new)

- Call queue ready
- Reminders: 17:45 and 18:15
- Packaging start: 18:45
- Car engine reminder: 19:00

### 2.5 Store exception (new)

STOREB and MELVIS: phone numbers not visible in the usual flow.

Employee must check Kaspi Pay app at 12:00 and 16:00, and contact via Kaspi Pay messaging/calls.

### 2.6 Rollout safety (new)

Excel CRM is kept as read-only audit artifact during a pilot period.

We do shadow/dual-run until reliability gates are proven.

## 3) Constraints & assumptions

Mac (Office): always on 24/7, runs DB, automation, and is the single source of truth.

Windows (Warehouse): on during work hours (~12:00–20:00), used by employee for calls + packaging, has USB printer.

Internet connectivity exists in both locations (but may have occasional issues → must design fallback).

We do not want to expose the Mac DB to the public internet without a strong protection layer.

Existing scripts/logic remain canonical where possible:
- Kaspi API sync
- Waybill generation/bundling
- Size engine

## 4) Connectivity layer (Office Mac ↔ Warehouse Windows)

Because LAN cannot be assumed, v2 must include a secure remote access strategy.

### 4.1 Recommended (best balance of reliability + simplicity): Private mesh VPN

Use a private overlay network such as Tailscale (or equivalent) so Windows can access a Mac-hosted internal service securely without opening public ports.

Why this is best here
- No public inbound ports required.
- Works across NAT/dynamic IP.
- Fast setup, low ongoing maintenance.
- Strong default encryption.

### 4.2 Fallback option (if VPN is not viable): Authenticated tunnel

Use a managed tunnel (e.g., Cloudflare Tunnel) with access control. Still no open ports, but introduces a dependency.

### 4.3 v2 decision

Default plan assumes private VPN overlay.

Keep tunnel as documented fallback.

## 5) Roles & ownership

System (Mac / Office):
- Kaspi API sync → DB
- Build call queue
- Accept Call UI updates
- Run sizing engine
- Trigger waybill build + bundling
- Build pack queue
- Publish Pack UI endpoints
- Send Telegram notifications
- Audit logs + safety gates

Employee (Windows / Warehouse):
- Contacts customers
- Inputs height/weight or override size
- Tracks call attempts and outcomes
- Packages orders via Packaging Station UI
- Physically hands to carrier

Owner (Adil / Office):
- Monitoring only (Telegram + dashboard)
- During pilot: spot-check diffs, approve cutover
- Emergency fallback authority (rare)

## 6) Workflow hierarchy (ASCII tree with owners)

```
Daily Pipeline (System/Mac — Office)
├─ 12:00 Kaspi Pay window (STOREB/MELVIS) [Employee/Windows]
│  └─ Check Kaspi Pay app for messages/phones; attempt contact in-app
├─ 16:00 Auto Fetch + Normalize [System/Mac]
│  ├─ Kaspi API sync (Orders → DB)
│  ├─ Build Call Queue (orders needing size/contact)
│  ├─ Publish Call Station UI (remote via private VPN/tunnel)
│  └─ Telegram: "Call queue ready" (+ counts)
├─ Call Station (Windows UI — Warehouse) [Employee]
│  ├─ Per order: attempts 1..3
│  │  ├─ Channel: PHONE or KASPI_PAY
│  │  ├─ Outcome: Answered / No answer / Callback / Declined
│  │  ├─ Height+Weight OR Size override (if Answered)
│  │  └─ Mark Done (validated)
│  └─ Updates written to Mac DB (audit)
├─ Auto‑Sizing Gate [System/Mac]
│  ├─ If Done + missing size → size engine
│  ├─ Enforce: cannot be Done without call_status
│  └─ Save assigned_size + source + confidence
├─ 17:45 Telegram reminder [System/Mac]
├─ 18:15 Telegram reminder [System/Mac]
├─ 18:30 Hard Cutoff (Calls/Sizing) [System/Mac]
│  ├─ Auto-finalize NO_ANSWER after cutoff
│  ├─ Auto-assign sizes if still missing
│  ├─ Exclude DECLINED from shipping queue
│  └─ Trigger waybill build
├─ Waybills + Bundles [System/Mac]
│  ├─ Ship via API (parcel counts) if applicable
│  ├─ Download waybills via API
│  ├─ Build bundles + strict packaging list
│  └─ Publish Packaging Station UI
├─ 18:45 Telegram: "Packaging start" [System/Mac]
├─ Packaging Station (Windows UI — Warehouse) [Employee]
│  ├─ One-order view in strict sequence
│  ├─ Auto-print label on load (Windows printer)
│  ├─ Employee packages → clicks Done → next order
│  └─ Packaging completion tracked in DB
├─ 19:00 Telegram: "Start car engine" [System/Mac]
└─ Dispatch to carrier (before 20:00) [Employee]
```

## 7) Call Station logic (detailed)

### 7.1 Supported outcomes

- ANSWERED
- NO_ANSWER
- CALLBACK
- DECLINED

### 7.2 Attempt tracking (max 3)

Each order has up to 3 attempts. UI shows an explicit checklist:

Attempt 1 ✅ / Attempt 2 ⬜ / Attempt 3 ⬜

Each attempt records:
- attempt_no (1..3)
- timestamp
- channel: PHONE or KASPI_PAY
- outcome
- notes (optional)

### 7.3 Validation rules for “Done”

Employee cannot mark an order as Done unless:

call_status is set (non-empty), AND

if status is ANSWERED:

either height+weight are filled OR explicit size override is filled

Rules by status:

ANSWERED → Done allowed (with required inputs)

NO_ANSWER → Done allowed only when:

attempt_count == 3 (No answer becomes final), OR

system cutoff triggers auto-finalization at 18:30

CALLBACK → Done is NOT allowed (it’s explicitly pending)

DECLINED → Done allowed, but order is removed from shipping/pack queue and flagged for cancellation workflow

### 7.4 Cutoff behavior (18:30)

At 18:30:

Any unresolved order (CALLBACK pending, or <3 NO_ANSWER attempts) becomes:

NO_ANSWER_FINAL (AUTO_AFTER_CUTOFF) (unless already ANSWERED or DECLINED)

Missing sizes are auto-assigned via size engine

System proceeds to waybills

## 8) Store-specific exception: STOREB & MELVIS phones

These stores do not display phone numbers in the normal pipeline.

### 8.1 Employee process

At 12:00 and 16:00:

Employee checks Kaspi Pay app

Contacts customers via Kaspi Pay messaging/calls

Records attempt outcomes in Call Station UI under channel KASPI_PAY

### 8.2 System/UI requirements

Orders may have phone=null

UI must show a badge:

STOREB: use Kaspi Pay

MELVIS: use Kaspi Pay

Attempt tracking still applies (3 attempts max), but “attempt” may be a message send / in-app call.

## 9) Telegram notifications

Notifications are automated and go to the operational Telegram channel(s).

### 9.1 Events

- Call queue ready (after 16:00 import)
- 17:45 reminder
- 18:15 reminder
- 18:30 cutoff fired (auto-sizing + proceed)
- 18:45 packaging start
- 19:00 start car engine

### 9.2 Message content (minimum useful payload)

Each message should include:

total pending orders

remaining call tasks

remaining pack tasks (once packing begins)

top “risk reasons” (e.g., unresolved callbacks count)

## 10) Packaging Station UI (one-order flow + auto-print)

### 10.1 Core UX goals

Show exactly one next order at a time (strict deterministic sequence).

Auto-print that order’s label immediately.

Employee presses Done → next order appears and prints.

Queue ordering must match the strict grouping rules to reduce mistakes.

### 10.2 Printing architecture (Windows-safe)

Browsers are unreliable for fully automatic silent printing, so we introduce a Windows Print Agent:

Runs locally on Windows

Downloads the PDF for the “current order”

Prints via a CLI tool (e.g., SumatraPDF silent print)

Reports success/failure back to Mac service

Prevents double-print (idempotent print job IDs)

### 10.3 Packaging completion target

System should push to finish packaging in time to leave warehouse for carrier handoff.

Car travel time is ~20 minutes, carrier closes at 20:00.

Telegram at 19:00 is the “departure prep” trigger.

## 11) Packaging order rules (config-driven)

Keep v1 rule, formalize in:

config/pack_order_rules.yaml

Base ordering:

Black: tights → leggings → t‑shirts → heavy (Print/Beli) → long sleeves → kids model 1

White: tights → leggings → t‑shirts → heavy → long sleeves

Color X: tights → leggings → t‑shirts → heavy → long sleeves → kids model 1 → kids model 2

These rules define the sort key for:

bundle generation order

packaging station queue order

## 12) Minimal system components (v2)

### 12.1 Mac “Ops Service” (remote-access via VPN)

Responsibilities:

Read/write DB

Serve Call Station UI + Pack Station UI

Provide endpoints for Windows Print Agent

Run scheduled tasks + notifications

Suggested endpoints:

/status

/call-queue

/call-attempts (append-only)

/call/mark-done

/pack-queue

/pack/next

/pack/mark-done

/pdf/<id> (serve label PDFs)

Auth:

If VPN is used, can be minimal, but still recommended to require a shared secret token (env) to avoid accidental exposure.

### 12.2 Windows Print Agent

Local service/daemon that:

pulls “next order to print”

downloads PDF

prints silently

reports status

### 12.3 Scheduler (Mac)

Use launchd to run:

16:00 import → queue build → publish UI → Telegram

17:45 / 18:15 reminders

18:30 cutoff + waybill build trigger

18:45 packaging reminder

19:00 car engine reminder

## 13) Rollout plan (zero-day-failure constraint)

Because daily ops = cashflow oxygen, we must roll out safely.

Stage 0 — Shadow mode (1–3 days)

New system runs fully but does not replace current workflow.

Generate and store:

call queue snapshot

auto-size results

pack queue + bundles

Produce a daily diff report against legacy outputs.

Stage 1 — Assisted mode (3–7 days)

Employee uses Call Station UI to enter outcomes and measurements.

Waybill build still cross-checked with existing process.

Owner monitors only, but keeps a “fallback switch”.

Stage 2 — Full autonomy

Auto-run waybills and packaging queue.

Windows Packaging Station UI becomes the primary.

Excel CRM becomes read-only audit only.

Rollback at any time:

Fall back to CSV export + manual steps for that day.

## 14) Reliability safeguards

All workflows must be idempotent (safe to rerun).

Append-only attempt logs (audit).

If connectivity drops, UI must not lose data:

either queue locally (optional), or allow re-entry later, and system still applies cutoff safely.

If printing fails, allow retries + fail-safe manual print path.

If any step fails after 18:30, Telegram alert escalates immediately.

## 15) Success criteria (business practical)

This plan is “done” when:

Owner daily ops time: < 5 minutes/day

No Google Sheets, no copy/paste to run daily ops

All same-day orders:

have tracked attempts (up to 3)

get a size (manual or auto by cutoff)

generate labels/bundles reliably

are packaged with near-zero wrong-item errors

Employee can package continuously with:

one-order UI

auto-print

strict deterministic order

The system runs successfully for a sustained pilot period (e.g., 10 consecutive days) without owner intervention.

## 16) Immediate next steps (v2, lowest-risk order)

Implement and document the remote connectivity layer (VPN-first).

Add call task + call attempt DB tables (append-only attempts).

Implement Mac Ops Service endpoints for Call Station.

Add cutoff logic (18:30) + auto-size and proceed.

Add Telegram notifications schedule.

Implement pack queue endpoints + publish Pack Station UI.

Implement Windows Print Agent and integrate auto-print.

Add “shadow mode” daily diff report for pilot.

Execute staged rollout (Stage 0 → Stage 1 → Stage 2).

End: PLAN_AUTONOMOUS_DAILY_WORKFLOW_v2.md
