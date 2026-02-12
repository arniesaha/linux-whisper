#!/bin/bash
# Run Linux Whisper Dictation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if the systemd service is already running
if systemctl --user is-active whisper-dictate.service &>/dev/null; then
    echo "[WARN] whisper-dictate.service is already running!"
    echo "       Running a second instance will cause conflicts with"
    echo "       keyboard input device access (evdev)."
    echo ""
    echo "  To stop the service first:"
    echo "    systemctl --user stop whisper-dictate"
    echo ""
    read -rp "Continue anyway? [y/N] " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running install first..."
    ./install.sh
fi

source venv/bin/activate
python whisper_dictate.py "$@"
