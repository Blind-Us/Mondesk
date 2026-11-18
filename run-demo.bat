@echo off
rem Demo: scripted printer, music, quota and weather. No account, extension or key; settings are not saved.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
start "" http://127.0.0.1:9362/
python server.py --demo --port 9362 %*
