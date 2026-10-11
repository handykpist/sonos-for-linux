#!/usr/bin/env bash
# Quick launcher for Sonos Controller using a project-local Wine prefix
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINEPREFIX="$SCRIPT_DIR/.wine"
export DISPLAY="${DISPLAY:-:0}"
export WINEPREFIX
export WINEARCH=win32
export WINEDEBUG=-all

# Auto-start Sonos SSDP Discovery Bridge if not running
if ! pgrep -f "sonos_ssdp_bridge.py" >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/sonos_ssdp_bridge.py" >/dev/null 2>&1 &
fi

INSTALLED_EXE="$WINEPREFIX/drive_c/Program Files/Sonos/Sonos.exe"

if [ -f "$INSTALLED_EXE" ]; then
    echo "[*] Launching Sonos Controller..."
    exec wine "$INSTALLED_EXE" "$@"
else
    echo "[*] Setting up local Sonos Controller environment..."
    mkdir -p "$WINEPREFIX"
    if [ -f "$SCRIPT_DIR/extracted/SonosController.msi" ]; then
        wine msiexec /i "$SCRIPT_DIR/extracted/SonosController.msi"
    else
        wine "$SCRIPT_DIR/Sonos_57.23-74170.exe"
    fi
fi

