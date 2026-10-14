#!/usr/bin/env bash
# Sonos Touchscreen Controller - Auto Update Script
# Checks remote Git repository for updates, pulls changes, and restarts the kiosk.

set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/sonos-touchscreen}"
LOG_FILE="$INSTALL_DIR/update.log"
mkdir -p "$INSTALL_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log "Checking for Sonos Touchscreen updates..."

# 1. Determine Git repository location
REPO_DIR=""
if [ -f "$INSTALL_DIR/repo_path.txt" ]; then
    SAVED_PATH="$(cat "$INSTALL_DIR/repo_path.txt" 2>/dev/null | tr -d '\r\n')"
    if [ -d "$SAVED_PATH/.git" ]; then
        REPO_DIR="$SAVED_PATH"
    fi
fi

if [ -z "$REPO_DIR" ]; then
    for CANDIDATE in "$HOME/sonos-rpi-touchscreen" "$HOME/sonos-for-linux" "$HOME/Documents/Projects/sonos-rpi-touchscreen" "$HOME/Documents/Projects/Sonos for Linux"; do
        if [ -d "$CANDIDATE/.git" ]; then
            REPO_DIR="$CANDIDATE"
            break
        fi
    done
fi

if [ -z "$REPO_DIR" ]; then
    log "[ERROR] No git repository found for sonos-touchscreen. Cannot perform auto-update."
    exit 1
fi

cd "$REPO_DIR"

# 2. Check internet connectivity / remote git access
if ! git ls-remote --exit-code -h origin HEAD >/dev/null 2>&1; then
    log "[WARN] Unable to reach git remote 'origin'. Network may be offline. Skipping."
    exit 0
fi

# 3. Fetch remote changes
git fetch origin

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")"
if [ "$CURRENT_BRANCH" = "HEAD" ]; then
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        CURRENT_BRANCH="main"
    else
        CURRENT_BRANCH="rpi4-touchscreen"
    fi
fi

LOCAL_HASH="$(git rev-parse HEAD 2>/dev/null)"
REMOTE_HASH="$(git rev-parse "origin/$CURRENT_BRANCH" 2>/dev/null || git rev-parse "origin/main" 2>/dev/null)"

if [ -z "$REMOTE_HASH" ]; then
    log "[ERROR] Could not resolve remote branch origin/$CURRENT_BRANCH."
    exit 1
fi

FORCE_UPDATE=0
if [ "$1" = "--force" ]; then
    FORCE_UPDATE=1
fi

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ] && [ $FORCE_UPDATE -eq 0 ]; then
    log "Already up-to-date ($LOCAL_HASH on $CURRENT_BRANCH)."
    exit 0
fi

log "Update detected! Moving from $LOCAL_HASH to $REMOTE_HASH on branch '$CURRENT_BRANCH'"

# 4. Pull changes
git checkout "$CURRENT_BRANCH"
git pull --ff-only origin "$CURRENT_BRANCH"

# 5. Deploy updated files to $INSTALL_DIR
if [ -d "$REPO_DIR/rpi-touchscreen" ]; then
    SRC_DIR="$REPO_DIR/rpi-touchscreen"
else
    SRC_DIR="$REPO_DIR"
fi

cp -r "$SRC_DIR/server.py" "$INSTALL_DIR/"
cp -r "$SRC_DIR/sonos_device.py" "$INSTALL_DIR/"
cp -r "$SRC_DIR/lyrics.py" "$INSTALL_DIR/"
cp -r "$SRC_DIR/static" "$INSTALL_DIR/"
cp -r "$SRC_DIR/kiosk" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/kiosk/"*.sh 2>/dev/null || true

# Remember repo path
echo "$REPO_DIR" > "$INSTALL_DIR/repo_path.txt"

# 6. Update systemd units if modified
mkdir -p "$HOME/.config/systemd/user"
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen.service" "$HOME/.config/systemd/user/" 2>/dev/null || true
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen-update.service" "$HOME/.config/systemd/user/" 2>/dev/null || true
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen-update.timer" "$HOME/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload 2>/dev/null || true

# 7. Restart application
log "Restarting sonos-touchscreen service..."
pkill -f "server.py" >/dev/null 2>&1 || true
systemctl --user restart sonos-touchscreen 2>/dev/null || true

log "Successfully updated to $REMOTE_HASH and restarted sonos-touchscreen."
exit 0
