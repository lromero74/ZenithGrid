# Repository Refactoring Plan
**Created**: 2025-11-23
**Branch**: HouseKeeping_1.0

---

## 📊 FILES REQUIRING REFACTORING

### Critical Priority (>1000 lines)
| File | Lines | Risk Level | Priority |
|------|-------|------------|----------|
| `backend/app/strategies/ai_autonomous.py` | 1745 | 🔴 HIGH | 1 |
| `backend/app/main.py` | 1658 | 🔴 CRITICAL | 2 |
| `backend/app/trading_engine_v2.py` | 1099 | 🔴 HIGH | 3 |
| `frontend/src/pages/Positions.tsx` | 2534 | 🔴 HIGH | 4 |
| `frontend/src/pages/Charts.tsx` | 1452 | 🟡 MEDIUM | 5 |
| `frontend/src/pages/Bots.tsx` | 1413 | 🟡 MEDIUM | 6 |
| `frontend/src/components/LightweightChartModal.tsx` | 1098 | 🟡 MEDIUM | 7 |

### High Priority (500-1000 lines)
| File | Lines | Risk Level | Priority |
|------|-------|------------|----------|
| `backend/app/routers/bots.py` | 896 | 🟡 MEDIUM | 8 |
| `backend/app/multi_bot_monitor.py` | 892 | 🟡 MEDIUM | 9 |
| `backend/app/coinbase_unified_client.py` | 874 | 🟡 MEDIUM | 10 |
| `backend/app/strategies/conditional_dca.py` | 636 | 🟢 LOW | 11 |
| `frontend/src/pages/Portfolio.tsx` | 753 | 🟢 LOW | 12 |
| `frontend/src/components/PhaseConditionSelector.tsx` | 611 | 🟢 LOW | 13 |

---

## 🎯 REFACTORING STRATEGY

### Phase 1: Backend Critical Files (Steps 1-3)
Focus on largest, most complex backend files first.

### Phase 2: Frontend Critical Files (Steps 4-7)
Split massive React components into smaller, focused components.

### Phase 3: Backend Medium Files (Steps 8-11)
Clean up remaining backend files over 500 lines.

### Phase 4: Frontend Medium Files (Steps 12-13)
Complete frontend refactoring.

---

## 📋 DETAILED STEP-BY-STEP PLAN

---

### **STEP 1: Split `backend/app/strategies/ai_autonomous.py` (1745 lines)**

**Risk Level**: 🔴 HIGH (Core AI trading logic)

**Analysis Required**:
- Read entire file to understand structure
- Identify logical boundaries (prompts, reasoning, execution, logging)
- Map all class methods and their dependencies
- Identify any circular dependencies

**Proposed Split**:
```
backend/app/strategies/ai_autonomous/
├── __init__.py                    # Main AIAutonomousStrategy class
├── prompts.py                     # All AI prompt templates
├── reasoning.py                   # AI reasoning and decision logic
├── execution.py                   # Trade execution logic
├── analysis.py                    # Market analysis helpers
└── logging.py                     # AI logging and debugging
```

**Safety Checks**:
- Verify all imports resolve correctly
- Ensure no circular dependencies
- Confirm strategy still loads in bot list
- Test AI reasoning generation (read-only check)

**Estimated Commits**: 6-8 (one per new file + updates)

---

### **STEP 2: Split `backend/app/main.py` (1658 lines)**

**Risk Level**: 🔴 CRITICAL (FastAPI application entry point)

**Analysis Required**:
- Identify all route groups
- Map middleware and startup events
- Check CORS and security configurations
- Verify dependency injection patterns

**Proposed Split**:
```
backend/app/
├── main.py                        # FastAPI app + startup (100-150 lines)
├── routers/
│   ├── positions.py               # Position management endpoints
│   ├── portfolio.py               # Portfolio/account endpoints
│   ├── trades.py                  # Trade history endpoints
│   └── ai_logs.py                 # AI logging endpoints
├── middleware/
│   └── cors.py                    # CORS configuration
└── dependencies.py                # Shared dependencies
```

**Safety Checks**:
- Verify all routes still register
- Test all API endpoints with curl
- Confirm WebSocket endpoints work
- Verify CORS headers present

**Estimated Commits**: 8-10

---

### **STEP 3: Split `backend/app/trading_engine_v2.py` (1099 lines)**

**Risk Level**: 🔴 HIGH (Core trading execution engine)

**Analysis Required**:
- Map buy/sell execution flows
- Identify DCA logic boundaries
- Check position update logic
- Verify trade recording

**Proposed Split**:
```
backend/app/trading_engine/
├── __init__.py                    # Main TradingEngine class
├── buy_execution.py               # Buy order logic
├── sell_execution.py              # Sell order logic (market + limit)
├── dca_logic.py                   # DCA/safety order logic
├── position_updates.py            # Position state management
└── trade_recording.py             # Trade database recording
```

**Safety Checks**:
- Verify bot can open positions
- Verify bot can close positions
- Test DCA triggers
- Confirm trade records created

**Estimated Commits**: 6-7

---

### **STEP 4: Split `frontend/src/pages/Positions.tsx` (2534 lines)**

**Risk Level**: 🔴 HIGH (Core position management UI)

**Analysis Required**:
- Identify all modals and their state
- Map action handlers (close, edit, notes, etc.)
- Check filter and sort logic
- Verify data fetching patterns

**Proposed Split**:
```
frontend/src/pages/Positions/
├── index.tsx                      # Main component + layout (200-300 lines)
├── components/
│   ├── PositionCard.tsx           # Individual position display
│   ├── PositionFilters.tsx        # Filter controls
│   ├── PositionActions.tsx        # Action buttons
│   ├── CloseConfirmModal.tsx      # Market close confirmation
│   └── NotesModal.tsx             # Notes editor
├── hooks/
│   ├── usePositions.tsx           # Data fetching
│   ├── usePositionActions.tsx     # Action handlers
│   └── usePositionFilters.tsx     # Filter/sort logic
└── types.ts                       # Local type definitions
```

**Safety Checks**:
- Verify positions load and display
- Test all action buttons
- Confirm modals open/close
- Test filters and sorting

**Estimated Commits**: 10-12

---

### **STEP 5: Split `frontend/src/pages/Charts.tsx` (1452 lines)**

**Risk Level**: 🟡 MEDIUM (Charting UI)

**Proposed Split**:
```
frontend/src/pages/Charts/
├── index.tsx                      # Main component
├── components/
│   ├── ChartControls.tsx          # Timeframe/interval controls
│   ├── IndicatorPanel.tsx         # Indicator configuration
│   └── ChartCanvas.tsx            # Chart rendering
├── hooks/
│   ├── useChartData.tsx           # Data fetching
│   └── useIndicators.tsx          # Indicator calculations
└── utils/
    └── chartHelpers.ts            # Chart formatting utilities
```

**Estimated Commits**: 6-8

---

### **STEP 6: Split `frontend/src/pages/Bots.tsx` (1413 lines)**

**Risk Level**: 🟡 MEDIUM (Bot management UI)

**Proposed Split**:
```
frontend/src/pages/Bots/
├── index.tsx                      # Main component + layout
├── components/
│   ├── BotCard.tsx                # Individual bot display
│   ├── BotFormModal.tsx           # Create/edit bot form
│   ├── BotActions.tsx             # Start/stop/delete actions
│   └── PnLChart.tsx               # Bot P&L chart (move from components/)
└── hooks/
    ├── useBots.tsx                # Data fetching
    └── useBotActions.tsx          # Action handlers
```

**Estimated Commits**: 7-9

---

### **STEP 7: Split `frontend/src/components/LightweightChartModal.tsx` (1098 lines)**

**Risk Level**: 🟡 MEDIUM (Chart modal component)

**Proposed Split**:
```
frontend/src/components/LightweightChart/
├── LightweightChartModal.tsx      # Modal wrapper (100-150 lines)
├── ChartRenderer.tsx              # Chart initialization/rendering
├── IndicatorManager.tsx           # Indicator overlays
├── TimeframeControls.tsx          # Timeframe selector
└── hooks/
    ├── useChartSetup.tsx          # Chart setup logic
    └── useIndicatorData.tsx       # Indicator data processing
```

**Estimated Commits**: 5-6

---

### **STEP 8: Split `backend/app/routers/bots.py` (896 lines)**

**Risk Level**: 🟡 MEDIUM (Bot API endpoints)

**Proposed Split**:
```
backend/app/routers/bots/
├── __init__.py                    # Router registration
├── crud.py                        # Create/Read/Update/Delete operations
├── validation.py                  # Bot configuration validation
├── statistics.py                  # Bot statistics calculations
└── schemas.py                     # Pydantic response models
```

**Estimated Commits**: 5-6

---

### **STEP 9: Split `backend/app/multi_bot_monitor.py` (892 lines)**

**Risk Level**: 🟡 MEDIUM (Background monitoring service)

**Proposed Split**:
```
backend/app/services/bot_monitoring/
├── __init__.py                    # Main MultiBotMonitor class
├── signal_checking.py             # Signal evaluation logic
├── action_execution.py            # Buy/sell action execution
└── logging.py                     # Monitor logging
```

**Estimated Commits**: 4-5

---

### **STEP 10: Split `backend/app/coinbase_unified_client.py` (874 lines)**

**Risk Level**: 🟡 MEDIUM (Exchange API client)

**Proposed Split**:
```
backend/app/coinbase/
├── __init__.py                    # Main CoinbaseClient class
├── trading.py                     # Buy/sell order methods
├── portfolio.py                   # Balance/portfolio methods
├── market_data.py                 # Price/ticker methods
└── orders.py                      # Order management (limit orders)
```

**Estimated Commits**: 5-6

---

### **STEP 11: Split `backend/app/strategies/conditional_dca.py` (636 lines)**

**Risk Level**: 🟢 LOW (DCA strategy)

**Proposed Split**:
```
backend/app/strategies/conditional_dca/
├── __init__.py                    # Main strategy class
├── parameters.py                  # Strategy parameter definitions
├── signal_logic.py                # Buy/sell signal logic
└── dca_logic.py                   # DCA/safety order logic
```

**Estimated Commits**: 4-5

---

### **STEP 12: Split `frontend/src/pages/Portfolio.tsx` (753 lines)**

**Risk Level**: 🟢 LOW (Portfolio UI)

**Proposed Split**:
```
frontend/src/pages/Portfolio/
├── index.tsx                      # Main component
├── components/
│   ├── PortfolioSummary.tsx       # Total value cards
│   ├── BalanceBreakdown.tsx       # BTC/USD breakdown
│   ├── HoldingsTable.tsx          # Holdings table
│   └── PnLCards.tsx               # P&L display cards
└── hooks/
    └── usePortfolio.tsx           # Data fetching
```

**Estimated Commits**: 5-6

---

### **STEP 13: Split `frontend/src/components/PhaseConditionSelector.tsx` (611 lines)**

**Risk Level**: 🟢 LOW (Condition builder component)

**Proposed Split**:
```
frontend/src/components/PhaseConditionSelector/
├── index.tsx                      # Main component
├── ConditionRow.tsx               # Individual condition editor
├── PhaseGroup.tsx                 # Phase grouping
└── hooks/
    └── useConditions.tsx          # Condition state management
```

**Estimated Commits**: 4-5

---

## 📊 SUMMARY

- **Total Files to Refactor**: 13
- **Total Steps**: 13
- **Estimated Commits**: 75-95
- **Critical Risk Files**: 3 (Steps 1-3)
- **Medium Risk Files**: 7 (Steps 4-10)
- **Low Risk Files**: 3 (Steps 11-13)

---

## ⚠️ RISK MITIGATION

### For Each Step:
1. Read and analyze entire file before making changes
2. Create detailed splitting plan for that specific file
3. Make one small commit per new file created
4. Verify imports resolve after each commit
5. Run Python syntax check: `python -m py_compile <file>`
6. Run TypeScript check: `npx tsc --noEmit`
7. Provide testing checklist for manual verification

### If Any Step Becomes Complex:
1. STOP immediately
2. Document the complexity
3. Ask for guidance
4. Wait for approval before proceeding

---

## 🎯 SUCCESS CRITERIA

- ✅ All files ≤ 500 lines
- ✅ All imports properly ordered
- ✅ No functionality removed or changed
- ✅ All syntax valid
- ✅ No runtime errors introduced
- ✅ Clear commit history
- ✅ Testing checklist completed for each step

---

## 📝 NEXT ACTION

**Awaiting approval to begin STEP 1: Split `backend/app/strategies/ai_autonomous.py`**

Please confirm:
1. Approve the overall refactoring plan
2. Approve starting with Step 1
3. Any changes or concerns about the approach
