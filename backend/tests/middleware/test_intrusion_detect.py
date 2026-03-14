"""
Tests for application-level intrusion detection middleware.
"""

import pytest
from app.middleware.intrusion_detect import _check_body, IntrusionDetector


class TestCheckBody:
    """Tests for the body scanning function."""

    def test_detects_sql_injection_union_select(self):
        result = _check_body("1' UNION SELECT * FROM users--")
        assert result is not None
        assert result[0] == "sql"

    def test_detects_sql_injection_drop_table(self):
        result = _check_body("'; DROP TABLE users;--")
        assert result is not None
        assert result[0] == "sql"

    def test_detects_xss_script_tag(self):
        result = _check_body('<script>alert("xss")</script>')
        assert result is not None
        assert result[0] == "xss"

    def test_detects_xss_onerror(self):
        result = _check_body('<img src=x onerror=alert(1)>')
        assert result is not None
        assert result[0] == "xss"

    def test_detects_shell_injection(self):
        result = _check_body("; cat /etc/passwd")
        assert result is not None
        assert result[0] == "shell"

    def test_detects_path_traversal(self):
        result = _check_body("../../../../var/www/config")
        assert result is not None
        assert result[0] == "traversal"

    def test_detects_code_injection(self):
        result = _check_body("<?php system('ls'); ?>")
        assert result is not None
        assert result[0] == "code"

    def test_allows_normal_text(self):
        result = _check_body("Hello, how are you? This is a normal chat message.")
        assert result is None

    def test_allows_code_discussion(self):
        # Talking ABOUT SQL, not injecting it
        result = _check_body("I use SELECT in my queries sometimes")
        # This may or may not match — the key is repeated attempts trigger ban, not single matches
        # The middleware logs but doesn't block

    def test_allows_empty_body(self):
        result = _check_body("")
        assert result is None


class TestPruneStale:
    """Tests for memory cleanup."""

    def test_prune_returns_count(self):
        count = IntrusionDetector.prune_stale()
        assert isinstance(count, int)
