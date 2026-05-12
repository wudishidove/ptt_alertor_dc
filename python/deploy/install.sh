#!/usr/bin/env bash
# Install ptt-alertor as a macOS LaunchAgent.
# - Renders deploy/com.user.pttalertor.plist with the current install dir
# - Copies it to ~/Library/LaunchAgents
# - Loads it via launchctl
# Usage: bash deploy/install.sh
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.user.pttalertor"
SOURCE_PLIST="$INSTALL_DIR/deploy/com.user.pttalertor.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/$LABEL.plist"

if [[ ! -d "$INSTALL_DIR/.venv" ]]; then
  echo "ERROR: $INSTALL_DIR/.venv not found." >&2
  echo "  Run: python3 -m venv .venv && .venv/bin/pip install -e .[dev]" >&2
  exit 1
fi

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  echo "WARNING: $INSTALL_DIR/.env not found. Copy .env.example and fill DISCORD_TOKEN before loading." >&2
fi

mkdir -p "$TARGET_DIR" "$INSTALL_DIR/logs"

# Render template by substituting the install dir placeholder.
sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$SOURCE_PLIST" > "$TARGET_PLIST"

# Reload (idempotent).
launchctl unload "$TARGET_PLIST" 2>/dev/null || true
launchctl load -w "$TARGET_PLIST"

echo "Installed: $TARGET_PLIST"
launchctl list | grep "$LABEL" || true
echo
echo "Logs:"
echo "  $INSTALL_DIR/logs/stdout.log"
echo "  $INSTALL_DIR/logs/stderr.log"
