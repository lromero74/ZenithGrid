# Changelog

All notable changes to BTC-Bot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.45.1] - 2026-02-24

### Fixed
- **Staking rewards row visual separation**: Added thicker border under staking rewards summary row to visually separate it from individual transfers below

## [v2.45.0] - 2026-02-24

### Changed
- **Staking rewards aggregated in reports**: Staking reward deposits are now shown as a single summary row (e.g. "Staking Rewards — 12 deposits, +$0.85") in HTML, PDF, and AI reports instead of cluttering the table with individual penny-sized entries

## [v2.44.2] - 2026-02-24

### Added
- **BTC accumulation context for AI**: AI reports now understand the crypto-maximalist thesis behind BTC-pair trading — that alt/BTC trades are a BTC accumulation strategy, not traditional trading with "capital lockup" risk

### Fixed
- **AI strategy context accuracy**: Restructured strategy notes to clearly separate DCA mechanics from investment philosophy, preventing generic risk warnings that miss the point of the strategy

## [v2.44.1] - 2026-02-24

### Fixed
- **AI strategy context accuracy**: AI now receives safety order step scale and volume scale parameters, and understands that safety orders require both a minimum price drop (increasing with each order) AND momentum signals — preventing incorrect claims about premature DCA entries

## [v2.44.0] - 2026-02-24

### Added
- **Bot strategy context in AI reports**: AI summaries now receive actual bot configurations — indicator entry/exit conditions (BB%, RSI, Volume RSI), take profit targets, safety order settings, and DCA mechanics — for bots that had trades in the period, so the AI can accurately interpret win rates and trading patterns

## [v2.43.1] - 2026-02-24

### Fixed
- **PDF generation crash**: Fixed "Not enough horizontal space" error when AI summary had bullet points followed by paragraph text
- **PDF error logging**: PDF errors now include full stack traces

## [v2.43.0] - 2026-02-24

### Changed
- **Two-tier AI report summaries**: Report AI analysis simplified from three tiers (Beginner/Comfortable/Experienced) to two — "Summary" (plain language, encouraging) and "Detailed Analysis" (expert depth, opinionated, may include extra sections like Risk Assessment or Strategy Notes)
- **Expense Coverage section placement**: Expense-type goals now appear immediately after Capital Movements in reports, before other goal types, for better visual flow

### Removed
- **Per-recipient experience level**: Recipients no longer have an experience level setting — all recipients receive the same report with both Summary and Detailed tiers available

## [v2.42.0] - 2026-02-24

### Added
- **Card spend itemization on reports**: Coinbase Card transactions now show as "Card Spend (BTC)" or "Card Spend (USD)" instead of generic "Withdrawal" in HTML, PDF, and AI report summaries
- **Transfer type labels**: All transfers now display descriptive labels — "Bank Deposit", "Bank Withdrawal", "Crypto Transfer", "Exchange Transfer" — across reports and AI narratives
- **Card spend on USD chart line**: Coinbase Card spend markers now appear on the USD line of the Dashboard Account Value chart (previously appeared on BTC line since the currency is BTC)

## [v2.41.1] - 2026-02-24

### Added
- **Marker visibility toggles**: Chart legend items are now clickable — show/hide trade wins, losses, deposits, and withdrawals independently

### Fixed
- **Staking rewards shown as deposits**: Coinbase staking/earn rewards (sub-$1 micro-transfers) no longer appear as deposit markers on the chart
- **AI omitting withdrawals in report narrative**: Strengthened AI prompt to require mentioning both deposits and withdrawals when both occurred, so the math always adds up

## [v2.41.0] - 2026-02-24

### Added
- **Chart activity markers**: Account Value chart now shows categorized markers — trade wins (green), trade losses (red), deposits (blue), withdrawals (amber) — placed on the correct BTC or USD line based on the trading pair or currency
- **Chart activity endpoint**: New `GET /api/account-value/activity` endpoint aggregates closed trades and transfers by day for chart markers
- **Trading summary in reports**: Capital Movements section in HTML, PDF, and AI reports now shows a trading activity summary row ("X trades (YW/ZL), net P&L: +$Z.ZZ") above individual deposit/withdrawal rows
- **Individual transfer table in reports**: HTML, PDF, and AI summaries now show a "Capital Movements" table listing the most recent deposits and withdrawals with dates, types, and amounts

### Changed
- **Adaptive coverage precision**: Expense coverage percentages now use adaptive decimal places — small values like 0.31% no longer misleadingly round to 0%. Applies to HTML badges, PDF badges, goal headers, and AI prompts
- **Deposit metrics always visible**: HTML report Key Metrics section now always shows the Net Deposits and Adjusted Growth row, even when deposits are zero (previously hidden when net deposits were exactly 0)

## [v2.40.16] - 2026-02-23

### Fixed
- **Transfer sync never ran**: CoinbaseAdapter was missing the `get_deposit_withdrawals` method, so the daily transfer sync silently failed — deposits and withdrawals were never recorded. Reports now have accurate deposit/withdrawal data from Coinbase

## [v2.40.15] - 2026-02-23

### Fixed
- **Report AI conflates deposits with trading profit**: AI summaries now always receive capital movement/reconciliation data (account change, trading profit, net deposits) and are instructed to never present account value growth as trading performance
- **Implied net deposits when no transfer records**: When the Coinbase transfer sync has no records, reports now compute implied net deposits from the accounting identity (account change - trading profit) instead of showing $0
- **PDF report crashes on AI bullet rendering**: Fixed fpdf2 "Not enough horizontal space" error when rendering bulleted lists in AI summaries by using explicit width calculation instead of implicit remaining width
- **PDF report missing capital movement metrics**: Period start value, net deposits, and adjusted growth are now always shown in the PDF Key Metrics section (previously only shown when deposits were non-zero)

## [v2.40.14] - 2026-02-23

### Fixed
- **News article thumbnails blocked by CSP**: Broadened `img-src` to allow HTTPS images from any news source domain (previously only YouTube CDN was whitelisted)
- **TTS silence init blocked by CSP**: Added `data:` to `media-src` so the silent WAV used for AudioContext initialization isn't rejected
- **PnL chart console warnings**: Added mount guard to defer Recharts rendering until container has valid dimensions, eliminating repeated "width(-1) and height(-1)" warnings

## [v2.40.13] - 2026-02-23

### Fixed
- **Report AI summaries broken for Gemini**: GeminiClientWrapper didn't forward kwargs (like `system_instruction`) to the underlying Google AI library, causing a silent TypeError that made all Gemini-powered report summaries fail
- **Report AI provider has no fallback**: When a specific AI provider was configured for a report schedule but failed (expired key, service down), the system gave up immediately. Now tries the preferred provider first, then falls back to other available providers

### Added
- **Comprehensive test coverage**: Expanded from 433 tests / 11% coverage to 3,101 tests / 55% backend coverage across 3 rounds of parallel test-writing agents
- **Backend test coverage**: 2,516 tests covering services, routers, strategies, trading engine, exchange clients, Coinbase API, and core logic modules
- **Frontend test coverage**: 585 tests covering contexts, hooks, utilities, helpers, and API service layer

## [v2.40.12] - 2026-02-23

### Fixed
- **Smooth volume slider on mobile**: Slider is now uncontrolled during drag — volume changes go directly to GainNode/audio element with zero React re-renders, then state syncs on release

## [v2.40.11] - 2026-02-23

### Fixed
- **Volume control works on iOS**: GainNode now initialized synchronously during the user gesture (in `stop()`) before any async gaps — fixes iOS AudioContext suspension that caused complete silence

## [v2.40.10] - 2026-02-23

### Fixed
- **Volume control works on iOS**: Added Web Audio API GainNode for volume control — iOS WebKit (used by all iOS browsers including Chrome) ignores `audio.volume`, so GainNode handles actual amplitude. Lazily initialized on first user gesture to avoid iOS AudioContext suspension.

## [v2.40.9] - 2026-02-23

### Fixed
- **Volume slider restored to original smooth behavior**: Removed unnecessary Web Audio API / GainNode complexity that caused stuttering and silence — reverted to simple direct `audio.volume` control which works correctly on Chrome iOS

## [v2.40.8] - 2026-02-23

### Fixed
- **Volume slider draggable on iOS**: Enlarged touch target from 14px to 28px and added `touch-action: none` to prevent iOS from hijacking horizontal drags as scroll gestures

## [v2.40.7] - 2026-02-23

### Fixed
- **Smooth volume slider on mobile**: Volume slider no longer stutters during drag — audio volume changes instantly via direct GainNode/audio element access while React state only updates on release

## [v2.40.6] - 2026-02-23

### Fixed
- **Volume control works on iOS**: Rewrote audio volume to use Web Audio API GainNode with lazy initialization on first user gesture — iOS Safari ignores `audio.volume` entirely
- **Volume slider no longer jittery on mobile**: Changed to uncontrolled input with `step="any"` and `onInput` to prevent React re-render conflicts with touch dragging

## [v2.40.5] - 2026-02-23

### Fixed
- **Article reader volume control on iOS**: Volume slider now works on iPhone/iPad using Web Audio API GainNode (iOS Safari ignores the standard audio.volume property)
- **Volume slider smoothness**: Changed slider step from 5% to 1% for smooth, fine-grained volume control

## [v2.40.4] - 2026-02-23

### Fixed
- **Article reader volume control**: Volume slider in the mini player now immediately changes audio volume instead of being delayed or unresponsive

## [v2.40.3] - 2026-02-23

### Changed
- **Codebase structure cleanup**: Extracted seed data from database.py (1319 → 55 lines), moved bot stats and validation logic into dedicated services, relocated shared frontend types and helpers out of pages/
- **Eliminated dependency violations**: Fixed service→router inversion in news fetch, removed cross-router imports for TTS cache path and position budget helper, fixed 4 frontend component→page import inversions
- **Reduced file sizes**: database.py (-96%), bot_crud_router.py (-33%), accounts_router.py (-15%) — moved business logic to proper service layer

## [v2.40.2] - 2026-02-23

### Added
- **Comprehensive unit test coverage**: Added 333 new tests across backend and frontend, nearly doubling the test suite from 336 to 669 total tests
- **Trading engine tests**: Order logger, trailing stops, position manager budget calculations
- **Auth & security tests**: JWT token handling, encryption roundtrips, token revocation, RequireAuth component
- **Strategy tests**: Grid trading arithmetic/geometric level calculations, condition mirroring for bidirectional bots
- **Business logic tests**: Currency formatting, precision handling, order validation, portfolio conversion service
- **Router helper tests**: Account key masking, SSRF protection for prop firm bridge URLs
- **Frontend utility tests**: Bot indicator detection, position PnL calculations, chart data transforms, news filtering/pagination, markdown-to-text conversion

## [v2.40.1] - 2026-02-23

### Fixed
- **Duplicate version history entries**: The About modal was showing each commit twice because `--no-ff` merges create a merge commit with the same subject as the feature commit — now deduplicated

## [v2.40.0] - 2026-02-23

### Added
- **Structured AI summaries**: AI report summaries now use markdown with consistent section headers (Performance Overview, Goal Progress, Capital Movements, Outlook & Action Items) across all tiers, with styled rendering in both HTML and PDF
- **Expense projection table**: Expenses goal card now shows income projections (daily avg, linear, compound after tax), deposit needed (both models), and trade basis — matching the projection math already available on income goals
- **System message for AI providers**: All three AI providers (Claude, OpenAI, Gemini) now receive a system message that enforces structured output format

### Changed
- **AI summary token limit**: Increased from 2048 to 4096 tokens to support richer structured content across three tiers
- **AI summary HTML rendering**: Switched from plain paragraph splitting to full markdown rendering with dark-theme styled headers, bold, bullets, and italic text
- **PDF AI rendering**: Summaries now render markdown headers in brand color, bullets as indented items, and bold text via fpdf2's built-in markdown support
- **PDF emoji handling**: Emoji characters are now stripped from PDF output (Helvetica lacks emoji glyphs) while preserved in HTML

## [v2.39.7] - 2026-02-23

### Fixed
- **PDF upcoming expenses**: PDF report now uses the same upcoming logic as HTML — correct anchor-aware dates, bill amounts, and current-month scoping
- **DRY upcoming logic**: Extracted shared `_get_upcoming_items` helper used by both HTML and PDF report generators, eliminating duplicated code that was drifting out of sync

## [v2.39.6] - 2026-02-23

### Fixed
- **Upcoming scoped to current month**: Weekly, biweekly, and every-N-days expenses no longer spill into next month in the upcoming tab — only shows what's due the rest of this month

## [v2.39.5] - 2026-02-23

### Changed
- **Upcoming due labels**: Due dates now include the month (e.g., "Fri Feb 27th" instead of "Fri 27th", "Feb 15th" instead of "15th")

## [v2.39.4] - 2026-02-23

### Fixed
- **Upcoming expense amounts**: Upcoming tab now shows the actual bill amount due on that date instead of the monthly-normalized amount

## [v2.39.3] - 2026-02-23

### Fixed
- **Biweekly due dates**: Biweekly expenses with different anchor dates now show correct next due dates instead of both landing on the same week
- **Every-N-days in reports**: Expenses with custom day intervals now appear in the Upcoming tab and show their computed next due date
- **Every-N-days anchor date**: Custom interval expenses can now set a start date in the expense editor so the system knows when to count from

### Added
- **Frontend test infrastructure**: Vitest setup with React Testing Library for frontend unit testing

## [v2.39.2] - 2026-02-23

### Fixed
- **Email reports missing expense data**: Coverage and Upcoming expense sections were hidden in email reports because CSS-only tabs don't work in email clients — now rendered as stacked inline sections
- **PDF reports missing upcoming expenses**: PDF reports only showed expense coverage items but completely omitted the Upcoming expenses section
- **Weekly expense due labels**: Upcoming expense due dates for weekly/biweekly items now show day-of-week and day-of-month (e.g., "Fri 27th") instead of just the day name

## [v2.39.1] - 2026-02-23

### Changed
- **Styled confirmation dialogs**: All native browser confirm/alert popups replaced with themed modal dialogs matching the app's dark trading UI
- **Toast notifications**: Error and success alerts now appear as styled toast notifications instead of browser popups

### Fixed
- **Expense fields not saved on create**: Due day, due month, and login URL were not being saved when creating new expense items (only when editing existing ones)

## [v2.39.0] - 2026-02-23

### Added
- **Expense due month**: Quarterly, semi-annual, and yearly expenses now support a due month selector so you can specify exactly when they're due (e.g., March 15th for annual insurance)
- **Day-of-week selector**: Weekly and biweekly expenses now show pill buttons to pick which day of the week they're due (Mon–Sun)
- **Biweekly start date**: Biweekly expenses can set a calendar anchor date so the "upcoming" tab knows which weeks they fall on
- **Expense login URLs**: Add an optional login URL to any expense — clicking the expense name in the HTML report opens the payment/login page in a new tab
- **Smart upcoming tab**: Upcoming expenses tab now handles weekly, biweekly, and multi-month frequencies correctly — not just monthly

## [v2.38.0] - 2026-02-22

### Added
- **Expense due days**: Set the day of month (1-31 or last day) when each expense is due
- **Upcoming expenses tab**: Report expense cards now have two tabs — "Coverage" (existing waterfall) and "Upcoming" (bills remaining this month sorted by due date)
- **Due day badges**: Expense list in the editor shows a compact "Due 15th" or "Due last" badge next to each item

## [v2.37.1] - 2026-02-22

### Fixed
- **AI summaries now visible in report viewer**: All three AI summary tiers (Simplified, Analysis, Technical) now display correctly when viewing reports in the app — CSS specificity issue prevented tab panels from appearing

### Added
- **`/code-quality` command**: New slash command to run comprehensive code quality sweeps across security, testing, architecture, dead code, and documentation
- **`code-hygiene` agent**: Audits dead code, modularization violations, hardcoded values, documentation gaps, and error handling anti-patterns
- **`regression-check` agent**: Diffs changes before shipping to flag deleted code, changed API contracts, and behavioral side effects

## [v2.37.0] - 2026-02-22

### Added
- **Semi-monthly and semi-annual expense frequencies**: Two new options for expenses that occur twice a month or twice a year
- **Pill-based frequency selector**: Expense editor now uses a clean pill button UI instead of a dropdown, making all frequency options visible at a glance
- **Custom frequency option**: "Custom" pill reveals an inline "Every ___ days" input for non-standard intervals

### Changed
- **Expense editor opens as overlay**: Add/edit expense form now appears as a centered overlay on top of the list, so you don't lose your scroll position with long expense lists
- **Deposit guidance shows incremental amount**: "Cover all listed expenses" line now includes the additional deposit beyond individually mentioned items, e.g. "~$12,345 total (+$3,456)"

### Fixed
- **Report AI summary tabs now work reliably**: Tab switching in report viewer no longer breaks intermittently
- **Custom expense categories available immediately**: Adding an expense with a custom category now shows it in the dropdown right away for the next expense

## [v2.36.4] - 2026-02-22

### Fixed
- **Report AI summary tabs now clickable**: Tabs were blocked by Content Security Policy; switched to blob URL rendering which bypasses CSP restrictions
- **Deposit calculation accounts for taxes**: Deposit suggestions now factor in tax withholding — shows how much trading capital to add so that after-tax returns cover expenses
- **Per-item deposit amounts**: Each uncovered expense shows the specific deposit needed, e.g. "Finish covering Insurance: deposit ~$2,400" and "Then cover Rent: deposit ~$21,800 more"

## [v2.36.3] - 2026-02-22

### Changed
- **Granular deposit guidance**: Expense reports now show targeted suggestions like "Finish covering Insurance: $165 more needed" and "Next: Rent ($1,500)" instead of just a total deposit figure
- Deposit guidance appears in HTML reports, PDFs, and AI summaries

## [v2.36.2] - 2026-02-22

### Changed
- **Tabbed AI summaries in reports**: The three AI analysis tiers (Simplified, Performance Analysis, Technical) now appear as clickable tabs instead of stacked sections
- **Email reports show single tier**: Emails display only the recipient's preferred analysis tier for a cleaner reading experience

### Fixed
- **Report delivery status**: Reports generated from schedules with no email recipients now correctly show "Manual" instead of getting stuck on "Pending"

## [v2.36.1] - 2026-02-22

### Fixed
- **Expenses goal creation**: Goal form no longer stays open after creating an expenses goal (async lazy-load crash)
- **Expense editor auto-opens**: After creating an expenses goal, the expense items editor opens automatically so you can start adding items right away

## [v2.36.0] - 2026-02-22

### Added
- **Expenses goal type**: New goal type that tracks itemized living expenses and measures how close your trading income is to covering them
- **Expense items management**: Add, edit, and delete individual expense items with flexible frequencies (daily, weekly, biweekly, every N days, monthly, quarterly, yearly)
- **Coverage waterfall**: Reports show which expenses are covered, partially covered, or uncovered by your income — sorted from cheapest to most expensive
- **Tax withholding**: Optional tax percentage deducted from income before expense coverage comparison
- **Automatic normalization**: All expense items normalized to your chosen period (weekly, monthly, quarterly, yearly) regardless of individual billing frequency
- **12 default expense categories**: Housing, Utilities, Transportation, Food, Insurance, Healthcare, Subscriptions, Entertainment, Education, Debt, Personal, Other — plus custom categories
- **Expense coverage in reports**: HTML and PDF reports include a detailed expense card with coverage progress bar, itemized waterfall table, and deposit-to-go suggestion
- **AI summary integration**: AI analysis now includes expense coverage data when summarizing reports with expenses goals

## [v2.35.1] - 2026-02-22

### Changed
- **Goal trend charts now appear in generated reports**: Trend line visualizations (actual vs ideal trajectory) are embedded directly in HTML and PDF reports instead of the Goals tab
- **Goals tab simplified**: Removed interactive trend chart from the Goals tab — goals are now clean and focused on targets

## [v2.35.0] - 2026-02-22

### Added
- **Goal trend line chart**: Visual progress tracking for financial goals — shows actual portfolio value vs. ideal trajectory over time with an interactive chart
- **Daily goal progress snapshots**: Automatic daily capture of goal progress during the account snapshot cycle for historical trend data
- **Auto-backfill on first view**: Existing goals automatically reconstruct historical progress from account value snapshots when you first view their trend
- **Smart on-track detection**: Chart shows whether you're ahead or behind your target trajectory with color-coded status badges

## [v2.34.1] - 2026-02-22

### Added
- **Development workflow commands**: New slash commands `/primer`, `/generate-prp`, `/execute-prp`, and `/fix-github-issue` for structured development workflows
- **Validation and documentation agents**: Automated code quality gating and architecture documentation sync
- **Domain knowledge reference**: Trading domain specifics (budget calculation, AI allocation flow) now in a dedicated reference doc

### Changed
- **Restructured project guide**: Cleaner, more focused development instructions with clear philosophy, rules, and architecture reference

## [v2.34.0] - 2026-02-22

### Added
- **Password visibility toggle on login**: Eye icon to show/hide password while typing, auto-hides after 5 seconds
- **TradingView chart loading indicator**: Spinner overlay while the chart widget downloads and initializes
- **Max Synthetic Candles % setting**: New bot-level filter to skip pairs with too many gap-filled candles during analysis
- **Broken articles "Retry All"**: When filtering to Broken articles, "Read All" becomes "Retry All" and re-attempts TTS instead of skipping

### Fixed
- **Modal buttons hidden behind mini player**: Modals now render above the article reader mini player
- **Number input snapping to 0**: Editing deal settings (take profit, safety orders, etc.) no longer snaps to 0 when clearing the field
- **Category filter resetting source selection**: Changing news/video categories no longer clears your source filter
- **"All" category button toggling confusingly**: "All" now always selects all categories instead of toggling to a single category

### Changed
- **Indicator logs responsive on mobile**: Filters wrap, condition details stack vertically, modal uses full viewport width
- **Bot config modal responsive on mobile**: Capped to viewport width, reduced padding, action buttons wrap
- **Balance columns readable on mobile**: Narrower columns, smaller text, BTC values show 6 decimals instead of 8

## [v2.33.0] - 2026-02-22

### Added
- **Video tab pagination**: Videos now load 50 at a time instead of all ~4000 at once, dramatically reducing thumbnail requests and page load time. Pagination controls match the article tab style. "Play All" and the playlist dropdown still use the full filtered list.

## [v2.32.8] - 2026-02-20

### Fixed
- **YouTube videos and news cleanup working again**: A timezone mismatch caused the video/article cleanup to crash, which broke the entire refresh cycle. Videos and news articles now refresh normally.

## [v2.32.7] - 2026-02-20

### Fixed
- **Crossing detection now uses candle data instead of stale cache**: Crossing above/below conditions (e.g., "MACD cross above 0") were comparing against cached values from a previous check cycle, which could be stale after service restarts or long gaps. Now compares the two most recent closed candles — a crossing only fires when it actually happened on the latest candle close.

## [v2.32.6] - 2026-02-20

### Fixed
- **Increasing/Decreasing conditions now work**: These operators were available in the condition builder but silently ignored at runtime — they always returned false. Now properly compares current vs previous closed candle values.
- Condition logs now show both previous and current values for increasing/decreasing checks (e.g., "48.2 → 52.3 ↑") instead of just one number

## [v2.32.5] - 2026-02-20

### Fixed
- Editing an existing bot no longer fails with "Please select an account" — the bot's existing account is preserved during updates

## [v2.32.4] - 2026-02-20

### Added
- Report title (schedule name) now appears in generated HTML reports, PDFs, and email subject lines instead of generic "Performance Report"

## [v2.32.3] - 2026-02-20

### Fixed
- Report viewer (eye icon) was broken — clicking it did nothing due to missing eager-load on schedule relationship

## [v2.32.2] - 2026-02-20

### Changed
- Report history table now shows the report name alongside frequency for easier identification

## [v2.32.0] - 2026-02-20

### Added
- **Auto wrap-up for period-start days**: When a report runs on the 1st of the month (MTD) or Monday (WTD), it automatically wraps up the full prior period instead of covering just one day. Solves the "missed last-day trades" problem in 24/7 crypto markets.
- **Three-state day toggle**: Period-start days (1st, Monday) cycle through amber (wrap-up), blue (standard), and deselected. Other days remain the normal two-state toggle.
- **Day picker legend**: Color key appears below the day picker explaining amber (wraps up prior period) vs blue (standard) when relevant

## [v2.31.3] - 2026-02-20

### Changed
- Report history "Created" column now shows the time in your local timezone (e.g., "Feb 20, 2026 11:53 PM")

## [v2.31.2] - 2026-02-20

### Fixed
- **PDF generation failing on Unicode characters**: AI summaries containing en-dashes, smart quotes, or other Unicode characters would crash PDF generation — now sanitized to Latin-1 equivalents

## [v2.31.1] - 2026-02-20

### Fixed
- **Goal lookback controlled by schedule**: Income goal projections now use the report schedule's period window (WTD, MTD, trailing N days, etc.) instead of a separate lookback setting on each goal — one place to control how far back reports look

### Removed
- Lookback Window dropdown from goal form (redundant with schedule-level period window)
- Lookback badge from goal cards on Reports page

## [v2.31.0] - 2026-02-20

### Added
- **Flexible report scheduling**: Replace the rigid frequency dropdown with two independent controls — pick exactly when reports run (specific weekdays, days of month, quarterly/yearly dates) and how far back they look (full prior period, WTD, MTD, QTD, YTD, or trailing N days/weeks/months/years)
- **Multi-day schedules**: Weekly schedules can run on multiple days (e.g., Mon + Wed), monthly on multiple dates (e.g., 1st & 15th), with "Last day" option for month-end reports
- **Ad-hoc reports don't affect schedule**: Manually generating a report no longer advances the schedule's next run time — your scheduled cadence stays intact

### Changed
- Schedule cards now display a human-readable description (e.g., "Every Mon, Wed - full prior period") instead of a single word

## [v2.30.0] - 2026-02-19

### Added
- **Goal date picker**: Set a specific target date for goals instead of just month presets — custom date input with prominent blue badge display on goal cards
- **Deposit/withdrawal tracking**: Automatically fetches deposits and withdrawals from Coinbase and stores them locally for accurate performance analysis
- **True PnL in reports**: Reports now show net deposits, adjusted account growth (excluding capital injections), and transfer counts — so you can see real trading performance separate from money added/removed
- **AI summary awareness**: AI-generated report summaries now factor in deposits and withdrawals, explicitly noting when account growth includes capital movements
- **Dashboard deposit note**: When deposits occurred in the last 30 days, a subtle info bar appears below the projection table explaining the capital context
- **Account value chart markers**: Deposit and withdrawal events appear as arrow markers on the account value chart so you can see exactly when capital was added or removed
- **Transfer management API**: Full REST API for syncing, listing, and manually entering transfers — with automatic daily background sync from Coinbase
- **Manual transfer entry**: Add transfers manually for deposits/withdrawals the API can't see

### Changed
- **Report trade count label**: Now shows "Total Trades (last Nd)" with the actual period length for clarity

## [v2.29.0] - 2026-02-19

### Added
- **Experience-level reports**: Each email recipient can be tagged as Beginner, Comfortable, or Experienced — the AI generates three summary tiers in a single call, and each recipient's email highlights their level's analysis with the others still accessible
- **Report delete**: Delete reports from the history tab with a confirmation prompt
- **Coin review scheduler**: Weekly AI-powered coin categorization now runs automatically inside the backend (no more external timer)

### Changed
- **Email branding**: Report emails now use the brand accent color instead of hardcoded blue for headers and AI section highlights
- **Tab persistence**: Active tab on the Reports page now survives page refresh and navigation
- **Gemini model updated**: Switched from deprecated `gemini-1.5-pro` to `gemini-2.0-flash` across all AI services (reports, coin review, grid optimizer)

### Fixed
- **AI report summaries not generating**: Gemini provider was failing silently due to deprecated model name — now uses `gemini-2.0-flash` and logs provider errors at warning level instead of debug

## [v2.28.1] - 2026-02-19

### Added
- **Performance disclaimer**: Income goal projections now include a professional disclaimer that past performance does not guarantee future results, both in the HTML report card and in AI-generated summaries

## [v2.28.0] - 2026-02-19

### Added
- **Income Goals**: New goal type that tracks your earning rate — set a target like "$1,000/month" and reports project your current income both linearly and with compounding, plus advise how much additional capital to deposit to reach the goal
- Configurable lookback window for income calculations (7/14/30/90/365 days or all-time)
- Income goal cards in reports show daily average, linear/compound projections, and deposit-needed estimates

### Fixed
- **Report account value**: Performance reports no longer include paper trading or inactive accounts when calculating total account value — previously inflated values by counting simulated accounts

## [v2.27.0] - 2026-02-19

### Added
- **Performance Reports & Goals**: Full reporting system with customizable financial goals (balance, profit, or both targets in USD/BTC), scheduled report generation (daily through yearly), AI-powered analysis summaries using your own AI provider credentials, and email delivery with PDF attachments
- **Report History**: View and download past reports in-app with HTML preview and PDF download
- **Goal Progress Tracking**: Visual progress bars showing on-track status relative to time elapsed, integrated into reports
- **Period-on-Period Comparison**: Reports automatically include prior period data for trend analysis
- **GitHub link on login page**: "Zenith Grid" text on the login page now links to the open source repository

## [v2.26.9] - 2026-02-19

### Fixed
- **Auto-buy BTC now actually executes**: Fixed three layered bugs preventing auto-buy from converting USD to BTC:
  1. Logs were invisible (uvicorn suppressed logger output)
  2. Coinbase order responses were parsed incorrectly — order_id was always None, failures were silently ignored
  3. Sending 100% of available balance failed because Coinbase needs room for taker fees (~0.6%)
- **Portfolio sell now returns real order details**: Manual "Sell to USD/BTC" was silently swallowing Coinbase errors and returning null order IDs
- **Account consolidation fee buffer**: USD-to-BTC consolidation now reserves 1% for exchange fees

## [v2.26.7] - 2026-02-19

### Fixed
- **Auto-buy logging now visible**: Auto-buy monitor messages (balance checks, triggers, order placements) now appear in production logs — previously invisible due to uvicorn logger configuration

## [v2.26.6] - 2026-02-19

### Fixed
- **Portfolio sell buttons now work**: Fixed "Sell to BTC" and "Sell to USD" failing with "Failed to execute market sell" — Coinbase API requires uppercase side parameter
- **Auto-buy BTC now executes**: Fixed auto-buy monitor silently failing when open USD positions existed due to referencing a nonexistent field; added visible logging so auto-buy activity shows in logs
- **Sell uses selected account**: Portfolio sell now targets the currently selected account instead of always using the default

## [v2.26.5] - 2026-02-19

### Fixed
- **Portfolio balances now match Coinbase**: Refresh button bypasses all backend caches and fetches live data directly from Coinbase
- **Faster portfolio updates**: Auto-refresh interval reduced from 60s to 30s, data refreshes on tab focus and page navigation
- **Bot action menu cut off**: Fixed dropdown menu on the Bots page overflowing off-screen — "Cancel All Deals", "Sell All at Market", and "Delete" options were hidden when many accounts existed

## [v2.26.4] - 2026-02-19

### Fixed
- **Bot action menu cut off**: Fixed dropdown menu on the Bots page overflowing off-screen — "Cancel All Deals", "Sell All at Market", and "Delete" options were hidden when many accounts existed. Menu now scrolls and positions correctly on all screen sizes.

## [v2.26.3] - 2026-02-19

### Fixed
- **News page loading**: Fixed regression where news articles failed to load — page_size=0 (return all) was incorrectly rejected as invalid
- **TTS audio playback**: Fixed Content-Security-Policy blocking blob: audio URLs used by the article reader

### Security
- **Server-side token revocation**: Logout now invalidates the token server-side — stolen tokens can no longer be reused
- **Password change invalidates all sessions**: Changing or resetting your password immediately logs out all other devices
- **WebSocket connection limits**: Each user is now limited to 5 concurrent WebSocket connections, with 4KB message size limit and 5-minute idle timeout
- **Image path traversal guard**: Added defense-in-depth path validation on the article thumbnail endpoint

## [v2.26.2] - 2026-02-19

### Security
- **Login timing attack fixed**: Response time is now identical whether an email exists or not, preventing username enumeration
- **MFA brute-force protection**: TOTP and email MFA verification endpoints now rate-limit to 5 attempts per token within 5 minutes
- **Nginx security headers**: Added HSTS (Strict-Transport-Security) and Content-Security-Policy headers
- **Nginx rate limiting**: Auth endpoints limited to 5 req/min, API endpoints to 30 req/s per IP — floods are blocked before reaching the application
- **Request size limit**: Added 10MB max body size in nginx to prevent memory exhaustion from oversized POST bodies
- **Unbounded page_size fixed**: News endpoint now clamps page_size to 200 max, preventing full-table dumps
- **Settings endpoint restricted**: Individual settings lookup now requires superuser access
- **Article flagging restricted**: Mark-article-issue endpoint now requires superuser access
- **Per-user article fetch rate limit**: External article content extraction limited to 30 per user per hour
- **Per-username login rate limiting**: Login attempts now tracked by both IP and email — rotating IPs can't bypass the limit
- **Per-email forgot-password rate limiting**: Password reset requests limited to 3 per email per hour
- **WebSocket timeout reduced**: Idle WebSocket connections now timeout after 5 minutes instead of 24 hours

## [v2.26.1] - 2026-02-19

### Changed
- **Architecture documentation overhaul**: Updated architecture.json, ARCHITECTURE.md, and README.md to reflect the current state of the application — added 13 missing migrations, 7 missing services, 5 missing models, 16 sentiment card components, multi-exchange support, MFA/email features, and TTS article reader
- **README modernized**: Added Security & Multi-User section, Multi-Exchange Support section, expanded features comparison table, updated roadmap with completed milestones, fixed stale URLs and descriptions

## [v2.26.0] - 2026-02-19

### Added
- **Parallel bot processing**: Bots now process concurrently (up to 5 at a time) instead of sequentially — 3-5x faster cycle times for multi-bot setups
- **Thundering herd prevention**: When cached prices/products expire, only one request fetches fresh data while others wait for the result — eliminates redundant API calls under load
- **Candle chart caching**: The charting endpoint now caches candle data with per-timeframe TTLs — multiple users viewing the same chart no longer trigger duplicate API calls
- **Rate limiter self-cleaning**: Login/signup/password-reset rate limiters now prune stale entries hourly to prevent slow memory growth

### Fixed
- **Exchange client cache race condition**: Added async locking to prevent duplicate client creation when multiple requests hit the same account concurrently
- **Monitor exchange cache race condition**: Same double-checked locking pattern applied to the bot monitor's per-account exchange cache
- **Candle cache shared across users**: Candle data (which is public/identical for all users) no longer includes account ID in cache keys — with 5 users trading the same pair, candle fetches drop from 5x to 1x
- **Unbounded cache growth**: Indicator and scheduling caches now prune entries for deleted/deactivated bots each cycle

## [v2.25.3] - 2026-02-19

### Fixed
- **"Full articles" filter now works**: The `content_scrape_allowed` field was being stripped from API responses by the Pydantic response model, so the frontend filter had no data to filter on — added the field to the response schema

## [v2.25.2] - 2026-02-19

### Changed
- **"Summary only" badge on article cards**: Renamed from "RSS" to "Summary only" with amber styling to clearly indicate articles that only have a summary (source blocks full content scraping)
- **Filter tooltip updated**: "Full articles" button tooltip now describes hiding summary-only articles instead of referencing RSS

## [v2.25.1] - 2026-02-19

### Changed
- **Source badge colors now driven by API category**: Source badges on articles, videos, and mini-players derive their color from the backend category field instead of a hardcoded frontend mapping — new and custom sources automatically get correct category colors

### Removed
- **Hardcoded source-to-category dictionaries**: Deleted ~100 lines of duplicated frontend mappings (SOURCE_CATEGORY, VIDEO_SOURCE_CATEGORY) that had to be manually kept in sync with the database

## [v2.25.0] - 2026-02-19

### Added
- **47 mainstream news sources**: BBC, NPR, CBS News, NBC News, ABC News, PBS NewsHour, The Hill, and Politico across World, Politics, Nation, Business, Technology, Entertainment, Sports, Science, and Health categories
- **RSS badge on article cards**: Articles from RSS-only sources (no in-app reader/TTS) now show a muted "RSS" badge next to the source name
- **"Full articles" filter toggle**: Button in the filter bar hides RSS-only articles so users can browse only sources that support full in-app reading and TTS; persists to localStorage

### Changed
- **Replaced frozen CNN feeds**: CNN RSS feeds (stale since Aug 2024) replaced with active feeds from BBC, NPR, CBS, NBC, ABC, PBS, The Hill, and Politico

### Removed
- **CNN RSS feeds**: 7 CNN category feeds dropped (rss.cnn.com returns stale content frozen since August 2024)

## [v2.24.0] - 2026-02-19

### Added
- **7 CNN RSS feeds**: CNN World, CNN Politics, CNN US, CNN Business, CNN Tech, CNN Entertainment, CNN Health — each mapped to its matching category
- **Politics category**: New news category slotted between World and Nation

### Changed
- **Equidistant category colors**: Rebalanced the 12-category color spectrum — Health moved from emerald to teal, Politics uses sky — so hues are evenly spaced across the Tailwind palette

## [v2.23.2] - 2026-02-19

### Fixed
- **URL scheme normalization for custom sources**: Bare domains like `cnn.com` are now automatically prefixed with `https://` before robots.txt checks, deduplication, and storage. Applies to `add_custom_source`, `check_robots`, and `normalize_feed_url`

## [v2.23.1] - 2026-02-19

### Fixed
- **robots.txt check: unreachable domains no longer show green checkmarks**: Connection-level failures (SSL errors, DNS failures, connection refused) now correctly block adding the source instead of defaulting to "all allowed"
- **Friendly error messages**: Raw SSL/DNS exception text replaced with human-readable messages (e.g., "SSL/TLS connection failed" instead of `[SSL: TLSV1_UNRECOGNIZED_NAME]...`)

## [v2.23.0] - 2026-02-19

### Added
- **robots.txt validation for custom sources**: When adding a custom news source, the system now fetches and parses the domain's robots.txt to determine RSS feed access, article scraping permissions, and crawl delay
- **"Check Source" button** in Add Custom Source form: Users can preview the robots.txt policy before adding — shows green (full access), amber (RSS-only), or red (blocked) status panel
- **Backend enforcement**: Custom news sources that block RSS access are rejected at the API level. Permitted sources automatically get `content_scrape_allowed` and `crawl_delay_seconds` set from robots.txt
- **New `/api/sources/check-robots` endpoint**: Authenticated POST endpoint that returns parsed robots.txt policy for any URL

## [v2.22.0] - 2026-02-19

### Added
- **Per-source content scraping policies**: robots.txt audit of all 47 news sources. Sources that block AI bots/scrapers are now marked RSS-only (`content_scrape_allowed=0`) — RSS feeds still work, but article body scraping is blocked. 26 sources marked RSS-only
- **Per-domain crawl delays**: Sources with specific crawl-delay in robots.txt are respected (e.g., Bitcoin Magazine 5s, SCMP 10s). Module-level tracking prevents hammering
- **20 new permissive sources**: 9 crypto (NewsBTC, CryptoPotato, Bitcoinist, U.Today, CoinJournal, The Crypto Basic, Crypto Briefing, Watcher Guru, Blockchain.News), 5 world (VOA News, Global Voices, RFE/RL, Africanews, SCMP), 6 science (Quanta Magazine, ScienceAlert, Futurism, Live Science, Space.com, Smithsonian Magazine)
- **SOURCE_SCRAPE_POLICIES dict** in database.py: Centralized policy definitions that seed function syncs to DB on every startup

### Removed
- **8 dropped sources**: Reddit r/CryptoCurrency, Reddit r/Bitcoin, Reddit r/artificial (ToS prohibit scraping), BBC World, The Guardian World, Al Jazeera (explicit legal prohibitions), New Scientist (aggressive anti-bot), The Block (broken feed + anti-scrape)

### Fixed
- **Stale frontend category map entries**: Removed leftover `ft_markets`, `marketwatch`, `reuters_finance`, `techcrunch` entries from newsUtils.tsx

## [v2.21.1] - 2026-02-19

### Changed
- **Video filter labels**: News Videos tab now shows "Watched/Unwatched" instead of "Read/Unread" for filter pills, bulk action buttons, and per-video eye button tooltips

## [v2.21.0] - 2026-02-19

### Added
- **Fetch once, never re-fetch**: Backend now persists `content_fetch_failed` flag on articles when external content extraction fails. Subsequent requests return instant failure from cache — no external network call. Prevents hammering failing sources
- **content_fetch_failed migration**: Backfills existing broken articles (`has_issue=1 AND content IS NULL`) so they're never re-fetched

### Changed
- **Retry button → Regenerate audio**: The "Retry full article" button now says "Regenerate audio" and regenerates TTS from existing text (content or summary) without any external fetch
- **Single fetch replaces exponential backoff**: Frontend no longer retries content fetch 4 times with increasing delays. One fetch attempt is sufficient since failures are now persisted server-side

### Removed
- **medicalxpress.com source**: Removed from all source lists, seed data, and category maps. Cleanup migration deletes existing articles, TTS cache, and source record. medicalxpress blocked our EC2 IP after repeated fetch attempts

## [v2.20.4] - 2026-02-19

### Fixed
- **TTS cache falsely invalidated for old records**: v2.20.2 content_hash check treated NULL hash (all pre-existing TTS) as a mismatch, causing regeneration on first play. For articles where the source site now blocks our server, this replaced full-content audio with summary-only audio. Fix: only invalidate when a hash exists AND differs

## [v2.20.3] - 2026-02-19

### Fixed
- **Broken articles skip instead of showing retry button**: Clicking a `has_issue` article auto-skipped to the next article before the mini-player could mount, making the retry button unreachable. Auto-skip now only fires during playlist auto-advance — user-initiated clicks always show the mini-player with the retry button visible. Also clears `has_issue` if the content fetch succeeds on open (not just on explicit retry)

## [v2.20.2] - 2026-02-19

### Fixed
- **TTS cache ignores text changes**: `_get_or_create_tts()` cached audio by `(article_id, voice)` only. When article content changed (e.g., retry fetched full text after initial summary-only), stale summary audio was returned. Cache now stores a `content_hash` (MD5-8) and invalidates on mismatch — deletes old audio file + DB record, regenerates from new text

## [v2.20.1] - 2026-02-19

### Fixed
- **TTS audio cache-buster**: Browser was serving stale (short) audio after article content was re-extracted. Audio URLs now include `?v={content_hash}` so the browser fetches fresh audio when the underlying text changes

## [v2.20.0] - 2026-02-19

### Added
- **Retry button for broken articles**: Articles flagged as `has_issue` or playing summary-only now show a blue "Retry" button in the mini-player (both expanded and collapsed modes). Clicking re-attempts full content extraction; on success, clears the broken flag and plays the full article
- **Persistent article content cache**: Extracted article text is now stored in the database (`news_articles.content` column). All users share the same cache — content is fetched once via trafilatura, then served from DB on all subsequent requests. Eliminates redundant fetches and survives backend restarts
- **TTS cleanup on article deletion**: When articles age out (>7 days), their TTS audio cache directories and DB records are now deleted alongside image files. Prevents orphaned files from accumulating on disk

### Fixed
- **setup.py lint cleanup**: Fixed all 154 flake8 violations (E302, E501, E128) — formatting only, no logic changes

## [v2.19.0] - 2026-02-18

### Added
- **Summary-only indicator**: Amber "Summary only" badge in mini-player (expanded + collapsed) when content extraction fails and falls back to RSS summary
- **Content fetch retry with backoff**: Article content now retries 4 times with exponential backoff (0s, 1.5s, 3s, 6s) before falling back to summary

### Changed
- Articles that fall back to summary are now auto-flagged as `has_issue` (appear in Broken filter)

### Fixed
- **Flake8 lint cleanup**: Fixed all 145 E501 (line too long) violations and 1 F401 (unused import) across 28 backend files. Formatting only — no logic changes

## [v2.18.9] - 2026-02-18

### Fixed
- **Version reporting accuracy**: Backend now snapshots the git version at startup and serves it from memory. Previously, `git describe --tags` ran on every API call, so pushing a new tag caused the old (still-running) backend to report the new version before being restarted — triggering premature update toasts

## [v2.18.8] - 2026-02-18

### Fixed
- **Version toast stability**: Now verifies the server is fully stable before showing the update notification. Performs 3 health checks over 20 seconds — all must return the same new version before prompting the user to reload

## [v2.18.7] - 2026-02-18

### Fixed
- **Resume from where you left off**: Session now saves playback position (every 5s), voice, and speed. On resume, restores the same voice and seeks to the saved position instead of starting the article over from the beginning

## [v2.18.6] - 2026-02-18

### Fixed
- **Version update toast timing**: Toast now waits 5 seconds and re-verifies the server is responding before prompting. Prevents showing "New Version Available" while the backend is still restarting

## [v2.18.5] - 2026-02-18

### Added
- **"Broken" filter pill**: New filter option alongside All/Unread/Read to show articles flagged with playback issues. Amber-tinted when active. Articles tab only

### Fixed
- **Issue badge always visible**: Amber AlertCircle badge now shows on flagged articles regardless of read/unread status (was hidden on read articles). Takes visual priority over the seen checkmark

## [v2.18.4] - 2026-02-18

### Fixed
- **Resume prompt after refresh**: Session was silently failing to save because the full 12k+ article playlist exceeded localStorage's 5MB quota. Now saves only a 50-article window ahead of current position (~25KB)

## [v2.18.3] - 2026-02-18

### Fixed
- **Article card click during playback**: Clicking an article that's already playing now expands the mini-player instead of restarting the article from the beginning

## [v2.18.2] - 2026-02-18

### Fixed
- **Optimistic mark-as-read**: Clicking the eye button now updates the UI instantly instead of waiting for a full data refetch (was re-downloading ~6MB of articles on every click). Reverts automatically if the API call fails
- **Nginx gzip compression**: Enabled gzip for JSON, JS, CSS, and other text types. News API response compressed from 6.5MB to 1.8MB (72% reduction)

## [v2.18.1] - 2026-02-18

### Added
- **"Powered by Zenith Grid" branding**: Subtle footer text on Login page, About modal, main app footer, and maintenance page

### Fixed
- **TTS retry before flagging**: Articles now get one retry before being flagged as having issues. First TTS error retries after 3s; only flags and skips on second failure (4s delay). Content fetch also retries once (1.5s) before giving up
- **Maintenance page branding**: Updated and synced `maintenance.html` to nginx server root

## [v2.18.0] - 2026-02-18

### Added
- **Continuous play toggle**: ON by default for "Read All", OFF for single article clicks. Repeat icon button in mini-player controls. When OFF, playback stops after each article but mini-player stays visible for manual control
- **Resume-on-refresh prompt**: Instead of silently auto-resuming TTS after page refresh, shows "Continue where you left off?" banner with Resume/Dismiss buttons
- **Article issue tracking**: `has_issue` flag on news articles for TTS failures. Amber AlertCircle badge on affected cards and playlist items. Backend `POST /api/news/article-issue` endpoint
- **Auto-skip failed articles**: TTS errors auto-flag the article and skip after 2s delay. Content fetch failures (no content AND no summary) skip after 1s. Known-bad articles skipped instantly (300ms) on future plays
- **Full retention period in News**: Removed 500-article cap — users now see all articles within their retention window (14 days default or custom override). Backend `page_size=0` returns all articles; client-side filtering + pagination handles display

### Fixed
- Mini-player now stays visible when article finishes with continuous play OFF (was disappearing)
- Missing `id` field in 2 of 4 ArticleItem construction points in News.tsx (article dropdown, text body click)
- `togglePlayPause` now handles stopped-but-visible state (replays current article)

## [v2.17.0] - 2026-02-18

### Added
- **Read/seen tracking for news articles and videos**: Per-user tracking of which articles and videos have been consumed. Polymorphic `user_content_seen_status` table with `content_type` discriminator scoped by `user_id`
- **Seen filter pills**: Three-state toggle (All / Unread / Read) above the news grid, with separate state for articles and videos tabs. Filter state persisted to localStorage
- **Seen indicators on cards**: Subtle check badge (top-left corner) and dimmed title on read articles/videos. Full card remains clickable
- **Per-card seen toggle**: Eye/EyeOff button on each article and video card to manually mark as read/unread
- **Bulk mark read/unread**: "Mark all read" / "Mark all unread" button operates on all currently filtered and visible items
- **Auto-mark on TTS completion**: Articles automatically marked as read when TTS finishes playing them
- **Auto-mark on reader open**: Articles marked as read when opened in the article reader
- **Auto-mark on video end**: Videos marked as read when YouTube player reaches the end
- **Backend API endpoints**: `POST /api/news/seen` (single) and `POST /api/news/seen/bulk` for marking content seen/unseen, with SQLite upsert-on-conflict handling
- **Video ID in API response**: `video_to_item()` now includes `id` field for seen tracking

## [v2.16.0] - 2026-02-18

### Added
- **Full rebrand to BTC-Bot**: "Big Truckin' Crypto Bot" identity across login, header, emails, maintenance page, favicon, about modal, and all auth screens. Truck icon replaces Activity icon throughout
- **Dynamic branding system**: All brand values (name, tagline, colors, images) loaded from `branding/custom/brand.json` — no hardcoded strings. New users copy `branding/template/` to get started. Backend serves `/api/brand` (public) and `/api/brand/images/` endpoints
- **Theme toggle**: Electric Blue Neon (`#00d4ff`) and Classic Blue (`#3b82f6`) themes via CSS custom properties. Toggle in Settings > Appearance, persists to localStorage. Brand config sets default theme for new users
- **BrandContext + ThemeContext**: React contexts provide `useBrand()` and `useTheme()` hooks to all components. Brand config fetched once from API, theme applied via CSS class on document root
- **Branding folder structure**: `branding/template/` (tracked, Zenith Grid defaults) + `branding/custom/` (gitignored, user's brand). README with full setup instructions

### Changed
- Email templates now use brand service for name, tagline, and copyright instead of hardcoded values
- FastAPI title, API root message, and TOTP issuer all read from brand config dynamically
- Tailwind extended with `theme-*` color utilities mapped to CSS variables and `neon`/`neon-sm` box shadows

## [v2.15.0] - 2026-02-18

### Added
- **"New Version Available" reload notification**: After a deployment, users with the app already open see a persistent amber toast prompting them to reload. Detected via WebSocket reconnect (fires ~5s after backend restart) and periodic 5-minute polling. Dismissing the toast allows it to reappear on the next check until the user actually reloads. Extends the Toast system with `persistent` flag, action buttons, and `'update'` type styling

## [v2.14.1] - 2026-02-18

### Fixed
- **TTS fails on long articles**: Increased TTS text limit from 15,000 to 50,000 characters — long review articles (e.g. drone roundups) no longer return 422 Unprocessable Entity
- **Maintenance page 403**: Moved `maintenance.html` to `/usr/share/nginx/html/` so nginx can serve it without traversing the user's home directory (was getting 403 Forbidden due to `700` perms on `/home/ec2-user`)

### Changed
- **Maintenance page auto-retry**: Page now counts down from 60 seconds and auto-reloads, in addition to the manual Retry button

## [v2.14.0] - 2026-02-18

### Added
- **Sample bots section**: Bots page now shows 8 pre-built bot templates (4 BTC + 4 USD) between the P&L chart and bot list — BB% Recovery, RSI Runner, AI Autonomous, and MACD Crossover strategies with real configs. View opens read-only modal, Copy pre-fills the create form. Collapsible with state saved in localStorage
- **Read-only modal mode**: BotFormModal now supports `readOnly` prop — disables all inputs via fieldset, hides validation, changes submit to "Close"

### Fixed
- **Changelog 401 error**: AboutModal used raw `fetch()` without JWT token to hit the auth-protected `/api/changelog` endpoint. Replaced with authenticated `api.get()` — changelog now loads correctly
- **Ship-it tag placement**: Tags were placed on dev branch commits before merging, causing `git describe` to show `vX.Y.Z-1-g<hash>` on main. Moved tag step to after merge so it lands on the merge commit. Fixed existing v2.13.0 tag

## [v2.13.0] - 2026-02-18

### Added
- **TTS volume slider**: Volume control in the TTS player settings dropdown — slider from 0-100% with mute/unmute toggle, persists across sessions via localStorage
- **Article playlist hover-to-scroll**: Hovering over articles in the TTS reading queue now scrolls to and highlights the article in the news list, automatically navigating to the correct pagination page if needed (matches video player behavior)
- **Persistent portfolio cache**: Portfolio data survives backend restarts via JSON file cache at `backend/.portfolio_cache/` — loads in ~1ms instead of re-fetching from Coinbase

### Changed
- **40x portfolio speed improvement**: Portfolio endpoint now uses Coinbase breakdown's built-in `total_balance_fiat` instead of making 30+ individual price API calls. Fresh fetch dropped from ~25s to ~0.6-1.4s
- **Sparkline charts 50% taller**: Dashboard carousel sparklines increased from 36px to 54px height, now pinned to card bottom with consistent positioning so eyes don't scan up and down when scrolling through cards

### Fixed
- **Dashboard/Bots portfolio skeleton stuck**: App header and Dashboard showed infinite pulsing grey boxes because the portfolio query was gated on `selectedAccount` (null during initial render). Added fallback to singular endpoint like Positions/Bots pages already use
- **Sparkline charts not rendering in PROD**: ResizeObserver never fired in production builds; replaced with `requestAnimationFrame` deferred mount

## [v2.12.5] - 2026-02-17

### Fixed
- **MFA mobile page eviction**: Switching to authenticator app on mobile caused the browser to evict the page from memory, losing MFA state and trapping users in a login loop. MFA challenge state now persists to `sessionStorage` (survives page reload, cleared on browser close)
- **News "1/500" on fresh mobile browsers**: Default category filter was `CryptoCurrency` only, so fresh browsers with no saved preferences saw nearly no articles. Default now selects all categories
- **Tab badges showed unfiltered count**: Article/video tab badges showed raw API total instead of filtered count, creating a confusing mismatch (e.g., badge "500" but only 1 article visible)

### Added
- **News retention info visible**: Pagination footer now shows "(last 14 days, min 5 per source)" so users understand the article retention policy. Backend includes `retention_days` in API response

## [v2.12.4] - 2026-02-17

### Fixed
- **Balances 500 error with multiple accounts**: `scalar_one_or_none()` crashed when a user had multiple active CEX accounts ("Multiple rows were found when one or none was required"). Added `.limit(1)` to 9 queries across 7 files — fixes "In Pos.", "In Grids", and "Available" columns showing "..." on the Active Deals page
- **Portfolio loading skeleton condition**: Changed from `isLoading && !portfolio` to `!portfolio` — React Query sets `isLoading=false` for disabled queries, so the skeleton never appeared when waiting for account selection

## [v2.12.3] - 2026-02-17

### Added
- **Service qualifier for bot.sh restart**: `--dev` restart now requires `--back-end`, `--front-end`, or `--both` to specify which service(s) to restart. Prevents unnecessary frontend restarts when only backend Python changed

### Fixed
- **Account Value loading skeleton**: Dashboard header and Account Value card now show animated pulse placeholders while portfolio data loads, instead of displaying misleading zeros
- **Rate limit messages include retry time**: All 4 rate limiters (login, signup, forgot-password, resend verification) now tell users exactly when they can try again ("Try again in X minutes") with standard `Retry-After` HTTP header

### Changed
- **Updated all documentation**: README.md, QUICKSTART.md, DEVELOPMENT_GUIDELINES.md, CLAUDE.md, and slash commands updated to reflect new `--back-end`/`--front-end`/`--both` syntax

## [v2.12.2] - 2026-02-17

### Fixed
- **"No accounts configured" on first login**: AccountProvider was mounted outside AuthProvider, so the accounts query fired before authentication completed. Moved AccountProvider inside the auth-gated content so accounts only fetch after login is confirmed
- **Account value slow to appear after login**: Portfolio query fired immediately with no selected account, hitting a legacy fallback endpoint, then re-fetching once accounts loaded. Added `enabled: !!selectedAccount` so portfolio only fetches after account selection — removes one wasted round-trip

## [v2.12.1] - 2026-02-17

### Fixed
- **Firefox silent WAV decode error**: Replaced 44-byte empty WAV (header only) with 844-byte WAV containing actual audio samples. Firefox requires real sample data to decode without `NS_ERROR_DOM_MEDIA_METADATA_ERR`
- **blob: ERR_FILE_NOT_FOUND on page refresh**: Delayed keepalive audio `src` assignment via `setTimeout(0)` so React Strict Mode cleanup can cancel it before the browser starts loading a blob URL that gets immediately revoked
- **WebSocket "closed before established" warning**: Delayed initial WebSocket connect via `setTimeout(0)` so React Strict Mode's immediate cleanup cancels the first attempt, preventing a connection that would be immediately closed

## [v2.12.0] - 2026-02-17

### Added
- **Mode-aware bot.sh restart**: `./bot.sh restart` now requires `--dev` or `--prod` flag. Manages nginx routing, frontend service, and backend as a single atomic operation
- **Mode-switch guard**: Warns when switching between dev/prod modes and requires `--force` to prevent accidental deployment changes ("Did you mean to switch to PROD deployment?")
- **Mixed-mode detection**: Detects inconsistent infrastructure state (e.g., nginx in dev but frontend service stopped) and warns on `restart` and `status`
- **Dynamic nginx discovery**: `bot.sh` searches standard nginx directories (`conf.d`, `sites-enabled`, `sites-available`) for the app's config — no hardcoded paths
- **Status enhancements**: `./bot.sh status` now shows current mode (DEV/PROD), nginx config path, and mixed-mode warnings

### Changed
- **All restart references in CLAUDE.md**: Replaced direct `systemctl` calls with `./bot.sh restart --dev/--prod`. The script is now the single source of truth for service management
- **`.gitignore` updated**: Added SQLite WAL files (`*.db-shm`, `*.db-wal`) and root-level cache files (`*_cache.json`)

## [v2.11.1] - 2026-02-17

### Fixed
- **Settings page slow to draw**: SQLite was using `delete` journal mode — reads blocked on writes from bot trading cycles. Switched to WAL mode (concurrent reads during writes). API response times dropped from 5-7s to sub-second
- **Coins endpoint hitting Coinbase API on every page load**: Added 10-minute cache for `/api/market-data/coins` — product listings rarely change. First hit from external API, subsequent hits from cache (5.3s → 4ms)
- **BlacklistManager blocking on slowest API call**: Split `Promise.all` into two phases — essential data (blacklist + categories) loads first and renders immediately, supplementary data (coins list + AI provider) loads in background. UI draws in ~0.2s instead of waiting 7.5s
- **database.py lint**: Reformatted all `DEFAULT_CONTENT_SOURCES` tuples to comply with 120-char line limit

## [v2.11.0] - 2026-02-17

### Added
- **Admin-only UI guards**: "AI Review" button (system-wide AI categorization) and "System Key" badges on AI providers are now hidden from non-superuser accounts. Regular users still see all providers and can manage their own API keys
- **Auth dependencies package** (`app/auth/`): Canonical home for `get_current_user`, `require_superuser`, `decode_token`, `get_user_by_id` — eliminates 57-module cascade load from router-level imports
- **Service layer extractions**: `ai_credential_service`, `settings_service`, `portfolio_service`, `news_fetch_service` — utility functions moved from routers to proper service layer
- **News data package** (`app/news_data/`): News models, sources, cache utilities, and debt ceiling data moved out of routers into dedicated data package
- **Paper trading validation**: Bot config validation now works for paper trading accounts using public market data

### Fixed
- **Settings 403 for non-admin users**: `GET /settings/{key}` was gated to superusers only — regular users couldn't load `decision_log_retention_days` on the Settings page. Changed to `get_current_user` (read access for all authenticated users, write remains admin-only)

### Changed
- **Import architecture overhaul**: Zero service→router imports remaining. All cross-package dependencies flow downward (auth → services → routers). ~3000 lines net reduction
- **`routers/__init__.py` gutted**: No longer eagerly imports 8+ routers — `main.py` imports each router directly
- **`main.py` cleanup**: All `noqa: E402` inline imports moved to top-level import section
- **Paper trading balance lookups**: `account_router.py` uses public market data API instead of requiring authenticated client for paper accounts
- **CLAUDE.md & whitebox command**: Added "do the right thing" and "no spaghetti code" architecture rules

### Removed
- **`routers/auth_dependencies.py`**: Replaced by `app/auth/dependencies.py` (all 30 consumers updated)
- **`routers/accounts/` subpackage**: Portfolio utils moved to `services/portfolio_service.py`
- **`routers/news/` subpackage**: Data files moved to `app/news_data/`

## [v2.10.1] - 2026-02-17

### Fixed
- **Empty article bodies (Yahoo Finance, etc.)**: aiohttp's default 8KB header limit rejected responses with large Set-Cookie headers (~27KB). Increased `max_field_size` to 32KB in article-content endpoint
- **"Invalid URI" console errors (Firefox)**: Replaced `audio.src = ''` and `removeAttribute('src')+load()` with a tiny silent WAV data URI to properly clear the audio element without triggering browser console errors
- **Keepalive audio cleanup**: Removed unnecessary `audio.src = ''` on unmount that triggered spurious errors

## [v2.10.0] - 2026-02-17

### Added
- **Gap Fill % condition type**: New bot condition that detects the percentage of synthetic/filler candles in a timeframe (0-100). Lets users block trades when data quality is poor (e.g., illiquid pairs where 50-80% of candles are synthetic)
- **Synthetic candle tagging**: `fill_candle_gaps()` now marks gap-filled candles with `_synthetic: True`; `aggregate_candles()` propagates synthetic counts through higher timeframes
- **Portfolio chart UX**: Escape key closes chart modal; click outside modal to close; resize observer keeps chart responsive

### Fixed
- **TEN_MINUTE timeframe extraction**: Added missing `"TEN"` prefix to indicator timeframe parsing — TEN_MINUTE conditions now work correctly
- **Paper trading candle order**: `PaperTradingClient.get_candles()` now reverses Coinbase API results to chronological order, matching `CoinbaseAdapter` behavior
- **Portfolio N+1 query**: Batch-fetch all position prices in parallel instead of sequential per-position API calls
- **News retention NULL handling**: `SQLite printf('-%d days', NULL)` returns `'-0 days'` not NULL — replaced `coalesce` with explicit `case()` for correct per-user retention
- **Deprecated `datetime.utcnow()`**: Replaced all remaining calls in news_router with `datetime.now(timezone.utc)`
- **Portfolio TypeScript**: Removed `as any` casts by adding `unrealized_pnl_usd` and `unrealized_pnl_percentage` to `Holding` interface
- **Account portfolio valuation**: Use public market data API (cached) instead of instantiating authenticated CoinbaseClient

### Changed
- **WebSocket routing in dev/prod commands**: `/ws` routes directly to backend (port 8100) instead of through Vite dev server — fixes fragile WebSocket proxying
- **Whitebox audit command**: Added "clean up dead code" rule
- **News article image endpoint**: Removed unnecessary auth requirement from `/api/news/image/{article_id}`

## [v2.9.6] - 2026-02-17

### Changed
- **Track `.claude/commands/`**: Removed blanket `.claude/` gitignore so slash command definitions (shipit, setdev, setprod, whitebox) are shared with other users
- **Updated `/shipit` command**: Added frontend deployment mode detection step and mode-aware deploy instructions

### Added
- **Coin icon cache gitignore**: `backend/coin_icons_cache/` now ignored (runtime-downloaded assets)
- **Whitebox audit command**: `.claude/commands/whitebox.md` — reusable slash command for structured security/performance audits

## [v2.9.5] - 2026-02-17

### Fixed
- **Carousel re-render storm**: Moved `liveDebt` (100ms) and `liveCountdown` (1s) timer state from parent into `USDebtCard` and `HalvingCard` — eliminates ~11 unnecessary re-renders/sec across all 14 cards
- **Deprecated `datetime.utcnow()`**: Replaced 3 calls with `datetime.now(timezone.utc)` in metric snapshot recording, pruning, and history queries
- **Prune on every read**: Metric snapshot pruning now guarded by 1-hour timestamp — no longer fires on every `/metric-history` request

### Changed
- **Monolith split**: `MarketSentimentCards.tsx` (1,948 lines) split into 17 individual card components in `components/cards/` with barrel export
- **Season detection extracted**: `determineMarketSeason` moved to `utils/seasonDetection.ts`; `useMarketSeason` hook updated to import from utility
- **Shared aiohttp session**: All 11 external API fetch functions now share a single `aiohttp.ClientSession` instead of creating per-request sessions
- **React.memo on all cards**: All 14 carousel card components wrapped in `React.memo` to prevent unnecessary re-renders
- **Resize debounce**: Carousel resize handler debounced with 150ms timeout
- **Fear/Greed color caching**: `getFearGreedColor()` result cached in variable instead of recalculated

### Added
- **Error states**: All cards accept `isError` prop and render `CardError` fallback when data fetch fails
- **Escape key handler**: `DebtCeilingModal` now closes on Escape key press

### Removed
- **Dead `funding_rates` code**: Removed `fetch_funding_rates()`, `/funding-rates` endpoint, and cache functions (CoinGlass API was non-functional)
- **Dead `exchange_flows` cache**: Removed `EXCHANGE_FLOWS_CACHE_FILE` and load/save functions (never used)

## [v2.9.4] - 2026-02-17

### Fixed
- **TTS memory leak**: Per-user semaphore dict now bounded (100 max, 1hr TTL) — prevents unbounded growth in multi-user environments
- **TTS duplicate generation**: Per-key dedup locks prevent concurrent requests from running edge-tts twice for the same article+voice
- **TTS bandwidth waste**: `/tts-sync` returns `audio_url` instead of base64 when `article_id` is provided — saves ~33% bandwidth and ~5MB peak RAM per request
- **Frontend memory triple-allocation**: Base64 audio decode now uses `atob()` + `Uint8Array` instead of `fetch(data:...)` which tripled peak memory
- **Stale word refs**: `wordRefs` array now reset at top of `renderedContent` useMemo — prevents stale DOM ref retention across article switches
- **Redundant import**: Removed duplicate `from sqlalchemy import delete` in TTS cleanup function

### Changed
- **Word click performance**: Replaced ~2000 per-word `onClick` closures with single event delegation handler via `data-tts-idx` attributes
- **TTS prefetch**: Next article's TTS is prefetched 5 seconds after playback starts, eliminating loading gaps between articles
- **New `/tts/prepare` endpoint**: Warms TTS cache without returning audio payload — used by frontend prefetch

### Added
- **`/whitebox` custom command**: Reusable audit command that bakes in standing assumptions about multi-user, security, performance, and code quality

## [v2.9.3] - 2026-02-17

### Fixed
- **Recharts width/height warnings (proper fix)**: Sparkline defers `ResponsiveContainer` render via `ResizeObserver` until parent has real dimensions — eliminates all 24 width(-1)/height(-1) warnings from off-screen cards in horizontal scroll

## [v2.9.2] - 2026-02-17

### Fixed
- **Recharts width(-1) warning**: Added `minWidth={1}` alongside `minHeight={1}` on all `ResponsiveContainer` components — both dimensions needed to suppress the warning during initial render

## [v2.9.1] - 2026-02-17

### Fixed
- **Recharts width/height -1 warnings**: PnLChart container changed from `min-h-[300px]` to explicit `h-[300px]`; added `minHeight={1}` to all `ResponsiveContainer` components in PnLChart and Sparkline

### Added
- **Debt ceiling countdown**: US National Debt card now shows countdown to when debt hits the ceiling, or time since exceeded if already past

## [v2.9.0] - 2026-02-17

### Added
- **TTS caching system**: Article TTS audio cached to disk and DB (`article_tts` table), shared across users — no re-generation for same article+voice
- **TTS history tracking**: `user_article_tts_history` table records last-used voice per article per user for auto-resume
- **Voice subscription preferences**: `user_voice_subscriptions` table for per-user voice enable/disable
- **TTS serve endpoint**: `GET /tts/audio/{article_id}/{voice_id}` serves cached MP3 files directly
- **Article source_id FK**: `news_articles` and `video_articles` now have `source_id` FK to `content_sources` for proper relational lookups (backfilled on migration)
- **Source subscription enhancements**: `user_category` (per-user category override) and `retention_days` (visibility filter) columns on `user_source_subscriptions`
- **Domain blacklist service**: New `domain_blacklist_service.py` for URL domain filtering
- **URL utilities**: New `url_utils.py` for URL normalization and validation
- **Custom commands**: `/shipit` (full release process), `/setdev` (switch to Vite dev mode), `/setprod` (switch to production dist/ mode)

### Fixed
- **S1: Voice path traversal**: Voice parameter validated against `TTS_VOICES` keys before filesystem use — rejects unknown voices with 400
- **S2: Path containment escape**: `serve_tts_audio` verifies resolved path stays within `TTS_CACHE_DIR` — blocks DB-driven path traversal
- **R1: TTS race condition**: `IntegrityError` caught in `_get_or_create_tts` — concurrent requests for same article+voice no longer cause 500 errors
- **R2: Rate parameter injection**: Strict regex validation (`^[+-]\d{1,3}%$`) rejects malformed rate strings like `+abc%`
- **Q1: Deprecated datetime**: `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` in TTS history

### Changed
- **O(1) word highlighting (MiniPlayer)**: Removed `currentWordIndex` from `renderedContent` useMemo deps; highlighting via direct DOM class toggle instead of rebuilding 1000+ spans per word
- **O(1) word highlighting (ArticleContent)**: Same DOM-based pattern — `useEffect` toggles highlight classes on prev/current word refs
- **Source subscriptions modal**: Enhanced with category/retention controls
- **News router**: Extended with source_id-aware queries and domain blacklist integration
- **Sources router**: Enhanced subscription management with category and retention support

## [v2.8.0] - 2026-02-17

### Fixed
- **Article cache race condition**: Added `asyncio.Lock` to prevent `KeyError` during concurrent cache eviction
- **Auto-buy monitor broken**: `PendingOrder` usage had wrong field names and missing columns — replaced with in-memory `AutoBuyPendingOrder` dataclass so repricing actually works
- **Broadcast crash**: `sell_executor`/`buy_executor` called non-existent `broadcast_position_update()` — fixed
- **Gemini AI race condition**: Fixed in AI service credential lookup

### Added
- **Auth on all news endpoints**: All 23 previously unprotected news/metrics endpoints now require authentication — unauthenticated scraping no longer possible
- **Per-user TTS semaphore**: TTS concurrency limited to 1 per user (nested inside global limit of 3) — one user can no longer starve others
- **Admin-gated endpoints**: Settings, seasonality, blacklist categories, template seed-defaults, strategy, monitor/shutdown/pair-sync all require superuser
- **ContentSource ownership**: Added `user_id` column + ownership check on delete
- **Per-user AI credentials**: AI service looks up credentials per-user via `AIProviderCredential`
- **Migration: content_source_user_id**: Adds `user_id` column to `content_sources`

### Changed
- **news_router modularized**: Split 2700-line `news_router.py` into 3 files — `news_router.py` (articles/videos), `news_metrics_router.py` (market metrics), `news_tts_router.py` (TTS)
- **Frontend auth enforcement**: 23 `fetch()` calls switched to `authFetch()` across MarketSentimentCards, useNewsData, useMarketSeason
- **Context memoization**: `ArticleReaderContext` value wrapped in `useMemo` — eliminates unnecessary 4Hz re-renders
- **MiniPlayer performance**: Constants moved to module scope; progress bar uses ref pattern for stable `useEffect` deps
- **Order reconciliation scoped**: `OrderReconciliationMonitor` and `MissingOrderDetector` scoped by `account_id`
- **Balance API scoped**: `account_id` passed to all `get_accounts()`/`get_btc_balance()` calls
- **Per-instance rate limiter**: No more cross-user API throttling
- **Market data**: Prefers system/public credentials over random user account
- **Bull flag scanner**: `BlacklistedCoin` query scoped to global + user

### Removed
- Dead `order_monitor.py` (231 lines), `SyncedArticleReader` component, `useTTS` hook, dead `calculate_available_balance`, dead `limit_order_monitor` methods

## [v2.7.0] - 2026-02-17

### Fixed
- **Order history data leak**: All 4 endpoints now filter by `Bot.user_id == current_user.id` — previously any user could see all orders
- **Perps position ownership**: `modify_tp_sl()` and `close_perps_position()` now verify position belongs to current user via account ownership chain — previously any user could modify/close any position by ID
- **Scanner logs data leak**: All 3 scanner log endpoints now filter by bot ownership
- **Signals data leak**: `GET /api/signals` now scoped to current user's positions via account chain — previously returned all users' signals
- **News cleanup unauthenticated**: `POST /api/news/cleanup` now requires authentication — previously anyone could purge the news cache
- **Account balance data leak**: `GET /account/balances` now filters by `Account.user_id` in both specified and default account branches
- **Bot name uniqueness**: Changed from global unique to per-user unique via composite constraint `(user_id, name)` — different users can now have bots with the same name
- **Delisted pair monitor hardcoded account**: Replaced `Account.id == 1` with dynamic query for any active CEX account

### Added
- **Migration: bot_name_per_user_unique**: Drops global unique index on `bots.name`, creates composite unique index on `(user_id, name)`

### Changed
- **Architecture docs**: Documented multi-user hardening patterns and ownership chain

## [v2.6.0] - 2026-02-17

### Changed
- **bot_products junction table**: Extracted `bots.product_ids` JSON array into a normalized `bot_products` table with proper indexes; enables SQL queries like "find all bots trading ETH-BTC" without JSON parsing
- **bot_template_products junction table**: Same normalization for bot templates
- **Bot.get_trading_pairs()**: Now reads from junction table instead of JSON column
- **News images moved to filesystem**: Article thumbnails stored as WebP files in `backend/news_images/` instead of base64 blobs in the database; reduces DB bloat by ~50MB
- **News image serving**: `/api/news/image/{id}` now serves from filesystem; cleanup also deletes orphaned image files
- **Bot CRUD operations**: Create, update, clone, and copy-to-account all sync `bot_products` junction table rows

### Added
- **Migration: extract_bot_products**: Creates `bot_products` and `bot_template_products` tables, populates from existing JSON data
- **Migration: move_news_images_to_filesystem**: Extracts base64 `image_data` from `news_articles` to `backend/news_images/` directory

## [v2.5.0] - 2026-02-17

### Added
- **Per-user coin category overrides**: Users can override the global AI-generated coin category (APPROVED/BORDERLINE/QUESTIONABLE/BLACKLISTED) for themselves; overrides are marked with an asterisk (*) in the UI
- **Override API endpoints**: `GET/PUT/DELETE /api/blacklist/overrides/{symbol}` for managing per-user overrides
- **Public market data fallback**: Paper trading and market data endpoints now fall back to Coinbase public API (no auth required) when no user credentials are available
- **Multi-user audit plan**: Comprehensive audit document (`MULTI_USER_AUDIT_PLAN.md`) tracking all data isolation work across 5 phases

### Changed
- **Multi-user data isolation (Phases 1-5)**: All user-facing queries now scoped by `user_id` or `account_id` — positions, trades, portfolio, dashboard stats, bots, WebSocket notifications, and balance caches are fully isolated between users
- **Balance cache keys scoped by account_id**: Cache keys like `balance_eth`, `aggregate_btc_value` now include account_id suffix (e.g., `balance_eth_3`) to prevent cross-user cache pollution
- **Aggregate BTC position query scoped**: `calculate_aggregate_btc_value()` now JOINs through bots table to scope positions to the correct account
- **Hardcoded DB path removed**: `account_balance_api.py` now uses `os.path.dirname` instead of `/home/ec2-user/...`
- **WebSocket manager user-scoped**: Connections stored as `(websocket, user_id)` tuples; `broadcast_order_fill` routes notifications only to the owning user
- **Portfolio/account queries strictly scoped**: Removed legacy `account_id IS NULL` fallbacks in `portfolio_utils.py` and `accounts_router.py`
- **Signal processor override-aware**: Buy decisions check per-user coin category overrides before falling back to global entries
- **Bot monitor category filtering**: `filter_pairs_by_allowed_categories()` now respects per-user overrides via `user_id` parameter
- **Paper trading client**: All 10 fallback methods now use public API instead of system credentials
- **Blacklist list endpoint**: Returns `user_override_category` field when current user has an override

### Fixed
- **Cross-user balance cache pollution**: User A's cached balances could be returned for User B (critical multi-user bug)
- **Unscoped position queries**: Dashboard stats, trades, portfolio PnL, and bot budget pre-fetch now filtered to current user's accounts
- **`get_coinbase_from_db()` not user-scoped**: Bot CRUD and validation routers now pass `user_id` to get the correct user's exchange client

## [v2.4.0] - 2026-02-16

### Added
- **Multi-method MFA**: Users can now choose between authenticator app (TOTP), email verification code, and email verification link for two-factor authentication
- **Email MFA login flow**: Login sends a styled HTML email with both a 6-digit code and a clickable "Verify Login" link; either completes the MFA challenge
- **Tabbed MFA UI on login**: When multiple MFA methods are enabled, login shows Authenticator / Email Code / Email Link tabs — only one method needs to succeed
- **Email MFA settings toggle**: Enable/disable email MFA independently from TOTP in Settings, with password confirmation and mutual-exclusion guard (can't disable your last MFA method)
- **MFA email resend**: "Resend code" button with 60-second cooldown during login MFA challenge
- **`/mfa-email-verify` route**: Handles email link clicks — auto-verifies and redirects to dashboard
- **Resend MFA email endpoint**: `POST /api/auth/mfa/resend-email` invalidates old tokens and sends fresh code+link
- **MFA encouragement updated**: Now mentions both authenticator app and email verification as options

### Changed
- **Login response**: Now includes `mfa_methods` list (e.g. `["totp", "email_code", "email_link"]`) so frontend knows which tabs to show
- **Device trust helper extracted**: `_create_device_trust()` shared across all MFA verify endpoints (DRY)
- **Trusted devices section**: Now visible when any MFA method is enabled (not just TOTP)
- **MFA encouragement gate**: Checks both `mfa_enabled` and `mfa_email_enabled` before showing encouragement screen

## [v2.3.0] - 2026-02-16

### Added
- **HTTPS domain access**: App publicly accessible at `https://tradebot.romerotechsolutions.com` via Nginx reverse proxy with Let's Encrypt SSL (auto-renewing)
- **TOTP MFA (Two-Factor Authentication)**: Authenticator app support (Google Authenticator, Authy, etc.) with QR code setup, manual key entry, and encrypted secret storage (Fernet)
- **MFA login flow**: Two-step login — password then 6-digit TOTP code — with auto-focus, numeric input, and "Back to login" escape
- **Remember device for 30 days**: Optional checkbox during MFA login stores a device trust token, skipping MFA on subsequent logins from the same browser
- **Trusted device management**: Settings page shows all trusted devices with browser/OS name, IP geolocation (city, state, country), and date added; individual or bulk revocation
- **Login page branding**: Subtle gradient accents, feature highlights (Automated Trading, AI Analysis, Grid Strategies), and polished card styling
- **Public signup disabled**: Registration locked down; new users created by admin only via `POST /api/auth/register`

### Infrastructure
- **Route53 DNS**: A record `tradebot.romerotechsolutions.com` -> EC2 (54.226.70.55)
- **EC2 security group**: Ports 80 and 443 opened for HTTP/HTTPS
- **Nginx**: Installed and configured as reverse proxy to localhost:8100, with WebSocket upgrade support
- **Certbot**: SSL certificate obtained and auto-renewal configured

## [v2.2.0] - 2026-02-16

### Added
- **Production frontend build**: Frontend now built with `vite build` and served by FastAPI backend — eliminates React dev-mode overhead that caused `DataCloneError: out of memory` (tab crashes on iPad/mobile during overnight TTS playback)
- **TTS session resilience**: Wake Lock API keeps screen awake during playback, silent audio keepalive prevents browser from discarding tab, session auto-resumes from localStorage after tab kill
- **Article reader UI improvements**: Full-screen mode on mobile, pinned image with blurred background fill (YouTube-style), pinned article info section with gradient separator, fade-out edges on scrollable text
- **Child voice content filter**: Expanded adult content keywords from ~25 to ~90+ covering sexuality, guns/weapons, alcohol, smoking/tobacco, drugs, and violence

### Changed
- **Single-service deployment**: Backend serves the production frontend bundle — `trading-bot-frontend` systemd service no longer needed
- **`bot.sh` production awareness**: Detects production build (`frontend/dist/index.html`) and skips frontend service operations
- **`update.py` builds frontend**: Automatically runs `vite build` when frontend changes are detected during updates
- **Badge polling reduced**: Closed/failed position badge queries reduced from 10s to 60s
- **News page size reduced**: Article fetch reduced from 10,000 to 500 per request
- **Slider-vertical fix**: MiniPlayer volume slider uses `direction: 'rtl'` instead of deprecated `-webkit-appearance: slider-vertical`
- **WebSocket cleanup fix**: NotificationContext properly detaches handlers before closing to prevent StrictMode reconnection cascade

### Removed
- **Vite client strip plugin**: No longer needed — production build doesn't include `/@vite/client`
- **HMR disable setting**: No longer needed — production build has no HMR
- **Page reload diagnostics**: Investigation scaffolding removed (DIAG_KEY, logDiag, /api/diag endpoint)
- **Root health check route**: Moved from `/` to `/api/` only, so SPA catch-all can serve frontend at root

## [v2.1.1] - 2026-02-16

### Fixed
- **TTS article reading interrupted by auth logout**: The 401 interceptor immediately cleared all tokens (including refresh token) and forced logout on any expired access token. Now attempts a token refresh first, with a mutex to prevent concurrent refresh races. This was the primary cause of "page refreshes" during long listening sessions.
- **TTS article reading interrupted by refetch cascades**: MarketSentimentCards had 23 React Query hooks refetching every 5-15 minutes regardless of user engagement, causing re-render cascades that disrupted TTS playback. All refetch intervals now pause when the user is actively listening to articles.

### Changed
- **Mobile header redesign**: Separate mobile/desktop header layouts for a cleaner design
  - Row 1: Brand + version (left), Account Value (right)
  - Row 2: Season indicator, Live/Paper toggle, Account Switcher, Logout — all equal-height pills with consistent styling
  - BTC/ETH prices hidden on mobile, version link visible and tappable
- **Consistent header control sizing**: Season badge, Paper Trading toggle, Account Switcher, and Logout button now share matching border-radius (`rounded-lg`), padding, and icon sizes across mobile and desktop
- **Season indicator visible on all screen sizes**: Previously hidden below `lg` breakpoint, now shown on mobile (in controls row) and tablet (in right-side controls)

## [v2.1.0] - 2026-02-16

### Added
- **Mobile-responsive layouts**: Full mobile-friendly UI across all pages and components (21 files updated)
  - **App shell**: Header hides Paper Trading toggle and Account Switcher on mobile; nav separator hidden on small screens
  - **Dashboard**: Projection table columns hidden on mobile, PropGuard grid stacks to single column, recent deals wrapped in overflow scroll
  - **Positions**: Balance panel tightens column widths and hides "In Grids" on mobile; action buttons wrap
  - **Bots**: Bot table hides non-essential columns on mobile; header buttons wrap
  - **Portfolio**: Hides Balance and Price columns on mobile for clean 4-column layout
  - **Charts**: Toolbar separators hidden on mobile; chart type and time interval buttons wrap
  - **History**: Trade history grid wraps on mobile; pagination controls wrap
  - **News**: Article and video grids transition to 2-column at smaller breakpoint
  - **Mini players**: Both article reader and video mini players now stack progress bar above centered buttons on mobile with auto-height; expanded mode stacks controls vertically
  - **Market sentiment carousel**: Responsive card count (1 on mobile, 2 on tablet, 3 on desktop) with resize listener
  - **Modals**: All modals use full-width on mobile with proper margin; internal grids stack to single column
  - **Charts**: PnL chart stats stack above chart on mobile; Account Value chart header and time buttons wrap

## [v2.0.1] - 2026-02-16

### Fixed
- **PropGuard fail-safe on DB unavailability**: `_load_state()` and `_snapshot_daily_start()` now raise RuntimeError on database failures, blocking all orders rather than silently allowing them through
- **WS equity staleness detection**: PropGuard now rejects WebSocket equity data older than 60 seconds and falls back to REST, with NaN/Inf guard on equity values
- **WS staleness check in monitor**: PropGuard background monitor now applies the same 60-second staleness check as the order preflight path
- **Exchange client cache cleanup**: Shutdown handler now properly closes all cached exchange clients (fixes httpx connection leak for MT5), and `clear_exchange_client_cache(None)` now closes clients before clearing
- **Missing null checks on exchange client**: Added null checks for `get_exchange_client_for_account()` in `bot_control_router` and `account_router` portfolio conversion
- **API key encryption for all exchanges**: `api_key_name` is now encrypted at rest for Coinbase accounts (was only encrypted for ByBit), decrypted on use, and masked in API responses
- **Frontend account validation**: Bot form now validates account selection before submission; AddAccountModal validates required credentials for ByBit, MT5, and Coinbase
- **PropGuardStatus 404 handling**: Frontend now treats 404 as "not initialized" instead of showing an error state
- **TradingView ByBit symbol mapping**: Correctly maps internal `-USD` suffix back to `-USDT` for ByBit charts on TradingView

## [v2.0.0] - 2026-02-16

### Added
- **Multi-Exchange Architecture**: ByBit V5 (HyroTrader) and FTMO MT5 Bridge exchange adapters implementing the ExchangeClient interface — ZenithGrid is no longer Coinbase-only
- **PropGuard Safety Middleware**: Real-time drawdown monitoring decorator that wraps any exchange client with pre-flight safety checks (daily/total drawdown limits, spread guard, volatility buffer, kill switch)
- **ByBit WebSocket Manager**: Real-time position, order, wallet, and ticker streams via pybit for sub-second equity monitoring
- **PropGuard Background Monitor**: Async service running every 30s to check all prop firm accounts, update equity state, and trigger kill switch on drawdown breach
- **PropGuard API Endpoints**: GET status, POST reset kill switch, POST manual emergency kill, GET history (`/api/propguard/{account_id}/...`)
- **PropGuard Status Widget**: Frontend dashboard card with live equity, color-coded daily/total drawdown progress bars, and manual kill/reset controls
- **Prop firm badges** on account cards in Settings showing firm name (HyroTrader/FTMO)
- **Database schema**: `prop_firm_state` table and 5 new columns on `accounts` (prop_firm, prop_firm_config, prop_daily_drawdown_pct, prop_total_drawdown_pct, prop_initial_deposit)
- **Account creation UI**: Exchange dropdown (Coinbase/ByBit/MT5 Bridge) with conditional fields per exchange type, prop firm dropdown, drawdown configuration with input validation
- **ByBit global rate limiter**: 100ms minimum spacing between ByBit API calls via async lock to prevent rate limit violations
- Added `pybit>=5.8.0` dependency for ByBit V5 API integration

### Changed
- Exchange factory now accepts `exchange_name` parameter to route to ByBit/MT5 adapters (backwards-compatible, defaults to Coinbase)
- Exchange service wraps clients with PropGuard decorator when `account.prop_firm` is set
- ByBitAdapter wraps order responses in Coinbase-compatible `success_response` format for consistent parsing by buy/sell executors
- ByBit `from_bybit_symbol()` maps USDT→USD so products appear as standard `-USD` pairs system-wide
- ByBitAdapter `calculate_aggregate_btc_value()` and `calculate_aggregate_usd_value()` use `totalEquity` (includes unrealized PnL)
- TradingClient buy/sell/get_balance now support USDT and USDC quote currencies alongside USD and BTC
- Order validation parameter renamed from `coinbase_client` to `exchange` for exchange-agnostic clarity
- Candle data reversal moved into each adapter's `get_candles()` — each adapter returns chronological (oldest-first) order
- Multi-bot monitor candle cache now keyed by account_id to prevent cross-account data bleed
- Missing order detector now checks all active accounts instead of only account_id=1
- Order reconciliation monitor iterates all active accounts for startup reconciliation
- Bot creation/update budget validation now uses `get_exchange_client_for_account()` instead of Coinbase-only factory calls
- Grid order fill handler uses bot's `account_id` to get correct exchange client
- Account creation validates exchange names, prop firm names, and bridge URLs (SSRF prevention)
- ByBit API keys encrypted at rest during account creation and update
- Exchange config changes trigger client cache invalidation (including monitor cache)
- Indicator-based strategy removes hardcoded 0.0001 BTC minimum floor — exchange-specific minimums enforced by order_validation at execution time
- ByBitAdapter `cancel_order()` falls back to order history when order not found in open orders
- ByBitAdapter `list_products()` and `get_product()` return Coinbase-compatible field aliases (`base_currency_id`, `quote_currency_id`, `display_name`) and normalized `"online"` status
- TradingView chart modal uses exchange-specific symbol prefix
- Frontend `authFetch()` used for all account management API calls (update, delete, setDefault)
- INTX perps section hidden for non-Coinbase accounts
- Fee-adjusted profit multiplier accepts optional `exchange` parameter
- Replaced Coinbase-specific error messages in buy/sell executors with exchange-agnostic wording

### Fixed
- **CRITICAL**: Infinite recursion in ByBit rate limiter — `_rate_limited_call()` was calling itself instead of `asyncio.to_thread()`
- **CRITICAL**: Bot creation/update called `create_exchange_client(db, account_id)` with wrong signature — would crash for all exchanges
- **CRITICAL**: ByBit buy orders treated as failures because buy_executor expected Coinbase's nested `success_response.order_id` format
- **CRITICAL**: ByBit `get_order()` missing `total_fees` field — fee calculation defaulted to zero
- **CRITICAL**: PropGuard safety blocks not detected by trading engine — now raise clear `PropGuard blocked:` errors
- **CRITICAL**: ByBit `cancel_all_orders()` failed for linear category — now passes `settleCoin="USDT"` as required by ByBit V5 API
- Fixed wrong Trade model field names in `execute_sell_short()` and `execute_buy_close_short()` — used nonexistent `size`/`filled_value`/`commission`/`executed_at` instead of `base_amount`/`quote_amount`/`timestamp`
- Fixed `sell_executor.execute_sell_short()` calling `validate_order_size()` without `await` and with wrong argument order
- Fixed grid order fill handler querying random active account instead of using bot's `account_id`
- Fixed limit order monitor `list_orders()` expecting dict wrapper instead of direct list return
- Fixed missing order detector removing unsupported `start_date` kwarg from `list_orders()` call
- Added USDT/USDC to order validation `DEFAULT_MINIMUMS` fallback (10 USDT min notional)
- Added `quote_min_size` (from ByBit `minNotionalValue`) to ByBitAdapter product responses
- Removed unused variable warnings from sell_executor and order_reconciliation_monitor

## [v1.31.13] - 2026-02-15

### Changed
- Moved Perpetual Futures portfolio linking from standalone Settings card into expandable per-account row in Centralized Exchanges section — each CEX account now shows its own perps status inline
- Perps portfolio fields (UUID, leverage, margin type) now included in accounts API response, eliminating extra API calls

### Fixed
- Fixed `link-perps-portfolio` endpoint passing wrong arguments to `get_coinbase_for_account()`

## [v1.31.12] - 2026-02-15

### Added
- Budget rejection events (insufficient funds, below exchange minimum) now appear on the History page's Failed Orders tab, not just in indicator logs
- Deduplication prevents repeated identical failed order entries for the same deal — a new entry is only logged when the error message changes

## [v1.31.11] - 2026-02-15

### Fixed
- Fixed `max_quote_allowed` set to raw per-position budget ceiling instead of actual expected deal cost when `auto_calculate_order_sizes=True`, causing misleading budget utilization percentages (e.g., 87% instead of ~100%)
- Fixed `calculate_max_deal_cost()` not accounting for `auto_calculate_order_sizes` flag — when enabled with fixed safety order type, safety orders now correctly equal base order size (matching actual trading logic in `indicator_based.py`)

## [v1.31.10] - 2026-02-15

### Fixed
- Fixed crossing conditions (bb_percent, MACD, etc.) being detected but not triggering trades — `analyze_signal()` results were discarded and conditions re-evaluated after previous indicators had already been updated, causing crossing events to be consumed before `process_signal()` could act on them

## [v1.31.9] - 2026-02-15

### Fixed
- Fixed safety order "Insufficient balance" errors caused by negative available balance calculation — when a position already exists, budget is now calculated from the position's own `max_quote_allowed` instead of pair-level budget which could over-subtract across multiple positions

## [v1.31.8] - 2026-02-15

### Fixed
- Updated `docs/architecture.json` version from v1.31.4 to v1.31.8
- Added missing `routers/auth_dependencies.py` to architecture.json routers section
- Added missing `components/news/newsUtils.tsx` to architecture.json sub_components section

## [v1.31.7] - 2026-02-15

### Fixed
- Fixed circular import in `routers/__init__.py` that prevented backend startup after `__pycache__` cleanup

### Removed
- Deleted 7 stale docs/ files (ARBITRAGE_PLATFORM_HANDOFF, CANDLE_FETCH_OPTIMIZATION_PLAN, COMPLETE_DOCUMENTATION, DEVELOPMENT_ROADMAP, LIMIT_ORDERS_TODO, PROJECT_OVERVIEW, TODO_MIN_PROFIT_GUI_DISPLAY)

### Changed
- Rewrote `docs/CONDITIONAL_STRATEGY.md` — reflects completed system with all operators (INCREASING/DECREASING), all indicators (AI_BUY/AI_SELL/BULL_FLAG/VOLUME_RSI), phase-based conditions
- Rewrote `docs/USER_GUIDE_CONDITIONAL_STRATEGY.md` — updated strategy name, phase-based conditions, correct JSON format, new operators and indicators
- Rewrote `docs/QUICKSTART.md` — correct ports, systemd instructions, setup.py workflow, removed MACD-centric content
- Rewrote `docs/DEVELOPMENT_GUIDELINES.md` — correct file paths, current architecture patterns, removed stale TODOs
- Updated `docs/FEATURE_CHECKLIST.md` — marked 50+ completed features (grid trading, paper trading, bidirectional, AI providers, notifications, security hardening, etc.)
- Updated `README.md` — fixed broken doc links, corrected strategy listing
- Updated `COMMERCIALIZATION.md` — marked Phase 1 items as complete

## [v1.31.6] - 2026-02-15

### Removed
- Deleted 18 stale root-level markdown files (completed migration plans, session handoffs, status reports) — all preserved in git history

### Changed
- Moved `AUTO_CALCULATE_BUDGET_LOGIC.md` and `SECURITY_AUDIT_v1.31.0.md` to `docs/` folder

## [v1.31.5] - 2026-02-15

### Added
- `docs/architecture.json` — Machine-readable catalog of all backend and frontend modules
- `docs/ARCHITECTURE.md` — Mermaid diagrams (system overview, backend layers, frontend layers, trading flow, data model) plus prose on auth, multi-tenancy, and background tasks

## [v1.31.4] - 2026-02-15

### Changed
- Removed dead commented-out code: `AuthTokens` interface in AuthContext.tsx, GALA mapping in dex_wallet_service.py
- Updated news_router.py docstring to reference dynamic news_sources.py config instead of hardcoded source list
- Fixed stale TODO comments in buy_executor.py and sell_executor.py (limit order tracking is implemented)
- Clarified TODO comments for short order limit logic (buy_executor, sell_executor)
- Removed obsolete `TODO: Support multiple exchange accounts per user` from order_monitor.py (Account model exists)
- Fixed inconsistent section numbering in BotFormModal.tsx (dropped numbers, kept descriptive names)
- Added explanatory comment for 3Commas-style DCA ladder calculation in ThreeCommasStyleForm.tsx
- Added explanatory comment for PnL carousel infinite-scroll pattern in BotListItem.tsx
- Added BUG comment flagging broken user credential lookup in ai_service.py (uses nonexistent User attrs)
- No behavioral changes — all fixes are comment/docstring only

## [v1.31.3] - 2026-02-15

### Changed
- Fixed all 175+ Python flake8 lint issues across 50 files (zero remaining)
- Fixed all 7 frontend TypeScript errors (zero remaining)
- Sorted imports with isort on all modified files
- Removed dead code: shadowed method definitions in PaperTradingClient, unused variables, unused imports
- Replaced bare `except:` with `except Exception:` (E722)
- Changed SQLAlchemy `== True/False` comparisons to idiomatic `.is_(True)/.is_(False)` (E712)
- Fixed f-strings without placeholders, ambiguous variable names, whitespace formatting
- Removed unused `global` declarations that only read (never assigned) module-level variables
- Added `logger` definition to exchange_clients/base.py (was undefined)
- Fixed PnLChart.tsx to use correct field names (`cumulative_pnl_usd` instead of `cumulative_pnl`)
- No behavioral changes — all fixes are mechanical/cosmetic

## [v1.31.2] - 2026-02-15

### Changed
- Codebase housekeeping: deleted 16 stale markdown docs, 17 duplicate/obsolete scripts from backend
- Removed unused arbitrage package (stat_arb_analyzer, triangular_detector) and empty bot_monitoring module
- Removed unused FundingRatesResponse type from frontend
- Replaced duplicate SELL_FEE_RATE constant in TradingViewChartModal with import from positionUtils
- Removed ~20 debug console.log statements from frontend (useIndicators, DealChart, Charts, ClosedPositions)
- Downgraded WebSocket lifecycle logs from console.log to console.debug in NotificationContext
- Moved 4 useful scripts (clean_slate, sell_all_simple, check_all_accounts, update_trade_fills) to backend/scripts/

### Fixed
- get_coinbase() in dependencies.py, settings_router.py, and system_router.py now filters by authenticated user's account (was grabbing first account in DB regardless of user — critical for multi-user support)
- Removed stale "TODO: Once authentication is wired up" comments (auth has been wired up since v1.31.0)

## [v1.31.1] - 2026-02-15

### Changed
- Remove dead `get_current_user_optional` from auth_dependencies.py and auth_router.py
- Add Query bounds (ge/le) on all paginated limit parameters to prevent abuse
- Sanitize remaining `str(e)` in error responses across templates, news, and trading routers

### Fixed
- Removed console.log that leaked wallet_private_key in BotFormModal
- Sanitized WebSocket console.log to not expose JWT token or message payloads
- Fixed broken slippage-check fetch in helpers.ts (wrong env var → authFetch)
- Closed positions page now correctly fetches up to 500 results (was broken by undefined base URL)

### Security
- Added security headers middleware (X-Frame-Options: DENY, X-Content-Type-Options: nosniff, X-XSS-Protection, Referrer-Policy)
- File permissions hardened: .env, trading.db, and backups set to 600
- Added DB-level unique index migration for bot names to prevent race conditions
- All query limit parameters now bounded to prevent DoS via unbounded result sets

## [v1.31.0] - 2026-02-15

### Added
- Fernet encryption for API keys at rest (exchange credentials + AI provider keys)
- `authFetch()` helper and exported `api` instance for centralized authenticated HTTP calls
- WebSocket authentication via JWT query parameter
- Login rate limiting (5 attempts per 15 minutes per IP)
- Password strength requirements (min 8 chars, uppercase, lowercase, digit)
- JWT secret startup validation (refuses to start with default/empty secret)
- Auto-generate `JWT_SECRET_KEY` and `ENCRYPTION_KEY` in `setup.py`

### Changed
- Enforce authentication on all protected API endpoints (100% coverage)
  - Backend: all bot, position, settings, system, order history, strategies, scanner logs, validation, and limit order endpoints now require JWT
  - Only intentionally public endpoints remain unauthenticated (market data, candles, news, coin icons, auth)
- Frontend: eliminate all bare `axios` imports in favor of auth-enabled `api` instance
  - Fixed 13 frontend files using raw `fetch()` or bare `axios` that bypassed auth headers
  - Affects: LimitCloseModal, PositionCard, usePositionMutations, PerpsPortfolioPanel, Portfolio, Settings, useValidation, useBotsData, useChartsData, usePositionsData, DealChart, DepthChart, useChartData
- Tighten CORS (explicit methods/headers instead of wildcards)
- Sanitize error responses (generic messages instead of leaking internal exceptions)

### Fixed
- Portfolio page "Failed to fetch portfolio" error caused by missing auth headers on auto-refresh
- PnL chart showing "No closed positions yet" due to unauthenticated `/api/positions/pnl-timeseries` call
- AISentimentIcon causing continuous 401 errors every 30 seconds
- Path traversal vulnerability in coin icons endpoint
- Debug print statements leaking JWT tokens in `coinbase_api/auth.py`

### Security
- Every non-public endpoint now returns 401 without valid JWT token
- API keys encrypted at rest using Fernet symmetric encryption
- Credential decryption at all read points (exchange client, AI service, settings)
- `.env.bak*` patterns added to `.gitignore` to prevent accidental secret commits

## [v1.30.1] - 2026-02-15

### Fixed
- Widen bot edit modal (max-w-2xl → max-w-4xl) to fit volume/RSI indicator fields without horizontal scrolling

## [v1.30.0] - 2026-02-15

### Added
- Coinbase INTX perpetual futures support: API layer, bracket TP/SL orders, position monitoring
- Futures bot configuration: leverage (1-10x), margin type (Cross/Isolated), TP/SL percentages, direction
- Perps portfolio linking in Settings (discovers INTX portfolio UUID)
- Futures position display: leverage badge, liquidation price, TP/SL, unrealized PnL, funding fees
- Perps portfolio panel: margin balance, open positions summary
- Backend endpoints for perps products, portfolio, positions, modify TP/SL, close position
- Database migration for perpetual futures fields (accounts, bots, positions)

## [v1.29.0] - 2026-02-14

### Added
- CHANGELOG.md
- Min volume filter UI for bot configuration
- Increasing/decreasing operators for indicators

## [v1.28.2] - 2026-02-14

- Remove 6 PnL cards from Portfolio page

## [v1.28.1] - 2026-02-14

- Remove Portfolio Totals from Bots page (moved to Dashboard)

## [v1.28.0] - 2026-02-14

- Fix bot toggle switch, add Portfolio Totals to Dashboard, add same-pair deals config

## [v1.27.0] - 2026-02-14

- Fix indicator logs crash, add 7d projection basis, persist UI state

## [v1.26.3] - 2026-02-14

- Add compounded projected PnL row to Portfolio Totals

## [v1.26.2] - 2026-02-14

- Fix sparkline width by adding w-full to wrapper div

## [v1.26.1] - 2026-02-14

- Add show-stopped toggle, smart resize button, resize-all improvements

## [v1.26.0] - 2026-02-14

- Add all-time PnL, sparkline time labels, bot PnL %, fix PnL/day calc

## [v1.25.7] - 2026-02-14

- Add cascading filters to History page

## [v1.25.6] - 2026-02-14

- Add bot, market, and pair filters to History page

## [v1.25.5] - 2026-02-14

- Drive progress bar at 60fps via direct DOM updates, bypass React state

## [v1.25.4] - 2026-02-14

- Sort article and video source chips by category order

## [v1.25.3] - 2026-02-14

- Fix timeline progress bar getting stuck during TTS playback

## [v1.25.2] - 2026-02-14

- Remove all window.location.reload() calls to prevent TTS interruption

## [v1.25.1] - 2026-02-14

- Filter adult content from child TTS voices

## [v1.25.0] - 2026-02-14

- Add simultaneous deals for same pair (max_simultaneous_same_pair)

## [v1.24.3] - 2026-02-14

- Add missing source color mappings, suppress reconnect refetch when engaged
- Add missing article sources to category color map

## [v1.24.2] - 2026-02-13

- Assign rainbow-ordered colors to category filters (red→violet)

## [v1.24.1] - 2026-02-13

- Fix news source color mappings, sort categories, suppress refetch when engaged

## [v1.24.0] - 2026-02-13

- Add Volume RSI indicator and 10m/4h timeframes for bot conditions

## [v1.23.0] - 2026-02-13

- Add deal cooldown per pair to prevent immediate re-entry after close

## [v1.22.15] - 2026-02-13

- Fix MACD crossing detection: pass indicator cache for all strategies + noise filter

## [v1.22.14] - 2026-02-08

- Add Total Budget column to Positions page overall stats

## [v1.22.13] - 2026-02-08

- Fix TTS tracking drift, source filter colors, drop paywalled news sources

## [v1.22.12] - 2026-02-08

- Fix news sources missing summaries: replace title-only feeds, add og:description fallback

## [v1.22.11] - 2026-02-08

- Fix crossing detection re-firing bug & improve position decision history UX

## [v1.22.10] - 2026-02-08

- Fix AI/Finance news: correct RSS URLs and YouTube channel IDs

## [v1.22.9] - 2026-02-08

- Add AI and Finance as distinct news categories

## [v1.22.8] - 2026-02-08

- Show relative PnL delta on non-All timeframes in summary chart

## [v1.22.7] - 2026-02-08

- Add news router enhancements, sentiment card updates, and coin icons
- Add multi-select for news sources, matching category filter behavior
- Add resize deal budget feature to recalculate max_quote_allowed

## [v1.22.6] - 2026-02-08

- Respect bot reservations in auto-buy, remove force-run button from bot actions

## [v1.22.5] - 2026-02-08

- Exempt grid bots from seasonality, smooth sparkline data to 30 averaged points

## [v1.22.4] - 2026-02-08

- Refine carousel animation with realistic archery-inspired draw timing

## [v1.22.3] - 2026-02-08

- Enhance carousel bowstring animation with longer tension hold

## [v1.22.2] - 2026-02-08

- Clarify UI labels for AI analysis interval and cycle-based bot management

## [v1.22.1] - 2026-02-08

- Fix Portfolio Today PnL bug, persist news filters, remove article cap

## [v1.22.0] - 2026-02-08

- Add sparkline charts, replace dead feeds, add YouTube sources for all categories

## [v1.21.4] - 2026-02-07

- Restore projected debt milestones to US National Debt card

## [v1.21.3] - 2026-02-07

- Consolidate TTS voices into single shared constants file

## [v1.21.2] - 2026-02-07

- Fix Find Reading to navigate across pagination pages

## [v1.21.1] - 2026-02-07

- Fix bot actions menu clipped by overflow-hidden container

## [v1.21.0] - 2026-02-07

- Add multi-category news system with 50 sources across 9 categories

## [v1.20.41] - 2026-02-06

- Add pip dependency installation to update.py

## [v1.20.40] - 2026-02-03

- Implement seasonality auto-management for bots (Phase 4)

## [v1.20.39] - 2026-02-03

- Fix spurious error from audio.onerror when clearing src

## [v1.20.38] - 2026-02-03

- Fix race condition causing red button during TTS load

## [v1.20.37] - 2026-02-03

- Fix red button showing during article load

## [v1.20.36] - 2026-02-03

- Fix TTS button colors: grey spinner during loading

## [v1.20.35] - 2026-02-03

- Fix TTS auto-retry and error state handling

## [v1.20.34] - 2026-02-03

- Add 50+ TTS voices from all English locales

## [v1.20.33] - 2026-02-03

- Fix TTS article navigation state sync issues

## [v1.20.32] - 2026-02-03

- Sync frontend season wheel with halving-anchored backend logic

## [v1.20.31] - 2026-02-03

- Enhance season detector with halving cycle anchoring

## [v1.20.30] - 2026-02-03

- Add seasonality toggle to Bots page

## [v1.20.29] - 2026-02-03

- Fix clone bot, update season colors, position wheel icons

## [v1.20.28] - 2026-02-02

- Add margin-right to season badge for spacing

## [v1.20.27] - 2026-02-02

- Fix season badge spacing in header

## [v1.20.26] - 2026-02-02

- Move season indicator to site header

## [v1.20.25] - 2026-02-02

- Rename market seasons to Winter/Spring/Summer/Fall

## [v1.20.24] - 2026-02-02

- Fix market season algorithm: better bear vs accumulation detection

## [v1.20.23] - 2026-02-02

- Add market season card and info tooltips to carousel
- Add 6 new market metrics cards to carousel

## [v1.20.22] - 2026-02-02

- Reset auto-cycle timer on manual carousel interaction

## [v1.20.21] - 2026-02-02

- Fix carousel transform calculation for infinite scroll

## [v1.20.20] - 2026-02-02

- Add infinite carousel with swipe/touch support

## [v1.20.19] - 2026-02-02

- Add spring animation to market sentiment carousel

## [v1.20.18] - 2026-02-02

- Add market metrics carousel with BTC dominance, altseason index, and stablecoin supply

## [v1.20.17] - 2026-02-02

- Add debt ceiling display and weekly AI monitoring

## [v1.20.16] - 2026-02-02

- Fix synthetic chart timeframes and stabilize debt rate calculation

## [v1.20.15] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close
- Revert "Reorder mini player controls: volume before replay, queue before close"

## [v1.20.14] - 2026-02-02

- Reorder mini player controls: volume before replay, queue before close

## [v1.20.13] - 2026-02-02

- Update article reader controls to match YouTube pattern

## [v1.20.12] - 2026-02-02

- Improve word highlighting for TTS sync

## [v1.20.11] - 2026-02-02

- Mini player thumbnail click navigates to News and finds article

## [v1.20.10] - 2026-02-01

- Add missing news sources to setup.py defaults

## [v1.20.9] - 2026-02-01

- Revert Playwright implementation
- Skip Playwright for bot-blocked sites like The Block
- Add Playwright support for JS-heavy sites like The Block

## [v1.20.8] - 2026-02-01

- Make video and article players mutually exclusive

## [v1.20.7] - 2026-02-01

- Use migration flag for voice cycling localStorage fix
- Force clear stale voice cycling localStorage value

## [v1.20.6] - 2026-02-01

- Restore voice cycling toggle with proper localStorage handling
- Debug: Force voice cycling always on to isolate issue
- Use persistent Audio element to fix autoplay between articles

## [v1.20.5] - 2026-02-01

- Change progress bar to word-based instead of time-based

## [v1.20.4] - 2026-02-01

- Fix word highlighting for en-dash separated words

## [v1.20.3] - 2026-02-01

- Fix word highlighting for em-dash separated words
- Add TODO for Playwright support for JS-rendered articles

## [v1.20.2] - 2026-01-31

- Fix word highlighting for hyphenated words and end-of-playback

## [v1.20.1] - 2026-01-31

- Fix voice cycling and improve word highlighting sync

## [v1.20.0] - 2026-01-31

- Add article reader with mini-player and voice cycling TTS
- Add synchronized TTS with word highlighting and auto-scroll

## [v1.19.1] - 2026-01-27

- Revert "Add acronym expansion for consistent TTS pronunciation"
- Add acronym expansion for consistent TTS pronunciation
- Strip markdown formatting from article text before TTS
- Fix TTS autoplay blocked by browser policy

## [v1.19.0] - 2026-01-27

- Add text-to-speech for reading news articles aloud

## [v1.18.4] - 2026-01-27

- Add missing dependencies for complete fresh install

## [v1.18.3] - 2026-01-27

- Sync setup.py schema defaults with production database

## [v1.18.2] - 2026-01-27

- Add polished toast notification for clipboard copy

## [v1.18.1] - 2026-01-27

- Improve bot import/export UX

## [v1.18.0] - 2026-01-27

- Add bot import/export functionality

## [v1.17.9] - 2026-01-27

- Fix Charts page not rendering data after loading

## [v1.17.8] - 2026-01-27

- Fix JSON field parsing for AI/Indicator logs
- Optimize AI/Indicator log loading with SQL UNION query

## [v1.17.7] - 2026-01-26

- Add pulse/glow notification effect for new AI and Indicator logs

## [v1.17.6] - 2026-01-26

- Add infinite loop scrolling to PnL carousel (Price is Right wheel effect)
- Fix number clipping in Projected PnL carousel
- Fix toggle overlap and add smooth vertical scrolling to PnL carousel
- Add auto-scrolling carousel for Projected PnL with expand/collapse toggle
- Add tasteful boxes around each Projected PnL timeframe for better grouping
- Add whitespace-nowrap and width constraints to prevent PnL text wrapping
- Further reduce Active trades column padding to free up space
- Reduce table column padding to prevent PnL text wrapping

## [v1.17.5] - 2026-01-26

- Add dual-currency (BTC/USD) display to bot PnL and Projected PnL columns

## [v1.17.4] - 2026-01-26

- Fix missing closing parenthesis in PnLChart.tsx ternary operator
- Add dual-currency display to PnL by day and by pair bar charts

## [v1.17.3] - 2026-01-26

- Increase news article thumbnail resolution by 50%

## [v1.17.2] - 2026-01-26

- Improve Portfolio table readability and reduce width
- Fix profit_btc calculation - compute dynamically from existing fields
- Fix linting warnings in PnLChart.tsx
- Add dual-currency (BTC/USD) display to Bots PnL chart with toggle

## [v1.17.1] - 2026-01-26

- Add chart panning constraints to Account Value chart

## [v1.17.0] - 2026-01-26

- Add Last Year to historical period selector

## [v1.16.0] - 2026-01-26

- Add WTD (Week To Date) and improve font consistency

## [v1.15.0] - 2026-01-26

- Reorganize realized PnL into logical groups

## [v1.14.0] - 2026-01-26

- Add selectable realized PnL periods with Last Month and Last Quarter

## [v1.13.0] - 2026-01-26

- Add MTD/QTD/YTD selector for realized PnL

## [v1.12.0] - 2026-01-26

- Add 4-week and YTD realized PnL tracking
- Add realized PnL stats (daily/weekly) to Positions page

## [v1.11.1] - 2026-01-26

- Fix: Handle nested condition groups in interval calculation

## [v1.11.0] - 2026-01-26

- Phase 3: Lazy fetching - only fetch timeframes for current trading phase
- Phase 2: Smart check scheduling based on indicator timeframes

## [v1.10.0] - 2026-01-26

- Phase 1: Smart candle caching with per-timeframe TTL

## [v1.9.9] - 2026-01-26

- Add image compression for news article thumbnails

## [v1.9.8] - 2026-01-26

- Add automated cleanup job for old failed orders

## [v1.9.7] - 2026-01-26

- Add automated cleanup job for failed condition logs

## [v1.9.6] - 2026-01-26

- Add detailed budget logging to indicator logs for GUI visibility

## [v1.9.5] - 2026-01-26

- Fix technical checks to evaluate conditions and execute trades

## [v1.9.4] - 2026-01-25

- Fix frontend N/A display for indicator condition details
- Fix AI indicator evaluation: pass product_id to analyze_signal
- Fix AI indicator evaluation: pass db and user_id to analyze_signal
- Fix syntax error in AIBotLogs.tsx (extra closing paren)
- Fix AI Bot Reasoning logs for indicator-based bots with AI indicators

## [v1.9.3] - 2026-01-25

- Add no-cache headers to positions API to prevent browser HTTP caching
- Fix stale cache showing incorrect positions/gains on page load

## [v1.9.2] - 2026-01-23

- Fix aggregate cache causing incorrect budget allocation after deposits
- Smart video muting: only mute on iOS devices
- Fix iPad video autoplay issue by starting videos muted

## [v1.9.1] - 2026-01-19

- Fix budget calculator to match order execution logic

## [v1.9.0] - 2026-01-19

- Add automatic paper trading account creation

## [v1.8.7] - 2026-01-19

- Improve Indicator Logs UI with better filter labels and stats
- Enable indicator logging for ALL evaluations, not just matches
- Stop tracking CLAUDE.md in git (add to .gitignore)
- Fix all TypeScript compilation errors

## [v1.8.6] - 2026-01-19

- Fix budget calculator: divide by max deals, not number of pairs
- Fix TypeScript linting errors: unused imports and type mismatches
- Fix bot config DCA budget validation math errors
- Fix trading router exchange client import

## [v1.8.5] - 2026-01-18

- Fix trading router import and disable sell when positions are open

## [v1.8.4] - 2026-01-18

- Add quick sell buttons to Portfolio page

## [v1.8.3] - 2026-01-18

- Fix TypeScript types for bidirectional trading and multi-currency balances

## [v1.8.2] - 2026-01-18

- Setup: Offer existing values as defaults when re-running

## [v1.8.1] - 2026-01-18

- Make setup.py safe to run multiple times (idempotent)

## [v1.8.0] - 2026-01-18

- Add migration to convert coin categorizations to global entries
- Fix setup.py to seed coin categorizations as global entries
- Add copy-to-account feature for bots

## [v1.7.3] - 2026-01-18

- Add smooth curved lines to chart (like 3Commas)

## [v1.7.2] - 2026-01-18

- Remove horizontal dashed current price lines from chart
- Remove rightOffset and barSpacing that were hiding data
- Add chart padding and margins to separate price lines from opposite axes
- Fix BTC y-axis to always show 8 decimal places
- Change BTC line color to solid orange (#ff8800)
- Fix chart default time range to 'all' instead of disabled '30d'

## [v1.7.1] - 2026-01-18

- Add account filter toggle to value chart - show selected account or all accounts

## [v1.7.0] - 2026-01-18

- Comprehensive macOS setup.py fixes for seamless installation

## [v1.6.3] - 2026-01-18

- Fix setup.py to properly install Homebrew and npm on macOS
- Fix account value snapshots to match portfolio display
- Fix account value chart to use authenticated API instance
- Fix account value chart authentication and paper trading toggle

## [v1.6.2] - 2026-01-17

- Complete paper trading snapshot implementation
- Fix account snapshot service SQLAlchemy async issues

## [v1.6.1] - 2026-01-17

- Update CLAUDE.md: Use systemctl for both backend and frontend services
- Add comprehensive plan verification document
- Complete bidirectional DCA grid bot implementation
- Final verification against implementation plan
- Phase 5: Add reservation display to Dashboard
- Add implementation summary and progress documentation
- Phase 3-4: Short order execution and bot validation
- Document per-account (per-CEX) reservation isolation
- Separate live and paper trading reservations
- Add asset conversion tracking for bidirectional bots
- Add bidirectional DCA grid bot foundation

## [v1.5.2] - 2026-01-16

- Fix import error: get_current_user from auth_dependencies

## [v1.5.1] - 2026-01-16

- Exclude paper trading accounts from account value chart by default

## [v1.5.0] - 2026-01-16

- Add account value history chart with daily snapshots

## [v1.4.0] - 2026-01-16

- Add ETH/USD price display next to BTC price in header

## [v1.3.1] - 2026-01-16

- Fix BTC/USD price display in header for paper trading

## [v1.3.0] - 2026-01-16

- Fix paper trading history isolation and update setup.py schema

## [v1.2.0] - 2026-01-14

- Restore AccountSwitcher dropdown, exclude paper trading from list
- Remove AccountSwitcher dropdown, keep only Paper Trading toggle
- Remove temporary debugging code
- Fix black screen: Add missing botsFetching destructuring
- CRITICAL FIX: Exclude paper trading accounts from get_coinbase_from_db
- Add temporary debug logging for bots page filtering issue
- Improve Bots page empty state message for account switching
- Fix: Reduce bot list refetch interval from 5s to 30s
- Add production-ready enhancements: rebalancing cooldown and exchange minimum validation
- Change paper trading toggle to orange when enabled
- Fix paper trading portfolio format to match frontend expectations
- Fix paper trading portfolio and balance queries
- Fix paper trading portfolio display in header
- Fix paper trading balances to show virtual balances
- Add Paper Trading balance management UI
- Fix import path for get_current_user in paper trading router
- Add paper trading functionality
- Update grid trading status documentation - ALL PHASES COMPLETE
- Phase 4: Complete Hybrid AI range mode
- Phase 7: Implement time-based grid rotation
- Phase 6: Implement volume-weighted grid levels
- Phase 5: Implement AI-Dynamic Grid optimization
- Add comprehensive grid trading implementation status document
- Fix unit test expectations for grid calculations
- Add strategies API endpoint and wire frontend to use it
- Phase 8: Enhanced frontend balance display with 3-column layout
- Phase 3: Dynamic breakout detection and grid rebalancing
- Phase 1-2: Grid order placement and neutral/long grid execution
- Phase 1: Implement GridTradingStrategy with core calculations
- Phase 0: Add capital reservation tracking for grid trading bots

## [v1.0.0] - 2026-01-13

- Show ALL quote currency balances (BTC, ETH, USD, USDC, USDT)
- Show reserved and available balances for all quote currencies
- Track BTC profit for all positions and show available balance
- Implement completed trades profit statistics on Positions page
- Fix backspace delete functionality for all numeric input fields

## [v0.134.2] - 2026-01-11

- Emphasize coin categorization is a critical safety feature

## [v0.134.1] - 2026-01-11

- Remove unused get_api_key_for_provider() fallback function

## [v0.134.0] - 2026-01-11

- Separate user and system AI API keys: users must configure their own

## [v0.133.13] - 2026-01-11

- Remove unused config variables: secret_key and ticker_interval

## [v0.133.12] - 2026-01-11

- Add missing video_articles table to setup.py database initialization

## [v0.133.11] - 2026-01-11

- Clarify AI Bot Quick Start is entirely GUI-based

## [v0.133.10] - 2026-01-11

- Remove auto-deployment comment from README

## [v0.133.9] - 2026-01-11

- Remove Recent Updates section from README

## [v0.133.8] - 2026-01-11

- Add update.py usage documentation to README

## [v0.133.7] - 2026-01-11

- Update README to accurately reflect setup ease and current capabilities

## [v0.133.6] - 2026-01-11

- Fix: Always monitor existing positions regardless of category filter

## [v0.133.5] - 2026-01-11

- Add category badges to pairs list and counts to category checkboxes

## [v0.133.4] - 2026-01-11

- Remove category permissions UI from Settings page
- Add bot-level category filtering for trading pairs
- Add dedicated MEME category for coin review
- Add auto-add new pairs option to bot configuration
- Reduce log noise from delisted pairs and fix port reference

## [v0.133.3] - 2026-01-09

- Fix portfolio conversion ImportError crash preventing sell orders

## [v0.133.2] - 2026-01-09

- Fix auto-buy BTC toggle not persisting on page refresh

## [v0.133.1] - 2026-01-09

- Make portfolio conversion per-account instead of global

## [v0.133.0] - 2026-01-09

- Restore Portfolio Conversion UI to Settings page

## [v0.132.0] - 2026-01-08

- Rename repository from GetRidOf3CommasBecauseTheyGoDownTooOften to ZenithGrid

## [v0.131.3] - 2026-01-08

- Clean up test files
- Add donation addresses to README

## [v0.131.2] - 2026-01-08

- Add donation addresses to LICENSE file

## [v0.131.1] - 2026-01-08

- Major refactoring: Modularize all large components and update licensing
- Fix setup.py: Add missing user_attempt_number column to positions table

## [v0.131.0] - 2026-01-08

- Major refactoring: Modularize all large components + fix auto-calculate budget

## [v0.130.1] - 2026-01-03

- Fix auto-buy USD conversion bugs

## [v0.130.0] - 2026-01-03

- Fix percentage placeholders appearing during portfolio refetch
- Fix loading screen when changing timeframes - use keepPreviousData
- Fix absurd projection calculations by using linear extrapolation
- Fix loading spinner appearing when changing timeframes
- Show full timeframe window in chart including zero-profit days
- Fix projections not updating when changing timeframes
- Prevent loading spinner when changing timeframes in Bots page
- Fix timeframe selector requiring double-click by adding explicit button type

## [v0.129.2] - 2026-01-03

- Fix auto-calculate safety order sizing bugs
- Archive all migration files - not needed for fresh installs
- Fix deal number migration to not assign numbers to failed positions

## [v0.129.1] - 2026-01-02

- Fix auto-calculate budget bug and UI deal number display
- Use Edit Order API for bid fallback instead of cancel-and-replace
- Implement Coinbase native Edit Order API for limit price updates

## [v0.129.0] - 2026-01-02

- Keep order type when enabling auto-calculate, compute optimal values
- Only auto-calculate base order size when toggle is enabled
- Auto-calculate base order size to fit budget with safety orders
- Use print() instead of logger for startup reconciliation messages
- Fix: Integrate startup reconciliation into main limit order monitor

## [v0.127.5] - 2026-01-02

- Add startup reconciliation for limit orders

## [v0.127.4] - 2026-01-02

- Fix base order sizing to reserve budget for safety orders

## [v0.127.3] - 2026-01-02

- Add rate limiting to Coinbase API calls to prevent 403 errors

## [v0.127.2] - 2026-01-02

- Add safety check: Prevent market order fallback below minimum profit target

## [v0.127.1] - 2026-01-02

- Fix: Round buy amounts to exchange increment to prevent profit loss on sell
- Fix model import: Setting -> Settings (plural)

## [v0.128.0] - 2026-01-01

- Add configurable cleanup for old decision logs

## [v0.127.0] - 2026-01-01

- Add unified decision logs (AI + Indicators)

## [v0.126.2] - 2026-01-01

- Fix all strategy parameter number inputs (including take profit)

## [v0.126.1] - 2026-01-01

- Fix number input fields allowing proper backspace/deletion

## [v0.126.0] - 2026-01-01

- Add clickable deal numbers with trade history popup

## [v0.125.0] - 2025-12-31

- Implement dual numbering system and 3Commas-style deal tracking

## [v0.124.1] - 2025-12-31

- Fix changelog cache not auto-refreshing when new tags created

## [v0.124.0] - 2025-12-31

- Add auto-buy BTC with stablecoins feature

## [v0.123.0] - 2025-12-31

- Add explicit auto-calculate toggle for DCA budget calculator

## [v0.122.2] - 2025-12-31

- Enforce exchange minimums in budget calculator with warnings

## [v0.122.1] - 2025-12-31

- Make order size fields read-only when budget calculator active

## [v0.122.0] - 2025-12-31

- Add DCA budget calculator with auto-sizing breakdown

## [v0.121.0] - 2025-12-31

- Make PnL projections configurable by chart timeframe

## [v0.120.0] - 2025-12-31

- Replace AI indicators with unified AI Spot Opinion system

## [v0.119.1] - 2025-12-31

- Fix Dashboard metrics to show accurate profit and win rate stats

## [v0.119.0] - 2025-12-26

- Frontend: Add real-time progress tracking for portfolio conversion
- Backend: Add real-time progress tracking for portfolio conversion

## [v0.118.0] - 2025-12-26

- Add detailed progress tracking to portfolio conversion
- Complete symmetric portfolio conversion logic + dust filtering

## [v0.117.0] - 2025-12-26

- Add rate limit delays to portfolio conversion (0.2s between orders)
- Add detailed error logging for Coinbase API failures
- Add error handling for Coinbase API failures in sell-portfolio endpoint
- Improve sell-portfolio-to-base: handle missing trading pairs via USD route
- Fix sell-portfolio-to-base endpoint - correct create_market_order call

## [v0.116.0] - 2025-12-25

- Enhance MissingOrderDetector to catch sell orders and stuck pending orders

## [v0.115.3] - 2025-12-25

- Fix critical duplicate limit order bug and position data inconsistencies

## [v0.115.2] - 2025-12-21

- Fix changelog Load More being slow - remove repeated git fetch

## [v0.115.1] - 2025-12-21

- Improve changelog loading performance

## [v0.115.0] - 2025-12-21

- Add About page with paginated changelog, fix stopped bots monitoring

## [v0.114.0] - 2025-12-18

- Add bidirectional chart synchronization for indicator panels

## [v0.113.4] - 2025-12-15

- Revert speculative bar spacing change - data is correct, label thinning is normal

## [v0.113.3] - 2025-12-15

- Adjust chart time scale spacing for better label visibility
- Add debug logging for PnL chart date range issue

## [v0.113.2] - 2025-12-15

- Fix PnL chart date range using string comparison

## [v0.113.1] - 2025-12-15

- Fix PnL chart not showing dates up to today

## [v0.113.0] - 2025-12-15

- Add >= and <= operators to phase condition selector

## [v0.112.16] - 2025-12-14

- Update cleanup documentation and fix setup.py service template
- Update cleanup script with comprehensive retention policies
- Add daily database cleanup script

## [v0.112.15] - 2025-12-14

- Add coin icon proxy to avoid CORS issues

## [v0.112.14] - 2025-12-14

- Fix recharts negative dimension warning by setting minimum chart height
- Fix greenlet SQLAlchemy error by eager loading Position.trades

## [v0.112.13] - 2025-12-14

- Add 14 days time range option

## [v0.112.12] - 2025-12-14

- Fix time range button logic - enable up to first covering timeframe

## [v0.112.11] - 2025-12-14

- Disable time range buttons that wouldn't show additional data

## [v0.112.10] - 2025-12-14

- Add 1 year time range filter to Bot Management PnL chart

## [v0.112.9] - 2025-12-14

- Fix AI coin review providers and model names

## [v0.112.8] - 2025-12-14

- Fix greenlet conflict by using sync SQLite for AI provider lookup

## [v0.112.7] - 2025-12-14

- Add AI provider selection for coin review

## [v0.112.6] - 2025-12-14

- Fix HTML entity encoding in og:image URLs (e.g., &amp; -> &)

## [v0.112.5] - 2025-12-14

- Add image proxy endpoint for cached thumbnails

## [v0.112.4] - 2025-12-14

- Add og:image fallback for feeds without thumbnails (Blockworks)

## [v0.112.3] - 2025-12-14

- Fix news loading performance by using URL thumbnails instead of base64

## [v0.112.2] - 2025-12-14

- Switch articles to client-side pagination for instant page changes

## [v0.112.1] - 2025-12-14

- Fix indicator logging: respect bot capacity and DCA slots

## [v0.112.0] - 2025-12-14

- Add pagination for news articles, remove video limit

## [v0.111.2] - 2025-12-14

- Fix: Use only closed candles for indicator calculations

## [v0.111.1] - 2025-12-13

- Skip entry indicator logging when position already exists

## [v0.111.0] - 2025-12-13

- Fix dropdown to float but start at button position
- Fix playlist dropdown to anchor below button instead of fixed position
- Extend news/video max age from 7 to 14 days

## [v0.110.0] - 2025-12-13

- Add new crypto news and YouTube sources

## [v0.109.5] - 2025-12-13

- Tone down pulse animation - subtler outline and fewer pulses

## [v0.109.4] - 2025-12-13

- Fix pulse animation using outline instead of box-shadow to avoid conflict with ring classes

## [v0.109.3] - 2025-12-13

- Reorganize MiniPlayer layout with stacked rows and enhance pulse effect

## [v0.109.2] - 2025-12-13

- Add pulsing red halo effect when clicking Find Playing button

## [v0.109.1] - 2025-12-13

- Fix time scrubber not updating on video autoplay
- Add db backup files to gitignore
- Add hover-to-scroll to News page 'Start from video' dropdown

## [v0.109.0] - 2025-12-13

- Fix VIDEO_CACHE_CHECK_MINUTES import and add MiniPlayer enhancements

## [v0.108.0] - 2025-12-13

- Add background content refresh and video database storage
- Fix video autoplay skipping every other video

## [v0.107.0] - 2025-12-13

- Add scroll-to-playing button for video list
- Add halo effect to currently playing video in News page
- Add database cleanup service creation to setup.py wizard

## [v0.106.2] - 2025-12-13

- Fix PnL chart to prevent zooming beyond data bounds

## [v0.106.1] - 2025-12-13

- Fix stopped bots to properly manage open positions

## [v0.106.0] - 2025-12-13

- Add database cleanup maintenance script with systemd timer

## [v0.105.2] - 2025-12-13

- Fix Active Deals showing empty due to failed position flood
- Increase throttling delays to allow API requests during bot monitoring
- Add throttling constants for t2.micro CPU optimization
- Add processing delays to reduce CPU burst on t2.micro
- Optimize API call frequency with increased cache TTLs

## [v0.105.1] - 2025-12-12

- Add percentage field validation against exchange minimums
- Add price_drop as visible DCA condition in indicator logs
- Fix: Remove redundant max_concurrent_deals division in calculate_base_order_size
- Fix: Respect split_budget_across_pairs toggle
- Fix budget_percentage: 0 means 0, 100 means 100
- Fix: budget_percentage=0 now means 100% (All) as UI indicates
- Fix MACD display: show 8 decimals, scientific notation for tiny values
- Fix USD-based bot form: dynamic currency labels
- Fix indicator precision: use 8 decimals for MACD values
- Fix indicator value display precision in logs
- Fix indicator logging and add higher timeframe support
- Add ONE_HOUR candle fetching for hourly MACD/RSI conditions
- Fix crossing detection for BB% and other indicators
- Skip logging DCA/Exit conditions for pairs without positions
- Fix crossing detection for indicator_based entry conditions
- Fix crossing detection for entry conditions (MACD Bot fix)

## [v0.105.0] - 2025-12-12

- Add daily trading pair monitor to sync delisted/new pairs
- Add deal age display to position cards

## [v0.104.1] - 2025-12-12

- Fix playlist double-advance bug: prevent nextVideo from being called twice
- Revert MiniPlayer to before background playback changes
- Fix YouTube player controls and background playback
- Keep YouTube video playing when tab loses focus

## [v0.104.0] - 2025-12-11

- Add bot creation fixes, optimistic updates, and schema sync
- Add npm dependency handling to update.py
- Upgrade all npm dependencies to latest major versions
- Update npm dependencies and CLAUDE.md environment detection

## [v0.103.2] - 2025-12-11

- Add rate limiting between order executions to prevent Coinbase 403 throttling

## [v0.103.1] - 2025-12-11

- Fix playlist auto-advance: subscribe to YouTube iframe events
- Increase video hover size to 6x (672x384px)
- Fix video hover: use overflow-visible and explicit size change
- Add hover-to-enlarge effect on mini player video

## [v0.103.0] - 2025-12-10

- Fix limit order UI: CoinbaseAdapter time_in_force and price step arrows
- Fix: Edit Limit Price now properly preselects current limit price
- Update setup.py schema for pending_orders GTD fields

## [v0.102.0] - 2025-12-10

- Add GTD (Good 'til Date) order type support for limit close orders

## [v0.101.0] - 2025-12-10

- Show Deal # and pair in limit close modal title
- Make depth chart rows dynamically fill available space
- Round mark price UP to valid precision for sell orders
- Add quick-select buttons for Bid, Mark, Ask prices in limit close modal
- Enhance limit close modal: clickable depth chart, extended slider range
- Highlight limit price in depth chart with light grey outline

## [v0.100.16] - 2025-12-10

- Add /api/market/btc-usd-price endpoint
- Add today's USD value for closed BTC positions (HODL tracker)
- Show USD profit value for closed BTC pair positions

## [v0.100.15] - 2025-12-09

- Add ESC key handler to LimitCloseModal
- Extend slider range when limit price is outside bid-ask
- Fix Coinbase orderbook API endpoint
- Fix: Add get_product_book to CoinbaseAdapter

## [v0.100.14] - 2025-12-09

- Add Level 2 order book depth chart to limit close modal
- Fix slider resetting: remove price reset from fetchTicker

## [v0.100.13] - 2025-12-09

- Fix slider resetting to mark on ticker updates

## [v0.100.12] - 2025-12-09

- Add tick marks on slider to show valid price levels

## [v0.100.11] - 2025-12-09

- Slider snaps to valid precision steps for each coin

## [v0.100.10] - 2025-12-09

- Add breakeven tick mark to limit close slider

## [v0.100.9] - 2025-12-09

- Improve visual loss indicators in limit close modal

## [v0.100.8] - 2025-12-09

- Add loss confirmation alert for limit close orders

## [v0.100.7] - 2025-12-09

- Fix: Handle whole number base_increment in get_base_precision()
- Fix crossing detection for indicator-based strategies
- Add database seeding for fresh installs

## [v0.100.6] - 2025-12-09

- Extract thumbnails from RSS description HTML as fallback
- Derive allowed article domains from database instead of hardcoded list
- Add Bitcoin Magazine and BeInCrypto to allowed article domains
- Replace Reddit sources with Bitcoin Magazine and BeInCrypto
- Fix: Correct Reddit source names in migration
- Fix: Add auth headers to sources API calls
- Fix: Replace get_async_db with get_db in sources_router

## [v0.100.5] - 2025-12-09

- Add user source subscription UI and migrate news to DB sources

## [v0.100.4] - 2025-12-09

- Add database-backed content sources with user subscriptions

## [v0.100.3] - 2025-12-09

- Sync setup.py with production schema

## [v0.100.2] - 2025-12-09

- Add 6 new crypto YouTube channels to video news

## [v0.100.1] - 2025-12-09

- Unify video playback: individual videos open in expanded modal

## [v0.100.0] - 2025-12-09

- Add play/pause controls to mini-player
- Refactor: Single morphing player that transforms between mini-bar and modal
- Fix: Collapse mini-player when full modal opens to prevent duplicate playback
- Fix: Remove duplicate video iframe from mini-player thumbnail area

## [v0.99.0] - 2025-12-09

- Feature: Add persistent mini-player for video playlist

## [v0.98.0] - 2025-12-09

- Add video player modal for Play All in Crypto News
- Add alias support to update.py completion
- Add bash completion script for update.py

## [v0.97.1] - 2025-12-09

- Feature: Add longer timeframes (2d, 3d, 1w, 2w, 1M)

## [v0.97.0] - 2025-12-09

- Fix: Verify profit at mark price before placing limit sell orders

## [v0.96.9] - 2025-12-09

- Add indicator condition logging for non-AI bots

## [v0.96.8] - 2025-12-09

- Fix AI indicator detection to prioritize type field over legacy indicator field

## [v0.96.7] - 2025-12-09

- Fix update_ai_bots_with_dca migration to detect already applied state
- Fix migration idempotency detection for table creation migrations

## [v0.96.5] - 2025-12-09

- Fix: AI min confluence score default from 65 to 40 (moderate preset)

## [v0.96.4] - 2025-12-09

- Add graceful shutdown to wait for in-flight orders before stopping

## [v0.96.3] - 2025-12-09

- UI: Hide Safety Orders/Take Profit for pattern-based entries

## [v0.96.2] - 2025-12-09

- Bull Flag: Use pattern-calculated TSL/TTP instead of percentage-based config

## [v0.96.1] - 2025-12-09

- Add toggleable Safety Orders option to bot form
- Fix: Bull flag params not reading migrated config values

## [v0.96.0] - 2025-12-09

- Fix: AI log only shows SELL for pairs with positions

## [v0.95.9] - 2025-12-09

- Fix: Condition exits now require Take Profit % as minimum

## [v0.95.8] - 2025-12-08

- Fix: Add 'equal' and 'not_equal' operators to phase condition evaluator

## [v0.95.7] - 2025-12-08

- Fix: Add ai_buy/ai_sell/bull_flag handler in phase_conditions

## [v0.95.6] - 2025-12-08

- Fix BB indicator key format mismatch (2.0 vs 2)

## [v0.95.5] - 2025-12-08

- Fix THREE_MINUTE timeframe detection and BB% lower band requirement

## [v0.95.4] - 2025-12-08

- Fix TypeError in should_sell() when take_profit_percentage is None

## [v0.95.3] - 2025-12-08

- Fix: Recalibrate AI confluence thresholds to match scoring reality

## [v0.95.2] - 2025-12-07

- Fix: Don't migrate blacklisted_coins user_id in multi-user migration

## [v0.95.1] - 2025-12-07

- Fix: Bot AI icon detection for grouped condition format

## [v0.95.0] - 2025-12-07

- Fix: Remove Position model properties that cause async greenlet errors
- Feature: Accurate DCA tick marks based on reference price setting
- UI: Show all DCA target levels as tick marks on position cards

## [v0.94.0] - 2025-12-07

- Feature: DCA target improvements

## [v0.93.0] - 2025-12-07

- Lint: Fix remaining lint errors (E712, F541, F841, E741)
- Lint: Remove unused imports (F401) - 14 errors fixed

## [v0.92.2] - 2025-12-07

- UI: Show time in changelog version dates

## [v0.92.1] - 2025-12-07

- Fix: Handle fixed_btc order type and show position ID in failed orders
- Backend: Use condition-level AI risk presets and handle grouped conditions
- UI: Add risk preset and AI provider selectors for AI Buy/Sell indicators
- Feature: Advanced condition builder with grouping and NOT support

## [v0.92.0] - 2025-12-07

- Fix: Allow full BTC precision (8 decimals) in order amount inputs
- Fix: Enforce max_safety_orders limit in indicator_based strategy
- UI: Add funds modal with slider for percentage of available balance
- Fix: Handle null profit in WebSocket order fill handler
- Fix: Apply candle gap-filling to all timeframes, not just THREE_MINUTE
- Fix: Show clear BUY/SELL/HOLD decisions in AI bot logs for indicator_based strategy
- Fix: Handle NaN values in ThreeCommasStyleForm number inputs
- Fix: Handle AI logging for indicator_based strategy
- Fix: Add AI logging to process_bot_pair for non-batch strategies
- Add Max Concurrent Deals field to ThreeCommasStyleForm
- UI: Make Safety Order Volume/Step Scale always visible
- Fix: Add missing db.commit() calls for scanner logs
- Fix: Handle None aggregate_value in debug print statements
- Fix condition type normalization for bot edit form
- Fix Strategy Parameters section for indicator_based bots
- Fix: Strip query params from JWT URI to fix 401 errors
- Fix: Add market_context parameter to IndicatorBasedStrategy.should_sell()
- Fix: Add **kwargs to IndicatorBasedStrategy.should_buy()
- Fix: Initialize candles variable before use in process_single_bot
- Fix: Move prepare_market_context to candle_utils
- Refactor: Replace pre-baked strategies with unified indicator-based bot builder

## [v0.91.0] - 2025-12-06

- Refactor: Extract indicator modals from DealChart.tsx
- Refactor: Extract types and utils from MarketSentimentCards.tsx
- Refactor: Remove duplicate CandleData interface from Portfolio.tsx
- Refactor: Extract DEX constants and ABIs to dedicated module
- Refactor: Extract portfolio utilities from accounts_router.py
- Refactor: Remove duplicate utilities from LightweightChartModal
- Refactor: Extract news utilities from News.tsx
- Refactor: Extract IndicatorSettingsModal from Charts.tsx
- Refactor: Extract candle utilities from multi_bot_monitor.py
- Refactor: Extract bot utilities from Bots.tsx
- Refactor: Extract DealChart component from Positions.tsx
- Refactor: Extract utilities and AISentimentIcon from Positions.tsx
- Refactor: Extract models, sources, and cache from news_router.py
- Refactor: Extract debt ceiling data from news_router.py
- Docs: Add housekeeping file splitting plan

## [v0.90.0] - 2025-12-06

- Enhance AI providers UI to use API data directly
- Add AI provider credentials UI to Settings page

## [v0.89.0] - 2025-12-06

- Wire up AI providers to use database credentials with .env fallback
- Add per-user AI provider credentials storage in database
- Add Groq AI provider support (14,400 RPD free tier)

## [v0.88.2] - 2025-12-06

- Fix: Store news images as base64 in database instead of filesystem

## [v0.88.1] - 2025-12-06

- Fix: Proxy /static route to backend for cached news images

## [v0.88.0] - 2025-12-06

- Feat: Database-backed news caching with local image storage

## [v0.87.10] - 2025-12-06

- Feat: Add update available indicator in header

## [v0.87.9] - 2025-12-06

- Fix: Expose version in root endpoint for reliable frontend access

## [v0.87.8] - 2025-12-06

- Fix: Use dynamic path resolution for git version detection

## [v0.87.7] - 2025-12-06

- Fix: Fetch app version from backend API instead of Vite build-time

## [v0.87.6] - 2025-12-06

- Fix: Extend price bar range to always show next DCA level

## [v0.87.5] - 2025-12-06

- Fix: Color version number instead of 'Installed:' label

## [v0.87.4] - 2025-12-06

- Color 'Installed:' label based on how far behind

## [v0.87.3] - 2025-12-06

- Fix: Show only next DCA tick on position bar

## [v0.87.2] - 2025-12-06

- Simplify changelog header to show Latest/Installed only

## [v0.87.1] - 2025-12-06

- Fix: Show DCA tick marks for AI bots with manual DCA targets

## [v0.87.0] - 2025-12-06

- Feat: Add 3Commas-style deal editing for open positions

## [v0.86.7] - 2025-12-06

- Fix changelog wording: use 'Installed' instead of 'Current version'

## [v0.86.6] - 2025-12-06

- Enhance changelog to show current version and unpulled updates

## [v0.86.5] - 2025-12-06

- Smart service restart detection in update.py

## [v0.86.4] - 2025-12-06

- Add --changelog flag to update.py

## [v0.86.3] - 2025-12-06

- Fix insufficient_funds calculation to use current position values

## [v0.86.2] - 2025-12-06

- Make order recording atomic to prevent missed trades
- Add missing order detector service to prevent untracked trades

## [v0.86.1] - 2025-12-06

- Fix: History page missing recently closed positions

## [v0.86.0] - 2025-12-06

- Fix: Profit target now uses bot config with sell-side fee adjustment
- Fix: Account for trading fees in base amount for BTC pairs
- Fix: product-precision endpoint URL in LimitCloseModal
- Add video playlist auto-play feature to News page
- Fix: Bull flag pullback detection now finds red candles within window
- Add --preview flag to update.py to view incoming changes

## [v0.85.1] - 2025-12-05

- Fix: History badge not persisting viewed state

## [v0.85.0] - 2025-12-05

- Fix budget percentage calculation for manual sizing mode

## [v0.84.6] - 2025-12-05

- Fix coin categorization showing all as approved + add --skip-pull flag

## [v0.84.5] - 2025-12-04

- Add idempotency checks to migrations

## [v0.84.4] - 2025-12-04

- Fix History badge to track closed/failed counts separately

## [v0.84.3] - 2025-12-04

- Fix migrations to use relative paths instead of hardcoded paths

## [v0.84.2] - 2025-12-04

- Skip service restart in update.py when already up to date

## [v0.84.1] - 2025-12-04

- Add user_id and user_deal_number columns to setup.py schema

## [v0.84.0] - 2025-12-04

- Add user-specific deal numbers for positions

## [v0.83.0] - 2025-12-04

- Add git check to setup.py for version display

## [v0.82.0] - 2025-12-04

- Auto-inject git version into app at build time
- Add version display to header

## [v0.81.0] - 2025-12-04

- Update: Add frontend service support to update.py
- Add update.py script for automated production updates
- Add EULA/risk disclaimer acceptance flow for users
- Add license agreement acceptance to setup wizard
- Fix: Persist failed orders seen count across sessions

## [v0.80.0] - 2025-12-04

- Setup: Make Gemini default AI provider, add PEM key format handling
- Fix: Rename limit order monitor method to match main.py call
- Refactor: Make coin categorization admin-only with global visibility
- Fix: Update bot routers and coin review service to get Coinbase client from database
- Fix: Update all routers to get Coinbase client from database
- Fix: Position router dependencies now get Coinbase client from database
- Fix: Update account_router to get exchange client from database
- Fix: Use _current_exchange to avoid property conflict
- Fix: Set exchange client per-bot in monitoring loop
- Fix: Guard against None order_monitor in start/stop
- Multi-user Coinbase credentials from database
- Add setup introduction with step overview and confirmation prompt
- Fix bcrypt import error in setup wizard
- Add multi-provider AI support for coin categorization
- Clarify system vs per-user AI API keys in setup wizard
- Protect git-tracked deployment scripts during cleanup
- Auto-restart setup with Python 3.11 after installation
- Add animated spinner for long-running operations
- Offer to install Homebrew on Mac if not present
- Auto-install Python 3.11 when version too old
- Require Python 3.10+ and pin exact dependency versions
- Use flexible version constraints in requirements.txt
- Add --cleanup flag to setup wizard
- Remove setup.sh wrapper - users run python3 setup.py directly
- Add --uninstall-services flag to setup wizard
- Add --services-only flag to setup wizard
- Improve setup wizard to auto-detect and install dependencies
- Add setup wizard for initial application configuration
- Store history badge count in database per user
- Add confirmation dialog for sign out button
- Add password change UI to Settings page
- Add public signup with comprehensive EULA and risk disclosure
- Add user filtering to all routers and frontend auth interceptors
- Add multi-user support with JWT authentication
- Fix: Set account_id when creating positions
- Fix: Clear stale position errors when market data fetch succeeds
- Add ONE_MINUTE option to bull flag scanner timeframe
- Clean up debug logging after verifying gap-fill works
- Switch gap-fill debug logging to print() for guaranteed visibility
- Add entry-point debug logging to gap-fill function
- Add always-on gap-fill debug logging with max_gap info
- Add detailed gap-fill debug logging
- Add info-level logging for candle gap-filling to debug THREE_MINUTE issues
- Add candle gap-filling for sparse BTC pairs like charting platforms
- Fix Coinbase API 400 error from exceeding 300 candle limit
- Fix THREE_MINUTE BB% conditions failing on low-volume pairs
- Add Polyform Noncommercial 1.0.0 license
- Feat: Close article modal with ESC key
- Feat: Use compound interest for PnL projections
- Fix: Extract video_id from YouTube Shorts URLs
- Fix: Video playback affecting multiple videos in News page
- Cleanup: Remove verbose debug print statements from candle caching
- Fix: Request 300 ONE_MINUTE candles upfront for THREE_MINUTE cache
- Debug: Add print statements for candle caching visibility
- Change cache debug to logger.info to be visible
- Add debug logging for candle cache hits/misses
- Update handoff doc - mark both issues as fixed
- Fix BB% THREE_MINUTE indicator not populating for AI bots
- Fix force-close 500 error and add BB% debug logging
- Add detailed rejection reasons to bull flag pattern detection

## [v0.79.0] - 2025-11-30

- Fix PnL charts to show all dates, including days with no trades
- Feature: Add pagination to History page

## [v0.78.3] - 2025-11-30

- Fix: Add account_id to order history API response

## [v0.78.2] - 2025-11-30

- Fix: Show loading indicator for projected PnL percentages

## [v0.78.1] - 2025-11-30

- Fix: Trust initial AI buy signal for DCA, don't let secondary AI block it
- Fix: AI bots require buy signal for DCA, price drop is safeguard
- Fix: DCA no longer requires signal_type=buy
- debug: Add detailed logging to DCA decision flow
- debug: Add DCA decision logging to diagnose why DCAs aren't executing
- Perf: Increase cache TTLs and skip dust balances for faster API
- Perf: Parallelize API calls in aggregate value calculations
- Fix: DCA Completed count showing 0 instead of actual count

## [v0.78.0] - 2025-11-30

- Add Win Rate column to Bots table
- Add batched concurrency to bull flag scanner for rate limiting
- Fix: Bull flag scanner now scans all approved coins (was limited to 50)
- Fix volume detection and bull flag pattern validation
- Revert: Re-enable redirect_slashes to fix 404 errors
- Fix: Increase refetch intervals to prevent constant reload loop
- Fix: Disable redirect_slashes to prevent 307 redirects
- Fix: Batch position price fetches to avoid Coinbase rate limits
- Fix: Use get_product() for volume detection in bull flag scanner
- Fix: Optimize list_bots endpoint - pre-fetch aggregate values and batch price requests
- Fix: Add batched price fetching to accounts_router to prevent rate limits
- Speed up portfolio loading with batched price fetching
- Fix portfolio pagination and add debugging logs
- Add scanner logs feature for bull flag strategy
- Fix: Add aggregate_value parameter to bull_flag should_buy
- Add volume confirmation to bull flag pattern detection
- Fix: Bull flag scanner get_candles API compatibility
- Fix: Frontend Active Trades display for bull_flag strategy
- Fix: Bot stats max_concurrent_positions and portfolio missing assets
- Fix: Render bull_flag strategy parameter groups in frontend
- Fix: Make product_id Optional in BotResponse for multi-pair strategies
- Fix circular import in bull_flag_scanner
- Add bull flag USD trading strategy with TSL/TTP

## [v0.77.0] - 2025-11-30

- Fix: Add account_id to API response schemas for multi-account filtering
- Extract market sentiment cards into reusable component
- Reorganize nav: group account-specific vs general pages
- Add account filtering to PnLChart and pnl-timeseries API
- Simplify account filtering after DB migration
- Fix account filtering: DEX accounts now show only their own data
- Make History and Dashboard pages account-specific
- Fix header Account Value to use account-specific portfolio
- Fix Portfolio CEX/DEX account switching regression
- Fix all TypeScript errors in frontend codebase
- Add coin icons to Settings page coin categories list
- Add real-time order fill notifications with audio and visual alerts
- Improve news caching: 15-min refresh, 7-day retention, merge strategy
- Add 15-minute auto-refresh for news articles and videos
- Fix debt ceiling display: show values under $1T in billions
- Add complete US debt ceiling history from 1939 to present
- Add political context and source links to debt ceiling history
- Move debt ceiling history to modal, rename Milestones to Projected Milestones
- Move debt ceiling history to backend API
- Add debt ceiling history section showing last 7 increases/suspensions
- Add debt milestone countdowns for $1T and $5T markers
- Show specific estimated date for BTC halving countdown
- Fix Max safety orders display for AI autonomous bots
- Move commercialization roadmap to separate file
- Add commercialization roadmap for Zenith Grid
- Remove brotli from Accept-Encoding (not installed)
- Add full browser headers to article fetcher to fix 403 errors
- Default to reader mode when opening articles, always show thumbnail
- Fix duplicate title in reader mode with fuzzy matching
- Enhance reader mode with markdown formatting support
- Fix paragraph preservation in reader mode article content
- Add Reader Mode for news articles
- Add article preview modal to News page
- Add prominent open-in-new-tab button for videos
- Add inline YouTube video playback to News page
- Move News link to between Dashboard and Bots in nav
- Fix news timestamps: add UTC timezone indicator (Z suffix)
- Add periodic refresh for news article timestamps
- Add cache files and db backup patterns to gitignore
- Fix US debt counter to always count up
- Add US National Debt counter and halving countdown format toggle
- Fix BTC halving countdown timer - use stable dependency
- Add Fear/Greed Index and BTC Halving countdown to News page
- Add video news section with YouTube crypto channels
- Add feedparser dependency for news aggregation
- Fix Dashboard bot cards: profit and deals display
- Add crypto news aggregation tab with 24-hour caching

## [v0.76.0] - 2025-11-29

- Fix: Summary PnL chart shows relative profit for time range
- Fix: Most profitable bot card respects time range filter
- Fix: PnL by pair chart respects time range filter
- Fix: PnL stat should sum profits within selected time range
- Fix: PnL stat also showing $0 on by_pair tab
- Fix: Closed trades count incorrectly showing days instead of trades
- Optimize startup: lazy load pages and defer non-critical API calls
- Fix Portfolio page showing different values than header
- Fix AI Reasoning modal missing initial buy log
- Fix Dashboard showing different Account Value than header
- Fix order validation to use correct aggregate BTC value from balance_breakdown
- Fix section numbering: Strategy Parameters shows as 6 for AI, 7 for others
- Add validation to block save when manual order values are below exchange minimum
- Fix NaN warning in strategy parameter inputs
- Frontend: Budget settings only show in AI mode, not Manual mode
- Frontend: Add Max Concurrent Positions to Bot Budget Allocation section
- Frontend: Move Budget Allocation into Strategy Parameters for AI bots
- Fix aggregate BTC calculation: use current prices, not cost basis
- Frontend: Reorganize AI bot settings with conditional budget display
- Manual order sizing: use aggregate value for percentage calculations
- Add Manual Order Sizing group to frontend display order
- Optimize portfolio API: parallel price fetches + fix balance breakdown
- Fix portfolio balance breakdown for legacy positions
- Add 3Commas-style manual order sizing override
- Add MINIMUM PERCENTAGE to AI prompts to prevent below-minimum orders
- Update Claude API link to billing page
- Fix position_status in AI bot logs to show actual status
- Increase AI review timeout to 3 minutes
- Update AI review to scan all Coinbase coins in batches
- Extend tracked coins to include USD and USDC markets
- Redesign BlacklistManager with single table and category dropdowns
- Fix route order: Move /categories before /{symbol} to prevent conflicts
- Revert trailing slashes - endpoint works without them
- Fix: Add trailing slashes to category API endpoints
- Add category trading permissions with toggle UI
- Add weekly AI coin review service
- Add APPROVED coin category with green badges
- Add color-coded blacklist badges: BORDERLINE (yellow), QUESTIONABLE (orange), BLACKLISTED (red)
- Fix blacklist API trailing slash redirect issue
- Add coin blacklist feature
- Add THREE_MINUTE* synthetic candle support via 1-min aggregation
- Fix: Use ONE_MINUTE candles (THREE_MINUTE not supported by Coinbase)
- Support multi-timeframe BB% and faster technical checks
- Add debug logging for BB% take profit condition evaluation
- Add configurable DCA drop settings for AI bots
- Fix broken take profit conditions and add BB% support for AI bots
- Fix volume filter to always analyze pairs with open positions
- Fix deprecated token pricing - don't show misleading values
- Add legacy token price mapping for deprecated tokens
- Fix CoinGecko price fetching for free tier limits
- Add CoinGecko price fetching for DEX token valuations
- Fix DEX portfolio to show all tokens regardless of USD pricing
- Add old GALA token address (v1) for migration compatibility
- Switch to PublicNode RPC endpoints
- Add rate limiting delays and switch to Ankr RPC
- Switch to Cloudflare Ethereum RPC for better rate limits
- Add cUSDC, GALA, MANA tokens to DEX wallet service
- Fix corrupted DAI contract address
- Fix DEX portfolio rendering with optional chaining
- Integrate account filtering across all main pages
- Add account-specific portfolio endpoint with DEX support
- Fix accounts dropdown menu visibility
- Remove unused legacy Trading/MACD parameters from Settings
- Remove legacy Coinbase API credentials section from Settings
- Phase 9: Complete UI account switching integration
- Update handoff document with implementation status
- Phases 6-8: Complete Arbitrage Strategy Implementation
- Phase 5: Account Management & Context Switching
- Fix web3.py v6+ compatibility: Update middleware import
- Phase 4: Complete DEX frontend UI integration
- Phase 3: Complete Uniswap V3 integration with swap execution
- Phase 3: Add DEX client skeleton for Ethereum + Uniswap V3
- Fix order reconciliation monitor to use exchange_client
- Fix settings attribute names in main.py
- Phase 2: Add DEX fields to database schema
- Refactor: Complete exchange abstraction layer (Phase 1)
- Add exchange abstraction layer (Phase 1 foundation)
- Fix MP line to use bot's min_profit_percentage instead of hardcoded 2%
- Implement DCA budget protection to prevent insufficient DCA funds
- Fix AI budget calculation to use per-position budget
- Add Grok AI provider support to client validation
- Skip logging technical-only HOLD checks to reduce UI noise
- Implement two-tier bot checking architecture for efficient monitoring
- Fix Bollinger Band % crossing threshold input and add 3m timeframe
- Add exchange minimum order size requirement to AI prompts
- Add PhaseConditionSelector UI handler to AI Autonomous custom sell conditions
- Fix import error: use IndicatorCalculator class instead of standalone functions
- Add custom technical sell conditions to AI Autonomous strategy
- Replace hardcoded USDC PnL with dynamic API calculations
- Add USDC PnL placeholder cards to match BTC/USD column layout
- Add separate USDC Balance Breakdown column
- Fix budget availability check - add actual BTC balance verification
- Fix Dashboard Edit button to properly navigate and open bot edit modal
- Reorder bot config sections: group all AI-related settings together
- Improve Risk Tolerance UX with Manual option and preset visibility
- Add Duration column to closed positions table
- Sort History page tables by most recent first
- Fix limit order price precision: use product-specific decimals
- Implement product minimum fetching from product_precision.json
- AI aware of product minimums: inform AI and validate before execution
- Fix orphaned positions: mark as failed instead of expunging
- Add hard constraint: DCA only on meaningful drops below cost basis
- Add AI failsafe: auto-sell profitable positions when AI analysis fails
- Remove strict mode - AI bots are now purely AI-directed
- Improve control mode description to clarify AI vs user control
- Add toggle switch for AI bot control mode with conditional parameter display
- Fix AI autonomous strategy parameter handling and reorganization
- Update CLAUDE.md with production notes
- Add unrealized PnL sorting to Holdings table
- Fix USD Balance Breakdown to show only USD-denominated assets
- CRITICAL FIX: DCA failures should not abort entire bot cycle
- Add adaptive limit order with bid fallback
- Fix budget calculation: divide by max_concurrent_deals for fair per-position budget
- Sort closed positions by closure date (most recent first)
- Simplify sell order precision handling to match buy orders
- Add automatic order reconciliation monitor
- Fix market order fill tracking to handle slow fills properly
- Add precision rounding to all sell orders and enable OrderMonitor
- Fix get_order() unwrapping and add precision to strategy limit sells
- Fix limit order precision - use product_precision.json instead of Coinbase API
- Add enhanced error logging for limit order failures
- Fix limit close order size precision
- Implement proper partial fill handling for limit close orders
- Fix History sorting: closed positions now sort by closed_at desc
- Update Phase 5 bug report with Bugs #6 and #7
- Fix Bug #7: AIAutonomousStrategy missing _prepare_market_context
- Add logging to debug Coinbase limit order response format
- Bug #6: Add error logging to limit-close endpoint
- Fix Vite proxy IPv6 issue - use 127.0.0.1 instead of localhost
- Fix syntax error in strategy signatures
- Fix all 5 bugs identified in Phase 5 investigation
- Phase 5: Bug investigation report (no fixes applied)
- Phase 4: Code cleanup - unused variables and imports
- Phase 3: Type hint improvements
- Add HouseKeeping 1.1 progress report
- Phase 2: Code style improvements (PEP 8 compliance)
- Phase 1: Code formatting and documentation improvements
- Fix PEP 8 indentation and spacing issues (E129, E131, E302)
- Update bug investigation - all clear to proceed
- Add detailed potential bugs investigation report
- Add comprehensive code quality analysis for HouseKeeping_1.1
- Add handoff summary section - refactoring complete and ready for merge
- Update verification doc with post-deployment fixes summary
- CRITICAL FIX v5: Remove OLD_BACKUP files from repository
- CRITICAL FIX v4: Correct dependency overrides in main.py
- CRITICAL FIX v3: Change empty path endpoints from "" to "/"
- CRITICAL FIX v2: Remove prefix parameter entirely from sub-routers
- Add router include verification to API signature document
- CRITICAL FIX: Add explicit empty prefix to all sub-routers
- Add deployment instructions for HouseKeeping_1.0 production testing
- HOUSEKEEPING: Refactoring Complete - 7 Major Files Under 500 Lines
- STEP 7: Refactor positions_router.py (804 → 6 modules)
- STEP 6: Refactor bots.py router (760 → 5 modules)
- STEP 5: Add extraction plan for multi_bot_monitor.py
- Add session summary (4/13 files complete)
- Update progress: STEP 4 complete (coinbase_unified_client.py)
- STEP 4.5: Refactor coinbase_unified_client.py into wrapper (~260 lines)
- STEP 4.4: Extract coinbase_api/order_api.py (~300 lines)
- STEP 4.3: Extract coinbase_api/market_data_api.py (~150 lines)
- STEP 4.2: Extract coinbase_api/account_balance_api.py (~300 lines)
- Add STEP 4 detailed status tracking
- STEP 4.1: Extract coinbase_api/auth.py (~220 lines)
- Update progress: STEP 3 complete (trading_engine_v2.py)
- Add detailed completion plan for STEPs 4-13
- STEP 3.6: Refactor trading_engine_v2.py into wrapper class (~180 lines)
- STEP 3.5: Extract signal_processor.py from trading_engine_v2.py (~325 lines)
- STEP 3.4: Extract sell_executor.py from trading_engine_v2.py (~235 lines)
- STEP 3.3: Extract buy_executor.py from trading_engine_v2.py (~330 lines)
- Add comprehensive housekeeping progress tracker
- Document STEP 3 completion plan for trading_engine_v2.py refactoring
- STEP 3.2: Extract order_logger.py from trading_engine_v2.py (119 lines)
- STEP 3.1: Extract position_manager.py from trading_engine_v2.py (99 lines)
- STEP 2.FINAL: Refactor main.py - split into 5 routers (1658 → 133 lines)
- STEP 2.5: Extract system_router.py from main.py (207 lines)
- STEP 2.4: Extract settings_router.py from main.py (159 lines)
- STEP 2.3: Extract market_data_router.py from main.py (196 lines)
- STEP 2.2: Extract account_router.py from main.py (371 lines)
- STEP 2.1: Extract positions_router.py from main.py (769 lines)
- STEP 1.9: Rename original ai_autonomous.py to _OLD_BACKUP.py
- STEP 1.8b: Create main __init__.py to wire all extracted modules together
- STEP 1.8a: Extract strategy_definition.py (230 lines) from ai_autonomous.py
- STEP 1.7: Extract trading_decisions.py module (buy/sell/DCA logic)
- STEP 1.6: Extract market_analysis.py module (market context, web search, caching)
- STEP 1.5: Extract Grok API provider module
- STEP 1.4: Extract Gemini API provider module
- STEP 1.3: Extract Claude API provider module
- STEP 1.2: Extract prompts.py module with all prompt templates
- STEP 1.1: Create ai_autonomous/ directory structure
- Add detailed refactoring plan with 13 steps and risk assessment
- Add HOUSEKEEPING.md documentation for refactoring work
- Fix Portfolio BTC Balance Breakdown calculation
- Add trade statistics columns to Bots table
- Phase 3.1: Add overall PnL to Holdings table
- Phase 2.3 (Part 2): Complete bot limit order close execution logic
- Phase 2.3 (Part 1): Add bot limit order close configuration
- Add AI bot API credit indicators
- Add market close slippage warnings
- Fix: Move Pydantic model definitions before endpoint usage
- Add budget utilization percentage to bot cards
- Add deployment notes for v1.5.0 database migration

## [v0.75.0] - 2025-11-23

- Add limit order monitoring background service
- Add limit order status display and edit/cancel UI
- Add limit close modal UI with bid/ask slider
- Add limit order position closing - backend implementation
- Fix Portfolio BTC Balance Breakdown calculations

## [v0.74.3] - 2025-11-22

- Add cryptocurrency icons to Positions page

## [v0.74.2] - 2025-11-22

- Add sub-badges to Closed and Failed tabs in History page
- Rewrite badge logic to use simple count delta
- Add 1ms to most recent timestamp to properly clear badge
- Fix badge clear to use most recent position timestamp
- Add debug logging for badge count calculation
- Fix History tab badge timer infinite loop

## [v0.74.1] - 2025-11-22

- Suppress React Router v7 future flag warnings
- Add 2% minimum drop requirement for DCA safety orders
- updated to ignore yet another naming convention for db backups :-/

## [v0.74.0] - 2025-11-22

- Add USD value display next to BTC volume in Positions page

## [v0.73.0] - 2025-11-22

- Fix closed positions main table timestamps to use local timezone
- Convert History page timestamps to local timezone

## [v0.72.0] - 2025-11-22

- Add URL-based routing with React Router
- Add BTC/USD price display to header with 2-minute updates
- Show AI reasoning from most recent buy decision onwards
- Add position_id filter to AI bot logs API endpoint
- Link AI decision logs to positions after position creation

## [v0.71.0] - 2025-11-22

- Fix session corruption in batch AI decision logging by expunging failed positions instead of rollback
- Fix duplicate timestamp error in P&L chart by deduplicating data points
- Fix SQLAlchemy async session corruption in AI decision logging
- Fix budget calculation bug preventing bots from scanning for new opportunities
- Fix aggregate BTC calculation to include positions from database

## [v0.70.0] - 2025-11-22

- Use portfolio breakdown for aggregate BTC calculation to include all positions (even those in open trades)
- Fix aggregate BTC calculation by forcing fresh account data + document BTC bot budget rules in CLAUDE.md
- Make aggregate BTC calculation logs visible by changing to logger.warning()
- Add CRITICAL budget calculation documentation to CLAUDE.md
- Fix budget calculation logging visibility - change INFO to WARNING level
- Add Force Run feature for bots
- Use bot's actual budget_percentage in logs instead of hardcoded 90%
- Fix budget calculation: aggregate should be total account BTC value, not just available balance
- Fix double-subtraction bug in budget calculation - available balance already excludes positions
- Remove caching from get_btc_balance() to always fetch fresh balance
- Add Python bytecode cache clearing to bot.sh start/restart commands
- Simplify calculate_aggregate_btc_value to return actual BTC balance
- Fix aggregate BTC calculation to include BTC + BTC pairs only
- Simplify aggregate BTC calculation to use actual BTC balance
- Temporarily disable aggregate BTC cache to debug balance calculation
- Add debug logging to aggregate BTC value calculation
- Fix Coinbase API rate limiting (429 errors) with caching and retries
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Fix budget calculation and config refresh bugs
- Add fallback to get_accounts() when portfolio endpoint returns 403
- Add debugging for History page badge auto-clear timer
- Create backend/scripts folder for one-off helper scripts
- Add auto-clearing timer to History page notification badge
- Trigger immediate re-analysis after position closes
- Fix order fill race condition with retry mechanism
- Fix double budget division bug in trading engine
- Fix critical database session bug preventing batch trades
- Fix double budget division causing orders below Coinbase minimum
- Add debug prints to _get_confidence_threshold_for_action to diagnose threshold issue
- Add debug prints for Grok batch analysis
- Add debug prints to see signal_data in should_buy()
- Add debug prints for budget calculation and should_buy logic
- Add debug prints for result processing loop to find exact hang point
- Add detailed debug prints in process_bot and process_bot_batch to find hang location
- Add debug prints in bot processing loop to find where it hangs
- Add comprehensive debug prints throughout monitor loop
- Use print() instead of logger for debugging - logger not showing in journalctl
- Add debug logging to diagnose why monitor loop isn't running
- Handle 403 rate limit errors gracefully with budget fallback
- Remove debug prints - monitor loop now working correctly
- Add debug prints throughout monitor loop
- Add more debug prints in monitor_loop
- Add debug prints to diagnose monitor loop not starting
- Fix multi-bot monitor not starting - AI bots now trade
- Remove unused bot-level AI Analysis Interval field
- Allow AI Analysis Interval range of 1-1440 minutes instead of 5-120
- Add database backups and temporary test scripts to .gitignore
- Fix execute_buy() to use actual filled amounts from Coinbase
- Reduce sell amount to 99% to handle discrepancy between tracked and actual balances
- Adjust bar chart margins to prevent top-squishing
- Restructure layout to match 3Commas time filter and chart tabs
- Make chart height match sidebar cards height
- Fix chart disposal error when navigating away from Bots page
- Add 'Most profitable bot' card and active trades count
- Improve bar chart tooltips to match 3Commas style
- Restructure P&L chart with sidebar stats like 3Commas
- Fix Summary PnL chart not displaying after switching tabs
- Add daily P&L bar chart for 'PnL by day' tab
- Replace P&L by pair table with bar chart
- Fix P&L endpoint route order - move before {position_id} route
- Add 3Commas-style P&L chart with comprehensive analytics
- Add professional loading spinners to improve UX
- Fix budget allocation to use max_concurrent_deals instead of pair count
- Fix force-close position to use profit_quote instead of profit_btc
- Add automatic deployment system
- Test backend auto-restart
- Test auto-deployment system
- Add deployment script for pulling from git on EC2
- Add percentage gains to Portfolio Totals on Bots page
- Add budget-aware bot monitoring and insufficient funds indicator
- Add red badge to History tab showing new closed positions
- Make site mobile-friendly with responsive layouts
- Add projected PnL display to Bots page
- Update risk tolerance confidence thresholds
- Fix React controlled input warnings in Bots.tsx
- Fix bot stats 500 error and frontend format crash
- Add OpenAI library and document AI strategy dependencies
- Upgrade Anthropic SDK to 0.74.0 to fix AsyncClient initialization error
- Add adaptive AI evaluation intervals and risk-based confidence thresholds
- Pass position and action context to strategy for intelligent web search
- Add DCA arrows to position chart and synthetic candles for entry timing
- Fix bot-macos.sh to only kill server processes, not browser connections
- Create unified AI prompt templates and add bot PnL tracking
- Give AI full control over sell decisions for autonomous bots
- Fix trade type labels: show 'Take Profit' for sell orders instead of 'DCA'
- Add macOS-compatible bot manager script
- Extend AI log time window to include 30s after position close
- Add backfill script to link existing AI logs to positions
- Add expandable closed positions with trade details, duration, and AI reasoning history
- Add failed order tracking and fix portfolio accuracy
- Add batch price endpoint and optimize frontend price fetching
- Add 10 second timeout to Vite API proxy
- Revert to simple f-string formatting that worked for base orders
- Fix API connection by using Vite proxy instead of direct backend URL
- Configure backend to use port 8100, frontend stays on 5173
- Revert frontend to use backend on port 8000
- Update frontend to use backend port 8100
- Fix Coinbase precision - use fixed-width decimal formatting
- Fix limit_price precision and remove hardcoded dev paths
- Consolidate Coinbase API clients into unified implementation
- Apply precision formatting to legacy CoinbaseClient as well
- Fix PREVIEW_INVALID_QUOTE_SIZE_PRECISION error by applying proper precision formatting
- Add retry logic and error tracking for market data failures
- Fix DCA order precision to avoid Coinbase PREVIEW_INVALID_QUOTE_SIZE_PRECISION error
- Fix DCA order size calculation to use position's initial balance
- Update bot.sh to use systemctl for service management
- Fix sell order execution by properly handling Coinbase API response
- Add minimum order size validation warnings to bot creation modal
- Fix import error - use CoinbaseClient directly
- Add minimum order size validation
- Add detailed branch workflow and cleanup instructions
- Add comprehensive development roadmap
- Consolidate documentation into /docs folder
- Fix Coinbase quote size precision error
- Fix TypeScript linting errors
- Improve Coinbase error message extraction
- Add notes and error fields to PositionResponse schema
- Add position notes feature (like 3Commas)
- Add position error tracking and display (like 3Commas)
- Add detailed Coinbase error logging for failed orders
- Fix DCA not triggering due to missing current_price in batch mode
- Fix duplicate AI log entries for batch analysis
- Add comprehensive debug logging to track duplicate AI opinion source
- Fix REAL cause of duplicate AI opinions - double monitor loop start
- Document duplicate AI opinions race condition fix in HANDOFF.md
- Fix duplicate AI opinions race condition
- Extract API_BASE_URL to centralized config
- Add 3Commas-style manual vs automatic DCA tracking
- Document DCA greenlet fix and API rate limit optimization
- Fix greenlet error preventing DCA order evaluation
- Add close position confirmation modal with proper warnings
- Document pending frontend work and known issues in HANDOFF
- Wire up position action buttons with proper handlers
- Improve bot monitoring responsiveness and database stability
- Sell 99.99% to prevent precision/rounding rejections
- Fix critical bug: Require order_id for buy/sell trades
- Integrate order monitor into MultiBotMonitor
- Fix duplicate AI log entries for batch analysis
- Add AI sentiment indicators and DCA visualization, fix bugs
- Add ESC key handler to close bot config modal
- Only show 'All' buttons for markets with available pairs
- Hide unavailable markets instead of graying them out
- Implement 3Commas-style single-market constraint for pair selection
- Reorganize bot configuration form into numbered sections
- Add 3Commas-style pair selection and interval configuration
- Fix Dashboard BotCard profit display error
- Add comprehensive PnL stats broken down by USD/BTC
- Refactor charts: separate oscillator panes with synchronized time scales
- Improve chart indicators: add priceScaleId and MACD/RSI enhancements
- Fix duplicate Entry/Target labels when changing chart type
- Fix price axis disappearing when switching to Heikin-Ashi
- Re-add indicator rendering functionality
- Fix chart: remove stop loss line and use actual profit target from config
- Use actual profit target from bot config instead of hardcoded 2%
- Remove stop loss reference line from chart (not used in strategy)
- Implement full indicator rendering system for TradingView charts
- Fix chart not displaying: use correct 'time' field from API
- Fix chart NaN error by filtering invalid candle data
- Adjust sell confidence threshold to 65%
- Lower AI sell confidence threshold to 50%
- Raise AI confidence threshold to 80% for all trades
- Fix AI ambivalence by adding temperature=0 to all AI calls
- Add order monitoring service for limit orders
- Add limit order support to trading engine
- Add pending_orders_count to API and frontend (Part 3 - Final)
- Add safety_order_type configuration parameter (Part 2)
- Add pending_orders system for limit order tracking (Part 1)
- Fix averaging orders (Avg. O) display to match 3Commas logic
- Add lightweight chart modal option with full programmatic control
- Add position reference prices to chart modal header
- Prevent background page scroll when chart modal is open
- Fix TradingView widget cleanup error on modal close
- Fix TradingView widget initialization error
- Add TradingView chart integration to Active Deals page
- Feature: Add clickable sorting to table column headers
- UX: Add 3Commas-style overall stats panel and simplified filters
- UX: Add 3Commas-style column headers to deals table
- Fix: Display base currency correctly in Volume column
- UX: Remove redundant coin amount from Filled percentage line
- UX: Add smart collision detection for price bar labels
- UX: Redesign price bar to match 3Commas with vertical tick marks
- Fix: Close unclosed Active Deals Section div and fix ternary operator
- Fix: Remove duplicate JSX code causing TypeScript compilation errors
- Major UX: Transform deal cards to 3Commas-style horizontal layout
- Feature: Add 3Commas-style tick marks with labels on Price Movement bar
- Feature: Add 3Commas-style dynamic labels to Price Movement bar
- Fix: Dynamic range for Price Movement bar visualization
- Fix: Use get_current_price() for ticker endpoint
- Fix: Align chart P&L calculation with main position P&L display
- Fix: Resolve greenlet async error (xd2s) in AIBotLog database operations
- Fix: Resolve AIBotLog SQLAlchemy error (7s2a) by fixing context field duplication
- Lint: Fix final architectural errors (E402, F401)
- Lint: Fix all remaining linting errors (E712, F841, F821, E722)
- Lint: Apply Python best practices and fix linting errors
- Fix: Move formatPrice utility to top level to fix DealChart scope error
- Refactor: Migrate to StrategyTradingEngine and remove old TradingEngine
- cleanup: Remove unused price_monitor.py file
- Refactor: Extract middleware to separate module
- docs: Update HANDOFF.md with Step 2 (schema extraction) completion
- Refactor: Extract Pydantic schemas to centralized schemas module
- docs: Update HANDOFF.md with Phase 1 modularization progress
- Refactor: Extract shared indicator utilities to eliminate code duplication
- Restore full Positions.tsx with all features lost in merge
- Restore Gain/Loss metadata line to position charts
- Housekeeping: Clean up old files and improve gitignore
- Fix: Replace totalProfitBTC with totalProfitQuote in Dashboard
- Fix: Update Positions.tsx field names for multi-currency support
- Fix: Re-apply timezone-aware date formatting to Positions page after merge
- Complete bot balance isolation system and fix portfolio/timezone issues
- Add modular multi-quote currency support (BTC + USD) - Phase 1
- Move closed positions to separate History page
- Update price indicator label from 'Entry' to 'Avg Entry'
- Add visual price movement indicator to position cards
- Fix Current Profit showing 0% in compact position view
- Fix USD currency display in positions/deals
- Fix frontend display of USD prices in AI Bot Logs
- Fix USD price display formatting in AI logs
- Fix Grok model name and implement Claude batch analysis
- Use candle data for current price instead of unreliable ticker API
- Fix AI bot logging to only process pairs with valid market data
- Fix AI Bot price data collection for batch analysis
- Enhance DealChart with full Charts page functionality
- Add bot name display to position details
- Fix hardcoded currency symbols in position details
- Fix crypto price precision for AI analysis
- Fix KeyError when candles are empty
- Add Grok support + optimize batch analysis for position quota
- Add Grok AI support with batch analysis
- WIP: Add batch AI analysis for multi-pair bots
- Add per-bot check_interval with AI provider-specific defaults
- Add position-specific AI logs modal
- Fix API quota issues - increase monitor interval to 10min and fix middleware
- Fix price display in AI logs and add product_id to positions
- Fix critical trade execution bug - trades now execute successfully
- Add transaction rollback: positions only persist if trade succeeds
- Update handoff: Monitor likely not starting - key hypothesis identified
- Add comprehensive handoff document for trade execution bug investigation
- Add debug logging to trace trade execution failure
- Fix critical database transaction conflicts preventing trades
- Add product_id to AI bot logs API response
- Add profit calculation method option (cost_basis vs base_order)
- Fix product_id bug and implement parallel batch processing
- Fix division by zero error in AI autonomous strategy
- Fix AI logs to show AI's actual recommendation, not bot's action
- Change hold icon from Minus to CircleDot for better clarity
- Add trading pair to AI logs + UI improvements
- Fix AI autonomous bot analysis and reasoning logs
- Implement smart budget division by max concurrent deals
- Add max concurrent deals and AI provider display
- Update checklist: Mark AI features and 3Commas UI as complete
- Add AI provider API key fields to Settings config
- Add AI provider selection, dynamic trading pairs, and 3Commas-style UI
- Final session update: Mark all completed features in checklist
- Add AI bot reasoning logs and custom instructions
- Update checklist: mark clone bots and AI log infrastructure as complete
- Add Clone Bots and AI Reasoning Log features
- Fix: Stopped bots now continue managing existing positions
- Update checklist: mark trailing TP/SL as complete
- Add proper trailing take profit and trailing stop loss
- Add .claude/ and .pids/ to gitignore
- Update README with AI bot and all new features
- Add comprehensive handoff document for laptop migration
- Add AI Autonomous Trading Bot powered by Claude AI
- Update checklist: mark bot templates as complete
- Add bot templates system with default presets
- Update checklist: mark multi-pair bots and budget splitting as complete
- Add budget splitting option for multi-pair bots
- Add multi-pair bot UI - frontend implementation
- WIP: Multi-pair bots backend implementation
- Update checklist with recent completed features
- Fix bot Edit button not working on Dashboard
- Add real-time price updates to Deals page
- Add safety order price level visualization to deal charts
- Add Take Profit and Stop Loss lines to deal charts
- Update settings
- Add multi-pair bots to roadmap as critical 3Commas feature
- Update checklist with dashboard overhaul completion
- Overhaul Dashboard with 3Commas-style metrics and recent deals
- Add product_id tracking to positions for accurate chart display
- Implement 3Commas-style DCA bot platform with full deal management
- Add crossing above/below operators to all applicable indicators
- Refactor to true 3Commas-style phase-based conditions
- Add comprehensive user guide for conditional strategy builder
- Implement 3Commas-style conditional DCA strategy system
- Add Heikin-Ashi candle option to Charts page
- Implement advanced charting with TradingView-style indicators
- Fix chart error handling and port management
- Fix lightweight-charts v5 API - use correct method names
- Add comprehensive documentation
- Fix lightweight-charts v5 API compatibility
- Initial commit: ETH/BTC trading bot with TradingView-style charts

