@echo off
cd /d D:\Develop\codex\stockapp_notion
".venv\Scripts\python.exe" -m stockapp_notion.cli daily-update >> logs\cron.log 2>&1
