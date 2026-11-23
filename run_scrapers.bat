@echo off
REM ============================================================================
REM  SOLARA full daily scraper pipeline
REM  Launched by the Windows Task Scheduler task "SOLARA Daily Scraper" (08:00).
REM  Runs run_daily.py = Amazon SP-API sales, Shopify re-pull, Blinkit/Swiggy/
REM  Zepto sales+SOH, Atlas WH stock, Amazon PI, Data Kiosk FC. NO EasyEcom.
REM ============================================================================
cd /d "C:\Users\accou\Documents\Projects\SOLARA-Data"
call "venv\Scripts\activate.bat"
if not exist "data\logs" mkdir "data\logs"
echo ==== run_scrapers.bat START %DATE% %TIME% ==== >> "data\logs\run_scrapers.log"
python run_daily.py >> "data\logs\run_scrapers.log" 2>&1
echo ==== run_scrapers.bat END   %DATE% %TIME% (exit %ERRORLEVEL%) ==== >> "data\logs\run_scrapers.log"
