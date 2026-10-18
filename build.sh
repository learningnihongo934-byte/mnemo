#!/usr/bin/env bash
# Build Mnemo: Python brain (virtualenv) + desktop app (Electron).
# Usage: ./build.sh            then  ./run.sh
#        ./build.sh --app      also packages Mnemo.app and installs it in /Applications
#        ./build.sh --test     also runs the test suite
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Python environment (.venv)"
if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
else
  PY=$(command -v python3.12 || command -v python3)
  [ -d .venv ] || "$PY" -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

echo "==> Desktop app (app/node_modules)"
(cd app && npm install)

for arg in "$@"; do
  case "$arg" in
    --test) echo "==> Tests"; .venv/bin/python -m pytest -q tests ;;
    --app) ./package-app.sh --install ;;
  esac
done

echo "Done. Start Mnemo with ./run.sh (or open Mnemo from Applications if you used --app)"
