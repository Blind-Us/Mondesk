#!/usr/bin/env sh
# Demo: scripted printer, music, quota and weather. No account, extension or key; settings are not saved.
cd "$(dirname "$0")" || exit 1
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
echo 'Open http://127.0.0.1:9362/'
exec python server.py --demo --port 9362 "$@"
