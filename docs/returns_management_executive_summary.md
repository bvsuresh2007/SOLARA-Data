# Solara Returns Management — Executive Summary

**Version**: 1.0 | **Date**: 2026-04-10 | **For**: Administrator Approval

---

## The Problem

Returned goods arrive from multiple channels (Shopify, Amazon, CarltonOne gifting, Retailez B2B) in varying conditions (good / damaged) — currently no standardized process for receiving, inspecting, accounting, or tracking, creating audit and GST compliance risks.

## The Solution

A 5-stage process with full traceability from package arrival to either resale or write-off.

---

## Process Flow (at a glance)

```
Package arrives
     │
     ▼
┌─────────────────┐
│ STAGE 1         │ Warehouse receives, scans AWB, matches to Delivery Note
│ Receiving (24h) │
└────────┬────────┘
         │
         ├─── Identified ──► STAGE 2A: Create Sales Return against original DN
         │                   → Stock to Returns Warehouse
         │
         └─── Orphan ──────► STAGE 2B: Create Orphan Return Log + Material Receipt
                             → Stock to Unknown Returns Warehouse
         │
         ▼
┌─────────────────┐
│ STAGE 3         │ QC team inspects, categorizes, photographs damage
│ QC (48h)        │ → Good: Main Warehouse
└────────┬────────┘ → Damaged-Repairable: Repair WIP
         │          → Damaged-Scrap: QC/Damaged
         │
         ▼
┌─────────────────┐
│ STAGE 4         │ Orphans investigated via courier manifests,
│ Investigation   │ platform dashboards, customer service leads
│ (7-15 days)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ STAGE 5         │ Unmatched orphans + Damaged-Scrap → Journal Entry
│ Write-off       │ Finance reviews monthly, approves > ₹10K
│ (Monthly)       │
└─────────────────┘
```

---

## Key Outcomes

| Goal | Achieved By |
|------|-------------|
| **Full audit trail** | Every return linked to DN or logged in Orphan Register |
| **Accurate inventory** | Stock Entries track every warehouse movement |
| **Correct accounting** | Channel-specific rules for Credit Notes & refunds |
| **GST compliance** | Credit Notes issued within same FY; proper GSTR-1 adjustments |
| **Quality insights** | Monthly reports on return reasons, condition, channel rates |

---

## Channel-Specific Treatment

| Channel | Accounting Document |
|---------|--------------------|
| B2C Shopify | Sales Return + Credit Note + Refund Payment |
| B2C Amazon/Flipkart/Meesho | Sales Return + Credit Note + Platform reconciliation |
| B2B2C Gifting (current month) | Sales Return only (adjust draft SO) |
| B2B2C Gifting (past month) | Sales Return + Credit Note against monthly invoice |
| B2B Direct | Sales Return + Credit Note |
| Replacement Returns | Sales Return only (no refund, already replaced) |

---

## Infrastructure Required

### New Warehouses
- `Unknown Returns - WTBBPL` (for orphan returns)
- `Repair WIP - WTBBPL` (for repairable items)

### New Custom Fields on Delivery Note
Return Reason, Return Condition, Return AWB, Received By, Inspected By, Return Photos

### New Doctype
`Orphan Return Log` — tracks unidentified returns through investigation to resolution

### Total Implementation Effort
**4 weeks** — ERPNext setup (1 week) + Training (1 week) + Reports (2 weeks)

---

## Key SLAs

| Step | SLA |
|------|-----|
| Receive package → Create record | 24 hours |
| QC inspection | 48 hours |
| Orphan investigation window | 7–15 days |
| B2C Credit Notes | 72 hours |
| Monthly write-offs | First week of following month |

---

## Ownership

| Team | Responsibility |
|------|---------------|
| Warehouse | Receiving, scanning, categorizing |
| QC | Inspection, condition, photo documentation |
| Customer Service | Orphan investigation |
| Finance | Credit Notes, Journal Entries, GST reconciliation, monthly write-offs |
| Operations Manager | Monthly review, approve write-offs > ₹10K |

---

## Risks Mitigated

- **Audit risk** — Every return traceable to original sale
- **GST non-compliance** — Credit Notes issued within statutory timelines
- **Inventory inaccuracy** — Physical stock matches ERPNext via mandatory Stock Entries
- **Revenue leakage** — Orphan returns investigated, not silently absorbed
- **Damage fraud** — Photo evidence required for all scrap write-offs

---

## Approval Required

| Approval | Name | Signature | Date |
|----------|------|-----------|------|
| Proposed By | Suresh | | |
| Finance Head | | | |
| Operations Head | | | |
| **Administrator** | | | |

---

**Full Process Document**: See `returns_management_process.md` for detailed procedures, accounting treatment, and implementation checklist.
