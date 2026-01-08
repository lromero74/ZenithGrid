#!/bin/bash
# Auto-deployment script - checks for git changes and deploys intelligently
# Runs every minute via systemd timer

set -e

REPO_DIR=~/ZenithGrid
LOG_FILE=~/auto-deploy.log
MAX_LOG_SIZE=1048576  # 1MB

# Rotate log if too large
if [ -f "$LOG_FILE" ] && [ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null) -gt $MAX_LOG_SIZE ]; then
    mv "$LOG_FILE" "$LOG_FILE.old"
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

cd "$REPO_DIR"

# Fetch latest changes
git fetch origin main >/dev/null 2>&1

# Check if there are changes
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    # No changes
    exit 0
fi

log "📥 New changes detected, deploying..."

# Get list of changed files
CHANGED_FILES=$(git diff --name-only HEAD origin/main)

log "Changed files:"
echo "$CHANGED_FILES" | while read file; do
    log "  - $file"
done

# Determine what needs to be restarted
RESTART_BACKEND=false
RESTART_FRONTEND=false

while IFS= read -r file; do
    if [[ "$file" == backend/* ]]; then
        RESTART_BACKEND=true
    elif [[ "$file" == frontend/* ]]; then
        RESTART_FRONTEND=true
    fi
done <<< "$CHANGED_FILES"

# Backup .env file
if [ -f backend/.env ]; then
    cp backend/.env backend/.env.backup
fi

# Pull changes
log "🔄 Pulling changes from origin/main..."
git pull origin main

# Restore .env if it changed
if [ -f backend/.env.backup ]; then
    if ! cmp -s backend/.env backend/.env.backup; then
        log "⚠️  .env file changed - restoring backup"
        mv backend/.env.backup backend/.env
    else
        rm backend/.env.backup
    fi
fi

# Restart services as needed
if [ "$RESTART_BACKEND" = true ]; then
    log "🔄 Restarting backend service..."
    sudo systemctl restart trading-bot-backend
    log "✅ Backend restarted"
fi

if [ "$RESTART_FRONTEND" = true ]; then
    log "ℹ️  Frontend changes detected (no service to restart - static files updated)"
fi

if [ "$RESTART_BACKEND" = false ] && [ "$RESTART_FRONTEND" = false ]; then
    log "ℹ️  Changes detected but no services need restart (docs/config only)"
fi

log "✅ Deployment complete!"
