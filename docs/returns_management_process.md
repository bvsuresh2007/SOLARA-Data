# Solara Returns Management — Process Note

**Version**: 1.0
**Effective Date**: 2026-04-10
**Owner**: Operations + Finance
**Approved By**: _______________________  **Date**: _______________

---

## 1. Purpose

This document defines the end-to-end process for handling returned goods received by Solara (Win The Buy Box Pvt Ltd) across all sales channels — ensuring full audit trail, accurate inventory, correct accounting treatment, and GST compliance.

---

## 2. Scope

Covers returns from:
- **B2C Shopify** (solara.in direct customers)
- **B2C Marketplaces** (Amazon, Flipkart, Meesho, Nykaa, etc.)
- **B2B2C Gifting** (CarltonOne and future gifting companies)
- **B2B Direct** (bulk customers like Retailez)
- **Replacement returns** (damaged units being returned after free replacement)
- **Orphan returns** (AWB unidentified / no matching Delivery Note)

---

## 3. Return Categories

| Category | Condition | Re-sellable? |
|----------|-----------|--------------|
| **A — Good** | Unopened, undamaged, all accessories intact | Yes |
| **B — Damaged, Repairable** | Cosmetic damage, missing accessories, minor defects | After refurbishment |
| **C — Damaged, Scrap** | Broken, unusable, water damage, major defects | No — scrap/write-off |
| **D — Missing Items** | Empty box or incomplete return | Investigation required |

---

## 4. Warehouse Structure

| Warehouse | Purpose | Status |
|-----------|---------|--------|
| `Returns Warehouse - WTBBPL` | Initial receiving for identified returns | Existing |
| `Unknown Returns - WTBBPL` | Orphan returns pending identification | **NEW — to be created** |
| `QC / Damaged - WTBBPL` | Damaged items awaiting write-off | Existing |
| `Repair WIP - WTBBPL` | Damaged-repairable items being refurbished | **NEW — to be created** |
| `Main Warehouse - WTBBPL` | Sellable stock | Existing |

---

## 5. Process Flow

### 5.1 Stage 1 — Receiving (Warehouse Team)

**Time**: Within 24 hours of package arrival

**Steps**:
1. Scan incoming AWB against return manifest
2. Cross-check with ERPNext Delivery Notes (by AWB field)
3. Categorize into two queues:
   - **Identified** → Proceed to Stage 2A
   - **Unidentified (Orphan)** → Proceed to Stage 2B

**Daily output**: Updated return register with package count, identified vs unidentified split

---

### 5.2 Stage 2A — Identified Returns

**Document**: Sales Return (Delivery Note with `is_return = 1`)

**Steps**:
1. On ERPNext → open original Delivery Note → click "Create → Return"
2. Fill mandatory fields:
   - **Return Reason** (dropdown: Damaged / Refused / Wrong Item / Size Issue / Customer Cancelled / RTO / Not Delivered)
   - **Return Condition** (Good / Damaged-Repairable / Damaged-Scrap / Missing Items)
   - **Return AWB, Received By, Received Date**
3. Target Warehouse: **Returns Warehouse**
4. Submit → stock reversed into Returns Warehouse, COGS reversed at valuation rate

**System Impact**:
- Stock ledger entry (reversal into Returns Warehouse)
- GL entry (COGS reversal)
- Original DN shows "Return Created" with link to Sales Return

---

### 5.3 Stage 2B — Orphan Returns (Unidentified)

**Document**: Stock Entry (Material Receipt) + Orphan Return Log

**Steps**:
1. Open package → identify the SKU by physical inspection
2. Create new record in **Orphan Return Log** doctype:
   - Received Date, AWB on package, Courier name
   - Item Code, Quantity, Condition
   - Receiver Notes (any clues: customer name, phone, platform indicators)
3. Create Stock Entry (Material Receipt):
   - Target Warehouse: **Unknown Returns**
   - Rate: Valuation Rate (COGS-neutral)
   - Reference: Link the Orphan Return Log entry in remarks

**Status**: "Investigating" — move to Stage 4 (Investigation)

---

### 5.4 Stage 3 — QC Inspection

**Time**: Within 48 hours of receipt
**Owner**: QC team

**Steps**:
1. Physical inspection of each returned unit
2. Update Sales Return DN (or Orphan Return Log) with final condition
3. Attach photos for Damaged-Scrap category (audit evidence)
4. Create Stock Entry (Material Transfer):

| Condition | From Warehouse | To Warehouse |
|-----------|----------------|--------------|
| Good | Returns Warehouse | Main Warehouse |
| Damaged-Repairable | Returns Warehouse | Repair WIP |
| Damaged-Scrap | Returns Warehouse | QC/Damaged |
| Missing Items | Keep in Returns Warehouse | Escalate to investigation |

**Output**: Physical stock now in correct warehouse, ERPNext reflects reality

---

### 5.5 Stage 4 — Orphan Investigation Window (7–15 Days)

**Owner**: Customer Service + Finance

**Investigation sources** (in order of priority):
1. Courier partner's return manifest (call/email courier with AWB on package)
2. Platform returns dashboards (Amazon, Flipkart, Meesho, Shopify)
3. Gifting company return lists (CarltonOne provides weekly return list)
4. Customer service — match to customer complaints/refund requests
5. Address/phone on return label — search ERPNext customer records

**Outcomes**:

| Outcome | Action |
|---------|--------|
| **Match found** | Cancel orphan Stock Entry → Create proper Sales Return linked to DN → Refund if applicable → Orphan Log status = "Matched" |
| **No match after 15 days** | Proceed to Stage 5 (Write-off) |

---

### 5.6 Stage 5 — Write-Off

**Owner**: Finance team
**Frequency**: Monthly (first week of following month)

**For Unmatched Orphans**:
- Create Journal Entry:
  - **Debit**: Unmatched Returns Income (other income account) — ₹ valuation value
  - **Credit**: Stock in Hand - Unknown Returns
- Move stock: Unknown Returns → Main Warehouse (if Good) or QC/Damaged (if Damaged)

**For Damaged-Scrap**:
- Create Stock Entry (Material Issue):
  - From: QC/Damaged Warehouse
  - Expense Account: Damaged Stock Write-off
- GL impact: Inventory reduced, expense booked

---

## 6. Channel-Specific Accounting Treatment

| Channel | Timing | Documents Required |
|---------|--------|-------------------|
| **B2C Shopify** | Immediately on return | Sales Return DN → Credit Note (SI with is_return=1) → Payment Entry (refund) → Shopify refund reconciliation |
| **B2C Amazon/Flipkart** | Within 48h of return | Sales Return DN → Credit Note → Match against platform settlement report |
| **B2C Meesho/Nykaa** | Per platform policy | Sales Return DN → Credit Note → Platform handles refund, we reconcile |
| **B2B2C Gifting (current month)** | Before SO submission | Sales Return DN only → Reduce qty on draft SO → Submit SO with adjusted qty |
| **B2B2C Gifting (past month, invoiced)** | After monthly SI created | Sales Return DN → Credit Note against monthly SI → Issue to gifting company |
| **B2B Direct** | Immediately | Sales Return DN → Credit Note → Apply to next invoice or refund |
| **Replacement Return** | Immediately | Sales Return DN (no refund, already replaced) → Usually goes to QC/Damaged |

---

## 7. GST Compliance

| Event | GST Treatment |
|-------|--------------|
| **Sales Return DN** (no SI yet) | No GST impact |
| **Credit Note against SI (same Financial Year)** | Reduce output GST liability in GSTR-1 (credit note table) |
| **Credit Note against SI (previous FY)** | Treat as write-off — no GST adjustment allowed after September of next FY |
| **B2B Credit Notes** | Buyer must also reverse ITC — issue credit note with buyer's GSTIN |
| **B2C Credit Notes** | Simple reduction, no ITC concern |
| **Orphan write-off** | No GST adjustment (goods treated as lost stock) |

---

## 8. Custom Fields (To Be Added in ERPNext)

### 8.1 On Delivery Note (existing `is_return` flag)

| Field Name | Type | Mandatory | Purpose |
|------------|------|-----------|---------|
| `return_reason` | Select | Yes (when is_return=1) | Damaged / Refused / Wrong Item / Size Issue / Customer Cancelled / RTO / Not Delivered |
| `return_condition` | Select | Yes (when is_return=1) | Good / Damaged-Repairable / Damaged-Scrap / Missing Items |
| `return_awb` | Data | Yes | Tracking number of return shipment |
| `received_by` | Link (User) | Yes | Who physically received |
| `inspected_by` | Link (User) | After QC | Who did QC inspection |
| `return_photos` | Attach (multiple) | For Damaged-Scrap | Evidence for write-off |

### 8.2 New Doctype: Orphan Return Log

| Field Name | Type |
|------------|------|
| received_date | Date |
| awb_on_package | Data |
| courier | Data |
| item_code | Link (Item) |
| qty | Int |
| condition | Select (Good / Damaged-Repairable / Damaged-Scrap / Missing Items) |
| receiver_notes | Text |
| identified_dn | Link (Delivery Note) — blank initially |
| status | Select (Investigating / Matched / Unmatched / Written Off) |
| match_date | Date |
| match_method | Select (Customer called / Platform manifest / AWB trace / Manual) |
| write_off_date | Date |
| write_off_je | Link (Journal Entry) |

---

## 9. Reports & Dashboards

Monthly reports to generate and review:

| Report | Purpose |
|--------|---------|
| **Returns by Channel** | Units + value split by Shopify/Amazon/B2B2C/etc. |
| **Returns by Reason** | Top return reasons for each channel — identify product/process issues |
| **Returns by Condition** | % Good vs Damaged — monitor courier handling quality |
| **Orphan Trends** | Unmatched % over time (target: below 5%) |
| **Write-off Summary** | Total ₹ written off each month |
| **Channel Return Rate** | (Returns ÷ Orders shipped) × 100 — identify problem channels |

---

## 10. Roles & Responsibilities

| Role | Responsibility |
|------|----------------|
| **Warehouse Receiving Team** | Scan AWBs, categorize identified vs orphan, create Sales Return/Stock Entry |
| **QC Team** | Physical inspection, update condition, attach photos, transfer to correct warehouse |
| **Customer Service** | Investigate orphans, match to customer complaints |
| **Finance Team** | Create Credit Notes, Journal Entries, monthly write-offs, GST reconciliation |
| **Operations Manager** | Monthly returns review, approve write-offs, identify process issues |

---

## 11. Service Level Agreements (SLAs)

| Process Step | SLA |
|--------------|-----|
| Receive → Create Sales Return/Stock Entry | Within 24 hours |
| QC Inspection completed | Within 48 hours of receipt |
| Orphan Investigation window | 7–15 days |
| Credit Note Creation (B2C) | Within 72 hours |
| Monthly Write-offs | First week of following month |

---

## 12. Escalation Matrix

| Issue | Escalate To |
|-------|-------------|
| Unmatched orphan with value > ₹10,000 | Operations Manager |
| Damaged-Scrap exceeds 10% of monthly returns | Quality Head |
| Frequent damage from specific courier | Courier Partner Relationship Manager |
| GST reconciliation mismatch | Finance Head → External CA |

---

## 13. Implementation Checklist

### Phase 1 — ERPNext Setup (Week 1)
- [ ] Create warehouse: `Unknown Returns - WTBBPL`
- [ ] Create warehouse: `Repair WIP - WTBBPL`
- [ ] Add custom fields to Delivery Note (return tracking — Section 8.1)
- [ ] Create `Orphan Return Log` doctype (Section 8.2)
- [ ] Configure Select field dropdowns with standard options

### Phase 2 — Training & Rollout (Week 2)
- [ ] Train warehouse team on new receiving process
- [ ] Train QC team on condition categorization and photo documentation
- [ ] Train finance team on Credit Note creation and GST adjustments
- [ ] Test process with 10 sample returns

### Phase 3 — Reporting & Controls (Week 3–4)
- [ ] Build monthly returns reports (Section 9)
- [ ] Define approval workflow for write-offs above ₹10K
- [ ] Set up dashboard for Operations Manager review

### Phase 4 — Automation (Future)
- [ ] Build Returns Processing app — upload return manifest Excel → auto-create Sales Returns
- [ ] Automated platform reconciliation (Shopify/Amazon returns API integration)
- [ ] AWB-to-DN matching algorithm for orphan reduction

---

## 14. Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Proposed By | Suresh | | |
| Reviewed By (Finance) | | | |
| Reviewed By (Operations) | | | |
| Approved By (Administrator) | | | |

---

**Document Control**:
- File: `docs/returns_management_process.md`
- Repository: SOLARA-Data
- Last Reviewed: 2026-04-10
- Next Review Due: 2026-07-10
