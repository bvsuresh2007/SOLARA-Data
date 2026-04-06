@echo off
cd /d C:\Users\accou\Documents\Projects\SOLARA-Data
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python -m scrapers.hourly_shopify_sync >> data\logs\hourly_shopify_sync.log 2>&1
