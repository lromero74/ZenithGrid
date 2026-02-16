from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown fields in .env
    )

    # Coinbase API - Legacy HMAC (if using old keys)
    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""

    # Coinbase CDP API - New EC private key method (recommended)
    coinbase_cdp_key_file: str = ""  # Path to cdp_api_key.json file
    coinbase_cdp_key_name: str = ""  # API key name from CDP
    coinbase_cdp_private_key: str = ""  # EC private key from CDP

    @field_validator("coinbase_cdp_private_key")
    @classmethod
    def convert_newlines(cls, v: str) -> str:
        """Convert literal \\n to actual newlines in private key"""
        if v:
            return v.replace("\\n", "\n")
        return v

    # System AI Provider (for news analysis, coin categorization, YouTube analysis)
    # Options: claude, gemini, grok, groq, openai
    system_ai_provider: str = "claude"

    # AI Provider API Keys
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    grok_api_key: str = ""  # x.AI Grok API
    groq_api_key: str = ""  # Groq API (Llama models - 14,400 RPD free tier)
    openai_api_key: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./trading.db"

    # Security
    # CORS origins as comma-separated string (parsed to list via validator)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Validate CORS origins format (comma-separated URLs)"""
        # Just validate it's a string - actual parsing happens in main.py
        return v

    def get_cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # JWT Authentication
    jwt_secret_key: str = "jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Encryption key for API credentials at rest (Fernet key)
    encryption_key: str = ""

    # Email / SES Configuration
    ses_region: str = "us-east-1"
    ses_sender_email: str = "noreply@romerotechsolutions.com"
    ses_enabled: bool = True
    frontend_url: str = "https://tradebot.romerotechsolutions.com"
    public_signup_enabled: bool = True
    mfa_email_code_lifetime_minutes: int = 5

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


settings = Settings()
