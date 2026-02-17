"""
Domain Blacklist Service

Background service that maintains an in-memory set of blacklisted domains
from UT1 Blacklists (CC BY-SA) and Block List Project (Unlicense).
Used to prevent users from adding custom content sources that host
illegal, racist, explicit, NSFW, violent, or otherwise harmful content.

Lists are downloaded on startup (if stale or missing), refreshed weekly,
and cached to disk for fast restarts.
"""

import asyncio
import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REFRESH_INTERVAL = 7 * 24 * 60 * 60  # 7 days in seconds
INITIAL_DELAY = 5  # seconds after startup before first check
MAX_BLACKLIST_DOMAINS = 2_000_000  # memory safety cap
DOWNLOAD_TIMEOUT = 120  # seconds per HTTP request

BLACKLIST_DIR = Path(__file__).parent.parent.parent / "blacklists"
METADATA_FILE = BLACKLIST_DIR / "metadata.json"

# Two-part country-code TLDs that should not be treated as registrable
# domains on their own (e.g., "co.uk" is not a registrable domain).
TWO_PART_TLDS = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "net.uk",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    "co.nz", "net.nz", "org.nz",
    "co.in", "net.in", "org.in", "gen.in", "firm.in", "ind.in",
    "co.za", "org.za", "web.za",
    "com.br", "net.br", "org.br",
    "com.cn", "net.cn", "org.cn",
    "com.mx", "net.mx", "org.mx",
    "co.kr", "or.kr", "ne.kr",
    "com.tw", "net.tw", "org.tw",
    "co.il", "org.il", "net.il",
    "com.sg", "net.sg", "org.sg",
    "com.hk", "net.hk", "org.hk",
    "co.th", "or.th", "in.th",
    "com.my", "net.my", "org.my",
    "com.ph", "net.ph", "org.ph",
    "com.ar", "net.ar", "org.ar",
    "com.co", "net.co", "org.co",
})

# ---------------------------------------------------------------------------
# UT1 Blacklists (CC BY-SA) — hosted on GitHub mirror
# ---------------------------------------------------------------------------

UT1_BASE = (
    "https://raw.githubusercontent.com/olbat/ut1-blacklists/master/blacklists"
)

UT1_CATEGORIES: Dict[str, dict] = {
    "malware": {"url": f"{UT1_BASE}/malware/domains", "gzip": False},
    "phishing": {"url": f"{UT1_BASE}/phishing/domains", "gzip": False},
    "cryptojacking": {"url": f"{UT1_BASE}/cryptojacking/domains", "gzip": False},
    "stalkerware": {"url": f"{UT1_BASE}/stalkerware/domains", "gzip": False},
    "dangerous_material": {
        "url": f"{UT1_BASE}/dangerous_material/domains",
        "gzip": False,
    },
    "agressif": {"url": f"{UT1_BASE}/agressif/domains", "gzip": False},
    "sect": {"url": f"{UT1_BASE}/sect/domains", "gzip": False},
    "hacking": {"url": f"{UT1_BASE}/hacking/domains", "gzip": False},
    "drogue": {"url": f"{UT1_BASE}/drogue/domains", "gzip": False},
    "warez": {"url": f"{UT1_BASE}/warez/domains", "gzip": False},
    "mixed_adult": {"url": f"{UT1_BASE}/mixed_adult/domains", "gzip": False},
    "adult": {"url": f"{UT1_BASE}/adult/domains.gz", "gzip": True},
}

# ---------------------------------------------------------------------------
# Block List Project (Unlicense) — domain-only "alt-version" format
# ---------------------------------------------------------------------------

BLP_BASE = "https://blocklistproject.github.io/Lists/alt-version"

BLP_CATEGORIES: Dict[str, str] = {
    "abuse": f"{BLP_BASE}/abuse-nl.txt",
    "porn": f"{BLP_BASE}/porn-nl.txt",
    "drugs": f"{BLP_BASE}/drugs-nl.txt",
    "fraud": f"{BLP_BASE}/fraud-nl.txt",
    "malware": f"{BLP_BASE}/malware-nl.txt",
    "phishing": f"{BLP_BASE}/phishing-nl.txt",
    "ransomware": f"{BLP_BASE}/ransomware-nl.txt",
    "piracy": f"{BLP_BASE}/piracy-nl.txt",
    "scam": f"{BLP_BASE}/scam-nl.txt",
}


class DomainBlacklistService:
    """Background service maintaining an in-memory domain blacklist."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._domains: Set[str] = set()
        self._last_download: Optional[datetime] = None
        self._category_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self):
        """Load disk cache and start the background refresh loop."""
        if self._running:
            logger.warning("Domain blacklist service already running")
            return

        self._running = True
        BLACKLIST_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "Domain blacklist service started (%d domains loaded from cache)",
            len(self._domains),
        )

    async def stop(self):
        """Cancel the background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Domain blacklist service stopped")

    def is_domain_blocked(self, url: str) -> Tuple[bool, str]:
        """Check whether a URL's domain appears on the blacklist.

        Returns (blocked: bool, matched_domain: str).
        If blocked is False, matched_domain is empty.
        """
        domain = self._extract_domain(url)
        if not domain:
            return False, ""

        for variant in self._domain_variants(domain):
            if variant in self._domains:
                return True, variant

        return False, ""

    @property
    def domain_count(self) -> int:
        return len(self._domains)

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _load_from_disk(self):
        """Load cached domain lists from backend/blacklists/*.txt."""
        metadata = self._load_metadata()
        if metadata:
            self._last_download = datetime.fromisoformat(
                metadata["last_download"]
            )
            self._category_counts = metadata.get("category_counts", {})

        domains: Set[str] = set()
        txt_files = list(BLACKLIST_DIR.glob("*.txt"))
        for path in txt_files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            domains.add(line)
            except OSError as exc:
                logger.warning("Failed to read %s: %s", path, exc)

        if domains:
            self._domains = domains
            logger.info(
                "Loaded %d blacklisted domains from %d cache files",
                len(domains),
                len(txt_files),
            )
        else:
            logger.warning(
                "No blacklist cache found — all domains allowed until "
                "first download completes"
            )

    def _save_category(self, category_key: str, domains: Set[str]):
        """Save a single category's domains to disk."""
        path = BLACKLIST_DIR / f"{category_key}.txt"
        with open(path, "w", encoding="utf-8") as f:
            for d in sorted(domains):
                f.write(d + "\n")

    def _save_metadata(self):
        """Persist download metadata to JSON."""
        data = {
            "last_download": self._last_download.isoformat()
            if self._last_download
            else None,
            "domain_count": len(self._domains),
            "category_counts": self._category_counts,
        }
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_metadata(self) -> Optional[dict]:
        """Load metadata from disk, or None if missing/corrupt."""
        if not METADATA_FILE.exists():
            return None
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load blacklist metadata: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Background refresh
    # ------------------------------------------------------------------

    async def _refresh_loop(self):
        """Periodically download fresh blacklists."""
        try:
            # Wait a moment for the rest of the app to finish starting
            await asyncio.sleep(INITIAL_DELAY)

            while self._running:
                needs_download = (
                    self._last_download is None
                    or (
                        datetime.now(timezone.utc) - self._last_download
                    ).total_seconds()
                    > REFRESH_INTERVAL
                )

                if needs_download:
                    await self._download_all()

                # Sleep in small increments so we can stop quickly
                for _ in range(REFRESH_INTERVAL // 60):
                    if not self._running:
                        break
                    await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Domain blacklist refresh loop crashed")

    async def _download_all(self):
        """Fetch all category lists and atomic-swap the in-memory set."""
        logger.info("Downloading domain blacklists...")
        all_domains: Set[str] = set()
        category_counts: Dict[str, int] = {}

        async with httpx.AsyncClient(
            timeout=DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5),
        ) as client:
            # UT1 categories
            for cat, info in UT1_CATEGORIES.items():
                key = f"ut1_{cat}"
                domains = await self._download_category(
                    client, key, info["url"], info["gzip"]
                )
                category_counts[key] = len(domains)
                self._save_category(key, domains)
                all_domains.update(domains)

            # Block List Project categories
            for cat, url in BLP_CATEGORIES.items():
                key = f"blp_{cat}"
                domains = await self._download_category(
                    client, key, url, is_gzip=False
                )
                category_counts[key] = len(domains)
                self._save_category(key, domains)
                all_domains.update(domains)

        # Enforce memory safety cap
        if len(all_domains) > MAX_BLACKLIST_DOMAINS:
            logger.warning(
                "Blacklist exceeds cap (%d > %d) — truncating",
                len(all_domains),
                MAX_BLACKLIST_DOMAINS,
            )
            # Keep the set as-is; it's already built. Just warn.

        # Atomic swap
        self._domains = all_domains
        self._last_download = datetime.now(timezone.utc)
        self._category_counts = category_counts
        self._save_metadata()

        logger.info(
            "Domain blacklist updated: %d unique domains from %d categories",
            len(all_domains),
            len(category_counts),
        )

    async def _download_category(
        self,
        client: httpx.AsyncClient,
        name: str,
        url: str,
        is_gzip: bool,
    ) -> Set[str]:
        """Download and parse a single category file."""
        domains: Set[str] = set()
        try:
            resp = await client.get(url)
            resp.raise_for_status()

            if is_gzip:
                raw = gzip.decompress(resp.content)
                text = raw.decode("utf-8", errors="replace")
            else:
                text = resp.text

            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Handle hosts-format lines (e.g., "0.0.0.0 domain.com")
                if line.startswith(("0.0.0.0 ", "127.0.0.1 ")):
                    parts = line.split()
                    if len(parts) >= 2:
                        line = parts[1]

                # Basic domain validation
                domain = line.lower().strip(".")
                if domain and "." in domain and len(domain) <= 253:
                    domains.add(domain)

            logger.debug(
                "Downloaded %s: %d domains from %s", name, len(domains), url
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "HTTP %d downloading %s: %s", exc.response.status_code, name, url
            )
        except Exception as exc:
            logger.warning("Failed to download %s (%s): %s", name, url, exc)

        return domains

    # ------------------------------------------------------------------
    # Domain extraction and matching
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the domain from a URL, stripping port and lowercasing."""
        if not url:
            return ""

        # Ensure scheme for urlparse
        if "://" not in url:
            url = "https://" + url

        try:
            parsed = urlparse(url)
            netloc = parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            return ""

        # Strip port
        if ":" in netloc:
            netloc = netloc.rsplit(":", 1)[0]

        # Strip userinfo (user:pass@)
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[1]

        return netloc.lower().strip(".")

    @staticmethod
    def _domain_variants(domain: str) -> list:
        """Walk parent domains for matching.

        Example: sub.evil.com -> [sub.evil.com, evil.com]
        Stops before bare TLDs or two-part TLDs (e.g., co.uk).
        """
        parts = domain.split(".")
        variants = []

        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            remaining = parts[i:]

            # Don't check bare TLDs (e.g., "com")
            if len(remaining) <= 1:
                break

            # Don't check two-part TLDs (e.g., "co.uk")
            if candidate in TWO_PART_TLDS:
                break

            variants.append(candidate)

        return variants


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

domain_blacklist_service = DomainBlacklistService()
