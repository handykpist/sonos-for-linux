#!/usr/bin/env bash
# Sonos Touchscreen Controller - Auto Update Script
# Checks remote Git repository for updates, pulls changes, and restarts the kiosk.

set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/sonos-touchscreen}"
LOG_FILE="$INSTALL_DIR/update.log"
STATUS_FILE="$INSTALL_DIR/update_status.json"
mkdir -p "$INSTALL_DIR"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

set_status() {
    local status="$1"
    local msg="$2"
    log "$msg"
    cat << EOF > "$STATUS_FILE"
{
  "status": "$status",
  "message": "$msg",
  "timestamp": $(date +%s)
}
EOF
}

set_status "checking" "Checking for Sonos Touchscreen updates..."

# 1. Determine Git repository location
REPO_DIR=""
if [ -d "$INSTALL_DIR/.git" ]; then
    REPO_DIR="$INSTALL_DIR"
elif [ -f "$INSTALL_DIR/repo_path.txt" ]; then
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
    set_status "error" "No Git repository found for sonos-touchscreen. Cannot perform auto-update."
    exit 1
fi

cd "$REPO_DIR"

# 2. Check remote repository configuration
REMOTE_NAME="origin"
if ! git remote | grep -q "^origin$"; then
    REMOTE_NAME="$(git remote | head -n 1)"
fi

if [ -z "$REMOTE_NAME" ]; then
    set_status "error" "No Git remote configured in repository ($REPO_DIR)."
    exit 1
fi

# 3. Check network connectivity / remote git access (10s timeout, without -h flag)
set_status "checking" "Connecting to remote Git repository ($REMOTE_NAME)..."
if ! timeout 10 git ls-remote --exit-code "$REMOTE_NAME" HEAD >/dev/null 2>&1; then
    set_status "error" "Unable to reach remote '$REMOTE_NAME'. Please verify your Wi-Fi/network connection."
    exit 1
fi

# 4. Fetch remote changes
set_status "checking" "Fetching latest commits from remote..."
git fetch "$REMOTE_NAME"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")"
if [ "$CURRENT_BRANCH" = "HEAD" ]; then
    if git rev-parse --verify "$REMOTE_NAME/main" >/dev/null 2>&1; then
        CURRENT_BRANCH="main"
    else
        CURRENT_BRANCH="rpi4-touchscreen"
    fi
fi

LOCAL_HASH="$(git rev-parse HEAD 2>/dev/null)"
REMOTE_HASH="$(git rev-parse "$REMOTE_NAME/$CURRENT_BRANCH" 2>/dev/null || git rev-parse "$REMOTE_NAME/main" 2>/dev/null)"

if [ -z "$REMOTE_HASH" ]; then
    set_status "error" "Could not resolve remote branch $REMOTE_NAME/$CURRENT_BRANCH."
    exit 1
fi

FORCE_UPDATE=0
if [ "$1" = "--force" ]; then
    FORCE_UPDATE=1
fi

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ] && [ $FORCE_UPDATE -eq 0 ]; then
    set_status "uptodate" "Already up-to-date with the latest version."
    exit 0
fi

log "Update detected! Moving from $LOCAL_HASH to $REMOTE_HASH on branch '$CURRENT_BRANCH'"
set_status "updating" "Applying updates from remote ($CURRENT_BRANCH)..."

# 5. Pull changes safely
git checkout "$CURRENT_BRANCH" 2>/dev/null || true
git reset --hard "$REMOTE_NAME/$CURRENT_BRANCH"

# 6. Deploy updated files to $INSTALL_DIR
set_status "deploying" "Installing updated files..."
if [ -d "$REPO_DIR/rpi-touchscreen" ]; then
    SRC_DIR="$REPO_DIR/rpi-touchscreen"
else
    SRC_DIR="$REPO_DIR"
fi

if [ "$SRC_DIR" != "$INSTALL_DIR" ]; then
    cp -r "$SRC_DIR/server.py" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/sonos_device.py" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/lyrics.py" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/static" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/kiosk" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/speakers_cache.json" "$INSTALL_DIR/" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/kiosk/"*.sh 2>/dev/null || true
fi

# Remember repo path
echo "$REPO_DIR" > "$INSTALL_DIR/repo_path.txt"

# 7. Update systemd units if modified
mkdir -p "$HOME/.config/systemd/user"
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen.service" "$HOME/.config/systemd/user/" 2>/dev/null || true
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen-update.service" "$HOME/.config/systemd/user/" 2>/dev/null || true
cp -u "$INSTALL_DIR/kiosk/sonos-touchscreen-update.timer" "$HOME/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload 2>/dev/null || true

set_status "restarting" "Update complete! Restarting Sonos Controller..."
sleep 1

# 8. Restart application
log "Restarting sonos-touchscreen service..."
pkill -f "server.py" >/dev/null 2>&1 || true
systemctl --user restart sonos-touchscreen 2>/dev/null || true

set_status "done" "Sonos Touchscreen successfully updated to $REMOTE_HASH."
exit 0
