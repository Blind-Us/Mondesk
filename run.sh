#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f config.json ] || cp config.example.json config.json
exec python server.py "$@"
