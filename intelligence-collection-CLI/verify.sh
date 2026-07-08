#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 -m pip install -q -e . 2>/dev/null || pip install -q -e .
intel-collect --version
intel-collect --help > /dev/null
intel-collect intel feed --demo --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['module'] == 'intel-feed'
assert d['data_source'] == 'demo'
assert len(d['items']) >= 1
print('verify OK')
"
