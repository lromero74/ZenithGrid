# Housekeeping: File Splitting Plan

This document outlines the detailed splitting plans for files over 1000 lines.
All changes must preserve exact functionality - no features added, no features removed.

---

## 1. frontend/src/pages/Positions.tsx (2622 lines)

### Current Structure Analysis

**Lines 1-113**: Imports, constants, types, utility functions
- Fee calculation helpers (`SELL_FEE_RATE`, `getFeeAdjustedProfitMultiplier`)
- Price formatting utilities (`getQuoteCurrency`, `getBaseCurrency`, `formatPrice`, etc.)
- `IndicatorConfig` type, `LineData` type

**Lines 114-1203**: `DealChart` component (~1089 lines)
- Full-featured embedded chart with indicators
- Chart controls, timeframes, pair selector
- Position price lines (entry, TP, SL, safety orders)
- Indicators system (SMA, EMA, Bollinger)
- Gain/loss display

**Lines 1205-1251**: `AISentimentIcon` component (~46 lines)
- Small component showing AI decision icon

**Lines 1253-2622**: `Positions` component (main) (~1369 lines)
- State management (~100 lines)
- Data fetching with react-query (~100 lines)
- Price fetching effect (~60 lines)
- Position calculations and filtering (~200 lines)
- JSX rendering (~900+ lines including modals)

### Splitting Plan

Create new files in `frontend/src/components/positions/`:

1. **`positionUtils.ts`** (~60 lines)
   - `SELL_FEE_RATE` constant
   - `getFeeAdjustedProfitMultiplier()`
   - `getTakeProfitPercent()`
   - `getQuoteCurrency()`, `getBaseCurrency()`
   - `formatPrice()`, `formatBaseAmount()`, `formatQuoteAmount()`
   - `IndicatorConfig` type

2. **`DealChart.tsx`** (~1000 lines, consider further splitting)
   - The `DealChart` component in its own file
   - Could potentially be split further:
     - Chart rendering hooks
     - Indicator rendering logic

3. **`AISentimentIcon.tsx`** (~50 lines)
   - The small AI sentiment indicator component

4. **`PositionRow.tsx`** (~400 lines)
   - Extract the position row rendering from the main component
   - Includes the price bar, volume column, action buttons

5. **`PositionFilters.tsx`** (~100 lines)
   - Filter panel (bot, market, pair filters)

6. **`PositionStats.tsx`** (~100 lines)
   - Overall stats panel

7. **`PositionModals.tsx`** (~300 lines)
   - All modal components used on the page:
     - Close confirmation modal
     - Add funds modal
     - Notes modal

8. **`Positions.tsx`** (main page, ~400 lines after extraction)
   - State management
   - Data fetching
   - Layout composition using extracted components

### Import/Export Strategy
```typescript
// positions/index.ts (barrel export)
export * from './positionUtils'
export { DealChart } from './DealChart'
export { AISentimentIcon } from './AISentimentIcon'
export { PositionRow } from './PositionRow'
export { PositionFilters } from './PositionFilters'
export { PositionStats } from './PositionStats'
```

---

## 2. backend/app/routers/news_router.py (2351 lines)

### Current Structure Analysis

**Lines 1-159**: Imports, config, source definitions
- Cache configuration constants
- `NEWS_SOURCES` dict (7 sources)
- `VIDEO_SOURCES` dict (6 YouTube channels)

**Lines 162-264**: Pydantic models
- `NewsItem`, `VideoItem`
- `NewsResponse`, `VideoResponse`
- `FearGreedData`, `FearGreedResponse`
- `BlockHeightResponse`, `USDebtResponse`
- `ArticleContentResponse`
- `DebtCeilingEvent`, `DebtCeilingHistoryResponse`

**Lines 266-1153**: `DEBT_CEILING_HISTORY` constant
- ~887 lines of historical data (static data)

**Lines 1154-1330**: Cache loading/saving functions
- `load_cache()`, `prune_old_items()`, `merge_news_items()`, `save_cache()`
- Video cache functions
- Fear/Greed cache functions
- Block height cache functions
- US debt cache functions

**Lines 1333-1500**: Database helper functions
- `get_articles_from_db()`
- `store_article_in_db()`
- `cleanup_old_articles()`
- `article_to_news_item()`

**Lines 1506-1923**: Fetch functions
- `fetch_btc_block_height()`
- `fetch_us_debt()`
- `fetch_fear_greed_index()`
- `fetch_youtube_videos()`
- `fetch_all_videos()`
- `fetch_reddit_news()`
- `fetch_rss_news()`
- `fetch_all_news()`
- `get_news_from_db()`

**Lines 1949-2351**: Route handlers
- `get_news()`, `get_sources()`, `get_cache_stats()`
- `cleanup_cache()`, `get_videos()`, `get_video_sources()`
- `get_fear_greed()`, `get_btc_block_height()`
- `get_us_debt()`, `get_debt_ceiling_history()`
- `get_article_content()`

### Splitting Plan

Create new files in `backend/app/routers/news/`:

1. **`debt_ceiling_data.py`** (~900 lines)
   - Move `DEBT_CEILING_HISTORY` list to its own file
   - This is static reference data, rarely changes

2. **`news_models.py`** (~120 lines)
   - All Pydantic models for news router
   - `NewsItem`, `VideoItem`, `NewsResponse`, `VideoResponse`
   - `FearGreedData`, `FearGreedResponse`
   - `BlockHeightResponse`, `USDebtResponse`
   - `ArticleContentResponse`
   - `DebtCeilingEvent`, `DebtCeilingHistoryResponse`

3. **`news_sources.py`** (~60 lines)
   - `NEWS_SOURCES` configuration dict
   - `VIDEO_SOURCES` configuration dict

4. **`news_cache.py`** (~200 lines)
   - All cache loading/saving functions
   - Cache file path constants
   - Cache timing constants

5. **`news_fetchers.py`** (~400 lines)
   - `fetch_reddit_news()`
   - `fetch_rss_news()`
   - `fetch_youtube_videos()`
   - `fetch_all_news()`
   - `fetch_all_videos()`
   - Helper functions for merging/pruning

6. **`external_apis.py`** (~200 lines)
   - `fetch_btc_block_height()`
   - `fetch_us_debt()`
   - `fetch_fear_greed_index()`

7. **`news_db.py`** (~100 lines)
   - Database CRUD functions
   - `get_articles_from_db()`
   - `store_article_in_db()`
   - `cleanup_old_articles()`
   - `article_to_news_item()`

8. **`news_router.py`** (main router, ~300 lines)
   - Route handlers only
   - Imports from all sub-modules

### Import Structure
```python
# news/__init__.py
from .news_router import router

# news/news_router.py imports:
from .news_models import NewsItem, NewsResponse, ...
from .news_sources import NEWS_SOURCES, VIDEO_SOURCES
from .news_cache import load_cache, save_cache, ...
from .news_fetchers import fetch_all_news, fetch_all_videos, ...
from .external_apis import fetch_btc_block_height, ...
from .news_db import get_articles_from_db, ...
from .debt_ceiling_data import DEBT_CEILING_HISTORY
```

---

## 3. frontend/src/pages/Bots.tsx (2031 lines)

### Analysis Needed
Need to read this file to create detailed splitting plan.

### Likely Structure (to be confirmed)
- Bot list view
- Bot card/row components
- Bot creation/editing modal
- Bot stats display
- Scanner logs viewer

### Proposed Split Approach
Create `frontend/src/components/bots/` folder:
- `BotCard.tsx` or `BotRow.tsx`
- `BotFilters.tsx`
- `BotStats.tsx`
- `BotModals.tsx` (create/edit modals)
- `botUtils.ts` (shared logic)

---

## 4. backend/app/multi_bot_monitor.py (1478 lines)

### Analysis Needed
Need to read this file to create detailed splitting plan.

### Likely Structure (to be confirmed)
- Bot monitoring loop
- Strategy execution
- Position management
- Trade execution

### Proposed Split Approach
- `bot_monitor.py` - Main monitoring class/loop
- `strategy_executor.py` - Strategy execution logic
- `position_manager.py` - Position handling
- `monitor_utils.py` - Shared utilities

---

## 5. frontend/src/pages/Charts.tsx (1452 lines)

### Analysis Needed
Need to read this file to create detailed splitting plan.

### Likely Structure (to be confirmed)
- TradingView or lightweight-charts integration
- Chart controls
- Indicator management
- Timeframe selection

### Proposed Split Approach
Create `frontend/src/components/charts/` folder:
- `ChartContainer.tsx`
- `ChartControls.tsx`
- `IndicatorPanel.tsx`
- `chartUtils.ts`

---

## 6. frontend/src/pages/News.tsx (1347 lines)

### Analysis Needed
Need to read this file to create detailed splitting plan.

### Likely Structure (to be confirmed)
- News feed display
- Video feed display
- Source filters
- Fear/Greed indicator
- Article reader

### Proposed Split Approach
Create `frontend/src/components/news/` folder:
- `NewsFeed.tsx`
- `VideoFeed.tsx`
- `NewsFilters.tsx`
- `FearGreedWidget.tsx`
- `ArticleModal.tsx`

---

## 7. frontend/src/components/LightweightChartModal.tsx (1111 lines)

### Analysis Needed
Need to read this file to create detailed splitting plan.

### Likely Structure (to be confirmed)
- Modal wrapper
- Chart rendering
- Indicator controls
- Timeframe selection

### Proposed Split Approach
Could potentially be merged with Charts.tsx refactoring:
- `LightweightChartCore.tsx` - Core chart logic
- `ChartIndicators.tsx` - Indicator management
- `LightweightChartModal.tsx` - Modal wrapper only

---

## Execution Order

1. **news_router.py** - Backend, low risk, mostly data separation
2. **Positions.tsx** - Largest frontend file, clear component boundaries
3. **Bots.tsx** - Similar pattern to Positions
4. **multi_bot_monitor.py** - Backend core logic, needs careful analysis
5. **Charts.tsx** - Chart-related, may share code with LightweightChartModal
6. **LightweightChartModal.tsx** - Coordinate with Charts.tsx
7. **News.tsx** - After backend news refactoring

## Safety Rules Reminder

- NO new features
- NO removed features
- NO changed behavior
- Every extracted component must work identically
- Test after each file split
- Small, focused commits
- Build must pass after each commit
