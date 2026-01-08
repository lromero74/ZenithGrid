# Quick Start Guide

## Local Development (5 minutes)

### 1. Get Coinbase API Credentials

1. Go to https://www.coinbase.com/settings/api
2. Create API key with "View" and "Trade" permissions
3. Save your API Key and Secret

### 2. Setup Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
nano .env  # Add your Coinbase credentials
```

### 3. Setup Frontend

```bash
cd frontend
npm install
```

### 4. Run the Application

**Terminal 1 - Backend:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

**Access:** http://localhost:5173

### 5. Start Trading

1. Click "Start Bot" in the dashboard
2. Monitor MACD signals and positions
3. Adjust settings as needed

---

## EC2 Deployment (One Command)

### Prerequisites
- EC2 instance running Ubuntu 22.04
- SSH access to instance
- Security group allows SSH (port 22)

### Deploy

```bash
# Upload code to EC2
scp -i your-key.pem -r . ubuntu@your-ec2-ip:~/ZenithGrid

# SSH into instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Run deployment script
cd ZenithGrid/deployment
./deploy.sh
```

### Access via SSH Tunnel

```bash
# On your local machine
ssh -i your-key.pem -L 8080:localhost:80 ubuntu@your-ec2-ip
```

**Access:** http://localhost:8080

---

## Key Features

✅ **MACD-based Trading** - Buys on MACD cross-up (above OR below zero!)
✅ **DCA Strategy** - Averages down on repeated cross-ups
✅ **Profit Protection** - Only sells when profitable
✅ **Manual Controls** - Pause, cancel, or force close positions
✅ **Real-time Dashboard** - Live account value in BTC & USD

## Important MACD Behavior

**The bot WILL buy on MACD cross-ups regardless of position relative to zero baseline:**

- MACD crosses signal from below → BUY (even if both lines are above zero)
- MACD crosses signal from above → SELL (only if profitable)

This means the bot can buy during uptrends when MACD recrosses above the signal line!

## Default Settings

| Setting | Value | Description |
|---------|-------|-------------|
| Initial Buy | 5% | First position size |
| DCA Amount | 3% | Additional buys |
| Max Usage | 25% | Position size limit |
| Min Profit | 1% | Required profit to sell |

Adjust in Settings page as needed!

## Need Help?

- Check backend logs: `sudo journalctl -u trading-bot -f`
- View positions: Go to "Positions" tab
- Monitor signals: Watch dashboard MACD chart
- Adjust parameters: Settings page

## Safety Tips

⚠️ **Start small** - Test with low percentages first
⚠️ **Monitor regularly** - Check dashboard daily
⚠️ **Secure your keys** - Never share API credentials
⚠️ **Use SSH tunnel** - Don't expose publicly
