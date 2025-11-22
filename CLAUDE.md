- if you create bots while we are developing, please do not create them started.
- Always think "How does 3Commas do it?" and do that.
- new work should be done in dev branches and merged after I confirm good
- always do git diff check before new git add to make sure we didn't lose functionality we want to keep
- we are now running from EC2.  Restarts should be done with "sudo systemctl restart trading-bot-backend"

## EC2 Test Instance (testbot)

**Instance Details:**
- **Host**: testbot (SSH alias in ~/.ssh/config)
- **Type**: t2.micro (1 vCPU, 1GB RAM, ~$8.50/month)
- **OS**: Amazon Linux 2023
- **Region**: us-east-1
- **Purpose**: 24/7 trading bot hosting

**Services Running:**
- Trading bot backend (systemd: trading-bot-backend.service)
- Trading bot frontend (Vite dev server on port 5173)
- Both auto-start on boot

**Accessing Frontend:**
- Frontend runs on testbot:5173 (Vite dev server)
- Access locally via SSH port forwarding (localhost:5173 → testbot:5173)
- After code changes, restart Vite: `ssh testbot "pkill -f vite && cd ~/GetRidOf3CommasBecauseTheyGoDownTooOften/frontend && nohup npm run dev > /tmp/vite.log 2>&1 &"`

**Management:**
```bash
ssh testbot
cd GetRidOf3CommasBecauseTheyGoDownTooOften
./bot.sh start|stop|restart|status|logs
```

**Important Notes:**
- ❌ **DO NOT install Claude Code on testbot** - t2.micro only has 1GB RAM and already runs backend + frontend
- Trading bot services consume most available memory
- If Claude Code needed, upgrade to t3.small (2GB RAM) first
- Database synced from local, stop local services before copying DB to avoid corruption

## Required Python Libraries for AI Strategies

**CRITICAL**: The following libraries must be installed on EC2 for AI strategies to work properly:

```bash
# Install on EC2 testbot (already in requirements.txt)
cd GetRidOf3CommasBecauseTheyGoDownTooOften/backend
./venv/bin/pip install anthropic==0.74.0
./venv/bin/pip install google-generativeai==0.8.3
./venv/bin/pip install openai==2.8.1
```

**Why These Are Required:**
- `anthropic`: Claude AI API integration for AI autonomous strategy
- `google-generativeai`: Google Gemini AI integration for alternative AI strategies
- `openai`: OpenAI API integration (GPT models) for AI decision-making

**Installation Notes:**
1. These are already listed in `backend/requirements.txt`
2. On fresh EC2 instance: `pip install -r requirements.txt`
3. If missing libraries cause errors in AI Bot Reasoning logs, install individually
4. After installation, always restart backend: `sudo systemctl restart trading-bot-backend`
- please always back up the database before you mess with it

## CRITICAL: Budget Calculation for BTC Bots

**IMPORTANT - BTC-based bots should ONLY look at BTC and BTC-pair values:**

For BTC-based bots (bots trading BTC pairs like ETH-BTC, ADA-BTC, etc.):

**The aggregate BTC value MUST include:**
1. Available BTC balance in the account
2. PLUS the BTC value of ALL altcoin positions in BTC pairs ONLY (e.g., if you have 10 ADA and ADA-BTC is trading at 0.00001, that's 0.0001 BTC)

**USD-based pairs should NOT be included** because when sold, they don't add to available BTC for BTC-based trading. Only BTC and BTC-pair positions should count toward the BTC bot's budget.

**Example Calculation:**
- Available BTC: 0.00273944
- ADA position: 100 ADA × 0.00001 BTC (ADA-BTC price) = 0.001 BTC
- AAVE position: 0.5 AAVE × 0.0005 BTC (AAVE-BTC price) = 0.00025 BTC
- **Total aggregate BTC = 0.00273944 + 0.001 + 0.00025 = 0.00398944 BTC**

Then bot budget = (budget_percentage / 100) × total_aggregate_btc

**This is implemented in `backend/app/coinbase_unified_client.py` in the `calculate_aggregate_btc_value()` function.**

If you see "INSUFFICIENT FUNDS" errors, verify that `calculate_aggregate_btc_value()` is correctly summing BOTH:
- BTC balance
- BTC value of all altcoin holdings in BTC pairs (NOT USD pairs)
- we run on testbot host in EC2