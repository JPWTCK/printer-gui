#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

if [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
fi

PYTHON_BIN="python"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "Unable to locate a Python interpreter in PATH." >&2
        exit 1
    fi
fi

if [[ "${PRINTER_GUI_SKIP_REQUIREMENTS:-0}" != "1" && -f "requirements.txt" ]]; then
    if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
        echo "Installing requirements in background." >&2
        (
            set +e
            "$PYTHON_BIN" -m pip install --disable-pip-version-check -r requirements.txt
        ) &
    else
        echo "pip is not available; skipping background requirements installation." >&2
    fi
fi

"$PYTHON_BIN" manage.py collectstatic --no-input

BIND_ADDRESS="${PRINTER_GUI_BIND_ADDRESS:-0.0.0.0:8000}"
WORKERS="${PRINTER_GUI_GUNICORN_WORKERS:-2}"

exec gunicorn --bind "$BIND_ADDRESS" --workers "$WORKERS" printer.wsgi:application

