# Development Notes & Guidelines

## Project Maintenance Guidelines

### Documentation
- **Always keep README.md up to date** with latest features and changes
- Update `docs/ARCHITECTURE.md` when adding new APIs or changing architecture
- Keep `docs/QUICKSTART.md` current with the simplest path to get started

### Git Best Practices
- **Check diffs before commits** to ensure we haven't lost functionality unintentionally
- Use descriptive commit messages (Keep a Changelog format)
- Commit related changes together
- Keep commits focused on single features/fixes
- Work in dev branches, merge to main after confirmation
- Always update CHANGELOG.md in the same commit as code changes

### Before Each Commit
```bash
# Review what's changed
git status
git diff --stat
git diff

# Lint all code
cd backend && ./venv/bin/python -m flake8 app/
cd frontend && npx tsc --noEmit
```

### Testing Before Commits
1. Restart services: `sudo systemctl restart trading-bot-backend trading-bot-frontend`
2. Check backend logs: `sudo journalctl -u trading-bot-backend -f`
3. Check frontend loads: http://localhost:5173
4. Verify key features work:
   - Dashboard loads with stats
   - Bots page functional (create, edit, start/stop)
   - Positions display with real-time P&L
   - Charts display with indicators
   - Settings page functional

## Architecture Decisions

### Why These Technologies?

**Backend:**
- **FastAPI**: Fast, modern, with automatic OpenAPI docs
- **SQLAlchemy async**: Non-blocking database operations
- **SQLite**: Simple, no separate database server needed, file-based for easy backup
- **Coinbase Advanced Trade**: Direct API access, no middleman

**Frontend:**
- **React + TypeScript**: Type safety, component-based architecture
- **Vite**: Fast builds and HMR (Hot Module Replacement)
- **Lightweight Charts**: Professional TradingView-style charts
- **TanStack Query**: Smart data fetching with caching
- **Tailwind CSS**: Utility-first styling, fast development

### Key Design Patterns

**Strategy Pattern:**
- `TradingStrategy` ABC defines the interface
- `IndicatorBasedStrategy` is the unified strategy (handles custom conditions, AI, bull flag via conditions)
- `GridTradingStrategy` handles grid trading
- Arbitrage strategies: `TriangularArbitrage`, `SpatialArbitrage`, `StatisticalArbitrage`

**Phase-Based Conditions:**
- `base_order_conditions` - entry signals
- `safety_order_conditions` - DCA/averaging down signals
- `take_profit_conditions` - exit signals
- Each phase has its own AND/OR logic

**Trading Engine (Modular):**
- `TradingEngineV2` coordinates execution
- `SignalProcessor` evaluates signals and calculates budgets
- `BuyExecutor` / `SellExecutor` / `PerpsExecutor` handle order placement
- `PositionManager` manages position lifecycle
- `TrailingStops` handles trailing TP/SL logic

**Exchange Client Factory:**
- `ExchangeClient` ABC defines the interface
- `CoinbaseAdapter` wraps `CoinbaseClient` for CEX trading
- `PaperTradingClient` for simulated trading
- `DexClient` for DEX trading
- `create_exchange_client()` factory function

**Price Feeds:**
- `PriceFeed` ABC defines the interface
- `CoinbaseFeed` and `DexFeed` implementations
- `PriceFeedAggregator` combines multiple feeds

**Position Management:**
- Position limits prevent over-allocation
- Manual controls for emergency situations (close position, add funds)
- Complete audit trail in database
- Budget tracking per bot with max concurrent deals

## Common Pitfalls

### API Integration
- Always handle rate limits (150ms min between Coinbase requests)
- Verify API credentials before trading
- Don't expose API keys in logs or UI
- Use encrypted storage for all credentials

### Database
- Two init paths: `database.py` (runtime) and `setup.py` (fresh installs)
- Both must be updated when adding new columns
- Migrations must be idempotent (catch "duplicate column name")
- Use `os.path.dirname(__file__)` for DB_PATH (not hardcoded)
- Back up database before applying migrations

### Frontend
- Use TypeScript for type safety
- Handle loading and error states
- Show user-friendly error messages
- Don't block UI on long operations
- `BotFormData` in `botUtils.ts` must match construction sites in `Bots.tsx` and `BotFormModal.tsx`

## Debugging Tips

### Backend Issues
```bash
# View live logs (EC2 / systemd)
sudo journalctl -u trading-bot-backend -f

# View live logs (local / bot.sh)
tail -f .pids/backend.log

# Test database
sqlite3 backend/trading.db ".tables"
sqlite3 backend/trading.db "SELECT * FROM positions WHERE status='open';"

# Check API docs
# Visit http://localhost:8100/docs when backend is running
```

### Frontend Issues
```bash
# Check browser console for errors (F12 → Console tab)
# Check network requests (F12 → Network tab → Filter by XHR)

# Rebuild frontend
cd frontend
npm install
npm run dev
```

### Database Queries
```sql
-- Check active positions
SELECT * FROM positions WHERE status='open';

-- View recent trades
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;

-- Check bot configurations
SELECT id, name, strategy, status FROM bots;

-- View AI decision logs
SELECT * FROM ai_bot_logs ORDER BY timestamp DESC LIMIT 10;

-- Check pending orders
SELECT * FROM pending_orders WHERE status='pending';
```

## File Organization

### Backend
- `backend/app/main.py` - FastAPI app, startup/shutdown, background tasks
- `backend/app/trading_engine_v2.py` - Trading engine coordinator
- `backend/app/trading_engine/` - Engine modules (signal processor, executors, etc.)
- `backend/app/multi_bot_monitor.py` - Multi-bot price monitoring loop
- `backend/app/strategies/` - Trading strategy implementations
- `backend/app/conditions.py` - Condition framework (operators, indicators)
- `backend/app/indicator_calculator.py` - Technical indicator calculations
- `backend/app/routers/` - API endpoint routers (20 routers)
- `backend/app/models.py` - SQLAlchemy models (22 models)
- `backend/app/coinbase_unified_client.py` - Coinbase API client
- `backend/app/exchange_clients/` - Exchange client implementations
- `backend/app/services/` - Business logic services
- `backend/migrations/` - Database migration scripts

### Frontend
- `frontend/src/pages/` - Page components (9 routes)
- `frontend/src/components/` - Reusable UI components
- `frontend/src/contexts/` - React Context providers (auth, account, notifications)
- `frontend/src/hooks/` - Custom React hooks
- `frontend/src/services/api.ts` - Axios API layer
- `frontend/src/types/` - TypeScript type definitions

---

*Last Updated: 2026-02-15*
