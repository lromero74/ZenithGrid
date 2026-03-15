"""
Application-level intrusion detection middleware.

Scans request bodies (POST/PUT/PATCH) AND GET query strings for injection
patterns (SQL, XSS, shell, path traversal). Logs attempts and triggers
fail2ban ban after threshold.

Does NOT block requests — only logs and tracks. This avoids false positives
on legitimate content while still catching repeat offenders.
"""

import logging
import os
import re
import time
import urllib.parse
from collections import defaultdict

logger = logging.getLogger(__name__)

# Patterns that indicate injection attempts
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # SQL injection
    ("sql", re.compile(
        r"(?i)(union\s+select|select\s+.*\s+from\s|insert\s+into\s|"
        r"drop\s+table\s|delete\s+from\s|update\s+.*\s+set\s)"
    )),
    ("sql", re.compile(r"(?i)('\s*or\s+'|'\s*or\s+1\s*=\s*1|--\s*$|;\s*drop\s)")),
    # NoSQL injection (MongoDB-style operators in JSON)
    ("nosql", re.compile(r'(?i)("\$gt"|"\$ne"|"\$lt"|"\$gte"|"\$lte"|"\$regex"|"\$where")')),
    # XSS
    ("xss", re.compile(r"(?i)(<script[\s>]|javascript\s*:|onerror\s*=|onload\s*=)")),
    ("xss", re.compile(r"(?i)(document\.cookie|document\.write|eval\s*\()")),
    # XSS encoded variants (URL-encoded and unicode-escaped)
    ("xss_encoded", re.compile(
        r"(?i)(%3cscript|%3e|\\u003c|\\u003e|&#x3c|&#60|\\x3c|\\x3e)"
    )),
    # Shell injection
    ("shell", re.compile(r"(?i)(/bin/sh|/bin/bash|/etc/passwd|/etc/shadow|cmd\.exe)")),
    ("shell", re.compile(r"(?i)(;\s*ls\s|;\s*cat\s|;\s*rm\s|;\s*wget\s|;\s*curl\s.*\|)")),
    # Command chaining (backticks, $(), || command)
    ("shell_chain", re.compile(r"(`[^`]+`|\$\([^)]+\)|\|\|\s*\w+|\&&\s*\w+)")),
    # Path traversal
    ("traversal", re.compile(r"\.\./\.\.\/")),
    # Code injection (PHP, Python, etc.)
    ("code", re.compile(r"(?i)(base64_decode\s*\(|system\s*\(|exec\s*\(|phpinfo\s*\()")),
    # LDAP injection
    ("ldap", re.compile(r"(\)\(cn=|\)\(uid=|\*\)\(|\(\||\(\&)")),
    # SSRF in request bodies (internal IPs, cloud metadata)
    ("ssrf", re.compile(
        r"(?i)(https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|169\.254\.169\.254"
        r"|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+))"
    )),
    # Template injection (Jinja2, Mako, EL, ERB)
    ("template", re.compile(r"(\{\{.*\}\}|\$\{.*\}|<%.*%>|#\{.*\})")),
    # XML/XXE
    ("xxe", re.compile(r"(?i)(<!DOCTYPE|<!ENTITY|SYSTEM\s+[\"']file://|SYSTEM\s+[\"']https?://)")),
]

# Only scan mutation methods
_SCAN_METHODS = {b"POST", b"PUT", b"PATCH"}

# Max bytes to scan from request body
_MAX_SCAN_BYTES = 4096

# Threshold: N attempts in WINDOW seconds → write [BAN] line
_BAN_THRESHOLD = 2
_BAN_WINDOW = 3600  # 1 hour
_STALE_SECONDS = 7200  # 2 hours

# In-memory tracking: IP → list of timestamps
_ip_attempts: dict[str, list[float]] = defaultdict(list)

# Log file path
_LOG_DIR = "/var/log/zenithgrid"
_LOG_FILE = os.path.join(_LOG_DIR, "intrusion.log")


def _get_client_ip(scope: dict) -> str:
    """Extract client IP from ASGI scope, checking X-Forwarded-For."""
    headers = dict(scope.get("headers", []))
    xff = headers.get(b"x-forwarded-for", b"").decode()
    if xff:
        return xff.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def _write_log(line: str) -> None:
    """Append a line to the intrusion log file."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        logger.debug(f"Failed to write intrusion log: {e}")


def _check_body(body_text: str) -> tuple[str, str] | None:
    """Scan text against injection patterns. Returns (type, matched) or None.

    Checks both raw text and URL-decoded text to catch encoded payloads.
    """
    # Check raw text first
    for pattern_type, regex in _PATTERNS:
        match = regex.search(body_text)
        if match:
            return (pattern_type, match.group(0)[:100])

    # Check URL-decoded version (catches %3Cscript%3E etc.)
    try:
        decoded = urllib.parse.unquote(body_text)
        if decoded != body_text:
            for pattern_type, regex in _PATTERNS:
                match = regex.search(decoded)
                if match:
                    return (pattern_type, match.group(0)[:100])
    except Exception:
        pass

    return None


class IntrusionDetector:
    """ASGI middleware that scans request bodies for injection patterns."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _log_and_track(ip: str, method: str, path: str, pattern_type: str, matched: str):
        """Log an intrusion attempt and check ban threshold."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        safe_content = matched.replace("\n", " ").replace("\r", "")
        log_line = (
            f"{ts} [INTRUSION] {ip} "
            f"{method} {path} "
            f"pattern={pattern_type} "
            f'content="{safe_content}"'
        )
        _write_log(log_line)
        logger.warning(f"Intrusion attempt: {ip} {pattern_type} on {path}")

        now = time.time()
        cutoff = now - _BAN_WINDOW
        attempts = _ip_attempts[ip]
        attempts[:] = [t for t in attempts if t > cutoff]
        attempts.append(now)

        if len(attempts) >= _BAN_THRESHOLD:
            ban_line = (
                f"{ts} [BAN] {ip} "
                f"threshold={_BAN_THRESHOLD} "
                f"attempts_in_{_BAN_WINDOW}s"
            )
            _write_log(ban_line)
            logger.warning(f"Intrusion ban triggered: {ip}")
            _ip_attempts[ip] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Scan GET query strings for injection patterns
        method = scope.get("method", "GET")
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        if query_string:
            result = _check_body(query_string)
            if result:
                ip = _get_client_ip(scope)
                pattern_type, matched = result
                path = scope.get("path", "?")
                self._log_and_track(ip, method, path, pattern_type, matched)

        if method.encode() not in _SCAN_METHODS:
            await self.app(scope, receive, send)
            return

        # Buffer the request body for scanning
        body_parts = []
        body_complete = False

        async def receive_wrapper():
            nonlocal body_complete
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if not body_complete:
                    body_parts.append(chunk)
                if not message.get("more_body", False):
                    body_complete = True
            return message

        # Read the first message to get the body
        first_message = await receive()
        if first_message["type"] == "http.request":
            body_parts.append(first_message.get("body", b""))

        # Scan the body
        body_bytes = b"".join(body_parts)[:_MAX_SCAN_BYTES]
        try:
            body_text = body_bytes.decode("utf-8", errors="ignore")
        except Exception:
            body_text = ""

        if body_text:
            result = _check_body(body_text)
            if result:
                ip = _get_client_ip(scope)
                pattern_type, matched = result
                path = scope.get("path", "?")
                self._log_and_track(ip, method, path, pattern_type, matched)

        # Replay the buffered first message
        first_sent = False

        async def replay_receive():
            nonlocal first_sent
            if not first_sent:
                first_sent = True
                return first_message
            return await receive()

        await self.app(scope, replay_receive, send)

    @classmethod
    def prune_stale(cls) -> int:
        """Remove tracking entries older than stale threshold."""
        now = time.time()
        cutoff = now - _STALE_SECONDS
        stale = [
            ip for ip, attempts in _ip_attempts.items()
            if not attempts or max(attempts) < cutoff
        ]
        for ip in stale:
            del _ip_attempts[ip]
        return len(stale)
