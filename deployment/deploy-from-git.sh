#!/bin/bash
# Deployment script for EC2 instance
# Pulls latest changes from origin/main and restarts the backend service
# Preserves .env file with production credentials

set -e

echo "🚀 Deploying from origin/main..."

cd ~/GetRidOf3CommasBecauseTheyGoDownTooOften

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
echo "🔄 Restarting trading-bot-backend service..."
sudo systemctl restart trading-bot-backend

echo "✅ Deployment complete!"
echo "📊 Service status:"
sudo systemctl status trading-bot-backend --no-pager | head -5
