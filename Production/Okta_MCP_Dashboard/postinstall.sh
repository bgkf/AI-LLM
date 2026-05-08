#!/bin/bash
set -e

LOGGED_IN_USER=$(stat -f "%Su" /dev/console)
UID_NUM=$(id -u "$LOGGED_IN_USER")
INSTALL_DIR="/Users/$LOGGED_IN_USER/Library/Application Support/oktaMCP-dashboard"
LOG="$INSTALL_DIR/launch.log"
PYTHON="/usr/local/bin/python3"
APFEL="/usr/local/bin/apfel"

mkdir -p "$INSTALL_DIR"
touch "$LOG"
chown "$LOGGED_IN_USER" "$LOG"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

runAsUser() {
  if [ "$LOGGED_IN_USER" != "loginwindow" ]; then
    launchctl asuser "$UID_NUM" sudo -u "$LOGGED_IN_USER" "$@"
  else
    log "ERROR: No user logged in — cannot run user-context commands"
    exit 1
  fi
}

log "=== Post-install started ==="
log "Logged in user: $LOGGED_IN_USER (uid $UID_NUM)"
log "Install dir: $INSTALL_DIR"
log "Python: $($PYTHON --version 2>&1)"

# ---------------------------------------------------------------------------
# Remove quarantine attribute from apfel
# ---------------------------------------------------------------------------

if [ ! -f "$APFEL" ]; then
    log "ERROR: apfel not found at $APFEL"
    exit 1
fi

log "Removing quarantine attribute from $APFEL"
xattr -dr com.apple.quarantine "$APFEL"

if xattr "$APFEL" | grep -q "com.apple.quarantine"; then
    log "ERROR: Failed to remove quarantine attribute from apfel"
    exit 1
fi

log "apfel quarantine attribute removed successfully"

# ---------------------------------------------------------------------------
# Create venv and install dependencies as the logged-in user
# ---------------------------------------------------------------------------

log "Creating venv at $INSTALL_DIR/venv as $LOGGED_IN_USER"
runAsUser "$PYTHON" -m venv "$INSTALL_DIR/venv" >> "$LOG" 2>&1

log "Upgrading pip"
runAsUser "$INSTALL_DIR/venv/bin/pip" install --upgrade pip >> "$LOG" 2>&1

log "Installing dependencies from requirements.txt"
if ! runAsUser "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" >> "$LOG" 2>&1; then
    log "ERROR: pip install failed — see above for details"
    exit 1
fi

log "Installing okta-mcp-server from bundled source"
if ! runAsUser "$INSTALL_DIR/venv/bin/pip" install "$INSTALL_DIR/data/okta-mcp-server-src/" >> "$LOG" 2>&1; then
    log "ERROR: okta-mcp-server install failed — see above for details"
    exit 1
fi

log "Writing MCP start script"
cat > "$INSTALL_DIR/data/okta-mcp-server/start.sh" << EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/okta-mcp-server"
EOF
chmod +x "$INSTALL_DIR/data/okta-mcp-server/start.sh"
log "MCP start script written and marked executable"

log "=== Post-install completed successfully ==="
exit 0