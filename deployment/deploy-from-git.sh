#!/bin/bash
# Deployment script for fedora.local production host
# Pulls latest changes from origin/main and restarts zenithgrid.service
# Preserves .env file with production credentials

set -e

echo "🚀 Deploying from origin/main..."

cd ~/ZenithGrid

# Backup .env file (in case it gets overwritten)
cp backend/.env backend/.env.backup

# Pull latest changes
echo "📥 Pulling latest changes from origin/main..."
git pull origin main

# Restore .env if it changed
if ! cmp -s backend/.env backend/.env.backup; then
    echo "⚠️  .env file changed - restoring backup"
    mv backend/.env.backup backend/.env
else
    rm backend/.env.backup
fi

# Restart backend service
echo "🔄 Restarting zenithgrid user service..."
systemctl --user restart zenithgrid

echo "✅ Deployment complete!"
echo "📊 Service status:"
systemctl --user status zenithgrid --no-pager | head -5
