# ETH/BTC Trading Bot - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Using the Application](#using-the-application)
7. [Trading Strategy](#trading-strategy)
8. [Persistence & Recovery](#persistence--recovery)
9. [API Reference](#api-reference)
10. [Troubleshooting](#troubleshooting)
11. [Development](#development)

---

## Overview

This is an automated trading bot for the ETH/BTC pair on Coinbase. It uses the MACD (Moving Average Convergence Divergence) indicator to generate buy/sell signals and implements a Dollar Cost Averaging (DCA) strategy to manage positions.

**Key Capabilities:**
- Automated MACD-based trading on Coinbase
- TradingView-style candlestick charts with multiple timeframes
- DCA strategy with configurable parameters
- Real-time monitoring and notifications
- Position tracking with BTC and USD profit calculation
- Persistent storage (survives power outages)
- Full GUI for configuration and monitoring

---

## Features

### 1. TradingView-Style Chart
- **Candlestick Display**: Professional candlestick chart for ETH/BTC
- **Multiple Timeframes**: 1m, 5m, 15m, 30m, 1h, 2h, 6h, 1D
- **Volume Indicator**: Toggle volume bars on/off
- **MACD Indicator**: Separate panel with MACD line, signal line, and histogram
- **Interactive Controls**: Click timeframe buttons to switch intervals
- **Real-time Updates**: Fetches latest candle data from Coinbase

### 2. Trading Strategy
- **MACD Cross-Up**: Buy signal when MACD crosses above signal line (works above AND below zero)
- **MACD Cross-Down**: Sell signal when MACD crosses below signal line
- **DCA (Dollar Cost Averaging)**: Automatically buy more on additional cross-up signals
- **Profit Target**: Minimum 1% profit required to sell
- **Position Limits**: Max 25% of BTC balance per position (configurable)

### 3. Position Management
- **Active Position Tracking**: View current position details in real-time
- **Cancel Position**: Cancel without selling (keeps ETH in account)
- **Force Close**: Sell entire position at current market price
- **Trade History**: View all buys/sells for each position
- **Profit Tracking**: Track profit in both BTC and USD

### 4. API Key Management
- **GUI Entry**: Enter Coinbase API credentials directly in Settings page
- **Test Connection**: Verify credentials before saving
- **Clear Keys**: Remove credentials with confirmation
- **Secure Storage**: Keys saved to .env file, masked in UI
- **Permission Guide**: Shows required Coinbase permissions (View + Trade)

### 5. Persistence & Recovery
- **SQLite Database**: All data stored in `trading.db`
- **Position Recovery**: Resumes active positions after restart
- **Trade History**: Complete record of all transactions
- **MACD State**: Market data preserved for indicator calculations
- **Power Loss Safe**: No data loss on unexpected shutdown

---

## Architecture

### Technology Stack

**Backend:**
- Python 3.13
- FastAPI (REST API framework)
- SQLAlchemy (async ORM)
- SQLite (database)
- httpx (async HTTP client)
- Coinbase Advanced Trade API

**Frontend:**
- React 18 with TypeScript
- Vite (build tool)
- TanStack Query (data fetching)
- Lightweight Charts v5 (TradingView-style charts)
- Tailwind CSS (styling)
- Lucide React (icons)

**Deployment:**
- uvicorn (ASGI server)
- nginx (reverse proxy for production)
- systemd (service management)

### Project Structure

```
ZenithGrid/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app & endpoints
│   │   ├── config.py            # Settings & configuration
│   │   ├── database.py          # Database connection
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── coinbase_client.py   # Coinbase API wrapper
│   │   ├── trading_engine.py    # Trading logic & DCA
│   │   ├── price_monitor.py     # Price monitoring service
│   │   └── indicators.py        # MACD calculation
│   ├── requirements.txt         # Python dependencies
│   ├── .env                     # Environment variables (API keys)
│   └── test_connection.py       # Test Coinbase connection
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── TradingChart.tsx # TradingView-style chart
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # Main dashboard
│   │   │   ├── Positions.tsx    # Position history
│   │   │   └── Settings.tsx     # Configuration page
│   │   ├── services/
│   │   │   └── api.ts           # API client
│   │   ├── types/
│   │   │   └── index.ts         # TypeScript types
│   │   ├── App.tsx              # Main app component
│   │   └── main.tsx             # Entry point
│   ├── package.json             # Node dependencies
│   └── vite.config.ts           # Vite configuration
├── deployment/
│   ├── deploy.sh                # EC2 deployment script
│   ├── nginx-trading-bot.conf   # Nginx config
│   └── trading-bot.service      # Systemd service
├── bot.sh                       # Start/stop/restart script
├── README.md                    # Quick start guide
├── QUICKSTART.md               # 5-minute setup
└── DOCUMENTATION.md            # This file
```

---

## Installation & Setup

### Prerequisites

1. **Python 3.13+**
2. **Node.js 20+ and npm**
3. **Git** (for version control)
4. **Coinbase Account** with API keys

### Quick Start

1. **Install Dependencies:**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

   cd ../frontend
   npm install
   ```

2. **Configure Environment:**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env and add your Coinbase API credentials
   ```

3. **Start the Bot:**
   ```bash
   cd ..
   ./bot.sh start
   ```

4. **Access the UI:**
   - Open http://localhost:5173 in your browser

### Coinbase API Setup

1. Go to https://www.coinbase.com/settings/api
2. Create a new API key with these permissions:
   - **View**: Read account balances and transaction history
   - **Trade**: Place buy and sell orders
3. Copy the API Key and API Secret
4. Enter them in Settings page or in `backend/.env` file

---

## Configuration

### Settings Page (GUI)

All settings can be configured via the Settings page in the web UI:

#### 1. **Coinbase API Credentials**
- **API Key**: Your Coinbase API key
- **API Secret**: Your Coinbase API secret
- **Test Connection**: Verify credentials work
- **Clear Keys**: Remove credentials

#### 2. **Trading Parameters**
- **Initial BTC Percentage** (default: 5.0%)
  - Percentage of BTC balance to spend on first buy
  - Example: If you have 1 BTC and set 5%, first buy uses 0.05 BTC

- **DCA Percentage** (default: 3.0%)
  - Percentage of BTC balance for additional buys
  - Used when MACD crosses up again before selling

- **Max BTC Usage Percentage** (default: 25.0%)
  - Maximum percentage of BTC balance for entire position
  - Prevents over-allocation to single position

- **Minimum Profit Percentage** (default: 1.0%)
  - Required profit before selling on MACD cross-down
  - Position won't close unless profit >= this value

#### 3. **MACD Indicator Parameters**
- **Candle Interval** (default: 5 Minutes)
  - Timeframe for MACD calculation
  - Options: 1m, 5m, 15m, 30m, 1h, 2h, 6h, 1D
  - **Important**: This affects signal frequency
    - Shorter intervals (1m, 5m) = More signals, faster trades
    - Longer intervals (1h, 1D) = Fewer signals, longer trends

- **Fast Period** (default: 12)
  - Fast EMA period for MACD calculation

- **Slow Period** (default: 26)
  - Slow EMA period for MACD calculation

- **Signal Period** (default: 9)
  - Signal line EMA period

**Standard MACD Values**: 12, 26, 9 (recommended for most strategies)

### Environment Variables (.env)

```bash
# Coinbase API Configuration
COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here

# Database
DATABASE_URL=sqlite+aiosqlite:///./trading.db

# Security
SECRET_KEY=your-secret-key-for-jwt-change-this

# Trading Parameters (can be overridden in GUI)
INITIAL_BTC_PERCENTAGE=5.0
DCA_PERCENTAGE=3.0
MAX_BTC_USAGE_PERCENTAGE=25.0
MIN_PROFIT_PERCENTAGE=1.0

# MACD Parameters
MACD_FAST_PERIOD=12
MACD_SLOW_PERIOD=26
MACD_SIGNAL_PERIOD=9
CANDLE_INTERVAL=FIVE_MINUTE
```

---

## Using the Application

### Starting the Bot

```bash
./bot.sh start
```

This starts both backend (port 8000) and frontend (port 5173).

### Dashboard

**Location**: http://localhost:5173

**Features:**
1. **Control Bar**
   - Monitor Status: Shows if price monitoring is running
   - Start/Stop Monitor: Toggle automated trading
   - Current Price: Real-time ETH/BTC price

2. **Stats Cards**
   - Total Positions: Number of completed positions
   - Total Profit: Cumulative profit in BTC
   - Win Rate: Percentage of profitable trades
   - Current Position: Active position details

3. **Active Position Panel** (when position is open)
   - Position ID and status
   - BTC spent and ETH acquired
   - Current profit (BTC and USD)
   - Average buy price
   - Max BTC allowed
   - Controls:
     - **Cancel**: Cancel position without selling
     - **Force Close**: Sell at current market price

4. **TradingView-Style Chart**
   - Timeframe selector (1m to 1D)
   - Volume toggle
   - MACD toggle
   - Interactive candlestick chart
   - Separate MACD indicator panel

### Position History

**Location**: http://localhost:5173/positions

View all past positions with:
- Open/close timestamps
- Entry and exit prices
- Total BTC spent and received
- Profit in BTC and USD
- Profit percentage
- Number of trades

### Settings

**Location**: http://localhost:5173/settings

Configure:
- Coinbase API credentials
- Trading parameters
- MACD indicator settings
- Candle interval

**Important**: Click "Save Settings" after making changes.

### Bot Management Script

```bash
# Start the bot
./bot.sh start

# Stop the bot
./bot.sh stop

# Restart the bot
./bot.sh restart

# Check status
./bot.sh status

# View logs
./bot.sh logs
```

**Log Files:**
- Backend: `.pids/backend.log`
- Frontend: `.pids/frontend.log`

---

## Trading Strategy

### MACD Strategy Explained

The bot uses MACD (Moving Average Convergence Divergence) to identify trend changes:

**Components:**
1. **MACD Line**: Fast EMA - Slow EMA
2. **Signal Line**: EMA of MACD Line
3. **Histogram**: MACD Line - Signal Line

**Signals:**
- **Cross-Up** (Bullish): MACD crosses above Signal → BUY
- **Cross-Down** (Bearish): MACD crosses below Signal → SELL (if profitable)

**Important**: Cross-ups trigger buys regardless of whether MACD is above or below the zero line.

### DCA (Dollar Cost Averaging) Strategy

**How it works:**

1. **First Buy** (MACD Cross-Up)
   - Bot detects MACD cross-up signal
   - Buys ETH with `initial_btc_percentage` of BTC balance
   - Opens new position
   - Records average buy price

2. **Additional Buys** (DCA)
   - If MACD crosses up AGAIN before selling
   - Bot buys more ETH with `dca_percentage` of BTC balance
   - Updates average buy price
   - Continues until `max_btc_usage_percentage` reached

3. **Sell Signal** (MACD Cross-Down)
   - Bot checks if profit >= `min_profit_percentage`
   - If YES: Sells entire ETH position
   - If NO: Waits for profit target to be reached
   - Records profit in BTC and USD

**Example:**
```
BTC Balance: 1.0 BTC
Initial %: 5%
DCA %: 3%
Max %: 25%

Trade Sequence:
1. MACD Cross-Up → Buy 0.05 BTC worth of ETH (5%)
2. MACD Cross-Up → Buy 0.03 BTC worth of ETH (8% total)
3. MACD Cross-Up → Buy 0.03 BTC worth of ETH (11% total)
4. Price drops, MACD Cross-Up → Buy 0.03 BTC (14% total)
5. Price rises, profit > 1%, MACD Cross-Down → Sell all ETH
```

### Risk Management

**Position Limits:**
- Maximum 25% of BTC balance per position (configurable)
- Prevents over-exposure to single trade
- Protects against large losses

**Profit Target:**
- Minimum 1% profit required (configurable)
- Won't sell at a loss on cross-down signal
- Waits for profitable exit

**Stop Loss:**
- Not implemented (consider adding based on your risk tolerance)
- Manual force close available if needed

### Choosing the Right Timeframe

**Shorter Timeframes (1m, 5m, 15m):**
- ✅ More signals, faster trades
- ✅ Good for volatile markets
- ✅ Quick profit opportunities
- ❌ More false signals
- ❌ Higher transaction fees
- ❌ Requires more monitoring

**Longer Timeframes (1h, 2h, 6h, 1D):**
- ✅ Fewer false signals
- ✅ Better for trends
- ✅ Lower transaction fees
- ❌ Fewer trading opportunities
- ❌ Slower to react to changes
- ❌ May miss quick moves

**Recommended Starting Point:**
- **5-15 minutes** for active trading
- **1-2 hours** for swing trading
- **Test with small percentages** first

---

## Persistence & Recovery

### Database Schema

The bot uses SQLite to store all data in `backend/trading.db`.

**Tables:**

1. **positions**
   - id (primary key)
   - status (open, closed, cancelled)
   - opened_at, closed_at
   - initial_btc_balance
   - max_btc_allowed
   - total_btc_spent
   - total_eth_acquired
   - average_buy_price
   - sell_price
   - total_btc_received
   - profit_btc
   - profit_percentage
   - btc_usd_price_at_open
   - btc_usd_price_at_close
   - profit_usd

2. **trades**
   - id (primary key)
   - position_id (foreign key)
   - timestamp
   - side (BUY, SELL)
   - btc_amount
   - eth_amount
   - price
   - trade_type (initial, dca, close)
   - order_id (Coinbase order ID)

3. **signals**
   - id (primary key)
   - timestamp
   - signal_type (cross_up, cross_down)
   - macd_value
   - macd_signal
   - macd_histogram
   - price
   - action_taken
   - reason

4. **market_data**
   - id (primary key)
   - timestamp
   - price
   - macd_value
   - macd_signal
   - macd_histogram

### What Happens After Power Loss

**Scenario**: Bot is running with an active position, power goes out for 2 weeks.

**On Restart:**

1. **Database Loads**
   - Bot reads `trading.db`
   - Finds active position (status = "open")
   - Loads position details:
     - Total BTC spent
     - Total ETH acquired
     - Average buy price
     - Trade history

2. **Coinbase Sync**
   - Connects to Coinbase API
   - Verifies current ETH balance
   - Gets current ETH/BTC price
   - Calculates current profit

3. **Resume Monitoring**
   - Starts price monitoring
   - Begins calculating MACD on new candles
   - Watches for cross-down signal
   - Will sell when:
     - MACD crosses down AND
     - Profit >= minimum profit percentage

4. **No Data Loss**
   - Average buy price preserved
   - DCA trades remembered
   - Position limits still enforced
   - Profit calculation accurate

**Important Notes:**
- ✅ Position recovery is automatic
- ✅ Profit targets still enforced
- ✅ No manual intervention needed
- ❌ Doesn't track price changes during downtime
- ❌ May miss sell signals that occurred while offline

### Backup & Restore

**Backup:**
```bash
# Backup database
cp backend/trading.db backend/trading.db.backup

# Backup .env file
cp backend/.env backend/.env.backup
```

**Restore:**
```bash
# Restore database
cp backend/trading.db.backup backend/trading.db

# Restore .env
cp backend/.env.backup backend/.env
```

**Automated Backup** (recommended):
```bash
# Add to crontab for daily backups
0 0 * * * cp /path/to/backend/trading.db /path/to/backups/trading-$(date +\%Y\%m\%d).db
```

---

## API Reference

### Base URL
- **Development**: http://localhost:8000
- **Production**: http://your-domain.com

### Endpoints

#### System

**GET /**
- Returns API status
- Response: `{"message": "ETH/BTC Trading Bot API", "status": "running"}`

**GET /api/status**
- Get system status
- Response: Connection status, monitor status

#### Dashboard

**GET /api/dashboard**
- Get dashboard statistics
- Response:
  ```json
  {
    "current_position": {...},
    "total_positions": 10,
    "total_profit_btc": 0.05,
    "win_rate": 80.0,
    "current_price": 0.034567,
    "btc_balance": 1.0,
    "eth_balance": 10.5,
    "monitor_running": true
  }
  ```

#### Positions

**GET /api/positions**
- Get all positions
- Query params: `limit` (default: 50), `offset` (default: 0)
- Response: Array of position objects

**GET /api/positions/{position_id}**
- Get specific position
- Response: Position object with trades

**POST /api/positions/{position_id}/cancel**
- Cancel position without selling
- Response: Updated position

**POST /api/positions/{position_id}/force-close**
- Force close position at market price
- Response: Closed position with profit

#### Trades

**GET /api/trades**
- Get all trades
- Query params: `position_id`, `limit`, `offset`
- Response: Array of trade objects

#### Signals

**GET /api/signals**
- Get MACD signals
- Query params: `limit` (default: 50)
- Response: Array of signal objects

#### Market Data

**GET /api/market-data**
- Get recent market data
- Query params: `hours` (default: 24)
- Response: Array of OHLCV + MACD data

**GET /api/candles**
- Get historical candle data
- Query params:
  - `product_id` (default: ETH-BTC)
  - `granularity` (ONE_MINUTE, FIVE_MINUTE, etc.)
  - `limit` (default: 300)
- Response:
  ```json
  {
    "candles": [
      {
        "time": 1699123456,
        "open": 0.034,
        "high": 0.035,
        "low": 0.033,
        "close": 0.034,
        "volume": 100.5
      }
    ],
    "interval": "FIVE_MINUTE",
    "product_id": "ETH-BTC"
  }
  ```

#### Account

**GET /api/account/balances**
- Get account balances
- Response:
  ```json
  {
    "btc": 1.0,
    "eth": 10.5,
    "eth_value_in_btc": 0.35,
    "total_btc_value": 1.35,
    "current_eth_btc_price": 0.034,
    "btc_usd_price": 50000.0,
    "total_usd_value": 67500.0
  }
  ```

#### Settings

**GET /api/settings**
- Get current settings
- Response: Settings object (API keys masked)

**POST /api/settings**
- Update settings
- Body:
  ```json
  {
    "coinbase_api_key": "your_key",
    "coinbase_api_secret": "your_secret",
    "initial_btc_percentage": 5.0,
    "dca_percentage": 3.0,
    "max_btc_usage_percentage": 25.0,
    "min_profit_percentage": 1.0,
    "macd_fast_period": 12,
    "macd_slow_period": 26,
    "macd_signal_period": 9,
    "candle_interval": "FIVE_MINUTE"
  }
  ```
- Response: `{"message": "Settings updated successfully"}`

**POST /api/test-connection**
- Test Coinbase API credentials
- Body:
  ```json
  {
    "coinbase_api_key": "your_key",
    "coinbase_api_secret": "your_secret"
  }
  ```
- Response:
  ```json
  {
    "success": true,
    "message": "Connection successful! BTC Balance: 1.00000000, ETH Balance: 10.50000000",
    "btc_balance": 1.0,
    "eth_balance": 10.5
  }
  ```

#### Monitor Control

**POST /api/monitor/start**
- Start price monitoring
- Response: `{"message": "Monitor started"}`

**POST /api/monitor/stop**
- Stop price monitoring
- Response: `{"message": "Monitor stopped"}`

---

## Troubleshooting

### Common Issues

#### 1. Backend won't start

**Error**: `401 Unauthorized` in logs

**Solution**:
- Check Coinbase API credentials in Settings
- Verify API key has View and Trade permissions
- Test connection using "Test Connection" button

**Error**: `greenlet library is required`

**Solution**:
```bash
cd backend
source venv/bin/activate
pip install greenlet
```

#### 2. Frontend shows blank page

**Solution**:
```bash
cd frontend
npm install
npm run dev
```

Check browser console for errors.

#### 3. Chart not displaying

**Error**: `addCandlestickSeries is not a function`

**Solution**: Already fixed in latest version. If still seeing this:
```bash
cd frontend
npm install lightweight-charts@latest
```

#### 4. Position not recovering after restart

**Check**:
1. Database file exists: `ls backend/trading.db`
2. Check backend logs: `tail -f .pids/backend.log`
3. Verify position in database:
   ```bash
   sqlite3 backend/trading.db "SELECT * FROM positions WHERE status='open';"
   ```

#### 5. MACD signals not triggering trades

**Possible Reasons**:
- Monitor not running (click "Start Monitor")
- Not enough historical data (wait 26+ candles)
- Position limit reached (check max BTC usage)
- API credentials invalid

**Check**:
- Dashboard shows "Monitor: Running"
- Backend logs show price updates
- Test connection in Settings

### Logs

**View Backend Logs:**
```bash
tail -f .pids/backend.log
```

**View Frontend Logs:**
```bash
tail -f .pids/frontend.log
```

**Check Process Status:**
```bash
./bot.sh status
```

### Performance

**Slow Chart Loading:**
- Reduce candle limit in TradingChart.tsx
- Use longer timeframes (1h, 6h, 1D)
- Clear old market_data from database

**High CPU Usage:**
- Increase `interval_seconds` in price_monitor.py
- Use longer candle intervals
- Reduce MACD calculation frequency

---

## Development

### Running in Development Mode

**Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm run dev
```

### Adding New Features

**Add New API Endpoint:**
1. Add endpoint in `backend/app/main.py`
2. Add corresponding function in `frontend/src/services/api.ts`
3. Update TypeScript types in `frontend/src/types/index.ts`
4. Use in React components

**Add New Indicator:**
1. Implement calculation in `backend/app/indicators.py`
2. Add to `TradingEngine` logic in `backend/app/trading_engine.py`
3. Add toggle in `frontend/src/components/TradingChart.tsx`

### Testing

**Test Coinbase Connection:**
```bash
cd backend
source venv/bin/activate
python test_connection.py
```

**Test API Endpoints:**
```bash
curl http://localhost:8000/api/status
curl http://localhost:8000/api/dashboard
curl http://localhost:8000/api/settings
```

### Deployment to Production

See `deployment/deploy.sh` for automated EC2 deployment.

**Manual Deployment:**
1. Set up server (Ubuntu 22.04+)
2. Install dependencies
3. Configure nginx as reverse proxy
4. Set up systemd service
5. Configure firewall
6. Use production .env settings

### Git Workflow

```bash
# Check status
git status

# Add changes
git add .

# Commit
git commit -m "Description of changes"

# View history
git log --oneline

# Create branch
git checkout -b feature-name

# Switch back to main
git checkout master
```

---

## Security Considerations

### API Keys

- ✅ Stored in `.env` file (not tracked in git)
- ✅ Masked in UI display
- ✅ Never logged or printed
- ❌ Stored in plaintext on disk
- ❌ Sent over HTTP in local development

**Production Recommendations:**
- Use HTTPS only
- Encrypt `.env` file at rest
- Use secret management service (AWS Secrets Manager, HashiCorp Vault)
- Rotate API keys regularly
- Use IP whitelist on Coinbase API keys

### Database

- Local SQLite file (no network exposure)
- Contains trade history (consider sensitive)
- Backup regularly
- Encrypt backups

### Network

- Default: localhost only (port 8000, 5173)
- Production: Use nginx with SSL/TLS
- Firewall: Allow only necessary ports
- Consider VPN for remote access

---

## Support & Resources

### Documentation
- Coinbase API: https://docs.cdp.coinbase.com/advanced-trade/docs
- FastAPI: https://fastapi.tiangolo.com/
- React: https://react.dev/
- Lightweight Charts: https://tradingview.github.io/lightweight-charts/

### Community
- Report issues in project repository
- Contribute improvements via pull requests

### Disclaimer

**⚠️ IMPORTANT ⚠️**

This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss and is not suitable for every investor.

- Past performance is not indicative of future results
- Automated trading can lead to significant losses
- Test with small amounts first
- Never invest more than you can afford to lose
- The authors are not responsible for any losses incurred

**Use at your own risk.**

---

## Changelog

### Version 1.0.0 (2025-01-08)
- Initial release
- MACD-based trading strategy
- DCA implementation
- TradingView-style charts
- Multiple timeframe support
- API key management in GUI
- Position tracking with BTC/USD profit
- SQLite persistence
- Power loss recovery

---

*Generated by Claude Code - Last Updated: 2025-01-08*
