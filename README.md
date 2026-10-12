# Official Sonos S1 Controller for Linux

Run the official Windows **Sonos S1 Desktop Controller** (`Sonos_57.23-74170.exe`) natively on Linux Mint / Ubuntu with 100% feature parity to Windows:
- Full Sonos Account login and synchronization
- Spotify integration, personal playlists, and Spotify search
- Sveriges Radio, TuneIn, and Sonos Radio
- Sonos Favorites and saved playlists
- Live queues, album artwork, room grouping, and volume controls
- Local Music Library & Line-In management

---

## 🛠️ Key Technical Components

1. **MSI Extraction & Automated Patching (`extract_sonos.py`)**:
   - Extracts `SonosController.msi` from `Sonos_57.23-74170.exe`.
   - Patches `InstallExecuteSequence` table in the MSI binary to eliminate .NET 4.0 launch condition blocks and disable the failing `SonosLibraryService.exe` service installation.
2. **SSDP Multicast Discovery Relay (`sonos_ssdp_bridge.py`)**:
   - Bypasses Linux firewall and multicast routing barriers by automatically relaying SSDP speaker discovery packets on port 1900 to `Sonos.exe`.
   - Runs as a persistent systemd user service (`sonos-ssdp-bridge.service`).
3. **TLS 1.2 Binary Fix**:
   - Eliminates `System.NotSupportedException` in `Sonos.Controller.Desktop.SCLib.UrlSessionProvider.startURLSession` by deploying .NET Framework 4.8 and NOP-patching the problematic IL call.
4. **WPF Software Rendering**:
   - Configures `DisableHWAcceleration=1` in the Wine registry to eliminate Direct3D9 WPF shader crashes.

---

## 🚀 Quick Start & Installation

```bash
# 1. Run the network and firewall configuration (run once)
sudo ./fix_sonos_network.sh

# 2. Install desktop application shortcuts and icons
./install_desktop_app.sh

# 3. Launch the controller
sonos
```

---

## 🖥️ System Integration

- **Desktop Shortcut:** Double-click the **Sonos Controller** desktop icon.
- **Start Menu:** **Sound & Video** $\rightarrow$ **Sonos Controller**.
- **Terminal:** Run `sonos`.
- **Systemd Service:** `systemctl --user status sonos-controller`

---

## 📱 Raspberry Pi 4 (7" Touchscreen) Controller

This branch includes a dedicated, 100% native touch controller crafted specifically for the **Raspberry Pi 4** and the **Official Raspberry Pi 7" Touchscreen (800×480)**.

- **Directory:** [`rpi-touchscreen/`](file:///home/bue/Documents/Projects/Sonos%20for%20Linux/rpi-touchscreen)
- **Features:** 800×480 pixel-exact layout, large capacitive buttons, now-playing artwork, volume slider, Sonos Favorites / Radio station drawer, synchronized lyrics mode, and auto-boot Kiosk mode.
- **Quick Setup:**
  ```bash
  cd rpi-touchscreen
  chmod +x install.sh
  ./install.sh
  ```
- Also available as a standalone repository at: [`https://github.com/handykpist/sonos-rpi-touchscreen`](https://github.com/handykpist/sonos-rpi-touchscreen)

