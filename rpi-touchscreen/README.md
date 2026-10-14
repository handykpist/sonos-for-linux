# Sonos Touchscreen Controller for Raspberry Pi (7" Touch Display)

A dedicated, standalone touch controller for your household **Sonos** sound system, specifically crafted for the **Raspberry Pi** and the **Official Raspberry Pi 7" Touchscreen (800×480)**.

Designed to live on your kitchen counter, living room wall, or bedside table as an instant, always-on smart home music hub.

![Sonos Touchscreen Player](docs/screenshots/main_player.png)

---

## 📸 Interface & Feature Tour

| **Now Playing & Playback Controls** | **Power & System Menu (Bottom-Left)** |
|:---:|:---:|
| ![Main Player](docs/screenshots/main_player.png) | ![Power & System Menu](docs/screenshots/power_system_menu.png) |
| *High-res artwork, tactile transport buttons & volume slider* | *Hidden hot-corner for Desktop exit, reboot & safe shutdown* |

| **Sonos Favorites & Radio** | **Live Synchronized Lyrics** |
|:---:|:---:|
| ![Favorites Drawer](docs/screenshots/favorites_drawer.png) | ![Lyrics Mode](docs/screenshots/lyrics_mode.png) |
| *1-tap access to TuneIn radio, playlists & stations* | *Word-by-word / line-by-line real-time lyrics (LRCLIB)* |

---

## 🌟 Key Features

- **Tailored 800×480 Touch Ergonomics**:
  - Pixel-exact UI layout designed specifically for the official 7" Raspberry Pi Touch Display.
  - Large capacitive touch targets (58px–76px) for effortless, tap-and-go control without needing a mouse or keyboard.
  - Zero scrollbars or cluttered desktop frames in full-screen Kiosk mode.
  - Chromium launched with `--password-store=basic` and `--use-mock-keychain` to eliminate OS keyring popups.

- **Full Sonos System Control**:
  - **Auto-Discovery**: Dynamically discovers all Sonos speakers across your home via UPnP/SSDP with zero hardcoded IPs or names.
  - **Multi-Room Selector**: Easily switch between rooms (Living Room, Kitchen, Bedroom, Move, Roam) with one touch.
  - **Playback Transport**: Big, tactile Play, Pause, Next Track, and Previous Track buttons.
  - **Touch Volume Control**: Capacitive touch volume slider with instant tactile step buttons (`-` and `+`) and 1-tap Mute.
  - **Scrubbing Seek Bar**: Tap anywhere on the progress track to jump forward or backward in the track.

- **Now Playing Artwork & Visualizer**:
  - High-resolution album artwork with real-time dynamic ambient backlight glow.
  - Animated audio playback waveform.
  - Formatted elapsed / total duration countdowns.

- **Sonos Radio & Favorites**:
  - Slide-over drawer with all your household Sonos Favorites, Spotify playlists, and TuneIn radio stations.
  - Tap any station or playlist to begin playback instantly.

- **🎤 Live Synchronized Lyrics Mode**:
  - One-tap drawer featuring synchronized word-by-word / line-by-line karaoke lyrics powered by LRCLIB.

- **🌙 Night / Sleep Mode**:
  - One-touch sleep mode transforms the screen into a subtle, low-light digital clock and date display.
  - Tap anywhere on the screen to wake it up instantly.

- **🔒 Hidden Power & Exit Menu (Bottom-Left Corner)**:
  - An unobtrusive, hidden touch button in the bottom-left corner opens a tactile system menu:
    - **Exit to Desktop**: Close kiosk mode and return to Raspberry Pi OS desktop.
    - **Restart Sonos App**: Cleanly reload the UI and backend service.
    - **Reboot Raspberry Pi**: Safely reboot the hardware.
    - **Shut Down Device**: Safely power off the Raspberry Pi.

- **100% Native ARM64 & ARMhf**:
  - Built with pure Python standard library and lightweight web standards.
  - Zero heavy x86 emulation or Wine overhead.
  - Uses < 35 MB of RAM on Raspberry Pi OS.

---

## 🛠️ Hardware Requirements

1. **Raspberry Pi** (Pi 3B or newer).
2. **Official Raspberry Pi 7" Touchscreen Display** (800×480 DSI) or any 7" HDMI/DSI capacitive display.
3. MicroSD card with **Raspberry Pi OS** (Bookworm or Bullseye with Desktop autologin enabled).
4. Standard 5V USB power supply.

---

## 🚀 Quick Installation

On your Raspberry Pi terminal (or via SSH):

```bash
# 1. Clone this repository
git clone https://github.com/handykpist/sonos-rpi-touchscreen.git
cd sonos-rpi-touchscreen

# 2. Run the automated installer
chmod +x install.sh
./install.sh
```

The installer will:
1. Verify system packages (`python3`, `chromium-browser`, `unclutter`).
2. Deploy the touchscreen application to `~/.local/share/sonos-touchscreen`.
3. Configure the systemd user service `sonos-touchscreen.service` to boot automatically into fullscreen Kiosk mode on startup.
4. Set up the `sonos-touchscreen-update.timer` to check for updates every night at 01:00 AM.

### 🔄 Updating an Existing Installation

If you already have `sonos-rpi-touchscreen` cloned and running on your Raspberry Pi:

```bash
cd ~/sonos-rpi-touchscreen
git pull
./install.sh
```
*(Running `./install.sh` refreshes all application files and ensures all systemd services and timers are active).*

---

## 📖 Touch Controls & Usage Guidelines

### 1. Switching Sonos Rooms
Tap the **Room Pill** button in the top-left corner (`Living Room ▼`). A modal overlay opens displaying all discovered Sonos speakers in your home. Tap any room to switch control instantly.

### 2. Playback & Scrubbing
- **Play / Pause**: Tap the large glowing circular center button.
- **Track Navigation**: Tap **⏮** for previous track or **⏭** for next track.
- **Seek Scrubbing**: Tap anywhere along the progress track bar to seek forward or backward.

### 3. Volume Control
- **Slider**: Drag your finger along the volume bar for fluid capacitive volume adjustment.
- **Step Buttons**: Tap `-` or `+` on either side of the slider for precise 2% incremental steps.
- **Mute**: Tap the speaker icon to toggle mute on or off.

### 4. Sonos Favorites & Radio
Tap the **⭐ Radio** button in the top-right header to slide out your saved Sonos Favorites, Spotify playlists, and TuneIn radio stations. Tap any card to begin playing.

### 5. Synchronized Lyrics
Tap the **🎤 Lyrics** button in the header. If timestamped lyrics exist for the current track, they will scroll in real time with the active singing line illuminated.

### 6. Night / Sleep Dimmer
Tap the **🌙** moon icon in the header. The screen enters a minimal, ultra-low power clock and date view. Tap anywhere on the display to wake it up.

### 7. Hidden Power & Exit Menu (Bottom-Left Corner)
To avoid accidental taps while keeping the UI clean, a subtle, hidden touch hot-corner is positioned at the **bottom-left corner** (`⏻`).
- Tap the bottom-left corner to open the **Power & System** menu.
- Choose **Exit to Desktop** to close Chromium kiosk mode.
- Choose **Restart Sonos App** to reload backend services.
- Choose **Reboot** or **Shut Down** to safely manage the Raspberry Pi hardware.

---

## 🔄 Screen Rotation (Upside-Down Display Fix)

Many popular 3D-printed cases and desktop stands for the official 7" display mount the screen upside down (so the power cables exit at the top or side).

Use the included rotation tool:

```bash
# Rotate 180 degrees (standard stand orientation)
sudo ~/.local/share/sonos-touchscreen/kiosk/setup_screen.sh rotate180
sudo reboot

# To reset to normal orientation:
sudo ~/.local/share/sonos-touchscreen/kiosk/setup_screen.sh rotate0
sudo reboot
```

### Manual Configuration:
- **Raspberry Pi OS Bookworm (Wayland / KMS)**: Add `video=DSI-1:800x480@60,rotate=180` to the end of the line in `/boot/firmware/cmdline.txt`.
- **Raspberry Pi OS Bullseye / Legacy (X11)**: Add `display_lcd_rotate=2` to `/boot/config.txt`.

---

## 💡 Backlight Brightness Control

You can adjust the screen brightness from terminal or scripts:

```bash
# Set brightness between 0 (off) and 255 (maximum)
sudo ~/.local/share/sonos-touchscreen/kiosk/setup_screen.sh brightness 180
```

---

## 🔧 Service Management & Shutdown

### Stop or Exit the Touchscreen App:
To close the fullscreen kiosk window and stop the controller from terminal:
```bash
~/.local/share/sonos-touchscreen/kiosk/exit_kiosk.sh
```
*(Or run `systemctl --user stop sonos-touchscreen && pkill -f "server.py"`)*

### Other Service Controls:
- **Start Controller**: `systemctl --user start sonos-touchscreen.service`
- **Restart Controller**: `systemctl --user restart sonos-touchscreen.service`
- **Check Status**: `systemctl --user status sonos-touchscreen.service`
- **View Live Kiosk Logs**: `journalctl --user -u sonos-touchscreen.service -f`
- **View Backend Server Logs**: `tail -f ~/.local/share/sonos-touchscreen/server.log`

### Safely Shut Down the Raspberry Pi Hardware:
To cleanly power off the Raspberry Pi without corrupting the SD card:
```bash
sudo shutdown -h now
```
*(or `sudo poweroff`)*

---

## 🌙 Nightly 01:00 Auto-Update

The controller includes an automated background updater that checks your Git repository every night at **01:00 AM** and applies updates without manual intervention.

- **Non-disruptive**: It checks remote Git commit hashes first. If no new commits were pushed, it exits silently and leaves your current playback uninterrupted.
- **Auto-Restart**: If a new commit is detected on GitHub, it fast-forward pulls the changes, syncs the application files, reloads systemd units, and restarts the kiosk smoothly.
- **Offline Resilient & Catch-Up**: Uses `Persistent=true` so if your Raspberry Pi was turned off at 01:00, it checks for updates immediately when powered on next.

### Auto-Update Commands:
- **Check Timer Schedule**:
  ```bash
  systemctl --user list-timers sonos-touchscreen-update.timer
  ```
- **Run Update Immediately (Manual Check)**:
  ```bash
  ~/.local/share/sonos-touchscreen/kiosk/auto_update.sh
  ```
- **Force Update**:
  ```bash
  ~/.local/share/sonos-touchscreen/kiosk/auto_update.sh --force
  ```
- **View Update History & Logs**:
  ```bash
  cat ~/.local/share/sonos-touchscreen/update.log
  ```

---

## 🌐 Remote Browser Access

You can also access the touch controller from any phone, tablet, or PC on your home Wi-Fi:

```
http://<raspberry-pi-ip>:5000
```

---

## 📄 License

MIT License. Designed with ❤️ for the Sonos and Raspberry Pi smart home community.
