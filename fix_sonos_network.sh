#!/usr/bin/env bash
# Sonos Linux Network & Firewall Configuration Fix
# Automatically configures multicast SSDP routing and firewall rules for Sonos speakers.
# Usage: sudo ./fix_sonos_network.sh [interface] [subnet]
set -e

# Auto-detect default network interface if not specified
IFACE="${1:-$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}')}"
if [ -z "$IFACE" ]; then
    IFACE=$(ip -o -4 route show to default 2>/dev/null | awk '{print $5; exit}')
fi

if [ -z "$IFACE" ]; then
    echo "[!] Error: Could not automatically detect primary network interface."
    echo "    Please specify it manually: sudo ./fix_sonos_network.sh <interface> <subnet>"
    exit 1
fi

# Auto-detect local subnet in CIDR notation (e.g. 192.168.1.0/24, 10.0.0.0/24)
SUBNET="${2:-$(ip -o -4 addr show dev "$IFACE" 2>/dev/null | awk '{print $4; exit}')}"
if [ -z "$SUBNET" ]; then
    echo "[!] Error: Could not determine subnet for interface $IFACE."
    echo "    Please specify it manually: sudo ./fix_sonos_network.sh $IFACE <subnet>"
    exit 1
fi

echo "=========================================================="
echo "         Sonos Discovery & Firewall Fix for Linux         "
echo "=========================================================="
echo "[*] Detected interface: $IFACE"
echo "[*] Detected subnet:    $SUBNET"
echo ""

echo "[*] Adding SSDP multicast route for Sonos on interface $IFACE..."
ip route replace 239.255.255.250 dev "$IFACE" 2>/dev/null || ip route add 239.255.255.250 dev "$IFACE"

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    echo "[*] Allowing Sonos local traffic from $SUBNET in UFW..."
    ufw allow in on "$IFACE" from "$SUBNET" comment "Sonos local speakers" || true

    echo "[*] Allowing SSDP multicast packets (port 1900 UDP)..."
    ufw allow in proto udp to 239.255.255.250 port 1900 comment "Sonos SSDP multicast" || true
else
    echo "[*] UFW is inactive or not installed; skipping UFW rule additions."
fi

echo ""
echo "[+] Network and firewall configuration successfully updated for Sonos!"
echo "Your Sonos S1 Controller will now discover all speakers on your network."
