#!/usr/bin/env python3
"""
Linux Whisper Dictation
A voice-to-text tool that types what you say at the cursor in any application.

Usage:
    python whisper_dictate.py

Default hotkey: Ctrl+Space (toggle recording)
Requires: input group membership for hotkey detection and text injection.
"""

import subprocess
import threading
import sys
import os
import json
import select
import time
import ctypes
from pathlib import Path

# Suppress noisy ALSA/JACK error messages from PortAudio during device enumeration.
# These are harmless warnings about unavailable sound servers (e.g. JACK not running).
try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _ALSA_ERR_HANDLER = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                          ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    _alsa_noop = _ALSA_ERR_HANDLER(lambda *_: None)
    _asound.snd_lib_error_set_handler(_alsa_noop)
except Exception:
    pass

# ============ Configuration ============

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {
    "hotkey": "<ctrl>+space",
    "model": "base.en",          # tiny.en, base.en, small.en, medium.en, large-v3
    "language": "en",
    "input_method": "auto",       # auto, ydotool, xdotool, wtype, clipboard
    "sound_feedback": True,
    "continuous_mode": False,
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            user_config = json.load(f)
            return {**DEFAULT_CONFIG, **user_config}
    return DEFAULT_CONFIG

def save_default_config():
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"Created config file: {CONFIG_PATH}")

config = load_config()

# ============ Input Simulation ============

def detect_input_method():
    """Detect the best input method for the current environment."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()

    if session_type == "wayland":
        if _has_cmd("ydotool"):
            return "ydotool"
        if _has_cmd("wtype"):
            return "wtype"

    if _has_cmd("xdotool"):
        return "xdotool"
    if _has_cmd("ydotool"):
        return "ydotool"

    return None

def _has_cmd(cmd):
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0

def type_text(text, method=None):
    """Type text at cursor using the appropriate tool. Returns True on success."""
    if not text.strip():
        return True

    method = method or config.get("input_method", "auto")
    if method == "auto":
        method = detect_input_method()

    if method == "clipboard":
        return _type_via_clipboard(text)

    if not method:
        print(f"[WARN] No input method available. Install ydotool.")
        print(f"[TEXT] {text}")
        return False

    try:
        if method == "xdotool":
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--", text],
                check=True, timeout=10
            )
        elif method == "ydotool":
            subprocess.run(
                ["ydotool", "type", "--", text],
                check=True, timeout=10
            )
        elif method == "wtype":
            subprocess.run(
                ["wtype", "--", text],
                check=True, timeout=10
            )
        return True

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[WARN] {method} failed: {e}")
        # Fall back to clipboard paste
        print("[INFO] Trying clipboard fallback...")
        return _type_via_clipboard(text)

def _type_via_clipboard(text):
    """Type text by copying to clipboard and simulating paste."""
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    try:
        if session_type == "wayland":
            subprocess.run(["wl-copy", "--", text], check=True, timeout=5)
            # ydotool key: Ctrl(29) down, V(47) down, V up, Ctrl up
            subprocess.run(
                ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
                check=True, timeout=5
            )
        else:
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode(), check=True, timeout=5
            )
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                check=True, timeout=5
            )
        return True

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[ERROR] Clipboard fallback also failed: {e}")
        print(f"[TEXT] {text}")
        return False

# ============ Sound Feedback ============

def play_sound(sound_type):
    """Play feedback sound (start/stop recording)."""
    if not config.get("sound_feedback", True):
        return
    try:
        if sound_type == "start":
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
                capture_output=True, timeout=1
            )
        elif sound_type == "stop":
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                capture_output=True, timeout=1
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

# ============ Desktop Notifications ============

def notify(summary, body="", urgency="normal"):
    """Send a desktop notification via notify-send (fire-and-forget).

    Falls back to print() if notify-send isn't available.
    urgency: 'low', 'normal', or 'critical'
    """
    try:
        cmd = [
            "notify-send",
            "--app-name=Whisper Dictate",
            f"--urgency={urgency}",
            summary,
        ]
        if body:
            cmd.append(body)
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"[NOTIFY] {summary}" + (f" - {body}" if body else ""))

# ============ Audio Health Monitor ============

class AudioHealthMonitor:
    """Background monitor that checks for working audio input devices.

    Sends desktop notifications on state transitions (mic connected/disconnected).
    """

    # Device name substrings that indicate virtual/loopback devices
    _VIRTUAL_NAMES = {"pipewire", "default", "null", "dummy", "loopback"}

    def __init__(self, check_interval=30):
        self.check_interval = check_interval
        self._mic_available = None  # None = unknown (first check)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AudioHealthMonitor")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _is_real_device(self, name):
        """Check if a device name looks like a real hardware device."""
        name_lower = name.lower()
        return not any(virt in name_lower for virt in self._VIRTUAL_NAMES)

    def _check_mic(self):
        """Check if any real audio input device is available."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            try:
                for i in range(pa.get_device_count()):
                    try:
                        info = pa.get_device_info_by_index(i)
                        if info.get("maxInputChannels", 0) > 0 and self._is_real_device(info.get("name", "")):
                            return True
                    except Exception:
                        continue
                return False
            finally:
                pa.terminate()
        except Exception as e:
            print(f"[WARN] Audio health check failed: {e}")
            return None  # unknown, don't change state

    def _run(self):
        """Background loop: check mic availability and notify on changes."""
        while not self._stop.is_set():
            available = self._check_mic()

            if available is None:
                # Check failed, skip this cycle
                pass
            elif self._mic_available is None:
                # First check — normal urgency so the user can dismiss it
                if not available:
                    notify(
                        "No Microphone Detected",
                        "Connect a microphone to use voice dictation.",
                    )
                    print("[WARN] No audio input device detected")
                self._mic_available = available
            elif available != self._mic_available:
                # State transition
                if available:
                    notify("Microphone Connected", "Voice dictation is ready.")
                    print("[INFO] Microphone connected")
                else:
                    notify(
                        "Microphone Disconnected",
                        "Voice dictation needs a microphone to work.",
                        urgency="critical",
                    )
                    print("[WARN] Microphone disconnected")
                self._mic_available = available

            self._stop.wait(self.check_interval)

# ============ Main Recorder ============

class WhisperDictation:
    def __init__(self):
        self.recorder = None
        self.is_recording = False
        self.is_processing = False
        self.lock = threading.Lock()
        self._processing_deadline = 0  # auto-reset safety net

        print(f"[INIT] Loading Whisper model: {config['model']}")
        print(f"[INIT] This may take a moment on first run...")

        # Prevent PipeWire/PulseAudio from ducking (lowering) other audio
        # when the microphone capture stream is opened. Without this, opening
        # a recording stream classified as "phone" or "communication" triggers
        # automatic volume reduction of music/video playback.
        os.environ.setdefault("PULSE_PROP_media.role", "music")

        from RealtimeSTT import AudioToTextRecorder
        self.recorder = AudioToTextRecorder(
            model=config["model"],
            language=config["language"],
            spinner=False,
            sample_rate=16000,
            silero_sensitivity=0.4,
            webrtc_sensitivity=2,
            post_speech_silence_duration=0.6,
            min_length_of_recording=0.5,
            min_gap_between_recordings=0,
            enable_realtime_transcription=False,
            on_recording_start=self._on_recording_start,
            on_recording_stop=self._on_recording_stop,
        )

        print(f"[READY] Model loaded. Press {config['hotkey']} to start dictating.")

    def _on_recording_start(self):
        print("[REC] Recording...")

    def _on_recording_stop(self):
        print("[REC] Processing...")

    def _process_text(self, text):
        """Called when transcription is complete."""
        try:
            if text and text.strip():
                print(f"[TEXT] {text}")
                type_text(text + " ")
        finally:
            # Always reset state, even if type_text raises an unexpected exception
            with self.lock:
                self.is_processing = False

    def _is_stuck(self):
        """Check if processing has been stuck too long (safety net)."""
        if self.is_processing and self._processing_deadline > 0:
            if time.time() > self._processing_deadline:
                print("[WARN] Processing timed out, resetting state...")
                self.is_processing = False
                self.is_recording = False
                self._processing_deadline = 0
                return True
        return False

    def toggle_recording(self):
        """Toggle recording on/off."""
        with self.lock:
            self._is_stuck()

            if self.is_processing:
                print("[BUSY] Still processing previous recording...")
                return

            if not self.is_recording:
                self.is_recording = True
                self.is_processing = True
                self._processing_deadline = time.time() + 120  # 2 minute safety timeout

                play_sound("start")

                def record():
                    try:
                        text = self.recorder.text()
                        self._process_text(text)
                    except Exception as e:
                        print(f"[ERROR] Recording failed: {e}")
                        with self.lock:
                            self.is_processing = False
                    finally:
                        with self.lock:
                            self.is_recording = False
                            self._processing_deadline = 0
                        play_sound("stop")

                threading.Thread(target=record, daemon=True).start()
            else:
                print("[INFO] Recording will stop when you stop speaking...")

# ============ Hotkey Listener (evdev) ============

def _init_evdev():
    """Import and validate evdev availability."""
    try:
        import evdev
        from evdev import ecodes
        return evdev, ecodes
    except ImportError:
        print("[ERROR] python-evdev is required but not installed.")
        print("        Install with: pip install evdev")
        sys.exit(1)

# Modifier key name -> evdev keycodes (left/right variants)
_MODIFIER_NAMES = {
    'ctrl':    'KEY_LEFTCTRL KEY_RIGHTCTRL',
    '<ctrl>':  'KEY_LEFTCTRL KEY_RIGHTCTRL',
    'alt':     'KEY_LEFTALT KEY_RIGHTALT',
    '<alt>':   'KEY_LEFTALT KEY_RIGHTALT',
    'shift':   'KEY_LEFTSHIFT KEY_RIGHTSHIFT',
    '<shift>': 'KEY_LEFTSHIFT KEY_RIGHTSHIFT',
    'super':   'KEY_LEFTMETA KEY_RIGHTMETA',
    '<super>': 'KEY_LEFTMETA KEY_RIGHTMETA',
    'cmd':     'KEY_LEFTMETA KEY_RIGHTMETA',
    '<cmd>':   'KEY_LEFTMETA KEY_RIGHTMETA',
}

# Non-modifier key names -> evdev keycode name
_KEY_NAMES = {
    'space': 'KEY_SPACE', 'enter': 'KEY_ENTER', 'tab': 'KEY_TAB',
    'esc': 'KEY_ESC', 'backspace': 'KEY_BACKSPACE', 'delete': 'KEY_DELETE',
    'up': 'KEY_UP', 'down': 'KEY_DOWN', 'left': 'KEY_LEFT', 'right': 'KEY_RIGHT',
    'home': 'KEY_HOME', 'end': 'KEY_END', 'pageup': 'KEY_PAGEUP', 'pagedown': 'KEY_PAGEDOWN',
    'insert': 'KEY_INSERT', 'pause': 'KEY_PAUSE', 'capslock': 'KEY_CAPSLOCK',
    **{f'f{i}': f'KEY_F{i}' for i in range(1, 13)},
}

def parse_hotkey_evdev(hotkey_str, ecodes):
    """Parse hotkey string into (modifier_sets, trigger_keycode).

    modifier_sets: list of frozensets, each containing equivalent keycodes
                   (e.g., frozenset({KEY_LEFTCTRL, KEY_RIGHTCTRL}))
    trigger_keycode: int keycode for the non-modifier key
    """
    parts = hotkey_str.lower().split('+')
    modifiers = []
    trigger = None

    for part in parts:
        part = part.strip()
        if part in _MODIFIER_NAMES:
            codes = frozenset(
                getattr(ecodes, name)
                for name in _MODIFIER_NAMES[part].split()
            )
            modifiers.append(codes)
        elif part in _KEY_NAMES:
            trigger = getattr(ecodes, _KEY_NAMES[part])
        elif len(part) == 1 and part.isalpha():
            trigger = getattr(ecodes, f'KEY_{part.upper()}', None)
        elif len(part) == 1 and part.isdigit():
            trigger = getattr(ecodes, f'KEY_{part}', None)

    # Support modifier-only hotkeys (e.g., just "alt")
    # Convert the modifier keycodes into trigger keycodes with no modifiers required
    if trigger is None and len(modifiers) == 1:
        trigger = modifiers[0]  # frozenset of equivalent keycodes (e.g., LEFT_ALT, RIGHT_ALT)
        modifiers = []

    return modifiers, trigger

def find_keyboard_devices(evdev, ecodes):
    """Find all keyboard input devices."""
    devices = []
    permission_denied = 0
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                keys = caps[ecodes.EV_KEY]
                # Accept devices with letter keys (standard keyboards)
                # or devices with the specific hotkey trigger key
                if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                    devices.append(dev)
        except PermissionError:
            permission_denied += 1
        except OSError:
            continue
    return devices, permission_denied

def run_hotkey_listener(hotkey_str, callback):
    """Block forever, listening for the hotkey combo and calling callback."""
    evdev, ecodes = _init_evdev()
    modifiers, trigger = parse_hotkey_evdev(hotkey_str, ecodes)

    if trigger is None:
        print(f"[ERROR] Could not parse hotkey trigger key from: {hotkey_str}")
        sys.exit(1)

    # Normalize trigger to a frozenset of keycodes for uniform handling
    if isinstance(trigger, int):
        trigger_keys = frozenset({trigger})
    else:
        trigger_keys = trigger  # already a frozenset from modifier-only hotkey

    keyboards, permission_denied = find_keyboard_devices(evdev, ecodes)
    if not keyboards:
        total_devices = len(list(Path("/dev/input/").glob("event*")))
        accessible = total_devices - permission_denied
        print("[ERROR] No keyboard devices found!")
        if permission_denied > 0:
            in_group = os.popen("id -nG").read().split()
            print(f"        {permission_denied} of {total_devices} input devices are inaccessible (permission denied).")
            if "input" not in in_group:
                print(f"        Your current session groups: {' '.join(in_group)}")
                print(f"        The 'input' group is NOT active in this session.")
                # Check if user is in the group in /etc/group but session hasn't picked it up
                import grp
                try:
                    input_members = grp.getgrnam("input").gr_mem
                    username = os.environ.get("USER", "")
                    if username in input_members:
                        print(f"        NOTE: '{username}' IS in the 'input' group in /etc/group,")
                        print(f"        but your desktop session hasn't picked it up yet.")
                        print(f"        You must FULLY LOG OUT of your desktop session and log back in.")
                        print(f"        (Closing a terminal or rebooting a service is not enough.)")
                    else:
                        print("        Add yourself to the 'input' group:")
                        print("          sudo usermod -aG input $USER")
                        print("        Then log out of your desktop session and log back in.")
                except KeyError:
                    print("        Add yourself to the 'input' group:")
                    print("          sudo usermod -aG input $USER")
                    print("        Then log out of your desktop session and log back in.")
            else:
                print("        You are in the 'input' group but no keyboard was detected.")
                print("        Your keyboard may not expose standard key capabilities.")
        else:
            print("        Make sure you're in the 'input' group:")
            print("          sudo usermod -aG input $USER")
            print("        Then log out and back in.")
        sys.exit(1)

    dev_names = ', '.join(d.name for d in keyboards)
    print(f"[INIT] Listening on: {dev_names}")

    pressed_keys = set()
    last_trigger = 0

    while True:
        try:
            r, _, _ = select.select(keyboards, [], [], 1.0)
            for dev in r:
                try:
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY:
                            continue
                        if event.value == 1:       # key down
                            pressed_keys.add(event.code)
                        elif event.value == 0:     # key up
                            pressed_keys.discard(event.code)

                        # Trigger on key-down of the trigger key
                        if event.code in trigger_keys and event.value == 1:
                            all_mods = all(
                                any(k in pressed_keys for k in mod_set)
                                for mod_set in modifiers
                            )
                            if all_mods:
                                now = time.time()
                                if now - last_trigger > 0.3:  # debounce
                                    last_trigger = now
                                    callback()
                except (OSError, IOError):
                    # Device disconnected, refresh list
                    time.sleep(0.5)
                    keyboards, _ = find_keyboard_devices(evdev, ecodes)
        except (OSError, IOError, ValueError):
            time.sleep(1)
            keyboards, _ = find_keyboard_devices(evdev, ecodes)

# ============ Main ============

def main():
    save_default_config()

    # Start audio health monitor early (before model load)
    audio_monitor = AudioHealthMonitor()
    audio_monitor.start()

    # Check for input method
    method = detect_input_method()
    if not method:
        print("[WARN] No input method found!")
        print("       Install ydotool: sudo apt install ydotool")
        print("       Then run: ./install.sh  (to set up permissions)")
        print("       Text will be printed to console instead.")
        notify(
            "No Input Method Found",
            "Install ydotool to enable typing. Text will be printed to console.",
            urgency="critical",
        )
    else:
        print(f"[INIT] Using input method: {method}")

    dictation = WhisperDictation()

    print(f"\n{'='*50}")
    print(f"  Linux Whisper Dictation")
    print(f"  Hotkey: {config['hotkey']}")
    print(f"  Model: {config['model']}")
    print(f"{'='*50}")
    print(f"\nPress {config['hotkey']} to start dictating.")
    print("Press Ctrl+C to exit.\n")

    notify("Whisper Dictate Ready", f"Press {config['hotkey']} to dictate.")

    try:
        run_hotkey_listener(config["hotkey"], dictation.toggle_recording)
    except KeyboardInterrupt:
        audio_monitor.stop()
        print("\n[EXIT] Goodbye!")

if __name__ == "__main__":
    main()
