#!/usr/bin/env bash
# Sonos Touchscreen Controller - Installer for Raspberry Pi 4 (800x480)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/sonos-touchscreen"

echo "=========================================================="
echo "   Sonos Touchscreen Controller - Raspberry Pi 4 Setup    "
echo "=========================================================="

# 1. Install system prerequisites
echo "[*] Checking system packages..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 chromium-browser unclutter
fi

# 2. Deploy application files
echo "[*] Installing Sonos Touchscreen to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/server.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/sonos_device.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/lyrics.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/static" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/kiosk" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/kiosk/launch_kiosk.sh"
chmod +x "$INSTALL_DIR/kiosk/setup_screen.sh"

# 3. Create Desktop Entry
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/bin"
ln -sfn "$INSTALL_DIR/kiosk/launch_kiosk.sh" "$HOME/.local/bin/sonos-touchscreen"

DESKTOP_FILE="$HOME/.local/share/applications/sonos-touchscreen.desktop"
cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Sonos Touchscreen
GenericName=Sonos 7" Touch Controller
Comment=Dedicated touch controller for Sonos speakers on Raspberry Pi 4
Exec=$INSTALL_DIR/kiosk/launch_kiosk.sh
Icon=multimedia-player
Terminal=false
Categories=AudioVideo;Audio;Player;
EOF
chmod +x "$DESKTOP_FILE"

# 4. Install systemd auto-start service
echo "[*] Setting up systemd auto-start service..."
mkdir -p "$HOME/.config/systemd/user"
SERVICE_SRC="$INSTALL_DIR/kiosk/sonos-touchscreen.service"
SERVICE_DEST="$HOME/.config/systemd/user/sonos-touchscreen.service"

cp "$SERVICE_SRC" "$SERVICE_DEST"
systemctl --user daemon-reload
systemctl --user enable sonos-touchscreen.service
systemctl --user restart sonos-touchscreen.service || true

echo ""
echo "=========================================================="
echo " [+] Sonos Touchscreen Controller successfully installed! "
echo "=========================================================="
echo " • Kiosk Launcher: $HOME/.local/bin/sonos-touchscreen"
echo " • Desktop Entry:  $DESKTOP_FILE"
echo " • Systemd Service: sonos-touchscreen.service (Active)"
echo ""
echo "The touch kiosk will automatically launch on every boot."
echo "If your 7\" screen is mounted upside-down, rotate it by running:"
echo "    sudo $INSTALL_DIR/kiosk/setup_screen.sh rotate180"
echo "=========================================================="
