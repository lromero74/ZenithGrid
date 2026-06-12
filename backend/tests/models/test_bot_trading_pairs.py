from app.models import Bot, BotProduct


def test_get_trading_pairs_uses_legacy_product_ids_when_junction_empty():
    bot = Bot(
        name="Legacy product ids bot",
        product_id="BTC-USD",
        product_ids=["BTC-USD", "ETH-USD"],
    )

    assert bot.get_trading_pairs() == ["BTC-USD", "ETH-USD"]
    assert bot.get_quote_currency() == "USD"


def test_get_trading_pairs_prefers_junction_products_when_present():
    bot = Bot(
        name="Junction products bot",
        product_id="BTC-USD",
        product_ids=["BTC-USD", "ETH-USD"],
    )
    bot.products = [
        BotProduct(product_id="SOL-USD"),
        BotProduct(product_id="ADA-USD"),
    ]

    assert bot.get_trading_pairs() == ["SOL-USD", "ADA-USD"]
    assert bot.get_quote_currency() == "USD"
