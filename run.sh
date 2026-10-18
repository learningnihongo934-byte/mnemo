#!/usr/bin/env bash
# Start the Mnemo desktop app (it launches the Python brain itself).
set -euo pipefail
cd "$(dirname "$0")/app"
exec npx electron .
