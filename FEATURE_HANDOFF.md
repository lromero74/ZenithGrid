# Feature Development Handoff Document
**Created**: 2025-11-23
**Project**: ZenithGrid
**Status**: Planning Phase

---

## Feature Requests Overview

### 1. Portfolio Holdings - Overall PnL Tracking
**Status**: Not Started
**Priority**: Medium
**Description**: In Holdings table on Portfolio page, include overall PnL of Coin across all open deals.

**Implementation Notes**:
- Calculate aggregate PnL for each coin across all positions
- Display in Holdings table
- Consider realized vs unrealized PnL

**Files to Modify**:
- [ ] `frontend/src/pages/Portfolio.tsx` (or relevant portfolio component)
- [ ] Backend API endpoint for position aggregation

---

### 2. Portfolio BTC Balance Breakdown - Fix Calculations
**Status**: Not Started
**Priority**: High
**Description**: Fix BTC Balance Breakdown calculations in Portfolio page.

**Requirements**:
- **Total**: Should match "Total BTC Value"
- **In Open Positions**: Should reflect total BTC value of open BTC pairs ONLY
- **Free**: Should be calculated as `Total - (Reserved + In Open Positions)`

**Current Issue**: Calculations appear incorrect

**Files to Modify**:
- [ ] `frontend/src/pages/Portfolio.tsx`
- [ ] Backend balance calculation logic
- [ ] Reference: CLAUDE.md note about BTC-based bot budget calculations

---

### 3. Manual Position Closing - Add Limit Order Option
**Status**: Not Started
**Priority**: High
**Description**: Add ability to close positions via limit order in addition to market orders.

**Requirements**:
- Add "Close at Limit" option alongside existing "Close at Market Price"
- Slider between current Bid and Ask prices
- Slider defaults to Mark price
- Slider steps respect coin's minimum precision
- Show pending limit order in open positions with status indicator
- Track percentage filled
- Allow user to cancel or edit remaining unfilled portion
- Adjust limit price between updated bid/ask when editing
- Record fill steps in Closed (History) when complete
- Show multiple fill prices if filled at different levels

**Files to Modify**:
- [ ] Position close modal/dialog component
- [ ] Backend API for limit order placement
- [ ] Backend API for limit order editing/cancellation
- [ ] Position tracking system for partial fills
- [ ] History/Closed positions display

**Technical Considerations**:
- Need real-time bid/ask price updates
- Need to handle Coinbase limit order API
- Need websocket updates for partial fill notifications
- Need precision calculation per coin pair

---

### 4. Market Close - Slippage Warning
**Status**: Not Started
**Priority**: Medium
**Description**: Warn users about potential slippage when closing at market price.

**Requirements**:
- Detect when spread is wide
- Analyze order book volume for slippage estimation
- If slippage would consume >25% of profits, show warning
- Recommend limit order as alternative
- Allow user to proceed with market order if they accept risk

**Files to Modify**:
- [ ] Market close logic
- [ ] Order book analysis utility
- [ ] Warning modal component

**Technical Considerations**:
- Need order book depth data from Coinbase
- Need profit calculation for position
- Need slippage estimation algorithm

---

### 5. AI Bots - API Credit Indicator
**Status**: Not Started
**Priority**: Medium
**Description**: Show remaining API credits for AI bots on Bots page.

**Requirements**:
- Display credit balance indicator for each AI bot
- Make indicator clickable
- Click takes user to API provider page to top up credits
- Support multiple AI providers (Anthropic, OpenAI, Google Gemini)

**Files to Modify**:
- [ ] Bot card component
- [ ] Backend API to fetch credit balances from AI providers
- [ ] Link configuration for each AI provider's billing page

**Technical Considerations**:
- Anthropic API: Check usage/credits endpoint
- OpenAI API: Check usage/credits endpoint
- Google Gemini API: Check usage/credits endpoint
- Cache credit balance to avoid excessive API calls

---

### 6. Bots - Limit vs Market Order Selection
**Status**: Not Started
**Priority**: Medium
**Description**: Allow bots to choose between limit (Mark) and market orders for position closing.

**Requirements**:
- Add bot configuration option for close order type
- **Default**: Limit close at Mark price
- Support both limit and market close strategies

**Files to Modify**:
- [ ] Bot configuration schema (database)
- [ ] Bot settings UI
- [ ] Bot execution logic for closing positions

---

### 7. Bots Page - Trade Statistics Column
**Status**: Not Started
**Priority**: Low
**Description**: Add columns to Bots table tracking trade activity.

**Requirements**:
- **Total Closed Trades**: Count of all closed positions
- **Trades/Day**: Estimated daily trade frequency = `total_closed / days_since_created`

**Files to Modify**:
- [ ] Bots table component
- [ ] Backend API for bot statistics
- [ ] Database query for closed position counts

---

### 8. Bots Page - Budget Utilization Display (ORIGINAL REQUEST)
**Status**: Not Started
**Priority**: High
**Description**: Show percentage of allocated budget tied up in open positions on bot cards.

**Requirements**:
- Calculate: `(total_value_of_open_positions / bot_allocated_budget) * 100`
- Display on each bot card
- Consider BTC vs USD budget types (see CLAUDE.md critical note)

**Files to Modify**:
- [ ] Bot card component
- [ ] Backend API for position value aggregation
- [ ] Budget calculation utilities

**Technical Considerations**:
- For BTC bots: Only count BTC and BTC-pair positions
- For USD bots: Only count USD and USD-pair positions
- Reference: `backend/app/coinbase_unified_client.py::calculate_aggregate_btc_value()`

---

## Implementation Strategy

### Phase 1: Critical Fixes (High Priority)
1. Portfolio BTC Balance Breakdown fix (#2)
2. Manual Position Closing - Limit Orders (#3)
3. Bots Budget Utilization (#8)

### Phase 2: User Experience Enhancements (Medium Priority)
4. Market Close Slippage Warning (#4)
5. AI Bots API Credit Indicator (#5)
6. Bots Limit vs Market Order Selection (#6)

### Phase 3: Statistics & Analytics (Low Priority)
7. Portfolio Holdings Overall PnL (#1)
8. Bots Trade Statistics (#7)

---

## Development Workflow
- All new work should be done in dev branches
- Always run `git diff` before `git add` to verify no functionality loss
- Merge to main only after Louis confirms testing on testbot
- Restart backend on testbot after changes: `sudo systemctl restart trading-bot-backend`

---

## Notes
- **Database backups**: Always backup database before schema changes
- **EC2 Testing**: All features must be tested on testbot EC2 instance
- **Frontend Updates**: After code changes, restart Vite on testbot
- **3Commas Philosophy**: Always think "How does 3Commas do it?" and follow that pattern

---

## Current Status: AWAITING APPROVAL TO BEGIN
Louis should review this handoff document and prioritize which features to implement first.
