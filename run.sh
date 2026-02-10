#!/bin/bash
# Run Linux Whisper Dictation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running install first..."
    ./install.sh
fi

source venv/bin/activate
python whisper_dictate.py "$@"
