# Domain Knowledge Reference

This document contains trading-domain-specific knowledge that Claude needs when working on related features. Referenced from CLAUDE.md.

## BTC Budget Calculation for BTC-Pair Bots

**Rule: BTC-based bots should ONLY look at BTC and BTC-pair values.**

For bots trading BTC pairs (ETH-BTC, ADA-BTC, etc.):

**The aggregate BTC value MUST include:**
1. Available BTC balance in the account
2. PLUS the BTC value of ALL altcoin positions in BTC pairs ONLY

**USD-based pairs are excluded** — when sold, they don't add to available BTC.

**Example:**
```
Available BTC:  0.00273944
ADA (100 × 0.00001 BTC):  0.001 BTC
AAVE (0.5 × 0.0005 BTC):  0.00025 BTC
─────────────────────────────────────
Total aggregate BTC:  0.00398944 BTC
```

Bot budget = `(budget_percentage / 100) × total_aggregate_btc`

**Implementation**: `backend/app/coinbase_unified_client.py` → `calculate_aggregate_btc_value()`

If you see "INSUFFICIENT FUNDS" errors, verify that function sums both BTC balance and BTC-pair altcoin holdings (NOT USD pairs).

---

## AI Bot Allocation System (Signal-to-Execution Flow)

### Budget Hierarchy (Nested Allocations)

```
Total Account BTC Value (aggregate)
  └─> Bot Budget Percentage (e.g., 33%)
      └─> Max Concurrent Deals (e.g., 6) → divides bot budget into per-position budgets
          └─> AI Suggested Allocation % (e.g., 8%) → final order size
              └─> Must meet Coinbase minimum (0.0001 BTC)
```

### Real Example (DASH-BTC that was rejected):
```
Total account BTC: 0.01193891 BTC
  In positions: 0.00792877 BTC  |  Available: 0.00401014 BTC

Bot budget (33%): 0.00393984 BTC
  Already in positions: 0.00066654 BTC  |  Available for new: 0.00327331 BTC

Per-position budget (÷ 6 deals): 0.00065664 BTC
AI suggests 8% → 0.00005253 BTC
Coinbase minimum: 0.0001 BTC → REJECTED (below minimum)
```

### Signal Flow Process
1. **Bot runs check cycle** (15min for AI bots)
2. **AI analyzes all pairs** → returns action, confidence, allocation %, reasoning
3. **Trading engine processes signals**: checks existing positions, calculates budget, applies allocations, validates against exchange minimums
4. **Execution or rejection**: place order or log rejection reason

### Common Rejection Reasons

| Reason | Cause | Fix |
|--------|-------|-----|
| Below exchange minimum | Small budget × many deals × low AI allocation % | Reduce max_concurrent_deals, increase bot budget %, tune AI prompts |
| Insufficient funds | Not enough available BTC after open positions | Close positions or increase bot budget |
| Max concurrent deals reached | Already at limit (e.g., 6 open positions) | Wait for closes or increase max_concurrent_deals |

### Key Insight
**The AI doesn't know about exchange minimums or budget constraints.** It suggests an allocation percentage. The trading engine enforces constraints and may reject if the resulting order is below Coinbase's minimum.

### AI Decision Storage
- Logged in `ai_bot_logs` table regardless of execution outcome
- Fields: bot_id, timestamp, product_id, decision, confidence, thinking, context
- Even rejected orders are logged with `position_id: None`
- Visible in Dashboard → AI Bot Reasoning tab

---

## Infrastructure Details

### MFA / Trusted Devices
- TOTP MFA via pyotp + qrcode[pil]
- Trusted device tokens: 30-day JWT + DB record
- IP geolocation: ip-api.com (city, state, country)
- TOTP secrets encrypted at rest via Fernet (`backend/app/encryption.py`)
- Key endpoints: `/api/auth/mfa/setup`, `/mfa/verify-setup`, `/mfa/verify`, `/mfa/disable`, `/mfa/devices`
- Public signup is disabled (guard in `auth_router.py`)

### AWS SES Email
- **Production access**: 50K emails/day, 14/sec
- **Sender**: noreply@romerotechsolutions.com
- **Domain**: romerotechsolutions.com verified with DKIM in us-east-1
- **IAM Role**: ZenithGridEC2Role (attached to EC2, no API keys needed)
- **Usage**: boto3 SES client, region us-east-1

### AI Provider Libraries
These must be installed in the venv for AI strategies:
```bash
/home/ec2-user/ZenithGrid/backend/venv/bin/python3 -m pip install anthropic google-generativeai openai
```
All three are in `backend/requirements.txt`. If missing, AI Bot Reasoning logs will show import errors.
