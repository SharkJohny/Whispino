#!/usr/bin/env python3
"""Superwhisper-like dictation for macOS using mlx-whisper.

Hold the configured hotkey (default: Right Command) to record.
On release, the audio is transcribed locally and pasted into the focused field.
"""
from __future__ import annotations

import json
import math
import os
import queue
import random
import subprocess
import threading
import time

import mlx_whisper
import numpy as np
import objc
import rumps
import sounddevice as sd
from AppKit import (
    NSApplication,
    NSApplicationActivateAllWindows,
    NSApplicationActivateIgnoringOtherApps,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSBundle,
    NSColor,
    NSEvent,
    NSPanel,
    NSRectFill,
    NSScreen,
    NSStatusWindowLevel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
    NSWorkspace,
)
from Foundation import NSMakePoint, NSMakeRect, NSProcessInfo
from PyObjCTools import AppHelper
from pynput import keyboard
from pynput.keyboard import Controller, Key

# ---- App metadata ---------------------------------------------------------
APP_NAME = "WhisperDictate"
CONFIG_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

# ---- Audio / overlay constants -------------------------------------------
SAMPLE_RATE = 16_000
MIN_RECORDING_SEC = 0.3
OVERLAY_BARS = 24
OVERLAY_WIDTH = 220
OVERLAY_HEIGHT = 64
OVERLAY_CURSOR_OFFSET = 28
START_SOUND = "/System/Library/Sounds/Tink.aiff"
STOP_SOUND = "/System/Library/Sounds/Pop.aiff"

# ---- User-selectable options ---------------------------------------------
HOTKEY_OPTIONS: dict[str, str] = {
    "Right ⌘": "cmd_r",
    "Left ⌘": "cmd_l",
    "Right ⌥": "alt_r",
    "Left ⌥": "alt_l",
    "Right ⌃": "ctrl_r",
    "F13": "f13",
    "F18": "f18",
    "F19": "f19",
}

MODEL_OPTIONS: dict[str, str] = {
    "Large v3 Turbo (fast, ~1.5 GB)": "mlx-community/whisper-large-v3-turbo",
    "Large v3 (best, ~3 GB)":         "mlx-community/whisper-large-v3-mlx",
    "Medium (~1.5 GB)":               "mlx-community/whisper-medium-mlx",
    "Small (~0.5 GB)":                "mlx-community/whisper-small-mlx",
    "Base (~150 MB)":                 "mlx-community/whisper-base-mlx",
    "Tiny (~80 MB)":                  "mlx-community/whisper-tiny-mlx",
}

LANGUAGE_OPTIONS: dict[str, str | None] = {
    "Auto-detect": None,
    "Čeština":     "cs",
    "English":     "en",
    "Slovenčina":  "sk",
    "Deutsch":     "de",
    "Français":    "fr",
    "Español":     "es",
}

DEFAULT_CONFIG: dict = {
    "hotkey":      "cmd_r",
    "model":       "mlx-community/whisper-large-v3-turbo",
    "language":    "cs",
    "play_sounds": True,
    "auto_paste":  True,
    "pause_media": True,
}

MEDIA_APPS = ("Music", "Spotify")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def resolve_hotkey(name: str):
    return getattr(Key, name, Key.cmd_r)


def play_sound(path: str) -> None:
    subprocess.Popen(
        ["afplay", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _osascript(script: str, timeout: float = 1.0) -> str | None:
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def pause_playing_media() -> list[str]:
    """Pause Music / Spotify if they're currently playing. Returns what was paused."""
    paused: list[str] = []
    running = _osascript(
        'tell application "System Events" to get name of every process'
    ) or ""
    for app in MEDIA_APPS:
        if app not in running:
            continue
        state = _osascript(f'tell application "{app}" to return (player state as string)')
        if state == "playing":
            _osascript(f'tell application "{app}" to pause')
            paused.append(app)
    return paused


def resume_media(apps: list[str]) -> None:
    for app in apps:
        _osascript(f'tell application "{app}" to play')


# ---- Login Item helpers --------------------------------------------------
LOGIN_ITEM_NAME = "WhisperDictate"


def running_app_path() -> str | None:
    """Return the path to the .app bundle if we're launched from one, else None."""
    bp = NSBundle.mainBundle().bundlePath()
    if bp and str(bp).endswith(".app"):
        return str(bp)
    return None


def is_login_item() -> bool:
    result = _osascript(
        'tell application "System Events" to get the name of every login item'
    )
    if not result:
        return False
    names = [n.strip() for n in result.split(",")]
    return LOGIN_ITEM_NAME in names


def set_login_item(enabled: bool) -> None:
    # Always remove any existing entries first, so paths/dupes are clean.
    _osascript(
        f'tell application "System Events" to delete '
        f'(every login item whose name is "{LOGIN_ITEM_NAME}")'
    )
    if enabled:
        path = running_app_path()
        if not path:
            return
        _osascript(
            f'tell application "System Events" to make login item at end '
            f'with properties {{path:"{path}", hidden:true}}'
        )


# ---- Overlay window -------------------------------------------------------
class WaveView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(WaveView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._bars = [0.0] * OVERLAY_BARS
        self._transcribing = False
        return self

    def pushLevel_(self, level):  # noqa: N802
        self._bars = self._bars[1:] + [float(level)]
        self.setNeedsDisplay_(True)

    def setTranscribing_(self, flag):  # noqa: N802
        self._transcribing = bool(flag)
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):  # noqa: N802, ARG002
        bounds = self.bounds()
        NSColor.clearColor().set()
        NSRectFill(bounds)

        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 16.0, 16.0)
        NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.88).set()
        bg.fill()

        w = bounds.size.width
        h = bounds.size.height
        n = len(self._bars)
        bar_w = 4.0
        gap = 4.0
        total = n * (bar_w + gap) - gap
        x = (w - total) / 2.0

        if self._transcribing:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.45, 0.75, 1.0, 1.0)
        else:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.35, 0.35, 1.0)
        color.set()

        for level in self._bars:
            bar_h = max(4.0, min(level, 1.0) * (h - 24.0))
            y = (h - bar_h) / 2.0
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, bar_w, bar_h), 2.0, 2.0
            )
            path.fill()
            x += bar_w + gap


def make_overlay() -> tuple[NSPanel, WaveView]:
    w, h = OVERLAY_WIDTH, OVERLAY_HEIGHT
    frame = NSMakeRect(0, 0, w, h)
    window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        frame,
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )
    window.setBackgroundColor_(NSColor.clearColor())
    window.setOpaque_(False)
    window.setLevel_(NSStatusWindowLevel)
    window.setIgnoresMouseEvents_(True)
    window.setHasShadow_(True)
    window.setHidesOnDeactivate_(False)
    window.setReleasedWhenClosed_(False)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorIgnoresCycle
    )
    view = WaveView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    window.setContentView_(view)
    return window, view


def position_overlay_near_cursor(window) -> None:
    mouse = NSEvent.mouseLocation()
    w, h = OVERLAY_WIDTH, OVERLAY_HEIGHT
    screen = None
    for s in NSScreen.screens():
        f = s.frame()
        if (f.origin.x <= mouse.x <= f.origin.x + f.size.width
                and f.origin.y <= mouse.y <= f.origin.y + f.size.height):
            screen = s
            break
    if screen is None:
        screen = NSScreen.mainScreen()
    sf = screen.frame()

    x = mouse.x - w / 2.0
    y = mouse.y + OVERLAY_CURSOR_OFFSET
    x = max(sf.origin.x + 8, min(x, sf.origin.x + sf.size.width - w - 8))
    if y + h > sf.origin.y + sf.size.height - 8:
        y = mouse.y - h - OVERLAY_CURSOR_OFFSET
    window.setFrameOrigin_(NSMakePoint(x, y))


# ---- Main app -------------------------------------------------------------
class Dictation(rumps.App):
    def __init__(self) -> None:
        super().__init__("🎙", quit_button=None)
        # Hide the Dock icon and rename the process so the app presents itself
        # as "WhisperDictate" instead of "Python" in Force Quit / Activity Monitor.
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        NSProcessInfo.processInfo().setProcessName_(APP_NAME)

        self.cfg = load_config()

        self._recording = False
        self._audio_q: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._start_ts = 0.0
        self._lock = threading.Lock()
        self._kb = Controller()
        self._current_level = 0.0
        self._target_app = None
        self._paused_media: list[str] = []

        self._overlay, self._wave = make_overlay()
        self._build_menu()

        self._overlay_timer = rumps.Timer(self._tick_overlay, 0.05)
        self._overlay_timer.start()

        threading.Thread(target=self._warmup, daemon=True).start()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    # ---- Menu -------------------------------------------------------------
    def _build_menu(self) -> None:
        hotkey = rumps.MenuItem("Hotkey")
        for label, name in HOTKEY_OPTIONS.items():
            mi = rumps.MenuItem(label, callback=self._pick_hotkey)
            mi.state = 1 if name == self.cfg["hotkey"] else 0
            hotkey.add(mi)

        model = rumps.MenuItem("Model")
        for label, repo in MODEL_OPTIONS.items():
            mi = rumps.MenuItem(label, callback=self._pick_model)
            mi.state = 1 if repo == self.cfg["model"] else 0
            model.add(mi)

        lang = rumps.MenuItem("Language")
        for label, code in LANGUAGE_OPTIONS.items():
            mi = rumps.MenuItem(label, callback=self._pick_language)
            mi.state = 1 if code == self.cfg["language"] else 0
            lang.add(mi)

        sounds = rumps.MenuItem("Play sounds", callback=self._toggle_sounds)
        sounds.state = 1 if self.cfg["play_sounds"] else 0

        paste = rumps.MenuItem("Auto-paste", callback=self._toggle_paste)
        paste.state = 1 if self.cfg["auto_paste"] else 0

        pause_media_item = rumps.MenuItem(
            "Pause music while recording", callback=self._toggle_pause_media
        )
        pause_media_item.state = 1 if self.cfg["pause_media"] else 0

        autostart_item = rumps.MenuItem(
            "Start at login", callback=self._toggle_autostart
        )
        if running_app_path() is None:
            autostart_item.title = "Start at login (install .app first)"
            autostart_item.set_callback(None)  # disable
        else:
            autostart_item.state = 1 if is_login_item() else 0

        self.menu = [
            hotkey, model, lang,
            None,
            sounds, paste, pause_media_item, autostart_item,
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

    def _set_checkmark(self, parent_title: str, chosen_label: str) -> None:
        parent = self.menu[parent_title]
        for item in parent.values():
            item.state = 1 if item.title == chosen_label else 0

    def _pick_hotkey(self, sender) -> None:
        self.cfg["hotkey"] = HOTKEY_OPTIONS[sender.title]
        save_config(self.cfg)
        self._set_checkmark("Hotkey", sender.title)

    def _pick_model(self, sender) -> None:
        repo = MODEL_OPTIONS[sender.title]
        self.cfg["model"] = repo
        save_config(self.cfg)
        self._set_checkmark("Model", sender.title)
        self.title = "⏬"
        threading.Thread(target=self._download_model, args=(repo,), daemon=True).start()

    def _pick_language(self, sender) -> None:
        self.cfg["language"] = LANGUAGE_OPTIONS[sender.title]
        save_config(self.cfg)
        self._set_checkmark("Language", sender.title)

    def _toggle_sounds(self, sender) -> None:
        sender.state = 0 if sender.state else 1
        self.cfg["play_sounds"] = bool(sender.state)
        save_config(self.cfg)

    def _toggle_paste(self, sender) -> None:
        sender.state = 0 if sender.state else 1
        self.cfg["auto_paste"] = bool(sender.state)
        save_config(self.cfg)

    def _toggle_pause_media(self, sender) -> None:
        sender.state = 0 if sender.state else 1
        self.cfg["pause_media"] = bool(sender.state)
        save_config(self.cfg)

    def _toggle_autostart(self, sender) -> None:
        new_state = not bool(sender.state)
        set_login_item(new_state)
        # Verify actual system state (permissions may have denied the change)
        sender.state = 1 if is_login_item() else 0

    # ---- Lifecycle --------------------------------------------------------
    def _warmup(self) -> None:
        self.title = "⏳"
        self._download_model(self.cfg["model"])

    def _download_model(self, repo: str) -> None:
        try:
            silent = np.zeros(SAMPLE_RATE, dtype=np.float32)
            mlx_whisper.transcribe(
                silent,
                path_or_hf_repo=repo,
                language=self.cfg["language"],
            )
        finally:
            AppHelper.callAfter(lambda: setattr(self, "title", "🎙"))

    # ---- Hotkey -----------------------------------------------------------
    def _on_press(self, key) -> None:
        if key != resolve_hotkey(self.cfg["hotkey"]):
            return
        threading.Thread(target=self._do_start, daemon=True).start()

    def _on_release(self, key) -> None:
        if key != resolve_hotkey(self.cfg["hotkey"]):
            return
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_start(self) -> None:
        with self._lock:
            if not self._recording:
                self._start()

    def _do_stop(self) -> None:
        with self._lock:
            if self._recording:
                self._stop_and_transcribe()

    # ---- Recording --------------------------------------------------------
    def _audio_cb(self, indata, frames, t, status) -> None:  # noqa: ARG002
        self._audio_q.put(indata.copy())
        block = indata.astype(np.float32)
        rms = float(np.sqrt(np.mean(block ** 2)))
        peak = float(np.max(np.abs(block)))
        mixed = rms * 6.0 + peak * 2.5
        self._current_level = min(1.0, mixed ** 0.55)

    def _start(self) -> None:
        self._recording = True
        self._target_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        self._audio_q = queue.Queue()
        self._start_ts = time.monotonic()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._audio_cb,
        )
        self._stream.start()
        if self.cfg["play_sounds"]:
            play_sound(START_SOUND)
        if self.cfg["pause_media"]:
            threading.Thread(target=self._run_pause_media, daemon=True).start()
        AppHelper.callAfter(self._ui_start)

    def _run_pause_media(self) -> None:
        self._paused_media = pause_playing_media()

    def _ui_start(self) -> None:
        self.title = "🔴"
        self._wave.setTranscribing_(False)
        position_overlay_near_cursor(self._overlay)
        self._overlay.setAlphaValue_(1.0)
        self._overlay.orderFrontRegardless()
        self._overlay.display()

    def _stop_and_transcribe(self) -> None:
        self._recording = False
        duration = time.monotonic() - self._start_ts
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                print(f"[warn] stream stop failed: {exc}", flush=True)
            self._stream = None
        self._current_level = 0.0
        if self.cfg["play_sounds"]:
            play_sound(STOP_SOUND)

        chunks: list[np.ndarray] = []
        while not self._audio_q.empty():
            chunks.append(self._audio_q.get())

        if duration < MIN_RECORDING_SEC or not chunks:
            AppHelper.callAfter(self._ui_idle)
            apps = self._paused_media
            self._paused_media = []
            if apps:
                threading.Thread(target=resume_media, args=(apps,), daemon=True).start()
            return

        audio = np.concatenate(chunks).flatten()
        AppHelper.callAfter(self._ui_transcribing)
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _ui_idle(self) -> None:
        self.title = "🎙"
        self._overlay.orderOut_(None)

    def _ui_transcribing(self) -> None:
        self.title = "⏳"
        self._wave.setTranscribing_(True)

    # ---- Transcription + paste -------------------------------------------
    def _transcribe(self, audio: np.ndarray) -> None:
        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self.cfg["model"],
                language=self.cfg["language"],
            )
            text = (result.get("text") or "").strip()
            if text:
                self._deliver(text)
        finally:
            AppHelper.callAfter(self._ui_idle)
            apps = self._paused_media
            self._paused_media = []
            if apps:
                threading.Thread(target=resume_media, args=(apps,), daemon=True).start()

    def _deliver(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        if not self.cfg["auto_paste"]:
            return
        target = self._target_app
        if target is not None:
            target.activateWithOptions_(
                NSApplicationActivateIgnoringOtherApps
                | NSApplicationActivateAllWindows
            )
            time.sleep(0.12)
        else:
            time.sleep(0.15)
        with self._kb.pressed(Key.cmd):
            self._kb.press("v")
            self._kb.release("v")

    # ---- Overlay refresh (main thread) -----------------------------------
    def _tick_overlay(self, _sender) -> None:
        if self._recording:
            level = self._current_level
            jitter = random.uniform(0.65, 1.25)
            baseline = 0.08 + random.random() * 0.08
            self._wave.pushLevel_(min(1.0, max(baseline, level * jitter)))
        elif self._wave._transcribing:  # noqa: SLF001
            t = time.monotonic() * 4.0
            self._wave.pushLevel_(0.35 + 0.25 * math.sin(t))


if __name__ == "__main__":
    Dictation().run()
