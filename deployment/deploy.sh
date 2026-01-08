#!/bin/bash

# ETH/BTC Trading Bot - EC2 Deployment Script
# Run this script on your EC2 instance after uploading the code

set -e

echo "🚀 Starting deployment..."

# Configuration
APP_DIR="/home/ubuntu/ZenithGrid"
SERVICE_NAME="trading-bot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as ubuntu user
if [ "$USER" != "ubuntu" ]; then
    echo -e "${RED}Please run this script as ubuntu user${NC}"
    exit 1
fi

# Update system
echo -e "${YELLOW}Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

# Install Python
echo -e "${YELLOW}Installing Python 3.11...${NC}"
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Node.js
echo -e "${YELLOW}Installing Node.js...${NC}"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# Install nginx
echo -e "${YELLOW}Installing nginx...${NC}"
sudo apt install -y nginx

# Setup backend
echo -e "${YELLOW}Setting up backend...${NC}"
cd $APP_DIR/backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${RED}.env file not found!${NC}"
    echo -e "${YELLOW}Creating .env from example...${NC}"
    cp .env.example .env
    echo -e "${RED}⚠️  Please edit $APP_DIR/backend/.env with your Coinbase API credentials${NC}"
    read -p "Press enter after editing .env file..."
fi

deactivate

# Setup frontend
echo -e "${YELLOW}Setting up frontend...${NC}"
cd $APP_DIR/frontend

# Install Node dependencies
npm install

# Build frontend
echo -e "${YELLOW}Building frontend...${NC}"
npm run build

# Deploy frontend to nginx
echo -e "${YELLOW}Deploying frontend to nginx...${NC}"
sudo mkdir -p /var/www/html/trading-bot
sudo cp -r dist/* /var/www/html/trading-bot/

# Setup systemd service
echo -e "${YELLOW}Setting up systemd service...${NC}"
sudo cp $APP_DIR/deployment/trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

# Setup nginx
echo -e "${YELLOW}Configuring nginx...${NC}"
sudo cp $APP_DIR/deployment/nginx-trading-bot.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
sudo nginx -t

# Start services
echo -e "${YELLOW}Starting services...${NC}"
sudo systemctl restart nginx
sudo systemctl restart $SERVICE_NAME
sudo systemctl enable $SERVICE_NAME

# Check service status
sleep 2
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✅ Backend service is running${NC}"
else
    echo -e "${RED}❌ Backend service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

if sudo systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✅ Nginx is running${NC}"
else
    echo -e "${RED}❌ Nginx failed to start${NC}"
    exit 1
fi

# Print access instructions
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}To access the application:${NC}"
echo ""
echo "1. From your local machine, run:"
echo -e "   ${GREEN}ssh -i your-key.pem -L 8080:localhost:80 ubuntu@$(curl -s ifconfig.me)${NC}"
echo ""
echo "2. Open your browser to:"
echo -e "   ${GREEN}http://localhost:8080${NC}"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  View logs:        sudo journalctl -u $SERVICE_NAME -f"
echo "  Restart backend:  sudo systemctl restart $SERVICE_NAME"
echo "  Restart nginx:    sudo systemctl restart nginx"
echo "  Edit config:      nano $APP_DIR/backend/.env"
echo ""
