# Linux Whisper Dictation

A simple, local voice-to-text tool for Linux. Press a hotkey, speak, and it types what you said at your cursor.

## Features

- 🎤 Local transcription using Whisper (no cloud, no API keys)
- ⌨️ Types directly at cursor (works in any app)
- 🔊 Audio feedback for start/stop
- ⚙️ Configurable hotkey and model size
- 🐧 Supports X11 and Wayland

## Requirements

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt install python3-pip python3-venv portaudio19-dev ffmpeg
# For X11:
sudo apt install xdotool
# For Wayland:
sudo apt install ydotool
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip portaudio ffmpeg
# For X11:
sudo pacman -S xdotool
# For Wayland:
sudo pacman -S ydotool
```

**Fedora:**
```bash
sudo dnf install python3-pip python3-devel portaudio-devel ffmpeg
sudo dnf install xdotool  # X11
sudo dnf install ydotool  # Wayland
```

### Wayland Note (ydotool)

If using Wayland with ydotool, you need the daemon running:
```bash
# Start the daemon (needs to run in background)
sudo ydotoold &

# Or create a systemd service (recommended)
sudo systemctl enable --now ydotool
```

You may also need to add your user to the `input` group:
```bash
sudo usermod -aG input $USER
# Log out and back in for this to take effect
```

## Installation

```bash
# Clone or copy the project
cd ~/projects/linux-whisper  # or wherever you put it

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Activate venv if not already
source venv/bin/activate

# Run the dictation tool
python whisper_dictate.py
```

**First run will download the Whisper model (~150MB for base.en).**

### Controls

- **Ctrl+Alt+Space** (default): Toggle recording
- Recording stops automatically when you stop speaking
- Transcribed text is typed at your cursor

## Configuration

Edit `config.json` to customize:

```json
{
  "hotkey": "<ctrl>+<alt>+space",
  "model": "base.en",
  "language": "en",
  "input_method": "auto",
  "sound_feedback": true,
  "continuous_mode": false
}
```

### Model Options

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `tiny.en` | ~75MB | Fastest | Good |
| `base.en` | ~150MB | Fast | Better |
| `small.en` | ~500MB | Medium | Great |
| `medium.en` | ~1.5GB | Slow | Excellent |
| `large-v3` | ~3GB | Slowest | Best |

For English-only, `.en` models are faster and often more accurate.

### Hotkey Format

Examples:
- `<ctrl>+<alt>+space`
- `<ctrl>+<shift>+d`
- `<super>+v`

## One-Liner Install

```bash
cd ~ && git clone https://your-repo/linux-whisper.git && cd linux-whisper && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python whisper_dictate.py
```

Or if copying from NAS:
```bash
scp -r arnab@nas:/home/Arnab/clawd/projects/linux-whisper ~/projects/ && cd ~/projects/linux-whisper && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python whisper_dictate.py
```

## Troubleshooting

### "No input method found"
Install xdotool (X11) or ydotool (Wayland):
```bash
# Check your session type
echo $XDG_SESSION_TYPE
```

### ydotool permission denied
Make sure ydotoold daemon is running and you're in the input group.

### Audio not working
Make sure you have a working microphone:
```bash
arecord -l  # List audio devices
```

### Hotkey not detected
On Wayland, some hotkey listeners require additional permissions. Try running with sudo for testing, then set up proper permissions.

## License

MIT - do whatever you want with it.
