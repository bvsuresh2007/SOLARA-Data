FROM python:3.11-slim

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
    cron curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY scrapers/requirements.txt ./scrapers/requirements.txt
RUN pip install --no-cache-dir -r scrapers/requirements.txt
RUN playwright install chromium --with-deps

# Copy full project (backend needed for DB models)
COPY . .

# Install cron job
COPY scrapers/crontab /etc/cron.d/solara-scraper
RUN chmod 0644 /etc/cron.d/solara-scraper && crontab /etc/cron.d/solara-scraper

# Apply schedule from env at startup
CMD ["sh", "-c", "echo \"${SCRAPE_SCHEDULE_MINUTE:-0} ${SCRAPE_SCHEDULE_HOUR:-2} * * * cd /app && python -m scrapers.orchestrator >> /var/log/solara_scraper.log 2>&1\" > /etc/cron.d/solara-scraper && cron -f"]
