#!/usr/bin/env bash
# Sonos Touchscreen - Clean Kiosk Exit Script
# Stops the kiosk service, closes fullscreen Chromium, and exits cleanly to the desktop.

# 1. Stop systemd user service so it will not auto-restart
systemctl --user stop sonos-touchscreen 2>/dev/null || true

# 2. Gracefully signal kiosk browser instances to close
pkill -TERM -f "chromium.*--kiosk" 2>/dev/null || true
pkill -TERM -f "chromium-browser.*--kiosk" 2>/dev/null || true
pkill -TERM -f "chrome.*--kiosk" 2>/dev/null || true
pkill -TERM -f "chromium.*5000" 2>/dev/null || true
pkill -TERM -f "chromium-browser.*5000" 2>/dev/null || true

# 3. Kill unclutter mouse cursor hider
pkill -f unclutter 2>/dev/null || true

# 4. Fallback force-close if browser is still lingering after 0.5s
sleep 0.5
killall -9 chromium-browser chromium google-chrome 2>/dev/null || true
pkill -9 -f "chromium.*--kiosk" 2>/dev/null || true
pkill -9 -f "chromium-browser.*--kiosk" 2>/dev/null || true

# 5. Terminate the backend Python server
(sleep 0.4 && pkill -9 -f "python3.*server.py" 2>/dev/null || true) &

exit 0
