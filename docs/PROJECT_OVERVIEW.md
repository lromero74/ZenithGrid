# ETH/BTC Trading Bot - Project Summary

## ✅ What's Been Built

A complete, production-ready trading bot that connects directly to Coinbase (replacing 3Commas) with a sophisticated DCA strategy based on MACD signals.

## 🎯 Core Features Implemented

### Trading Engine
- ✅ **MACD Signal Detection** - Detects crossovers above AND below zero baseline
- ✅ **DCA Strategy** - Dollar cost averages into positions on repeated MACD cross-ups
- ✅ **Profit Protection** - Only sells when minimum profit threshold met (default 1%)
- ✅ **Position Limits** - Caps maximum BTC usage per position (default 25%)
- ✅ **USD Tracking** - Records profit in both BTC and USD

### Backend (Python/FastAPI)
- ✅ Coinbase Advanced Trade API integration
- ✅ Custom MACD indicator with pandas
- ✅ SQLite database for position/trade history
- ✅ Price monitoring service (60-second intervals)
- ✅ RESTful API with WebSocket support
- ✅ Automatic signal processing and trade execution

### Frontend (React/TypeScript)
- ✅ Real-time dashboard with live account value (BTC & USD)
- ✅ MACD and price charts (Recharts)
- ✅ Position history with detailed trade logs
- ✅ Configurable settings panel
- ✅ Manual controls (pause, cancel, force close)
- ✅ Responsive UI with Tailwind CSS

### Deployment
- ✅ EC2 deployment scripts
- ✅ Systemd service configuration
- ✅ Nginx reverse proxy setup
- ✅ SSH tunnel access (secure remote access)
- ✅ Comprehensive README and Quick Start guides

## 📁 Project Structure

```
GetRidOf3CommasBecauseTheyGoDownTooOften/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── coinbase_client.py   # Coinbase API wrapper
│   │   ├── trading_engine.py    # Core trading logic
│   │   ├── indicators.py        # MACD calculation
│   │   ├── price_monitor.py     # Price monitoring service
│   │   ├── models.py            # Database models
│   │   ├── database.py          # DB configuration
│   │   └── config.py            # Settings management
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # Main dashboard
│   │   │   ├── Positions.tsx    # Position history
│   │   │   └── Settings.tsx     # Configuration
│   │   ├── services/
│   │   │   └── api.ts           # API client
│   │   ├── types/
│   │   │   └── index.ts         # TypeScript types
│   │   ├── App.tsx              # Main app component
│   │   └── main.tsx             # Entry point
│   ├── package.json
│   └── vite.config.ts
├── deployment/
│   ├── deploy.sh                # Automated deployment script
│   ├── trading-bot.service      # Systemd service file
│   └── nginx-trading-bot.conf   # Nginx configuration
├── README.md                    # Full documentation
├── QUICKSTART.md                # Quick start guide
└── PROJECT_SUMMARY.md           # This file
```

## 🔄 Trading Logic Flow

1. **Price Monitor** fetches ETH/BTC price every 60 seconds
2. **MACD Calculator** updates indicators and stores in database
3. **Signal Detector** checks for MACD crossovers
4. **Trading Engine** processes signals:

### MACD Cross Up (Bullish)
```
IF no position exists:
  → Create position
  → Buy with initial_btc_percentage (default 5%)
ELSE IF position exists:
  → DCA buy with dca_percentage (default 3%)
  → Only if within max_btc_usage limit
```

### MACD Cross Down (Bearish)
```
IF position exists:
  IF current_profit >= min_profit_percentage (default 1%):
    → Sell entire ETH position
    → Close position and record profit (BTC & USD)
  ELSE:
    → Hold position (wait for better price)
```

## 🎚️ Configurable Parameters

All adjustable via Settings UI:

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| Initial BTC % | 5.0 | 0.1-100 | First position entry |
| DCA % | 3.0 | 0.1-100 | Dollar cost average amount |
| Max BTC Usage % | 25.0 | 1-100 | Position size limit |
| Min Profit % | 1.0 | 0.1-100 | Required profit to sell |
| MACD Fast | 12 | 1-100 | Fast EMA period |
| MACD Slow | 26 | 1-100 | Slow EMA period |
| MACD Signal | 9 | 1-100 | Signal line period |

## 🚀 Quick Start

### Local Testing
```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your Coinbase API keys
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install && npm run dev
```

### EC2 Deployment
```bash
# Upload code
scp -i key.pem -r . ubuntu@your-ec2-ip:~/GetRidOf3CommasBecauseTheyGoDownTooOften

# Deploy
ssh -i key.pem ubuntu@your-ec2-ip
cd GetRidOf3CommasBecauseTheyGoDownTooOften/deployment
./deploy.sh

# Access via tunnel
ssh -i key.pem -L 8080:localhost:80 ubuntu@your-ec2-ip
# Then open: http://localhost:8080
```

## 🔒 Security Features

- ✅ Coinbase API keys stored in `.env` (not committed)
- ✅ SSH tunnel access (no public exposure)
- ✅ EC2 security groups (SSH only)
- ✅ Validated API requests
- ✅ CORS protection

## 📊 Dashboard Features

### Header
- **Account Value**: Real-time total in BTC and USD
- **Auto-refresh**: Updates every 5 seconds

### Stats Cards
- Current ETH/BTC price
- Total profit (BTC)
- Win rate percentage
- Account balances

### Active Position Card
- Total BTC spent / ETH acquired
- Average buy price
- Number of trades
- Usage percentage
- **Controls**: Cancel or Force Close buttons

### Charts
- ETH/BTC price chart (24h)
- MACD indicator with signal line

## 🎯 Manual Controls

### Start/Stop Bot
- Pause monitoring without affecting positions
- Resume monitoring at any time

### Cancel Position
- Closes position tracking
- Leaves ETH in account (no sell)
- Use when you want to hold ETH manually

### Force Close Position
- Sells entire ETH position at market price
- Records profit/loss
- Use when you want to exit regardless of profit threshold

## 📈 Position Tracking

Each position records:
- All buy/sell trades with timestamps
- Average buy price and sell price
- Total BTC spent and received
- Profit in BTC and USD
- BTC/USD price at open and close
- MACD values at each trade

## 🔍 Monitoring & Logs

```bash
# Backend service logs
sudo journalctl -u trading-bot -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log

# Restart services
sudo systemctl restart trading-bot
sudo systemctl restart nginx
```

## ⚠️ Important Notes

### MACD Behavior
**The bot WILL buy on ANY MACD cross-up, even when both MACD and signal are above zero!**

This is intentional - crossovers work in both directions:
- MACD crosses above signal → BUY (bullish)
- MACD crosses below signal → SELL (bearish, if profitable)

The zero baseline is NOT a barrier for signals.

### Risk Management
- Start with LOW percentages for testing
- Monitor the dashboard regularly
- Set realistic profit thresholds
- Don't over-allocate to single positions

### API Limits
- Coinbase has rate limits
- Price monitor runs every 60 seconds (safe)
- Don't manually spam trade buttons

## 🛠️ Troubleshooting

### "API connection failed"
→ Check Coinbase API credentials in `.env`
→ Verify API key has "View" and "Trade" permissions

### "Bot not buying on MACD cross-up"
→ Check if you've reached max BTC usage limit
→ View signals in database or logs

### "Frontend won't load"
→ Check nginx is running: `sudo systemctl status nginx`
→ Verify frontend was built: `ls frontend/dist`

### "Database errors"
→ Delete and recreate: `rm backend/trading.db` then restart

## 📚 Documentation Files

- **README.md** - Full setup and deployment guide
- **QUICKSTART.md** - 5-minute local setup guide
- **PROJECT_SUMMARY.md** - This file (overview)

## 🎉 Success Criteria - All Met!

✅ Connects to Coinbase (not 3Commas)
✅ Monitors ETH/BTC with MACD signals
✅ DCA buys on cross-ups (above or below zero)
✅ Sells on cross-downs with 1%+ profit
✅ Limits max BTC usage per position (25%)
✅ Tracks positions and profit (BTC & USD)
✅ Real-time dashboard with graphs
✅ User-configurable parameters
✅ Manual position controls
✅ Deployable to EC2
✅ Secure SSH tunnel access

## 🚀 Ready to Deploy!

Your ETH/BTC trading bot is complete and ready to use. Follow the QUICKSTART.md for immediate testing, or README.md for full EC2 deployment.

**Happy Trading! 📈**
