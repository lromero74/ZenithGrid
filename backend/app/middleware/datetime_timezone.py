"""Middleware to add 'Z' suffix to datetime fields in JSON responses"""
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse


class DatetimeTimezoneMiddleware(BaseHTTPMiddleware):
    """Add 'Z' suffix to ISO datetime strings in JSON responses to indicate UTC"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Only modify JSON responses (not streaming responses)
        if (response.headers.get("content-type", "").startswith("application/json") and
            not isinstance(response, StreamingResponse)):
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Add 'Z' suffix to ISO datetime strings without timezone
            # Pattern: "2025-11-16T01:50:13.090200" -> "2025-11-16T01:50:13.090200Z"
            modified_body = re.sub(
                rb'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)"',
                rb'"\1Z"',
                body
            )

            return Response(
                content=modified_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response
