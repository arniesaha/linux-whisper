# Research: System-Wide Dictation on Linux

## Goal

Build a WhisperFlow/Wispr Flow equivalent for Linux: press a hotkey, speak, and have
transcribed text typed into any focused application (browser, editor, terminal, etc.).

## Wispr Flow (Commercial Reference)

[Wispr Flow](https://wisprflow.ai) is a commercial macOS/Windows dictation tool. No Linux support.
It captures audio, transcribes via cloud, and types at cursor. It also captures screenshots
for context-aware rewriting (privacy concern). Our goal is a local, privacy-respecting equivalent.

## Existing Linux Tools

| Tool | Engine | Text Output | Hotkey | Platform | Notes |
|------|--------|-------------|--------|----------|-------|
| [nerd-dictation](https://github.com/ideasman42/nerd-dictation) | VOSK | xdotool/ydotool/wtype | External (sxhkd/DE) | X11+Wayland | Simple, hackable, but VOSK is less accurate than Whisper |
| [SoupaWhisper](https://github.com/ksred/soupawhisper) | faster-whisper | xclip+xdotool | pynput (F12) | X11 only | Clean push-to-talk, but X11 only |
| [whisper-overlay](https://github.com/oddlama/whisper-overlay) | faster-whisper/RealtimeSTT | Wayland virtual-keyboard | evdev | Wayland (wlroots only) | Real-time overlay, but no GNOME support |
| [whisprd](https://github.com/AgenticToaster/whisprd) | faster-whisper | uinput | Global hotkey | X11+Wayland | Voice commands, GUI available |
| [Speech Note](https://github.com/mkiol/dsnote) | whisper.cpp/VOSK | GlobalShortcuts portal | KDE/GNOME 48+ | Wayland | Full GUI app, heavier |
| [OpenWhispr](https://github.com/HeroTools/open-whispr) | Whisper | D-Bus GlobalShortcuts | GNOME Wayland | Wayland | Cross-platform, GNOME-aware |

**Conclusion**: None are a drop-in replacement. Our RealtimeSTT + ydotool approach is the most
practical for GNOME Wayland. The main gaps were: pynput doesn't work on Wayland, ydotool
needs proper setup, and error handling needed improvement.

## Text Injection Methods

| Method | X11 | Wayland (GNOME) | Wayland (wlroots) | TTY | Permissions | Notes |
|--------|-----|-----------------|-------------------|-----|-------------|-------|
| xdotool | Yes | No | No | No | None | X11 XTEST extension |
| ydotool | Yes | Yes | Yes | Yes | input group + uinput | Kernel-level via uinput |
| dotool | Yes | Yes | Yes | Yes | input group + uinput | stdin-based, similar to ydotool |
| wtype | No | No | Yes | No | None | virtual-keyboard-v1 (no GNOME) |
| wl-copy + paste | No | Yes | Yes | No | None + ydotool for paste | Clipboard-based, instant |
| evdev/uinput (Python) | Yes | Yes | Yes | Yes | input group | Zero external deps |

**Chosen**: ydotool (primary) with wl-copy+paste clipboard fallback. ydotool is the only
universal option that works on GNOME Wayland.

## Hotkey Detection Methods

| Method | X11 | Wayland | Push-to-Talk | Notes |
|--------|-----|---------|--------------|-------|
| pynput | Yes | **No** | Yes | Uses X11 backend, broken on Wayland |
| python-evdev | Yes | Yes | Yes | Kernel-level, needs input group |
| DE shortcuts (gsettings) | Yes | Yes | No (toggle only) | No key-release detection |
| XDG Portal GlobalShortcuts | No | Partial (GNOME 48+) | No | Emerging standard |
| sxhkd | Yes | No | Possible | X11-only daemon |

**Chosen**: python-evdev. Works on all display servers at the kernel level.
Same `input` group permission needed for ydotool anyway.

## X11 vs Wayland Key Differences

Wayland's security model intentionally prevents apps from:
- Reading keyboard input from other windows (no global hotkeys via X11 APIs)
- Injecting keyboard events into other windows (no xdotool)
- Enumerating other windows

**Workaround**: Both evdev (hotkey reading) and uinput/ydotool (text injection) operate at the
kernel level, below the compositor. The compositor sees them as real hardware input.

**Permission requirement**: User must be in the `input` group with udev rules for `/dev/uinput`.

## Architecture Decision

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Hotkey Listener │     │  Audio Capture    │     │  Text Output    │
│  (python-evdev)  │────>│  (RealtimeSTT/   │────>│  (ydotool)      │
│  kernel-level    │     │   sounddevice)   │     │  uinput-based   │
└─────────────────┘     └──────────────────┘     │  + clipboard    │
                                │                 │  fallback       │
                                v                 └─────────────────┘
                        ┌──────────────────┐
                        │  Whisper Model    │
                        │  (faster-whisper) │
                        │  local, no cloud  │
                        └──────────────────┘
```

- **Daemon**: Keeps Whisper model warm in memory (model load takes seconds)
- **Hybrid toggle+VAD**: Press hotkey to start, auto-stop on silence via VAD
- **Local transcription**: faster-whisper via RealtimeSTT (no API keys, no cloud)
- **Clipboard fallback**: If ydotool type fails, falls back to wl-copy + Ctrl+V paste

## Permission Setup Required

```bash
# 1. Add user to input group (for evdev + ydotool)
sudo usermod -aG input $USER

# 2. Create udev rule for /dev/uinput
echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# 3. Start ydotoold daemon
systemctl --user enable --now ydotoold.service

# 4. Log out and back in (for group membership to take effect)
```
