"""
News and video source configurations.

Categories:
- CryptoCurrency: Crypto-specific news and videos
- AI: Artificial intelligence news and research
- Finance: Traditional finance, markets, and investing
- World: International news
- Nation: US national news
- Business: Business and finance
- Technology: Tech industry news
- Entertainment: Movies, TV, music
- Sports: Sports news
- Science: Scientific discoveries
- Health: Health and medical news
"""

# Available news categories
NEWS_CATEGORIES = [
    "CryptoCurrency",
    "AI",
    "Finance",
    "World",
    "Nation",
    "Business",
    "Technology",
    "Entertainment",
    "Sports",
    "Science",
    "Health",
]

# News sources configuration
NEWS_SOURCES = {
    # ===== CryptoCurrency =====
    "reddit_crypto": {
        "name": "Reddit r/CryptoCurrency",
        "url": "https://www.reddit.com/r/CryptoCurrency/hot.json?limit=15",
        "type": "reddit",
        "website": "https://www.reddit.com/r/CryptoCurrency",
        "category": "CryptoCurrency",
    },
    "reddit_bitcoin": {
        "name": "Reddit r/Bitcoin",
        "url": "https://www.reddit.com/r/Bitcoin/hot.json?limit=10",
        "type": "reddit",
        "website": "https://www.reddit.com/r/Bitcoin",
        "category": "CryptoCurrency",
    },
    "coindesk": {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss",
        "website": "https://www.coindesk.com",
        "category": "CryptoCurrency",
    },
    "cointelegraph": {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss",
        "type": "rss",
        "website": "https://cointelegraph.com",
        "category": "CryptoCurrency",
    },
    "decrypt": {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "type": "rss",
        "website": "https://decrypt.co",
        "category": "CryptoCurrency",
    },
    "theblock": {
        "name": "The Block",
        "url": "https://www.theblock.co/rss.xml",
        "type": "rss",
        "website": "https://www.theblock.co",
        "category": "CryptoCurrency",
    },
    "cryptoslate": {
        "name": "CryptoSlate",
        "url": "https://cryptoslate.com/feed/",
        "type": "rss",
        "website": "https://cryptoslate.com",
        "category": "CryptoCurrency",
    },
    "bitcoin_magazine": {
        "name": "Bitcoin Magazine",
        "url": "https://bitcoinmagazine.com/feed",
        "type": "rss",
        "website": "https://bitcoinmagazine.com",
        "category": "CryptoCurrency",
    },
    "blockworks": {
        "name": "Blockworks",
        "url": "https://blockworks.co/feed",
        "type": "rss",
        "website": "https://blockworks.co",
        "category": "CryptoCurrency",
    },

    # ===== AI =====
    "reddit_artificial": {
        "name": "Reddit r/artificial",
        "url": "https://www.reddit.com/r/artificial/hot.json?limit=15",
        "type": "reddit",
        "website": "https://www.reddit.com/r/artificial",
        "category": "AI",
    },
    "openai_blog": {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "type": "rss",
        "website": "https://openai.com/blog",
        "category": "AI",
    },
    "mit_tech_ai": {
        "name": "MIT Tech Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "type": "rss",
        "website": "https://www.technologyreview.com/topic/artificial-intelligence",
        "category": "AI",
    },
    "the_ai_beat": {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "type": "rss",
        "website": "https://venturebeat.com/category/ai",
        "category": "AI",
    },

    # ===== Finance =====
    "yahoo_finance_news": {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "type": "rss",
        "website": "https://finance.yahoo.com",
        "category": "Finance",
    },
    "motley_fool": {
        "name": "Motley Fool",
        "url": "https://www.fool.com/feeds/index.aspx",
        "type": "rss",
        "website": "https://www.fool.com",
        "category": "Finance",
    },
    "kiplinger": {
        "name": "Kiplinger",
        "url": "https://www.kiplinger.com/feed/all",
        "type": "rss",
        "website": "https://www.kiplinger.com",
        "category": "Finance",
    },

    # ===== World =====
    "guardian_world": {
        "name": "The Guardian World",
        "url": "https://www.theguardian.com/world/rss",
        "type": "rss",
        "website": "https://www.theguardian.com/world",
        "category": "World",
    },
    "bbc_world": {
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "type": "rss",
        "website": "https://www.bbc.com/news/world",
        "category": "World",
    },
    "al_jazeera": {
        "name": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "type": "rss",
        "website": "https://www.aljazeera.com",
        "category": "World",
    },

    # ===== Nation (US) =====
    "npr_news": {
        "name": "NPR News",
        "url": "https://feeds.npr.org/1001/rss.xml",
        "type": "rss",
        "website": "https://www.npr.org",
        "category": "Nation",
    },
    "pbs_newshour": {
        "name": "PBS NewsHour",
        "url": "https://www.pbs.org/newshour/feeds/rss/headlines",
        "type": "rss",
        "website": "https://www.pbs.org/newshour",
        "category": "Nation",
    },
    "ap_news": {
        "name": "AP News",
        "url": "https://feedx.net/rss/ap.xml",
        "type": "rss",
        "website": "https://apnews.com",
        "category": "Nation",
    },

    # ===== Business =====
    "cnbc_business": {
        "name": "CNBC",
        "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
        "type": "rss",
        "website": "https://www.cnbc.com",
        "category": "Business",
    },
    "business_insider": {
        "name": "Business Insider",
        "url": "https://www.businessinsider.com/rss",
        "type": "rss",
        "website": "https://www.businessinsider.com",
        "category": "Business",
    },

    # ===== Technology =====
    "engadget": {
        "name": "Engadget",
        "url": "https://www.engadget.com/rss.xml",
        "type": "rss",
        "website": "https://www.engadget.com",
        "category": "Technology",
    },
    "ars_technica": {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "type": "rss",
        "website": "https://arstechnica.com",
        "category": "Technology",
    },
    "the_verge": {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "type": "rss",
        "website": "https://www.theverge.com",
        "category": "Technology",
    },
    "wired": {
        "name": "Wired",
        "url": "https://www.wired.com/feed/rss",
        "type": "rss",
        "website": "https://www.wired.com",
        "category": "Technology",
    },

    # ===== Entertainment =====
    "variety": {
        "name": "Variety",
        "url": "https://variety.com/feed/",
        "type": "rss",
        "website": "https://variety.com",
        "category": "Entertainment",
    },
    "hollywood_reporter": {
        "name": "Hollywood Reporter",
        "url": "https://www.hollywoodreporter.com/feed/",
        "type": "rss",
        "website": "https://www.hollywoodreporter.com",
        "category": "Entertainment",
    },
    "deadline": {
        "name": "Deadline",
        "url": "https://deadline.com/feed/",
        "type": "rss",
        "website": "https://deadline.com",
        "category": "Entertainment",
    },

    # ===== Sports =====
    "espn": {
        "name": "ESPN",
        "url": "https://www.espn.com/espn/rss/news",
        "type": "rss",
        "website": "https://www.espn.com",
        "category": "Sports",
    },
    "cbs_sports": {
        "name": "CBS Sports",
        "url": "https://www.cbssports.com/rss/headlines/",
        "type": "rss",
        "website": "https://www.cbssports.com",
        "category": "Sports",
    },
    "yahoo_sports": {
        "name": "Yahoo Sports",
        "url": "https://sports.yahoo.com/rss/",
        "type": "rss",
        "website": "https://sports.yahoo.com",
        "category": "Sports",
    },

    # ===== Science =====
    "science_daily": {
        "name": "Science Daily",
        "url": "https://www.sciencedaily.com/rss/all.xml",
        "type": "rss",
        "website": "https://www.sciencedaily.com",
        "category": "Science",
    },
    "nasa": {
        "name": "NASA",
        "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "type": "rss",
        "website": "https://www.nasa.gov",
        "category": "Science",
    },
    "new_scientist": {
        "name": "New Scientist",
        "url": "https://www.newscientist.com/feed/home/",
        "type": "rss",
        "website": "https://www.newscientist.com",
        "category": "Science",
    },

    # ===== Health =====
    "stat_news": {
        "name": "STAT News",
        "url": "https://www.statnews.com/feed/",
        "type": "rss",
        "website": "https://www.statnews.com",
        "category": "Health",
    },
    "npr_health": {
        "name": "NPR Health",
        "url": "https://feeds.npr.org/103537970/rss.xml",
        "type": "rss",
        "website": "https://www.npr.org/sections/health",
        "category": "Health",
    },
    "science_daily_health": {
        "name": "Science Daily Health",
        "url": "https://www.sciencedaily.com/rss/health_medicine.xml",
        "type": "rss",
        "website": "https://www.sciencedaily.com",
        "category": "Health",
    },
    "medical_xpress": {
        "name": "Medical Xpress",
        "url": "https://medicalxpress.com/rss-feed/",
        "type": "rss",
        "website": "https://medicalxpress.com",
        "category": "Health",
    },
    "the_lancet": {
        "name": "The Lancet",
        "url": "https://www.thelancet.com/rssfeed/lancet_online.xml",
        "type": "rss",
        "website": "https://www.thelancet.com",
        "category": "Health",
    },
    "nature_medicine": {
        "name": "Nature Medicine",
        "url": "https://www.nature.com/nm.rss",
        "type": "rss",
        "website": "https://www.nature.com/nm",
        "category": "Health",
    },
    "genetic_engineering_news": {
        "name": "Genetic Engineering News",
        "url": "https://www.genengnews.com/feed/",
        "type": "rss",
        "website": "https://www.genengnews.com",
        "category": "Health",
    },
    "who_news": {
        "name": "WHO News",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
        "type": "rss",
        "website": "https://www.who.int",
        "category": "Health",
    },
    "nutrition_org": {
        "name": "Nutrition.org",
        "url": "https://nutrition.org/feed/",
        "type": "rss",
        "website": "https://nutrition.org",
        "category": "Health",
    },
    "self_wellness": {
        "name": "SELF",
        "url": "https://www.self.com/feed/rss",
        "type": "rss",
        "website": "https://www.self.com",
        "category": "Health",
    },
}

# YouTube video sources - most reputable crypto channels
VIDEO_SOURCES = {
    "coin_bureau": {
        "name": "Coin Bureau",
        "channel_id": "UCqK_GSMbpiV8spgD3ZGloSw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw",
        "website": "https://www.youtube.com/@CoinBureau",
        "description": "Educational crypto content & analysis",
        "category": "CryptoCurrency",
    },
    "benjamin_cowen": {
        "name": "Benjamin Cowen",
        "channel_id": "UCRvqjQPSeaWn-uEx-w0XOIg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg",
        "website": "https://www.youtube.com/@intothecryptoverse",
        "description": "Technical analysis & market cycles",
        "category": "CryptoCurrency",
    },
    "altcoin_daily": {
        "name": "Altcoin Daily",
        "channel_id": "UCbLhGKVY-bJPcawebgtNfbw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw",
        "website": "https://www.youtube.com/@AltcoinDaily",
        "description": "Daily crypto news & updates",
        "category": "CryptoCurrency",
    },
    "bankless": {
        "name": "Bankless",
        "channel_id": "UCAl9Ld79qaZxp9JzEOwd3aA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA",
        "website": "https://www.youtube.com/@Bankless",
        "description": "Ethereum & DeFi ecosystem",
        "category": "CryptoCurrency",
    },
    "the_defiant": {
        "name": "The Defiant",
        "channel_id": "UCL0J4MLEdLP0-UyLu0hCktg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg",
        "website": "https://www.youtube.com/@TheDefiant",
        "description": "DeFi news & interviews",
        "category": "CryptoCurrency",
    },
    "crypto_banter": {
        "name": "Crypto Banter",
        "channel_id": "UCN9Nj4tjXbVTLYWN0EKly_Q",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q",
        "website": "https://www.youtube.com/@CryptoBanter",
        "description": "Live crypto shows & trading",
        "category": "CryptoCurrency",
    },
    "datadash": {
        "name": "DataDash",
        "channel_id": "UCCatR7nWbYrkVXdxXb4cGXw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCCatR7nWbYrkVXdxXb4cGXw",
        "website": "https://www.youtube.com/@DataDash",
        "description": "Macro markets & crypto analysis",
        "category": "CryptoCurrency",
    },
    "cryptosrus": {
        "name": "CryptosRUs",
        "channel_id": "UCI7M65p3A-D3P4v5qW8POxQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCI7M65p3A-D3P4v5qW8POxQ",
        "website": "https://www.youtube.com/@CryptosRUs",
        "description": "Market analysis & project reviews",
        "category": "CryptoCurrency",
    },
    "the_moon": {
        "name": "The Moon",
        "channel_id": "UCc4Rz_T9Sb1w5rqqo9pL1Og",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCc4Rz_T9Sb1w5rqqo9pL1Og",
        "website": "https://www.youtube.com/@TheMoonCarl",
        "description": "Daily Bitcoin analysis & news",
        "category": "CryptoCurrency",
    },
    "digital_asset_news": {
        "name": "Digital Asset News",
        "channel_id": "UCJgHxpqfhWEEjYH9cLXqhIQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJgHxpqfhWEEjYH9cLXqhIQ",
        "website": "https://www.youtube.com/@DigitalAssetNews",
        "description": "Bite-sized crypto news updates",
        "category": "CryptoCurrency",
    },
    "paul_barron": {
        "name": "Paul Barron Network",
        "channel_id": "UC4VPa7EOvObpyCRI4YKRQRw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC4VPa7EOvObpyCRI4YKRQRw",
        "website": "https://www.youtube.com/@paulbarronnetwork",
        "description": "Tech, AI & crypto intersection",
        "category": "CryptoCurrency",
    },
    "lark_davis": {
        "name": "Lark Davis",
        "channel_id": "UCl2oCaw8hdR_kbqyqd2klIA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCl2oCaw8hdR_kbqyqd2klIA",
        "website": "https://www.youtube.com/@TheCryptoLark",
        "description": "Altcoin analysis & opportunities",
        "category": "CryptoCurrency",
    },
    "pompliano": {
        "name": "Anthony Pompliano",
        "channel_id": "UCevXpeL8cNyAnww-NqJ4m2w",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCevXpeL8cNyAnww-NqJ4m2w",
        "website": "https://www.youtube.com/@AnthonyPompliano",
        "description": "Bitcoin advocate & market commentary",
        "category": "CryptoCurrency",
    },
    "whiteboard_crypto": {
        "name": "Whiteboard Crypto",
        "channel_id": "UCsYYksPHiGqXHPoHI-fm5sg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsYYksPHiGqXHPoHI-fm5sg",
        "website": "https://www.youtube.com/@WhiteboardCrypto",
        "description": "Educational crypto explainers",
        "category": "CryptoCurrency",
    },

    # ===== AI =====
    "two_minute_papers": {
        "name": "Two Minute Papers",
        "channel_id": "UCbfYPyITQ-7l4upoX8nvctg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg",
        "website": "https://www.youtube.com/@TwoMinutePapers",
        "description": "AI research explained in short videos",
        "category": "AI",
    },
    "ai_explained": {
        "name": "AI Explained",
        "channel_id": "UCNJ1Ymd5yFuUPtn21xtRbbw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw",
        "website": "https://www.youtube.com/@aiaborz",
        "description": "Clear AI news and explanations",
        "category": "AI",
    },
    "matt_wolfe": {
        "name": "Matt Wolfe",
        "channel_id": "UCJtUOos_MwJa_Ewii-R3cJA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJtUOos_MwJa_Ewii-R3cJA",
        "website": "https://www.youtube.com/@maborz",
        "description": "AI tools, news & tutorials",
        "category": "AI",
    },

    # ===== Finance =====
    "financial_times": {
        "name": "Financial Times",
        "channel_id": "UCoUxsWakJucWg46KW5RsvPw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCoUxsWakJucWg46KW5RsvPw",
        "website": "https://www.youtube.com/@FinancialTimes",
        "description": "Financial news and analysis",
        "category": "Finance",
    },
    "graham_stephan": {
        "name": "Graham Stephan",
        "channel_id": "UCV6KDgJskWaEckne5aPA0aQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCV6KDgJskWaEckne5aPA0aQ",
        "website": "https://www.youtube.com/@GrahamStephan",
        "description": "Personal finance & investing",
        "category": "Finance",
    },

    # ===== World =====
    "wion": {
        "name": "WION",
        "channel_id": "UCWEIPvoxRwn6llPOIn555rQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCWEIPvoxRwn6llPOIn555rQ",
        "website": "https://www.youtube.com/@WIONews",
        "description": "World Is One News - international coverage",
        "category": "World",
    },
    "dw_news": {
        "name": "DW News",
        "channel_id": "UCknLrEdhRCp1aegoMqRaCZg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCknLrEdhRCp1aegoMqRaCZg",
        "website": "https://www.youtube.com/@daborintv",
        "description": "Deutsche Welle international news",
        "category": "World",
    },
    "channel4_news": {
        "name": "Channel 4 News",
        "channel_id": "UCTrQ7HXWRRxr7OsOtodr2_w",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCTrQ7HXWRRxr7OsOtodr2_w",
        "website": "https://www.youtube.com/@Channel4News",
        "description": "UK-based international news coverage",
        "category": "World",
    },

    # ===== Nation (US) =====
    "pbs_newshour_yt": {
        "name": "PBS NewsHour",
        "channel_id": "UC6ZFN9Tx6xh-skXCuRHCDpQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6ZFN9Tx6xh-skXCuRHCDpQ",
        "website": "https://www.youtube.com/@PBSNewsHour",
        "description": "In-depth US national news",
        "category": "Nation",
    },
    "nbc_news": {
        "name": "NBC News",
        "channel_id": "UCeY0bbntWzzVIaj2z3QigXg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCeY0bbntWzzVIaj2z3QigXg",
        "website": "https://www.youtube.com/@NBCNews",
        "description": "Major US network news",
        "category": "Nation",
    },
    "abc_news": {
        "name": "ABC News",
        "channel_id": "UCBi2mrWuNuyYy4gbM6fU18Q",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCBi2mrWuNuyYy4gbM6fU18Q",
        "website": "https://www.youtube.com/@ABCNews",
        "description": "Major US network news",
        "category": "Nation",
    },

    # ===== Business =====
    "cnbc_yt": {
        "name": "CNBC",
        "channel_id": "UCvJJ_dzjViJCoLf5uKUTwoA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCvJJ_dzjViJCoLf5uKUTwoA",
        "website": "https://www.youtube.com/@CNBC",
        "description": "Business and financial news",
        "category": "Business",
    },
    "bloomberg": {
        "name": "Bloomberg Television",
        "channel_id": "UCIALMKvObZNtJ6AmdCLP7Lg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCIALMKvObZNtJ6AmdCLP7Lg",
        "website": "https://www.youtube.com/@bloombergtv",
        "description": "Global business and financial news",
        "category": "Business",
    },
    "yahoo_finance": {
        "name": "Yahoo Finance",
        "channel_id": "UCEAZeUIeJs0IjQiqTCdVSIg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCEAZeUIeJs0IjQiqTCdVSIg",
        "website": "https://www.youtube.com/@YahooFinance",
        "description": "Financial news and market analysis",
        "category": "Business",
    },

    # ===== Technology =====
    "mkbhd": {
        "name": "Marques Brownlee",
        "channel_id": "UCBJycsmduvYEL83R_U4JriQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCBJycsmduvYEL83R_U4JriQ",
        "website": "https://www.youtube.com/@mkbhd",
        "description": "Tech reviews and commentary",
        "category": "Technology",
    },
    "linus_tech_tips": {
        "name": "Linus Tech Tips",
        "channel_id": "UCXuqSBlHAE6Xw-yeJA0Tunw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCXuqSBlHAE6Xw-yeJA0Tunw",
        "website": "https://www.youtube.com/@LinusTechTips",
        "description": "Tech reviews and builds",
        "category": "Technology",
    },
    "the_verge_yt": {
        "name": "The Verge",
        "channel_id": "UCddiUEpeqJcYeBxX1IVBKvQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCddiUEpeqJcYeBxX1IVBKvQ",
        "website": "https://www.youtube.com/@TheVerge",
        "description": "Technology news and reviews",
        "category": "Technology",
    },

    # ===== Entertainment =====
    "screen_junkies": {
        "name": "Screen Junkies",
        "channel_id": "UCOpcACMWblDls9Z6GERVi1A",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCOpcACMWblDls9Z6GERVi1A",
        "website": "https://www.youtube.com/@ScreenJunkies",
        "description": "Movie commentary and Honest Trailers",
        "category": "Entertainment",
    },
    "collider": {
        "name": "Collider",
        "channel_id": "UC5hX0jtOEAobccb2dvSnYbw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC5hX0jtOEAobccb2dvSnYbw",
        "website": "https://www.youtube.com/@Collider",
        "description": "Movies and TV discussion",
        "category": "Entertainment",
    },
    "ign": {
        "name": "IGN",
        "channel_id": "UCKy1dAqELo0zrOtPkf0eTMw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCKy1dAqELo0zrOtPkf0eTMw",
        "website": "https://www.youtube.com/@IGN",
        "description": "Gaming and entertainment news",
        "category": "Entertainment",
    },

    # ===== Sports =====
    "espn_yt": {
        "name": "ESPN",
        "channel_id": "UCiWLfSweyRNmLpgEHekhoAg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCiWLfSweyRNmLpgEHekhoAg",
        "website": "https://www.youtube.com/@espn",
        "description": "Sports news and highlights",
        "category": "Sports",
    },
    "cbs_sports_yt": {
        "name": "CBS Sports",
        "channel_id": "UCja8sZ2T4ylIqjggA1Zuukg",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCja8sZ2T4ylIqjggA1Zuukg",
        "website": "https://www.youtube.com/@CBSSports",
        "description": "Sports coverage and analysis",
        "category": "Sports",
    },
    "pat_mcafee": {
        "name": "The Pat McAfee Show",
        "channel_id": "UCxcTeAKWJca6XyJ37_ZoKIQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxcTeAKWJca6XyJ37_ZoKIQ",
        "website": "https://www.youtube.com/@ThePatMcAfeeShow",
        "description": "Sports talk and commentary",
        "category": "Sports",
    },

    # ===== Science =====
    "veritasium": {
        "name": "Veritasium",
        "channel_id": "UCHnyfMqiRRG1u-2MsSQLbXA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCHnyfMqiRRG1u-2MsSQLbXA",
        "website": "https://www.youtube.com/@veritasium",
        "description": "Science education and experiments",
        "category": "Science",
    },
    "kurzgesagt": {
        "name": "Kurzgesagt",
        "channel_id": "UCsXVk37bltHxD1rDPwtNM8Q",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q",
        "website": "https://www.youtube.com/@kurzgesagt",
        "description": "Animated science explainers",
        "category": "Science",
    },
    "smarter_every_day": {
        "name": "SmarterEveryDay",
        "channel_id": "UC6107grRI4m0o2-emgoDnAA",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6107grRI4m0o2-emgoDnAA",
        "website": "https://www.youtube.com/@smartereveryday",
        "description": "Science and engineering exploration",
        "category": "Science",
    },

    # ===== Health =====
    "doctor_mike": {
        "name": "Doctor Mike",
        "channel_id": "UC0QHWhjbe5fGJEPz3sVb6nw",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC0QHWhjbe5fGJEPz3sVb6nw",
        "website": "https://www.youtube.com/@DoctorMike",
        "description": "Medical education and health advice",
        "category": "Health",
    },
    "medlife_crisis": {
        "name": "Medlife Crisis",
        "channel_id": "UCgRBRE1DUP2w7HTH9j_L4OQ",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCgRBRE1DUP2w7HTH9j_L4OQ",
        "website": "https://www.youtube.com/@MedlifeCrisis",
        "description": "Medical topics from a cardiologist",
        "category": "Health",
    },
    "dr_eric_berg": {
        "name": "Dr. Eric Berg DC",
        "channel_id": "UC3w193M5tYPJqF0Hi-7U-2g",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC3w193M5tYPJqF0Hi-7U-2g",
        "website": "https://www.youtube.com/@drberg",
        "description": "Health and nutrition advice",
        "category": "Health",
    },
}
