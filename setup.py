"""py2app build script.

Usage:
    pip install py2app
    python setup.py py2app

The bundled app lands in dist/WhisperDictate.app — drag it to /Applications.
Then add that app to System Settings → Privacy & Security →
  - Microphone
  - Accessibility
  - Input Monitoring
"""
from setuptools import setup

APP = ["whisper_dictate.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName":            "WhisperDictate",
        "CFBundleDisplayName":     "WhisperDictate",
        "CFBundleIdentifier":      "com.sharkjohny.whisperdictate",
        "CFBundleVersion":         "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # menu-bar only, no Dock icon
        "NSMicrophoneUsageDescription":
            "WhisperDictate uses your microphone to transcribe speech locally.",
        "NSAppleEventsUsageDescription":
            "Used to paste transcribed text into the focused application.",
    },
    "packages": [
        "rumps", "pynput", "sounddevice", "numpy",
        "mlx_whisper", "mlx", "objc", "PyObjCTools",
    ],
    "includes": ["tiktoken_ext", "tiktoken_ext.openai_public"],
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
