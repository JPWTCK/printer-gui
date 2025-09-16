#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

if [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
fi

BIND_ADDRESS="${PRINTER_GUI_BIND_ADDRESS:-0.0.0.0:8000}"

exec python3 manage.py runserver "$BIND_ADDRESS"

