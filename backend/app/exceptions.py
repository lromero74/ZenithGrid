"""
Domain exceptions for the application.

Services raise these instead of fastapi.HTTPException to avoid coupling
the service layer to the web framework. A global exception handler in
main.py translates them into HTTP responses.
"""


class AppError(Exception):
    """Base application error with an HTTP-equivalent status code."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(AppError):
    """Input validation failure (400)."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Not found"):
        super().__init__(message, status_code=404)


class ExchangeUnavailableError(AppError):
    """Exchange API unavailable (503)."""

    def __init__(self, message: str = "Exchange service unavailable"):
        super().__init__(message, status_code=503)


class RateLimitError(AppError):
    """Too many requests (429)."""

    def __init__(self, message: str, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message, status_code=429)


class SessionLimitError(AppError):
    """Session limit exceeded (403)."""

    def __init__(self, message: str = "Session limit reached"):
        super().__init__(message, status_code=403)
