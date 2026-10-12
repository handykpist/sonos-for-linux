#!/usr/bin/env bash
# Official Raspberry Pi 7" Display Rotation & Brightness Utility
set -e

echo "=========================================================="
echo "   Raspberry Pi 7\" Touch Display Setup & Rotation Tool    "
echo "=========================================================="

# Check if running as root for /boot modifications
if [ "$EUID" -ne 0 ]; then
    echo "[!] Please run with sudo to modify display orientation:"
    echo "    sudo ./setup_screen.sh rotate180"
    exit 1
fi

ACTION="${1:-help}"

case "$ACTION" in
    rotate180)
        echo "[*] Configuring 180-degree display rotation (common for Pi stands)..."
        # Bookworm (Wayland / KMS)
        if [ -f "/boot/firmware/cmdline.txt" ]; then
            if ! grep -q "video=DSI-1" /boot/firmware/cmdline.txt; then
                sed -i '1 s/$/ video=DSI-1:800x480@60,rotate=180/' /boot/firmware/cmdline.txt
                echo "[+] Added rotation to /boot/firmware/cmdline.txt"
            fi
        fi
        # Bullseye / Legacy
        if [ -f "/boot/config.txt" ]; then
            if ! grep -q "display_lcd_rotate=2" /boot/config.txt; then
                echo "display_lcd_rotate=2" >> /boot/config.txt
                echo "[+] Added display_lcd_rotate=2 to /boot/config.txt"
            fi
        fi
        echo "[+] Done. Please reboot your Raspberry Pi: sudo reboot"
        ;;
    rotate0)
        echo "[*] Resetting display rotation to standard orientation..."
        if [ -f "/boot/firmware/cmdline.txt" ]; then
            sed -i 's/ video=DSI-1:800x480@60,rotate=180//g' /boot/firmware/cmdline.txt
        fi
        if [ -f "/boot/config.txt" ]; then
            sed -i '/display_lcd_rotate=2/d' /boot/config.txt
        fi
        echo "[+] Rotation reset. Please reboot: sudo reboot"
        ;;
    brightness)
        LEVEL="${2:-200}"
        echo "[*] Setting screen backlight brightness to $LEVEL (0-255)..."
        if [ -f "/sys/class/backlight/rpi_backlight/brightness" ]; then
            echo "$LEVEL" > /sys/class/backlight/rpi_backlight/brightness
            echo "[+] Backlight set to $LEVEL"
        else
            echo "[!] rpi_backlight device not found at /sys/class/backlight/rpi_backlight/brightness"
        fi
        ;;
    *)
        echo "Usage: sudo $0 [rotate180 | rotate0 | brightness <0-255>]"
        echo "  rotate180      - Rotates screen 180 degrees (standard for official stand)"
        echo "  rotate0        - Normal orientation"
        echo "  brightness 150 - Sets backlight level from 0 to 255"
        ;;
esac
