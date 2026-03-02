"""
Database Models — domain-organized package.

All model classes are re-exported here so existing imports continue to work:
    from app.models import User, Bot, Position, ...
"""

from app.database import Base  # noqa: F401 — re-exported for tests/conftest.py
from app.models.auth import (
    user_groups, group_roles, role_permissions,
    User, Group, Role, Permission,
    TrustedDevice, EmailVerificationToken, RevokedToken, ActiveSession,
)
from app.models.trading import (
    Account, Bot, BotProduct, BotTemplate, BotTemplateProduct,
    Position, Trade, Signal, PendingOrder, OrderHistory, BlacklistedCoin,
)
from app.models.content import (
    AIProviderCredential, NewsArticle, VideoArticle, ContentSource,
    UserSourceSubscription, ArticleTTS, UserVoiceSubscription,
    UserArticleTTSHistory, UserContentSeenStatus,
)
from app.models.reporting import (
    AccountValueSnapshot, MetricSnapshot, PropFirmState, PropFirmEquitySnapshot,
    ReportGoal, ExpenseItem, GoalProgressSnapshot,
    ReportSchedule, ReportScheduleGoal, Report, AccountTransfer,
)
from app.models.system import (
    Settings, MarketData, AIBotLog, ScannerLog, IndicatorLog,
)

__all__ = [
    "Base",
    # Auth
    "user_groups", "group_roles", "role_permissions",
    "User", "Group", "Role", "Permission",
    "TrustedDevice", "EmailVerificationToken", "RevokedToken", "ActiveSession",
    # Trading
    "Account", "Bot", "BotProduct", "BotTemplate", "BotTemplateProduct",
    "Position", "Trade", "Signal", "PendingOrder", "OrderHistory", "BlacklistedCoin",
    # Content
    "AIProviderCredential", "NewsArticle", "VideoArticle", "ContentSource",
    "UserSourceSubscription", "ArticleTTS", "UserVoiceSubscription",
    "UserArticleTTSHistory", "UserContentSeenStatus",
    # Reporting
    "AccountValueSnapshot", "MetricSnapshot", "PropFirmState", "PropFirmEquitySnapshot",
    "ReportGoal", "ExpenseItem", "GoalProgressSnapshot",
    "ReportSchedule", "ReportScheduleGoal", "Report", "AccountTransfer",
    # System
    "Settings", "MarketData", "AIBotLog", "ScannerLog", "IndicatorLog",
]
