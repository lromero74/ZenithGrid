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

## How AI Bot Allocation System Works

**Understanding the full signal-to-execution flow:**

### 1. Budget Hierarchy (Nested Allocations)
The system uses multiple layers of allocation that multiply together:

```
Total Account BTC Value (aggregate)
  └─> Bot Budget Percentage (e.g., 33%)
      └─> Max Concurrent Deals (e.g., 6) → divides bot budget into per-position budgets
          └─> AI Suggested Allocation % (e.g., 8%) → final order size
              └─> Must meet Coinbase minimum (0.0001 BTC)
```

### 2. Real Example (DASH-BTC that failed):
```
- Total account BTC: 0.01193891 BTC
  - In positions: 0.00792877 BTC
  - Available: 0.00401014 BTC

- Bot budget (33%): 0.00393984 BTC
  - Already in positions: 0.00066654 BTC
  - Available for new: 0.00327331 BTC

- Max concurrent deals: 6
  - Per-position budget: 0.00393984 / 6 = 0.00065664 BTC

- AI suggests 8% allocation for DASH-BTC
  - Actual order size: 0.00065664 × 0.08 = 0.00005253 BTC

- Coinbase minimum: 0.0001 BTC
  - Result: ❌ REJECTED (below minimum)
```

### 3. Signal Flow Process
1. **Bot runs check cycle** (every 15 minutes for AI bots)
2. **AI analyzes all pairs** and returns recommendations with:
   - Action (buy/sell/hold)
   - Confidence score (0-100%)
   - Suggested allocation percentage
   - Reasoning
3. **Trading engine picks up signals** and processes each one:
   - Checks if position already exists
   - Calculates aggregate account value
   - Applies bot budget percentage
   - Divides by max concurrent deals
   - Applies AI's suggested allocation percentage
   - Validates against exchange minimums
4. **Execution or rejection**:
   - If valid: Place order with Coinbase
   - If invalid: Log reason (below minimum, insufficient funds, etc.)

### 4. Common Rejection Reasons

**"Below exchange minimum"** (most common):
- Cause: Small bot budget + many max deals + low AI allocation % = tiny order
- Solution: Reduce max_concurrent_deals, increase bot budget %, or tune AI prompts for larger allocations

**"Insufficient funds"**:
- Cause: Not enough available BTC after subtracting open positions
- Solution: Close some positions or increase bot budget

**"Max concurrent deals reached"**:
- Cause: Already have 6 open positions (if max_concurrent_deals = 6)
- Solution: Wait for positions to close or increase max_concurrent_deals

### 5. AI Decision Storage
- AI decisions are logged in `ai_bot_logs` table regardless of execution
- Fields: bot_id, timestamp, product_id, decision, confidence, thinking, context
- Even rejected orders are logged with `position_id: None`
- Check Dashboard → AI Bot Reasoning tab to see all decisions

### 6. Key Insight
**The AI doesn't know about exchange minimums or budget constraints.** It just suggests what percentage of the per-position budget to allocate. The trading engine enforces the constraints and may reject the AI's suggestion if it results in an order below Coinbase's minimum (0.0001 BTC for BTC pairs).

- we run on testbot host in EC2
- keep our repo tidy
- tidy branch and repo applies to local as well as testbot host
- one-off debug and helper scripts belong in scripts folder
- when you make a change to local repo you have to push so testbot host (where this is actually running) can pick it up
- remember that changes to local db need to be done on prod db at testbot ec2 host, and you must back up prod db before applying changes.
- production trading db is backend/trading.db
- remember our python is in venv on localhost and in production (testbot host on EC2)
- lint all code before committing new or changed code
- CRITICAL!: be sure to stop production services (EC2 testbot host), and back up the database (/home/ec2-user/GetRidOf3CommasBecauseTheyGoDownTooOften/backend/trading.db), before applying migrations to it

## Commercialization Roadmap

See **COMMERCIALIZATION.md** for the full roadmap to make Zenith Grid sale-ready.

**Quick checklist when building new features:**
1. Does this work for multiple users, not just me?
2. Are credentials stored securely (encrypted, not in code)?
3. Is this feature something users would pay for?
4. Does it help differentiate from 3Commas?
- when updating prod, use our "update.py --yes" script to ensure user experience will be good when they* too use it
- be sure not to hardcode migrations paths (use os.path.dirname pattern we currently use).  Otherwise the update.py script will fail when other folk try to update and run.