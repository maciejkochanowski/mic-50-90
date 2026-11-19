#!/usr/bin/env bash
# Software verification: source integrity, self-test and Python tests.
# Usage: bash verify.sh [MANIFEST]
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
[ -x "$PY" ] || PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
[ -x "$PY" ] || { echo "No Python interpreter found"; exit 2; }
MAN="${1:-PACKAGE_MANIFEST.sha256}"
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
echo "1/3 Source integrity"
"$PY" scripts/refresh_package_manifest.py --check --manifest "$MAN"
echo "2/3 Offline software self-test"
"$PY" reproducibility/self_test.py
echo "3/3 Python tests"
"$PY" -m pytest tests -q -rs
echo "PASS: software source integrity, controlled report and Python tests"
