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
    _lookup_ip_geo_batch,
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
            country_name="United Kingdom",
            org="Virgin Media", hostname="host.example.com",
        )
        assert ip.ip == "1.2.3.4"
        assert ip.jail == "sshd"
        assert ip.country == "GB"
        assert ip.country_name == "United Kingdom"

    def test_create_with_defaults(self):
        """Edge case: optional geo fields default to None."""
        ip = BannedIP(ip="5.6.7.8", jail="nginx")
        assert ip.city is None
        assert ip.region is None
        assert ip.country is None
        assert ip.country_name is None
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
# _lookup_ip_geo_batch — ip-api.com batch endpoint
# ===========================================================================


def _make_batch_response(ips: list[str], country: str = "US", country_code: str = "US",
                         city: str = "New York", region: str = "New York",
                         isp: str = "Test ISP") -> bytes:
    """Build a mock ip-api.com batch JSON response for the given IPs."""
    entries = [
        {
            "query": ip,
            "status": "success",
            "country": country,
            "countryCode": country_code,
            "regionName": region,
            "city": city,
            "isp": isp,
        }
        for ip in ips
    ]
    return json.dumps(entries).encode()


def _make_urlopen_mock(body: bytes) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestLookupIpGeoBatch:
    """Tests for _lookup_ip_geo_batch() — batch geo lookup via ip-api.com."""

    def test_successful_batch_lookup(self):
        """Happy path: batch returns correct geo data for all queried IPs."""
        ips = ["1.1.1.1", "8.8.8.8"]
        body = _make_batch_response(ips, country="United States", country_code="US", isp="Google LLC")

        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)):
            result = _lookup_ip_geo_batch(ips)

        assert set(result.keys()) == {"1.1.1.1", "8.8.8.8"}
        assert result["1.1.1.1"]["country"] == "US"
        assert result["1.1.1.1"]["country_name"] == "United States"
        assert result["1.1.1.1"]["org"] == "Google LLC"
        assert result["1.1.1.1"]["region"] == "New York"

    def test_single_ip_lookup(self):
        """Happy path: single IP lookup returns a dict with the IP key."""
        body = _make_batch_response(["10.0.0.1"], country="Canada", country_code="CA", isp="Rogers")
        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)):
            result = _lookup_ip_geo_batch(["10.0.0.1"])
        assert result["10.0.0.1"]["country"] == "CA"
        assert result["10.0.0.1"]["country_name"] == "Canada"

    def test_failed_status_returns_empty_dict(self):
        """Failure: ip-api returns status='fail' → empty dict for that IP (not cached)."""
        body = json.dumps([{"query": "1.2.3.4", "status": "fail", "message": "private range"}]).encode()
        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)):
            result = _lookup_ip_geo_batch(["1.2.3.4"])
        assert result["1.2.3.4"] == {}
        assert "1.2.3.4" not in ban_mod._geo_cache

    def test_network_error_returns_empty_dicts_for_batch(self):
        """Failure: network error returns {} for all IPs in the failed batch."""
        with patch('urllib.request.urlopen', side_effect=Exception("Connection refused")):
            result = _lookup_ip_geo_batch(["1.1.1.1", "2.2.2.2"])
        assert result["1.1.1.1"] == {}
        assert result["2.2.2.2"] == {}

    def test_empty_list_returns_empty_dict_no_network(self):
        """Edge case: empty input list returns empty result without any network calls."""
        with patch('urllib.request.urlopen') as mock_open:
            result = _lookup_ip_geo_batch([])
        assert result == {}
        mock_open.assert_not_called()

    def test_all_cached_makes_zero_network_calls(self):
        """Edge case: when all IPs are cached, no network requests are made."""
        ban_mod._geo_cache["1.2.3.4"] = {"country": "US", "country_name": "United States",
                                          "city": None, "org": None, "region": None, "hostname": None}
        ban_mod._geo_cache["5.6.7.8"] = {"country": "GB", "country_name": "United Kingdom",
                                          "city": None, "org": None, "region": None, "hostname": None}
        with patch('urllib.request.urlopen') as mock_open:
            result = _lookup_ip_geo_batch(["1.2.3.4", "5.6.7.8"])
        mock_open.assert_not_called()
        assert result["1.2.3.4"]["country"] == "US"
        assert result["5.6.7.8"]["country"] == "GB"

    def test_partial_cache_only_fetches_uncached(self):
        """Edge case: IPs already in cache are not fetched; only uncached IPs are requested."""
        ban_mod._geo_cache["1.2.3.4"] = {"country": "DE", "country_name": "Germany",
                                          "city": None, "org": None, "region": None, "hostname": None}
        body = _make_batch_response(["5.6.7.8"], country="France", country_code="FR")

        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)) as mock_open:
            result = _lookup_ip_geo_batch(["1.2.3.4", "5.6.7.8"])

        assert mock_open.call_count == 1
        assert result["1.2.3.4"]["country"] == "DE"   # From cache
        assert result["5.6.7.8"]["country"] == "FR"   # From network

    def test_deduplicates_duplicate_ips(self):
        """Edge case: duplicate IPs in the list result in only one network call."""
        body = _make_batch_response(["1.1.1.1"], country="Japan", country_code="JP")
        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)) as mock_open:
            result = _lookup_ip_geo_batch(["1.1.1.1", "1.1.1.1", "1.1.1.1"])
        assert mock_open.call_count == 1
        assert result["1.1.1.1"]["country"] == "JP"

    def test_successful_lookup_stored_in_cache(self):
        """Happy path: successful lookups are stored in _geo_cache for future use."""
        body = _make_batch_response(["192.168.1.1"], country="France", country_code="FR", city="Paris")
        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)):
            _lookup_ip_geo_batch(["192.168.1.1"])
        assert "192.168.1.1" in ban_mod._geo_cache
        assert ban_mod._geo_cache["192.168.1.1"]["country"] == "FR"
        assert ban_mod._geo_cache["192.168.1.1"]["city"] == "Paris"

    def test_failed_lookup_not_cached(self):
        """Failure: IPs that fail lookup are not cached so they can be retried next run."""
        with patch('urllib.request.urlopen', side_effect=Exception("Timeout")):
            _lookup_ip_geo_batch(["9.9.9.9"])
        assert "9.9.9.9" not in ban_mod._geo_cache

    def test_batches_large_lists(self):
        """Edge case: lists > 100 IPs are split into batches of 100."""
        ips = [f"10.0.{i // 256}.{i % 256}" for i in range(250)]

        call_count = [0]

        def urlopen_side_effect(req, timeout=None):
            body = json.loads(req.data)
            call_count[0] += 1
            response_data = [
                {"query": ip, "status": "success", "country": "US", "countryCode": "US",
                 "regionName": "CA", "city": "X", "isp": "ISP"}
                for ip in body
            ]
            return _make_urlopen_mock(json.dumps(response_data).encode())

        with patch('urllib.request.urlopen', side_effect=urlopen_side_effect):
            result = _lookup_ip_geo_batch(ips)

        assert call_count[0] == 3  # ceil(250/100) = 3 batches
        assert len(result) == 250

    def test_cache_prevents_rate_limit_exhaustion(self):
        """Regression: IPs looked up once are served from cache on subsequent refreshes.

        Guards against the bug where Country/ISP showed 'Unknown' because
        ip-api.com was being re-queried on every refresh cycle.
        """
        ips = [f"10.0.{i}.1" for i in range(10)]
        body = _make_batch_response(ips, country="United States", country_code="US")

        with patch('urllib.request.urlopen', return_value=_make_urlopen_mock(body)) as mock_open:
            # First refresh: all IPs fetched
            _lookup_ip_geo_batch(ips)
            first_call_count = mock_open.call_count

            # Second refresh: zero new network calls (all in cache)
            _lookup_ip_geo_batch(ips)
            second_call_count = mock_open.call_count

        assert first_call_count == 1   # One batch request
        assert second_call_count == 1  # No additional requests


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

        batch_result = {
            "1.2.3.4": {"country": "US", "country_name": "United States",
                         "city": None, "org": None, "region": None, "hostname": None},
            "5.6.7.8": {"country": "US", "country_name": "United States",
                         "city": None, "org": None, "region": None, "hostname": None},
        }

        with patch('subprocess.run', side_effect=mock_subprocess_run), \
             patch.object(ban_mod, '_lookup_ip_geo_batch', return_value=batch_result):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 2
        assert snapshot.total_banned == 10
        assert snapshot.total_failed == 100
        assert len(snapshot.banned_ips) == 2
        assert snapshot.banned_ips[0].ip == "1.2.3.4"
        assert snapshot.banned_ips[0].jail == "sshd"
        assert snapshot.banned_ips[0].country == "US"
        assert snapshot.banned_ips[0].country_name == "United States"
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

        batch_result = {
            "1.1.1.1": {}, "2.2.2.2": {}, "3.3.3.3": {}, "4.4.4.4": {},
        }

        with patch('subprocess.run', side_effect=mock_run), \
             patch.object(ban_mod, '_lookup_ip_geo_batch', return_value=batch_result):
            snapshot = _query_fail2ban()

        assert snapshot.currently_banned == 4  # 1 + 3
        assert snapshot.total_banned == 20     # 5 + 15
        assert snapshot.total_failed == 250    # 50 + 200
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

    def test_query_fail2ban_uses_batch_lookup(self):
        """Happy path: _query_fail2ban calls _lookup_ip_geo_batch for all IPs at once."""
        status_output = "Status\n`- Jail list:\tsshd\n"
        jail_output = (
            "Status for the jail: sshd\n"
            "|- Currently banned:\t3\n"
            "|- Total banned:\t3\n"
            "|- Total failed:\t30\n"
            "`- Banned IP list:\t1.1.1.1 2.2.2.2 3.3.3.3\n"
        )

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if len(cmd) == 3:
                result.stdout = status_output
            else:
                result.stdout = jail_output
            return result

        batch_result = {
            "1.1.1.1": {"country": "US", "country_name": "United States",
                         "city": None, "org": None, "region": None, "hostname": None},
            "2.2.2.2": {"country": "DE", "country_name": "Germany",
                         "city": None, "org": None, "region": None, "hostname": None},
            "3.3.3.3": {"country": "JP", "country_name": "Japan",
                         "city": None, "org": None, "region": None, "hostname": None},
        }

        with patch('subprocess.run', side_effect=mock_run), \
             patch.object(ban_mod, '_lookup_ip_geo_batch', return_value=batch_result) as mock_batch:
            snapshot = _query_fail2ban()

        mock_batch.assert_called_once()
        call_args = mock_batch.call_args[0][0]
        assert set(call_args) == {"1.1.1.1", "2.2.2.2", "3.3.3.3"}
        assert len(snapshot.banned_ips) == 3
        assert snapshot.banned_ips[0].country == "US"
        assert snapshot.banned_ips[0].country_name == "United States"


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
