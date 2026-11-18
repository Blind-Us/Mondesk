#!/usr/bin/env sh
# Checks this copy of Mondesk: packages, all tests and a demo run. Needs no account or key.
cd "$(dirname "$0")" || exit 1
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec python tools/check.py "$@"
