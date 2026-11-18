#!/usr/bin/env sh
# Mondesk from source (Linux / macOS). First run sets up the Python packages.
#   ./mondesk.sh            the panel (in its own window when a web view is available, otherwise the browser)
#   ./mondesk.sh --demo     scripted data: no printer, account or key; nothing is saved
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  python3 -m venv .venv || { echo "Python 3.10 or newer is needed"; exit 1; }
  .venv/bin/python -m pip install -q -r requirements-desktop.txt || exit 1
fi
exec .venv/bin/python desktop.py "$@"
