#!/bin/bash
# Remove the WhisperDictate LaunchAgent.
set -euo pipefail

LABEL="com.sharkjohny.whisperdictate"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ -f "$PLIST" ]]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $PLIST"
else
    echo "No LaunchAgent installed (nothing to do)."
fi

# Kill any still-running instance
pkill -f "whisper_dictate.py" 2>/dev/null || true
