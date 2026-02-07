import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False  # Disable autoflush to avoid greenlet issues
)


async def get_db():
    async with async_session_maker() as session:
        yield session


# Default content sources for news and videos
# Format: (source_key, name, type, url, website, description, channel_id, category)
DEFAULT_CONTENT_SOURCES = [
    # ===== CryptoCurrency =====
    ('reddit_crypto', 'Reddit r/CryptoCurrency', 'news', 'https://www.reddit.com/r/CryptoCurrency/hot.json?limit=15', 'https://www.reddit.com/r/CryptoCurrency', 'Community-driven crypto discussion', None, 'CryptoCurrency'),
    ('reddit_bitcoin', 'Reddit r/Bitcoin', 'news', 'https://www.reddit.com/r/Bitcoin/hot.json?limit=10', 'https://www.reddit.com/r/Bitcoin', 'Bitcoin-focused community news', None, 'CryptoCurrency'),
    ('bitcoin_magazine', 'Bitcoin Magazine', 'news', 'https://bitcoinmagazine.com/feed', 'https://bitcoinmagazine.com', 'Bitcoin news, analysis & culture', None, 'CryptoCurrency'),
    ('beincrypto', 'BeInCrypto', 'news', 'https://beincrypto.com/feed/', 'https://beincrypto.com', 'Crypto news, guides & price analysis', None, 'CryptoCurrency'),
    ('blockworks', 'Blockworks', 'news', 'https://blockworks.co/feed', 'https://blockworks.co', 'Crypto & DeFi institutional news', None, 'CryptoCurrency'),
    ('coindesk', 'CoinDesk', 'news', 'https://www.coindesk.com/arc/outboundfeeds/rss/', 'https://www.coindesk.com', 'Crypto news & analysis', None, 'CryptoCurrency'),
    ('cointelegraph', 'CoinTelegraph', 'news', 'https://cointelegraph.com/rss', 'https://cointelegraph.com', 'Blockchain & crypto news', None, 'CryptoCurrency'),
    ('decrypt', 'Decrypt', 'news', 'https://decrypt.co/feed', 'https://decrypt.co', 'Web3 news & guides', None, 'CryptoCurrency'),
    ('theblock', 'The Block', 'news', 'https://www.theblock.co/rss.xml', 'https://www.theblock.co', 'Institutional crypto news', None, 'CryptoCurrency'),
    ('cryptoslate', 'CryptoSlate', 'news', 'https://cryptoslate.com/feed/', 'https://cryptoslate.com', 'Crypto news & data', None, 'CryptoCurrency'),
    # CryptoCurrency video sources
    ('coin_bureau', 'Coin Bureau', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw', 'https://www.youtube.com/@CoinBureau', 'Educational crypto content & analysis', 'UCqK_GSMbpiV8spgD3ZGloSw', 'CryptoCurrency'),
    ('benjamin_cowen', 'Benjamin Cowen', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg', 'https://www.youtube.com/@intothecryptoverse', 'Technical analysis & market cycles', 'UCRvqjQPSeaWn-uEx-w0XOIg', 'CryptoCurrency'),
    ('altcoin_daily', 'Altcoin Daily', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCbLhGKVY-bJPcawebgtNfbw', 'https://www.youtube.com/@AltcoinDaily', 'Daily crypto news & updates', 'UCbLhGKVY-bJPcawebgtNfbw', 'CryptoCurrency'),
    ('bankless', 'Bankless', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCAl9Ld79qaZxp9JzEOwd3aA', 'https://www.youtube.com/@Bankless', 'Ethereum & DeFi ecosystem', 'UCAl9Ld79qaZxp9JzEOwd3aA', 'CryptoCurrency'),
    ('the_defiant', 'The Defiant', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCL0J4MLEdLP0-UyLu0hCktg', 'https://www.youtube.com/@TheDefiant', 'DeFi news & interviews', 'UCL0J4MLEdLP0-UyLu0hCktg', 'CryptoCurrency'),
    ('crypto_banter', 'Crypto Banter', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCN9Nj4tjXbVTLYWN0EKly_Q', 'https://www.youtube.com/@CryptoBanter', 'Live crypto shows & trading', 'UCN9Nj4tjXbVTLYWN0EKly_Q', 'CryptoCurrency'),
    ('datadash', 'DataDash', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCCatR7nWbYrkVXdxXb4cGXw', 'https://www.youtube.com/@DataDash', 'Macro markets & crypto analysis', 'UCCatR7nWbYrkVXdxXb4cGXw', 'CryptoCurrency'),
    ('cryptosrus', 'CryptosRUs', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCI7M65p3A-D3P4v5qW8POxQ', 'https://www.youtube.com/@CryptosRUs', 'Market analysis & project reviews', 'UCI7M65p3A-D3P4v5qW8POxQ', 'CryptoCurrency'),
    ('the_moon', 'The Moon', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCc4Rz_T9Sb1w5rqqo9pL1Og', 'https://www.youtube.com/@TheMoonCarl', 'Daily Bitcoin analysis & news', 'UCc4Rz_T9Sb1w5rqqo9pL1Og', 'CryptoCurrency'),
    ('digital_asset_news', 'Digital Asset News', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCJgHxpqfhWEEjYH9cLXqhIQ', 'https://www.youtube.com/@DigitalAssetNews', 'Bite-sized crypto news updates', 'UCJgHxpqfhWEEjYH9cLXqhIQ', 'CryptoCurrency'),
    ('paul_barron', 'Paul Barron Network', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC4VPa7EOvObpyCRI4YKRQRw', 'https://www.youtube.com/@paulbarronnetwork', 'Tech, AI & crypto intersection', 'UC4VPa7EOvObpyCRI4YKRQRw', 'CryptoCurrency'),
    ('lark_davis', 'Lark Davis', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCl2oCaw8hdR_kbqyqd2klIA', 'https://www.youtube.com/@TheCryptoLark', 'Altcoin analysis & opportunities', 'UCl2oCaw8hdR_kbqyqd2klIA', 'CryptoCurrency'),
    ('pompliano', 'Anthony Pompliano', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCevXpeL8cNyAnww-NqJ4m2w', 'https://www.youtube.com/@AnthonyPompliano', 'Bitcoin advocate & market commentary', 'UCevXpeL8cNyAnww-NqJ4m2w', 'CryptoCurrency'),
    ('whiteboard_crypto', 'Whiteboard Crypto', 'video', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCsYYksPHiGqXHPoHI-fm5sg', 'https://www.youtube.com/@WhiteboardCrypto', 'Educational crypto explainers', 'UCsYYksPHiGqXHPoHI-fm5sg', 'CryptoCurrency'),
    # ===== World =====
    ('reuters_world', 'Reuters World', 'news', 'https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best', 'https://www.reuters.com/world', 'International breaking news', None, 'World'),
    ('bbc_world', 'BBC World', 'news', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'https://www.bbc.com/news/world', 'Global news from BBC', None, 'World'),
    ('al_jazeera', 'Al Jazeera', 'news', 'https://www.aljazeera.com/xml/rss/all.xml', 'https://www.aljazeera.com', 'International news coverage', None, 'World'),
    # ===== Nation (US) =====
    ('npr_news', 'NPR News', 'news', 'https://feeds.npr.org/1001/rss.xml', 'https://www.npr.org', 'US national public radio news', None, 'Nation'),
    ('pbs_newshour', 'PBS NewsHour', 'news', 'https://www.pbs.org/newshour/feeds/rss/headlines', 'https://www.pbs.org/newshour', 'In-depth US news', None, 'Nation'),
    ('ap_news', 'AP News', 'news', 'https://apnews.com/apf-topnews/feed', 'https://apnews.com', 'Associated Press top stories', None, 'Nation'),
    # ===== Business =====
    ('cnbc_business', 'CNBC', 'news', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147', 'https://www.cnbc.com', 'Business & financial news', None, 'Business'),
    ('marketwatch', 'MarketWatch', 'news', 'https://www.marketwatch.com/rss/topstories', 'https://www.marketwatch.com', 'Financial markets & investing', None, 'Business'),
    ('wsj_markets', 'WSJ Markets', 'news', 'https://feeds.a.dj.com/rss/RSSMarketsMain.xml', 'https://www.wsj.com/news/markets', 'Wall Street Journal market news', None, 'Business'),
    # ===== Technology =====
    ('techcrunch', 'TechCrunch', 'news', 'https://techcrunch.com/feed/', 'https://techcrunch.com', 'Startup & technology news', None, 'Technology'),
    ('ars_technica', 'Ars Technica', 'news', 'https://feeds.arstechnica.com/arstechnica/index', 'https://arstechnica.com', 'Technology news & analysis', None, 'Technology'),
    ('the_verge', 'The Verge', 'news', 'https://www.theverge.com/rss/index.xml', 'https://www.theverge.com', 'Tech, science & culture', None, 'Technology'),
    ('wired', 'Wired', 'news', 'https://www.wired.com/feed/rss', 'https://www.wired.com', 'Technology & future trends', None, 'Technology'),
    # ===== Entertainment =====
    ('variety', 'Variety', 'news', 'https://variety.com/feed/', 'https://variety.com', 'Entertainment industry news', None, 'Entertainment'),
    ('hollywood_reporter', 'Hollywood Reporter', 'news', 'https://www.hollywoodreporter.com/feed/', 'https://www.hollywoodreporter.com', 'Movies, TV & entertainment', None, 'Entertainment'),
    ('ew', 'Entertainment Weekly', 'news', 'https://ew.com/feed/', 'https://ew.com', 'Pop culture & entertainment', None, 'Entertainment'),
    # ===== Sports =====
    ('espn', 'ESPN', 'news', 'https://www.espn.com/espn/rss/news', 'https://www.espn.com', 'Sports news & scores', None, 'Sports'),
    ('bleacher_report', 'Bleacher Report', 'news', 'https://bleacherreport.com/articles/feed', 'https://bleacherreport.com', 'Sports news & highlights', None, 'Sports'),
    ('sports_illustrated', 'Sports Illustrated', 'news', 'https://www.si.com/rss/si_topstories.rss', 'https://www.si.com', 'Sports journalism', None, 'Sports'),
    # ===== Science =====
    ('science_daily', 'Science Daily', 'news', 'https://www.sciencedaily.com/rss/all.xml', 'https://www.sciencedaily.com', 'Breaking science news', None, 'Science'),
    ('nasa', 'NASA', 'news', 'https://www.nasa.gov/rss/dyn/breaking_news.rss', 'https://www.nasa.gov', 'Space & science updates', None, 'Science'),
    ('new_scientist', 'New Scientist', 'news', 'https://www.newscientist.com/feed/home/', 'https://www.newscientist.com', 'Science & technology news', None, 'Science'),
    # ===== Health =====
    ('medical_news', 'Medical News Today', 'news', 'https://www.medicalnewstoday.com/rss', 'https://www.medicalnewstoday.com', 'Health & medical news', None, 'Health'),
    ('health_news', 'Healthline', 'news', 'https://www.healthline.com/rss', 'https://www.healthline.com', 'Health information & wellness', None, 'Health'),
    ('webmd', 'WebMD', 'news', 'https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC', 'https://www.webmd.com', 'Health news & advice', None, 'Health'),
]


async def seed_default_sources():
    """Seed default content sources, adding any missing sources."""
    from app.models import ContentSource

    async with async_session_maker() as db:
        # Get existing source keys
        result = await db.execute(select(ContentSource.source_key))
        existing_keys = set(result.scalars().all())

        # Insert missing sources and update category on existing ones
        added = 0
        updated = 0
        for source_key, name, source_type, url, website, description, channel_id, category in DEFAULT_CONTENT_SOURCES:
            if source_key not in existing_keys:
                source = ContentSource(
                    source_key=source_key,
                    name=name,
                    type=source_type,
                    url=url,
                    website=website,
                    description=description,
                    channel_id=channel_id,
                    is_system=True,
                    is_enabled=True,
                    category=category,
                )
                db.add(source)
                added += 1
            else:
                # Update category on existing sources
                result = await db.execute(
                    select(ContentSource).where(ContentSource.source_key == source_key)
                )
                existing = result.scalars().first()
                if existing and existing.category != category:
                    existing.category = category
                    updated += 1

        await db.commit()
        if added > 0:
            logger.info(f"Seeded {added} new content sources")
        if updated > 0:
            logger.info(f"Updated category on {updated} existing sources")


# Default coin categories from AI review (352 coins)
# Format: (symbol, reason) - reason includes category prefix like [APPROVED], [BORDERLINE], etc.
DEFAULT_COIN_CATEGORIES = [
    ("00", "Meme coin, no clear utility or development"),
    ("1INCH", "[APPROVED] Leading DEX aggregator, strong utility, active dev"),
    ("2Z", "[QUESTIONABLE] Limited adoption, unclear long-term viability"),
    ("A8", "[QUESTIONABLE] Low market presence, uncertain fundamentals"),
    ("AAVE", "[APPROVED] Top DeFi lending protocol, proven track record"),
    ("ABT", "[BORDERLINE] Declining relevance, limited recent progress"),
    ("ACH", "[QUESTIONABLE] Payment focus but limited merchant adoption"),
    ("ACS", "[QUESTIONABLE] Niche market, uncertain competitive position"),
    ("ACX", "[QUESTIONABLE] New project, unproven market fit"),
    ("ADA", "[BORDERLINE] Slow development, losing ground to competitors"),
    ("AERGO", "[QUESTIONABLE] Limited adoption, enterprise focus struggling"),
    ("AERO", "[QUESTIONABLE] New DEX token, unproven sustainability"),
    ("AGLD", "Gaming token with questionable utility"),
    ("AIOZ", "[QUESTIONABLE] CDN market crowded, limited differentiation"),
    ("AKT", "[BORDERLINE] Cloud computing niche, slow adoption"),
    ("ALCX", "[QUESTIONABLE] DeFi protocol with limited TVL growth"),
    ("ALEO", "[BORDERLINE] Privacy focus but mainnet still developing"),
    ("ALEPH", "[QUESTIONABLE] Decentralized cloud, limited market traction"),
    ("ALGO", "[BORDERLINE] Strong tech but ecosystem growth stagnant"),
    ("ALICE", "Gaming metaverse token, speculative hype"),
    ("ALLO", "[QUESTIONABLE] New protocol, unproven adoption"),
    ("ALT", "[QUESTIONABLE] Restaking narrative but execution uncertain"),
    ("AMP", "[QUESTIONABLE] Payment collateral but limited real usage"),
    ("ANKR", "[BORDERLINE] Infrastructure play but competitive market"),
    ("APE", "Meme/NFT token, no sustainable utility"),
    ("API3", "[QUESTIONABLE] Oracle space dominated by Chainlink"),
    ("APR", "[QUESTIONABLE] New project, unclear market position"),
    ("APT", "[APPROVED] Strong L1 with Meta backing, active ecosystem"),
    ("ARB", "[APPROVED] Leading Ethereum L2, strong TVL and adoption"),
    ("ARKM", "[QUESTIONABLE] AI narrative but unclear differentiation"),
    ("ARPA", "[QUESTIONABLE] Privacy computing, limited real adoption"),
    ("ASM", "[QUESTIONABLE] Gaming token with uncertain utility"),
    ("AST", "[QUESTIONABLE] Telecom blockchain, niche market"),
    ("ASTER", "[QUESTIONABLE] Polkadot parachain with limited traction"),
    ("ATH", "[QUESTIONABLE] New project, unproven fundamentals"),
    ("ATOM", "[APPROVED] Cosmos hub, strong interchain ecosystem"),
    ("AUCTION", "[QUESTIONABLE] Parachain auction token, limited utility"),
    ("AUDD", "[QUESTIONABLE] Stablecoin with limited adoption"),
    ("AUDIO", "[BORDERLINE] Music streaming but slow user growth"),
    ("AURORA", "[QUESTIONABLE] NEAR EVM but limited ecosystem growth"),
    ("AVAX", "[APPROVED] Strong L1 ecosystem, institutional adoption"),
    ("AVNT", "[QUESTIONABLE] Enterprise blockchain, limited traction"),
    ("AVT", "[QUESTIONABLE] Supply chain focus, niche market"),
    ("AWE", "[QUESTIONABLE] New project, uncertain market fit"),
    ("AXL", "[BORDERLINE] Cross-chain infrastructure, competitive space"),
    ("AXS", "[QUESTIONABLE] Gaming token, declining player base"),
    ("B3", "[QUESTIONABLE] New project, unproven utility"),
    ("BADGER", "[QUESTIONABLE] Bitcoin DeFi but limited growth"),
    ("BAL", "[BORDERLINE] DEX protocol but losing market share"),
    ("BAND", "[QUESTIONABLE] Oracle protocol overshadowed by Chainlink"),
    ("BARD", "[QUESTIONABLE] Unclear utility, limited adoption and development"),
    ("BAT", "[BORDERLINE] Declining relevance, Brave browser growth stalled"),
    ("BCH", "[BORDERLINE] Bitcoin fork, limited adoption vs BTC"),
    ("BERA", "[QUESTIONABLE] New project, unproven utility and adoption"),
    ("BICO", "[QUESTIONABLE] Limited traction, overshadowed by competitors"),
    ("BIGTIME", "[QUESTIONABLE] Gaming token, unclear long-term viability"),
    ("BIO", "[QUESTIONABLE] New DeSci project, unproven model"),
    ("BLAST", "[QUESTIONABLE] Controversial launch, yield sustainability concerns"),
    ("BLUR", "[BORDERLINE] NFT marketplace declining, OpenSea competition"),
    ("BLZ", "[QUESTIONABLE] Limited adoption, unclear competitive advantage"),
    ("BNB", "[APPROVED] Major exchange token, strong utility and ecosystem"),
    ("BNKR", "[QUESTIONABLE] New project, limited track record"),
    ("BNT", "[BORDERLINE] Bancor declining relevance in DeFi space"),
    ("BOBA", "[QUESTIONABLE] L2 solution overshadowed by major competitors"),
    ("BOBBOB", "Meme coin, no real utility or purpose"),
    ("BONK", "Meme coin, speculative with no utility"),
    ("BTC", "[APPROVED] Digital gold, store of value, network effect"),
    ("BTRST", "[QUESTIONABLE] Braintrust declining, limited platform growth"),
    ("C98", "[QUESTIONABLE] Coin98 wallet, limited differentiation"),
    ("CAKE", "[BORDERLINE] PancakeSwap declining TVL, BSC dependency"),
    ("CBETH", "[APPROVED] Coinbase ETH staking, legitimate utility"),
    ("CELR", "[QUESTIONABLE] Celer Network limited adoption vs competitors"),
    ("CFG", "[QUESTIONABLE] Centrifuge niche use case, limited adoption"),
    ("CGLD", "[APPROVED] Celo mobile-first blockchain, real-world use"),
    ("CHZ", "[BORDERLINE] Chiliz sports tokens declining interest"),
    ("CLANKER", "Meme/social token, no fundamental utility"),
    ("CLV", "[QUESTIONABLE] Clover Finance limited traction, unclear value"),
    ("COMP", "[APPROVED] Compound DeFi protocol, established lending"),
    ("COOKIE", "Meme token, no real utility or purpose"),
    ("CORECHAIN", "[QUESTIONABLE] New blockchain, unproven adoption"),
    ("COSMOSDYDX", "[APPROVED] dYdX derivatives DEX, strong trading volume"),
    ("COTI", "[QUESTIONABLE] Payment solution, limited merchant adoption"),
    ("COW", "[BORDERLINE] CoW Protocol MEV protection, niche utility"),
    ("CRO", "[BORDERLINE] Crypto.com token, reduced rewards program"),
    ("CRV", "[APPROVED] Curve Finance major DEX, DeFi infrastructure"),
    ("CTSI", "[QUESTIONABLE] Cartesi limited adoption, unclear advantage"),
    ("CTX", "[QUESTIONABLE] Cryptex Finance limited traction"),
    ("CVC", "[QUESTIONABLE] Civic identity, limited real-world adoption"),
    ("CVX", "[BORDERLINE] Convex Finance declining TVL, Curve dependency"),
    ("DAI", "[APPROVED] Decentralized stablecoin, DeFi cornerstone"),
    ("DASH", "[BORDERLINE] Privacy coin, regulatory concerns, declining use"),
    ("DBR", "[QUESTIONABLE] New DeFi token, limited track record"),
    ("DEGEN", "Meme coin, speculative with no utility"),
    ("DEXT", "[QUESTIONABLE] DEXTools utility token, niche use case"),
    ("DIA", "[QUESTIONABLE] Oracle solution, overshadowed by Chainlink"),
    ("DIMO", "[QUESTIONABLE] IoT vehicle data, unproven business model"),
    ("DNT", "[QUESTIONABLE] District0x limited adoption, unclear utility"),
    ("DOGE", "Meme coin, no real utility beyond speculation"),
    ("DOGINME", "Meme coin derivative, no fundamental value"),
    ("DOLO", "[QUESTIONABLE] New project, limited information and adoption"),
    ("DOT", "[APPROVED] Strong parachain ecosystem, active development"),
    ("DRIFT", "[QUESTIONABLE] New DeFi protocol, unproven long-term viability"),
    ("EDGE", "[QUESTIONABLE] Privacy focus but limited adoption, niche market"),
    ("EGLD", "[BORDERLINE] Solid tech but losing ground to competitors"),
    ("EIGEN", "[QUESTIONABLE] Early stage restaking protocol, high risk"),
    ("ELA", "[QUESTIONABLE] Declining relevance, limited ecosystem growth"),
    ("ENA", "[QUESTIONABLE] Synthetic dollar protocol, regulatory uncertainty"),
    ("ENS", "[APPROVED] Essential Ethereum infrastructure, clear utility"),
    ("EOS", "[BORDERLINE] Lost momentum to newer L1s, declining activity"),
    ("ERA", "[BORDERLINE] zkSync ecosystem token, competitive L2 space"),
    ("ETC", "[BORDERLINE] Multiple 51% attacks, security concerns"),
    ("ETH", "[APPROVED] #2 crypto, massive ecosystem, DeFi foundation"),
    ("ETHFI", "[QUESTIONABLE] Liquid staking derivative, crowded market"),
    ("EUL", "[QUESTIONABLE] Lending protocol governance, limited adoption"),
    ("EURC", "[APPROVED] Circle EUR stablecoin, regulatory compliant"),
    ("FAI", "[QUESTIONABLE] Obscure project, limited information available"),
    ("FARM", "[QUESTIONABLE] DeFi aggregator, declining TVL and activity"),
    ("FARTCOIN", "Meme coin, no real utility"),
    ("FET", "[APPROVED] AI/ML blockchain, strong partnerships, active dev"),
    ("FIDA", "[QUESTIONABLE] Solana DEX token, limited market share"),
    ("FIL", "[BORDERLINE] Decentralized storage, slow adoption vs competitors"),
    ("FIS", "[QUESTIONABLE] Liquid staking, overshadowed by Lido"),
    ("FLOCK", "[QUESTIONABLE] New AI training protocol, unproven model"),
    ("FLOKI", "Meme coin derivative, speculative only"),
    ("FLOW", "[BORDERLINE] NFT-focused blockchain, declining NFT market"),
    ("FLR", "[QUESTIONABLE] Flare Network utility token, limited adoption"),
    ("FLUID", "[QUESTIONABLE] DeFi lending protocol, early stage"),
    ("FORT", "[QUESTIONABLE] Forta network security, niche use case"),
    ("FORTH", "[QUESTIONABLE] Ampleforth governance, complex tokenomics"),
    ("FOX", "[QUESTIONABLE] ShapeShift DAO token, declining exchange relevance"),
    ("G", "[QUESTIONABLE] Gravity bridge token, limited ecosystem"),
    ("GFI", "[QUESTIONABLE] Goldfinch credit protocol, regulatory risks"),
    ("GHST", "[QUESTIONABLE] Gaming token, speculative NFT game economy"),
    ("GIGA", "[QUESTIONABLE] Meme-adjacent token, limited utility"),
    ("GLM", "[BORDERLINE] Distributed computing, slow adoption"),
    ("GMT", "[QUESTIONABLE] Move-to-earn token, unsustainable model"),
    ("GNO", "[APPROVED] Gnosis ecosystem, prediction markets, active dev"),
    ("GODS", "[QUESTIONABLE] Gaming token, volatile game economy"),
    ("GRT", "[APPROVED] Web3 indexing protocol, essential infrastructure"),
    ("GST", "[QUESTIONABLE] Green Satoshi Token, unsustainable tokenomics"),
    ("GTC", "[QUESTIONABLE] Gitcoin governance, funding model uncertainty"),
    ("HBAR", "[APPROVED] Enterprise adoption, strong governance council"),
    ("HFT", "[QUESTIONABLE] Hashflow DEX token, competitive market"),
    ("HIGH", "[QUESTIONABLE] Highstreet metaverse, speculative gaming"),
    ("HNT", "[BORDERLINE] IoT network, migration challenges to Solana"),
    ("HOME", "[QUESTIONABLE] Real estate tokenization, early stage"),
    ("HONEY", "[QUESTIONABLE] DeFi yield farming, high risk protocol"),
    ("HOPR", "[QUESTIONABLE] Privacy network, limited adoption"),
    ("ICP", "[BORDERLINE] Internet Computer, controversial but active dev"),
    ("IDEX", "[QUESTIONABLE] DEX token, losing market share"),
    ("ILV", "[QUESTIONABLE] Gaming token, limited adoption, high volatility"),
    ("IMX", "[APPROVED] Leading NFT/gaming L2, strong partnerships, active dev"),
    ("INDEX", "[BORDERLINE] DeFi index protocol, niche use case, limited growth"),
    ("INJ", "[APPROVED] DEX protocol with real utility, growing ecosystem"),
    ("INV", "[QUESTIONABLE] Inverse Finance, past exploit history, small market"),
    ("IO", "[QUESTIONABLE] New project, unclear long-term utility"),
    ("IOTX", "[BORDERLINE] IoT blockchain, slow adoption, niche market"),
    ("IP", "[QUESTIONABLE] Story Protocol, very new, unproven model"),
    ("IRYS", "[BORDERLINE] Data storage, niche use case, limited adoption"),
    ("JASMY", "[QUESTIONABLE] IoT data, unclear utility, heavy token unlocks"),
    ("JITOSOL", "[APPROVED] Solana liquid staking, growing TVL, solid utility"),
    ("JTO", "[APPROVED] Jito Network, Solana MEV/staking, strong fundamentals"),
    ("KAITO", "[QUESTIONABLE] AI search, very new, unproven market fit"),
    ("KARRAT", "[QUESTIONABLE] Gaming infrastructure, new project, unclear adoption"),
    ("KAVA", "[BORDERLINE] Cosmos DeFi, declining relevance vs competitors"),
    ("KERNEL", "[QUESTIONABLE] New project, limited information, unproven"),
    ("KEYCAT", "[QUESTIONABLE] Gaming token, very new, unclear utility"),
    ("KITE", "[QUESTIONABLE] New project, limited adoption, unclear roadmap"),
    ("KMNO", "[QUESTIONABLE] New token, limited information available"),
    ("KNC", "[BORDERLINE] Kyber Network, declining vs newer DEX aggregators"),
    ("KRL", "[QUESTIONABLE] Kryll trading bots, niche market, limited growth"),
    ("KSM", "[APPROVED] Kusama parachain network, active development"),
    ("KTA", "[QUESTIONABLE] New project, unclear utility and adoption"),
    ("L3", "[QUESTIONABLE] New L3 project, unproven technology stack"),
    ("LA", "[QUESTIONABLE] New project, limited information, unclear utility"),
    ("LAYER", "[QUESTIONABLE] New infrastructure project, unproven adoption"),
    ("LCX", "[BORDERLINE] Regulated exchange token, limited global reach"),
    ("LDO", "[APPROVED] Lido liquid staking, dominant market position"),
    ("LINEA", "[APPROVED] ConsenSys L2, strong backing, growing ecosystem"),
    ("LINK", "[APPROVED] Leading oracle network, essential DeFi infrastructure"),
    ("LOKA", "[QUESTIONABLE] Gaming token, limited adoption, high volatility"),
    ("LPT", "[APPROVED] Livepeer video streaming, real utility, growing use"),
    ("LQTY", "[APPROVED] Liquity protocol governance, solid DeFi fundamentals"),
    ("LRC", "[BORDERLINE] Loopring L2, declining vs other scaling solutions"),
    ("LRDS", "[QUESTIONABLE] New project, limited information available"),
    ("LSETH", "[APPROVED] Liquid staking ETH, growing DeFi utility"),
    ("LTC", "[APPROVED] Established cryptocurrency, payment utility, longevity"),
    ("MAGIC", "[QUESTIONABLE] Gaming ecosystem token, limited real adoption"),
    ("MAMO", "[QUESTIONABLE] New project, unclear utility and roadmap"),
    ("MANA", "[QUESTIONABLE] Metaverse hype faded, declining user activity"),
    ("MANTLE", "[APPROVED] BitDAO L2, strong treasury, active development"),
    ("MASK", "[BORDERLINE] Web3 social, niche use case, slow adoption"),
    ("MATH", "[BORDERLINE] Multi-chain wallet, competitive market"),
    ("MDT", "[QUESTIONABLE] Data economy token, unclear adoption metrics"),
    ("ME", "[QUESTIONABLE] Magic Eden token, NFT market dependency"),
    ("MET", "[QUESTIONABLE] Metronome, limited adoption, unclear utility"),
    ("METIS", "[APPROVED] Ethereum L2, growing DeFi ecosystem, solid tech"),
    ("MINA", "[APPROVED] Zero-knowledge blockchain, unique tech, active dev"),
    ("MKR", "[APPROVED] MakerDAO governance, established DeFi protocol"),
    ("MLN", "[BORDERLINE] Enzyme Protocol, niche asset management use case"),
    ("MNDE", "[QUESTIONABLE] Marinade DAO token, limited utility beyond governance"),
    ("MOG", "Meme coin with no fundamental utility or purpose"),
    ("MON", "Meme coin derivative, purely speculative asset"),
    ("MOODENG", "Meme coin based on hippo, no real use case"),
    ("MORPHO", "[APPROVED] Innovative DeFi lending protocol, strong development"),
    ("MPLX", "[BORDERLINE] Metaplex governance token, limited broader utility"),
    ("MSOL", "[APPROVED] Marinade staked SOL, legitimate liquid staking token"),
    ("NCT", "[QUESTIONABLE] Polyswarm utility token, niche cybersecurity use"),
    ("NEAR", "[APPROVED] Layer-1 blockchain, strong dev activity, real adoption"),
    ("NEON", "[BORDERLINE] Neon EVM token, limited ecosystem compared to rivals"),
    ("NEWT", "Meme coin with amphibian theme, no utility"),
    ("NKN", "[QUESTIONABLE] Decentralized internet project, slow adoption"),
    ("NMR", "[BORDERLINE] Numeraire hedge fund token, very niche use case"),
    ("NOICE", "Meme coin with social media theme, no substance"),
    ("NOM", "Meme coin derivative, purely speculative trading"),
    ("OCEAN", "[APPROVED] Data marketplace protocol, AI narrative, active dev"),
    ("OGN", "[BORDERLINE] Origin Protocol token, declining DeFi relevance"),
    ("OMNI", "[QUESTIONABLE] Cross-chain protocol, heavy competition in space"),
    ("ONDO", "[APPROVED] RWA tokenization platform, strong institutional focus"),
    ("OP", "[APPROVED] Optimism L2 token, major Ethereum scaling solution"),
    ("ORCA", "[BORDERLINE] Solana DEX token, overshadowed by Jupiter/Raydium"),
    ("OSMO", "[APPROVED] Osmosis DEX, leading Cosmos ecosystem exchange"),
    ("OXT", "[QUESTIONABLE] Orchid VPN token, limited adoption and usage"),
    ("PAX", "[BORDERLINE] Paxos Standard stablecoin, regulatory uncertainties"),
    ("PAXG", "[APPROVED] Gold-backed token by Paxos, regulated asset"),
    ("PENDLE", "[APPROVED] Yield trading protocol, innovative DeFi mechanics"),
    ("PENGU", "Pudgy Penguins meme coin, no fundamental value"),
    ("PEPE", "Meme coin based on frog, purely speculative"),
    ("PERP", "[APPROVED] Perpetual Protocol DEX, solid derivatives platform"),
    ("PIRATE", "Meme coin with pirate theme, no real utility"),
    ("PLU", "[QUESTIONABLE] Pluton rewards token, limited merchant adoption"),
    ("PNG", "[QUESTIONABLE] Pangolin DEX token, Avalanche ecosystem decline"),
    ("PNUT", "Peanut meme coin, viral but no substance"),
    ("POL", "[APPROVED] Polygon ecosystem token, major L2 scaling solution"),
    ("POLS", "[QUESTIONABLE] Polkastarter launchpad token, declining relevance"),
    ("POND", "[QUESTIONABLE] Marlin Protocol token, limited network adoption"),
    ("POPCAT", "Cat meme coin, purely speculative trading asset"),
    ("POWR", "[QUESTIONABLE] Power Ledger energy token, slow real adoption"),
    ("PRCL", "[QUESTIONABLE] Parcl real estate protocol, unproven market fit"),
    ("PRIME", "[QUESTIONABLE] Echelon Prime gaming token, speculative sector"),
    ("PRO", "[QUESTIONABLE] Propy real estate token, limited transaction volume"),
    ("PROMPT", "[QUESTIONABLE] AI prompt marketplace, unproven business model"),
    ("PROVE", "[QUESTIONABLE] ProveAI verification token, early stage project"),
    ("PUMP", "Pump.fun meme coin launcher token, speculative"),
    ("PUNDIX", "[QUESTIONABLE] Pundi X payments token, limited merchant adoption"),
    ("PYR", "[QUESTIONABLE] Vulcan Forged gaming token, niche gaming focus"),
    ("PYTH", "[APPROVED] Oracle network, strong institutional partnerships"),
    ("QI", "[QUESTIONABLE] Benqi lending protocol, limited beyond Avalanche"),
    ("QNT", "[APPROVED] Quant network interoperability, enterprise adoption"),
    ("RAD", "[QUESTIONABLE] Radicle code collaboration, limited developer uptake"),
    ("RARE", "[QUESTIONABLE] NFT gaming declining, limited adoption"),
    ("RARI", "[QUESTIONABLE] NFT marketplace overshadowed by OpenSea"),
    ("RECALL", "[QUESTIONABLE] Unclear utility, limited market presence"),
    ("RED", "[QUESTIONABLE] Vague project goals, minimal development"),
    ("RENDER", "[APPROVED] Strong GPU rendering utility, growing AI demand"),
    ("REQ", "[BORDERLINE] Payment protocol, slow adoption growth"),
    ("REZ", "[QUESTIONABLE] New project, unproven utility"),
    ("RLC", "[BORDERLINE] Decentralized computing, limited traction"),
    ("RLS", "[QUESTIONABLE] Gaming token, unclear competitive edge"),
    ("RONIN", "[APPROVED] Axie Infinity sidechain, proven gaming utility"),
    ("ROSE", "[APPROVED] Privacy-focused blockchain, active development"),
    ("RPL", "[APPROVED] Rocket Pool ETH staking, strong fundamentals"),
    ("RSC", "[QUESTIONABLE] Limited information, unclear roadmap"),
    ("RSR", "[BORDERLINE] Stablecoin protocol, regulatory uncertainty"),
    ("S", "[QUESTIONABLE] Vague ticker, unclear project identity"),
    ("SAFE", "[APPROVED] Multi-sig wallet infrastructure, proven utility"),
    ("SAND", "[BORDERLINE] Metaverse gaming, declining interest"),
    ("SAPIEN", "[QUESTIONABLE] Social platform, limited user adoption"),
    ("SD", "[QUESTIONABLE] Stader Labs, competitive staking market"),
    ("SEAM", "[QUESTIONABLE] New DeFi project, unproven model"),
    ("SEI", "[APPROVED] Trading-focused L1, strong backing"),
    ("SHDW", "[BORDERLINE] Decentralized storage, competitive market"),
    ("SHIB", "Meme coin, no fundamental utility"),
    ("SHPING", "[QUESTIONABLE] Shopping rewards, limited adoption"),
    ("SKL", "[BORDERLINE] Ethereum scaling, competitive L2 space"),
    ("SKY", "[APPROVED] MakerDAO rebrand, established DeFi protocol"),
    ("SNX", "[APPROVED] Synthetic assets protocol, proven DeFi utility"),
    ("SOL", "[APPROVED] Major L1 blockchain, strong ecosystem"),
    ("SPA", "[QUESTIONABLE] Sperax stablecoin, limited market share"),
    ("SPELL", "[QUESTIONABLE] Abracadabra Money, declining TVL"),
    ("SPK", "[QUESTIONABLE] Spark Protocol, new lending platform"),
    ("SPX", "[QUESTIONABLE] Speculation token, unclear fundamentals"),
    ("SQD", "[QUESTIONABLE] Data indexing, niche market"),
    ("STG", "[APPROVED] Stargate cross-chain bridge, proven utility"),
    ("STORJ", "[BORDERLINE] Decentralized storage, competitive market"),
    ("STRK", "[APPROVED] Starknet L2 scaling, strong technology"),
    ("STX", "[APPROVED] Bitcoin L2, unique value proposition"),
    ("SUI", "[APPROVED] High-performance L1, strong development"),
    ("SUKU", "[QUESTIONABLE] Supply chain tracking, limited adoption"),
    ("SUP", "[QUESTIONABLE] SuperRare NFT platform, declining market"),
    ("SUPER", "[QUESTIONABLE] Gaming platform, competitive market"),
    ("SUSHI", "[BORDERLINE] DEX protocol, losing market share"),
    ("SWELL", "[QUESTIONABLE] Liquid staking, competitive market"),
    ("SWFTC", "[QUESTIONABLE] Cross-chain swaps, limited differentiation"),
    ("SXT", "[QUESTIONABLE] Space and Time, unproven market fit"),
    ("SYND", "[QUESTIONABLE] Syndicate DAO, unclear utility"),
    ("SYRUP", "[QUESTIONABLE] DeFi yield farming, high risk"),
    ("T", "[APPROVED] Threshold Network, proven privacy tech"),
    ("TAO", "[APPROVED] Bittensor AI network, growing utility"),
    ("TIA", "[APPROVED] Celestia modular blockchain, innovative tech"),
    ("TIME", "[QUESTIONABLE] Declining DeFi relevance, limited current utility"),
    ("TNSR", "[BORDERLINE] Solana NFT marketplace, niche but functional"),
    ("TON", "[APPROVED] Telegram integration, active development, growing"),
    ("TOSHI", "Meme coin derivative, no substantial utility"),
    ("TOWNS", "[QUESTIONABLE] Social experiment token, unclear long-term value"),
    ("TRAC", "[BORDERLINE] Supply chain focus, limited adoption progress"),
    ("TRB", "[QUESTIONABLE] Oracle project overshadowed by Chainlink"),
    ("TREE", "[QUESTIONABLE] Environmental token, unproven business model"),
    ("TROLL", "Obvious meme coin, no real utility"),
    ("TRU", "[BORDERLINE] DeFi lending, competitive market position"),
    ("TRUMP", "Political meme coin, pure speculation"),
    ("TRUST", "[QUESTIONABLE] Vague utility, limited development activity"),
    ("TURBO", "AI-generated meme coin, no fundamentals"),
    ("UMA", "[APPROVED] Synthetic assets protocol, proven DeFi utility"),
    ("UNI", "[APPROVED] Leading DEX, strong fundamentals, active dev"),
    ("USD1", "[QUESTIONABLE] New stablecoin, unproven stability mechanism"),
    ("USDS", "[BORDERLINE] Stablecoin variant, regulatory uncertainty"),
    ("USDT", "[APPROVED] Dominant stablecoin despite transparency concerns"),
    ("USELESS", "Name says it all, meme token"),
    ("VARA", "[QUESTIONABLE] New blockchain, unproven adoption"),
    ("VELO", "[BORDERLINE] Payments focus, limited market penetration"),
    ("VET", "[APPROVED] Enterprise blockchain, real-world partnerships"),
    ("VOXEL", "[QUESTIONABLE] Gaming metaverse, declining NFT interest"),
    ("VTHO", "[BORDERLINE] VeChain gas token, tied to VET success"),
    ("VVV", "[QUESTIONABLE] New project, unclear utility and adoption"),
    ("W", "[QUESTIONABLE] Wormhole token, bridge security concerns"),
    ("WAXL", "[BORDERLINE] Wrapped Axelar, depends on bridge adoption"),
    ("WCT", "[QUESTIONABLE] Waves ecosystem token, platform struggles"),
    ("WELL", "[QUESTIONABLE] Health/wellness token, unproven model"),
    ("WIF", "Dog-themed meme coin, no utility"),
    ("WLD", "[QUESTIONABLE] Worldcoin privacy concerns, regulatory issues"),
    ("WLFI", "Trump-related DeFi token, political risk"),
    ("WMTX", "[QUESTIONABLE] Wrapped token, limited independent utility"),
    ("XAN", "[QUESTIONABLE] New project, unclear value proposition"),
    ("XCN", "[QUESTIONABLE] Chain protocol, competitive L1 space"),
    ("XLM", "[APPROVED] Stellar payments, institutional partnerships"),
    ("XPL", "[QUESTIONABLE] Limited information, unclear utility"),
    ("XRP", "[APPROVED] Major payments crypto, regulatory clarity"),
    ("XSGD", "[BORDERLINE] Singapore dollar stablecoin, regional use"),
    ("XTZ", "[BORDERLINE] Tezos blockchain, slow adoption growth"),
    ("XYO", "[QUESTIONABLE] Location oracle, limited real adoption"),
    ("YB", "[QUESTIONABLE] New yield token, unproven sustainability"),
    ("YFI", "[APPROVED] DeFi yield farming pioneer, strong protocol"),
    ("ZEC", "[APPROVED] Privacy coin, proven technology, niche use"),
    ("ZEN", "[BORDERLINE] Privacy blockchain, regulatory headwinds"),
    ("ZETA", "[BORDERLINE] Cross-chain protocol, early development"),
    ("ZETACHAIN", "[BORDERLINE] Same as ZETA, interoperability focus"),
    ("ZK", "[QUESTIONABLE] Generic ZK token, unclear differentiation"),
    ("ZKC", "[QUESTIONABLE] ZK competitor, crowded scaling space"),
    ("ZORA", "[BORDERLINE] NFT protocol, declining NFT market interest"),
    ("ZRO", "[APPROVED] LayerZero omnichain protocol, strong dev activity"),
    ("ZRX", "[BORDERLINE] 0x protocol solid but declining DEX relevance"),
]


async def seed_default_coins():
    """Seed default coin categories if table is empty."""
    from app.models import BlacklistedCoin

    async with async_session_maker() as db:
        # Check if any global coin entries exist (user_id IS NULL)
        result = await db.execute(
            select(BlacklistedCoin).where(BlacklistedCoin.user_id.is_(None)).limit(1)
        )
        if result.scalars().first():
            return  # Already seeded

        # Insert default coin categories
        added = 0
        for symbol, reason in DEFAULT_COIN_CATEGORIES:
            coin = BlacklistedCoin(
                symbol=symbol.upper(),
                reason=reason,
                user_id=None,  # Global entry
            )
            db.add(coin)
            added += 1

        await db.commit()
        logger.info(f"Seeded {added} default coin categories")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default data
    await seed_default_sources()
    await seed_default_coins()
