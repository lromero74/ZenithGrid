# ETH/BTC Trading Bot

A focused trading bot that connects to Coinbase and implements an automated DCA (Dollar Cost Averaging) strategy for ETH/BTC trading based on MACD signals.

## Features

- **Automated MACD-based Trading**: Monitors ETH/BTC price and executes trades based on MACD crossover signals
- **DCA Strategy**: Dollar cost averages into positions when MACD crosses up before selling
- **Profit Protection**: Only sells when minimum profit threshold is met (default 1%)
- **Position Management**: Track positions with detailed trade history
- **Real-time Dashboard**: Monitor account value, positions, and market data
- **Configurable Parameters**: Adjust trading parameters, MACD settings, and risk limits
- **Manual Controls**: Pause bot, cancel positions, or force close at market price
- **USD Tracking**: Track profits in both BTC and USD

## Architecture

- **Backend**: Python FastAPI with async SQLite database
- **Frontend**: React + TypeScript with Recharts for visualization
- **Exchange**: Coinbase Advanced Trade API
- **Indicators**: Custom MACD implementation with pandas

## Prerequisites

- Python 3.11+
- Node.js 18+
- Coinbase account with API credentials
- BTC and/or ETH in your Coinbase account

## Setup

### 1. Get Coinbase API Credentials

1. Go to [Coinbase Advanced Trade](https://www.coinbase.com/settings/api)
2. Create a new API key with permissions for:
   - View accounts
   - Trade
3. Save your API Key and API Secret securely

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env and add your Coinbase credentials
nano .env
```

Update `.env` with your values:
```env
COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here

# Optional: Adjust trading parameters
INITIAL_BTC_PERCENTAGE=5.0
DCA_PERCENTAGE=3.0
MAX_BTC_USAGE_PERCENTAGE=25.0
MIN_PROFIT_PERCENTAGE=1.0
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build
```

### 4. Run Locally

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend (development):**
```bash
cd frontend
npm run dev
```

Access the app at: `http://localhost:5173`

## Deployment to EC2

### 1. Launch EC2 Instance

1. Launch Ubuntu 22.04 LTS instance (t3.small or larger recommended)
2. Configure security group to allow:
   - SSH (port 22) from your IP
   - HTTP (port 80) - optional
   - HTTPS (port 443) - optional

### 2. Initial Server Setup

```bash
# SSH into your instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python
sudo apt install python3.11 python3.11-venv python3-pip -y

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install nginx (for serving frontend)
sudo apt install nginx -y
```

### 3. Deploy Application

```bash
# Clone or upload your code
git clone <your-repo-url>
# OR use scp to upload:
# scp -i your-key.pem -r . ubuntu@your-ec2-ip:~/trading-bot

cd trading-bot

# Backend setup
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env with your Coinbase credentials
cp .env.example .env
nano .env

# Frontend setup
cd ../frontend
npm install
npm run build

# Copy built frontend to nginx
sudo cp -r dist/* /var/www/html/
```

### 4. Setup Systemd Service

Create `/etc/systemd/system/trading-bot.service`:

```bash
sudo nano /etc/systemd/system/trading-bot.service
```

```ini
[Unit]
Description=ETH/BTC Trading Bot API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-bot/backend
Environment="PATH=/home/ubuntu/trading-bot/backend/venv/bin"
ExecStart=/home/ubuntu/trading-bot/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Start and enable service
sudo systemctl daemon-reload
sudo systemctl start trading-bot
sudo systemctl enable trading-bot

# Check status
sudo systemctl status trading-bot
```

### 5. Configure Nginx

Create `/etc/nginx/sites-available/trading-bot`:

```bash
sudo nano /etc/nginx/sites-available/trading-bot
```

```nginx
server {
    listen 80;
    server_name _;

    root /var/www/html;
    index index.html;

    # Frontend
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default

# Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Access via SSH Tunnel

Since the app is for personal use, access it securely via SSH port forwarding:

```bash
# On your local machine
ssh -i your-key.pem -L 8080:localhost:80 ubuntu@your-ec2-ip
```

Then access the app at: `http://localhost:8080`

## Usage

### Starting the Bot

1. Open the dashboard
2. Check that your Coinbase API connection is working (green indicator)
3. Review and adjust settings if needed
4. Click "Start Bot" to begin monitoring

### Monitoring

- **Dashboard**: View current position, account value, and MACD chart
- **Positions**: Browse historical positions and detailed trade logs
- **Settings**: Adjust trading parameters and MACD settings

### Manual Controls

- **Pause Bot**: Stop monitoring without affecting current positions
- **Cancel Position**: Close position tracking without selling (ETH remains in account)
- **Force Close**: Sell entire position at current market price

## Trading Logic

### Buy Signals (MACD Cross Up)

1. **No Position**: Opens new position with initial BTC percentage (default 5%)
2. **Existing Position**: DCA buys with configured percentage (default 3%) if within max BTC limit

### Sell Signals (MACD Cross Down)

1. Checks current profit
2. Sells only if profit ≥ minimum threshold (default 1%)
3. Otherwise holds position

### Risk Management

- **Max BTC Usage**: Limits total BTC allocated per position (default 25% of balance at position open)
- **DCA Protection**: Prevents over-allocation during market downturns
- **Profit Threshold**: Ensures trades close profitably

## Configuration

All parameters can be adjusted via the Settings page:

| Parameter | Default | Description |
|-----------|---------|-------------|
| Initial BTC % | 5.0% | Percentage of BTC to use for initial buy |
| DCA % | 3.0% | Percentage of BTC to use for DCA buys |
| Max BTC Usage % | 25.0% | Maximum BTC allocation per position |
| Min Profit % | 1.0% | Minimum profit required to sell |
| MACD Fast Period | 12 | Fast EMA period |
| MACD Slow Period | 26 | Slow EMA period |
| MACD Signal Period | 9 | Signal line period |

## Monitoring & Logs

```bash
# View backend logs
sudo journalctl -u trading-bot -f

# View nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Troubleshooting

### API Connection Issues

- Verify Coinbase API credentials in `.env`
- Check API key permissions
- Ensure API key is not IP-restricted

### Database Issues

```bash
# Reset database (⚠️ deletes all data)
cd backend
rm trading.db
python -m app.main  # Recreates database
```

### Service Not Starting

```bash
# Check logs
sudo journalctl -u trading-bot -n 50

# Restart service
sudo systemctl restart trading-bot
```

## Security Notes

- **Never commit `.env` file** to version control
- **Use SSH key authentication** for EC2 access
- **Access via SSH tunnel** rather than exposing publicly
- **Regularly rotate** API keys
- **Monitor account** for unexpected activity

## License

Private use only.

## Support

For issues or questions, check the logs and verify your configuration matches this README.
