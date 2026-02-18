- if you create bots while we are developing, please do not create them started.
- Always think "How does 3Commas do it?" and do that.
- new work should be done in dev branches and merged after I confirm good
- CRITICAL: Always `git diff` against the previous version before staging. Verify you are not losing functionality you did not explicitly intend to remove. If a diff shows deleted logic, confirm it was intentional — never silently drop working code.
- CRITICAL: Do the right thing, not the lazy thing. No re-export shims, backwards-compat wrappers, or proxy modules as permanent solutions. When moving code, actually move it — update all consumers to point at the new canonical location and delete the old one. A little extra work now gives us a solid, clean pattern. This applies everywhere: imports, migrations, refactors, file moves. Fix pre-existing bugs and lint errors you encounter — you are the only coder on this project, so there is no "someone else's problem". If you touch a file and see broken code, fix it.
- CRITICAL: No spaghetti code. We write properly hierarchical, layered, modularized code with a clear dependency graph. Think layer cake / tree structure: auth utilities → services → routers (never upward). No circular imports, no cross-layer reaches, no god files. If a file is growing beyond ~1200 lines, split it into logical modules.
- CRITICAL: Always update CHANGELOG.md as part of every commit that will be tagged. The changelog entry must be included in the same commit as the code changes so that users pulling a tagged version see what's in it. Use Keep a Changelog format (Added/Changed/Fixed/Removed sections). Never tag without a changelog entry.

## "Ship It" — Full Release Process

**When the user says "ship it", execute this entire process end-to-end:**

### 1. Determine Version
- **Patch bump** (X.Y.Z+1): bug fixes, security hardening, code quality — things that should already work
- **Minor bump** (X.Y+1.0): new features, new endpoints, new UI components
- **Major bump** (X+1.0.0): breaking changes (rare, user will specify)
- Check current version: `git describe --tags --abbrev=0`

### 2. Pre-flight Checks
- `git diff` to review all uncommitted changes — ensure nothing unwanted is staged
- Lint all changed files (flake8 for Python, tsc for TypeScript)
- Verify the dev branch is clean and all work is committed

### 3. Database & Schema (if applicable)
- **If any models changed** (`backend/app/models.py`):
  - Back up prod DB: `cp backend/trading.db backend/trading.db.bak.$(date +%s)`
  - Stop services: `./bot.sh stop`
  - Create/verify idempotent migration in `backend/migrations/`
  - Run migrations: `backend/venv/bin/python3 update.py --yes`
  - Update `setup.py` raw SQL if new tables/columns were added (for fresh installs)
  - Update `database.py` `Base.metadata.create_all()` models if needed (runtime init)
  - Restart after: `./bot.sh restart --dev --both` (or `--prod`)

### 4. Update Version References (all in the SAME commit)
All of these must match the new tag version:

| File | What to update |
|------|---------------|
| `CHANGELOG.md` | Add `## [vX.Y.Z] - YYYY-MM-DD` section (Keep a Changelog format: Added/Changed/Fixed/Removed/Security) |
| `docs/architecture.json` | `"version"` field at top of file |

### 5. Commit, Merge, Tag
```
git add <all changed files>
git commit -m "vX.Y.Z: <concise summary>"
git checkout main
git merge <dev-branch> --no-ff -m "Merge <dev-branch>: <summary>"
git tag vX.Y.Z
git push origin main --tags
```

### 6. Branch Cleanup
- Delete dev branch locally: `git branch -d <dev-branch>`
- Delete dev branch on remote: `git push origin --delete <dev-branch>`
- Return to main: `git checkout main`

### 7. Deploy to Production (EC2)
- Backend changes: `./bot.sh restart --dev --back-end` (or `--prod`)
- Frontend changes: `./bot.sh restart --dev --front-end` (Vite config/deps only)
- Both changed: `./bot.sh restart --dev --both` (or `--prod`)
- If switching modes, add `--force`: `./bot.sh restart --prod --force`
- Verify services are running: `./bot.sh status`

### 8. Post-ship Verification
- Confirm `git describe --tags --abbrev=0` shows the new tag
- Confirm no stale branches remain locally or on remote
- Confirm services are healthy

**The end state after "ship it": main branch is tagged, all version numbers match, dev branch is gone (local + remote), production is running the new code.**

## Service Restart Policy

**Always use `./bot.sh` for restarts — never call systemctl directly.**

```bash
./bot.sh restart --dev --back-end    # Backend only (Python changes)
./bot.sh restart --dev --front-end   # Frontend only (Vite config/deps)
./bot.sh restart --dev --both        # Both services
./bot.sh restart --prod              # Rebuild + restart (prod mode)
./bot.sh restart --prod --force      # Switch modes (e.g., dev → prod)
./bot.sh status                      # Check current mode and services
```

- The script enforces mode consistency (nginx, systemd, frontend service)
- In dev mode, you must specify `--back-end`, `--front-end`, or `--both`
- If you pass a mode different from current, it warns and requires `--force`
- Backend changes always require a restart (`--back-end`)
- Frontend-only changes in dev mode usually do NOT need a restart (Vite HMR handles it)
- Only restart frontend (`--front-end`) for Vite config changes or dependency updates
- Never restart services unnecessarily — it disrupts the running trading bot

## Current Environment Detection

**If hostname contains `ec2.internal`**: You are ON the EC2 production instance.
- Services run LOCALLY - no SSH needed
- Use `./bot.sh restart --dev --back-end` (or `--front-end`/`--both`/`--prod`) for restarts
- Use `./bot.sh status` to check mode and services
- Database is local: `backend/trading.db`
- This IS production - be careful with changes

**If hostname is something else (e.g., MacBook)**: You are on the development machine.
- Services run REMOTELY on testbot
- SSH required: `ssh testbot`
- Push changes to git, then pull on testbot

## EC2 Test Instance (testbot)

**Instance Details:**
- **Host**: testbot (SSH alias in ~/.ssh/config)
- **Type**: t2.micro (1 vCPU, 1GB RAM, ~$8.50/month)
- **OS**: Amazon Linux 2023
- **Region**: us-east-1
- **Purpose**: 24/7 trading bot hosting

**Services Running:**
- Trading bot backend (systemd: trading-bot-backend.service)
- Trading bot frontend (systemd: trading-bot-frontend.service)
- Both auto-start on boot
```

**Accessing Frontend:**
- Frontend runs on testbot:8100 (Vite prod server)

**Management:**
```bash
ssh testbot
cd ZenithGrid
./bot.sh start|stop|restart --dev --back-end|--front-end|--both|restart --prod [--force]|status|logs
```

**Important Notes:**
- Claude Code can now run on testbot (memory managed carefully)
- Database synced from local, stop local services before copying DB to avoid corruption

## Required Python Libraries for AI Strategies

**CRITICAL**: The following libraries must be installed on EC2 for AI strategies to work properly:

```bash
# Install on EC2 testbot (already in requirements.txt)
cd ZenithGrid/backend
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
4. After installation, restart: `./bot.sh restart --dev --back-end` (or `--prod`)
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
- CRITICAL!: be sure to stop production services (EC2 testbot host), and back up the database (/home/ec2-user/ZenithGrid/backend/trading.db), before applying migrations to it

## Commercialization Roadmap

See **COMMERCIALIZATION.md** for the full roadmap to make Zenith Grid sale-ready.

**Quick checklist when building new features:**
1. Does this work for multiple users, not just me?
2. Are credentials stored securely (encrypted, not in code)?
3. Is this feature something users would pay for?
4. Does it help differentiate from 3Commas?
- when updating prod, use our "update.py --yes" script to ensure user experience will be good when they* too use it
- be sure not to hardcode migrations paths (use os.path.dirname pattern we currently use).  Otherwise the update.py script will fail when other folk try to update and run.
- you can tell the update.py script to answer "yes" automatically with "-y"
- if we are just fixing things that should already work, bump tag patch number when I tell you it's time (major.minor.patch)
- if we are adding a new feature, bump tag minor number when I tell you it's time (major.minor.patch)
- use `./bot.sh restart --dev --back-end` (or `--front-end`/`--both`/`--prod`) for restarts. Never call systemctl directly — the script manages nginx, systemd, and frontend service consistency. Never restart unnecessarily.
## HTTPS & Nginx (v2.3.0+)

**Public URL**: https://tradebot.romerotechsolutions.com
- **Nginx config**: /etc/nginx/conf.d/tradebot.conf (reverse proxy to localhost:8100)
- **SSL**: Let's Encrypt via certbot (auto-configured in nginx)
- **Renew SSL**: sudo certbot renew --nginx

**CRITICAL: pip install must use the venv Python, not system pip:**
```bash
# CORRECT — always use this form:
/home/ec2-user/ZenithGrid/backend/venv/bin/python3 -m pip install <package>

# WRONG — pip shebang may be broken, and system pip installs outside venv:
pip install <package>
pip3 install <package>
./venv/bin/pip install <package>
```

## MFA / Trusted Devices (v2.3.0+)

- TOTP MFA via pyotp + qrcode[pil] (installed in venv)
- Trusted device tokens (30-day JWT + DB record)
- IP geolocation via ip-api.com (city, state, country)
- TOTP secrets encrypted at rest via Fernet (backend/app/encryption.py)
- Key auth endpoints: /api/auth/mfa/setup, /mfa/verify-setup, /mfa/verify, /mfa/disable, /mfa/devices
- Public signup is disabled (guard in auth_router.py)

## AWS SES Email (v2.3.0+)

- **Production access**: Granted, 50K emails/day, 14/sec
- **Sender**: noreply@romerotechsolutions.com
- **Domain**: romerotechsolutions.com verified with DKIM in us-east-1
- **IAM Role**: ZenithGridEC2Role attached to this EC2 instance
- **Auth**: boto3 picks up IAM role credentials automatically — no API keys needed in code or .env
- **Policy**: SES-SendEmail (ses:SendEmail, ses:SendRawEmail, ses:GetSendQuota, ses:GetSendStatistics)
- **Usage**: Use boto3 SES client with region us-east-1, Source noreply@romerotechsolutions.com


