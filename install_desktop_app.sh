#!/usr/bin/env bash
# Sonos Desktop Application Installer for Linux Mint / Ubuntu
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_256="$SCRIPT_DIR/extracted/sonos-256.png"
if [ ! -f "$ICON_256" ]; then
    ICON_256="$SCRIPT_DIR/sonos.png"
fi
ICON_48="$SCRIPT_DIR/sonos-48.png"

echo "=========================================================="
echo "         Sonos Controller - Linux Desktop Setup           "
echo "=========================================================="

mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$HOME/.local/share/icons/hicolor/48x48/apps"
mkdir -p "$HOME/.local/share/sonos"

# 1. Install High-Resolution Icons
echo "[*] Installing Sonos application icons..."
if [ -f "$ICON_256" ]; then
    cp "$ICON_256" "$HOME/.local/share/icons/hicolor/256x256/apps/sonos.png"
fi
if [ -f "$ICON_48" ]; then
    cp "$ICON_48" "$HOME/.local/share/icons/hicolor/48x48/apps/sonos.png"
fi

# 2. Install Official Sonos Controller Launcher (Wine)
echo "[*] Installing official Sonos Controller launcher..."
OFFICIAL_LAUNCHER="$HOME/.local/bin/sonos"
cat << EOF > "$OFFICIAL_LAUNCHER"
#!/usr/bin/env bash
SCRIPT_DIR="$SCRIPT_DIR"
WINEPREFIX="\$HOME/.local/share/sonos/wineprefix"
if [ ! -d "\$WINEPREFIX" ] && [ -d "$SCRIPT_DIR/.wine" ]; then
    mkdir -p "\$HOME/.local/share/sonos"
    ln -sfn "$SCRIPT_DIR/.wine" "\$WINEPREFIX"
fi
export DISPLAY="\${DISPLAY:-:0}"
export WINEPREFIX="\$SCRIPT_DIR/.wine"
export WINEARCH=win32
export WINEDEBUG=-all

# Auto-start Sonos SSDP Discovery Bridge if not running
if ! pgrep -f "sonos_ssdp_bridge.py" >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/sonos_ssdp_bridge.py" >/dev/null 2>&1 &
fi

INSTALLED_EXE="\$WINEPREFIX/drive_c/Program Files/Sonos/Sonos.exe"

if [ -f "\$INSTALLED_EXE" ]; then
    exec wine "\$INSTALLED_EXE" "\$@"
else
    echo "[!] Sonos.exe not found at \$INSTALLED_EXE"
    exit 1
fi
EOF
chmod +x "$OFFICIAL_LAUNCHER"

# 3. Create Desktop Entry in Applications Menu
DESKTOP_FILE="$HOME/.local/share/applications/sonos.desktop"
cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Sonos Controller
GenericName=Sonos S1 Music Controller
Comment=Official Sonos S1 Controller for Linux with Account, Playlists, Radio & Music Services
Exec=$OFFICIAL_LAUNCHER
Icon=sonos
Terminal=false
Categories=AudioVideo;Audio;Player;
Keywords=sonos;music;speaker;audio;s1;controller;livingroom;spotify;radio;
StartupWMClass=sonos.exe
EOF
chmod +x "$DESKTOP_FILE"

# 4. Update Desktop Database & Icon Cache
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

# Clean up legacy sonos-native launcher if present
rm -f "$HOME/.local/bin/sonos-native"

echo ""
echo "[+] Successfully installed Sonos S1 Controller on Linux Mint!"
echo "    • Application:  $DESKTOP_FILE"
echo "    • Launcher:     $OFFICIAL_LAUNCHER"
echo "    • Icon:         $HOME/.local/share/icons/hicolor/256x256/apps/sonos.png"
echo ""
echo "You can now open 'Sonos Controller' from your Linux Mint Start Menu"
echo "(under Sound & Video), or launch it by typing 'sonos' in your terminal."
