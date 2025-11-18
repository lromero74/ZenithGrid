# Development Notes & Guidelines

## Project Maintenance Guidelines

### Documentation
- **Always keep README.md up to date** with latest features and changes
- Update DOCUMENTATION.md when adding new APIs or changing architecture
- Keep QUICKSTART.md current with the simplest path to get started

### Git Best Practices
- **Check diffs before commits** to ensure we haven't lost functionality unintentionally
- Use descriptive commit messages
- Commit related changes together
- Keep commits focused on single features/fixes

### Before Each Commit
```bash
# Review what's changed
git status
git diff --stat
git diff

# Verify no functionality was accidentally removed
# Check that all features still work
```

### Testing Before Commits
1. Test bot starts: `./bot.sh start`
2. Check backend logs: `tail -f .pids/backend.log`
3. Check frontend loads: http://localhost:5173
4. Verify key features work:
   - Dashboard loads
   - Settings page functional
   - Charts display
   - API connections work

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

**Persistence:**
- All state stored in SQLite (positions, trades, signals, market data)
- No in-memory state that would be lost on restart
- Database is source of truth

**Trading Strategy:**
- MACD calculated on configurable timeframes
- Cross-up/cross-down detection works above AND below zero
- DCA on subsequent cross-ups
- Profit protection - won't sell at loss

**Position Management:**
- Position limits prevent over-allocation
- Manual controls for emergency situations
- Complete audit trail in database

## Common Pitfalls

### API Integration
- ✅ Always test Coinbase API changes in sandbox first
- ✅ Handle rate limits gracefully
- ✅ Verify API credentials before trading
- ⚠️ Don't expose API keys in logs or UI

### MACD Calculation
- ✅ Need minimum 26 candles for MACD slow period
- ✅ More candles = more accurate signals
- ⚠️ Don't calculate MACD on incomplete data

### Position Recovery
- ✅ Always check database for active positions on startup
- ✅ Verify balances match database records
- ⚠️ Handle case where ETH was manually sold outside bot

### Frontend
- ✅ Use TypeScript for type safety
- ✅ Handle loading and error states
- ✅ Show user-friendly error messages
- ⚠️ Don't block UI on long operations

## Future Improvements

### Potential Features
- [ ] Multiple trading pairs (not just ETH/BTC)
- [ ] Additional indicators (RSI, Bollinger Bands, etc.)
- [ ] Stop-loss functionality
- [ ] Take-profit levels
- [ ] Email/SMS notifications
- [ ] Backtesting framework
- [ ] Paper trading mode
- [ ] Advanced position sizing strategies
- [ ] Multi-strategy support
- [ ] Machine learning signal enhancement

### Technical Debt
- [ ] Add comprehensive unit tests
- [ ] Add integration tests for trading logic
- [ ] Implement proper logging framework
- [ ] Add error tracking (Sentry, etc.)
- [ ] Improve error handling in edge cases
- [ ] Add database migrations system
- [ ] Optimize MACD calculation performance
- [ ] Add WebSocket support for live price updates
- [ ] Implement proper secret management
- [ ] Add rate limiting on API endpoints

### Security Enhancements
- [ ] Encrypt .env file at rest
- [ ] Use secret management service (AWS Secrets Manager, Vault)
- [ ] Add 2FA for sensitive operations
- [ ] Implement audit logging
- [ ] Add IP whitelist for Coinbase API
- [ ] Use HTTPS in production
- [ ] Add security headers in nginx
- [ ] Implement CSRF protection

### Performance
- [ ] Cache frequently accessed data
- [ ] Optimize database queries
- [ ] Add database indexes
- [ ] Lazy load chart data
- [ ] Implement pagination for position history
- [ ] Add database connection pooling

## Debugging Tips

### Backend Issues
```bash
# View live logs
tail -f .pids/backend.log

# Check specific error
grep "ERROR" .pids/backend.log

# Test database
sqlite3 backend/trading.db ".tables"
sqlite3 backend/trading.db "SELECT * FROM positions;"

# Test Coinbase connection
cd backend && source venv/bin/activate && python test_connection.py
```

### Frontend Issues
```bash
# Check browser console for errors
# Open DevTools (F12) and look at Console tab

# Rebuild frontend
cd frontend
npm install
npm run dev

# Check API requests
# DevTools -> Network tab -> Filter by XHR
```

### Database Queries
```sql
-- Check active positions
SELECT * FROM positions WHERE status='open';

-- View recent trades
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;

-- Check MACD signals
SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10;

-- View recent market data
SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 10;
```

## Notes for Future Developers

### Trading Logic Flow
1. Price monitor fetches candle data every N seconds
2. MACD calculator processes candles
3. Crossover detection checks for signals
4. Trading engine executes buy/sell logic
5. Database stores all state
6. Frontend displays via REST API

### Important Constants
- **Default MACD**: 12, 26, 9 (standard)
- **Default Initial**: 5% of BTC balance
- **Default DCA**: 3% of BTC balance
- **Default Max**: 25% of BTC balance
- **Default Min Profit**: 1%

### File Organization
- `backend/app/main.py`: REST API endpoints
- `backend/app/trading_engine.py`: Core trading logic
- `backend/app/indicators.py`: MACD calculation
- `backend/app/price_monitor.py`: Price monitoring loop
- `frontend/src/components/TradingChart.tsx`: Chart component
- `frontend/src/pages/Dashboard.tsx`: Main dashboard

---

*Last Updated: 2025-01-08*
