#!/bin/bash
# Linux Whisper Dictation - Quick Install Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  Linux Whisper Dictation - Installer"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 is required but not installed."
    exit 1
fi

# Check for input method
INPUT_METHOD=""
if command -v xdotool &> /dev/null; then
    INPUT_METHOD="xdotool"
elif command -v ydotool &> /dev/null; then
    INPUT_METHOD="ydotool"
elif command -v wtype &> /dev/null; then
    INPUT_METHOD="wtype"
fi

if [ -z "$INPUT_METHOD" ]; then
    echo "[WARN] No input method found!"
    echo "       Install one of the following:"
    echo ""
    if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
        echo "       For Wayland: sudo apt install ydotool"
    else
        echo "       For X11: sudo apt install xdotool"
    fi
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "[OK] Found input method: $INPUT_METHOD"
fi

# Create venv
echo ""
echo "[SETUP] Creating virtual environment..."
python3 -m venv venv

# Activate and install
echo "[SETUP] Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "To run:"
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  python whisper_dictate.py"
echo ""
echo "Or use the run script:"
echo "  ./run.sh"
echo ""
