#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SERVICE_FILE="$SCRIPT_DIR/printergui.service"
DEFAULT_TARGET_DIR="/etc/systemd/system"

SERVICE_FILE="$DEFAULT_SERVICE_FILE"
TARGET_DIR="$DEFAULT_TARGET_DIR"
ENABLE_SERVICE=0
START_SERVICE=0

usage() {
    cat <<'USAGE'
Usage: install-service.bash [OPTIONS]

Install the printergui systemd service unit.

Options:
  -f, --service-file PATH  Path to the service unit file to install
                           (default: printergui.service next to this script)
  -t, --target-dir DIR     Directory to copy the service file into
                           (default: /etc/systemd/system)
      --enable             Enable the service with systemctl enable
      --start, --now       Start (activate) the service with systemctl start
  -h, --help               Show this help message
USAGE
}

while (($# > 0)); do
    case "$1" in
        -f|--service-file)
            if (($# < 2)); then
                echo "Missing argument for $1." >&2
                exit 1
            fi
            SERVICE_FILE="$2"
            shift 2
            ;;
        -t|--target-dir)
            if (($# < 2)); then
                echo "Missing argument for $1." >&2
                exit 1
            fi
            TARGET_DIR="$2"
            shift 2
            ;;
        --enable)
            ENABLE_SERVICE=1
            shift
            ;;
        --start|--now)
            START_SERVICE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
        *)
            echo "Unexpected positional argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if (($# > 0)); then
    echo "Unexpected positional arguments: $*" >&2
    usage >&2
    exit 1
fi

if [[ ! -f "$SERVICE_FILE" ]]; then
    echo "Service file '$SERVICE_FILE' does not exist." >&2
    exit 1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
    echo "Target directory '$TARGET_DIR' does not exist." >&2
    exit 1
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This script must be run as root to install systemd service files." >&2
    echo "Re-run with sudo or as root." >&2
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl is required but was not found in PATH." >&2
    exit 1
fi

SERVICE_BASENAME="$(basename "$SERVICE_FILE")"
TARGET_PATH="$TARGET_DIR/$SERVICE_BASENAME"

install -m 0644 "$SERVICE_FILE" "$TARGET_PATH"

echo "Installed '$SERVICE_BASENAME' to '$TARGET_DIR'."

systemctl daemon-reload

echo "Reloaded systemd manager configuration."

UNIT_NAME="${SERVICE_BASENAME%.service}"

if (( ENABLE_SERVICE )); then
    systemctl enable "$UNIT_NAME"
    echo "Enabled service '$UNIT_NAME'."
fi

if (( START_SERVICE )); then
    systemctl start "$UNIT_NAME"
    echo "Started service '$UNIT_NAME'."
fi

cat <<EOFMSG
Done. You can manage the service with:
  systemctl status $UNIT_NAME
  systemctl restart $UNIT_NAME
  systemctl stop $UNIT_NAME
EOFMSG

