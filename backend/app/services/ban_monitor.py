"""
Fail2ban ban monitor — queries banned IPs hourly and caches the results.

Runs as a background task so the admin endpoint doesn't shell out on every request.
"""

import asyncio
import json
import logging
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ip-api.com batch endpoint — free tier, no key required, 100 IPs per request.
# Returns full country names directly so no pycountry resolution needed.
_GEO_BATCH_URL = "http://ip-api.com/batch"
_GEO_FIELDS = "status,country,countryCode,regionName,city,isp,query"
_GEO_BATCH_SIZE = 100


@dataclass
class BannedIP:
    ip: str
    jail: str
    city: str | None = None
    region: str | None = None
    country: str | None = None       # 2-letter ISO code
    country_name: str | None = None  # Full country name (e.g. "United States")
    org: str | None = None
    hostname: str | None = None


@dataclass
class BanSnapshot:
    """Cached snapshot of fail2ban state."""
    banned_ips: list[BannedIP] = field(default_factory=list)
    total_banned: int = 0
    currently_banned: int = 0
    total_failed: int = 0
    last_updated: float = 0.0


_snapshot = BanSnapshot()

# Geo cache: persists across refreshes so each IP is looked up only once.
# Avoids hammering the rate limit when hundreds of IPs are banned.
_geo_cache: dict[str, dict] = {}


def get_ban_snapshot() -> BanSnapshot:
    """Return the current cached ban snapshot."""
    return _snapshot


async def refresh_ban_snapshot() -> BanSnapshot:
    """Force an immediate refresh of the ban snapshot (admin-triggered)."""
    global _snapshot
    loop = asyncio.get_event_loop()
    _snapshot = await loop.run_in_executor(None, _query_fail2ban)
    return _snapshot


def _lookup_ip_geo_batch(ips: list[str]) -> dict[str, dict]:
    """Look up geolocation for a list of IPs via ip-api.com batch endpoint.

    - Already-cached IPs are served from _geo_cache without any network call.
    - Uncached IPs are fetched in batches of up to 100 per request.
    - Failed lookups return {} and are NOT stored in the cache.
    - Returns a mapping of {ip: geo_dict} for all IPs in the input list.
    """
    unique_ips = list(dict.fromkeys(ips))  # Deduplicate, preserve order
    result: dict[str, dict] = {}

    uncached = []
    for ip in unique_ips:
        if ip in _geo_cache:
            result[ip] = _geo_cache[ip]
        else:
            uncached.append(ip)

    if not uncached:
        return result

    for i in range(0, len(uncached), _GEO_BATCH_SIZE):
        batch = uncached[i:i + _GEO_BATCH_SIZE]
        try:
            body = json.dumps(batch).encode()
            req = urllib.request.Request(
                f"{_GEO_BATCH_URL}?fields={_GEO_FIELDS}",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "ZenithGrid-BanMonitor",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                entries = json.loads(resp.read())

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                ip = entry.get("query")
                if not ip:
                    continue
                if entry.get("status") != "success":
                    result[ip] = {}
                    continue
                geo = {
                    "city": entry.get("city"),
                    "region": entry.get("regionName"),
                    "country": entry.get("countryCode"),
                    "country_name": entry.get("country"),
                    "org": entry.get("isp"),
                    "hostname": None,
                }
                _geo_cache[ip] = geo
                result[ip] = geo

        except Exception as e:
            logger.debug(f"Geo batch lookup failed (batch starting {batch[0]}): {e}")
            for ip in batch:
                result.setdefault(ip, {})

    return result


def _query_fail2ban() -> BanSnapshot:
    """Query fail2ban-client for current ban status. Runs synchronously (subprocess)."""
    snapshot = BanSnapshot(last_updated=time.time())

    try:
        # Get jail list
        result = subprocess.run(
            ["sudo", "fail2ban-client", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(f"fail2ban-client status failed: {result.stderr}")
            return snapshot

        # Parse jail names
        jails = []
        for line in result.stdout.splitlines():
            if "Jail list:" in line:
                jails = [j.strip() for j in line.split(":", 1)[1].split(",") if j.strip()]

        # Pass 1: query each jail, collect (ip, jail) pairs and counts
        raw_bans: list[tuple[str, str]] = []  # (ip, jail)
        for jail in jails:
            jail_result = subprocess.run(
                ["sudo", "fail2ban-client", "status", jail],
                capture_output=True, text=True, timeout=10,
            )
            if jail_result.returncode != 0:
                continue

            for line in jail_result.stdout.splitlines():
                line = line.strip()
                if "Currently banned:" in line:
                    try:
                        snapshot.currently_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total banned:" in line:
                    try:
                        snapshot.total_banned += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Total failed:" in line:
                    try:
                        snapshot.total_failed += int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                elif "Banned IP list:" in line:
                    for ip in line.split(":", 1)[1].strip().split():
                        if ip.strip():
                            raw_bans.append((ip.strip(), jail))

        # Pass 2: batch geo lookup for all unique IPs (cache-aware)
        all_ips = [ip for ip, _ in raw_bans]
        geo_map = _lookup_ip_geo_batch(all_ips)

        for ip, jail in raw_bans:
            geo = geo_map.get(ip, {})
            snapshot.banned_ips.append(BannedIP(
                ip=ip, jail=jail,
                city=geo.get("city"),
                region=geo.get("region"),
                country=geo.get("country"),
                country_name=geo.get("country_name"),
                org=geo.get("org"),
                hostname=geo.get("hostname"),
            ))

    except subprocess.TimeoutExpired:
        logger.warning("fail2ban-client timed out")
    except FileNotFoundError:
        logger.info("fail2ban-client not found — ban monitor disabled")
    except Exception as e:
        logger.error(f"Ban monitor error: {e}")

    return snapshot


async def run_ban_monitor_once(session_maker=None):
    """Query fail2ban and cache the result. Called by APScheduler every 24 hours."""
    global _snapshot
    try:
        loop = asyncio.get_event_loop()
        _snapshot = await loop.run_in_executor(None, _query_fail2ban)
        logger.info(
            f"Ban monitor: {_snapshot.currently_banned} currently banned, "
            f"{_snapshot.total_banned} total banned"
        )
    except Exception as e:
        logger.error(f"Ban monitor error: {e}")
