#!/usr/bin/env bash
# Software-only verification; article material is maintained separately.
# Usage: bash verify.sh [MANIFEST]
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
[ -x "$PY" ] || PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
[ -x "$PY" ] || { echo "No Python interpreter found"; exit 2; }
MAN="${1:-PACKAGE_MANIFEST.sha256}"
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
echo "1/4 Source integrity"
"$PY" scripts/refresh_package_manifest.py --check --manifest "$MAN"
echo "2/4 Offline software self-test"
"$PY" reproducibility/self_test.py
echo "3/4 Python tests"
"$PY" -m pytest tests -q -rs
echo "4/4 JavaScript form tests"
node --test "tests/*.cjs"
echo "PASS: software source integrity, controlled report, Python and JavaScript tests"
