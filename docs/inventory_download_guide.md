# Inventory Data Download Guide

**Last Updated**: 2026-02-25

## Overview

Inventory data is exported manually from 4 portals: **EasyEcom (Amazon)**, **Zepto**, **Blinkit**, and **Swiggy**.

> **Important**: Inventory snapshots reflect the current state only. Historical/backdated downloads are **not available** on any portal. Missing past data cannot be recovered — once the automated scraper workflows are running on schedule, inventory data will be collected daily without gaps.

---

## Portals

### 1. Amazon — EasyEcom

1. Log into EasyEcom.
2. Navigate to **Inventory → Manage Inventory**.
3. Click the **Download Inventory** button.
4. Wait for the download to complete (progress indicator shown).
5. Save the downloaded file.

---

### 2. Zepto

1. Log into Zepto vendor portal.
2. Navigate to **Reports → Request Report**.
3. For report type, select **Vendor Inventory**.
4. Click **Submit**.
5. Wait for the report to complete (status updates on the same page).
6. Download the completed report.

---

### 3. Blinkit — Partners Portal

1. Log into the Blinkit Partners Portal (`https://partnersbiz.com`).
2. Navigate to **Stock on Hand** (`/app/soh`).
3. Click **Download Sales Data**.
   > Note: This option appears under the Stock on Hand section. For sales data it appears under the Sales section (`/app/sales`) — make sure you are on Stock on Hand here.
4. Set the date range (start date = end date = today).
5. Click **Request Data**.
6. Navigate to **Report Requests** (`/app/report-requests`).
7. Wait for the report row to show status **"success"** (poll/refresh the page — can take a few minutes).
8. Click the **download icon** in the Actions column of that row to download the file.

---

### 4. Swiggy

1. Navigate directly to: `https://partner.swiggy.com/im-vendor/stock-on-hand`
2. Click the **Bulk Download** button on that page.
3. Go to **Downloads** and retrieve the Excel report once it appears.

---

## Cadence

| Portal   | Report Type      | Frequency | Notes                              |
|----------|------------------|-----------|------------------------------------|
| EasyEcom | Manage Inventory | Daily     | Direct download, no queue          |
| Zepto    | Vendor Inventory | Daily     | Queued report, wait for completion |
| Blinkit  | Stock on Hand    | Daily     | Queued report via Report Request   |
| Swiggy   | Stock on Hand    | Daily     | Bulk download, retrieve from Downloads section |

---

## Automation Status

These steps are currently **manual**. Automated scraper workflows will be built to perform these downloads on schedule. Once live, inventory data will be captured daily at the scheduled run times.

The Blinkit scraper is functional — a single verification run against the Stock on Hand flow is needed to confirm the inventory selectors match (vs the confirmed sales selectors). No code changes are expected to be required.

Files should be placed in `data/raw/<portal>/` after download for the import pipeline to pick them up.
