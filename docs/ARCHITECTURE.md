# ZenithGrid Architecture

> Machine-readable catalog: [`architecture.json`](architecture.json)

## Stack & Deployment

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy (async) + SQLite |
| Frontend | React 18 + TypeScript + Vite + TailwindCSS |
| State | React Context (app) + React Query (server) |
| Charts | TradingView Lightweight Charts |
| Auth | JWT (python-jose) + bcrypt |
| Encryption | Fernet (AES-128-CBC + HMAC-SHA256) |
| Deployment | AWS EC2 (Amazon Linux 2023) + systemd |
| Exchange | Coinbase (HMAC/CDP), ByBit V5, MT5 Bridge |
| AI | Anthropic Claude, OpenAI GPT, Google Gemini |

The backend runs as a systemd service (`trading-bot-backend`) on port 8000.
The frontend runs as a Vite dev server (`trading-bot-frontend`) on port 5173.
Both auto-start on boot.

---

## 1. System Overview

```mermaid
graph TB
    subgraph Browser
        FE[React Frontend<br/>:5173]
    end

    subgraph "EC2 Instance"
        BE[FastAPI Backend<br/>:8000]
        DB[(SQLite<br/>trading.db)]
        BG[Background Tasks<br/>13 scheduled jobs]
    end

    subgraph "External Services"
        CB[Coinbase API<br/>REST + WebSocket]
        BB[ByBit V5 API<br/>REST + WebSocket]
        MT5[MT5 Bridge<br/>HTTP JSON]
        AI[AI Providers<br/>Claude / GPT / Gemini]
        DEX[DEX Networks<br/>Ethereum / L2s]
        NEWS[News Feeds<br/>RSS / Reddit / YouTube]
        MKT[Market Data<br/>Fear&Greed / Dominance]
    end

    FE <-->|REST + WebSocket| BE
    BE <--> DB
    BG --> DB
    BE <--> CB
    BE <--> BB
    BE <--> MT5
    BE <--> AI
    BE <--> DEX
    BG --> NEWS
    BG --> MKT
    BG --> CB
    BG --> BB
```

---

## 2. Backend Layers

```mermaid
graph TB
    subgraph "API Layer (20 routers)"
        R_AUTH[auth]
        R_BOTS[bots<br/><small>crud / control / ai_logs<br/>indicator_logs / scanner_logs / validation</small>]
        R_POS[positions<br/><small>queries / actions / limit_orders<br/>manual_ops / perps</small>]
        R_ACCT[accounts]
        R_MKT[market_data]
        R_NEWS[news<br/><small>sources / cache / models<br/>debt_ceiling</small>]
        R_TRADE[trading]
        R_OTHER[settings / templates<br/>order_history / blacklist<br/>seasonality / sources<br/>ai_credentials / ...]
    end

    subgraph "Service Layer"
        SVC_GRID[GridTradingService]
        SVC_BUDGET[BudgetCalculator]
        SVC_EXCH[ExchangeService]
        SVC_AI_OPT[AIGridOptimizer]
        SVC_SNAP[AccountSnapshotService]
        SVC_COIN[CoinReviewService]
    end

    subgraph "Trading Engine"
        MBM[MultiBotMonitor]
        TEV2[TradingEngineV2]
        subgraph "Engine Modules"
            SIG[SignalProcessor]
            BUY[BuyExecutor]
            SELL[SellExecutor]
            PERPS_EX[PerpsExecutor]
            PM[PositionManager]
            OL[OrderLogger]
            TS[TrailingStops]
        end
        TC[TradingClient]
        OV[OrderValidation]
        PREC[Precision]
    end

    subgraph "Strategy Layer"
        S_GRID[GridTradingStrategy]
        S_IND[IndicatorBasedStrategy]
        S_STAT[StatisticalArbitrage]
        S_SPAT[SpatialArbitrage]
        S_TRI[TriangularArbitrage]
    end

    subgraph "Exchange Clients"
        BASE[ExchangeClient ABC]
        CADAP[CoinbaseAdapter]
        BBADAP[ByBitAdapter]
        MT5C[MT5BridgeClient]
        PGUARD[PropGuardClient<br/><small>safety decorator</small>]
        PAPER[PaperTradingClient]
        DEXC[DexClient]
        FACTORY[Factory]
    end

    subgraph "Coinbase API Modules"
        CB_AUTH[auth.py]
        CB_BAL[account_balance_api.py]
        CB_MKT[market_data_api.py]
        CB_ORD[order_api.py]
        CB_PERP[perpetuals_api.py]
    end

    subgraph "ByBit Modules"
        BB_CLIENT[ByBitClient<br/><small>pybit + asyncio.to_thread</small>]
        BB_WS[ByBitWSManager<br/><small>equity / position / ticker</small>]
    end

    subgraph "Core"
        AI_SVC[AIService]
        COND[Conditions]
        INDCALC[IndicatorCalculator]
        IND_MOD[Indicators<br/><small>ai_spot_opinion / bull_flag<br/>risk_presets</small>]
        CACHE[Cache]
        ENC[Encryption]
        CFG[Config]
        DB[(SQLite)]
    end

    subgraph "Price Feeds"
        PF_AGG[Aggregator]
        PF_CB[CoinbaseFeed]
        PF_DEX[DexFeed]
    end

    R_BOTS --> SVC_GRID
    R_BOTS --> MBM
    R_POS --> TEV2
    R_TRADE --> TC
    R_ACCT --> SVC_EXCH

    MBM --> S_GRID & S_IND & S_STAT & S_SPAT & S_TRI
    S_GRID --> COND & INDCALC
    S_IND --> COND & INDCALC
    INDCALC --> IND_MOD
    TEV2 --> SIG --> BUY & SELL & PERPS_EX
    TEV2 --> PM & OL & TS
    BUY & SELL --> TC
    TC --> OV --> PREC
    TC --> FACTORY

    SVC_EXCH --> FACTORY
    FACTORY --> CADAP & BBADAP & MT5C & PAPER & DEXC
    PGUARD -.->|wraps| BBADAP & MT5C
    CADAP --> CB_AUTH & CB_BAL & CB_MKT & CB_ORD & CB_PERP
    BBADAP --> BB_CLIENT
    BB_WS -.->|real-time state| PGUARD
    BASE -.->|interface| CADAP & BBADAP & MT5C & PAPER & DEXC & PGUARD

    MBM --> PF_AGG
    PF_AGG --> PF_CB & PF_DEX

    S_GRID -.-> AI_SVC
    SVC_AI_OPT --> AI_SVC
    SVC_COIN --> AI_SVC
    AI_SVC --> ENC

    SVC_GRID --> DB
    SVC_SNAP --> DB
    TEV2 --> DB
```

---

## 3. Frontend Layers

```mermaid
graph TB
    subgraph "Pages (9 routes)"
        P_DASH[Dashboard /]
        P_BOTS[Bots /bots]
        P_POS[Positions /positions]
        P_HIST[History /history]
        P_PORT[Portfolio /portfolio]
        P_NEWS[News /news]
        P_CHART[Charts /charts]
        P_SET[Settings /settings]
        P_LOGIN[Login]
    end

    subgraph "Contexts (global state)"
        CTX_AUTH[AuthContext]
        CTX_ACCT[AccountContext]
        CTX_NOTIF[NotificationContext]
        CTX_VIDEO[VideoPlayerContext]
        CTX_READER[ArticleReaderContext]
    end

    subgraph "Page Hooks"
        H_BOTS[useBotsData<br/>useBotMutations<br/>useValidation]
        H_POS[usePositionsData<br/>usePositionMutations<br/>usePositionFilters]
        H_CHART[useChartsData<br/>useChartManagement<br/>useIndicators]
        H_NEWS[useNewsData<br/>useNewsFilters<br/>useTTS / useTTSSync]
    end

    subgraph "API Layer (services/api.ts)"
        API[Axios Instance<br/>+ Auth Interceptor]
        API_MODS[botsApi / positionsApi<br/>accountApi / marketDataApi<br/>settingsApi / orderHistoryApi<br/>+ 11 more modules]
    end

    subgraph "Backend"
        BE[FastAPI :8000]
        WS[WebSocket /ws/notifications]
    end

    P_BOTS --> H_BOTS
    P_POS --> H_POS
    P_CHART --> H_CHART
    P_NEWS --> H_NEWS

    H_BOTS & H_POS & H_CHART & H_NEWS --> API_MODS
    API_MODS --> API --> BE

    CTX_AUTH -.->|provides auth state| P_DASH & P_BOTS & P_POS & P_HIST & P_PORT & P_NEWS & P_CHART & P_SET
    CTX_ACCT -.->|provides account| P_DASH & P_BOTS & P_POS & P_PORT
    CTX_NOTIF -.->|order fills| P_POS & P_DASH
    CTX_NOTIF --> WS
```

---

## 4. Trading Flow

```mermaid
sequenceDiagram
    participant MBM as MultiBotMonitor
    participant PF as PriceFeed Aggregator
    participant STRAT as Strategy
    participant AI as AIService
    participant TEV2 as TradingEngineV2
    participant SIG as SignalProcessor
    participant BUY as BuyExecutor
    participant TC as TradingClient
    participant OV as OrderValidation
    participant EX as ExchangeClient
    participant PG as PropGuard<br/>(prop firms)
    participant API as Exchange API<br/>(Coinbase / ByBit / MT5)
    participant PM as PositionManager
    participant DB as SQLite
    participant WS as WebSocketManager

    loop Every check interval
        MBM->>PF: get_prices(pairs)
        PF-->>MBM: prices
        MBM->>STRAT: check_signals(bot, prices)
        alt AI Strategy
            STRAT->>AI: get_recommendation(pairs, context)
            AI-->>STRAT: decision + confidence + allocation%
        else Indicator Strategy
            STRAT->>STRAT: evaluate_conditions(candles)
        end
        STRAT-->>MBM: signals[]
    end

    MBM->>TEV2: process_signal(signal, bot)
    TEV2->>SIG: evaluate(signal, bot, account)
    SIG->>SIG: calculate_budget(bot, account)
    SIG->>OV: validate_order(size, product)
    alt Valid Order
        SIG->>BUY: execute(product, size, price)
        BUY->>TC: buy(product, size, price)
        TC->>EX: place_order(params)
        alt Prop Firm Account
            EX->>PG: preflight_check(drawdown, spread, vol)
            PG-->>EX: pass/block
        end
        EX->>API: place_order (REST)
        API-->>EX: order_id
        EX-->>TC: result
        TC-->>BUY: fill
        BUY->>PM: create_position(fill)
        PM->>DB: INSERT Position + Trade
        BUY->>WS: broadcast(order_fill)
    else Below Minimum
        SIG->>DB: log rejection reason
    end
```

---

## 5. Data Model

```mermaid
erDiagram
    User ||--o{ Account : "has many"
    User ||--o{ AIProviderCredential : "has many"
    User ||--o{ BotTemplate : "has many"
    User ||--o{ UserSourceSubscription : "subscribes to"
    User ||--o{ Settings : "has many"

    Account ||--o{ Bot : "has many"
    Account ||--o{ OrderHistory : "has many"
    Account ||--o{ AccountValueSnapshot : "daily snapshots"
    Account ||--o| PropFirmState : "has one (prop)"
    Account ||--o{ PropFirmEquitySnapshot : "equity history"

    Bot ||--o{ Position : "opens"
    Bot ||--o{ AIBotLog : "logs decisions"
    Bot ||--o{ ScannerLog : "logs scans"
    Bot ||--o{ IndicatorLog : "logs indicators"

    Position ||--o{ Trade : "has trades"
    Position ||--o{ PendingOrder : "has pending"
    Position ||--o{ Signal : "triggered by"

    ContentSource ||--o{ UserSourceSubscription : "subscribed by"
    ContentSource ||--o{ NewsArticle : "produces"
    ContentSource ||--o{ VideoArticle : "produces"

    User {
        int id PK
        string email
        string hashed_password
        bool is_active
        bool terms_accepted
    }

    Account {
        int id PK
        int user_id FK
        string name
        string exchange
        string account_type
        string api_key_encrypted
        bool is_default
        string prop_firm
        json prop_firm_config
        float prop_daily_drawdown_pct
        float prop_total_drawdown_pct
        float prop_initial_deposit
    }

    PropFirmState {
        int id PK
        int account_id FK
        float initial_deposit
        float current_equity
        float daily_start_equity
        bool is_killed
        string kill_reason
    }

    PropFirmEquitySnapshot {
        int id PK
        int account_id FK
        float equity
        float daily_drawdown_pct
        float total_drawdown_pct
        datetime timestamp
    }

    Bot {
        int id PK
        int account_id FK
        string name
        string strategy
        string status
        json trading_pairs
        float budget_percentage
        int max_concurrent_deals
    }

    Position {
        int id PK
        int bot_id FK
        string product_id
        string status
        string side
        float total_base_acquired
        float total_quote_spent
        float average_buy_price
    }

    Trade {
        int id PK
        int position_id FK
        string trade_type
        float price
        float amount
        float quote_amount
    }

    PendingOrder {
        int id PK
        int position_id FK
        string order_id
        string order_type
        string side
        float price
        float size
        string status
    }
```

---

## Authentication Flow

1. User submits email/password to `POST /api/auth/login`
2. Backend verifies bcrypt hash, issues JWT access + refresh tokens
3. Frontend stores tokens in `localStorage` via `AuthContext`
4. Every API request includes `Authorization: Bearer {token}` via Axios interceptor
5. Backend `get_current_user` dependency validates JWT on protected routes
6. On 401 response, frontend clears session and redirects to login
7. On first login, `RiskDisclaimer` modal requires terms acceptance

## Multi-Tenancy Model

- Single-user deployment (owner-operator) but architected for multi-user
- `User` -> `Account` -> `Bot` -> `Position` hierarchy enforces data isolation
- Each user has their own encrypted exchange credentials, AI provider keys, and settings
- All API routes require JWT authentication and scope queries to the authenticated user

## Background Task Scheduling

All background tasks are launched in `main.py` during the FastAPI `startup` event:

| Task | Interval | Method |
|------|----------|--------|
| MultiBotMonitor | Per-strategy | `asyncio` event loop |
| LimitOrderMonitor | 10s | `asyncio.create_task` loop |
| OrderReconciliationMonitor | 60s | `asyncio.create_task` loop |
| MissingOrderDetector | 5min | `asyncio.create_task` loop |
| TradingPairMonitor | Daily | Service `.start()` method |
| ContentRefreshService | 30min/60min | Service `.start()` method |
| DebtCeilingMonitor | Weekly | Service `.start()` method |
| AutoBuyMonitor | Per-account | Service `.start()` method |
| PerpsMonitor | 60s | Service `.start()` method |
| PropGuardMonitor | 30s | `asyncio.create_task` loop |
| DecisionLogCleanup | Daily | `asyncio.create_task` loop |
| FailedConditionCleanup | 6h | `asyncio.create_task` loop |
| FailedOrderCleanup | 6h | `asyncio.create_task` loop |
| AccountSnapshotCapture | Daily | `asyncio.create_task` loop |

All tasks are cancelled gracefully during `shutdown` event. The `ShutdownManager` ensures no orders are mid-execution before allowing shutdown.
