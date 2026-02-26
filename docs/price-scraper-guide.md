# Amazon Price Scraper — Step-by-Step Guide

This tool checks **live prices**, **Best Seller Rank (BSR)**, and **seller info** for any Amazon product.
You give it a list of ASINs, it opens Amazon and pulls the data automatically.

---

## Before You Start — One-Time Setup

You only need to do this section **once**. After that, jump straight to "Running the Scraper" every time.

---

### Step 1 — Open Terminal

On your Mac, press **⌘ + Space**, type `Terminal`, and press Enter.
A black/white window will open. This is where you type commands.

---

### Step 2 — Get the Code

Type this exactly and press Enter:

```
cd ~/Documents
git clone https://github.com/YOUR-ORG/SolaraDashboard.git
cd SolaraDashboard
```

> If the folder already exists on your Mac, skip the `git clone` line and just do:
> ```
> cd ~/Documents/SolaraDashboard
> git checkout main
> git pull
> ```

---

### Step 3 — Go to the Scraper Folder

```
cd scrapers/tools/amazon_asin_scraper
```

Your terminal is now "inside" the scraper tool.

---

### Step 4 — Install Python Packages

Type this and press Enter. It downloads the libraries the scraper needs (takes ~1 minute):

```
pip install -r requirements.txt
```

You'll see a lot of text scroll by. Wait for it to finish. That's normal.

---

### Step 5 — Install the Browser Engine

The scraper uses a real (invisible) browser. Install it with:

```
playwright install chromium
```

Wait for it to finish. You only ever need to do this once.

---

## Preparing Your ASIN List

An **ASIN** is the unique Amazon product code — 10 characters, usually starting with `B0`.
You can find it in any Amazon product URL: `amazon.in/dp/`**`B0CZHTGKJN`**

Create a plain text file called `asins.txt` in the scraper folder.
Put one ASIN per line, like this:

```
B0CZHTGKJN
B0CF9FKRVTJ
B0D1MZ7Z5W
B0BLR7HK4G
```

**How to create this file using Claude Code:**

1. Open Claude Code in the `SolaraDashboard` folder
2. Type: *"Create a file at scrapers/tools/amazon_asin_scraper/asins.txt with these ASINs: [paste your list]"*
3. Claude will create the file for you

---

## Running the Scraper

Make sure your terminal is in the scraper folder:

```
cd ~/Documents/SolaraDashboard/scrapers/tools/amazon_asin_scraper
```

---

### Run 1 — Quick check on a single ASIN

Use this to test that everything is working before doing a big run.

```
python main.py B0CZHTGKJN -m in
```

What you'll see printed:
```
ASIN: B0CZHTGKJN
Title:      Solara Water Bottle 1L...
Price:      ₹499
Main BSR:   #1,204 in Kitchen & Dining
Sold by:    RetailEZ
Ships from: Amazon
```

---

### Run 2 — Bulk run from your ASIN list, save to CSV

This is your main command for regular use.
Replace `results_today.csv` with whatever filename you want:

```
python main.py -f asins.txt -m in -o results_today.csv
```

- `-f asins.txt` → reads your ASIN list file
- `-m in` → Amazon India
- `-o results_today.csv` → saves everything to a spreadsheet

The scraper will go through each ASIN one by one. You'll see progress printed as it runs.
When finished, open `results_today.csv` in Excel or Google Sheets.

---

### Run 3 — Filter by a specific seller

If you only want to see products sold by a particular seller (e.g. to check if Solara is the buy-box winner):

```
python main.py -f asins.txt -m in -o results_today.csv -s "RetailEZ"
```

The CSV will only include rows where that seller has the buy box.
The terminal will also print a summary showing which ASINs are *not* with that seller.

---

### Run 4 — Send results to Slack

If your team uses Slack and a webhook is already configured, add `--slack` to any command:

```
python main.py -f asins.txt -m in -o results_today.csv --slack
```

**First-time Slack setup** (one time only):

```
python main.py --slack-setup https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

Ask your tech team for the webhook URL. After saving it once, `--slack` will always work.

---

## Reading the CSV Output

Open the file in Excel or Google Sheets. The columns are:

| Column | What it means |
|--------|--------------|
| `ASIN` | The product code |
| `Title` | Product name |
| `Price` | Current price (e.g. ₹499) |
| `Price_Value` | Price as a number (useful for sorting) |
| `BSR_Rank` | Best Seller Rank in main category |
| `BSR_Category` | Which category the rank is in |
| `Sub_BSR_Rank` | Rank in sub-category |
| `Seller` | Who currently has the buy box |
| `Ships_From` | Amazon / Seller |
| `Fulfilled_By` | Who handles delivery |
| `Error` | Empty = success. If something failed, the reason is here |
| `Scraped_At` | Date and time the data was pulled |

---

## Common Problems & Fixes

### "command not found: python"
Try `python3` instead of `python` in all commands.

### "No module named playwright" or "No module named bs4"
Run the install step again:
```
pip install -r requirements.txt
playwright install chromium
```

### Some ASINs show an Error in the CSV
Amazon occasionally blocks automated requests. Try re-running just the failed ASINs,
or add a longer delay between requests:
```
python main.py -f asins.txt -m in -o results_today.csv --delay 5
```

### Results look wrong / prices missing
Amazon's page layout changes sometimes. Ask your tech team to check — or use Claude Code:
open the scraper folder in Claude Code and describe what's wrong.

---

## Updating the Code (Getting Latest Changes)

Before each run, it's good practice to pull the latest version:

```
cd ~/Documents/SolaraDashboard
git checkout main
git pull
cd scrapers/tools/amazon_asin_scraper
```

---

## Using Claude Code to Help

If anything goes wrong, Claude Code can help fix it.

1. Open Claude Code in the `SolaraDashboard` folder
2. Paste the error message you see in Terminal
3. Ask: *"I'm running the price scraper and getting this error — how do I fix it?"*

Claude Code can read the files, diagnose the problem, and tell you exactly what to type.

---

## Quick Reference Card

| What you want to do | Command |
|--------------------|---------|
| Test one ASIN | `python main.py B0XXXXXXXXX -m in` |
| Run full list, save CSV | `python main.py -f asins.txt -m in -o results.csv` |
| Run + filter by seller | `python main.py -f asins.txt -m in -o results.csv -s "SellerName"` |
| Run + post to Slack | `python main.py -f asins.txt -m in -o results.csv --slack` |
| Show browser window | add `--no-headless` to any command |
| Set up Slack | `python main.py --slack-setup https://hooks.slack.com/...` |

> **Always make sure your terminal shows** `amazon_asin_scraper` **in the path before running any command.**
> If unsure, run: `cd ~/Documents/SolaraDashboard/scrapers/tools/amazon_asin_scraper`
