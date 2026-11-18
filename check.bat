@echo off
rem Checks this copy of Mondesk: packages, all tests and a demo run. Needs no account or key.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python tools\check.py %*
