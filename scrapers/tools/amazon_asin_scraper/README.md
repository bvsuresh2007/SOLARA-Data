# Amazon ASIN Scraper

Standalone CLI tool to fetch real-time **price**, **BSR rank**, and **seller info** for Amazon ASINs.

Originally developed as the SOLARA-Data project; integrated here as a standalone research tool.

## Usage

```bash
cd scrapers/tools/amazon_asin_scraper

pip install -r requirements.txt

# Single ASIN (Amazon India)
python main.py B0CZHTGKJN -m in

# Multiple ASINs with CSV output
python main.py B0CZHTGKJN B09G9HD6PD -o results.csv -m in

# Bulk from file, Selenium mode (bypasses CAPTCHA)
python main.py -f asins.txt --browser -m in -o results.csv

# Filter by seller name, post to Slack
python main.py -f asins.txt --seller "Solara" --slack

# Set up Slack webhook (persisted in slack_config.json)
python main.py --slack-setup https://hooks.slack.com/services/...
```

## CLI Arguments

| Flag | Description |
|------|-------------|
| `asins` | One or more ASINs (positional) |
| `-f FILE` | Text/CSV file of ASINs (one per line) |
| `-o FILE` | Output CSV path |
| `-m CODE` | Marketplace code: `in`, `com`, `co.uk`, `de`, etc. |
| `--browser` | Use Selenium Chrome (bypasses CAPTCHA) |
| `--delay N` | Seconds between requests (default 3.0) |
| `--debug` | Save raw HTML to `debug_<ASIN>.html` |
| `-s SELLER` | Filter results by seller name (substring match) |
| `--slack` | Post results to Slack after run |
| `--slack-setup URL` | Save Slack webhook URL |

## Output Columns (CSV)

`ASIN, Title, Price, Price_Value, BSR_Rank, BSR_Category, Sub_BSR_Rank, Sub_BSR_Category, All_BSR, Seller, Ships_From, Fulfilled_By, URL, Error, Scraped_At`

## Dependencies

- `requests` + `beautifulsoup4` + `lxml` — HTTP scraping
- `selenium` + `webdriver-manager` — Browser mode
- `fake-useragent` — Realistic user agents
