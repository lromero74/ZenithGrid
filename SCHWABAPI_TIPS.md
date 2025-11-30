Here’s a straightforward, beginner-friendly overview of the **Charles Schwab / TD Ameritrade API** (the one you use for thinkorswim bot trading) as of late 2025:

| Category              | What It Is / Does                                      | Key Details You’ll Care About for Bot Trading |
|-----------------------|--------------------------------------------------------|-----------------------------------------------|
| **Official Name**     | Schwab Trading Services API (formerly TD Ameritrade API) | Same API thinkorswim bots have always used |
| **Authentication**    | OAuth 2.0 (user-based, not just app keys)              | You must log in with your real Schwab username/password the first time (or use a refresh token afterward). No way around this for live trading. |
| **Base URL**          | https://api.schwab.com or https://api.tdameritrade.com (both still work) | Schwab is slowly migrating everything to api.schwab.com |
| **Main Endpoints You’ll Use for Bots** |                                                        |                                               |
| Quotes                | GET /marketdata/v1/pricehistory                        | Streaming & historical bars (1m, 5m, daily, etc.) |
| Real-time streaming   | WebSocket at wss://streamer.schwab.com                 | Level 1 quotes, chart data, time & sale – essential for fast bots |
| Account & Positions   | GET /trader/v1/accounts/{accountNumber}                | See cash, positions, buying power |
| Place Order           | POST /trader/v1/accounts/{accountNumber}/orders        | Market, limit, stop, OCO, multi-leg options, etc. |
| Replace/Cancel Order  | PUT or DELETE on the same orders endpoint             |                                               |
| Option Chains         | GET /marketdata/v1/optionchains                        | Build spreads automatically |
| Rate Limits           | ≈ 120 requests per minute per access token (non-streaming) | Streaming has its own limits (usually generous) |
| Languages / Libraries | Official: none<br>Community: very good unofficial ones | Python: tda-api (most popular), schwab-api, td-ameritrade-python-api<br>Node.js, C#, etc. also exist |
| Sandbox / Paper Trading | Yes – separate developer sandbox + your regular paperMoney account | Sandbox uses fake data; paperMoney uses delayed but real market data |
| Cost                  | Completely free (no monthly fees)                      | Only your normal Schwab commissions apply when you go live |

### Quick “Hello World” Example in Python (using the popular tda-api library)
```python
from tda import auth, client

# Log in once and it saves a token.json file
c = auth.client_from_token_file('token.json', 'YOUR_API_KEY')
# If first time:
# c = auth.client_from_login_flow('YOUR_API_KEY', 'redirect_uri', 'token.json')

# Get real-time price
resp = c.get_price_history('AAPL', period_type=client.Client.PriceHistory.PeriodType.DAY,
                            frequency_type=client.Client.PriceHistory.FrequencyType.MINUTE,
                            frequency=1)
print(resp.json()['candles'][-1]['close'])

# Place a market order (paper account)
order = client.Client.build_order_market_buy('AAPL', 1)
c.place_order('your-account-hash', order)
```

### Things That Trip Up Almost Every New Bot Developer
1. You have to re-authenticate every 90 days (refresh tokens last 90 days).
2. The account number in the URL is the hashed version (not your visible account number). The library usually grabs it for you.
3. Streaming (WebSocket) is where the speed comes from – polling HTTP every second will feel slow and hit rate limits.
4. Options orders are JSON monsters (you usually build them with the library’s helpers).

If you just want to get something running quickly in 2025, start with:
- https://github.com/alexgolec/tda-api (Python) – best docs and examples
- https://github.com/areed1192/schwab-api (also excellent)

That’s the 80 % of the API you’ll actually use for most bots.
