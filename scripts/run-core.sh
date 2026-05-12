#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-src}"
exec python3 -m lifeops.server --host "${LIFEOPS_HOST:-127.0.0.1}" --port "${LIFEOPS_PORT:-8765}"
