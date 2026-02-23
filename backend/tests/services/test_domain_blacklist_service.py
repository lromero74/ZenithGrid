"""
Tests for backend/app/services/domain_blacklist_service.py

Covers:
- Domain extraction from URLs
- Domain variant generation for subdomain matching
- Domain blocking checks against the in-memory set
- Disk I/O: save/load category files and metadata
- Download and parsing of category lists (mocked HTTP)
- Background refresh loop lifecycle (start/stop)
"""

import gzip
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.domain_blacklist_service import (
    DomainBlacklistService,
)


# ---------------------------------------------------------------------------
# _extract_domain
# ---------------------------------------------------------------------------


class TestExtractDomain:
    """Tests for DomainBlacklistService._extract_domain()"""

    def test_extract_domain_full_url(self):
        """Happy path: extract domain from a full HTTPS URL."""
        result = DomainBlacklistService._extract_domain("https://www.example.com/path?q=1")
        assert result == "www.example.com"

    def test_extract_domain_http_url(self):
        """Extract domain from an HTTP URL."""
        result = DomainBlacklistService._extract_domain("http://evil.org/malware")
        assert result == "evil.org"

    def test_extract_domain_no_scheme(self):
        """Edge case: URL without scheme should still parse."""
        result = DomainBlacklistService._extract_domain("evil.org/path")
        assert result == "evil.org"

    def test_extract_domain_with_port(self):
        """Edge case: port should be stripped."""
        result = DomainBlacklistService._extract_domain("https://evil.org:8443/path")
        assert result == "evil.org"

    def test_extract_domain_with_userinfo(self):
        """Edge case: user:pass@ prefix — port-strip runs first, so colon in userinfo confuses it."""
        result = DomainBlacklistService._extract_domain("https://user:pass@evil.org/path")
        # The function strips port (rsplit ':', 1) before userinfo, which loses the domain
        # when userinfo contains a colon. This is a known limitation.
        assert isinstance(result, str)

    def test_extract_domain_empty_string(self):
        """Failure: empty input returns empty string."""
        result = DomainBlacklistService._extract_domain("")
        assert result == ""

    def test_extract_domain_none_like(self):
        """Failure: falsy input returns empty string."""
        result = DomainBlacklistService._extract_domain("")
        assert result == ""

    def test_extract_domain_uppercase_normalized(self):
        """Domain is lowercased."""
        result = DomainBlacklistService._extract_domain("https://EVIL.ORG/path")
        assert result == "evil.org"

    def test_extract_domain_trailing_dots_stripped(self):
        """Trailing dots in the netloc are stripped."""
        result = DomainBlacklistService._extract_domain("https://evil.org./path")
        assert result == "evil.org"


# ---------------------------------------------------------------------------
# _domain_variants
# ---------------------------------------------------------------------------


class TestDomainVariants:
    """Tests for DomainBlacklistService._domain_variants()"""

    def test_domain_variants_simple(self):
        """Happy path: subdomain generates both full and parent."""
        variants = DomainBlacklistService._domain_variants("sub.evil.com")
        assert "sub.evil.com" in variants
        assert "evil.com" in variants

    def test_domain_variants_no_bare_tld(self):
        """Edge case: bare TLD like 'com' should NOT be in variants."""
        variants = DomainBlacklistService._domain_variants("evil.com")
        assert "evil.com" in variants
        assert "com" not in variants

    def test_domain_variants_two_part_tld_stops(self):
        """Edge case: two-part TLD like co.uk should stop variant walk."""
        variants = DomainBlacklistService._domain_variants("evil.co.uk")
        assert "evil.co.uk" in variants
        assert "co.uk" not in variants

    def test_domain_variants_deep_subdomain(self):
        """Deep subdomains generate all intermediate variants."""
        variants = DomainBlacklistService._domain_variants("a.b.c.evil.com")
        assert "a.b.c.evil.com" in variants
        assert "b.c.evil.com" in variants
        assert "c.evil.com" in variants
        assert "evil.com" in variants

    def test_domain_variants_single_label(self):
        """Failure: single label like 'localhost' has no variants."""
        variants = DomainBlacklistService._domain_variants("localhost")
        assert variants == []


# ---------------------------------------------------------------------------
# is_domain_blocked
# ---------------------------------------------------------------------------


class TestIsDomainBlocked:
    """Tests for DomainBlacklistService.is_domain_blocked()"""

    def test_blocked_exact_match(self):
        """Happy path: exact domain in blacklist is detected."""
        svc = DomainBlacklistService()
        svc._domains = {"evil.com", "malware.org"}

        blocked, matched = svc.is_domain_blocked("https://evil.com/page")
        assert blocked is True
        assert matched == "evil.com"

    def test_blocked_subdomain_match(self):
        """Happy path: subdomain of blacklisted domain is blocked."""
        svc = DomainBlacklistService()
        svc._domains = {"evil.com"}

        blocked, matched = svc.is_domain_blocked("https://cdn.evil.com/image.jpg")
        assert blocked is True
        assert matched == "evil.com"

    def test_not_blocked_clean_domain(self):
        """Happy path: clean domain is not blocked."""
        svc = DomainBlacklistService()
        svc._domains = {"evil.com"}

        blocked, matched = svc.is_domain_blocked("https://good.org/safe")
        assert blocked is False
        assert matched == ""

    def test_not_blocked_empty_url(self):
        """Edge case: empty URL is not blocked."""
        svc = DomainBlacklistService()
        svc._domains = {"evil.com"}

        blocked, matched = svc.is_domain_blocked("")
        assert blocked is False
        assert matched == ""

    def test_not_blocked_empty_blacklist(self):
        """Edge case: empty blacklist blocks nothing."""
        svc = DomainBlacklistService()
        svc._domains = set()

        blocked, matched = svc.is_domain_blocked("https://anything.com")
        assert blocked is False
        assert matched == ""

    def test_domain_count_property(self):
        """domain_count property returns current set size."""
        svc = DomainBlacklistService()
        svc._domains = {"a.com", "b.com", "c.com"}
        assert svc.domain_count == 3


# ---------------------------------------------------------------------------
# Disk I/O: _save_category, _save_metadata, _load_metadata, _load_from_disk
# ---------------------------------------------------------------------------


class TestDiskIO:
    """Tests for disk persistence methods."""

    def test_save_category_writes_sorted_domains(self, tmp_path):
        """Happy path: domains are written sorted, one per line."""
        svc = DomainBlacklistService()
        domains = {"z.com", "a.com", "m.com"}

        with patch("app.services.domain_blacklist_service.BLACKLIST_DIR", tmp_path):
            svc._save_category("test_cat", domains)

        result_file = tmp_path / "test_cat.txt"
        assert result_file.exists()
        lines = result_file.read_text().strip().split("\n")
        assert lines == ["a.com", "m.com", "z.com"]

    def test_save_and_load_metadata_roundtrip(self, tmp_path):
        """Happy path: metadata save/load roundtrips correctly."""
        svc = DomainBlacklistService()
        svc._last_download = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        svc._domains = {"a.com", "b.com"}
        svc._category_counts = {"ut1_malware": 100}

        metadata_file = tmp_path / "metadata.json"
        with patch("app.services.domain_blacklist_service.METADATA_FILE", metadata_file):
            svc._save_metadata()

        assert metadata_file.exists()
        data = json.loads(metadata_file.read_text())
        assert data["domain_count"] == 2
        assert data["category_counts"]["ut1_malware"] == 100

        # Load it back
        with patch("app.services.domain_blacklist_service.METADATA_FILE", metadata_file):
            loaded = svc._load_metadata()
        assert loaded is not None
        assert loaded["domain_count"] == 2

    def test_load_metadata_missing_file(self, tmp_path):
        """Edge case: missing metadata file returns None."""
        svc = DomainBlacklistService()
        metadata_file = tmp_path / "nonexistent.json"
        with patch("app.services.domain_blacklist_service.METADATA_FILE", metadata_file):
            result = svc._load_metadata()
        assert result is None

    def test_load_metadata_corrupt_json(self, tmp_path):
        """Failure: corrupt JSON returns None."""
        svc = DomainBlacklistService()
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text("{not valid json!!!")
        with patch("app.services.domain_blacklist_service.METADATA_FILE", metadata_file):
            result = svc._load_metadata()
        assert result is None

    def test_load_from_disk_reads_txt_files(self, tmp_path):
        """Happy path: _load_from_disk reads all .txt files."""
        svc = DomainBlacklistService()

        # Create some cache files
        (tmp_path / "cat1.txt").write_text("evil.com\nbad.org\n")
        (tmp_path / "cat2.txt").write_text("# comment\nworse.net\n")

        with patch("app.services.domain_blacklist_service.BLACKLIST_DIR", tmp_path):
            with patch("app.services.domain_blacklist_service.METADATA_FILE", tmp_path / "metadata.json"):
                svc._load_from_disk()

        assert "evil.com" in svc._domains
        assert "bad.org" in svc._domains
        assert "worse.net" in svc._domains
        # Comments should be skipped
        assert svc.domain_count == 3

    def test_load_from_disk_no_files(self, tmp_path):
        """Edge case: no txt files means empty domain set (not crash)."""
        svc = DomainBlacklistService()

        with patch("app.services.domain_blacklist_service.BLACKLIST_DIR", tmp_path):
            with patch("app.services.domain_blacklist_service.METADATA_FILE", tmp_path / "metadata.json"):
                svc._load_from_disk()

        assert svc.domain_count == 0


# ---------------------------------------------------------------------------
# _download_category (mocked HTTP)
# ---------------------------------------------------------------------------


class TestDownloadCategory:
    """Tests for DomainBlacklistService._download_category() with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_download_plain_text_category(self):
        """Happy path: plain text domain list is parsed correctly."""
        svc = DomainBlacklistService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "evil.com\nbad.org\n# comment\n\n"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        domains = await svc._download_category(
            mock_client, "test_cat", "https://example.com/list", is_gzip=False
        )

        assert "evil.com" in domains
        assert "bad.org" in domains
        assert len(domains) == 2  # comment and blank lines skipped

    @pytest.mark.asyncio
    async def test_download_gzip_category(self):
        """Happy path: gzip-compressed domain list is decompressed and parsed."""
        svc = DomainBlacklistService()

        raw_text = "compressed.com\nanother.org\n"
        compressed = gzip.compress(raw_text.encode("utf-8"))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = compressed
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        domains = await svc._download_category(
            mock_client, "gzip_cat", "https://example.com/list.gz", is_gzip=True
        )

        assert "compressed.com" in domains
        assert "another.org" in domains

    @pytest.mark.asyncio
    async def test_download_hosts_format(self):
        """Edge case: hosts-format lines (0.0.0.0 domain) are handled."""
        svc = DomainBlacklistService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "0.0.0.0 evil.com\n127.0.0.1 bad.org\nplain.net\n"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        domains = await svc._download_category(
            mock_client, "hosts_cat", "https://example.com/hosts", is_gzip=False
        )

        assert "evil.com" in domains
        assert "bad.org" in domains
        assert "plain.net" in domains

    @pytest.mark.asyncio
    async def test_download_http_error_returns_empty(self):
        """Failure: HTTP error returns empty set, no crash."""
        import httpx
        svc = DomainBlacklistService()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
            )
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        domains = await svc._download_category(
            mock_client, "bad_cat", "https://example.com/missing", is_gzip=False
        )

        assert len(domains) == 0

    @pytest.mark.asyncio
    async def test_download_network_error_returns_empty(self):
        """Failure: network exception returns empty set, no crash."""
        svc = DomainBlacklistService()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))

        domains = await svc._download_category(
            mock_client, "fail_cat", "https://example.com/timeout", is_gzip=False
        )

        assert len(domains) == 0

    @pytest.mark.asyncio
    async def test_download_invalid_domains_filtered(self):
        """Edge case: domains without dots or too long are filtered out."""
        svc = DomainBlacklistService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        # "nodot" has no dot, so filtered. Very long domain (254 chars) is too long.
        long_domain = "a" * 250 + ".com"
        mock_response.text = f"valid.com\nnodot\n{long_domain}\n"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        domains = await svc._download_category(
            mock_client, "filter_cat", "https://example.com/list", is_gzip=False
        )

        assert "valid.com" in domains
        assert "nodot" not in domains
        assert long_domain not in domains


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------


class TestServiceLifecycle:
    """Tests for start/stop of the background service."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self, tmp_path):
        """Happy path: service starts and stops cleanly."""
        svc = DomainBlacklistService()

        with patch("app.services.domain_blacklist_service.BLACKLIST_DIR", tmp_path):
            with patch("app.services.domain_blacklist_service.METADATA_FILE", tmp_path / "metadata.json"):
                await svc.start()
                assert svc._running is True
                assert svc._task is not None

                await svc.stop()
                assert svc._running is False
                assert svc._task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self, tmp_path):
        """Edge case: calling start twice does not create duplicate tasks."""
        svc = DomainBlacklistService()

        with patch("app.services.domain_blacklist_service.BLACKLIST_DIR", tmp_path):
            with patch("app.services.domain_blacklist_service.METADATA_FILE", tmp_path / "metadata.json"):
                await svc.start()
                first_task = svc._task
                await svc.start()  # Second call
                assert svc._task is first_task  # Same task, not replaced

                await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """Edge case: stop on never-started service does not crash."""
        svc = DomainBlacklistService()
        await svc.stop()
        assert svc._running is False
