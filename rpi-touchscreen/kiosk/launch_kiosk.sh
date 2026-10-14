#!/usr/bin/env bash
# Sonos Touchscreen Kiosk Launcher for Raspberry Pi (800x480)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/sonos-touchscreen}"
LOG_FILE="$INSTALL_DIR/server.log"
mkdir -p "$INSTALL_DIR"

# 1. Start Python server if not already running
if ! pgrep -f "server.py" >/dev/null 2>&1; then
    echo "[*] Starting Sonos Touchscreen backend server..."
    if [ -f "$LOG_FILE" ] && [ $(wc -c < "$LOG_FILE" 2>/dev/null || echo 0) -gt 1048576 ]; then
        mv "$LOG_FILE" "$LOG_FILE.old" 2>/dev/null || true
    fi
    python3 "$SCRIPT_DIR/server.py" >> "$LOG_FILE" 2>&1 &
fi

# Ensure localhost traffic is direct and never routed through any network proxy
export no_proxy="localhost,127.0.0.1,localaddress,.local"
export NO_PROXY="localhost,127.0.0.1,localaddress,.local"

# 2. Wait until server responds (using python3 urllib to avoid curl dependency, max 15s)
echo "[*] Waiting for Sonos Touchscreen server on port 5000..."
MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if python3 -c "import urllib.request; o=urllib.request.build_opener(urllib.request.ProxyHandler({})); o.open('http://127.0.0.1:5000/api/status', timeout=1)" >/dev/null 2>&1; then
        echo "[+] Backend ready."
        break
    fi
    sleep 0.5
    WAITED=$((WAITED + 1))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[!] Warning: Backend server did not respond within 15s. Check $LOG_FILE"
fi

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
    --password-store=basic \
    --use-mock-keychain \
    --proxy-bypass-list="127.0.0.1;localhost" \
    --window-size=800,480 \
    --window-position=0,0 \
    --app="$KIOSK_URL" "$@"
