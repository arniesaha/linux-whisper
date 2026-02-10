#!/usr/bin/env python3
"""
Linux Whisper Dictation
A simple voice-to-text tool that types what you say at the cursor.

Usage:
    python whisper_dictate.py

Default hotkey: Ctrl+Alt+Space (toggle recording)
"""

import subprocess
import threading
import sys
import os
import json
from pathlib import Path

# Check dependencies before importing
def check_dependencies():
    missing = []
    try:
        from RealtimeSTT import AudioToTextRecorder
    except ImportError:
        missing.append("RealtimeSTT")
    try:
        from pynput import keyboard
    except ImportError:
        missing.append("pynput")
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        sys.exit(1)

check_dependencies()

from RealtimeSTT import AudioToTextRecorder
from pynput import keyboard

# ============ Configuration ============

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {
    "hotkey": "<ctrl>+<alt>+space",
    "model": "base.en",  # tiny.en, base.en, small.en, medium.en, large-v3
    "language": "en",
    "input_method": "auto",  # auto, xdotool, ydotool, wtype
    "sound_feedback": True,
    "continuous_mode": False,  # If True, keeps listening after transcription
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
        # Prefer ydotool on Wayland (works everywhere)
        if subprocess.run(["which", "ydotool"], capture_output=True).returncode == 0:
            return "ydotool"
        if subprocess.run(["which", "wtype"], capture_output=True).returncode == 0:
            return "wtype"
    
    # X11 or fallback
    if subprocess.run(["which", "xdotool"], capture_output=True).returncode == 0:
        return "xdotool"
    
    if subprocess.run(["which", "ydotool"], capture_output=True).returncode == 0:
        return "ydotool"
    
    return None

def type_text(text, method=None):
    """Type text at cursor using the appropriate tool."""
    if not text.strip():
        return
    
    method = method or config.get("input_method", "auto")
    if method == "auto":
        method = detect_input_method()
    
    if not method:
        print(f"[ERROR] No input method available. Install xdotool or ydotool.")
        print(f"[TEXT] {text}")
        return
    
    try:
        if method == "xdotool":
            # xdotool types text directly
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True)
        
        elif method == "ydotool":
            # ydotool needs the daemon running
            subprocess.run(["ydotool", "type", "--", text], check=True)
        
        elif method == "wtype":
            # wtype for Wayland
            subprocess.run(["wtype", "--", text], check=True)
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to type text: {e}")
        print(f"[TEXT] {text}")
    except FileNotFoundError:
        print(f"[ERROR] {method} not found. Install it or change config.")
        print(f"[TEXT] {text}")

# ============ Sound Feedback ============

def play_sound(sound_type):
    """Play feedback sound (start/stop recording)."""
    if not config.get("sound_feedback", True):
        return
    
    # Use simple beep via paplay or aplay if available
    try:
        if sound_type == "start":
            # Higher pitch for start
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
                capture_output=True, timeout=1
            )
        elif sound_type == "stop":
            # Lower pitch for stop
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                capture_output=True, timeout=1
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Silently ignore if sounds not available

# ============ Main Recorder ============

class WhisperDictation:
    def __init__(self):
        self.recorder = None
        self.is_recording = False
        self.is_processing = False
        self.lock = threading.Lock()
        
        print(f"[INIT] Loading Whisper model: {config['model']}")
        print(f"[INIT] This may take a moment on first run...")
        
        self.recorder = AudioToTextRecorder(
            model=config["model"],
            language=config["language"],
            spinner=False,
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
        print("[REC] 🎤 Recording...")
    
    def _on_recording_stop(self):
        print("[REC] ⏹️  Processing...")
    
    def _process_text(self, text):
        """Called when transcription is complete."""
        if text and text.strip():
            print(f"[TEXT] {text}")
            type_text(text + " ")
        self.is_processing = False
    
    def toggle_recording(self):
        """Toggle recording on/off."""
        with self.lock:
            if self.is_processing:
                print("[BUSY] Still processing previous recording...")
                return
            
            if not self.is_recording:
                # Start recording
                self.is_recording = True
                self.is_processing = True
                play_sound("start")
                
                # Run in thread to not block hotkey listener
                def record():
                    try:
                        text = self.recorder.text()
                        self._process_text(text)
                    except Exception as e:
                        print(f"[ERROR] {e}")
                        self.is_processing = False
                    finally:
                        self.is_recording = False
                        play_sound("stop")
                
                threading.Thread(target=record, daemon=True).start()
            else:
                # Stop is handled automatically by voice activity detection
                print("[INFO] Recording will stop when you stop speaking...")

# ============ Hotkey Listener ============

def parse_hotkey(hotkey_str):
    """Parse hotkey string like '<ctrl>+<alt>+space' into pynput format."""
    parts = hotkey_str.lower().split('+')
    keys = set()
    
    for part in parts:
        part = part.strip()
        if part in ('<ctrl>', 'ctrl'):
            keys.add(keyboard.Key.ctrl)
        elif part in ('<alt>', 'alt'):
            keys.add(keyboard.Key.alt)
        elif part in ('<shift>', 'shift'):
            keys.add(keyboard.Key.shift)
        elif part in ('<super>', 'super', '<cmd>', 'cmd'):
            keys.add(keyboard.Key.cmd)
        elif part == 'space':
            keys.add(keyboard.Key.space)
        elif len(part) == 1:
            keys.add(keyboard.KeyCode.from_char(part))
        else:
            # Try as key name
            try:
                keys.add(getattr(keyboard.Key, part))
            except AttributeError:
                keys.add(keyboard.KeyCode.from_char(part[0]))
    
    return keys

def main():
    save_default_config()
    
    # Check for input method
    method = detect_input_method()
    if not method:
        print("[WARN] No input method found!")
        print("       Install one of: xdotool (X11), ydotool (Wayland/X11), wtype (Wayland)")
        print("       Text will be printed to console instead.")
    else:
        print(f"[INIT] Using input method: {method}")
    
    dictation = WhisperDictation()
    
    hotkey_keys = parse_hotkey(config["hotkey"])
    current_keys = set()
    
    def on_press(key):
        current_keys.add(key)
        if hotkey_keys.issubset(current_keys):
            dictation.toggle_recording()
    
    def on_release(key):
        try:
            current_keys.discard(key)
        except KeyError:
            pass
    
    print(f"\n{'='*50}")
    print(f"  Linux Whisper Dictation")
    print(f"  Hotkey: {config['hotkey']}")
    print(f"  Model: {config['model']}")
    print(f"{'='*50}")
    print(f"\nPress {config['hotkey']} to start dictating.")
    print("Press Ctrl+C to exit.\n")
    
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n[EXIT] Goodbye!")

if __name__ == "__main__":
    main()
