#!/bin/bash
# Build WhisperDictate.app — a minimal .app bundle that launches
# whisper_dictate.py from the local venv.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
APP_DIR="$ROOT/dist/WhisperDictate.app"
VENV_PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/whisper_dictate.py"
ICON_SRC="$ROOT/icon.icns"

if [[ ! -x "$VENV_PY" ]]; then
    echo "Virtualenv not found at $VENV_PY — run 'python3 -m venv .venv && pip install -r requirements.txt' first." >&2
    exit 1
fi

# Regenerate icon each build
"$VENV_PY" "$ROOT/make_icon.py" "$ICON_SRC"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cp "$ICON_SRC" "$APP_DIR/Contents/Resources/icon.icns"

cat > "$APP_DIR/Contents/MacOS/WhisperDictate" <<EOF
#!/bin/bash
exec "$VENV_PY" "$SCRIPT"
EOF
chmod +x "$APP_DIR/Contents/MacOS/WhisperDictate"

cat > "$APP_DIR/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>WhisperDictate</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundleIdentifier</key>
    <string>com.sharkjohny.whisperdictate</string>
    <key>CFBundleName</key>
    <string>WhisperDictate</string>
    <key>CFBundleDisplayName</key>
    <string>WhisperDictate</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>WhisperDictate uses your microphone to transcribe speech locally.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Used to paste transcribed text and pause media playback.</string>
</dict>
</plist>
EOF

echo "Built: $APP_DIR"
