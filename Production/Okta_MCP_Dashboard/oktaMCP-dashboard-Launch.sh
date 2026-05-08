#!/bin/bash

# ─── Run as user setup ────────────────────────────────────────────────────────
loggedInUser=$(stat -f "%Su" /dev/console)
uid=$(id -u "$loggedInUser" 2>/dev/null)

runAsUser() {
    launchctl asuser "$uid" sudo -u "$loggedInUser" "$@"
}
# ─────────────────────────────────────────────────────────────────────────────

DASHBOARD_DIR="/Users/$loggedInUser/Library/Application Support/oktaMCP-dashboard"
SERVER_SCRIPT="$DASHBOARD_DIR/dashboard/server.py"
VENV_PYTHON="$DASHBOARD_DIR/venv/bin/python"   # ← use venv interpreter, not system python3
DASHBOARD_URL="http://localhost:8080"
LOG_FILE="$DASHBOARD_DIR/launch.log"            # ← matches launch.log used by server.py and postinstall

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"  # ← tee so it also prints to stdout, and bracket format to match server.py
}

log "=== Launch started (user: $loggedInUser) ==="

# Check 1 — apfel
if ! runAsUser command -v apfel &> /dev/null; then
    log "FAIL: apfel not found in PATH"
    runAsUser osascript -e 'display dialog "apfel is not installed. Please contact IT." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi
log "OK: apfel found"

# Check 2 — model availability
if ! runAsUser apfel --model-info 2>&1 | grep -q "available:.*yes"; then
    log "FAIL: Apple Intelligence model not available"
    runAsUser osascript -e 'display dialog "Apple Intelligence is not ready. If you have just enabled it, the model may still be downloading — wait a few minutes and try again. If the issue persists, contact IT." buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi
log "OK: Apple Intelligence model available"

# Check 3 — dashboard files
if [ ! -f "$SERVER_SCRIPT" ]; then
    log "FAIL: server.py not found at $SERVER_SCRIPT"
    runAsUser osascript -e 'display dialog "Dashboard files not found. Please re-run the MDM package from Self Service." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi
log "OK: server.py found"

# Check 4 — venv interpreter exists            ← new: catch missing venv before trying to launch
if [ ! -f "$VENV_PYTHON" ]; then
    log "FAIL: venv not found at $VENV_PYTHON — re-run the MDM package from Self Service"
    runAsUser osascript -e 'display dialog "Python environment not found. Please re-run the MDM package from Self Service." buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi
log "OK: venv interpreter found"

# Check 5 — already running
if curl -s "$DASHBOARD_URL" > /dev/null 2>&1; then
    log "INFO: Dashboard already running — opening browser"
    runAsUser open "$DASHBOARD_URL"
    exit 0
fi

# Check 6 — kill orphaned apfel on 11434
APFEL_PID=$(lsof -ti :11434)
if [ -n "$APFEL_PID" ]; then
    log "INFO: Killing orphaned apfel process $APFEL_PID on port 11434"
    kill "$APFEL_PID" 2>/dev/null
    sleep 1
fi

# Start server using venv interpreter          ← was python3.13 — now uses venv/bin/python
log "INFO: Starting dashboard server"
runAsUser "$VENV_PYTHON" "$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1 &

# Poll until ready — server.py opens the browser itself, so just wait and exit
for i in $(seq 1 30); do
    if curl -s "$DASHBOARD_URL" > /dev/null 2>&1; then
        log "OK: Dashboard ready after ${i} polls"
        exit 0
    fi
    sleep 0.5
done

log "FAIL: Dashboard did not respond within 15 seconds"
runAsUser osascript -e 'display dialog "Dashboard failed to start within 15 seconds. Check launch.log for details." buttons {"OK"} default button "OK" with icon stop'
exit 1