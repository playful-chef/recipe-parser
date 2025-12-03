#!/usr/bin/env bash
set -euo pipefail
PYTHON="${PYTHON:-python3.12}"
VENV="${VENV:-.venv}"
if [ ! -d "$VENV" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install uv
"$VENV/bin/uv" pip install .
"$VENV/bin/playwright" install --with-deps chromium
