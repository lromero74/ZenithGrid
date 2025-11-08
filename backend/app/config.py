from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Coinbase API
    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./trading.db"

    # Security
    secret_key: str = "change-this-secret-key"
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Trading Parameters
    initial_btc_percentage: float = 5.0
    dca_percentage: float = 3.0
    max_btc_usage_percentage: float = 25.0
    min_profit_percentage: float = 1.0

    # MACD Parameters
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9

    # Candle/Chart Parameters
    # Valid intervals: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY
    candle_interval: str = "FIVE_MINUTE"  # Default to 5-minute candles
    ticker_interval: str = "1m"  # Legacy support

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
