#!/usr/bin/env bash
# Sonos Touchscreen Kiosk Launcher for Raspberry Pi 4 (800x480)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Start Python server if not already running
if ! pgrep -f "server.py" >/dev/null 2>&1; then
    echo "[*] Starting Sonos Touchscreen backend server..."
    python3 "$SCRIPT_DIR/server.py" >/dev/null 2>&1 &
fi

# 2. Wait until server responds
echo "[*] Waiting for Sonos Touchscreen server on port 5000..."
until curl -s http://127.0.0.1:5000/api/status >/dev/null 2>&1; do
    sleep 0.5
done
echo "[+] Backend ready."

# 3. Disable screen sleep and hide mouse pointer if unclutter is installed
if command -v xset >/dev/null 2>&1; then
    xset s off 2>/dev/null || true
    xset -dpms 2>/dev/null || true
    xset s noblank 2>/dev/null || true
fi

if command -v unclutter >/dev/null 2>&1; then
    unclutter -idle 1 -root >/dev/null 2>&1 &
fi

# 4. Launch Chromium in Kiosk Mode with touch screen flags
KIOSK_URL="http://127.0.0.1:5000"
CHROMIUM_CMD=""

if command -v chromium-browser >/dev/null 2>&1; then
    CHROMIUM_CMD="chromium-browser"
elif command -v chromium >/dev/null 2>&1; then
    CHROMIUM_CMD="chromium"
elif command -v google-chrome >/dev/null 2>&1; then
    CHROMIUM_CMD="google-chrome"
else
    echo "[!] Chromium not found. Opening in default browser..."
    exec xdg-open "$KIOSK_URL"
fi

exec $CHROMIUM_CMD \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --check-for-update-interval=31536000 \
    --enable-features=OverlayScrollbar \
    --touch-events=enabled \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-translate \
    --disable-features=Translate \
    --window-size=800,480 \
    --window-position=0,0 \
    --app="$KIOSK_URL" "$@"
