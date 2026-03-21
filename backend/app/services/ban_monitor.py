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


@dataclass
class BannedIP:
    ip: str
    jail: str
    city: str | None = None
    region: str | None = None
    country: str | None = None
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
# Avoids hammering ipinfo.io rate limits when hundreds of IPs are banned.
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


def _lookup_ip_geo(ip: str) -> dict:
    """Look up IP geolocation via ipinfo.io (free, no key needed for basic data).

    Results are cached in _geo_cache so each IP is only queried once per process
    lifetime — avoids rate-limiting when hundreds of IPs are banned.
    """
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        req = urllib.request.Request(
            f"https://ipinfo.io/{ip}/json",
            headers={"Accept": "application/json", "User-Agent": "ZenithGrid-BanMonitor"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            result = {
                "city": data.get("city"),
                "region": data.get("region"),
                "country": data.get("country"),
                "org": data.get("org"),
                "hostname": data.get("hostname"),
            }
            _geo_cache[ip] = result
            return result
    except Exception as e:
        logger.debug(f"IP geo lookup failed for {ip}: {e}")
        return {}


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

        # Query each jail
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
                    ips = line.split(":", 1)[1].strip().split()
                    for ip in ips:
                        ip = ip.strip()
                        if ip:
                            geo = _lookup_ip_geo(ip)
                            snapshot.banned_ips.append(BannedIP(
                                ip=ip, jail=jail,
                                city=geo.get("city"),
                                region=geo.get("region"),
                                country=geo.get("country"),
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


async def ban_monitor_loop():
    """Background task: query fail2ban every hour and cache the result."""
    global _snapshot

    # Initial query after 30s startup delay
    await asyncio.sleep(30)

    while True:
        try:
            # Run subprocess in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            _snapshot = await loop.run_in_executor(None, _query_fail2ban)
            logger.info(
                f"Ban monitor: {_snapshot.currently_banned} currently banned, "
                f"{_snapshot.total_banned} total banned"
            )
        except Exception as e:
            logger.error(f"Ban monitor loop error: {e}")

        await asyncio.sleep(86400)  # Every 24 hours
