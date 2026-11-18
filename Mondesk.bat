@echo off
rem Mondesk from source, in its own window, without a console. First run sets up Python packages.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Python 3.10 or newer is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python.exe -m pip install -q -r requirements-desktop.txt || (pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" desktop.py %*
