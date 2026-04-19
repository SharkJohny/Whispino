#!/bin/bash
# Install a LaunchAgent so WhisperDictate runs at login.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV_PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/whisper_dictate.py"
LABEL="com.sharkjohny.whisperdictate"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -x "$VENV_PY" ]]; then
    echo "Virtualenv not found at $VENV_PY" >&2
    echo "Create it first: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PY</string>
        <string>$SCRIPT</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>/tmp/whisperdictate.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/whisperdictate.log</string>
</dict>
</plist>
EOF

# Reload if already installed
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed: $PLIST"
echo "Running now — check menu bar for 🎙."
echo "Log:    /tmp/whisperdictate.log"
echo "Remove: ./uninstall_autostart.sh"
