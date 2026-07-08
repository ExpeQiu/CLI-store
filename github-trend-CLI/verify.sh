#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 -m pip install -q -e . 2>/dev/null || pip install -q -e .
github-trend --version
github-trend --help > /dev/null
github-trend fetch trending --demo --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['module'] == 'github-trending'
assert d['data_source'] == 'demo'
assert len(d['items']) >= 1
print('verify OK')
"
