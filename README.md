# Linux Whisper Dictation

A local voice-to-text tool for Linux. Press a hotkey, speak, and it types what you said at your cursor — in any app (browser, editor, terminal, etc.).

Works on both X11 and Wayland (including GNOME).

## Features

- Local transcription using Whisper (no cloud, no API keys)
- Types directly at cursor in any focused application
- Works on Wayland (GNOME, KDE, Sway, Hyprland) and X11
- Audio feedback for start/stop
- Configurable hotkey and model size
- Clipboard fallback if direct typing fails

## Quick Start

```bash
git clone <repo-url> ~/dev/linux-whisper
cd ~/dev/linux-whisper
./install.sh    # Installs deps, sets up permissions
# Log out and back in (required for input group)
./run.sh        # Start dictating
```

## Requirements

### System Dependencies

The install script handles these automatically, but for reference:

**Ubuntu/Debian:**
```bash
sudo apt install python3-pip python3-venv portaudio19-dev ffmpeg ydotool wl-clipboard
```

### Permissions (handled by install.sh)

Both hotkey detection (evdev) and text injection (ydotool) require kernel-level access:

1. **input group** — your user must be in the `input` group
2. **uinput device** — `/dev/uinput` must be accessible to the `input` group
3. **ydotoold daemon** — must be running as a user service

```bash
# The install script does all of this, but manually:
sudo usermod -aG input $USER
echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
systemctl --user enable --now ydotoold.service
# Log out and back in
```

## Usage

```bash
./run.sh
```

First run downloads the Whisper model (~150MB for base.en).

### Controls

- **Ctrl+Space** (default): Start recording
- Recording stops automatically when you stop speaking (VAD)
- Transcribed text is typed at your cursor in the focused app

## Configuration

Edit `config.json`:

```json
{
  "hotkey": "<ctrl>+space",
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

### Input Methods

| Method | X11 | Wayland (GNOME) | Wayland (wlroots) |
|--------|-----|-----------------|-------------------|
| `ydotool` | Yes | Yes | Yes |
| `xdotool` | Yes | No | No |
| `wtype` | No | No | Yes |
| `clipboard` | Yes | Yes | Yes |

`auto` picks the best method for your session. Falls back to clipboard paste if typing fails.

### Hotkey Format

Examples: `<ctrl>+space`, `<ctrl>+<shift>+d`, `<super>+v`, `<alt>+<shift>+r`

## How It Works

1. **Hotkey detection** via `python-evdev` — reads keyboard events at the kernel level (works on X11 and Wayland)
2. **Audio capture** via RealtimeSTT — records until voice activity stops
3. **Transcription** via faster-whisper — local Whisper model, no cloud
4. **Text injection** via `ydotool` — types at cursor via uinput (kernel-level, below compositor)
5. **Clipboard fallback** — if ydotool typing fails, copies to clipboard and pastes with Ctrl+V

## Troubleshooting

### "No keyboard devices found"
You need to be in the `input` group:
```bash
sudo usermod -aG input $USER
# Log out and back in
```

### ydotool "failed to open uinput device"
The udev rule for `/dev/uinput` is missing or permissions aren't applied:
```bash
# Check current permissions
ls -la /dev/uinput
# Should be: crw-rw---- root input

# If not, re-run install.sh or:
echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### ydotoold not running
```bash
systemctl --user status ydotoold
systemctl --user start ydotoold
```

### Audio not working
```bash
arecord -l  # List audio devices
```

## Architecture

See [RESEARCH.md](RESEARCH.md) for detailed analysis of alternatives and design decisions.

## License

MIT
