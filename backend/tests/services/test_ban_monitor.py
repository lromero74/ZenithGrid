"""
Tests for backend/app/services/ban_monitor.py

Covers BannedIP/BanSnapshot dataclasses, fail2ban query parsing, IP geo lookup,
snapshot caching, error handling for subprocess failures. All subprocess calls
and network requests are mocked.
"""

import json
import time

import pytest
from unittest.mock import MagicMock, patch

from app.services.ban_monitor import (
    BannedIP,
    BanSnapshot,
    get_ban_snapshot,
    refresh_ban_snapshot,
    _lookup_ip_geo,
    _query_fail2ban,
)
import app.services.ban_monitor as ban_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_snapshot():
    """Reset the global snapshot and geo cache before each test."""
    ban_mod._snapshot = BanSnapshot()
    ban_mod._geo_cache.clear()
    yield
    ban_mod._snapshot = BanSnapshot()
    ban_mod._geo_cache.clear()


# ===========================================================================
# BannedIP dataclass
# ===========================================================================


class TestBannedIP:
    """Tests for the BannedIP dataclass."""

    def test_create_with_all_fields(self):
        """Happy path: create BannedIP with all fields populated."""
        ip = BannedIP(
            ip="1.2.3.4", jail="sshd",
            city="London", region="England", country="GB",
            org="AS1234 Example ISP", hostname="host.example.com",
        )
        assert ip.ip == "1.2.3.4"
        assert ip.jail == "sshd"
        assert ip.country == "GB"

    def test_create_with_defaults(self):
        """Edge case: optional geo fields default to None."""
        ip = BannedIP(ip="5.6.7.8", jail="nginx")
        assert ip.city is None
        assert ip.region is None
        assert ip.country is None
        assert ip.org is None
        assert ip.hostname is None


# ===========================================================================
# BanSnapshot dataclass
# ===========================================================================


class TestBanSnapshot:
    """Tests for the BanSnapshot dataclass."""

    def test_default_snapshot(self):
        """Happy path: default snapshot has zero counts and empty list."""
        snap = BanSnapshot()
        assert snap.banned_ips == []
        assert snap.total_banned == 0
        assert snap.currently_banned == 0
        assert snap.total_failed == 0
        assert snap.last_updated == 0.0

    def test_snapshot_with_data(self):
        """Happy path: snapshot stores data correctly."""
        snap = BanSnapshot(
            banned_ips=[BannedIP(ip="1.1.1.1", jail="sshd")],
            total_banned=5,
            currently_banned=1,
            total_failed=20,
            last_updated=1234567890.0,
        )
        assert len(snap.banned_ips) == 1
        assert snap.total_banned == 5


# ===========================================================================
# get_ban_snapshot
# ===========================================================================


class TestGetBanSnapshot:
    """Tests for get_ban_snapshot()."""

    def test_returns_current_snapshot(self):
        """Happy path: returns the module-level cached snapshot."""
        snap = get_ban_snapshot()
        assert isinstance(snap, BanSnapshot)
        assert snap.total_banned == 0

    def test_returns_updated_snapshot(self):
        """Edge case: returns updated snapshot after module state changes."""
        ban_mod._snapshot = BanSnapshot(total_banned=10, currently_banned=3)
        snap = get_ban_snapshot()
        assert snap.total_banned == 10
        assert snap.currently_banned == 3


# ===========================================================================
# _lookup_ip_geo
# ===========================================================================


class TestLookupIpGeo:
    """Tests for _lookup_ip_geo() — IP geolocation lookup."""

    def test_successful_lookup(self):
        """Happy path: ipinfo.io returns geo data."""
        mock_data = json.dumps({
            "city": "San Francisco",
            "region": "California",
            "country": "US",
            "org": "AS13335 Cloudflare",
            "hostname": "one.one.one.one",
        }).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = _lookup_ip_geo("1.1.1.1")

        assert result["city"] == "San Francisco"
        assert result["country"] == "US"
        assert result["org"] == "AS13335 Cloudflare"

    def test_network_error_returns_empty_dict(self):
        """Failure: network error returns empty dict (logged, not raised)."""
        with patch('urllib.request.urlopen', side_effect=Exception("Connection refused")):
            result = _lookup_ip_geo("1.2.3.4")

        assert result == {}

    def test_timeout_returns_empty_dict(self):
        """Failure: timeout returns empty dict."""
        from urllib.error import URLError
        with patch('urllib.request.urlopen', side_effect=URLError("timeout")):
            result = _lookup_ip_geo("1.2.3.4")

        assert result == {}

    def test_invalid_json_returns_empty_dict(self):
        """Failure: invalid JSON response returns empty dict."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = _lookup_ip_geo("1.2.3.4")

        assert result == {}


# ===========================================================================
# _lookup_ip_geo — geo cache behaviour
# ===========================================================================


class TestLookupIpGeoCache:
    """Tests for the _geo_cache caching layer in _lookup_ip_geo()."""

    def _make_urlopen_mock(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_second_call_uses_cache_not_network(self):
        """Happy path: second lookup for same IP returns cached result without hitting the network."""
        payload = {"city": "London", "country": "GB", "org": "AS5089 Virgin Media", "region": "England", "hostname": None}

        with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)) as mock_open:
            result1 = _lookup_ip_geo("10.0.0.1")
            result2 = _lookup_ip_geo("10.0.0.1")

        assert mock_open.call_count == 1  # Only one HTTP call despite two lookups
        assert result1 == result2
        assert result1["country"] == "GB"

    def test_different_ips_each_make_a_network_call(self):
        """Edge case: distinct IPs are each looked up once via the network."""
        payload = {"city": "X", "country": "US", "org": "AS1 Test", "region": "CA", "hostname": None}

        with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)) as mock_open:
            _lookup_ip_geo("10.0.0.1")
            _lookup_ip_geo("10.0.0.2")
            _lookup_ip_geo("10.0.0.1")  # cache hit — no extra call

        assert mock_open.call_count == 2

    def test_cache_stores_geo_data_in_module_dict(self):
        """Happy path: successful lookup is stored in the module-level _geo_cache."""
        payload = {"city": "Paris", "country": "FR", "org": "AS3215 Orange", "region": "IDF", "hostname": "host.fr"}

        with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)):
            _lookup_ip_geo("192.168.1.1")

        assert "192.168.1.1" in ban_mod._geo_cache
        assert ban_mod._geo_cache["192.168.1.1"]["country"] == "FR"

    def test_failed_lookup_not_cached(self):
        """Failure: network error returns empty dict and is NOT stored in cache (retried next time)."""
        with patch('urllib.request.urlopen', side_effect=Exception("Rate limited")) as mock_open:
            result1 = _lookup_ip_geo("10.0.0.5")
            result2 = _lookup_ip_geo("10.0.0.5")

        assert result1 == {}
        assert result2 == {}
        assert mock_open.call_count == 2  # Both calls hit the network (no cache)
        assert "10.0.0.5" not in ban_mod._geo_cache

    def test_cache_prevents_rate_limit_exhaustion_on_bulk_refresh(self):
        """Regression: many banned IPs refreshed repeatedly must not re-hit ipinfo.io.

        This guards against the bug where Country/ISP showed 'Unknown' because
        ipinfo.io was rate-limited on every manual refresh cycle.
        """
        payload = {"city": "Tokyo", "country": "JP", "org": "AS4713 NTT", "region": "TK", "hostname": None}
        ips = [f"10.0.{i}.{j}" for i in range(5) for j in range(10)]  # 50 IPs

        with patch('urllib.request.urlopen', return_value=self._make_urlopen_mock(payload)) as mock_open:
            # First refresh: all 50 IPs looked up
            for ip in ips:
                _lookup_ip_geo(ip)
            first_run_calls = mock_open.call_count

            # Second refresh (simulate monitor re-run): zero new network calls
            for ip in ips:
                _lookup_ip_geo(ip)
            second_run_calls = mock_open.call_count

        assert first_run_calls == 50
        assert second_run_calls == 50  # No additional calls — all served from cache


# ===========================================================================
# _query_fail2ban
# ===========================================================================


class TestQueryFail2ban:
    """Tests for _query_fail2ban() — subprocess-based fail2ban querying."""

    def test_successful_query_single_jail(self):
        """Happy path: single jail with banned IPs parsed correctly."""
        status_output = "Status\n|- Number of jail:\t1\n`- Jail list:\tsshd\n"
        jail_output = (
            "Status for the jail: sshd\n"
            "|- Filter\n"
            "|  |- Currently failed:\t5\n"
            "|  `- Total failed:\t100\n"
            "`- Actions\n"
            "   |- Currently banned:\t2\n"
            "   |- Total banned:\t10\n"
            "   `- Banned IP list:\t1.2.3.4 5.6.7.8\n"
        )

        def mock_subprocess_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd == ["sudo", "fail2ban-client", "status"]:
                result.stdout = status_output
            elif cmd == ["sudo", "fail2ban-client", "status", "sshd"]:
                result.stdout = jail_output
            return result

        with patch('subprocess.run', side_effect=mock_subprocess_run), \
             patch.object(ban_mod, '_lookup_ip_geo', return_value={"country": "US"}):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 2
        assert snapshot.total_banned == 10
        assert snapshot.total_failed == 100
        assert len(snapshot.banned_ips) == 2
        assert snapshot.banned_ips[0].ip == "1.2.3.4"
        assert snapshot.banned_ips[0].jail == "sshd"
        assert snapshot.banned_ips[0].country == "US"
        assert snapshot.last_updated > 0

    def test_multiple_jails(self):
        """Edge case: multiple jails have their counts summed."""
        status_output = "Status\n`- Jail list:\tsshd, nginx-http-auth\n"
        sshd_output = (
            "Status for the jail: sshd\n"
            "|- Currently banned:\t1\n"
            "|- Total banned:\t5\n"
            "|- Total failed:\t50\n"
            "`- Banned IP list:\t1.1.1.1\n"
        )
        nginx_output = (
            "Status for the jail: nginx-http-auth\n"
            "|- Currently banned:\t3\n"
            "|- Total banned:\t15\n"
            "|- Total failed:\t200\n"
            "`- Banned IP list:\t2.2.2.2 3.3.3.3 4.4.4.4\n"
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd[-1] == "status" and len(cmd) == 3:
                result.stdout = status_output
            elif "sshd" in cmd:
                result.stdout = sshd_output
            elif "nginx-http-auth" in cmd:
                result.stdout = nginx_output
            return result

        with patch('subprocess.run', side_effect=mock_run), \
             patch.object(ban_mod, '_lookup_ip_geo', return_value={}):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 4  # 1 + 3
        assert snapshot.total_banned == 20  # 5 + 15
        assert snapshot.total_failed == 250  # 50 + 200
        assert len(snapshot.banned_ips) == 4

    def test_fail2ban_not_found(self):
        """Failure: fail2ban-client not installed returns empty snapshot."""
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0
        assert snapshot.banned_ips == []

    def test_fail2ban_status_nonzero_return(self):
        """Failure: fail2ban-client returns non-zero exit code."""
        result = MagicMock()
        result.returncode = 1
        result.stderr = "Error: could not find server"

        with patch('subprocess.run', return_value=result):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0

    def test_fail2ban_timeout(self):
        """Failure: subprocess timeout returns empty snapshot."""
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="test", timeout=10)):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0

    def test_empty_jail_list(self):
        """Edge case: no jails configured returns empty snapshot."""
        status_output = "Status\n|- Number of jail:\t0\n`- Jail list:\t\n"

        result = MagicMock()
        result.returncode = 0
        result.stdout = status_output

        with patch('subprocess.run', return_value=result):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0
        assert snapshot.banned_ips == []

    def test_no_banned_ips_in_jail(self):
        """Edge case: jail exists but has no currently banned IPs."""
        status_output = "Status\n`- Jail list:\tsshd\n"
        jail_output = (
            "Status for the jail: sshd\n"
            "|- Currently banned:\t0\n"
            "|- Total banned:\t5\n"
            "|- Total failed:\t50\n"
            "`- Banned IP list:\t\n"
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if len(cmd) == 3:
                result.stdout = status_output
            else:
                result.stdout = jail_output
            return result

        with patch('subprocess.run', side_effect=mock_run):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0
        assert snapshot.total_banned == 5
        assert snapshot.banned_ips == []

    def test_invalid_count_values_ignored(self):
        """Edge case: non-integer count values are silently ignored."""
        status_output = "Status\n`- Jail list:\tsshd\n"
        jail_output = (
            "Status for the jail: sshd\n"
            "|- Currently banned:\tN/A\n"
            "|- Total banned:\tN/A\n"
            "|- Total failed:\tN/A\n"
            "`- Banned IP list:\t\n"
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if len(cmd) == 3:
                result.stdout = status_output
            else:
                result.stdout = jail_output
            return result

        with patch('subprocess.run', side_effect=mock_run):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 0
        assert snapshot.total_banned == 0
        assert snapshot.total_failed == 0


# ===========================================================================
# refresh_ban_snapshot
# ===========================================================================


class TestRefreshBanSnapshot:
    """Tests for refresh_ban_snapshot() — async wrapper."""

    @pytest.mark.asyncio
    async def test_refresh_updates_global_snapshot(self):
        """Happy path: refresh updates the module-level snapshot."""
        new_snapshot = BanSnapshot(currently_banned=5, total_banned=20, last_updated=time.time())

        with patch.object(ban_mod, '_query_fail2ban', return_value=new_snapshot):
            result = await refresh_ban_snapshot()

        assert result.currently_banned == 5
        assert result.total_banned == 20
        # Global state also updated
        assert ban_mod._snapshot.currently_banned == 5
