#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -q -e ".[dev]"

invest --version
invest --help > /dev/null

invest market score --demo --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['module'] == 'market-score'
assert d['data_source'] == 'demo'
assert 'total' in d
assert 'components' in d
print('market-score OK')
"

invest account status --demo --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['module'] == 'account-status'
assert d['data_source'] == 'demo'
assert 'account' in d
print('account-status OK')
"

invest market macro --demo --format json | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['module'] == 'market-macro'
assert d['data_source'] == 'demo'
assert len(d['items']) >= 1
print('market-macro OK')
"

python -m pytest -q tests/

echo "verify OK"
