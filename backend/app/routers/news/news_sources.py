"""
News and video source configurations.

Categories:
- CryptoCurrency: Crypto-specific news and videos
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

    # ===== World =====
    "reuters_world": {
        "name": "Reuters World",
        "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "type": "rss",
        "website": "https://www.reuters.com/world",
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
        "url": "https://apnews.com/apf-topnews/feed",
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
    "marketwatch": {
        "name": "MarketWatch",
        "url": "https://www.marketwatch.com/rss/topstories",
        "type": "rss",
        "website": "https://www.marketwatch.com",
        "category": "Business",
    },
    "wsj_markets": {
        "name": "WSJ Markets",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "type": "rss",
        "website": "https://www.wsj.com/news/markets",
        "category": "Business",
    },

    # ===== Technology =====
    "techcrunch": {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "type": "rss",
        "website": "https://techcrunch.com",
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
    "ew": {
        "name": "Entertainment Weekly",
        "url": "https://ew.com/feed/",
        "type": "rss",
        "website": "https://ew.com",
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
    "bleacher_report": {
        "name": "Bleacher Report",
        "url": "https://bleacherreport.com/articles/feed",
        "type": "rss",
        "website": "https://bleacherreport.com",
        "category": "Sports",
    },
    "sports_illustrated": {
        "name": "Sports Illustrated",
        "url": "https://www.si.com/rss/si_topstories.rss",
        "type": "rss",
        "website": "https://www.si.com",
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
    "medical_news": {
        "name": "Medical News Today",
        "url": "https://www.medicalnewstoday.com/rss",
        "type": "rss",
        "website": "https://www.medicalnewstoday.com",
        "category": "Health",
    },
    "health_news": {
        "name": "Healthline",
        "url": "https://www.healthline.com/rss",
        "type": "rss",
        "website": "https://www.healthline.com",
        "category": "Health",
    },
    "webmd": {
        "name": "WebMD",
        "url": "https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC",
        "type": "rss",
        "website": "https://www.webmd.com",
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
}
