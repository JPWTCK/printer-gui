#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="$PROJECT_ROOT/venv"
VENV_ACTIVATE="$VENV_DIR/bin/activate"
VENV_PYTHON="$VENV_DIR/bin/python"

if [[ ! -f "$VENV_ACTIVATE" ]]; then
    echo "Virtual environment not found at $VENV_ACTIVATE; creating it now." >&2
    if ! command -v python3 >/dev/null 2>&1; then
        echo "python3 is required to create the virtual environment but was not found in PATH." >&2
        exit 1
    fi
    python3 -m venv "$VENV_DIR"
fi

if [[ ! -f "$VENV_ACTIVATE" ]]; then
    echo "Failed to create the virtual environment at $VENV_DIR." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_ACTIVATE"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Python interpreter not found at $VENV_PYTHON. The virtual environment may be corrupted." >&2
    exit 1
fi

PYTHON_BIN="$VENV_PYTHON"

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

