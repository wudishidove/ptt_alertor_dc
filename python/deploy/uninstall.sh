#!/usr/bin/env bash
# Stop and remove the ptt-alertor LaunchAgent.
set -euo pipefail

LABEL="com.user.pttalertor"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ -f "$TARGET_PLIST" ]]; then
  launchctl unload "$TARGET_PLIST" 2>/dev/null || true
  rm -f "$TARGET_PLIST"
  echo "Removed $TARGET_PLIST"
else
  echo "Not installed: $TARGET_PLIST"
fi
