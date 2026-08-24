#!/usr/bin/env bash
# run_checks.sh — CI-style quality gate for L&D Command Center (P6.2).
#
# WHAT: one command that must pass before any merge/tag: full offline
#       test suite with a coverage floor across engines/model-layer/
#       storage/shell, plus a syntax gate over every source file.
# WHY:  Exit criteria E1/E7 of docs/PRODUCTION_PLAN.md.
# BREAKS IF DELETED: The release gate loses its single entry point.

set -euo pipefail
cd "$(dirname "$0")"

echo "== syntax gate =="
python3 - << 'PY'
import py_compile, sys
from pathlib import Path
files = [p for p in Path(".").rglob("*.py")
         if ".git" not in p.parts and "pagefile" not in p.name]
for f in files:
    py_compile.compile(str(f), doraise=True)
print(f"compiled {len(files)} files cleanly")
PY

echo "== offline suite (live deselected) with coverage floor 90% =="
python3 -m pytest --cov=engines --cov=model-layer --cov=storage \
    --cov=desktop_shell --cov-report=term-missing --cov-fail-under=90

echo "== ALL CHECKS PASSED =="
